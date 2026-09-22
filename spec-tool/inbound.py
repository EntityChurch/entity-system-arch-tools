#!/usr/bin/env python3
"""spec inbound — has a packet addressed to us reached our ledger?

    spec inbound                       # reader, exits 0
    spec inbound --gate                # 0 clean · 1 findings · 2 could-not-look
    spec inbound --owed                # just the worklist, one path per line
    spec inbound --unaddressed         # the packets nobody can route mechanically
    spec inbound --peers DIR           # where the sibling repos live
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
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

CLEAN, VIOLATIONS, CANNOT_LOOK = 0, 1, 2

# The reconciled view a packet is expected to reach. Kept as a list so a repo
# that splits its ledger does not silently lose the check.
LEDGERS = ("docs/COHORT-OPEN-ITEMS.md",)

PACKET_GLOB = "ROUTING-*.md"
PACKET_DIR = "docs/status"

# How this corpus is spelled when someone addresses it. Repo directory name
# plus the short forms the ecosystem actually writes — measured, not assumed:
# `arch` and `architecture` are both in live use as the To: value, and a
# matcher calibrated on the formal name alone misses 8+ packets outright.
#
# This is the same defect `register` hit twice and `ledger` once: a matcher
# calibrated against the names the rule-writer expects, rather than against the
# corpus's actual vocabulary.
ALIASES: Dict[str, Tuple[str, ...]] = {
    "entity-system-architecture": ("entity-system-architecture", "arch",
                                   "architecture"),
    "entity-core-protocol": ("entity-core-protocol", "core-protocol"),
    "entity-system-arch-tools": ("entity-system-arch-tools", "arch-tools"),
}

# `**To:** X · **From:** Y` puts both on one line, so the value terminates at
# the next bold marker, never at the end of the line.
TO_FIELD = re.compile(r"\*\*\s*(?:To|TO|to)\s*:?\s*\*\*\s*([^\n]*)")
BOLD_STOP = re.compile(r"\*\*")

# A cc may be its own bold field or a parenthetical inside the To: value.
CC_FIELD = re.compile(r"\*\*\s*cc\s*:?\s*\*\*\s*([^\n]*)", re.I)
CC_INLINE = re.compile(r"\(\s*cc[:\s]([^)]*)\)|—\s*cc\s+([^\n]*)", re.I)

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
        cc_parts.append(m.group(1) or m.group(2) or "")

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
CITATION = re.compile(r"ROUTING-\d{4}-\d{2}-\d{2}(?:-[A-Za-z0-9]+)*")

# The shortest citation that may credit anything. A bare `ROUTING-<date>` names
# a day, not a document, and on a busy day that is up to nine packets — so a
# date-only mention is recorded as too coarse rather than allowed to credit.
MIN_CITE_PARTS = 5  # ROUTING + Y + M + D + at least one discriminator


def ledger_citations(text: str) -> List[str]:
    """Every packet citation the ledger makes, longest first."""
    seen = {t for t in CITATION.findall(text)
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


def scan(root: Path, peers: Optional[Path] = None) -> Tuple[int, dict]:
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

    ledger_text = ""
    seen_ledger = []
    for rel in LEDGERS:
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
                     "reconcile packets against" % (", ".join(LEDGERS), root)}

    packets = iter_packets(peers, self_name)
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
    other = 0
    by_seat: Dict[str, int] = {}
    # token -> every scanned packet it reaches. A token reaching more than one
    # is an ambiguous identifier, which is a finding about the NAMING scheme
    # and not about routing, so it is reported in its own bucket.
    reach: Dict[str, List[str]] = {}

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

        hit = cites(stem, tokens)
        if hit:
            reach.setdefault(hit, []).append(str(p))
            cited.append(str(p))
            continue
        if kind == "to":
            owed.append(rec)
            by_seat[seat] = by_seat.get(seat, 0) + 1
        else:
            cc_owed.append(rec)

    ambiguous = [{"citation": t, "matches": v}
                 for t, v in sorted(reach.items()) if len(v) > 1]

    res = {
        "root": str(root),
        "peers": str(peers),
        "ledgers": seen_ledger,
        "scanned": len(packets),
        "addressed_to_us": len(owed) + len(cited),
        "cited": len(cited),
        "owed": owed,
        "cc_owed": cc_owed,
        "unaddressed": unaddressed,
        "ambiguous_citations": ambiguous,
        "addressed_elsewhere": other,
        "by_seat": by_seat,
    }
    return (VIOLATIONS if owed else CLEAN), res


def report(res: dict, gate: bool, owed_only: bool, unaddressed_only: bool
           ) -> None:
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

    for seat in sorted(res["by_seat"], key=lambda k: -res["by_seat"][k]):
        print("  %-32s %4d owed" % (seat, res["by_seat"][seat]))
    print("\n%d routing packet(s) under %s — %d addressed here, %d already on "
          "the ledger, %d owed."
          % (res["scanned"], res["peers"], res["addressed_to_us"],
             res["cited"], len(res["owed"])))
    if res["cc_owed"]:
        print("%d further packet(s) copy us without addressing us — a lower "
              "obligation, counted separately, not merged."
              % len(res["cc_owed"]))
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
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)

    root = args.root
    if root is None:
        try:
            import config as _config
            root = _config.corpus_root()
        except Exception:  # noqa: BLE001
            root = Path.cwd()

    code, res = scan(Path(root), args.peers)
    if args.json:
        print(json.dumps(res, indent=1))
    else:
        report(res, args.gate, args.owed, args.unaddressed)
    if code == CANNOT_LOOK:
        return CANNOT_LOOK
    return code if args.gate else CLEAN


if __name__ == "__main__":
    raise SystemExit(main())
