#!/usr/bin/env python3
"""disclose self-test — §5.3a's cell disclosure, both directions.

Fixtures rather than corpus counts, so a fold never makes this stale.

**Validated against the incident that motivated the rule, in BOTH directions.**
Four revisions landed before §5.3a with no disclosure, under a condition that
forbade them and that nobody could meet. This gate must score those four CLEAN
— they are out of scope by the rule, not by a baseline — and must score the
same document a finding the moment its revision crosses the binding line. A gate
that reddens on the backlog is one people switch off, and a gate that cannot
fire on the incident is one that measures nothing.

**The two silent directions this file exists for.** ① scope taken from the BODY
rather than the header region would put every proposal that mentions a revision
into scope, and a proposal citing what it corrects is most of them. ② the
template in `GUIDE-CONFORMANCE` §5.3a.1 carries `<commit>` and `<date>`
placeholders — a proposal that pastes it and fills in nothing looks disclosed
and cites no run, which is the exact failure the `Read from:` requirement is
for.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import disclose  # noqa: E402

FAILURES = []


def ok(name, cond, extra=""):
    if cond:
        print("  ok   %s" % name)
    else:
        FAILURES.append(name)
        print("  FAIL %s %s" % (name, extra))


DISCLOSURE = """## Cell disclosure

**Read from:** `entity-core-keystone` `2b3703ed` `2026-09-17` — scope-cell table summary

| cell | state | note |
|---|---|---|
| `D3/C2` | `driven` | |
| `D3/C7` | **driven** | |
| `D5/C1` | `no vector` | requirement on the check set |
| `D5/C4` | `named-vector-not-driven` | |
"""


def doc(rev="0.8.2.40", disclosure=DISCLOSURE, lead="", status=None):
    return """# A proposal that folds something

{lead}**Status:** {status}
**Author:** architecture team

---

## 1. The delta

Words that also mention `0.8.2.17`, which this corrects.

{disclosure}
## 2. Open items

None.
""".format(disclosure=disclosure, lead=lead,
           status=status if status is not None
           else "**RATIFIED and FOLDED — `ENTITY-CORE-PROTOCOL` v`%s`.**" % rev)


def draft(rev="0.8.2.40", **kw):
    return doc(rev=rev,
               status="DRAFT -> folds as `ENTITY-CORE-PROTOCOL` **%s**" % rev,
               **kw)


def run(docs, roots=("corpus",), **kw):
    with tempfile.TemporaryDirectory() as td:
        paths = []
        for r in roots:
            d = Path(td) / r / "docs" / "proposals"
            d.mkdir(parents=True, exist_ok=True)
            paths.append(Path(td) / r)
        for name, (where, body) in docs.items():
            (Path(td) / where / "docs" / "proposals" / name).write_text(
                body, encoding="utf-8")
        return disclose.scan(paths, **kw)


def result(res, fname):
    return next(r for r in res["results"] if r["file"].endswith(fname))


def codes(rec):
    return [c for c, _ in rec["findings"]]


def main() -> int:
    print("disclose self-test")

    # --- the happy path ----------------------------------------------------
    code, res = run({"P-A.md": ("corpus", doc())})
    r = result(res, "P-A.md")
    ok("a complete disclosure is clean", not r["findings"], r["findings"])
    ok("...and exits 0", code == disclose.CLEAN, code)
    ok("four cells counted", r["cells"] == 4, r["cells"])
    ok("states are tallied by the closed vocabulary",
       res["by_state"] == {"driven": 2, "named-vector-not-driven": 1,
                           "no vector": 1}, res["by_state"])
    ok("markup around a state does not hide it",
       r["by_state"]["driven"] == 2, r["by_state"])

    # --- the gate fires ----------------------------------------------------
    code, res = run({"P-A.md": ("corpus", doc(disclosure=""))})
    r = result(res, "P-A.md")
    ok("a fold with no disclosure is a finding",
       codes(r) == ["disclosure-missing"], r["findings"])
    ok("...and the gate exits 1", code == disclose.VIOLATIONS, code)

    # --- the template pasted and not filled in ------------------------------
    template = """## Cell disclosure

**Read from:** `<repo>` `<commit>` `<date>` — scope-cell table summary

| cell | state | note |
|---|---|---|
| `D3/C2` | `driven` | |
"""
    _c, res = run({"P-A.md": ("corpus", doc(disclosure=template))})
    r = result(res, "P-A.md")
    ok("an unfilled `Read from:` template is unsourced",
       codes(r) == ["disclosure-unsourced"], r["findings"])
    ok("...and its rows still count", r["cells"] == 1, r["cells"])

    # a `Read from:` naming a commit but no date is not a run either
    partial = DISCLOSURE.replace(" `2026-09-17`", "")
    _c, res = run({"P-A.md": ("corpus", doc(disclosure=partial))})
    ok("a `Read from:` with no date is unsourced",
       "disclosure-unsourced" in codes(result(res, "P-A.md")))

    # --- an empty section ---------------------------------------------------
    empty = """## Cell disclosure

We will fill this in later.
"""
    _c, res = run({"P-A.md": ("corpus", doc(disclosure=empty))})
    ok("a section with no rows is empty AND unsourced",
       sorted(codes(result(res, "P-A.md")))
       == ["disclosure-empty", "disclosure-unsourced"],
       result(res, "P-A.md")["findings"])

    # --- the closed vocabulary ---------------------------------------------
    loose = DISCLOSURE.replace("| `D5/C1` | `no vector` |",
                               "| `D5/C1` | `partially covered` |")
    _c, res = run({"P-A.md": ("corpus", doc(disclosure=loose))})
    r = result(res, "P-A.md")
    ok("a state outside the vocabulary is a finding",
       codes(r) == ["disclosure-state-unknown"], r["findings"])
    ok("...and it names the cell and the state",
       "D5/C1" in r["findings"][0][1] and "partially covered" in r["findings"][0][1],
       r["findings"])

    # --- THE FOUNDING INCIDENT, BOTH DIRECTIONS -----------------------------
    landed = {"P-%d.md" % n: ("corpus", doc(rev="0.8.2.%d" % n, disclosure=""))
              for n in (23, 24, 25, 26)}
    code, res = run(landed)
    ok("the four revisions that landed before the rule are OUT OF SCOPE",
       res["in_scope"] == 0 and code == disclose.CLEAN,
       (res["in_scope"], code))
    ok("...and they are still SEEN, not silently unmatched",
       res["name_a_revision"] == 4, res["name_a_revision"])

    code, res = run({"P-33.md": ("corpus", doc(rev="0.8.2.33", disclosure=""))})
    ok("the same document one revision past the line IS a finding",
       code == disclose.VIOLATIONS
       and codes(result(res, "P-33.md")) == ["disclosure-missing"], res)

    code, res = run({"P-32.md": ("corpus", doc(rev="0.8.2.32", disclosure=""))})
    ok("the binding revision itself is the last one outside the rule",
       code == disclose.CLEAN and res["in_scope"] == 0, res)

    # the line is a flag, not a constant welded into the tool
    code, res = run({"P-24.md": ("corpus", doc(rev="0.8.2.24", disclosure=""))},
                    binds_from="0.8.2.23")
    ok("--binds-from moves the line", code == disclose.VIOLATIONS, code)

    # --- scope rule 2: a PENDING fold lands past the line, whatever number
    #     its header currently writes. This is the silent half.
    code, res = run({"P-E.md": ("corpus", draft(rev="0.8.2.22",
                                                disclosure=""))})
    r = result(res, "P-E.md")
    ok("a DRAFT naming a revision BELOW the line is still in scope",
       r["in_scope"] and not r["landed"] and code == disclose.VIOLATIONS, r)
    ok("...and the finding says WHY it is in scope",
       "pending" in r["findings"][0][1], r["findings"])

    # a proposal whose header names only the revision it CORRECTS — two live
    # core proposals are exactly this shape
    corrects_only = """# PROPOSAL — the floor did not follow

**Proposes:** two corrections to §9.1.

**Status:** **DRAFT 2026-09-16 · revision 1.**
**Answers:** a finding against `0.8.2.22`.

---

## 1. The delta

Words.
"""
    code, res = run({"P-F.md": ("corpus", corrects_only)})
    ok("a pending proposal naming only what it CORRECTS is in scope",
       res["in_scope"] == 1 and code == disclose.VIOLATIONS, res)

    # ...and a HELD proposal has not landed either
    code, res = run({"P-G.md": ("corpus", doc(
        rev="0.8.2.22", disclosure="",
        status="**HELD — the design question is RULED, the change is "
               "DEFERRED.** Target: `0.8.2.22`."))})
    ok("RULED and DEFERRED is not landed",
       res["name_a_revision"] == 1 and res["in_scope"] == 1, res)

    # RATIFIED alone is not FOLDED — this corpus separates them on purpose
    code, res = run({"P-H.md": ("corpus", doc(
        rev="0.8.2.10", disclosure="",
        status="**RATIFIED 2026-09-01** as `0.8.2.10`. The fold is owed."))})
    ok("RATIFIED without FOLDED is still pending",
       res["name_a_revision"] == 1 and res["in_scope"] == 1, res)

    # the `implemented/` directory corroborates a landed fold
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "docs" / "proposals" / "implemented" / "core"
        d.mkdir(parents=True)
        (d / "P.md").write_text(
            doc(rev="0.8.2.10", disclosure="",
                status="DRAFT (2026-07-21) — target `0.8.2.10`"),
            encoding="utf-8")
        code, res = disclose.scan([Path(td)])
    ok("a proposal under implemented/ counts as landed",
       res["name_a_revision"] == 1 and res["in_scope"] == 0
       and code == disclose.CLEAN, res)

    # --- scope comes from the HEADER REGION, never the body -----------------
    body_only = """# A proposal about something else

**Status:** DRAFT -> folds as `GUIDE-CONFORMANCE` §5.3a

---

## 1. Why

This corrects a reading of `0.8.2.40` and cites `0.8.2.41` twice.
"""
    _c, res = run({"P-B.md": ("corpus", body_only)})
    ok("a revision named only in the BODY does not put a proposal in scope",
       res["name_a_revision"] == 0, res["name_a_revision"])

    # ...and the region is a region, not a line window: two live core proposals
    # carry `Status:` at line 7 under a revision block.
    lead = "\n".join("**Revision %d:** a paragraph of history." % i
                     for i in range(1, 12)) + "\n\n"
    _c, res = run({"P-C.md": ("corpus", doc(disclosure="", lead=lead))})
    ok("eleven lines of history above the Status line do not hide it",
       res["in_scope"] == 1, res)

    # --- table parsing ------------------------------------------------------
    noisy = """## Cell disclosure

**Read from:** `entity-core-keystone` `2b3703ed` `2026-09-17` — summary

| cell | state |
|:---|---:|
| `D3/C2` | `driven` |

| a one-column pipe line is prose |
"""
    _c, res = run({"P-A.md": ("corpus", doc(disclosure=noisy))})
    r = result(res, "P-A.md")
    ok("the header row, the separator and a one-column line are not cells",
       r["cells"] == 1 and not r["findings"], (r["cells"], r["findings"]))

    # a numbered heading is the same heading
    numbered = DISCLOSURE.replace("## Cell disclosure", "### 4. Cell Disclosure")
    _c, res = run({"P-A.md": ("corpus", doc(disclosure=numbered))})
    ok("a numbered, differently-cased heading is found",
       not result(res, "P-A.md")["findings"],
       result(res, "P-A.md")["findings"])

    # a `####` sub-heading inside the disclosure does not end it
    nested = DISCLOSURE.replace("| cell | state | note |",
                                "#### The cells\n\n| cell | state | note |")
    _c, res = run({"P-A.md": ("corpus", doc(disclosure=nested))})
    ok("a sub-heading inside the disclosure does not truncate it",
       result(res, "P-A.md")["cells"] == 4,
       result(res, "P-A.md")["cells"])

    # --- two roots ----------------------------------------------------------
    code, res = run({"P-A.md": ("corpus", doc()),
                     "P-D.md": ("peer", doc(rev="0.8.2.41", disclosure=""))},
                    roots=("corpus", "peer"))
    ok("a second root is scanned, not ignored",
       code == disclose.VIOLATIONS and res["scanned"] == 2, res)
    ok("...and both roots are reported", len(res["roots"]) == 2, res["roots"])

    # --- could-not-look is not a pass --------------------------------------
    with tempfile.TemporaryDirectory() as td:
        code, res = disclose.scan([Path(td)])
    ok("an empty root is could-not-look, not clean",
       code == disclose.CANNOT_LOOK, code)

    with tempfile.TemporaryDirectory() as td:
        code, res = disclose.scan([Path(td) / "nope"])
    ok("a root that does not exist is could-not-look, never a silent skip",
       code == disclose.CANNOT_LOOK and "do not exist" in res["error"], res)

    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "docs" / "proposals"
        d.mkdir(parents=True)
        (d / "P.md").write_text(doc(), encoding="utf-8")
        code, _res = disclose.scan([Path(td)], binds_from="0.8.2")
    ok("a malformed --binds-from is could-not-look, not a crash",
       code == disclose.CANNOT_LOOK, code)

    print("\ndisclose self-test: %s"
          % ("all assertions passed" if not FAILURES
             else "%d FAILURE(S): %s" % (len(FAILURES), ", ".join(FAILURES))))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
