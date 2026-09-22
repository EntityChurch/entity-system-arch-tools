#!/usr/bin/env python3
"""spec inbound — has a packet addressed to us reached our ledger?

    spec inbound                       # reader, exits 0
    spec inbound --gate                # 0 clean · 1 findings · 2 could-not-look
    spec inbound --owed                # just the worklist, one path per line
    spec inbound --unaddressed         # the packets nobody can route mechanically
    spec inbound --peers DIR           # where the sibling repos live
    spec inbound --ledger PATH         # this corpus's reconciled view (repeatable)
    spec inbound --trackers            # peer TRACKER files naming this corpus
    spec inbound --since 2026-09-10    # the RECENT window — what is flowing now
    spec inbound --since 7d            # same, relative to today
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

WHY THERE IS A TIME WINDOW, AND WHY IT IS NEVER THE DEFAULT

**The estate carries 1,766 routing packets and writes ~30 a day.** A lifetime
count over a channel at that rate answers *"has anything ever gone unread"*,
which nobody can act on, and it drowns the question people actually have: **is
what is flowing NOW being picked up.** `--since` scopes the report to a window.

Three properties keep it honest, and each is the opposite of what the obvious
implementation does:

* **The window scopes the REPORT, never the SCAN.** Ambiguity — a `date-letter`
  citation reaching several packets — is a property of the whole corpus, so it
  is computed over every packet and then filtered. Filter first and a token
  reaching two packets, one of them outside the window, reads as resolving.
* **What the window excluded is PRINTED, every run.** A silent cap reads as
  "covered everything" when it did not. The out-of-window owed count is stated
  beside the in-window one, never dropped.
* **It dates a packet by its OWN id (`ROUTING-YYYY-MM-DD-…`), not by mtime or
  commit date.** A checkout's mtimes are the clone's, not the packet's, and
  commit dates do not survive the release boundary ([ADR-0027]) — `census`
  measured that the hard way when nine of one repo's ten commits carried one
  date. A packet's date is in its name because the naming convention put it
  there.

WHY RECIPROCITY IS REPORTED — `ask which seats keep a tracker for YOU`

Filed by `entity-core-keystone` 2026-09-16, who had it filed against them first
by `entity-system-conformance`: **twelve asks that never arrived, because the
receiving seat kept no tracker for the sending one.** Their sentence is the
rule — *"a reconciliation keyed on the trackers you KEEP cannot see the
counterpart you OMITTED"* — and it is a blind spot no other check in this
toolkit can reach, because every one of them starts from a file we wrote.

So the run prints both directions: seats keeping a standing index aimed at us
that we keep none for, and the inverse. **It never gates.** Whether a seat
warrants a tracker is a judgement about how much traffic it carries, and a gate
on it would either be permanently red or quietly mandate one file per sibling.

**Reader by default**, on the same reasoning as `pins`, `register` and
`coverage`: the first run against a live ecosystem scores a backlog, and a gate
that is red on day one teaches people to skip it.

Stdlib-only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
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
# A DOCUMENT THAT ADDRESSES US IN ITS FILENAME IS INBOUND, WHEREVER IT LIVES
#
# `iter_packets` globs `ROUTING-*` under `docs/status`. **Both halves of that
# scope are assumptions, and measured 2026-09-17 both are wrong for the seat
# that files the most asks against architecture.**
#
# `entity-core-keystone` writes `HANDOFF-TO-ARCH-<date>-<slug>.md` into
# `research/stewardship/`. Ten of them. Their own standing tracker cites those
# files as the Packet column for **14 of their 18 open asks** — so the majority
# of one seat's open set against us has never appeared in any run of this gate,
# invisible on TWO independent counts, either of which alone is enough: wrong
# directory AND wrong filename. `entity-core-go` files four more under
# `docs/validation/reports/`.
#
# This is the same class already written down for the meta seat (wrong root AND
# wrong filename) — third instance — and the generalization is the toolkit's
# own recurring one: **a scope was set once, when every inbound document was a
# `ROUTING-*` under `docs/status`, and nothing re-read it when a seat started
# writing somewhere else.** Nobody was careless: the sending seat named us in
# the filename, which is a *stronger* addressee signal than the `**To:**` field
# this gate was built to parse.
#
# So discovery is by NAME across the peer's whole tree, pruned. A filename
# containing `to-<alias>` addresses us — `HANDOFF-TO-ARCH-…`, and nothing else
# in the live estate matches by accident. Counted in its OWN class and never
# merged into the packet count, so the packet numbers stay comparable with
# every measurement this gate has published.
# ----------------------------------------------------------------------------
NAME_ADDRESSED_EXT = ".md"

# Build output, vendored copies and publish staging hold byte-copies of real
# documents. `.publish-staging` alone carries three copies of one browser-rust
# file under buildset directories. Counting those is the clone defect arriving
# by a different road.
PRUNE_DIRS = {
    ".git", ".hg", "node_modules", "target", "dist", "build", "vendor",
    ".core-pin", ".venv", "venv", "__pycache__", ".publish-staging",
    ".verify-generator", ".cache", "_site",
}

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

# ----------------------------------------------------------------------------
# A SEAT IS NOT A REPOSITORY, AND THIS GATE ASSUMED IT WAS `[2026-09-17]`
#
# `self_name = root.name` resolved ONE identity from the directory name, so a
# seat that owns several repositories was graded as one of them and the rest of
# its inbound channel was scored `addressed-elsewhere` — indistinguishable, in
# every published number, from mail for somebody else.
#
# **Measured on the architecture seat, which owns three trees and says so in its
# own `AGENTS.md`:** run from `entity-system-architecture` the gate reported
# `0 owed`. Re-run scoped to `entity-core-protocol` — the SAME seat, the same
# ledger, the same people — **37 packets addressed there, 31 cited, 2 OWED**,
# both from `entity-core-formalization`, plus a standing
# `TRACKER-entity-core-protocol.md` carrying **nine open asks** that appeared in
# no run this gate has ever done. The counterpart had it right: their own
# tracker opens *"arch owns three trees … One tracker covers all three, because
# it is one seat."* The gate was the only party that thought otherwise.
#
# ⛔ **This is the EIGHTH could-not-look in this toolkit and the third on THIS
# gate** (`--peers` defaulting to the sibling directory, `LEDGERS` as a
# one-element tuple, now the identity itself). The generalization has stopped
# being about flags: **when a scope is derived from a path, ask what the path
# assumes about the world, and whether that was ever true.** Here it assumed
# repo == seat, which was true when the gate was written and has not been true
# since the architecture seat took ownership of the core protocol.
#
# Membership is DECLARED, never inferred. A heuristic — shared remote, shared
# owner file, a naming prefix — would fold `entity-core-{go,rust,py}` into one
# seat, which is false and would let one seat's ledger discharge another's mail.
# A repo absent from this table is its own seat, which is the safe default and
# the state of every seat but one.
SEAT_REPOS: Dict[str, Tuple[str, ...]] = {
    # The architecture seat: the optional capability layer, the core protocol
    # it is upstream of, and the toolkit that gates both. One team, one
    # `docs/COHORT-OPEN-ITEMS.md`.
    "entity-system-architecture": ("entity-system-architecture",
                                   "entity-core-protocol",
                                   "entity-system-arch-tools"),
}


def seat_repos(name: str) -> Tuple[str, ...]:
    """Every repository that is the same SEAT as `name`, including itself.

    Symmetric by construction: running the gate from any member resolves the
    same set, so `--root ../entity-core-protocol` and `--root .` grade the same
    channel against the same ledger rather than two different halves of one.
    """
    for members in SEAT_REPOS.values():
        if name in members:
            return members
    return (name,)


def seat_aliases(members: Tuple[str, ...]) -> Tuple[str, ...]:
    """Every spelling that addresses this seat, across all its repositories.

    Order-preserving and de-duplicated. A repo with no alias entry contributes
    its own directory name, so a newly-added seat member is addressable by its
    formal name on day one rather than silently unmatched.
    """
    out: List[str] = []
    for m in members:
        for a in ALIASES.get(m, (m,)):
            if a not in out:
                out.append(a)
    return tuple(out)

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


def addressee_clauses(text: str) -> Tuple[Optional[str], List[str]]:
    """The `To:` value with cc stripped out of it, and the cc values.

    **One implementation, two callers.** `classify` decides to/cc/other and
    `addressed_as` decides WHICH of our repos was named; both have to strip cc
    from the `To:` value the same way, and two copies of that rule is how the
    breakdown ends up disagreeing with the count it breaks down.
    """
    to = field_value(text, TO_FIELD)

    cc_parts: List[str] = []
    cc = field_value(text, CC_FIELD)
    if cc:
        cc_parts.append(cc)
    for m in CC_INLINE.finditer(text[:4000]):
        cc_parts.append(m.group(1) or m.group(2) or m.group(3) or "")

    if to is None:
        return None, cc_parts

    # A cc clause living inside the To: value must not make the packet read
    # as addressed to us — strip what we recognised as cc before testing.
    primary = to
    for c in cc_parts:
        if c and c in primary:
            primary = primary.replace(c, " ")
    return CC_INLINE.sub(" ", primary), cc_parts


def classify(text: str, aliases: Tuple[str, ...]) -> str:
    """`to` · `cc` · `other` · `unaddressed` — and the last is not `other`."""
    primary, cc_parts = addressee_clauses(text)

    if primary is not None:
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


# A packet's date is in its own id. Not its mtime (that is the clone's), not its
# commit date (that does not survive the release boundary — [ADR-0027], and
# `census` measured nine of one repo's ten commits carrying a single date).
PACKET_DATE = re.compile(r"^ROUTING-(\d{4}-\d{2}-\d{2})")

RELATIVE_WINDOW = re.compile(r"^(\d+)d$")


def packet_date(name: str) -> Optional[str]:
    """`ROUTING-2026-09-16-h-…` -> `2026-09-16`, or None if it carries no date.

    **None is UNKNOWN, never old.** A packet whose name does not carry a parsable
    date cannot be placed in or out of a window, so it is reported in its own
    line rather than being silently dropped out of a recency view — the same
    asymmetry `unaddressed` exists for. Dropping it would be the cheaper code
    and would hide exactly the packets whose naming is already irregular.
    """
    m = PACKET_DATE.match(name)
    return m.group(1) if m else None


ANY_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def doc_date(name: str) -> Optional[str]:
    """A date from anywhere in the filename — for documents that are not
    `ROUTING-*` and so carry no anchored date position.

    `packet_date` stays anchored deliberately: for a packet the date IS the
    start of the id, and a loose search there would date
    `ROUTING-…-the-0.8.2.19-fold-2026-01-01-regression` from its slug.
    """
    anchored = packet_date(name)
    if anchored:
        return anchored
    m = ANY_DATE.search(name)
    return m.group(1) if m else None


def resolve_since(value: str) -> str:
    """`2026-09-10` or `7d` -> an ISO date string.

    The relative form is resolved against today at parse time and the ABSOLUTE
    result is what the report prints, so a run is quotable: `--since 7d` in a
    handoff means nothing a week later, `since 2026-09-10` still does.
    """
    m = RELATIVE_WINDOW.match(value.strip())
    if m:
        d = _dt.date.today() - _dt.timedelta(days=int(m.group(1)))
        return d.isoformat()
    try:
        return _dt.date.fromisoformat(value.strip()).isoformat()
    except ValueError:
        raise ValueError(
            "--since takes YYYY-MM-DD or Nd (e.g. 7d), not %r" % value)


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


def iter_packets(peers: Path, self_names: Tuple[str, ...]) -> List[Path]:
    found: List[Path] = []
    for repo in sorted(p for p in peers.iterdir() if p.is_dir()):
        if repo.name in self_names or repo.name.startswith("."):
            continue
        d = repo / PACKET_DIR
        if not d.is_dir():
            continue
        found.extend(sorted(d.glob(PACKET_GLOB)))
    return found


def peer_trackers(peers: Path, self_names: Tuple[str, ...],
                  aliases: Tuple[str, ...]) -> List[Path]:
    """A sibling's `docs/status/TRACKER-<us>.md` — a standing index aimed at us.

    Matched on the filename's alias token rather than on file contents, because
    a tracker names its counterpart in its own name and that is the cheap,
    unambiguous signal. `names_us` is reused so the substring guard that keeps
    `rust` from firing inside `entity-browser-rust` applies here too.
    """
    found: List[Path] = []
    for repo in sorted(pp for pp in peers.iterdir() if pp.is_dir()):
        if repo.name in self_names or repo.name.startswith("."):
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


def iter_name_addressed(peers: Path, self_names: Tuple[str, ...],
                        aliases: Tuple[str, ...]) -> List[Path]:
    """Documents naming US in their FILENAME, anywhere in a peer's tree.

    `HANDOFF-TO-ARCH-2026-09-08-…md`. See the PRUNE_DIRS block for why this
    exists and what it measured.

    **`ROUTING-*` and `TRACKER-*` are excluded here**, not because they are not
    inbound, but because they are counted by their own passes and a document
    must not be two obligations. `ROUTING-…-to-arch-…` is the overwhelmingly
    common spelling and would otherwise double every packet in the estate.

    The match requires a `to-<alias>` token with a separator in front of it, so
    `…-into-architecture-notes.md` does not fire and neither does a bare alias
    appearing anywhere in a slug. That is deliberately narrow: this class is
    reported as a delivery event, and over-reporting one costs a seat a
    re-read of something never sent to them.
    """
    pats = [re.compile(r"(?:^|[-_.])to[-_]%s(?:[-_.]|$)" % re.escape(a), re.I)
            for a in aliases]
    found: List[Path] = []
    for repo in sorted(p for p in peers.iterdir() if p.is_dir()):
        if repo.name in self_names or repo.name.startswith("."):
            continue
        for dirpath, dirnames, filenames in os.walk(repo):
            dirnames[:] = [d for d in dirnames
                           if d not in PRUNE_DIRS and not d.startswith(".")]
            for fn in filenames:
                if not fn.endswith(NAME_ADDRESSED_EXT):
                    continue
                if fn.startswith("ROUTING-") or fn.startswith("TRACKER-"):
                    continue
                if any(p.search(fn) for p in pats):
                    found.append(Path(dirpath) / fn)
    return sorted(found)


def own_tracker_seats(root: Path, peers: Path,
                      self_names: Tuple[str, ...]) -> List[str]:
    """Seats THIS corpus keeps a `docs/status/TRACKER-<seat>.md` for.

    Filtered to names that are actually sibling repositories, because a tracker
    file may legitimately track a *subject* rather than a seat — this corpus
    carries `TRACKER-THE-EXCHANGE-AND-COMPOSITION-ARC.md` — and counting those
    as counterparts would report reciprocity we do not have.
    """
    siblings = {p.name for p in peers.iterdir() if p.is_dir()}
    d = root / PACKET_DIR
    if not d.is_dir():
        return []
    seats = []
    for f in sorted(d.glob(OWN_TRACKER_GLOB)):
        subject = f.stem[len("TRACKER-"):]
        # A tracker naming one of our OWN seat repositories is not a
        # counterpart — it would report reciprocity with ourselves.
        if subject in siblings and subject not in self_names:
            seats.append(subject)
    return seats


def addressed_as(text: str, self_names: Tuple[str, ...]) -> List[str]:
    """WHICH of our repositories a packet's addressee clause named.

    **Reported so the count is falsifiable by inspection.** `305 addressed here`
    is a number nobody can check; `entity-system-architecture 268 ·
    entity-core-protocol 37` is a table a reader can disagree with — and it is
    the breakdown that makes a multi-repo seat's second channel visible at all,
    which is the whole defect this exists for.

    A packet may name more than one of ours; all matches are returned, so the
    breakdown can legitimately exceed the total it describes. That overlap is
    REPORTED rather than resolved — silently picking one repo would invent a
    precision the packet does not have.

    A packet that only `cc`s us has no repo attribution and is keyed `(cc)`.
    **It is not `unattributed`**: the first cut labelled it that way and the
    live run published `unattributed 30` for thirty packets whose addressee was
    perfectly parseable and simply was not us. A bucket named for the wrong
    cause is worse than no bucket.
    """
    primary, cc_parts = addressee_clauses(text)
    if primary is not None:
        hits = [m for m in self_names
                if names_us(primary, ALIASES.get(m, (m,)))]
        if hits:
            return hits
    if any(names_us(c, self_aliases_all(self_names)) for c in cc_parts if c):
        return ["(cc)"]
    return ["(unparsed)"]


def self_aliases_all(self_names: Tuple[str, ...]) -> Tuple[str, ...]:
    return seat_aliases(self_names)


def seat_of(p: Path, peers: Optional[Path] = None) -> str:
    """Which repository holds this file.

    `parents[2]` is right only for `<repo>/docs/status/FILE.md` and is wrong
    the moment a seat files somewhere deeper — `entity-core-go` writes into
    `docs/validation/reports/`, where `parents[2]` is the string `docs`. When
    the peer root is known, take the first path segment under it instead.
    """
    if peers is not None:
        try:
            return p.resolve().relative_to(peers).parts[0]
        except ValueError:
            pass
    return p.parents[2].name


def dedupe_clones(packets: List[Path],
                  weights: Optional[Dict[str, int]] = None,
                  peers: Optional[Path] = None
                  ) -> Tuple[List[Path], List[dict]]:
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
    # **`weights` is which directory is LIVE, and it must be measured over the
    # fullest population available — not over the handful of files being
    # deduped.** Caught on the first run of the name-addressed pass: three
    # copies of one browser-rust document, one each in the live tree and two
    # clones, ranked by name-addressed count alone. Every directory scored 1,
    # the tie broke on the name, and the obligation was attributed to
    # `entity-browser-rust-vm` — a clone — instead of `entity-browser-rust`.
    # A misattributed obligation is worse than a duplicated one: it names a
    # seat that cannot act on it.
    per_dir = dict(weights) if weights is not None else {}
    for p in packets:
        seat = seat_of(p, peers)
        per_dir.setdefault(seat, 0)
        if weights is None:
            per_dir[seat] += 1

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
        best = max(group, key=lambda q: (per_dir.get(seat_of(q, peers), 0),
                                         seat_of(q, peers)))
        canonical.append(best)
        for other in group:
            if other != best:
                collapsed.append({"file": str(other),
                                  "seat": seat_of(other, peers),
                                  "same_as": str(best)})
    canonical.sort()
    return canonical, collapsed


def scan(root: Path, peers: Optional[Path] = None,
         ledgers: Optional[List[str]] = None,
         since: Optional[str] = None) -> Tuple[int, dict]:
    root = root.resolve()
    self_name = root.name
    self_names = seat_repos(self_name)
    if self_name not in ALIASES and len(self_names) == 1:
        return CANNOT_LOOK, {
            "error": "no addressee aliases known for %r — this gate cannot "
                     "tell what 'addressed to us' means for this corpus, "
                     "which is a could-not-look and not a clean channel"
                     % self_name}
    aliases = seat_aliases(self_names)

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
    # A seat's reconciled view lives in ONE of its repositories, not in each of
    # them. The architecture seat's ledger is in `entity-system-architecture`
    # and `entity-core-protocol` holds none — so resolving the default against
    # `root` alone made `--root ../entity-core-protocol` a could-not-look for a
    # seat that has a perfectly good ledger one directory over.
    seat_roots: List[Path] = [root]
    for m in self_names:
        if m == self_name:
            continue
        sibling = peers / m
        if sibling.is_dir():
            seat_roots.append(sibling.resolve())

    def ledger_path(rel: str) -> Optional[Path]:
        for base in seat_roots:
            p = base / rel
            if p.is_file():
                return p
        return None

    explicit = bool(ledgers)
    candidates: List[str] = list(ledgers) if ledgers else list(LEDGERS)
    if not explicit and not any(ledger_path(rel) for rel in candidates):
        # FALLBACK ONLY, and the "only" is the whole safety argument.
        #
        # The defect was COULD-NOT-LOOK for a seat with no file at the default
        # path. Adding trackers *beside* an existing ledger would instead widen
        # what counts as a discharge — and for an inbox gate, over-crediting is
        # the dangerous direction: a spurious row is read once and dismissed, a
        # packet that never appears is the failure this gate exists to prevent.
        # So trackers stand in for a missing ledger; they never supplement one.
        fallback: List[str] = []
        for base in seat_roots:
            own = base / PACKET_DIR
            if own.is_dir():
                fallback.extend("%s/%s" % (PACKET_DIR, f.name)
                                for f in sorted(own.glob(OWN_TRACKER_GLOB)))
        if fallback:
            candidates = sorted(set(fallback))

    ledger_text = ""
    seen_ledger = []
    for rel in candidates:
        p = ledger_path(rel)
        if p is not None:
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

    trackers = peer_trackers(peers, self_names, aliases)
    tracker_recs = [{"file": str(t), "seat": t.parents[2].name}
                    for t in trackers]

    packets = iter_packets(peers, self_names)
    packets, collapsed = dedupe_clones(packets, None, peers)
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
        rec = {"file": str(p), "seat": seat, "stem": stem, "kind": kind,
               "date": packet_date(p.name),
               "addressed_as": addressed_as(text, self_names)}
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
            cited.append(rec)
            continue
        if hits:
            ambiguous_credit.append(dict(rec, cited_by=sorted(hits)))
            continue
        if rec["kind"] == "to":
            owed.append(rec)
        else:
            cc_owed.append(rec)

    ambiguous = [{"citation": t, "matches": v}
                 for t, v in sorted(reach.items()) if len(v) > 1]

    # ------------------------------------------------------------------
    # THE WINDOW SCOPES THE REPORT AND NOT THE SCAN, and it is applied HERE
    # — after `reach` is built over every packet in the estate. Filtering
    # earlier would make a `date-letter` token reaching two packets, one of
    # them outside the window, read as resolving, and silently discharge the
    # one nobody looked at. That is the exact defect this gate shipped in
    # 2026-09-11 (a token discharging five packets while printing "-> 5
    # packets" in its own summary), reintroduced one feature later.
    #
    # `undated` is its OWN bucket and never falls out. A packet whose name
    # carries no parsable date cannot be placed in or out of a window, and a
    # recency view that quietly drops it hides exactly the packets whose
    # naming is already irregular — UNKNOWN, never old.
    # ------------------------------------------------------------------
    def in_window(rec: dict) -> bool:
        return since is None or (rec["date"] or "") >= since

    excluded = {}
    undated = {}
    if since is not None:
        for label, bucket in (("owed", owed), ("cited", cited),
                              ("cc_owed", cc_owed),
                              ("unaddressed", unaddressed),
                              ("ambiguous_credit", ambiguous_credit)):
            excluded[label] = sum(
                1 for r in bucket if r["date"] and r["date"] < since)
            undated[label] = sum(1 for r in bucket if not r["date"])
        owed = [r for r in owed if in_window(r) or not r["date"]]
        cited = [r for r in cited if in_window(r) or not r["date"]]
        cc_owed = [r for r in cc_owed if in_window(r) or not r["date"]]
        unaddressed = [r for r in unaddressed
                       if in_window(r) or not r["date"]]
        ambiguous_credit = [r for r in ambiguous_credit
                            if in_window(r) or not r["date"]]

    for rec in owed:
        by_seat[rec["seat"]] = by_seat.get(rec["seat"], 0) + 1

    # The addressed-to-us total, broken down by WHICH of our repositories the
    # clause named. **Computed HERE — after the window filter — over the same
    # three buckets `addressed_to_us` sums**, so the table and the number it
    # breaks down cannot disagree. Computing it before the filter was the first
    # cut and it would have published a breakdown larger than its own total on
    # every `--since` run.
    #
    # ⚠ **The breakdown can EXCEED the total and that is not a bug** — a packet
    # naming two of our repositories is one obligation attributed twice. The
    # overlap is computed and printed rather than hidden, because a table that
    # silently fails to sum is the thing that makes a reader stop trusting the
    # number it breaks down. First cut asserted the sum and the assertion only
    # passed because no fixture had a multi-match packet; live, it was 316
    # against a total of 308.
    addressed_by_repo: Dict[str, int] = {}
    multi_named = 0
    for rec in owed + cited + ambiguous_credit:
        named = rec.get("addressed_as") or ["(unparsed)"]
        if len([m for m in named if m in self_names]) > 1:
            multi_named += 1
        for m in named:
            addressed_by_repo[m] = addressed_by_repo.get(m, 0) + 1

    # ------------------------------------------------------------------
    # NAME-ADDRESSED DOCUMENTS — `HANDOFF-TO-ARCH-…`, anywhere in the tree.
    #
    # Its own class, and it does NOT gate today. Not timidity: this is a
    # population nobody has ever reconciled, so gating it turns the run red
    # on introduction, which is how a gate teaches people to skip it. The
    # count is printed with the reason. When the backlog is worked it
    # becomes an `owed` bucket like any other.
    #
    # Dedupe against the packet set by (name, digest) too — a `HANDOFF-TO-`
    # under a working clone is one obligation, same as a packet.
    # ------------------------------------------------------------------
    named = iter_name_addressed(peers, self_names, aliases)
    # Weighted by the PACKET census, which is the measure of which directory is
    # the live tree — see the comment in `dedupe_clones`.
    packet_weights: Dict[str, int] = {}
    for p in packets:
        s = seat_of(p, peers)
        packet_weights[s] = packet_weights.get(s, 0) + 1
    named, _named_clones = (dedupe_clones(named, packet_weights, peers)
                            if named else ([], []))
    name_addressed = []
    for p in named:
        stem = stem_of(p.name)
        # **The FULL stem, and nothing shorter.** These names carry no
        # `date-letter` short form, so there is no vocabulary to calibrate
        # against here — and for an inbox gate the safe direction is to
        # report a document nobody has cited precisely, never to credit one
        # on a partial match. Under-crediting costs a re-read; over-crediting
        # is the failure this gate exists to prevent.
        rec = {"file": str(p), "seat": seat_of(p, peers),
               "stem": stem, "date": doc_date(p.name),
               "cited": stem in ledger_text}
        if since is None or not rec["date"] or rec["date"] >= since:
            name_addressed.append(rec)

    # Reciprocity — the one blind spot no check starting from a file WE wrote
    # can reach. See the module docstring.
    keep_for_us = sorted({t["seat"] for t in tracker_recs})
    we_keep = own_tracker_seats(root, peers, self_names)
    flow = {}
    for rec in owed + cited + cc_owed + ambiguous_credit:
        flow[rec["seat"]] = flow.get(rec["seat"], 0) + 1

    res = {
        "root": str(root),
        "peers": str(peers),
        "ledgers": seen_ledger,
        "scanned": len(packets),
        "collapsed_clones": collapsed,
        "clone_seats": sorted({c["seat"] for c in collapsed}),
        "addressed_to_us": len(owed) + len(cited) + len(ambiguous_credit),
        "cited": len(cited),
        # WHICH of this seat's repositories the channel actually named. One
        # entry when the seat is one repo, which is every seat but arch.
        "seat_repos": list(self_names),
        "addressed_by_repo": addressed_by_repo,
        "addressed_multi_named": multi_named,
        "since": since,
        "excluded_by_window": excluded,
        "undated": undated,
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
        "tracker_reciprocity": {
            "they_keep_for_us": keep_for_us,
            "we_keep_for_them": we_keep,
            # The finding keystone named: a seat aiming a standing index at us
            # that we hold no counterpart for. Their own twelve-ask incident.
            "not_reciprocated": [s for s in keep_for_us if s not in we_keep],
            # The inverse is informational, not a defect: arch keeps trackers
            # for the core tier precisely BECAUSE it does not correspond with
            # two of those seats directly.
            "ours_only": [s for s in we_keep if s not in keep_for_us],
        },
        "flow_by_seat": flow,
        "name_addressed": name_addressed,
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

    if res.get("since"):
        print("  %-32s %4s %6s   (window: packets dated >= %s)"
              % ("seat", "owed", "flow", res["since"]))
        for seat in sorted(res["flow_by_seat"],
                           key=lambda k: -res["flow_by_seat"][k]):
            print("  %-32s %4d %6d" % (seat, res["by_seat"].get(seat, 0),
                                       res["flow_by_seat"][seat]))
    else:
        for seat in sorted(res["by_seat"], key=lambda k: -res["by_seat"][k]):
            print("  %-32s %4d owed" % (seat, res["by_seat"][seat]))
    print("\n%d routing packet(s) under %s — %d addressed here, %d already on "
          "the ledger, %d owed."
          % (res["scanned"], res["peers"], res["addressed_to_us"],
             res["cited"], len(res["owed"])))
    # A SEAT IS NOT A REPOSITORY. Printed only when this one spans several, and
    # printed as a breakdown rather than a total, because `305 addressed here`
    # is a number nobody can check and a per-repo table is one a reader can
    # disagree with. This seat's second channel was invisible for as long as
    # the identity was `root.name`.
    if len(res.get("seat_repos", [])) > 1:
        bd = res.get("addressed_by_repo", {})
        line = ("SEAT: this corpus is one seat across %d repositories (%s) — "
                "they share this ledger, so mail to any of them is mail to "
                "us. Attribution: %s."
                % (len(res["seat_repos"]), ", ".join(res["seat_repos"]),
                   " · ".join("%s %d" % (k, v) for k, v in
                              sorted(bd.items(), key=lambda kv: -kv[1]))))
        # The attribution is per-NAMING and the total is per-PACKET, so state
        # the difference instead of leaving a reader to find that a published
        # table does not add up. `(cc)` is a packet copying us with no repo of
        # ours in its `To:`; `(unparsed)` is one we cannot attribute at all.
        extra = sum(bd.values()) - res["addressed_to_us"]
        if extra:
            line += (" ⚠ that is %d attributions over %d packets — %d packet(s)"
                     " name more than one of our repositories and are counted"
                     " once per name."
                     % (sum(bd.values()), res["addressed_to_us"],
                        res.get("addressed_multi_named", 0)))
        print(line)
    if res.get("since"):
        ex = res["excluded_by_window"]
        print("WINDOW: dated >= %s. The counts above are the WINDOW, not the "
              "channel — %d owed, %d cited, %d cc, %d unaddressed and %d "
              "ambiguous packet(s) are older and are NOT reported above. A "
              "window is a reading order, never a discharge."
              % (res["since"], ex.get("owed", 0), ex.get("cited", 0),
                 ex.get("cc_owed", 0), ex.get("unaddressed", 0),
                 ex.get("ambiguous_credit", 0)))
        nd = sum(res.get("undated", {}).values())
        if nd:
            print("%d packet(s) carry no parsable date in their filename and "
                  "are reported IN the window regardless — undated is UNKNOWN, "
                  "never old." % nd)
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
    na = res.get("name_addressed") or []
    if na:
        uncited = [r for r in na if not r["cited"]]
        seats = sorted({r["seat"] for r in na})
        print("%d document(s) address this corpus IN THEIR FILENAME and are "
              "not ROUTING packets (%s) — %d of them are cited nowhere in the "
              "reconciled view. A seat that writes `HANDOFF-TO-US-….md` into "
              "its own research directory has addressed us more explicitly "
              "than a **To:** field does. Counted separately and NOT gated "
              "yet: this population has never been reconciled, and a gate red "
              "on introduction is one people switch off."
              % (len(na), ", ".join(seats), len(uncited)))
        for r in uncited:
            print("    [uncited] %s" % r["file"])
    rec = res.get("tracker_reciprocity") or {}
    if rec.get("not_reciprocated"):
        print("⚠ %d seat(s) keep a standing index aimed at US and we keep none "
              "for them: %s. A reconciliation keyed on the trackers you KEEP "
              "cannot see the counterpart you OMITTED — an absent row in an "
              "absent table. Reported, never gated: whether a seat warrants a "
              "tracker is a judgement about traffic."
              % (len(rec["not_reciprocated"]),
                 ", ".join(rec["not_reciprocated"])))
    if rec.get("ours_only"):
        print("  (we keep one for %s who keep none for us — not a defect: a "
              "tracker is also how a seat we do not correspond with directly "
              "gets its worklist written down.)" % ", ".join(rec["ours_only"]))
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
    ap.add_argument("--since", default=None, metavar="DATE",
                    help="scope the REPORT to packets dated on or after DATE "
                         "(YYYY-MM-DD, or Nd for N days back). The scan still "
                         "covers everything; what the window excluded is "
                         "printed rather than dropped")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)

    since = None
    if args.since is not None:
        try:
            since = resolve_since(args.since)
        except ValueError as exc:
            print("could not look: %s" % exc, file=sys.stderr)
            return CANNOT_LOOK

    root = args.root
    if root is None:
        try:
            import config as _config
            root = _config.corpus_root()
        except Exception:  # noqa: BLE001
            root = Path.cwd()

    code, res = scan(Path(root), args.peers, args.ledger, since)
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
