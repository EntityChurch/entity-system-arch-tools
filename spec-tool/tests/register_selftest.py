#!/usr/bin/env python3
"""register self-test — builds a synthetic corpus and asserts the contract.

Fixtures rather than corpus counts, like `standards_selftest`, so corpus
corrections never make this stale.

**The invariant that earns most of this file is stem matching.** The register
cites a document's distinctive tail (`THE-REDUCTION §4.4`), never its full
filename, so a gate that matches whole names reports every document as owed —
a wall of red that is really one wrong comparison. The first hand-run of that
comparison returned "0 of 97 cited" where the truth was 2. A count of one
spelling is not a census of the thing, and this gate would have shipped that
number as its headline.

Every assertion runs in BOTH directions: a document that should be owed is
owed, AND a document that should be discharged is discharged. A negative
control proves the gate can fire; only the positive one shows the pass
condition is right.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import register  # noqa: E402

FAILURES = []


def ok(name, cond, extra=""):
    if cond:
        print("  ok   %s" % name)
    else:
        FAILURES.append(name)
        print("  FAIL %s %s" % (name, extra))


def build(tmp: Path, register_text: str, docs: dict) -> Path:
    root = tmp / "corpus"
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "DESIGN-REGISTER.md").write_text(register_text,
                                                      encoding="utf-8")
    for rel, body in docs.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return root


with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)

    print("stem matching — the comparison that decides everything")
    root = build(
        tmp,
        "# REGISTER\n\n| F-1 | q | a | exploration `THE-REDUCTION` §4.4 | OK |\n",
        {
            # cited by its TAIL, which is how the register actually writes it
            "docs/research/explorations/"
            "EXPLORATION-THE-REDUCTION-MONOTONICITY-IS-THE-PATTERN.md": "# x\n",
            # not cited anywhere
            "docs/proposals/active/PROPOSAL-SOMETHING-UNMENTIONED-ENTIRELY.md": "# y\n",
        })
    code, res = register.scan(root)
    ok("a document cited by its stem counts as cited",
       res["cited"] == 1, "res=%r" % res)
    ok("an uncited document is owed",
       len(res["owed"]) == 1
       and res["owed"][0]["file"].endswith("UNMENTIONED-ENTIRELY.md"),
       "owed=%r" % res["owed"])
    ok("owed findings make it VIOLATIONS", code == register.VIOLATIONS)

    print("\na dropped leading article is truncation too")
    root = build(
        tmp / "a2",
        "# REGISTER\n\n| F-1 | q | a | exploration `P2P-COVERAGE-AUDIT` §2 "
        "| MEASURED |\n",
        {
            # the house style: file says THE-, the register row does not
            "docs/research/explorations/"
            "EXPLORATION-THE-P2P-COVERAGE-AUDIT-AND-THE-AXES.md": "# x\n",
            # negative control: the article is not a licence to match anything
            "docs/research/explorations/"
            "EXPLORATION-THE-UNRELATED-SUBJECT-ENTIRELY.md": "# y\n",
        })
    code, res = register.scan(root)
    ok("a row citing the article-stripped stem discharges the document",
       res["cited"] == 1, "res=%r" % res)
    ok("and stripping it does not credit an unrelated document",
       len(res["owed"]) == 1
       and res["owed"][0]["file"].endswith("UNRELATED-SUBJECT-ENTIRELY.md"),
       "owed=%r" % res["owed"])
    ok("the prefix discipline survives: a mid-name substring still misses",
       not register.is_cited("SOMETHING-P2P-COVERAGE-AUDIT-INSIDE",
                             "cites `P2P-COVERAGE-AUDIT`",
                             ["P2P-COVERAGE-AUDIT"]))

    print("\na date prefix and an absorption class prefix are noise too")
    root = build(
        tmp / "a3",
        "# REGISTER\n\ncites `THE-KEYSTONE-AUDIT` and `compute-axis1-results`\n",
        {
            # date between the class prefix and the subject
            "docs/research/reviews/"
            "REVIEW-2026-09-01-THE-KEYSTONE-AUDIT-AND-WHAT-IT-INHERITS.md":
                "# x\n",
            # ABSORPTION is a class prefix in this corpus like any other
            "docs/research/reviews/ABSORPTION-compute-axis1-results.md": "# y\n",
            "docs/research/reviews/REVIEW-2026-09-01-SOMETHING-ELSE.md": "# z\n",
        })
    code, res = register.scan(root)
    ok("a dated review is discharged by a row citing its subject",
       res["cited"] == 2, "res=%r" % res)
    ok("and the date alone does not credit a different document",
       len(res["owed"]) == 1
       and res["owed"][0]["file"].endswith("SOMETHING-ELSE.md"),
       "owed=%r" % res["owed"])
    ok("every spelling stays a PREFIX of the real stem",
       all(register.stem_of("REVIEW-2026-09-01-THE-KEYSTONE-AUDIT.md")
           .endswith(s) for s in
           register.spellings_of(
               register.stem_of("REVIEW-2026-09-01-THE-KEYSTONE-AUDIT.md"))))

    print("\nthe explicit marker — a blank is not a declaration")
    root = build(
        tmp / "b", "# REGISTER\n\nnothing here\n",
        {"docs/proposals/active/PROPOSAL-NO-CONCLUSION-TO-RECORD.md":
             "# t\n\nDesign-Conclusions: none\n",
         "docs/proposals/active/PROPOSAL-STILL-OWED.md": "# t\n"})
    code, res = register.scan(root)
    ok("`Design-Conclusions: none` discharges a document",
       res["declared_none"] == 1, "res=%r" % res)
    ok("a document without it is still owed",
       len(res["owed"]) == 1
       and res["owed"][0]["file"].endswith("STILL-OWED.md"),
       "owed=%r" % res["owed"])

    print("\nthe positive control — a fully discharged corpus goes GREEN")
    root = build(
        tmp / "c",
        "# REGISTER\n\ncites `A-CLEAN-CONCLUSION`\n",
        {"docs/proposals/active/PROPOSAL-A-CLEAN-CONCLUSION.md": "# t\n",
         "docs/research/explorations/EXPLORATION-NOTHING-SETTLED-HERE.md":
             "# t\n\nDesign-Conclusions: none\n"})
    code, res = register.scan(root)
    ok("no owed documents is CLEAN, not merely quiet",
       code == register.CLEAN and not res["owed"], "res=%r" % res)
    ok("and both discharge paths are counted separately",
       res["cited"] == 1 and res["declared_none"] == 1, "res=%r" % res)

    print("\nscope — dev history and the indexes themselves are not design docs")
    root = build(
        tmp / "d", "# REGISTER\n\nnothing\n",
        {"docs/proposals/INDEX.md": "# i\n",
         "docs/research/README.md": "# r\n",
         "docs/research/archive/EXPLORATION-OLD-AND-ARCHIVED.md": "# o\n",
         "docs/proposals/active/PROPOSAL-REAL-ONE.md": "# p\n"})
    code, res = register.scan(root)
    ok("INDEX, README and archived docs are out of scope",
       res["scanned"] == 1 and len(res["owed"]) == 1,
       "scanned=%r owed=%r" % (res["scanned"], res["owed"]))

    print("\nthree-valued contract — scanning nothing is never passing")
    bare = tmp / "e" / "corpus"
    (bare / "docs" / "proposals").mkdir(parents=True)
    (bare / "docs" / "DESIGN-REGISTER.md").write_text("# R\n", encoding="utf-8")
    code, res = register.scan(bare)
    ok("a scope matching no document is 2, not a clean corpus",
       code == register.CANNOT_LOOK and "error" in res, "got %d" % code)
    noreg = tmp / "f" / "corpus"
    (noreg / "docs" / "proposals" / "active").mkdir(parents=True)
    (noreg / "docs" / "proposals" / "active" / "PROPOSAL-X.md").write_text(
        "# x\n", encoding="utf-8")
    code, res = register.scan(noreg)
    ok("a missing register is 2 — there is nothing to resolve against",
       code == register.CANNOT_LOOK and "error" in res, "got %d" % code)

    print("\na too-short stem must not match noise")
    ok("MIN_STEM keeps a tiny tail from reporting a false clean",
       register.MIN_STEM >= 8)

print()
if FAILURES:
    print("FAILED: %d" % len(FAILURES))
    raise SystemExit(1)
print("register self-test: all invariants hold")
