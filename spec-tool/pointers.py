#!/usr/bin/env python3
"""pointers — does a declared pointer still say what its authority says?

    spec pointers [--root DIR|FILE ...] [--namespace-root DIR ...]
                  [--json] [--unpinned] [--update] [--gate]

A **declared pointer** is a passage that names another section as the normative
home of the rule it is restating:

    "ENTITY-CORE-PROTOCOL.md §7.3 is the normative home and this sentence is a
     pointer, not a second statement of the rule."

From the moment it is written, that sentence and §7.3 are two artifacts with one
meaning. Nothing in this toolkit compared them across documents. `coherence` is
same-file and pseudocode-scoped; `address` checks that a citation *resolves*,
never that it is still *true*; `standards` reads shape; `provenance` reads a
**commit**, and the two halves of a drifting pair need never move in the same
one — usually it is the **authority** that moves, in a commit that does not
touch the restating document at all.

## The instance this was built for

`ENTITY-NATIVE-TYPE-SYSTEM` §10.2 said a signature is computed over "the target
entity's content hash **digest** bytes" while citing `ENTITY-CORE-PROTOCOL` §7.3
— which specifies the hash **with** its format code — **in the same sentence**.
An unmarked restatement, drifted by one field from the authority it named. It
fired neither `provenance` trigger: the version did not move and the *count* of
normative tokens did not move, because the sentence is indicative prose
restating a `[MUST]` whose home is another document. Reported from outside this
estate as `CQ-47`, four days after it landed.

`entity-core-protocol/AGENTS.md` had already retired a whole document over this
class: *"a hand-maintained restatement ages on every edit to its source,
**nothing in the toolkit gates spec-against-spec**, and the drift is reachable
only by a human reading both documents side by side."*

## Why this is a new analyzer and not a third `provenance` trigger

Unit mismatch, not tuning. `provenance`'s unit is a commit; this defect's unit
is a **pair of documents**. A third trigger would catch the subset where both
sides move together and report clean on the rest, which is could-not-look
wearing a verdict's clothes — built deliberately, this time.

## Why it can only see restatements that DECLARE themselves

Because an undeclared one is indistinguishable from ordinary prose. That is the
stated residue and it is not closed here. What changes is the incentive:
declaring a pointer now buys enforcement. The measured case for believing the
declaration is worth something is register row `EN-4` — two restatements of one
registry, one naming its authority and one not; **the one that named it stayed
correct, the one that named nothing drifted on three axes at once.**

## `--floor` — the residue, narrowed to the one place it is CHEAP to close

    spec pointers --floor

An undeclared restatement is indistinguishable from prose **in general**. It is
not indistinguishable **in a conformance floor**, and a floor is where this
class has done its damage: a floor row is a list an implementer BUILDS FROM, so
it carries a rule in short form by construction, and when the authority moves
the row keeps publishing the superseded version positively.

`ENTITY-CORE-PROTOCOL` §9.1 landed exactly this rule at `0.8.2.31` —

    A row here that restates a rule stated elsewhere NAMES that section as its
    normative home [MUST].

— and then applied it to the two rows it was investigating.
`entity-core-keystone` measured the rest and filed it (`F87`, 2026-09-16):
**8 of 22.** They wrote the scan in fifteen lines and offered it; this is that
scan, in the module whose docstring already stated the class in the general.

**It is a READER and it NEVER gates, for the same reason `arms` does not.**
Whether a row RESTATES a rule or is its sole statement is a judgement that
requires opening the cited section — §9.1 rows do both, and several cite the
section that genuinely is the only home. A gate here would file accusations
against correct text at roughly the rate it finds real ones. What a run
produces is a **worklist with the surface printed beside it**, never a verdict.

⚠ **The count it prints is NOT `8 of 22`.** Keystone's discriminator for *a row
that asserts a rule* was narrower than this one's, and re-deriving it here gives
a larger population. **That does not move their finding, and neither number is
the deliverable** — publish the surface, never the count alone.

## The mechanism

Same as `sdksync`, whose `normalize`/`digest`/`span_for_anchor` this module
imports rather than re-implements. A pin file — `.spec-pointer-map.json` at the
corpus root — records, per pointer, the authority span it was written against
and a digest of that span at pin time.

  pointer-source-moved     The pinned authority span changed since this pointer
                           was written against it. **The pointer is not
                           necessarily wrong — it is unreviewed.**

  pointer-source-missing   The pin names a document or section that no longer
                           resolves **in a corpus this run could read**. A
                           finding, never a skip.

  pointer-unresolved       The authority lives in a corpus this run was not
                           pointed at. **UNKNOWN — never `missing`, never a
                           pass.** Pass --namespace-root. The roots searched are
                           printed on every run.

  pointer-unanchored       A pointer naming a document but no section. Nothing
                           to pin: a whole-document digest changes on every
                           unrelated edit, and a gate that fires on everything
                           is read as a gate that fires on nothing.

  pointer-unpinned         A declared pointer with no pin. **Reported, ratchets,
                           does not gate** — a first run of 19 reds is a gate
                           the next contributor learns to skip.

Self-declarations — *"this section is the normative home"* — are **authorities,
not pointers**. They are counted and never flagged: the count is the other half
of the picture and a run reporting 0 pointers over 0 authorities is a pattern
that stopped matching, not a corpus that came out clean.

Stdlib-only. Beside sdksync.py, whose docstring states this class in the
general and whose scope was two constants.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import config as _config
from sdksync import digest, span_for_anchor

PIN_RELPATH = ".spec-pointer-map.json"
DEFAULT_ROOTS = [Path("specs"), Path("guides")]

RULES = {
    "pointer-source-moved": (
        "error", "the pinned authority span changed; this pointer is unreviewed"),
    "pointer-source-missing": (
        "error", "a pin names a document or section that no longer resolves"),
    "pointer-unresolved": (
        "warn", "the authority is outside every root this run searched — UNKNOWN"),
    "pointer-ambiguous": (
        "warn", "a bare section number whose document is not adjacent — UNKNOWN"),
    "pointer-unanchored": (
        "warn", "a pointer naming a document but no section; nothing to pin"),
    "pointer-unpinned": (
        "warn", "a declared pointer with no recorded authority span"),
}

# Calibrated against all 19 live occurrences in the two corpora, not against
# the spelling this module's author expected. Both orderings occur:
#
#   "`ENTITY-CORE-PROTOCOL.md` §7.3 is the normative home"     doc-then-section
#   "§3.3a is its normative home"                              section, same doc
#   "whose normative home is TREE"                             doc, no section
#
# The document token is optional because a same-document pointer is the CQ-16
# class (a rule executing in one section, restated in another) and is just as
# pinnable. Requiring a document name would have silently dropped four of ten.
#
# ADJACENCY IS LOAD-BEARING and the first cut did not have it. Allowing any
# text between the document token and the `§` made the leftmost uppercase word
# on the line the document: `EXTENSION-NETWORK` §33 reads "SERVES and FETCHES
# but does NOT own.** TREE §3.3a is the normative home", and the run reported
# an authority in a document called `FETCHES`. It resolved nowhere, so it
# surfaced as `pointer-unresolved` — a plausible, confident, WRONG finding that
# a reader would have answered by passing another --namespace-root. Caught by
# running against the live corpus before publishing a number.
_DOC = r"[`*]*(?P<doc>[A-Z][A-Z0-9-]{3,})(?:\.md)?[`*]*"
_SEC = r"§(?P<sec>\d+(?:\.\d+)*[a-z]?)"

# A SHORT QUALIFIER MAY SIT BETWEEN THE SECTION AND THE VERB, because the corpus
# writes one: "§1.8 item 1 is the normative home", "§6.3's frame rule is the
# normative home", "§5.2a's enumeration is the normative home". Requiring
# adjacency there matched 2 of 6 rows in the fold that motivated this and
# reported the other 4 as ordinary prose — the calibrate-against-the-corpus's-
# own-vocabulary lesson, arriving for the fourth time in this toolkit.
#
# The gap is bounded, forbids a second `§` (so the leftmost match cannot reach
# past an intervening citation) and forbids sentence punctuation (so it cannot
# span a clause boundary). Document adjacency is UNCHANGED and still strict —
# that is the defect this must not reintroduce.
POINTER_RE = re.compile(
    r"(?:" + _DOC + r"\s{1,3})?" + _SEC +
    r"(?:['\u2019]s)?(?:[^\u00A7.;:!?\n]{0,28}?)?"
    r"\s+(?:is|are)\s+(?:the|its)\s+(?:single\s+)?normative\s+home")
# The reversed form, which names a document and no section.
UNANCHORED_RE = re.compile(
    r"normative\s+home\s+is\s+" + _DOC)
# A self-declaration is an AUTHORITY, not a pointer. Matched to be excluded and
# counted, never to be flagged.
AUTHORITY_RE = re.compile(
    r"(?:this|the)\s+section\s+is\s+the\s+(?:single\s+)?normative\s+home",
    re.IGNORECASE)


# ---------------------------------------------------------------------------
# `--floor`: undeclared restatements inside a conformance floor.
# ---------------------------------------------------------------------------

# A floor is a heading, not a filename. `ENTITY-CORE-PROTOCOL` §9.1 is
# `MUST Implement`; other documents spell theirs `## N. Conformance`. Keyed on
# the heading text so a document that grows a floor is covered without a list
# of filenames to keep current — the scope-set-once failure this toolkit has
# now shipped seven times.
FLOOR_HEADING = re.compile(
    r"^#{2,4}\s+.*?(?:(?:MUST|SHOULD|MAY)\s+Implement|Conformance)\b",
    re.IGNORECASE | re.MULTILINE)

# What makes a row an ASSERTION rather than a feature name.
#
# Calibrated against §9.1's live text, both directions. `- Wire framing (§1.6)`
# names a feature and asserts nothing — it cannot drift, because it says
# nothing that could stop being true. `- Path validation (§1.4) — no null
# bytes, no leading slash` states the rule and can.
#
# ⚠ A bare `MUST` is NOT sufficient and was the first cut's error: the floor's
# own heading is "MUST Implement" and several rows read "MUST be safe under"
# as part of a feature description. The discriminator is a rule's TELL — a
# normative verb, a wire code, a refusal, a status — not the word MUST.
#
# ⚠ **Widened once, on its own first use, and the miss was in the SILENT
# direction.** The first cut matched `emits?` and missed two §9.1 rows that
# restate a rule in the passive or with a different verb — *"the **emitted**
# code is the lowest-numbered failing step's"* and *"bind-to-marker **fires**
# `modified`, NOT `deleted`"*. Both were found by reading the section the
# worklist was for. An under-reporting reader is worse than an over-reporting
# one here: a candidate a human discards costs a lookup, a row that never
# appears is the defect going unfixed, which is what this whole class is.
ASSERTS = re.compile(
    r"\bMUST NOT\b|\[MUST\]|\bnon-?conformant\b|\bemits?\b|\bemitted\b"
    r"|\bfires?\b|\breject(?:s|ed)?\b|\brefus(?:e|es|ed|al)\b"
    r"|\b[45]\d\d\s+[`\"]|\bis WITHDRAWN\b|\bnever\b|\bMUST\s+(?:be\s+)?"
    r"(?:omitted|validated|execute|stay|enforce|resolve|key|run)\b")

# The authority phrases in live use, measured across both corpora rather than
# invented: the fold that landed the rule wrote six spellings in one commit.
# `--floor` uses a WIDER net than POINTER_RE on purpose — here a phrase's job
# is to EXCLUDE a row from the worklist, so missing one manufactures work
# against correct text, which is the expensive direction for a reader nobody
# is obliged to act on.
HAS_AUTHORITY = re.compile(
    r"normative home|is the authority|\bgoverns\b|§[\d.]+[a-z]?\s+wins"
    r"|\bRESTATES\b|\brestatement\b|where they differ|defers to"
    r"|takes precedence|\blives in\b", re.IGNORECASE)

CITES_SECTION = re.compile(r"§\d")


def floor_rows(text: str):
    """(line, row text) for every list item inside a conformance-floor section.

    The unit is a LIST ITEM and it may wrap — `paragraphs()` is wrong here
    because a floor is one unbroken block of `- ` lines with no blank lines
    between them, so paragraph-splitting would return the whole floor as a
    single unit and every row would inherit every other row's authority
    phrase. **That failure reports a clean floor**, which is the direction
    this module exists to avoid.
    """
    lines = text.splitlines()
    in_floor = False
    cur: List[str] = []
    cur_line = 0
    out = []

    def flush():
        if cur:
            out.append((cur_line, " ".join(cur)))

    for i, ln in enumerate(lines, start=1):
        if ln.startswith("#"):
            flush()
            cur.clear()
            in_floor = bool(FLOOR_HEADING.match(ln))
            continue
        if not in_floor:
            continue
        if ln.startswith("- ") or ln.startswith("* "):
            flush()
            cur = [ln[2:].strip()]
            cur_line = i
        elif cur and ln.strip() and not ln.startswith("#"):
            cur.append(ln.strip())
        elif not ln.strip():
            flush()
            cur = []
    flush()
    return out


def floor_candidates(text: str):
    """Rows that assert a rule, cite a section, and name no authority."""
    total = asserting = 0
    out = []
    for line, row in floor_rows(text):
        total += 1
        if not (CITES_SECTION.search(row) and ASSERTS.search(row)):
            continue
        asserting += 1
        if HAS_AUTHORITY.search(row):
            continue
        out.append((line, row))
    return out, total, asserting


class CouldNotLook(Exception):
    """Raised when the scope resolves to nothing — exit 2, never 0."""


@dataclass
class Finding:
    rule: str
    line: int
    text: str

    def severity(self) -> str:
        return RULES[self.rule][0]


@dataclass
class Pointer:
    doc: Optional[str]   # the authority's document, None = this one
    sec: str             # the authority's section number
    line: int            # 1-indexed line of the declaration


def paragraphs(text: str):
    """(paragraph text, 1-indexed start line) for each blank-line-delimited block.

    ⛔ **THE SCAN UNIT IS A PARAGRAPH, NOT A LINE, AND THE FIRST CUT WAS A LINE.**
    This corpus hard-wraps prose, so a declaration lands across a break as often
    as not — *"… and §7.3 is its\\nsingle normative home."* A line matcher finds
    nothing there and reports a clean file, which is the silent-drop family this
    whole module exists to close, reintroduced in the module closing it. **Found
    by the selftest, not by a run**, because a run's output was identical either
    way: the visible half stayed right.
    """
    out, buf, start = [], [], 1
    for i, ln in enumerate(text.splitlines(), start=1):
        if ln.strip():
            if not buf:
                start = i
            buf.append(ln)
        elif buf:
            out.append(("\n".join(buf), start))
            buf = []
    if buf:
        out.append(("\n".join(buf), start))
    return out


def find_pointers(text: str) -> Tuple[List[Pointer], int, List[int]]:
    """(pointers, authority self-declarations, unanchored declaration lines).

    A self-declaration — *"this section is the normative home"* — is counted and
    never treated as a pointer. The two patterns cannot match the same text (one
    requires `section is`, the other `§N is`), so they are read independently
    rather than by suppressing a whole region: `ENTITY-CORE-PROTOCOL` §1.2
    declares itself the registry's home **and** lists the four sections that
    restate it in the same paragraph, and a region-wide suppression there would
    discard an authority's own map of its restatements.
    """
    out: List[Pointer] = []
    authorities, unanchored = 0, []
    for para, start in paragraphs(text):
        authorities += len(AUTHORITY_RE.findall(para))
        for m in POINTER_RE.finditer(para):
            line = start + para[:m.start()].count("\n")
            out.append(Pointer(m.group("doc"), m.group("sec"), line))
        if not POINTER_RE.search(para):
            for m in UNANCHORED_RE.finditer(para):
                unanchored.append(start + para[:m.start()].count("\n"))
    return out, authorities, unanchored


def resolve_doc(name: str, corpus: Path, ns_roots: List[Path]) -> Optional[Path]:
    """Find `<name>.md` in the corpus, then in each namespace root.

    Returns None when no root holds it — which the caller reports as
    `pointer-unresolved` and NEVER as `missing`. A resolver's scope is a
    premise, and a wrong premise produces confident findings rather than an
    error: this toolkit has shipped that defect six times (`address`,
    `provenance`, `coverage`, `pins`, `inbound`, `deps`) and the seventh is not
    going to be the module written to close it.
    """
    for root in [corpus] + list(ns_roots):
        if not root.exists():
            continue
        hits = sorted(root.rglob(name + ".md"))
        if hits:
            return hits[0]
    # Nicknames. The corpus writes `TREE §3.3a` for `EXTENSION-TREE.md` and it
    # is the house idiom, not sloppiness — `address` carries the same expansion
    # for the same reason. Suffix-matched rather than table-driven so a new
    # family does not need a code change; **ambiguity returns None** and
    # surfaces as UNKNOWN, because a nickname resolving to two documents is
    # exactly the case where guessing is worse than saying so.
    for root in [corpus] + list(ns_roots):
        if not root.exists():
            continue
        hits = sorted(q for q in root.rglob("*" + name + ".md")
                      if q.stem.endswith(name))
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            return None
    return None


def section_span(text: str, sec: str) -> Optional[List[str]]:
    """The span of `## N.` / `### N.M` … whose number is exactly `sec`.

    Anchored on the number, not on the title, because a pointer cites a number
    and a title is free to be reworded. Runs to the next heading of the same or
    higher level — `span_for_anchor`'s rule, reused via the heading it finds.
    """
    pat = re.compile(r"^(#{2,6})\s+" + re.escape(sec) + r"[.\s]")
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        m = pat.match(ln)
        if not m:
            continue
        level, out = len(m.group(1)), [ln]
        for ln2 in lines[i + 1:]:
            m2 = re.match(r"^(#{1,6})\s+", ln2)
            if m2 and len(m2.group(1)) <= level:
                break
            out.append(ln2)
        return out
    return None


def key(rel_path: str, doc: Optional[str], sec: str) -> str:
    """The pin unit is the (citing document, authority) PAIR, not the sentence.

    `ENTITY-CORE-PROTOCOL` points at its own §4.11 from two places — §938's
    wire-message rule and §2787's decode-boundary rule — and both are the same
    claim about the same span. One pin watches both, and a second pin would
    only be a second place for the same digest to go stale.

    **The count is reported in pairs for exactly this reason.** The first run
    printed `10 declared pointer(s) … 8 pinned` and looked like a backlog of
    two; nothing was unwatched, the unit had simply changed between the two
    halves of one sentence.
    """
    return "%s::%s§%s" % (rel_path, doc or "", sec)


def analyze(rel_path: str, text: str, self_path: Path, pins: Dict[str, dict],
            corpus: Path, ns_roots: List[Path]):
    """(findings, pointer occurrences, distinct (doc, authority) pairs, authorities)."""
    found: List[Finding] = []
    ptrs, authorities, unanchored = find_pointers(text)
    pairs = {key(rel_path, p.doc, p.sec) for p in ptrs}

    for line in unanchored:
        found.append(Finding("pointer-unanchored", line,
                             "names a document as the normative home but no "
                             "section — nothing to pin"))

    for p in ptrs:
        label = "%s§%s" % (p.doc + " " if p.doc else "", p.sec)
        src = self_path if p.doc is None else resolve_doc(p.doc, corpus, ns_roots)
        if src is None:
            found.append(Finding("pointer-unresolved", p.line,
                                 "`%s` is in no root this run searched — "
                                 "UNKNOWN, not clean. Pass --namespace-root"
                                 % label))
            continue
        span = section_span(src.read_text(encoding="utf-8"), p.sec)
        if span is None:
            # A BARE section number that does not resolve locally is AMBIGUOUS,
            # never missing. The document may be named earlier in the sentence,
            # out of adjacency range: the ECF changelog writes "`ENTITY-CORE-
            # PROTOCOL` 0.8.2.26 ruled … and §7.3 is its single normative home",
            # where §7.3 is three documents away. The first cut called that
            # `source-missing` — an ERROR against correct text, which is the
            # expensive direction for a gate to be wrong in.
            rule = ("pointer-source-missing" if p.doc
                    else "pointer-ambiguous")
            detail = ("names §%s, which is not a heading in %s (renumbered? a "
                      "renumber is a finding, not a skip)" % (p.sec, src.name)
                      if p.doc else
                      "names §%s with no adjacent document and no such heading "
                      "here — the authority is named elsewhere in the sentence "
                      "or not at all. UNKNOWN, not a defect" % p.sec)
            found.append(Finding(rule, p.line, "`%s` %s" % (label, detail)))
            continue
        pin = pins.get(key(rel_path, p.doc, p.sec))
        if pin is None:
            found.append(Finding("pointer-unpinned", p.line,
                                 "`%s` is a declared pointer with no recorded "
                                 "authority span" % label))
            continue
        now = digest(span)
        if now != pin.get("digest"):
            found.append(Finding("pointer-source-moved", p.line,
                                 "`%s` was written against a span digesting %s; "
                                 "it now digests %s — re-read the authority, "
                                 "correct this pointer if it drifted, then "
                                 "--update" % (label, pin.get("digest", "?"), now)))
    return found, len(ptrs), len(pairs), authorities


def load_pins(corpus: Path) -> Dict[str, dict]:
    p = corpus / PIN_RELPATH
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8")).get("pins", {})


def iter_docs(roots: List[Path], corpus: Path) -> List[Path]:
    out: List[Path] = []
    for r in roots:
        p = r if r.is_absolute() else corpus / r
        if p.is_file() and p.suffix == ".md":
            out.append(p)
        elif p.is_dir():
            out.extend(sorted(q for q in p.rglob("*.md")))
    return out


def rel(p: Path, corpus: Path) -> str:
    try:
        return str(p.relative_to(corpus))
    except ValueError:
        return str(p)


def collect(roots: List[Path], corpus: Path, ns_roots: List[Path]):
    docs = iter_docs(roots, corpus)
    if not docs:
        raise CouldNotLook("no .md under %s" % ", ".join(str(r) for r in roots))
    pins = load_pins(corpus)
    report: Dict[str, List[Finding]] = {}
    n_ptr = n_pair = n_auth = 0
    for d in docs:
        r = rel(d, corpus)
        text = d.read_text(encoding="utf-8")
        f, np_, npair, na = analyze(r, text, d, pins, corpus, ns_roots)
        n_ptr += np_
        n_pair += npair
        n_auth += na
        if f:
            report[r] = f
    return docs, pins, report, n_ptr, n_pair, n_auth


def do_update(roots: List[Path], corpus: Path, ns_roots: List[Path]) -> int:
    """Re-pin every declared pointer that resolves.

    Unlike `sdksync --update`, this DOES create pins for unpinned pointers —
    because the mapping a human has to judge there (which source span does this
    block restate?) is already stated here, by the author, in the sentence
    itself. What --update still is not is a review: a pin proves the authority
    span is byte-identical to when someone last claimed to read it against this
    pointer. It never proves the pointer was right then.
    """
    pinfile = corpus / PIN_RELPATH
    doc = (json.loads(pinfile.read_text(encoding="utf-8"))
           if pinfile.exists() else {"pins": {}})
    pins = doc.setdefault("pins", {})
    added = moved = 0
    for d in iter_docs(roots, corpus):
        r = rel(d, corpus)
        text = d.read_text(encoding="utf-8")
        ptrs, _, _ = find_pointers(text)
        for p in ptrs:
            src = d if p.doc is None else resolve_doc(p.doc, corpus, ns_roots)
            if src is None:
                continue
            span = section_span(src.read_text(encoding="utf-8"), p.sec)
            if span is None:
                continue
            k = key(r, p.doc, p.sec)
            dg = digest(span)
            if k not in pins:
                pins[k] = {"doc": p.doc, "section": p.sec, "digest": dg}
                added += 1
            elif pins[k].get("digest") != dg:
                pins[k]["digest"] = dg
                moved += 1
    doc.setdefault("meta", {})["pins"] = len(pins)
    pinfile.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
    print("pinned %d new, re-pinned %d moved — %d total in %s"
          % (added, moved, len(pins), PIN_RELPATH))
    return 0


def run_check(roots: List[Path], ns_roots: List[Path], as_json: bool,
              show_unpinned: bool, gate: bool) -> int:
    corpus = _config.corpus_root()
    try:
        docs, pins, report, n_ptr, n_pair, n_auth = collect(
            roots, corpus, ns_roots)
    except CouldNotLook as e:
        print("could not look: %s" % e, file=sys.stderr)
        return 2

    n_error = sum(1 for fs in report.values()
                  for x in fs if x.severity() == "error")
    counts: Dict[str, int] = {}
    for fs in report.values():
        for x in fs:
            counts[x.rule] = counts.get(x.rule, 0) + 1

    if as_json:
        out = {rp: [{"rule": x.rule, "severity": x.severity(),
                     "line": x.line, "text": x.text} for x in fs]
               for rp, fs in report.items()}
        print(json.dumps({"summary": {"errors": n_error, "pointers": n_ptr,
                                      "pairs": n_pair, "authorities": n_auth,
                                      "pins": len(pins),
                                      "scanned": len(docs), "by_rule": counts},
                          "findings": out}, indent=2))
        return (1 if n_error else 0) if gate else 0

    quiet = set() if show_unpinned else {"pointer-unpinned"}
    for rp in sorted(report):
        shown = [x for x in report[rp] if x.rule not in quiet]
        if not shown:
            continue
        print("\n%s  (%d finding)" % (rp, len(shown)))
        for x in shown:
            print("  %-6s %-22s %s:%d  %s"
                  % (x.severity().upper(), x.rule, rp, x.line, x.text))

    # The roots searched are part of the answer, not a debug line: a run that
    # could not reach the sibling corpus reports `unresolved`, and a reader has
    # to be able to tell that from a clean one without re-deriving the scope.
    print("\nroots searched: %s" % ", ".join(
        [str(corpus)] + [str(r) for r in ns_roots] or ["<corpus only>"]))
    # Pointers and pins are counted in DIFFERENT units and the run says so:
    # the pin watches a (document, authority) pair, and one document may reach
    # one authority from several sentences.
    print("scanned %d document(s) — %d declared pointer(s) over %d "
          "(document, authority) pair(s), %d authority self-declaration(s), "
          "%d pinned."
          % (len(docs), n_ptr, n_pair, n_auth, len(pins)))
    if counts:
        print("  " + " · ".join("%s %d" % (k, counts[k])
                                for k in sorted(counts)))
    if counts.get("pointer-unpinned") and not show_unpinned:
        print("unpinned pointers are a backlog, not a gate — list with --unpinned")
    if counts.get("pointer-unresolved"):
        print("unresolved is UNKNOWN, never a pass — pass --namespace-root "
              "for the sibling corpus")
    if not gate:
        print("reader mode — exits 0. Run with --gate to enforce.")
    return (1 if n_error else 0) if gate else 0


def run_floor(roots: List[Path], as_json: bool) -> int:
    """The undeclared-restatement worklist. Reader only; always exits 0."""
    corpus = _config.corpus_root()
    docs = list(iter_docs(roots, corpus))
    if not docs:
        print("could not look: no documents under %s"
              % ", ".join(str(r) for r in roots), file=sys.stderr)
        return 2

    result = {}
    n_rows = n_assert = n_cand = 0
    for d in docs:
        text = d.read_text(encoding="utf-8")
        cands, total, asserting = floor_candidates(text)
        if not total:
            continue
        r = rel(d, corpus)
        n_rows += total
        n_assert += asserting
        n_cand += len(cands)
        if cands:
            result[r] = cands

    if as_json:
        print(json.dumps({"summary": {"floor_rows": n_rows,
                                      "asserting": n_assert,
                                      "candidates": n_cand},
                          "candidates": {k: [{"line": l, "text": t}
                                             for l, t in v]
                                         for k, v in result.items()}},
                         indent=2))
        return 0

    for r in sorted(result):
        print("\n%s  (%d candidate)" % (r, len(result[r])))
        for line, row in result[r]:
            print("  %s:%d  %s" % (r, line, row[:150]))

    # THE SURFACE, not the count alone. `asserting` is the denominator the
    # candidate figure only means anything against, and `floor_rows` is the
    # denominator THAT only means anything against.
    print("\n%d floor row(s) across %d document(s) — %d assert a rule and cite "
          "a section, %d of those name no authority."
          % (n_rows, len(docs), n_assert, n_cand))
    print("A CANDIDATE IS NOT A FINDING. Whether a row RESTATES a rule or is "
          "its sole statement is decided by OPENING the cited section — some "
          "of these cite the only home there is. Reader only, always exits 0.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", action="append", type=Path,
                    help="document or dir to scan (repeatable; "
                         "default specs/ and guides/)")
    ap.add_argument("--namespace-root", action="append", type=Path, default=[],
                    help="a sibling corpus to resolve authorities in "
                         "(repeatable) — without it a cross-repo pointer is "
                         "UNKNOWN, not clean")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--unpinned", action="store_true",
                    help="list the unpinned backlog (non-gating)")
    ap.add_argument("--update", action="store_true",
                    help="pin/re-pin authority spans after reviewing them")
    ap.add_argument("--gate", action="store_true",
                    help="0 clean · 1 findings · 2 could-not-look")
    ap.add_argument("--floor", action="store_true",
                    help="UNDECLARED restatements in a conformance floor — a "
                         "worklist, never a verdict; always exits 0")
    args = ap.parse_args(argv)
    roots = args.root or DEFAULT_ROOTS
    if args.floor:
        return run_floor(roots, args.json)
    if args.update:
        return do_update(roots, _config.corpus_root(), args.namespace_root)
    return run_check(roots, args.namespace_root, args.json, args.unpinned,
                     args.gate)


if __name__ == "__main__":
    raise SystemExit(main())
