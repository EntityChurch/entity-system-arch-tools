#!/usr/bin/env python3
"""standards — release-readiness checker + refiner for the entity-core spec corpus.

Mechanical enforcement of `SPECIFICATION-FORMAT.md`: it checks each normative
spec for a release-grade shape (clean header, declared status/depends, no
process narrative fossilized into normative text) and reports every deviation
with file:line.

Modes:

    spec standards [--root DIR|FILE ...]            # check (default): flag deviations
    spec standards --refine --root FILE --output D  # refine: write a cleaned copy to D
    spec standards --init-baseline                  # accept today's debt (one-time)
    spec standards --update-baseline                # ratchet the baseline DOWN
    spec standards --no-baseline                    # report the full un-ratcheted state

THE BASELINE RATCHET. Five rules — `impl-team-ref`, `date-in-body`,
`proposal-citation`, `amendment-provenance`, `document-history-section` — flag
process narrative fossilized into normative text: which implementation built a
thing, on what date, argued by whom. They are the difference between a spec and
a lab notebook, and a spec is implemented by people who have never heard of this
cohort.

All five were `warn` for months and were firing correctly the entire time: 573
findings across 26 of 40 specs on the arch corpus, in runs that printed
"✓ all gates passed". That is this ecosystem's own D9 conclusion turned on its
own toolchain — *a WARN in a green run is a claim nobody reads.*

Promoting them to `error` alone would have turned the corpus red on contact, and
a gate that is red on arrival gets switched off. So severity ships with a
ratchet: findings within the count recorded in `<corpus>/.spec-baseline.json` are
reported as **known debt** and do not gate; anything beyond it is an **error**.
The baseline lives with the corpus it describes, not in this repo.

`--update-baseline` may only ever LOWER a count and refuses, atomically, to
raise one. That asymmetry is the entire mechanism: a baseline that can be raised
is not a ratchet but a rubber stamp, and the next contaminated commit
re-baselines itself green while looking clean.

*What it does not see.* Entries are keyed `(file, rule) → count`, so a **swap is
invisible** — delete one violation and add a different one in the same file and
the count is unchanged. Line numbers were rejected as a key because every edit
above a finding moves it, so a line-keyed baseline reports whole files as new
debt on unrelated changes and gets deleted within a week. This gate catches
ACCUMULATION, not SUBSTITUTION; a reviewer still reads the diff. What it
guarantees is that the total never silently grows.

Refine applies only the *safe* mechanical fixes (collapse a changelog-blob
Version header to a bare version; drop a trailing Document History section).
It never edits normative prose — inline dates / impl-team refs / proposal
citations are reported as remaining editorial work, not auto-stripped, because
they may sit next to load-bearing text. The source file is never modified.

Boundary: the publish-time scrub (secrets, dates, license furniture) is
`entity-core-devops/release-builder`'s job. This analyzer is spec-standards
conformance only — the quality bar, paralleling `spec style` for naming.

Stdlib-only Python 3.11+. Exit code is non-zero when gating (error) violations
exist, so it composes as a contributor/CI gate.
(Was tools/spec-standards/spec_standards.py.)
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
import config as _config  # sibling in tools/spec/

# Corpus knowledge — root, excludes, accepted Status values — now comes from the
# single source of truth (tools/spec/config.default.toml, scope "core-specs-strict").
# The format spec quotes counter-examples; never lint the rulebooks themselves —
# that exclusion now lives in config exclude_files.
_CFG = _config.load()
_SCOPE = _CFG.scope("core-specs-strict")
DEFAULT_ROOT = _SCOPE.root
EXCLUDE_DIRS = _SCOPE.exclude_dirs
EXCLUDE_FILES = _SCOPE.exclude_files

CANONICAL_STATUS = _CFG.canonical_status

# ---- rule catalog -----------------------------------------------------------
# severity: "error" gates (non-zero exit); "warn" reports (editorial candidates).
RULES = {
    "header-version-missing":   ("error", "no `**Version**:` header field"),
    "header-version-blob":      ("error", "Version field carries a changelog blob, not a bare version"),
    "header-status-missing":    ("error", "no `**Status**:` header field"),
    "header-status-unknown":    ("warn",  "Status value not one of Draft/Active/Superseded/Normative"),
    "title-not-h1":             ("error", "first content line is not an H1 title"),
    "depends-missing":          ("error", "extension spec without a `**Depends**:` declaration (§8.1)"),
    "document-history-section": ("error", "Document History section (process history; belongs in the changelog)"),
    "date-in-body":             ("error", "calendar date in body (internal-lab timing; not normative)"),
    "impl-team-ref":            ("error", "implementation/team reference (internal process; not normative)"),
    "proposal-citation":        ("error", "proposal-filename citation (internal routing; not normative)"),
    "proposal-citation-unresolved": ("warn", "cited proposal not found, and no archive root was configured to look in"),
    "proposal-citation-dangling":   ("error", "cited proposal resolves to no file under any configured root"),
    "amendment-provenance":     ("error", "amendment-provenance note (how-we-got-here; not normative)"),
    "hash-width-pin":           ("error", "hash width stated as a requirement (SPECIFICATION-FORMAT.md §8.4.5)"),
}

# `entity-browser-rust` was absent from this alternation for months, and the gap is
# instructive: every *other* seat is caught by a bare word this list already carries
# (`workbench` catches entity-workbench-go, `keystone` catches entity-core-keystone),
# and the browser seat is the only one whose repo name shares no such token — it is
# neither `entity-core-*` nor a one-word product name. So the rule read as complete
# while being blind to exactly one team, and a seat name reached normative text.
# Match the bare form too: prose says "browser-rust" as often as the full repo name.
IMPL_TEAM_RE = re.compile(
    r"\b(cohort|keystone|workbench|egui|godot|raylib"
    r"|entity-core-(?:go|rust|python|py)|(?:entity-)?browser-rust|wb-go)\b",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
PROPOSAL_RE = re.compile(r"\bPROPOSAL-[A-Z0-9]|\bproposals/")
AMENDMENT_RE = re.compile(r"\bAmendment\s+\d", re.IGNORECASE)
VERSION_TOKEN_RE = re.compile(r"^\s*v?(\d+(?:\.\d+)*)\b")

# ---- hash-width-pin (SPECIFICATION-FORMAT.md §8.4.5) ------------------------
# A content hash is (format_code, digest); its length follows the leading varint
# and is never a constant. This rule fires where a width literal sits next to a
# hash term -- the shape that shipped `hex33` past three reviews, pinned
# NETWORK 6.5.3.1 at 66 while the same bullet promised crypto-agility, and fixed
# ENCRYPTION 7.3's HKDF `info` at 33 bytes, which derives a key.
#
# A width is legitimate as a WORKED INSTANCE of a format, or where the format
# itself is pinned (8.4.6 derive-to-meet). Both are recognised by the text
# saying so within EXEMPT_WINDOW lines -- the acknowledgement is the exemption,
# so a width can never appear without a reader being told why it is safe.
HASH_CTX_RE = re.compile(
    # `content hash` with a SPACE is the prose form -- the NETWORK 6.5.3.1 bullet
    # was written that way, so an underscore-only pattern missed the defect the
    # rule exists for. Caught by standards_selftest.
    r"content[\s_-]hash|hash hex|system/hash|hex33|hex\(|\bdigest\b|recipient_key"
    r"|envelope_inner|value_hash|prefix_hash|peer_id_hex|content_hash_format",
    re.IGNORECASE,
)
HASH_WIDTH_RE = re.compile(
    r"\b(?:33|49|66|98)[\s-]*(?:byte|bytes|B\b|char|chars|character|characters|hex)\b"
    r"|\bbytes\((?:33|49|0x21|0x31)\)"
    r"|\bhex33\b"
    r"|(?:!=|==|===)\s*(?:33|49|66|98)\b"
    # `Hash hex = 66` -- the exact phrasing of the NETWORK 6.5.3.1 defect, which
    # an earlier draft of this rule missed. Caught by standards_selftest.
    r"|\b(?:hex|len|length|width|size)\s*(?:!=|===|==|=|is)\s*(?:33|49|66|98)\b"
    r"|\blen(?:gth)?\s*(?:\(\))?\s*(?:!=|==)\s*(?:33|49|66|98)\b",
    re.IGNORECASE,
)
# Saying WHY the width is safe is what makes it safe.
HASH_WIDTH_EXEMPT_RE = re.compile(
    r"8\.4\.5|8\.4\.6"
    r"|length follows|follows the format byte|follows its own format byte"
    r"|follows that byte|length per (?:its|that|the) format byte"
    r"|implied by (?:its own |that |the )?(?:leading )?format byte"
    r"|never (?:be )?fixed|MUST NOT be fixed|not fixed|never assumed|never a fixed"
    r"|NOT fixed-width|not fixed-width"
    r"|pinned to the ECFv1-SHA-256 floor|SHA-256 floor|derive-to-meet"
    r"|re-lock|relock|removed|retired|lock-in|counter-example|is gone|are gone"
    # text that is arguing AGAINST a width is not asserting one
    r"|only today's|variable-length|variable length|is not a length|not a fixed-length"
    r"|length per format byte|per its format byte"
    # a width guarded by an explicit format conditional is a worked instance (8.4.5)
    # the format id is written both `ECFv1-SHA-256` and `ecfv1-sha256` in the corpus
    r"|(?:for|under|per) +`?(?:ECFv1-)?SHA-?\d+`?|under `?0x0\d`?"
    r"|= *ECFv1-SHA-?\d+|`?0x0\d`? *= *ECFv1",
    re.IGNORECASE,
)
HASH_WIDTH_EXEMPT_WINDOW = 4


# ---- proposal-citation resolution -------------------------------------------
# The rule above flags a proposal citation as *editorial* noise. It says nothing
# about whether the citation points at anything, and that gap is what shipped a
# false escalation: a landed spec cited `PROPOSAL-CONVERGENT-MIRRORING`, a search
# concluded "zero files, by filename and by content", and four conformance checks
# were proposed for retraction — while the document sat in the pre-split archive
# the search never opened. To the gate it looked exactly like the 103 citations
# that were fine.
#
# So resolution is mechanical now, and it is deliberately three-valued, matching
# the CLI's own contract (0 clean / 1 violations / 2 could-not-look):
#
#   archive configured and present, name resolves nowhere -> ERROR   (dangling)
#   no archive configured, name resolves nowhere          -> WARN    (unresolved)
#   archive configured and MISSING                        -> exit 2  (could-not-look)
#
# The middle case is the point. Reporting "dangling" when no archive was searched
# would reproduce the original defect inside the tool that exists to prevent it —
# absence of evidence rendered as evidence of absence. We only call it dangling
# when we actually looked everywhere we were told to look.
#
# Archive roots are machine-specific (the pre-split corpus is a sibling checkout,
# and per AGENTS-STANDARD local paths are not committed), so they are supplied by
# the operator, never baked in:
#
#   spec standards --proposal-archive PATH [--proposal-archive PATH ...]
#   SPEC_PROPOSAL_ARCHIVES=/path/one:/path/two spec standards
PROPOSAL_ARCHIVES_ENV = "SPEC_PROPOSAL_ARCHIVES"

# A citation names a document; a filename may carry a suffix the citation drops
# (`PROPOSAL-ROLE-V1` cites `PROPOSAL-ROLE-V1.2.md`; `-cgid-10-216` stamps are
# routinely omitted). Prefix matching is what makes resolution agree with how
# these names are actually written — 16 of the 104 citations in this corpus
# resolve only under it.
PROPOSAL_NAME_RE = re.compile(r"\bPROPOSAL-[A-Z0-9][A-Z0-9-]*[A-Z0-9]\b")

# Process vocabulary that is spelled like a document name but is not one. The
# ecosystem's own term for the lifecycle is "proposal-first" (AGENTS-STANDARD:
# *significant or normative changes are proposal-first, not a direct edit*), and
# the applications corpus tags items `[PROPOSAL-FIRST]` to mark that lifecycle.
# Resolving it would report the corpus's own vocabulary as a missing file — an
# error nobody can fix, which is how a gate teaches people to ignore it.
PROPOSAL_VOCAB_EXEMPT = {"PROPOSAL-FIRST"}

_ARCHIVE_INDEX: Optional[List[str]] = None
_ARCHIVE_ROOTS: List[Path] = []


# ---- the baseline ratchet ---------------------------------------------------
# Five rules above were `warn` until they were promoted to `error`. They were
# not promoted because anyone changed their mind about severity — they had been
# firing correctly the whole time. On the arch corpus they scored 573 findings
# across 26 of 40 specs, in a run that printed "✓ all gates passed", because a
# warn does not gate. That is this ecosystem's own D9 finding turned on its own
# toolchain: *a WARN in a green run is a claim nobody reads.*
#
# Promoting them alone would have turned the corpus red on contact and been
# switched off within a day, which is the failure mode the coherence gate's
# docstring already warns about. So severity comes with a ratchet:
#
#   known debt  → reported, does not gate      (it is in the baseline)
#   new debt    → ERROR, gates                 (it is not)
#
# The baseline describes a CORPUS, not the tool, so it lives with the corpus
# (`<corpus>/.spec-baseline.json`), not in this repo. `--init-baseline` writes
# one; `--update-baseline` may only ever LOWER a count. That asymmetry is the
# whole mechanism: a baseline that can be raised is not a ratchet, it is a
# rubber stamp, and the next contaminated commit re-baselines itself green.
#
# KEY SHAPE, and its blind spot, stated rather than discovered later. Entries
# are keyed `(file, rule) → count`. Line numbers were rejected as a key because
# every edit above a finding moves it, so a line-keyed baseline reports the
# whole file as new debt on an unrelated change and gets deleted. The cost of
# counting instead: **a swap is invisible.** Delete one `impl-team-ref` from a
# spec and add a different one in the same file, and the count is unchanged and
# the gate stays green. This rule catches ACCUMULATION, not substitution. A
# reviewer still has to read the diff; what the gate guarantees is that the
# total never silently grows.
BASELINE_FILENAME = ".spec-baseline.json"
BASELINE_RULES = frozenset({
    "impl-team-ref", "date-in-body", "proposal-citation",
    "amendment-provenance", "document-history-section",
})

# WHICH DOCUMENTS THESE RULES APPLY TO — the specs, not the workflow.
#
# `specs/` holds two kinds of document and they are not the same artifact. The
# normative specs are architecture's OUTPUT: implemented by people who have never
# heard of this cohort, so naming a repo or a date in one is a defect. Alongside
# them sit informative architecture docs and guides — the navigable map, the
# identity-stack overview, the domain charter — which describe how the work is
# organized. Naming the reference implementations in those is their JOB.
#
# The corpus already draws this line and `standards` was not reading it:
# `[classes]` in the config maps each doc to canonical-spec | guide | arch-doc |
# intent, and its own comment states the principle these rules need — *a
# normative spec citing an intent artifact is a leak; an arch/guide doc citing
# one is permitted provenance.* `address` has honoured that since it was written.
#
# So the narrative rules score `canonical-spec` only. Every doc is still scanned
# and every STRUCTURAL rule (header, title, depends) still applies everywhere —
# class drives disposition, not discovery. Measured on the arch corpus this moves
# 46 of 573 findings out of the debt: the overview legitimately listing the
# implementations stops being counted as contamination, and the remaining number
# is the one that means something.
NARRATIVE_SCORED_CLASSES = frozenset({"canonical-spec"})


def narrative_rules_apply(path_or_stem) -> bool:
    """True when the narrative rules score this document (normative specs only)."""
    stem = Path(path_or_stem).stem
    return _CFG.doc_class(stem) in NARRATIVE_SCORED_CLASSES


class Baseline:
    """Known, accepted debt for one corpus: {(file, rule): count} + categories."""

    def __init__(self, counts=None, categories=None, meta=None):
        self.counts: Dict[Tuple[str, str], int] = dict(counts or {})
        self.categories: Dict[str, str] = dict(categories or {})
        self.meta: Dict[str, object] = dict(meta or {})

    @classmethod
    def load(cls, path: Path) -> "Baseline":
        d = json.loads(path.read_text(encoding="utf-8"))
        counts = {(f, r): n
                  for f, rules in d.get("debt", {}).items()
                  for r, n in rules.items()}
        return cls(counts, d.get("categories", {}), d.get("meta", {}))

    def to_json(self) -> str:
        debt: Dict[str, Dict[str, int]] = {}
        for (f, r), n in sorted(self.counts.items()):
            if n:
                debt.setdefault(f, {})[r] = n
        doc = {
            "meta": dict(self.meta, total=sum(self.counts.values()),
                         files=len(debt), rules=sorted(BASELINE_RULES)),
            "categories": self.categories,
            "debt": debt,
        }
        return json.dumps(doc, indent=2, sort_keys=False) + "\n"

    def allowed(self, path: str, rule: str) -> int:
        return self.counts.get((path, rule), 0)


def observed_counts(report: Dict[str, List["Finding"]]) -> Dict[Tuple[str, str], int]:
    out: Dict[Tuple[str, str], int] = {}
    for rp, fs in report.items():
        for x in fs:
            if x.rule in BASELINE_RULES:
                out[(rp, x.rule)] = out.get((rp, x.rule), 0) + 1
    return out


def apply_baseline(report: Dict[str, List["Finding"]], base: "Baseline",
                   scanned: Optional[Set[str]] = None):
    """Split baseline-eligible findings into (new, known, retired).

    `new` are the ones that gate: findings beyond the accepted count for their
    (file, rule). Which INSTANCE is called new is arbitrary when a file has
    several — the count is what is authoritative, so the last N are reported and
    the message says so rather than implying the gate identified a culprit.
    """
    new: Dict[str, List[Finding]] = {}
    n_known = 0
    seen = observed_counts(report)
    for rp, fs in report.items():
        per: Dict[str, List[Finding]] = {}
        for x in fs:
            if x.rule in BASELINE_RULES:
                per.setdefault(x.rule, []).append(x)
        for rule, items in per.items():
            budget = base.allowed(rp, rule)
            n_known += min(len(items), budget)
            if len(items) > budget:
                new.setdefault(rp, []).extend(items[budget:])
    # A baseline entry that no longer fires: the debt was paid. Reported so the
    # baseline can be tightened, never auto-tightened — silently rewriting the
    # file the gate is measured against is how an oracle stops being one.
    #
    # Only files this run actually READ can have paid anything. A narrowed run
    # (`--root ONE-FILE`) leaves every other file unscanned at zero findings, and
    # counting those as retired reported "80 entries over-count — debt was paid"
    # for a corpus of which one file had been opened, while pointing the reader
    # at the command that would act on it.
    # `scanned` is every file READ, including those that came back clean — a file
    # whose debt fell to zero has no entry in `report`, so keying off findings
    # would under-report exactly the paydowns worth reporting. Passing None means
    # "assume everything was read", which is only correct for a direct caller that
    # says so; every CLI path supplies the real set.
    retired = {k: v for k, v in base.counts.items()
               if (scanned is None or k[0] in scanned) and seen.get(k, 0) < v}
    return new, n_known, retired


def ratchet_baseline(old: "Baseline", seen: Dict[Tuple[str, str], int],
                     scanned: Optional[Set[str]] = None) -> Tuple["Baseline", List[str]]:
    """Lower counts to what is observed. REFUSES to raise any count.

    `scanned` is the set of file paths this run actually opened. Entries for any
    other file are carried forward **untouched** — a file that was not read
    produced zero findings, and zero-because-unread is not zero. Without this,
    `--root ONE-FILE --update-baseline` lowers every other file to 0 and erases
    the ratchet's entire record; because the ratchet only ever lowers, no refusal
    fires and the run reports success.
    """
    refused: List[str] = []
    counts: Dict[Tuple[str, str], int] = {}
    for key, was in old.counts.items():
        if scanned is not None and key[0] not in scanned:
            counts[key] = was          # not read this run — carry forward
            continue
        now = seen.get(key, 0)
        counts[key] = min(was, now)
    for key, now in seen.items():
        if key not in old.counts and now:
            refused.append("%s  %s  (+%d, not in baseline)" % (key[0], key[1], now))
        elif now > old.counts.get(key, 0):
            refused.append("%s  %s  (%d → %d, would raise)"
                           % (key[0], key[1], old.counts[key], now))
    return Baseline(counts, old.categories, old.meta), refused


class CouldNotLook(Exception):
    """A configured archive root does not exist — the run must exit 2, not report."""


def set_proposal_archives(paths: List[Path]) -> None:
    """Install the archive roots for this run and reset the resolution index."""
    global _ARCHIVE_ROOTS, _ARCHIVE_INDEX
    _ARCHIVE_ROOTS = [Path(p) for p in paths]
    _ARCHIVE_INDEX = None


def _archive_roots_from_env() -> List[Path]:
    raw = os.environ.get(PROPOSAL_ARCHIVES_ENV, "").strip()
    if not raw:
        return []
    return [Path(p).expanduser() for p in raw.split(os.pathsep) if p.strip()]


def proposal_index() -> List[str]:
    """Every proposal-ish filename stem reachable from the corpus + archive roots.

    Raises CouldNotLook if a configured archive root is absent: a root we were
    told to search and could not is not the same as a name that is not there.
    """
    global _ARCHIVE_INDEX
    if _ARCHIVE_INDEX is not None:
        return _ARCHIVE_INDEX
    stems: List[str] = []
    roots = list(_ARCHIVE_ROOTS)
    for r in roots:
        if not r.exists():
            raise CouldNotLook("proposal archive root does not exist: %s" % r)
    # The corpus's own proposals always count, archive or no archive.
    corpus_proposals = _CFG.repo_root / "docs" / "proposals"
    if corpus_proposals.is_dir():
        roots.append(corpus_proposals)
    for r in roots:
        for p in r.rglob("PROPOSAL-*.md"):
            stems.append(p.stem)
    _ARCHIVE_INDEX = sorted(set(stems))
    return _ARCHIVE_INDEX


def resolves(name: str) -> bool:
    """True if `name` prefix-matches any known proposal filename stem."""
    return any(stem == name or stem.startswith(name) for stem in proposal_index())


def archives_configured() -> bool:
    return bool(_ARCHIVE_ROOTS)


class Finding:
    __slots__ = ("rule", "line", "text")

    def __init__(self, rule: str, line: int, text: str):
        self.rule = rule
        self.line = line
        self.text = text

    def severity(self) -> str:
        return RULES[self.rule][0]


def iter_specs(root: Path):
    if root.is_file():
        yield root
        return
    for p in sorted(root.rglob("*.md")):
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        if p.name in EXCLUDE_FILES:
            continue
        yield p


def find_header_field(lines: List[str], name: str) -> Optional[Tuple[int, str]]:
    """Find a `**Name**: value` line in the header region (before first `## `)."""
    pat = re.compile(r"^\*\*%s\*\*\s*:\s*(.*)$" % re.escape(name))
    for i, ln in enumerate(lines):
        if ln.startswith("## "):
            break
        m = pat.match(ln)
        if m:
            return i, m.group(1).strip()
    return None


def first_content_line(lines: List[str]) -> Optional[Tuple[int, str]]:
    for i, ln in enumerate(lines):
        if ln.strip():
            return i, ln
    return None


def doc_history_span(lines: List[str]) -> Optional[Tuple[int, int]]:
    """Return [start, end) line indices of a Document History section, or None."""
    start = None
    for i, ln in enumerate(lines):
        if re.match(r"^##\s+document\s+history\b", ln, re.IGNORECASE):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return start, end


def analyze(path: Path, text: str) -> List[Finding]:
    lines = text.splitlines()
    findings: List[Finding] = []

    # --- title ---
    fc = first_content_line(lines)
    if not fc or not fc[1].startswith("# "):
        findings.append(Finding("title-not-h1", (fc[0] + 1) if fc else 1,
                                fc[1].strip() if fc else "(empty file)"))

    # --- version ---
    ver = find_header_field(lines, "Version")
    if ver is None:
        findings.append(Finding("header-version-missing", 1, ""))
    else:
        idx, val = ver
        m = VERSION_TOKEN_RE.match(val)
        remainder = val[m.end():].strip() if m else val
        if not m or len(remainder) > 60:
            findings.append(Finding("header-version-blob", idx + 1, val[:90]))

    # --- status ---
    st = find_header_field(lines, "Status")
    if st is None:
        findings.append(Finding("header-status-missing", 1, ""))
    else:
        idx, val = st
        primary = re.split(r"[ \|/]", val.strip())[0]
        if primary and primary not in CANONICAL_STATUS:
            findings.append(Finding("header-status-unknown", idx + 1, val[:60]))

    # --- depends (extension specs only) ---
    if path.name.startswith("EXTENSION-"):
        if find_header_field(lines, "Depends") is None:
            findings.append(Finding("depends-missing", 1, ""))

    # --- document history ---
    span = doc_history_span(lines)
    if span:
        findings.append(Finding("document-history-section", span[0] + 1,
                                lines[span[0]].strip()))

    # --- body cruft (skip fenced code blocks) ---
    in_fence = False
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        ln1 = i + 1
        if DATE_RE.search(ln):
            findings.append(Finding("date-in-body", ln1, ln.strip()[:90]))
        if IMPL_TEAM_RE.search(ln):
            findings.append(Finding("impl-team-ref", ln1, ln.strip()[:90]))
        if PROPOSAL_RE.search(ln):
            findings.append(Finding("proposal-citation", ln1, ln.strip()[:90]))
            for name in dict.fromkeys(PROPOSAL_NAME_RE.findall(ln)):
                if name in PROPOSAL_VOCAB_EXEMPT or resolves(name):
                    continue
                rule = ("proposal-citation-dangling" if archives_configured()
                        else "proposal-citation-unresolved")
                findings.append(Finding(rule, ln1, name))
        if AMENDMENT_RE.search(ln):
            findings.append(Finding("amendment-provenance", ln1, ln.strip()[:90]))

    # --- hash width pins (SPECIFICATION-FORMAT.md 8.4.5) ---
    # Deliberately scans INSIDE fences: every instance found in the 2026-08-10
    # sweep that the SHA-384 run could not reach was in a CDDL block or
    # pseudocode, which is exactly where an implementer reads a width.
    for i, ln in enumerate(lines):
        if not (HASH_WIDTH_RE.search(ln) and HASH_CTX_RE.search(ln)):
            continue
        lo = max(0, i - HASH_WIDTH_EXEMPT_WINDOW)
        hi = min(len(lines), i + HASH_WIDTH_EXEMPT_WINDOW + 1)
        if any(HASH_WIDTH_EXEMPT_RE.search(lines[j]) for j in range(lo, hi)):
            continue
        findings.append(Finding("hash-width-pin", i + 1, ln.strip()[:90]))

    # The narrative rules score normative specs only. An architecture overview
    # naming the reference implementations, or a charter naming its workstream,
    # is doing its job — see NARRATIVE_SCORED_CLASSES. Structural rules above
    # are unaffected and still apply to every document.
    if not narrative_rules_apply(path):
        findings = [f for f in findings if f.rule not in BASELINE_RULES]

    return findings


# ---- refine -----------------------------------------------------------------
def refine_text(text: str) -> Tuple[str, List[str]]:
    """Apply safe mechanical fixes. Returns (new_text, list_of_fixes_applied)."""
    lines = text.splitlines()
    fixes: List[str] = []

    # F1: collapse the header changelog run — keep the first **Version**
    # (as a bare version), drop every later **Version**/**Prior** entry. These
    # are pure provenance and belong in the changelog, not the spec header.
    header_end = next((i for i, ln in enumerate(lines) if ln.startswith("## ")), len(lines))
    kept: List[str] = []
    seen_version = False
    dropped = 0
    for i in range(header_end):
        ln = lines[i]
        is_version = ln.startswith("**Version**")
        is_prior = ln.startswith("**Prior**")
        if is_version and not seen_version:
            seen_version = True
            m = VERSION_TOKEN_RE.match(ln.split(":", 1)[1] if ":" in ln else ln)
            kept.append("**Version**: %s" % m.group(1) if m else ln)
            continue
        if is_version or is_prior:
            dropped += 1
            continue
        kept.append(ln)
    # squeeze runs of blank lines left behind in the header
    squeezed: List[str] = []
    for ln in kept:
        if ln.strip() == "" and squeezed and squeezed[-1].strip() == "":
            continue
        squeezed.append(ln)
    if dropped:
        lines = squeezed + lines[header_end:]
        fixes.append("collapsed header changelog (dropped %d Version/Prior entries)" % dropped)

    # F2: drop a Document History section.
    span = doc_history_span(lines)
    if span:
        start, end = span
        # also drop a trailing `---` separator immediately above the section
        drop_from = start
        k = start - 1
        while k >= 0 and not lines[k].strip():
            k -= 1
        if k >= 0 and lines[k].strip() == "---":
            drop_from = k
        del lines[drop_from:end]
        fixes.append("removed Document History section (%d lines)" % (end - drop_from))

    new_text = "\n".join(lines)
    if text.endswith("\n"):
        new_text += "\n"
    return new_text, fixes


# ---- reporting --------------------------------------------------------------
def rel(path: Path) -> str:
    """Display path, anchored on the CORPUS root so it is copy-pasteable from
    inside the repo being linted. Falls back to the tool root, then absolute."""
    for anchor in (_CFG.repo_root, REPO_ROOT):
        try:
            return str(path.relative_to(anchor))
        except ValueError:
            continue
    return str(path)


def run_check(roots: List[Path], as_json: bool, max_examples: int,
              baseline_path: Optional[Path] = None,
              use_baseline: bool = True) -> int:
    report: Dict[str, List[Finding]] = {}
    scanned_paths: Set[str] = set()
    n_scanned = 0
    for root in roots:
        for spec in iter_specs(root):
            n_scanned += 1
            try:
                text = spec.read_text(encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                report[rel(spec)] = [Finding("title-not-h1", 1, "unreadable: %s" % exc)]
                continue
            try:
                f = analyze(spec, text)
            except CouldNotLook as exc:
                # A root we were told to search and could not. Reporting every
                # citation as dangling here would be the exact laundering this
                # rule exists to stop.
                print("could not look: %s" % exc, file=sys.stderr)
                print("  proposal citations were NOT resolved — this is neither a pass"
                      " nor a lint failure.", file=sys.stderr)
                return 2
            scanned_paths.add(rel(spec))
            if f:
                report[rel(spec)] = f

    # A gate that scanned nothing has not passed — it did not look. Printing
    # "0 file(s) flagged — 0 error(s)" and exiting 0 is what hid a corpus root
    # naming a directory present in no checkout: green, over an empty set,
    # indefinitely. Exit 2 (could-not-look) is deliberately distinct from 1
    # (violations found) so a caller can tell the two apart.
    if n_scanned == 0:
        print("no spec found under: %s" % ", ".join(str(r) for r in roots), file=sys.stderr)
        print("  scanned 0 files — this is not a pass, it is a gate that did not look.",
              file=sys.stderr)
        print("  point it at a corpus: --root PATH, `spec --corpus PATH standards`,"
              " $SPEC_CORPUS, or run from the corpus root.", file=sys.stderr)
        return 2

    # ---- ratchet ------------------------------------------------------------
    # Baseline-eligible findings that sit within the accepted count are demoted
    # to "known debt": counted and reported, not gating. Everything else keeps
    # the severity the rule table gives it.
    base = None
    baseline_new: Dict[str, List[Finding]] = {}
    n_known = 0
    retired: Dict[Tuple[str, str], int] = {}
    if use_baseline and baseline_path and baseline_path.exists():
        try:
            base = Baseline.load(baseline_path)
        except Exception as exc:  # noqa: BLE001
            # A malformed baseline must not be read as "no debt accepted" — that
            # silently turns a ratchet into a full red wall, and the reflex fix
            # is to delete the file. Refuse to guess.
            print("baseline unreadable: %s: %s" % (baseline_path, exc), file=sys.stderr)
            print("  this is neither a pass nor a lint failure — fix or pass --no-baseline.",
                  file=sys.stderr)
            return 2
        baseline_new, n_known, retired = apply_baseline(report, base, scanned_paths)

    # `Finding` defines no __eq__, so identity is the comparison — and identity
    # is what is wanted: apply_baseline hands back the very objects it selected,
    # not copies. Held as an id-set so this stays O(1) per finding.
    _new_ids = {id(x) for fs in baseline_new.values() for x in fs}

    def gates(rp: str, x: "Finding") -> bool:
        if base is not None and x.rule in BASELINE_RULES:
            return id(x) in _new_ids
        return x.severity() == "error"

    n_error = sum(1 for rp, fs in report.items() for x in fs if gates(rp, x))
    n_warn = sum(1 for fs in report.values() for x in fs if x.severity() == "warn")

    if as_json:
        out = {
            rp: [{"rule": x.rule, "severity": x.severity(), "line": x.line, "text": x.text,
                  "gates": gates(rp, x),
                  "known_debt": bool(base is not None and x.rule in BASELINE_RULES
                                     and not gates(rp, x))}
                 for x in fs]
            for rp, fs in report.items()
        }
        summary = {"errors": n_error, "warnings": n_warn, "files": len(report)}
        if base is not None:
            summary["known_debt"] = n_known
            summary["retired"] = {"%s::%s" % k: v for k, v in sorted(retired.items())}
        print(json.dumps({"summary": summary, "findings": out}, indent=2))
        return 1 if n_error else 0

    for rp in sorted(report):
        fs = report[rp]
        errs = [x for x in fs if gates(rp, x)]
        warns = [x for x in fs if x.severity() == "warn"]
        debt = [x for x in fs
                if base is not None and x.rule in BASELINE_RULES and not gates(rp, x)]
        if not (errs or warns or debt):
            continue
        # The known-debt column appears only when a baseline is in play. Adding
        # it unconditionally would rewrite every report line for corpora that
        # have no baseline at all — churn in the parity oracle for a number that
        # is always zero.
        if base is None:
            print("\n%s  (%d error, %d warn)" % (rp, len(errs), len(warns)))
        else:
            print("\n%s  (%d error, %d warn, %d known)"
                  % (rp, len(errs), len(warns), len(debt)))
        for x in errs:
            print("  ERROR  %-26s %s:%d  %s" % (x.rule, rp, x.line, x.text))
        # collapse repetitive warns (dates/impl-refs) to a count + a few examples
        by_rule: Dict[str, List[Finding]] = {}
        for x in warns:
            by_rule.setdefault(x.rule, []).append(x)
        for rule, items in sorted(by_rule.items()):
            print("  warn   %-26s x%d" % (rule, len(items)))
            show = items if max_examples == 0 else items[:max_examples]
            for x in show:
                print("           %s:%d  %s" % (rp, x.line, x.text))
            if max_examples and len(items) > max_examples:
                print("           ... +%d more" % (len(items) - max_examples))
        by_debt: Dict[str, int] = {}
        for x in debt:
            by_debt[x.rule] = by_debt.get(x.rule, 0) + 1
        for rule, n in sorted(by_debt.items()):
            cat = base.categories.get(rp, "") if base else ""
            print("  known  %-26s x%d%s" % (rule, n, ("  [%s]" % cat) if cat else ""))

    print("\n%d file(s) flagged — %d error(s), %d warning(s)." % (len(report), n_error, n_warn))
    if base is not None:
        print("%d known-debt finding(s) held by %s (not gating)."
              % (n_known, rel(baseline_path) if baseline_path else BASELINE_FILENAME))
        if retired:
            paid = sum(v - 0 for v in retired.values())
            print("%d baseline entr(ies) now over-count real findings — debt was paid."
                  % len(retired))
            print("  tighten with: spec standards --update-baseline   (it can only lower)")
        if n_error:
            print("the %d error(s) above are NEW — they are beyond the accepted baseline."
                  % n_error)
    print("errors gate; warnings are editorial candidates (run --refine for the safe subset).")
    return 1 if n_error else 0


def run_baseline(roots: List[Path], path: Path, update: bool) -> int:
    """Write (`--init-baseline`) or ratchet down (`--update-baseline`) the baseline.

    The asymmetry is the mechanism. `--init-baseline` accepts today's debt
    wholesale and is a one-time act; `--update-baseline` may only ever LOWER a
    count, and reports every entry it refused to raise. Without that refusal the
    next contaminated commit re-baselines itself green, which is the failure the
    ratchet exists to prevent — and it would look exactly like a clean run.
    """
    report: Dict[str, List[Finding]] = {}
    scanned_paths: Set[str] = set()
    n_scanned = 0
    for root in roots:
        for spec in iter_specs(root):
            n_scanned += 1
            scanned_paths.add(rel(spec))
            try:
                text = spec.read_text(encoding="utf-8")
            except Exception:  # noqa: BLE001
                continue
            try:
                f = analyze(spec, text)
            except CouldNotLook as exc:
                print("could not look: %s" % exc, file=sys.stderr)
                return 2
            if f:
                report[rel(spec)] = f
    if n_scanned == 0:
        print("scanned 0 files — refusing to write a baseline over an empty read.",
              file=sys.stderr)
        return 2

    seen = observed_counts(report)

    if update:
        if not path.exists():
            print("no baseline at %s — use --init-baseline first." % path, file=sys.stderr)
            return 2
        old = Baseline.load(path)
        new, refused = ratchet_baseline(old, seen, scanned_paths)
        # Atomic refusal. A run that lowered some entries while refusing others
        # would leave the baseline in a state matching neither the old nor the
        # new corpus, and — worse — it would have *written* during a failed run,
        # so a re-run reports different numbers than the first. Refuse whole.
        if refused:
            print("REFUSED to raise %d entr(ies) — these are new debt and must gate:"
                  % len(refused))
            for line in refused:
                print("  %s" % line)
            print("\nbaseline NOT written. Fix them, or accept them deliberately"
                  " with --init-baseline.")
            return 1
        lowered = sum(1 for k, v in old.counts.items() if new.counts.get(k, 0) < v)
        path.write_text(new.to_json(), encoding="utf-8")
        print("baseline ratcheted: %d entr(ies) lowered, total %d → %d"
              % (lowered, sum(old.counts.values()), sum(new.counts.values())))
        return 0

    base = Baseline(seen, {}, {"note": "accepted debt; --update-baseline may only lower"})
    path.write_text(base.to_json(), encoding="utf-8")
    print("baseline written: %s" % path)
    print("  %d finding(s) across %d file(s), rules: %s"
          % (sum(seen.values()),
             len({f for f, _ in seen}),
             ", ".join(sorted(BASELINE_RULES))))
    return 0


def run_refine(root: Path, output: Path) -> int:
    output.mkdir(parents=True, exist_ok=True)
    specs = list(iter_specs(root))
    if not specs:
        print("no specs found at %s" % root, file=sys.stderr)
        return 2
    base = root if root.is_dir() else root.parent
    for spec in specs:
        text = spec.read_text(encoding="utf-8")
        new_text, fixes = refine_text(text)
        try:
            dest = output / spec.relative_to(base)
        except ValueError:
            dest = output / spec.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(new_text, encoding="utf-8")
        remaining = [x for x in analyze(spec, new_text)]
        print("\n%s -> %s" % (rel(spec), rel(dest)))
        if fixes:
            for fx in fixes:
                print("  fixed: %s" % fx)
        else:
            print("  fixed: (nothing auto-fixable)")
        rem_warn = [x for x in remaining if x.severity() == "warn"]
        rem_err = [x for x in remaining if x.severity() == "error"]
        if rem_err:
            print("  STILL ERROR: %s" % ", ".join("%s@%d" % (x.rule, x.line) for x in rem_err))
        if rem_warn:
            by = {}
            for x in rem_warn:
                by[x.rule] = by.get(x.rule, 0) + 1
            print("  manual editorial remaining: %s"
                  % ", ".join("%s x%d" % (r, c) for r, c in sorted(by.items())))
    print("\nrefined %d spec(s) into %s (source untouched)." % (len(specs), rel(output)))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", action="append", type=Path,
                    help="spec dir or single .md file (repeatable; default: core-protocol-domain/specs)")
    ap.add_argument("--refine", action="store_true",
                    help="write cleaned copies (safe fixes only) instead of checking")
    ap.add_argument("--output", type=Path, help="output dir for --refine")
    ap.add_argument("--json", action="store_true", help="emit JSON (check mode)")
    ap.add_argument("--max-examples", type=int, default=8,
                    help="max example lines per repetitive warn rule (0 = all)")
    ap.add_argument("--proposal-archive", action="append", type=Path, metavar="PATH",
                    help="root to resolve proposal citations against (repeatable; "
                         "also $%s, %s-separated). Without one, an unresolvable "
                         "citation is a warn, not an error — we do not call a name "
                         "dangling when we did not search everywhere it might live."
                         % (PROPOSAL_ARCHIVES_ENV, os.pathsep))
    ap.add_argument("--baseline", type=Path, metavar="PATH",
                    help="accepted-debt file (default: <corpus>/%s). Findings within "
                         "the accepted count are reported as known debt and do not "
                         "gate; anything beyond it is an error." % BASELINE_FILENAME)
    ap.add_argument("--no-baseline", action="store_true",
                    help="ignore the baseline — report the full, un-ratcheted state")
    ap.add_argument("--init-baseline", action="store_true",
                    help="write a baseline from the CURRENT findings (one-time; "
                         "accepts today's debt wholesale)")
    ap.add_argument("--update-baseline", action="store_true",
                    help="ratchet the baseline DOWN to what is observed. Refuses to "
                         "raise any count — a baseline that can be raised is not a "
                         "ratchet")
    args = ap.parse_args(argv)

    set_proposal_archives(args.proposal_archive or _archive_roots_from_env())

    roots = args.root or [DEFAULT_ROOT]

    if args.refine:
        if not args.output:
            ap.error("--refine requires --output DIR")
        if len(roots) != 1:
            ap.error("--refine takes a single --root (dir or file)")
        return run_refine(roots[0], args.output)

    baseline_path = args.baseline or (_config.corpus_root() / BASELINE_FILENAME)

    if args.init_baseline or args.update_baseline:
        return run_baseline(roots, baseline_path, update=args.update_baseline)

    return run_check(roots, args.json, args.max_examples,
                     baseline_path=baseline_path, use_baseline=not args.no_baseline)


if __name__ == "__main__":
    raise SystemExit(main())
