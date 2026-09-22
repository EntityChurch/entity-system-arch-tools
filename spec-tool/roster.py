#!/usr/bin/env python3
"""roster — a roadmap's version column against the spec header it copies.

    spec roster [--root PATH] [--gate] [--owed] [--json]

Why it exists. `AGENTS.md` states the source of truth in one clause — **"the
spec header is source of truth"** — and the corpus then restates each spec's
version in a second place: the living roadmaps (`ROADMAP-EXTENSIONS.md`,
`ROADMAP-SDK.md`, `ROADMAP-APPLICATIONS.md`) carry a version column, and the
tier standards carry a members table with a version inside a status cell.
**Neither the roster nor the spec says the roster is a copy**, so a divergence
is invisible from both ends — the same structural defect `charter` exists for,
one tier down and against a different pair of documents.

**It is not hypothetical and the first run is not close: 13 of 33 roster rows
were stale.** `EXTENSION-REGISTRY` read 1.21 against a header at 1.26,
`EXTENSION-TREE` 4.3 against 4.8, `EXTENSION-HISTORY` 1.7 against 1.10. **These
are the documents a cohort seat opens to learn what state an extension is in**,
which is what makes a stale row expensive rather than untidy: it is read as a
build-state fact, and this corpus's most-repeated defect is a build-state claim
that outlived its measurement.

**Why there is no baseline, unlike the narrative gates.** A ratcheted baseline
exists where the debt is real authoring work and a first run of N reds would
teach people to skip the gate. Here the debt is *a number that is one edit from
correct* — there is nothing to burn down and no judgement to apply, so the
honest configuration is fix-them-all-and-gate-at-zero. A baseline would be a
place for correct numbers to go and hide.

The rules:

  roster-version-drift   A roster row's version differs from the spec header's.
                         The spec header wins, always and without argument: it
                         is the declared source of truth and the roster is the
                         copy. **The fix is never to edit the spec.**

  roster-unknown-spec    A roster row names a spec stem that resolves to no
                         file. This catches the rename case, which is the one
                         a pattern-matching gate is otherwise blind to — after
                         a rename the row simply stops matching anything and
                         every count stays green while the roster describes a
                         document that no longer exists. Same reasoning as
                         `ledger`'s directory-does-not-exist rule.

What it deliberately does NOT flag, and this is the calibration that decides
whether the gate is usable at all. **A `Depends:` pin is not a roster row.** A
spec header's `Depends: EXTENSION-TREE.md §3.2 (v4.0.2)` names the version its
author reasoned against, and that is a deliberate, dated statement which MUST
NOT track the dependency's HEAD — auto-advancing it would erase the only record
of what was actually checked. On the live corpus there are 97 occurrences of a
spec name near a version and only 33 are roster rows; a gate that read all 97
would file 60-odd accusations against correct text, and **a false accusation
against correct text is the expensive direction** (the `vocab` calibration,
same trade). So the match is anchored to a *table row* whose first cell is the
spec name and whose version sits in a version-or-status cell — never to prose,
never to a `Depends` line, never to a citation.

Nor does it check that the roster's *prose* about a spec is current. A row's
narrative column is commentary and goes stale in ways no gate can adjudicate;
the version is the one cell with a mechanical source of truth, and it is the
cell a reader trusts most.

Stdlib-only Python 3.11+. Exit **0** clean, **1** findings, **2** could-not-
look — a run that parsed no roster rows, or found no spec headers to compare
against, has not passed; it has failed to read, and the two are otherwise the
same zero-finding output.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import config as _config

_CFG = _config.load()
_A = _CFG.analyzer("roster")
_RULES: Dict[str, str] = _A.get("rules", {})
_ROSTERS: List[str] = _A.get("rosters", [
    "ROADMAP-EXTENSIONS.md", "ROADMAP-SDK.md", "ROADMAP-APPLICATIONS.md",
    "guides/GUIDE-APPLICATION-DEVELOPMENT.md",
])
_SPEC_DIRS: List[str] = _A.get("spec_dirs", ["specs"])

# A spec's own declared version: `**Version**: 4.8` / `**Version:** `4.8``.
# The header REGION only — the first `##` ends it — because a spec may carry
# sixty lines of version history further down and the newest number in the file
# is not necessarily the header's. Same invariant `declare` was calibrated on.
VERSION_RE = re.compile(r"^\*\*Version\*\*:?\s*`?([0-9][0-9.]*)", re.M)

# A roster row: `| `EXTENSION-TREE` | 4.3 | …` — the spec name in cell 1 and a
# bare version in cell 2. Anchored to the line start and to the cell boundary
# so a version mentioned inside a narrative cell is not read as the claim.
#
# `(?:\.md)?` sits INSIDE the optional backticks, not after them: the corpus
# spells it `` `EXTENSION-SIGNALING.md` ``, so a suffix group placed outside the
# closing backtick never matches. Caught by the self-test, on a spelling that is
# live in `ROADMAP-EXTENSIONS.md`.
ROW_VERSION_RE = re.compile(
    r"^\|\s*`?([A-Z][A-Z0-9-]{3,})(?:\.md)?`?\s*\|\s*v?([0-9][0-9.]*)\s*\|")

# The members-table shape: the version lives inside a status cell as
# `Draft v0.5 — …`. Keyed on the spec name in cell 1 and the FIRST `vN.N` that
# follows a maturity word, so a `v1` mentioned later in the same prose cell
# does not win over the declared one.
ROW_STATUS_RE = re.compile(
    r"^\|\s*`?([A-Z][A-Z0-9-]{3,})(?:\.md)?`?\s*\|.*?\|"
    r"[^|]*?\b(?:Draft|Stable|Final|Active|Candidate)\b\s*\*{0,2}v([0-9][0-9.]*)",
    re.I)


# The tier-classification shape: `| `EXTENSION-TREE` | Draft v4.9 | role… |` —
# the maturity word and the version share cell 2, where ROW_STATUS_RE expects
# them in cell 3. Kept as its own pattern rather than loosening ROW_STATUS_RE,
# because the loose form ("a maturity word in ANY later cell") would read the
# 59 narrative mentions of a spec-plus-version as roster rows. The maturity word
# must open the cell and the version must close it.
# Both orderings occur in one table: `Draft v4.9` and `v0.1 Exploratory`. The
# second was live (the Tier 4 row) and unread by the first cut, which would have
# been a silent hole rather than a wrong number — the worse direction.
ROW_TIER_RE = re.compile(
    r"^\|\s*`?([A-Z][A-Z0-9-]{3,})(?:\.md)?`?\s*\|\s*(?:"
    r"(?:Draft|Stable|Final|Active|Candidate|Exploratory)\s+v?([0-9][0-9.]*)"
    r"|v([0-9][0-9.]*)\s+(?:Draft|Stable|Final|Active|Candidate|Exploratory)"
    r")[^|]*\|", re.I)


class Finding:
    __slots__ = ("rule", "line", "text")

    def __init__(self, rule: str, line: int, text: str):
        self.rule = rule
        self.line = line
        self.text = text

    def severity(self) -> str:
        return _RULES.get(self.rule, "error")


def spec_versions(root: Path) -> Dict[str, Tuple[str, Path]]:
    """`{SPEC-STEM: (version, path)}` from every spec's header region."""
    out: Dict[str, Tuple[str, Path]] = {}
    for d in _SPEC_DIRS:
        base = root / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.md")):
            text = p.read_text(encoding="utf-8", errors="ignore")
            # Header region: everything before the first `##`. A version
            # restated in a document-history section is not the header's claim.
            head = text.split("\n## ", 1)[0]
            m = VERSION_RE.search(head)
            if m:
                out[p.stem] = (m.group(1), p)
    return out


def roster_rows(text: str) -> List[Tuple[int, str, str]]:
    """`[(line, spec-stem, declared-version)]` for one roster document.

    A line is matched by at most one shape. The bare-version column wins over
    the status-cell form when both could match, because a dedicated version
    cell is the more explicit claim.
    """
    rows: List[Tuple[int, str, str]] = []
    for i, line in enumerate(text.splitlines(), 1):
        m = ROW_VERSION_RE.match(line)
        if m is None:
            m = ROW_TIER_RE.match(line)
            if m is not None:
                # two alternatives, one version group each
                rows.append((i, m.group(1), m.group(2) or m.group(3)))
                continue
            m = ROW_STATUS_RE.match(line)
        if m:
            rows.append((i, m.group(1), m.group(2)))
    return rows


def analyze(root: Path, versions: Dict[str, Tuple[str, Path]]
            ) -> Tuple[List[Tuple[str, Finding]], int, int]:
    findings: List[Tuple[str, Finding]] = []
    n_rows = 0
    n_docs = 0
    for rel in _ROSTERS:
        p = root / rel
        if not p.is_file():
            continue
        n_docs += 1
        for line, name, declared in roster_rows(
                p.read_text(encoding="utf-8", errors="ignore")):
            n_rows += 1
            actual = versions.get(name)
            if actual is None:
                # Only accuse when the name LOOKS like a spec this corpus owns.
                # An arbitrary uppercase token in cell 1 is a table of something
                # else, and an inferred attribution that misses is a defect in
                # the inference, not a finding about the corpus.
                if not any(name.startswith(pfx) for pfx in
                           ("EXTENSION-", "SDK-", "APP-CONVENTION-", "ENTITY-")):
                    n_rows -= 1
                    continue
                findings.append((rel, Finding(
                    "roster-unknown-spec", line,
                    "row names `%s` (v%s); no spec of that stem exists — renamed or retired?"
                    % (name, declared))))
            elif actual[0] != declared:
                findings.append((rel, Finding(
                    "roster-version-drift", line,
                    "`%s` roster says v%s; the spec header says v%s — the header is source "
                    "of truth, so fix the roster" % (name, declared, actual[0]))))
    return findings, n_rows, n_docs


def run_check(root: Path, gate: bool, owed: bool, as_json: bool) -> int:
    versions = spec_versions(root)
    if not versions:
        print("could-not-look: parsed 0 spec headers under %s"
              % ", ".join(_SPEC_DIRS), file=sys.stderr)
        return 2

    findings, n_rows, n_docs = analyze(root, versions)

    if n_docs == 0:
        print("could-not-look: none of the %d configured roster document(s) exist"
              % len(_ROSTERS), file=sys.stderr)
        return 2
    if n_rows == 0:
        # A reformatted table and a table with no drift produce the same
        # zero-finding output otherwise. This is the whole family of defect
        # this toolkit is built against.
        print("could-not-look: parsed 0 roster rows from %d document(s)" % n_docs,
              file=sys.stderr)
        return 2

    n_err = sum(1 for _, f in findings if f.severity() == "error")

    if owed:
        for doc, f in findings:
            print("%s:%d  %s" % (doc, f.line, f.text))
        return 0

    if as_json:
        report: Dict[str, list] = {}
        for doc, f in findings:
            report.setdefault(doc, []).append(
                {"rule": f.rule, "severity": f.severity(),
                 "line": f.line, "text": f.text})
        print(json.dumps({"summary": {"errors": n_err, "rows": n_rows,
                                      "documents": n_docs,
                                      "specs": len(versions)},
                          "findings": report}, indent=2))
        return (1 if n_err else 0) if gate else 0

    by_doc: Dict[str, List[Finding]] = {}
    for doc, f in findings:
        by_doc.setdefault(doc, []).append(f)
    for doc in sorted(by_doc):
        print("\n%s  (%d finding)" % (doc, len(by_doc[doc])))
        for f in by_doc[doc]:
            print("  %-6s %-22s %s:%d  %s"
                  % (f.severity().upper(), f.rule, doc, f.line, f.text))

    print("\nscanned %d roster document(s), %d row(s) against %d spec header(s) "
          "— %d finding(s)." % (n_docs, n_rows, len(versions), n_err))
    print("the spec header is source of truth; a roster row is a copy. Fix the copy.")
    if not gate:
        print("reader mode — exits 0. Run with --gate to enforce.")
    return (1 if n_err else 0) if gate else 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, help="corpus root (default: configured)")
    ap.add_argument("--gate", action="store_true",
                    help="exit 1 on findings (0 clean, 1 findings, 2 could-not-look)")
    ap.add_argument("--owed", action="store_true", help="the worklist, one per line")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)
    return run_check(args.root or _CFG.corpus_dir, args.gate, args.owed, args.json)


if __name__ == "__main__":
    raise SystemExit(main())
