#!/usr/bin/env python3
"""spec inbound — has a packet addressed to us reached our ledger?

    spec inbound                       # reader, exits 0
    spec inbound --gate                # 0 clean · 1 findings · 2 could-not-look
    spec inbound --owed                # just the worklist, one path per line
    spec inbound --unaddressed         # the packets nobody can route mechanically
    spec inbound --peers DIR           # where the sibling repos live
    spec inbound --ledger PATH         # this corpus's reconciled view (repeatable)
    spec inbound --trackers            # peer TRACKER files naming this corpus
    spec inbound --json

WHAT THIS GATES, AND THE FAILURE IT IS BUILT ON

`docs/COHORT-OPEN-ITEMS.md` §0.2 already states the rule this enforces: a row is
created *"the moment a finding is filed anywhere: a routing packet, a proposal §8
table, a seat's spec-issue, a conformance FAIL."* The rule is right, canonical,
and was three weeks old when five packets routed to architecture by one seat were
found sitting unread — **zero of them cited by name anywhere in the receiving
tree.** They were found by a human reading the sending seat's directory.

Nothing was careless. **Cross-repo delivery in this ecosystem is: commit a
document to your own tree and trust the other party looks.** There is no
notification, no queue, and — until this gate — nothing that could even
enumerate what was addressed to you. A rule with no enforcement point is a wish,
and this is the ladder's own §3 applied to the one channel every seat depends on.

WHY THE `unaddressed` BUCKET IS THE LOAD-BEARING PART

Measured across the ecosystem at the time this was written: **577 routing
packets, 424 of them (73%) carrying a `**To:**` field.** The other 27% name their
recipient in the filename, in the prose, or nowhere at all.

So the tempting design — *"parse `To:`, keep the ones naming us"* — silently
drops a quarter of the channel into a bucket labelled **not yours**, when the
truth is **unknown**. That is `could-not-look wearing a verdict's clothes`, the
defect this toolkit has now shipped three times (`address` without
`--namespace-root`, `provenance` without `--proposal-root`, `coverage` reading
the class map). **A packet with no parseable addressee is reported in its own
bucket and is never counted as somebody else's.**

The same asymmetry governs `cc`. A packet addressed to another seat that copies
us is a lower obligation than one addressed to us, so the two are counted
separately rather than merged — but a cc is still reported, because the reason
this gate exists is a finding nobody was formally on the hook for.

WHAT IT DELIBERATELY DOES NOT DO

* **It does not check that a ledger row is correct**, or current, or that the
  item was actually handled. A citation is evidence of *attention*. A packet can
  be cited by a row that misreads it — which is exactly what happened to the
  five packets that prompted this tool, where a review scored one absorbed that
  was not.
* **It does not write.** Deciding what a packet's items are and whose they are is
  the reading; a tool that appended rows would fill the ledger with entries
  nobody stands behind.
* **It does not judge staleness.** A packet answered in a routing reply rather
  than on the ledger is reported as owed. That is intentional: the ledger is the
  reconciled view, and *"I replied once"* is the practice that produced a channel
  nobody could enumerate.

**Reader by default**, on the same reasoning as `pins`, `register` and
`coverage`: the first run against a live ecosystem scores a backlog, and a gate
that is red on day one teaches people to skip it.

Stdlib-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

CLEAN, VIOLATIONS, CANNOT_LOOK = 0, 1, 2

# The reconciled view a packet is expected to reach.
#
# **This was a one-element tuple and it made the gate unusable by every seat but
# one `[2026-09-15]`.** `AGENTS-STANDARD.md` tells every repo in the ecosystem to
# point this gate at its own tree — and only the architecture seat keeps a file at
# this path, so `spec inbound --root .` anywhere else returned COULD-NOT-LOOK.
# The generation seat found it, named this line by file:line, and correctly
# declined to widen it on the grounds that the ledger convention was not theirs
# to set. **Fifth could-not-look in this toolkit** (`address` without
# `--namespace-root`, `provenance` without `--proposal-root`, `coverage` reading
# the class map, `pins`' composition filter) — and the first where the scope was
# wrong for everyone except the author.
#
# So: a DEFAULT, not a constant. `--ledger` overrides it, and when nothing is
# passed the own-tree `TRACKER-*.md` files count as reconciled surfaces too —
# because for several seats that is where the reconciled view actually lives.
LEDGERS = ("docs/COHORT-OPEN-ITEMS.md",)

# The own-tree fallback: per-counterpart trackers. `SEAT-CLEANUP-INSTRUCTIONS`
# told every seat to keep one of these, so a seat with no COHORT-OPEN-ITEMS.md
# is not a seat with no ledger.
OWN_TRACKER_GLOB = "TRACKER-*.md"

PACKET_GLOB = "ROUTING-*.md"
PACKET_DIR = "docs/status"

# ----------------------------------------------------------------------------
# A PEER'S TRACKER ADDRESSED TO US IS AN INBOUND SURFACE, AND THE GLOB MISSED IT
#
# `iter_packets` globs `ROUTING-*`. A peer's `docs/status/TRACKER-<us>.md` is a
# standing index of everything that seat is carrying to us, it is not a
# `ROUTING-*` file, and it was therefore invisible to every run this gate has
# ever done — while being, in practice, **the surface that actually recovers
# unread packets.** Two application seats independently reported recovering
# packets by reconciling against a counterpart's tracker, one of them in about
# two minutes, in the same week a third seat reported the hardcoded-ledger
# defect above.
#
# **Counted SEPARATELY and never merged into the packet count.** A tracker is a
# standing index; a packet is a delivery event. Merging them would let one
# tracker citation discharge the packets it indexes, which is the same
# unit-mismatch that let nine numbered asks sit green behind one cited packet
# (`docs/COHORT-OPEN-ITEMS.md` §0bz). The gate reports the surface; a human
# reads it.
# ----------------------------------------------------------------------------
PEER_TRACKER_GLOB = "TRACKER-*.md"

# How this corpus is spelled when someone addresses it. Repo directory name
# plus the short forms the ecosystem actually writes — measured, not assumed:
# `arch` and `architecture` are both in live use as the To: value, and a
# matcher calibrated on the formal name alone misses 8+ packets outright.
#
# This is the same defect `register` hit twice and `ledger` once: a matcher
# calibrated against the names the rule-writer expects, rather than against the
# corpus's actual vocabulary.
# **The table held only the three repos the arch seat owns, so `--root` at any
# other tree returned COULD-NOT-LOOK** — while `AGENTS-STANDARD.md` tells every
# seat in the ecosystem to point this gate at its own tree. Measured 2026-09-10
# by running it from a cohort tree to check whether a relay addressed to that
# seat was visible: it was not, and the reason was this table, not the packet.
# Extended from the addressee vocabulary actually in use across the estate's
# `ROUTING-*` files, counted rather than guessed.
#
# `names_us` matches on word boundaries that exclude `-`, so a short form is
# never a substring hit: `core-rust` does not fire inside `entity-core-rust`,
# `rust` does not fire inside `entity-browser-rust`, and each alias only ever
# matches a genuinely bare token.
#
# **Bare `go` is the one alias with a plausible false positive** — the English
# verb, inside a `To:`/`cc:` clause ("this should go to arch"). It is kept
# deliberately: for an INBOX gate, over-reporting is the safe direction. A
# spurious row is read once and dismissed; a packet that never appears is the
# failure this gate exists to prevent.
ALIASES: Dict[str, Tuple[str, ...]] = {
    "entity-system-architecture": ("entity-system-architecture", "arch",
                                   "architecture"),
    "entity-core-protocol": ("entity-core-protocol", "core-protocol"),
    "entity-system-arch-tools": ("entity-system-arch-tools", "arch-tools"),
    "entity-core-go": ("entity-core-go", "core-go", "go"),
    "entity-core-rust": ("entity-core-rust", "core-rust", "rust"),
    "entity-core-py": ("entity-core-py", "core-py", "py"),
    "entity-core-keystone": ("entity-core-keystone", "core-keystone",
                             "keystone"),
    "entity-core-formalization": ("entity-core-formalization",
                                  "core-formalization", "formalization"),
    "entity-browser-rust": ("entity-browser-rust", "browser-rust"),
    "entity-workbench-go": ("entity-workbench-go", "workbench-go"),
    "entity-system-generator": ("entity-system-generator", "generator"),
}

# `**To:** X · **From:** Y` puts both on one line, so the value terminates at
# the next bold marker, never at the end of the line.
TO_FIELD = re.compile(r"\*\*\s*(?:To|TO|to)\s*:?\s*\*\*\s*([^\n]*)")
BOLD_STOP = re.compile(r"\*\*")

# A cc may be its own bold field or ride inside the To: value. Three inline
# spellings occur and all three must be stripped before the To: value is
# tested, or a packet that merely copies us reads as addressed to us.
#
# The comma form was missing until 2026-09-09, when
# `**To:** `entity-core-go` (`ext/network`), cc `entity-system-architecture``
# scored as `to`. That over-reports what we owe.
CC_FIELD = re.compile(r"\*\*\s*cc\s*:?\s*\*\*\s*([^\n]*)", re.I)
CC_INLINE = re.compile(
    r"\(\s*cc[:\s]([^)]*)\)"      # (cc X)
    r"|—\s*cc[:\s]\s*([^\n]*)"    # — cc X
    r"|,\s*cc[:\s]\s*([^\n]*)",   # , cc X
    re.I)

# `entity-core-{go,rust,py}` — expanded so a brace list is not read as one
# unknown seat, and so it cannot accidentally substring-match an alias.
BRACE = re.compile(r"([a-z0-9-]+)-\{([a-z0-9,\s-]+)\}")


def expand_braces(text: str) -> str:
    def sub(m: re.Match) -> str:
        stem, inner = m.group(1), m.group(2)
        return " ".join("%s-%s" % (stem, p.strip())
                        for p in inner.split(",") if p.strip())
    return BRACE.sub(sub, text)


def field_value(text: str, pat: re.Pattern) -> Optional[str]:
    """The value of a bold field, terminated at the next bold marker."""
    m = pat.search(text)
    if not m:
        return None
    val = m.group(1)
    stop = BOLD_STOP.search(val)
    if stop:
        val = val[:stop.start()]
    return val.strip()


def names_us(value: str, aliases: Tuple[str, ...]) -> bool:
    """True when an addressee clause names this corpus.

    Matched on word boundaries after brace expansion. A bare substring test
    would let `entity-system-arch-tools` satisfy a query for `arch`, which
    over-credits in the direction that reports a false clean.
    """
    hay = expand_braces(value.lower())
    for a in aliases:
        if re.search(r"(?<![a-z0-9-])%s(?![a-z0-9-])" % re.escape(a.lower()),
                     hay):
            return True
    return False


def classify(text: str, aliases: Tuple[str, ...]) -> str:
    """`to` · `cc` · `other` · `unaddressed` — and the last is not `other`."""
    to = field_value(text, TO_FIELD)

    cc_parts: List[str] = []
    cc = field_value(text, CC_FIELD)
    if cc:
        cc_parts.append(cc)
    for m in CC_INLINE.finditer(text[:4000]):
        cc_parts.append(m.group(1) or m.group(2) or m.group(3) or "")

    if to is not None:
        # A cc clause living inside the To: value must not make the packet read
        # as addressed to us — strip what we recognised as cc before testing.
        primary = to
        for c in cc_parts:
            if c and c in primary:
                primary = primary.replace(c, " ")
        primary = CC_INLINE.sub(" ", primary)
        if names_us(primary, aliases):
            return "to"
        if any(names_us(c, aliases) for c in cc_parts if c):
            return "cc"
        return "other"

    if any(names_us(c, aliases) for c in cc_parts if c):
        return "cc"
    return "unaddressed"


def stem_of(name: str) -> str:
    return name[:-3] if name.endswith(".md") else name


# How a ledger actually cites a packet, measured rather than assumed:
# `ROUTING-2026-08-20-e`, not
# `ROUTING-2026-08-20-e-core-go-the-fourth-pass-closes-...`. Both forms occur.
#
# **A first cut of this gate required the full stem and reported 0 of 210
# cited** — the identical defect `register` shipped twice ("0 of 97" where the
# truth was 2) and `ledger` once. A matcher calibrated on the name the
# rule-writer expects is not a census of the corpus's vocabulary. It is written
# down here because three tools in this toolkit have now made it.
# A segment MAY contain an internal `.` or `_`, because real packet filenames do:
# `ROUTING-2026-08-04-s10.3-seam-...` names a spec section in its slug. With
# `[A-Za-z0-9]+` alone the match stopped at `...-08-04-s10`, the leading-clause
# test then failed on `.3-seam`, and **that packet was uncitable by any
# spelling** — it reported `owed` however correctly the ledger named it. Fifth
# matcher in this toolkit calibrated against the spelling the rule-writer
# expected rather than the corpus's actual vocabulary.
#
# The trailing character must stay alphanumeric so a citation ending a sentence
# does not swallow the full stop into the identifier.
CITATION = re.compile(
    r"ROUTING-\d{4}-\d{2}-\d{2}(?:-[A-Za-z0-9]+(?:[._][A-Za-z0-9]+)*)*")

# The shortest citation that may credit anything. A bare `ROUTING-<date>` names
# a day, not a document, and on a busy day that is up to nine packets — so a
# date-only mention is recorded as too coarse rather than allowed to credit.
MIN_CITE_PARTS = 5  # ROUTING + Y + M + D + at least one discriminator


def ledger_citations(text: str) -> List[str]:
    """Every packet citation the ledger makes, longest first."""
    # A ledger may cite the FILENAME rather than the stem. Allowing internal
    # dots (so `...-s10.3-seam-...` matches at all) means `.md` is now a legal
    # continuation, and `...-federation.md` reaches no packet — the mirror of
    # the defect the dot support was added for, introduced by the same edit and
    # caught by the same run. Strip a known document extension after matching.
    seen = {t[:-3] if t.endswith(".md") else t
            for t in CITATION.findall(text)
            if len(t.split("-")) >= MIN_CITE_PARTS}
    return sorted(seen, key=len, reverse=True)


def cites(stem: str, tokens: List[str]) -> Optional[str]:
    """The ledger token that reaches this packet, or None.

    A **leading clause** of the stem, not a bare substring: the citation is an
    identifier prefix, and requiring the next character to be a separator stops
    `ROUTING-2026-09-06-b` from crediting `...-09-06-bb`.
    """
    for t in tokens:
        if stem == t or stem.startswith(t + "-"):
            return t
    return None


def citing_tokens(stem: str, tokens: List[str]) -> List[str]:
    """EVERY ledger token that reaches this packet, not just the longest.

    Settling the ambiguity question needs the whole set, not one match: a
    packet reached by its full stem AND by a bare `date-letter` is genuinely
    cited, and one reached ONLY by the bare id is not. `cites` returns the
    longest and cannot tell those apart.
    """
    return [t for t in tokens if stem == t or stem.startswith(t + "-")]


def iter_packets(peers: Path, self_name: str) -> List[Path]:
    found: List[Path] = []
    for repo in sorted(p for p in peers.iterdir() if p.is_dir()):
        if repo.name == self_name or repo.name.startswith("."):
            continue
        d = repo / PACKET_DIR
        if not d.is_dir():
            continue
        found.extend(sorted(d.glob(PACKET_GLOB)))
    return found


def peer_trackers(peers: Path, self_name: str,
                  aliases: Tuple[str, ...]) -> List[Path]:
    """A sibling's `docs/status/TRACKER-<us>.md` — a standing index aimed at us.

    Matched on the filename's alias token rather than on file contents, because
    a tracker names its counterpart in its own name and that is the cheap,
    unambiguous signal. `names_us` is reused so the substring guard that keeps
    `rust` from firing inside `entity-browser-rust` applies here too.
    """
    found: List[Path] = []
    for repo in sorted(pp for pp in peers.iterdir() if pp.is_dir()):
        if repo.name == self_name or repo.name.startswith("."):
            continue
        d = repo / PACKET_DIR
        if not d.is_dir():
            continue
        for f in sorted(d.glob(PEER_TRACKER_GLOB)):
            # strip the `TRACKER-` prefix and the extension before matching, so
            # `TRACKER-entity-system-architecture.md` yields the bare name.
            subject = f.stem[len("TRACKER-"):]
            if names_us(subject, aliases):
                found.append(f)
    return found


def dedupe_clones(packets: List[Path]) -> Tuple[List[Path], List[dict]]:
    """Collapse byte-identical packets held by working clones of one repository.

    **A packet is ONE obligation however many checkouts hold it.** This scope is
    a directory of directories, and several of those directories are working
    clones of the same repository at different tips — measured 2026-09-09, nine
    of them were clones of two repos, and *every* packet in four of them was a
    byte-identical copy of one already counted. That inflated the owed figure
    this gate publishes by 194 -> 135, about 30%, and the inflation is invisible
    because each copy is a real file with a real addressee block.

    Canonical copy = the one under the directory holding the MOST scanned
    packets (ties broken by name). A stale clone is a strict subset of the live
    tree's history, so the fullest directory is the live one, and attributing
    the obligation there is what makes the per-seat table actionable.

    Deduping only ever LOWERS an accusation, which is the direction an
    instrument reporting on five seats at once has to be wrong in.
    """
    per_dir: Dict[str, int] = {}
    for p in packets:
        per_dir[p.parents[2].name] = per_dir.get(p.parents[2].name, 0) + 1

    # **The key is FILENAME + content digest, and the filename half is not
    # decoration.** A first cut keyed on content alone and collapsed two
    # genuinely distinct packets from ONE seat that happened to share a short
    # body — caught by four existing assertions in the self-test, which is what
    # that suite is for. A clone copy is the same path suffix with the same
    # bytes; two files with different names are two packets whatever they say.
    groups: Dict[Tuple[str, str], List[Path]] = {}
    for p in packets:
        try:
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError:
            digest = "unreadable:%s" % p
        groups.setdefault((p.name, digest), []).append(p)

    canonical: List[Path] = []
    collapsed: List[dict] = []
    for _key, group in groups.items():
        best = max(group, key=lambda q: (per_dir[q.parents[2].name],
                                         q.parents[2].name))
        canonical.append(best)
        for other in group:
            if other != best:
                collapsed.append({"file": str(other),
                                  "seat": other.parents[2].name,
                                  "same_as": str(best)})
    canonical.sort()
    return canonical, collapsed


def scan(root: Path, peers: Optional[Path] = None,
         ledgers: Optional[List[str]] = None) -> Tuple[int, dict]:
    root = root.resolve()
    self_name = root.name
    aliases = ALIASES.get(self_name)
    if aliases is None:
        return CANNOT_LOOK, {
            "error": "no addressee aliases known for %r — this gate cannot "
                     "tell what 'addressed to us' means for this corpus, "
                     "which is a could-not-look and not a clean channel"
                     % self_name}

    if peers is None:
        peers = root.parent
    peers = peers.resolve()
    if not peers.is_dir():
        return CANNOT_LOOK, {
            "error": "peer root %s is not a directory — nothing was scanned"
                     % peers}

    # --- which files are this corpus's reconciled view? -------------------
    # Explicit `--ledger` wins outright. Otherwise the default path, PLUS the
    # own-tree per-counterpart trackers — a seat that keeps only trackers has a
    # ledger, and reporting it as could-not-look was the defect.
    explicit = bool(ledgers)
    candidates: List[str] = list(ledgers) if ledgers else list(LEDGERS)
    if not explicit and not any((root / rel).is_file() for rel in candidates):
        # FALLBACK ONLY, and the "only" is the whole safety argument.
        #
        # The defect was COULD-NOT-LOOK for a seat with no file at the default
        # path. Adding trackers *beside* an existing ledger would instead widen
        # what counts as a discharge — and for an inbox gate, over-crediting is
        # the dangerous direction: a spurious row is read once and dismissed, a
        # packet that never appears is the failure this gate exists to prevent.
        # So trackers stand in for a missing ledger; they never supplement one.
        own = root / PACKET_DIR
        if own.is_dir():
            candidates = ["%s/%s" % (PACKET_DIR, f.name)
                          for f in sorted(own.glob(OWN_TRACKER_GLOB))]

    ledger_text = ""
    seen_ledger = []
    for rel in candidates:
        p = root / rel
        if p.is_file():
            try:
                ledger_text += p.read_text(encoding="utf-8", errors="ignore")
                seen_ledger.append(rel)
            except OSError:
                pass
    if not seen_ledger:
        return CANNOT_LOOK, {
            "error": "none of %s exist under %s — there is nothing to "
                     "reconcile packets against. Pass --ledger PATH if this "
                     "corpus keeps its reconciled view somewhere else; a "
                     "missing default is not an empty inbox"
                     % (", ".join(candidates), root)}

    trackers = peer_trackers(peers, self_name, aliases)
    tracker_recs = [{"file": str(t), "seat": t.parents[2].name}
                    for t in trackers]

    packets = iter_packets(peers, self_name)
    packets, collapsed = dedupe_clones(packets)
    if not packets:
        return CANNOT_LOOK, {
            "error": "no %s found under any sibling's %s below %s — the scope "
                     "matched nothing, which is not an empty inbox"
                     % (PACKET_GLOB, PACKET_DIR, peers)}

    tokens = ledger_citations(ledger_text)

    owed: List[dict] = []
    cited: List[str] = []
    cc_owed: List[dict] = []
    unaddressed: List[dict] = []
    ambiguous_credit: List[dict] = []
    other = 0
    by_seat: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # PASS 1 — classify, and map every token to every packet it reaches.
    #
    # This used to be one pass that credited a packet the moment `cites`
    # returned a hit, and computed `reach` from those hits afterwards. So a
    # token reaching five packets DISCHARGED ALL FIVE, and the run printed
    # "-> 5 packets" in its own summary while doing it: the ambiguity was
    # reported as a note and consumed as a credit.
    #
    # Measured when it was found (2026-09-11): a bare `ROUTING-2026-09-10-c`
    # on arch's ledger, naming entity-core-go's packet, silently discharged
    # entity-workbench-go's UNRELATED packet of the same id. Found by hand.
    # A `date-letter` id is unique to one repo on one day, which is not
    # unique, so this is a standing property of the naming scheme and not a
    # one-off.
    # ------------------------------------------------------------------
    reach: Dict[str, List[str]] = {}
    staged: List[Tuple[dict, List[str]]] = []

    for p in packets:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            text = ""
        kind = classify(text, aliases)
        if kind == "other":
            other += 1
            continue

        seat = p.parents[2].name
        stem = stem_of(p.name)
        rec = {"file": str(p), "seat": seat, "stem": stem, "kind": kind}
        if kind == "unaddressed":
            unaddressed.append(rec)
            continue

        hits = citing_tokens(stem, tokens)
        for t in hits:
            reach.setdefault(t, []).append(str(p))
        staged.append((rec, hits))

    # ------------------------------------------------------------------
    # PASS 2 — a token that reaches more than one packet discharges NONE of
    # them. It is could-not-look at the level of a single row: the citation
    # cannot be resolved by a reader, which is the whole reason the standard
    # says to cite a packet by its full stem.
    #
    # Its own bucket, never folded into `cited` and never into `owed` — the
    # same design as `unaddressed`, and for the same reason. Silently
    # crediting hides a real obligation; silently owing manufactures work
    # against a row that may well exist. UNKNOWN is the honest answer and it
    # is the one a human can act on in a minute.
    # ------------------------------------------------------------------
    for rec, hits in staged:
        resolving = [t for t in hits if len(reach[t]) == 1]
        if resolving:
            cited.append(rec["file"])
            continue
        if hits:
            ambiguous_credit.append(dict(rec, cited_by=sorted(hits)))
            continue
        if rec["kind"] == "to":
            owed.append(rec)
            by_seat[rec["seat"]] = by_seat.get(rec["seat"], 0) + 1
        else:
            cc_owed.append(rec)

    ambiguous = [{"citation": t, "matches": v}
                 for t, v in sorted(reach.items()) if len(v) > 1]

    res = {
        "root": str(root),
        "peers": str(peers),
        "ledgers": seen_ledger,
        "scanned": len(packets),
        "collapsed_clones": collapsed,
        "clone_seats": sorted({c["seat"] for c in collapsed}),
        "addressed_to_us": len(owed) + len(cited) + len(ambiguous_credit),
        "cited": len(cited),
        "owed": owed,
        "cc_owed": cc_owed,
        "unaddressed": unaddressed,
        "ambiguous_credit": ambiguous_credit,
        "ambiguous_citations": ambiguous,
        "addressed_elsewhere": other,
        "by_seat": by_seat,
        # A standing index a peer keeps aimed at us. Reported, never merged:
        # a tracker is not a delivery event and must not discharge one.
        "peer_trackers": tracker_recs,
        "ledger_default_used": not explicit,
    }
    return (VIOLATIONS if owed else CLEAN), res


def report(res: dict, gate: bool, owed_only: bool, unaddressed_only: bool,
           trackers_only: bool = False) -> None:
    if "error" in res:
        print("could not look: %s" % res["error"], file=sys.stderr)
        return
    if owed_only:
        for o in res["owed"]:
            print(o["file"])
        return
    if unaddressed_only:
        for o in res["unaddressed"]:
            print(o["file"])
        return
    if trackers_only:
        for t in res.get("peer_trackers", []):
            print(t["file"])
        return

    for seat in sorted(res["by_seat"], key=lambda k: -res["by_seat"][k]):
        print("  %-32s %4d owed" % (seat, res["by_seat"][seat]))
    print("\n%d routing packet(s) under %s — %d addressed here, %d already on "
          "the ledger, %d owed."
          % (res["scanned"], res["peers"], res["addressed_to_us"],
             res["cited"], len(res["owed"])))
    if res["collapsed_clones"]:
        print("%d further file(s) are byte-identical copies of a packet already "
              "counted, held by working clones of the same repository (%s) — a "
              "packet is ONE obligation however many checkouts hold it."
              % (len(res["collapsed_clones"]), ", ".join(res["clone_seats"])))
    if res["cc_owed"]:
        print("%d further packet(s) copy us without addressing us — a lower "
              "obligation, counted separately, not merged."
              % len(res["cc_owed"]))
    if res.get("peer_trackers"):
        seats = sorted({t["seat"] for t in res["peer_trackers"]})
        print("%d peer TRACKER file(s) name this corpus (%s) — a standing index "
              "of what those seats are carrying to us. NOT counted above and "
              "never discharged by a citation: a tracker is an index, a packet "
              "is a delivery event. Read them."
              % (len(res["peer_trackers"]), ", ".join(seats)))
        for t in res["peer_trackers"]:
            print("    %s" % t["file"])
    if res["unaddressed"]:
        print("%d packet(s) name no recipient this gate can parse. That is "
              "UNKNOWN, never 'not ours' — read them or give them a **To:** "
              "field." % len(res["unaddressed"]))
    if res["ambiguous_citations"]:
        print("%d ledger citation(s) reach more than one packet — the id "
              "names a day and a letter, which is not unique across repos:"
              % len(res["ambiguous_citations"]))
        for a in res["ambiguous_citations"]:
            print("    %s -> %d packets" % (a["citation"], len(a["matches"])))
    if res.get("ambiguous_credit"):
        print("%d packet(s) are reached ONLY by such a citation and are "
              "therefore NEITHER cited nor owed — that is UNKNOWN, and it is "
              "one lookup to settle. Re-cite the row by FULL STEM:"
              % len(res["ambiguous_credit"]))
        for a in res["ambiguous_credit"]:
            print("    %s\n        reached only by: %s"
                  % (a["file"], ", ".join(a["cited_by"])))
    print("a ledger row is evidence of ATTENTION, never that the item was "
          "read correctly.")
    if not gate:
        print("reader mode — exits 0. Run with --gate to enforce.")
    print("to discharge one: add a row to %s citing the packet by name."
          % ", ".join(res["ledgers"]))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=None,
                    help="corpus root (default: --corpus / $SPEC_CORPUS / cwd)")
    ap.add_argument("--peers", type=Path, default=None,
                    help="directory holding the sibling repos "
                         "(default: the corpus root's parent)")
    ap.add_argument("--gate", action="store_true",
                    help="exit non-zero on findings (default: reader, exits 0)")
    ap.add_argument("--owed", action="store_true",
                    help="print only the worklist, one path per line")
    ap.add_argument("--unaddressed", action="store_true",
                    help="print the packets with no parseable recipient")
    ap.add_argument("--ledger", action="append", default=None, metavar="PATH",
                    help="corpus-relative path to a reconciled-view document; "
                         "repeatable. Default: docs/COHORT-OPEN-ITEMS.md plus "
                         "this tree's own docs/status/TRACKER-*.md")
    ap.add_argument("--trackers", action="store_true",
                    help="print only the peer TRACKER files naming this corpus")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)

    root = args.root
    if root is None:
        try:
            import config as _config
            root = _config.corpus_root()
        except Exception:  # noqa: BLE001
            root = Path.cwd()

    code, res = scan(Path(root), args.peers, args.ledger)
    if args.json:
        print(json.dumps(res, indent=1))
    else:
        report(res, args.gate, args.owed, args.unaddressed,
               args.trackers)
    if code == CANNOT_LOOK:
        return CANNOT_LOOK
    return code if args.gate else CLEAN


if __name__ == "__main__":
    raise SystemExit(main())
