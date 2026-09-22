#!/usr/bin/env python3
"""census — which normative obligations does anyone downstream actually cite?

    spec census [--cohort DIR] [--doc NAME] [--json] [--drift] [--gaps]

**The problem this exists for, stated as the failure and not as a feature.**
Arch writes the specs; the cohort implements them; and when nothing goes wrong,
nothing comes back. So arch's picture of what is built is assembled from peer
reports (prose, dated, expiring) and from re-reading trees by hand. Both fail
the same way and the failure is on the record: a claim measured in one tree
published as a claim about a cohort, an absence measured with the wrong
checkout, a MUST that shipped and was gated by nothing for two releases. The
governing doctrine concedes the structural half outright — *"arch cannot
observe build state directly and every check it can run is the same check that
produced the error."*

**What is new here is that a deterministic join already exists and had never
been read.** The implementations annotate their own source with section
references back into this corpus. Measured on first run across the five
non-generated seats: **27,498 `§`-citations, 2,092 of them document-qualified**
in `entity-core-go` alone. That is a map, written by the implementers, of which
parts of the spec they believe they are implementing — and no arch instrument
had ever opened it.

So this analyzer inverts the usual direction. Every other one reads a document
against a rule. This one reads **the corpus against its consumers**.

What it computes, per (document, section):

  S   specified      — the section exists and carries normative tokens
  I   implemented    — at least one seat's PRODUCT source cites it
  X   exercised      — the conformance ORACLE cites it
  ?   ambiguous      — cited by a bare `§N.M` no rule could attribute

and reports four findings from the shape of that table:

  unobserved-must    Normative tokens, cited by product code, and cited by NO
                     oracle check. **This is the class that produced FM-1**:
                     `ENTITY-CORE-PROTOCOL` §4.7 declares itself a
                     "normative MUST-emit contract" with ten rows, roughly one
                     of which is gated, and the contradiction between two of
                     its rows survived two releases because nothing drove
                     them. It is also live in this corpus right now — the
                     `EXTENSION-RELAY` §4.2 poll-visibility rule landed
                     2026-08-30 with three private unit tests behind it and no
                     cross-impl check at all.

  uncited-section    Normative tokens and NO citation from any seat, product
                     or oracle. Weaker than it sounds and deliberately not an
                     error: plenty of correct code cites nothing. It is a
                     reading list, ordered by MUST density.

  orphan-citation    A seat cites a section this corpus does not have.
                     Either the section moved (and an implementer is working
                     from a stale reading) or the citation was always wrong.
                     `spec address` finds this for documents citing documents;
                     this finds it for CODE citing documents, which is the
                     direction that reaches an implementer.

  spec-moved-under   `--drift` only. The section's NORMATIVE content changed
                     after the last commit touching the file that cites it:
                     the obligation moved and the implementation has not been
                     opened since. The one finding here that is about TIME
                     rather than presence, and the closest thing to a
                     mechanical answer to "who did not get told."

                     Normative content, not lines. A blame-based first draft
                     reported 2,174 findings clustered on one date, because a
                     corpus-wide prose sweep had touched every line of every
                     spec without moving a single obligation.

**What a citation is, and what it is not.** A `§`-reference in a comment is
evidence of *attention*, not of *correctness*. A seat can cite §4.2 and
implement it wrong; a seat can implement §4.2 perfectly and cite nothing. So:

  - `I` means *someone downstream believes this section is theirs*. It is not a
    conformance result and must never be reported as one.
  - A blank cell means **unknown**, never "unbuilt" — the same rule the cohort
    build ledger already runs under, for the same reason.
  - The `?` bucket is reported separately and is never silently resolved. A
    guessed attribution would produce exactly the false-confidence artifact
    this tool exists to replace.

**Reader by default, exits 0**, on the same reasoning that keeps `coverage` a
reader: the first run reports a large backlog by construction, and a gate that
is red on day one teaches people to skip it. `--gate` is available for when a
scoped subset is clean enough to hold.

**Could-not-look is not a pass.** If no cohort tree resolves, this exits **2**
and says so. The wrong-checkout failure — an absence measured against a stale
clone on a different branch, nearly published as a claim that five seats had no
relay implementation — is precisely what a silent empty scan looks like. Every
run therefore prints the seats it resolved, their branch and HEAD, and the file
count it read, because **the set actually scanned is part of the answer.**

**Document attribution is derived from the corpus, never hardcoded.** A bare
`§6.2` in `ext/relay/relay.go` is attributed to `EXTENSION-RELAY` because the
corpus contains a document whose stem token is `relay` and the path carries it.
Add an extension and the mapping follows; there is no table to forget to
update. Where two stems both match, or none does, the citation goes to `?`.

Stdlib-only Python 3.11+.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import config as _config

_CFG = _config.load()
_CENSUS = _CFG.analyzer("census")

# Seats to scan, relative to the corpus root's PARENT (the polyrepo checkout).
# A seat that is not present is skipped and named in the run header — never
# silently dropped, because an unscanned seat and a clean seat produce
# byte-identical output.
_SEATS: Dict[str, dict] = _CENSUS.get("seats", {})

# Documents whose sections are the obligations. Scoped to the published
# surface: specs and guides, in this repo and in the sibling core-protocol
# repo, since a citation to `V7 §4.6` resolves there and reporting it as
# dangling would be "could-not-look wearing a verdict's clothes".
_NAMESPACE_ROOTS: List[str] = _CENSUS.get("namespace_roots", [])

# `V7` is how the whole cohort spells `ENTITY-CORE-PROTOCOL` in source. An
# alias table is the honest way to carry that: the alternative is a bare
# 993-citation bucket reported as ambiguous.
_ALIASES: Dict[str, str] = _CENSUS.get("aliases", {})

_RULES: Dict[str, str] = _CENSUS.get("rules", {})

# `### §6.2 Something` or `## 6.2 Something` — the section sign is optional and
# BOTH forms are live in this corpus. Requiring the bare form measured
# `EXTENSION-SUBSTITUTE` §9.1 as absent when it is present and `[RULED]`; that
# false negative is the reason this pattern is written the way it is.
HEADING_RE = re.compile(r"^#{1,6}\s+§?\s?([0-9]+[0-9a-z]*(?:\.[0-9a-z]+)*)\b")

# A citation in source: an optional document qualifier within a short window,
# then the section sign. The window is deliberately tight — a document name
# forty characters away is prose about something else.
#
# The alternation must include the BARE form, because that is how the cohort
# actually writes it: `NETWORK §6.5.2b`, `REVISION §4.3.1`, `RELAY §8` — not
# `EXTENSION-NETWORK §6.5.2b`. Matching only the prefixed form sent every one
# of those to bare-inference, which cost ~1,500 citations of attribution in
# `entity-core-go` alone and hid a real defect in three conformance checks.
# The bare names are DERIVED from the corpus (see `derived_aliases`), so a new
# extension is covered the day it lands.
#
# The alternation is BUILT FROM THE CORPUS at run time (`qualified_re`), not
# written out here. Two attempts came before that and both were wrong in
# instructive ways:
#
#   Prefixed forms only (`EXTENSION-NETWORK`) — misses how the cohort actually
#   writes it (`NETWORK §6.5.2b`, `REVISION §4.3.1`, `RELAY §8`), sending
#   thousands of perfectly clear citations to the ambiguous bucket.
#
#   Any uppercase token (`[A-Z][A-Z0-9-]{2,}`) — matches `TODO`, `HTTP`, `PUT`,
#   `NOTE`. Ambiguity went UP by 431 in one seat, because a matched qualifier
#   that names no document is worse than no qualifier at all: it consumes the
#   citation and blocks the path-based inference that would have resolved it.
#
# A closed alternation over the documents that exist has neither failure, and
# it extends itself the day a spec lands.
SECTION_TAIL = r"[^\n§]{0,24}?§\s?([0-9]+[0-9a-z]*(?:\.[0-9a-z]+)*)"
BARE_RE = re.compile(r"§\s?([0-9]+[0-9a-z]*(?:\.[0-9a-z]+)*)")

NORMATIVE_RE = re.compile(r"\b(MUST NOT|MUST|SHALL NOT|SHALL|REQUIRED)\b")

# How far back to walk a document's own history looking for the commit that
# last changed a section's normative content. Generous: the release boundary
# re-authors published commits, so specs here carry 5-22 commits, not hundreds.
DRIFT_MAX_COMMITS = 80

# Below this, the spec edit and the implementation edit are the same piece of
# work, not a notification failure. One day.
DRIFT_MIN_GAP = 86400


class Finding:
    __slots__ = ("rule", "doc", "section", "text")

    def __init__(self, rule: str, doc: str, section: str, text: str):
        self.rule = rule
        self.doc = doc
        self.section = section
        self.text = text

    def severity(self) -> str:
        return _RULES.get(self.rule, "warn")


# --------------------------------------------------------------------------
# 1. Obligations — the corpus side
# --------------------------------------------------------------------------

def sections_of(path: Path) -> List[Tuple[str, int, int, int]]:
    """(section, start_line, end_line, normative_token_count) for one document.

    A section owns its lines up to the next heading at any level. Nesting is
    not modelled: `§6.2` and `§6.2.1` are separate rows, which matches how
    they are cited.
    """
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    marks: List[Tuple[str, int]] = []
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m:
            marks.append((m.group(1).rstrip("."), i))
    out: List[Tuple[str, int, int, int]] = []
    for j, (sec, start) in enumerate(marks):
        end = marks[j + 1][1] if j + 1 < len(marks) else len(lines)
        body = "\n".join(lines[start:end])
        out.append((sec, start + 1, end, len(NORMATIVE_RE.findall(body))))
    return out


# A document stem the cohort could plausibly cite: this corpus's SCREAMING-KEBAB
# authoring convention. The filter is not cosmetic — without it,
# `specs/test-vectors/crypto-agility/CHANGELOG.md` is loaded as a document, its
# derived token is `changelog`, and every bare `§` in any file under a path
# containing that word is attributed to it. That was 16 false orphans on the
# first run, and every one of them read like a real finding.
DOC_STEM_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+$")
_DOC_SKIP_DIRS = ("test-vectors",)


# Not every `§`-shaped token is a section reference. Two shapes were measured
# on the first run and both read like real findings until they were opened:
#
#   `§2688`, `§975`, `§232`  — a LINE number in a citation of the form
#                              "V7 §2688". A bare integer of three digits or
#                              more is never a section in this corpus.
#   `§6.x`, `§4.3.x`         — a deliberate placeholder for "the subsections
#                              of §6", written by implementers on purpose.
#
# Reporting either as a defect would be the tool inventing work for the cohort,
# which is the failure mode an instrument like this has to be most careful of:
# it publishes to five seats at once.
PLACEHOLDER_RE = re.compile(r"(^|\.)x$", re.IGNORECASE)


def is_section_ref(sec: str) -> bool:
    if PLACEHOLDER_RE.search(sec):
        return False
    head = sec.split(".")[0]
    if head.isdigit() and len(head) >= 3:
        return False
    return True


def corpus_documents(corpus: Path) -> Dict[str, Path]:
    """Stem -> path, over the published surface of this repo and the sibling
    namespace roots. Keyed by stem because that is how source cites it."""
    docs: Dict[str, Path] = {}
    roots = [corpus / "specs", corpus / "guides"]
    for extra in _NAMESPACE_ROOTS:
        p = (corpus / extra).resolve()
        roots.extend([p / "specs", p / "guides"])
    for root in roots:
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*.md")):
            if any(d in p.parts for d in _DOC_SKIP_DIRS):
                continue
            if not DOC_STEM_RE.match(p.stem):
                continue
            docs.setdefault(p.stem, p)
    return docs


def build_obligations(docs: Dict[str, Path]) -> Dict[Tuple[str, str], dict]:
    ob: Dict[Tuple[str, str], dict] = {}
    for stem, path in docs.items():
        for sec, start, end, musts in sections_of(path):
            ob[(stem, sec)] = {"path": path, "line": start, "end": end,
                               "musts": musts}
    return ob


# --------------------------------------------------------------------------
# 2. Attribution — derived from the corpus, never a hardcoded table
# --------------------------------------------------------------------------

def derived_aliases(docs: Dict[str, Path]) -> Dict[str, str]:
    """Every way a document is spelled in source, derived from the corpus.

    `EXTENSION-NETWORK` is written `NETWORK` in cohort source far more often
    than in full; `SDK-OPERATIONS` is written `SDK-OPERATIONS`. The bare form
    is registered only when it is unambiguous across the whole corpus — if two
    documents reduce to the same bare name, neither claims it, and the
    citation stays ambiguous rather than being awarded to whichever sorted
    first.
    """
    counts: Dict[str, List[str]] = defaultdict(list)
    for stem in docs:
        for prefix in ("EXTENSION-", "APP-CONVENTION-", "GUIDE-", "SDK-"):
            if stem.startswith(prefix):
                counts[stem[len(prefix):]].append(stem)
                break
    out = dict(_ALIASES)
    for bare, owners in counts.items():
        if len(owners) == 1 and bare not in docs:
            out.setdefault(bare, owners[0])
    return out


def qualified_re(aliases: Dict[str, str], docs: Dict[str, Path]):
    """The citation pattern, closed over the names that actually exist.

    Longest-first so `EXTENSION-NETWORK` is preferred over `NETWORK` and the
    match does not stop halfway through a name.
    """
    names = sorted(set(aliases) | set(docs), key=len, reverse=True)
    alt = "|".join(re.escape(n) for n in names)
    # NOT `\b...\b`. A hyphen is a word boundary, so `\bTYPE\b` matches the
    # `TYPE` inside `TYPE-SYSTEM` and charges every `TYPE-SYSTEM spec §9.4` in
    # `entity-core-py` to `EXTENSION-TYPE`, whose §9 has no subsections at all.
    # That was 12 of 52 orphans on one run — a dozen confident, specific, wrong
    # findings about one seat, which is exactly the artifact this tool exists to
    # stop producing. The lookarounds require the matched name to be the WHOLE
    # hyphenated token.
    return re.compile(r"(?<![A-Z0-9-])(" + alt + r")(?![A-Z0-9-])" + SECTION_TAIL)


def stem_tokens(docs: Dict[str, Path]) -> Dict[str, str]:
    """`EXTENSION-RELAY` -> token `relay`, for attributing a bare `§N.M` by the
    directory the citing file sits in.

    Derived from the corpus, so adding an extension extends the mapping for
    free and there is no table to forget to update. Restricted to `EXTENSION-*`
    because those are the documents whose subject is also a source directory
    name — `APP-CONVENTION-SEMANTIC-CONTENT-SITE` yields the token `site`,
    which matches half of every front-end tree and is why the unrestricted
    version produced dozens of confident wrong attributions.
    """
    out: Dict[str, str] = {}
    for stem in docs:
        if not stem.startswith("EXTENSION-"):
            continue
        tok = stem.split("-")[-1].lower()
        if len(tok) >= 4 and tok not in out:
            out[tok] = stem
    return out


def attribute(line: str, segments: Set[str], docs: Dict[str, Path],
              tokens: Dict[str, str], aliases: Dict[str, str],
              qual_re) -> List[Tuple[Optional[str], str, bool]]:
    """Every citation on one line, as (document-stem or None, section, qualified).

    A qualified citation wins outright. A bare one is attributed only when the
    citing file's path contains **exactly one** token as a whole path segment
    or file stem; two matches or none resolve to `None`, which is reported as
    ambiguous and never guessed.

    The third element is what keeps the tool honest. An *inferred* attribution
    that fails to resolve is evidence the inference was wrong, not evidence the
    implementer cited a section that does not exist — so only a **qualified**
    citation is ever allowed to produce an `orphan-citation` finding. Without
    that rule the first run reported 529 orphans, essentially all of them the
    tool's own guesses charged to the cohort.
    """
    out: List[Tuple[Optional[str], str, bool]] = []
    consumed: Set[int] = set()
    for m in qual_re.finditer(line):
        raw = m.group(1)
        stem = aliases.get(raw, raw)
        known = stem in docs
        out.append((stem if known else None, m.group(2).rstrip("."), known))
        consumed.add(m.end(2))

    hits = sorted(tok for tok in tokens if tok in segments)
    inferred = tokens[hits[0]] if len(hits) == 1 else None
    for m in BARE_RE.finditer(line):
        if m.end(1) in consumed:
            continue
        out.append((inferred, m.group(1).rstrip("."), False))
    return out


def path_segments(relpath: str) -> Set[str]:
    """Whole path segments and file stems, lowercased. Segment equality rather
    than substring containment: `composite/` must not match `site`."""
    parts = relpath.lower().replace("\\", "/").split("/")
    segs = set(parts)
    if parts:
        stem = parts[-1].rsplit(".", 1)[0]
        segs.add(stem)
        segs.update(stem.split("_"))
    return segs


# --------------------------------------------------------------------------
# 3. The seats
# --------------------------------------------------------------------------

def git(repo: Path, *args: str) -> str:
    try:
        r = subprocess.run(("git", "-C", str(repo)) + args, capture_output=True,
                           text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def seat_files(root: Path, globs: List[str], skip: List[str]) -> List[Path]:
    out: List[Path] = []
    for g in globs:
        for p in root.rglob(g):
            rel = str(p.relative_to(root))
            if any(s in rel for s in skip):
                continue
            out.append(p)
    return sorted(out)


def scan_seat(name: str, root: Path, spec: dict, docs: Dict[str, Path],
              tokens: Dict[str, str], aliases: Dict[str, str],
              qual_re) -> dict:
    """One seat's citations, split into product and oracle.

    The split is the whole point: a section cited only by product code is
    implemented-and-ungated, which is a different and more urgent state than
    uncited. `oracle_paths` names the conformance harness within the seat.
    """
    globs = spec.get("source", [])
    skip = spec.get("skip", [])
    oracle = spec.get("oracle_paths", [])
    product: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    checks: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    # Qualified citations are tracked separately because they are the only ones
    # allowed to accuse the cohort of citing a section that does not exist.
    qualified: Set[Tuple[str, str]] = set()
    ambiguous = 0
    total = 0
    files = seat_files(root, globs, skip)
    for p in files:
        rel = str(p.relative_to(root))
        is_oracle = any(o in rel for o in oracle)
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "§" not in text:
            continue
        segs = path_segments(rel)
        for line in text.splitlines():
            if "§" not in line:
                continue
            for stem, sec, is_q in attribute(line, segs, docs, tokens, aliases, qual_re):
                total += 1
                if stem is None:
                    ambiguous += 1
                    continue
                (checks if is_oracle else product)[(stem, sec)].add(rel)
                if is_q:
                    qualified.add((stem, sec))
    return {"name": name, "root": root, "files": len(files), "total": total,
            "ambiguous": ambiguous, "product": product, "checks": checks,
            "qualified": qualified,
            "branch": git(root, "rev-parse", "--abbrev-ref", "HEAD"),
            "head": git(root, "rev-parse", "--short", "HEAD")}


def resolve_seats(corpus: Path) -> Tuple[List[dict], List[str]]:
    """(present, missing). A missing seat is NAMED, not dropped."""
    base = corpus.parent
    present: List[dict] = []
    missing: List[str] = []
    for name, spec in _SEATS.items():
        root = (base / spec.get("path", name)).resolve()
        if root.is_dir():
            present.append({"name": name, "root": root, "spec": spec})
        else:
            missing.append(name)
    return present, missing


# --------------------------------------------------------------------------
# 4. Drift — the time axis
# --------------------------------------------------------------------------

def history_is_collapsed(times: List[int]) -> bool:
    """True when a document's commit dates carry no usable time signal.

    Two shapes, both measured: fewer than three distinct days, or one day
    holding 80% or more of the commits. `ENTITY-CORE-PROTOCOL` is the worked
    example — **nine of its ten commits share one date**, because [ADR-0027]
    re-authors published history at the release boundary.
    """
    if not times:
        return True
    days = [w // 86400 for w in times]
    distinct = set(days)
    if len(distinct) < 3:
        return True
    top = max(days.count(d) for d in distinct)
    return top >= 0.8 * len(days)


class CollapsedHistory(Exception):
    """The document's commit dates are not a usable time axis — see
    `section_last_normative_change`. Raised rather than returned so a caller
    cannot mistake it for "no sections changed"."""

    def __init__(self, rel: str, commits: int, distinct_days: int):
        super().__init__(rel)
        self.rel = rel
        self.commits = commits
        self.distinct_days = distinct_days


def repo_of(path: Path) -> Optional[Path]:
    p = path
    while p != p.parent:
        if (p / ".git").exists():
            return p
        p = p.parent
    return None


def normative_fingerprint(text: str) -> Dict[str, str]:
    """Section -> a digest of its NORMATIVE sentences only.

    This is the whole reason drift is not computed from `git blame`. The first
    implementation was blame-based and reported **2,174** findings, clustered
    on a single date: a corpus-wide prose sweep had touched every line of every
    spec without changing one obligation, and blame cannot tell those apart.
    A rule that fires on a reformat is a rule that gets switched off in a week.

    So the unit is the set of lines carrying a normative token. Rewording the
    rationale around a MUST does not move it; changing the MUST does.
    """
    lines = text.splitlines()
    marks: List[Tuple[str, int]] = []
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m:
            marks.append((m.group(1).rstrip("."), i))
    out: Dict[str, str] = {}
    for j, (sec, start) in enumerate(marks):
        end = marks[j + 1][1] if j + 1 < len(marks) else len(lines)
        keep = [re.sub(r"\s+", " ", l).strip()
                for l in lines[start:end] if NORMATIVE_RE.search(l)]
        if keep:
            out[sec] = hashlib.sha256("\n".join(keep).encode()).hexdigest()[:16]
    return out


def section_last_normative_change(path: Path, max_commits: int) -> Dict[str, int]:
    """Section -> author-time of the newest commit that changed its normative
    content, walked from the document's own history.

    Cheap here for a structural reason worth stating: [ADR-0027] re-authors
    every published commit at the release boundary, so a spec file carries
    5-22 commits rather than hundreds. `max_commits` bounds it regardless, and
    a section whose change is not found inside the window is simply ABSENT
    from the result rather than reported as unchanged — could-not-look is not
    a clean bill of health.
    """
    repo = repo_of(path)
    if repo is None:
        return {}
    try:
        rel = str(path.resolve().relative_to(repo.resolve()))
    except ValueError:
        return {}
    log = git(repo, "log", "--format=%H %at", "-n", str(max_commits), "--", rel)
    if not log:
        return {}
    revs: List[Tuple[str, int]] = []
    for line in log.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit():
            revs.append((parts[0], int(parts[1])))
    revs.reverse()  # oldest first

    # A document whose history was RE-AUTHORED has no usable time axis, and
    # that must be detected rather than measured through. [ADR-0027] writes
    # every published commit fresh at the release boundary: measured on
    # `ENTITY-CORE-PROTOCOL`, **nine of its ten commits carry one date**, so
    # every section touched in that batch reports the same 63-day gap against
    # every implementation file older than the cut. That was 176 findings, all
    # of them an artifact of the boundary and none of them a notification
    # failure.
    #
    # This is L24's property on the time axis: an identifier that does not
    # survive the boundary cannot carry a claim across it. Where the axis is
    # collapsed we return **nothing and say so** — could-not-look, not clean.
    if history_is_collapsed([w for _, w in revs]):
        raise CollapsedHistory(rel, len(revs),
                               len({w // 86400 for _, w in revs}))

    changed: Dict[str, int] = {}
    prev: Optional[Dict[str, str]] = None
    for sha, when in revs:
        blob = git(repo, "show", "%s:%s" % (sha, rel))
        if not blob:
            continue
        cur = normative_fingerprint(blob)
        if prev is None:
            # The OLDEST revision in the window establishes the baseline; it is
            # not itself an edit. Treating it as one put every section's "last
            # change" at the bottom of the window, which produced a 63-day
            # cluster spanning half the cohort — the release boundary
            # re-authors published history ([ADR-0027]), so the oldest visible
            # commit is usually an artifact of the boundary and not a change
            # anyone made. A section that never moves inside the window is
            # simply absent from this map: unknown, not unchanged.
            prev = cur
            continue
        for sec, digest in cur.items():
            if prev.get(sec) != digest:
                changed[sec] = when
        prev = cur
    return changed


def file_mtime(root: Path, rel: str) -> int:
    out = git(root, "log", "-1", "--format=%at", "--", rel)
    return int(out) if out.isdigit() else 0


# --------------------------------------------------------------------------
# 5. Report
# --------------------------------------------------------------------------

def run(corpus: Path, only_doc: Optional[str], as_json: bool, gaps: bool,
        drift: bool, gate: bool) -> int:
    docs = corpus_documents(corpus)
    if not docs:
        print("no specs/ or guides/ under %s" % corpus, file=sys.stderr)
        print("  scanned 0 documents — this is not a pass.", file=sys.stderr)
        return 2

    obligations = build_obligations(docs)
    tokens = stem_tokens(docs)
    aliases = derived_aliases(docs)
    qual_re = qualified_re(aliases, docs)
    present, missing = resolve_seats(corpus)
    if not present:
        print("no cohort tree resolved beside %s" % corpus, file=sys.stderr)
        print("  looked for: %s" % ", ".join(sorted(_SEATS)), file=sys.stderr)
        print("  scanned 0 seats — this is COULD-NOT-LOOK, not a clean census.",
              file=sys.stderr)
        return 2

    seats = [scan_seat(s["name"], s["root"], s["spec"], docs, tokens, aliases, qual_re)
             for s in present]

    product: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    checks: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
    qualified: Set[Tuple[str, str]] = set()
    for s in seats:
        for k in s["product"]:
            product[k].add(s["name"])
        for k in s["checks"]:
            checks[k].add(s["name"])
        qualified |= s["qualified"]

    findings: List[Finding] = []
    cited_keys = set(product) | set(checks)

    # Only a QUALIFIED citation may produce an orphan. An inferred attribution
    # that does not resolve is a defect in the inference, and charging it to the
    # cohort is exactly the "measured in one tree, published about all" shape.
    #
    # And "not a heading" is not "not in the document". Plenty of live sections
    # are table rows or numbered clauses inside a parent heading — §4.7 row 6 is
    # the one that just cost the cohort a release cycle. So a citation resolves
    # if the document mentions it ANYWHERE; only a section the document never
    # names at all is an orphan.
    body_cache: Dict[str, str] = {}
    for key in sorted(cited_keys & qualified):
        stem, sec = key
        if stem not in docs or not is_section_ref(sec):
            continue
        if key in obligations:
            continue
        body = body_cache.get(stem)
        if body is None:
            body = docs[stem].read_text(encoding="utf-8", errors="replace")
            body_cache[stem] = body
        if re.search(r"§\s?%s\b" % re.escape(sec), body):
            continue
        findings.append(Finding(
            "orphan-citation", stem, sec,
            "cited by %s; the document never names this section — it moved, "
            "or the citation was always wrong"
            % ", ".join(sorted(product.get(key, set()) | checks.get(key, set())))))

    for (stem, sec), meta in sorted(obligations.items()):
        if only_doc and only_doc not in stem:
            continue
        if meta["musts"] == 0:
            continue
        key = (stem, sec)
        impls = product.get(key, set())
        gates = checks.get(key, set())
        if impls and not gates:
            findings.append(Finding(
                "unobserved-must", stem, sec,
                "%d normative token(s); implemented per %s; NO oracle check "
                "cites it" % (meta["musts"], ", ".join(sorted(impls)))))
        elif not impls and not gates:
            findings.append(Finding(
                "uncited-section", stem, sec,
                "%d normative token(s); no seat cites it (product or oracle)"
                % meta["musts"]))

    drift_findings: List[Finding] = []
    drift_skipped: List[Tuple[str, int, int]] = []
    if drift:
        by_doc: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        for key in cited_keys:
            if key not in obligations:
                continue
            if only_doc and only_doc not in key[0]:
                continue
            if obligations[key]["musts"] == 0:
                continue
            by_doc[key[0]].append(key)
        mtime_cache: Dict[Tuple[str, str], int] = {}
        for stem, keys in sorted(by_doc.items()):
            try:
                mt = section_last_normative_change(docs[stem], DRIFT_MAX_COMMITS)
            except CollapsedHistory as ch:
                # NAMED, never dropped. A document we could not time-check and
                # a document that came out clean are the same output otherwise.
                drift_skipped.append((stem, ch.commits, ch.distinct_days))
                continue
            for key in sorted(keys):
                spec_t = mt.get(key[1])
                if not spec_t:
                    continue
                for s in seats:
                    for rel in sorted(s["product"].get(key, set()) |
                                      s["checks"].get(key, set())):
                        ck = (s["name"], rel)
                        if ck not in mtime_cache:
                            mtime_cache[ck] = file_mtime(s["root"], rel)
                        ft = mtime_cache[ck]
                        # A gap under one day is same-session work, not drift.
                        if ft and spec_t - ft > DRIFT_MIN_GAP:
                            days = (spec_t - ft) // 86400
                            drift_findings.append(Finding(
                                "spec-moved-under", stem, key[1],
                                "%s:%s last touched %dd BEFORE this section's "
                                "normative content last changed" % (s["name"], rel, days)))
        findings.extend(drift_findings)

    n_err = sum(1 for f in findings if f.severity() == "error")

    if as_json:
        print(json.dumps({
            "summary": {
                "documents": len(docs), "sections": len(obligations),
                "normative_sections": sum(1 for m in obligations.values() if m["musts"]),
                "seats_scanned": [s["name"] for s in seats],
                "seats_missing": missing,
                "drift_undeterminable": [s for s, _, _ in drift_skipped],
                "citations": sum(s["total"] for s in seats),
                "ambiguous": sum(s["ambiguous"] for s in seats),
                "findings": len(findings), "errors": n_err,
            },
            "findings": [{"rule": f.rule, "severity": f.severity(),
                          "document": f.doc, "section": f.section,
                          "text": f.text} for f in findings],
        }, indent=2))
        return 1 if (gate and n_err) else 0

    print("census — the corpus against its consumers\n")
    print("  corpus     %s" % corpus)
    print("  documents  %d  (%d sections, %d carrying normative tokens)"
          % (len(docs), len(obligations),
             sum(1 for m in obligations.values() if m["musts"])))
    print("  seats read:")
    for s in seats:
        print("    %-24s %-8s %-9s %5d files  %6d citations  %5d ambiguous"
              % (s["name"], s["branch"] or "?", s["head"] or "?", s["files"],
                 s["total"], s["ambiguous"]))
    if missing:
        print("    NOT PRESENT: %s  (named, not dropped — an unscanned seat "
              "and a clean seat look identical)" % ", ".join(missing))

    by_rule: Dict[str, List[Finding]] = defaultdict(list)
    for f in findings:
        by_rule[f.rule].append(f)

    order = ["orphan-citation", "spec-moved-under", "unobserved-must",
             "uncited-section"]
    for rule in order:
        fs = by_rule.get(rule, [])
        if not fs:
            continue
        print("\n%s — %d" % (rule, len(fs)))
        shown = fs if (gaps or rule != "uncited-section") else fs[:25]
        for f in shown:
            print("  %-6s %-34s §%-12s %s"
                  % (f.severity().upper(), f.doc, f.section, f.text))
        if len(shown) < len(fs):
            print("  … %d more (pass --gaps for the full list)"
                  % (len(fs) - len(shown)))

    if drift_skipped:
        print("\ndrift NOT determinable — %d document(s)" % len(drift_skipped))
        for stem, ncommits, ndays in sorted(drift_skipped):
            print("  SKIP   %-34s %d commit(s) across %d distinct day(s) — "
                  "history re-authored at the release boundary ([ADR-0027]); "
                  "commit dates are not a time axis here"
                  % (stem, ncommits, ndays))
        print("  This is COULD-NOT-LOOK. These documents are not drift-clean; "
              "they are unmeasured.")

    amb = sum(s["ambiguous"] for s in seats)
    tot = sum(s["total"] for s in seats)
    print("\n%d citation(s) read across %d seat(s); %d could not be attributed "
          "to a document and are NOT counted either way." % (tot, len(seats), amb))
    print("A citation is evidence of ATTENTION, not of correctness. A blank "
          "cell means unknown, never unbuilt.")
    return 1 if (gate and n_err) else 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="spec census",
        description="Normative obligations against the citations the cohort "
                    "writes back into its own source.")
    ap.add_argument("--corpus", type=Path, default=None)
    ap.add_argument("--doc", default=None,
                    help="restrict the obligation side to documents whose stem "
                         "contains this substring")
    ap.add_argument("--gaps", action="store_true",
                    help="print every uncited section rather than the head")
    ap.add_argument("--drift", action="store_true",
                    help="also check whether a cited section changed after the "
                         "citing file was last touched (one git blame per doc)")
    ap.add_argument("--gate", action="store_true",
                    help="exit 1 on error-severity findings (reader by default)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    corpus = _config.corpus_root(a.corpus)
    return run(corpus, a.doc, a.json, a.gaps, a.drift, a.gate)


if __name__ == "__main__":
    sys.exit(main())
