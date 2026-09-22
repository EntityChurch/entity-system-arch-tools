#!/usr/bin/env python3
"""inventory self-test — builds a synthetic corpus and asserts the contract.

Fixtures rather than corpus counts, like `register_selftest`, so a corpus
conversion never makes this stale.

**Every assertion runs in BOTH directions.** A shape that should be flagged is
flagged, AND a shape that should pass passes. A negative control only proves
the gate can fire; the positive one is what shows the pass condition is right.
That discipline is not decorative here — four analyzers in this toolkit have
now shipped a first measurement that was wrong because it was calibrated
against the spelling the rule-writer expected rather than the corpus's actual
vocabulary, and each of those looked green.

**The section-selection invariant earns its own case.** The conformance section
is the LAST `##`-level heading matching the word, not the first: at least one
spec's §1.3 is a definitions section containing it, and a census that matched
the first heading reported ten specs unshaped where the true number is four.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import inventory  # noqa: E402

FAILURES = []


def ok(name, cond, extra=""):
    if cond:
        print("  ok   %s" % name)
    else:
        FAILURES.append(name)
        print("  FAIL %s %s" % (name, extra))


def build(tmp: Path, specs: dict) -> Path:
    root = tmp / "corpus"
    d = root / "specs" / "extensions"
    d.mkdir(parents=True, exist_ok=True)
    for name, body in specs.items():
        (d / name).write_text(body, encoding="utf-8")
    return root


GOOD = """# X

## 3. Storage

## 9. Conformance

**Requirement id prefix:** `XX`

### 9.1 Requirements

| id | Requirement | Level | § |
|---|---|---|---|
| `XX-R1` | Store the thing | MUST | §3 |
| `XX-R2` | Never store the other thing | MUST NOT | §3 |
| `XX-R3` | The vocabulary of levels is not constrained | IMPL-DEFINED | §3 |
"""


def run(specs):
    with tempfile.TemporaryDirectory() as td:
        root = build(Path(td), specs)
        return inventory.scan(root)


def rules(res, fname):
    for r in res["results"]:
        if r["file"].endswith(fname):
            return {f["rule"] for f in r["findings"]}, {n["rule"] for n in r["notes"]}
    return set(), set()


def main() -> int:
    print("inventory self-test")

    # --- the pass condition, first: a conformant inventory is clean ---------
    code, res = run({"EXTENSION-A.md": GOOD})
    f, _n = rules(res, "EXTENSION-A.md")
    ok("a conformant inventory raises no findings", not f, f)
    ok("a conformant inventory is counted conformant", res["conformant"] == 1,
       res["conformant"])
    ok("a clean corpus exits 0", code == inventory.CLEAN, code)

    # --- the closed level vocabulary ---------------------------------------
    bad = GOOD.replace("| `XX-R2` | Never store the other thing | MUST NOT |",
                       "| `XX-R2` | Never store the other thing | Compatibility |")
    _c, res = run({"EXTENSION-A.md": bad})
    f, _n = rules(res, "EXTENSION-A.md")
    ok("a Level outside the vocabulary fires", "bad-level" in f, f)
    ok("...and the spec is no longer conformant", res["conformant"] == 0)

    # MUST NOT is a LEVEL, not a fourth heading. This is the case the format
    # standard changed for: a prohibition filed under a heading named
    # "Implementation-Defined" reads to an implementer as unconstrained.
    _c, res = run({"EXTENSION-A.md": GOOD})
    f, _n = rules(res, "EXTENSION-A.md")
    ok("`MUST NOT` is accepted as a level", "bad-level" not in f, f)

    # --- ids ---------------------------------------------------------------
    dup = GOOD + "| `XX-R1` | Store the thing again | MUST | §3 |\n"
    _c, res = run({"EXTENSION-A.md": dup})
    f, _n = rules(res, "EXTENSION-A.md")
    ok("a duplicate id fires", "duplicate-id" in f, f)

    mismatch = GOOD.replace("| `XX-R3` |", "| `YY-R3` |")
    _c, res = run({"EXTENSION-A.md": mismatch})
    f, _n = rules(res, "EXTENSION-A.md")
    ok("a row under an undeclared prefix fires", "prefix-mismatch" in f, f)

    noprefix = GOOD.replace("**Requirement id prefix:** `XX`\n\n", "")
    _c, res = run({"EXTENSION-A.md": noprefix})
    f, _n = rules(res, "EXTENSION-A.md")
    ok("rows without a declared prefix fire", "undeclared-prefix" in f, f)

    # Gaps in the sequence are LEGAL and must not fire: an id is allocated once
    # and never reused, so a retired row leaves a hole by design. A gate that
    # demanded density would force exactly the renumbering the scheme forbids.
    gappy = GOOD.replace("| `XX-R3` |", "| `XX-R47` |")
    _c, res = run({"EXTENSION-A.md": gappy})
    f, _n = rules(res, "EXTENSION-A.md")
    ok("a gap in the id sequence is not a finding", not f, f)

    # --- shape classification ----------------------------------------------
    legacy = """# X

## 9. Conformance

### 9.1 MUST Implement

- Store the thing.

### 9.2 SHOULD Implement

- Prefer the other thing.
"""
    _c, res = run({"EXTENSION-A.md": legacy})
    f, _n = rules(res, "EXTENSION-A.md")
    ok("a legacy-shaped inventory is reported", "legacy-shape" in f, f)
    ok("...and is listed in `legacy`", res["legacy"], res["legacy"])

    none = "# X\n\n## 1. Overview\n\nWords.\n"
    _c, res = run({"EXTENSION-A.md": none})
    f, _n = rules(res, "EXTENSION-A.md")
    ok("no conformance section at all is its own finding",
       "no-conformance-section" in f, f)
    ok("...and is NOT reported as a legacy shape", "legacy-shape" not in f, f)

    # The section-selection invariant: a §1.3 whose title contains the word must
    # not be scored as the inventory.
    decoy = """# X

## 1. Overview

### 1.3 Conformance terminology

Words about what conformance means.

## 9. Conformance

**Requirement id prefix:** `XX`

| id | Requirement | Level | § |
|---|---|---|---|
| `XX-R1` | Store the thing | MUST | §3 |
"""
    _c, res = run({"EXTENSION-A.md": decoy})
    f, _n = rules(res, "EXTENSION-A.md")
    ok("the LAST conformance heading is the inventory, not the first",
       not f, f)

    # --- drives -------------------------------------------------------------
    driven = GOOD + """
### 9.2 Conformance items

- `XX-STORE-1` — stores the thing. **Drives:** `XX-R1`, `XX-R2`.
"""
    _c, res = run({"EXTENSION-A.md": driven})
    f, n = rules(res, "EXTENSION-A.md")
    ok("a driven requirement is not reported undriven",
       "undriven-requirement" in n, n)   # R3 is still undriven
    for r in res["results"]:
        note = next((x for x in r["notes"]
                     if x["rule"] == "undriven-requirement"), None)
    ok("...and the undriven count is exactly the rows no item names",
       note and note["count"] == 1, note)
    ok("a `Drives:` annotation never gates", res["conformant"] == 1,
       res["conformant"])

    orphan = GOOD + "\n- `XX-STORE-1` — **Drives:** `XX-R99`.\n"
    _c, res = run({"EXTENSION-A.md": orphan})
    _f, n = rules(res, "EXTENSION-A.md")
    ok("an item driving an undeclared id is reported",
       "drives-undeclared" in n, n)

    # --- could-not-look is not a pass --------------------------------------
    with tempfile.TemporaryDirectory() as td:
        code, res = inventory.scan(Path(td))
    ok("an empty root is could-not-look, not clean",
       code == inventory.CANNOT_LOOK, code)
    ok("...and says so rather than reporting a count", "error" in res)

    # --- the ratchet --------------------------------------------------------
    # A backlog does not gate; a regression does. Those are different questions
    # and conflating them is what makes a first run 24 reds people learn to skip.
    code, res = run({"EXTENSION-A.md": GOOD,
                     "EXTENSION-B.md": legacy})
    ok("a legacy backlog alone does not gate", code == inventory.CLEAN, code)
    code, res = run({"EXTENSION-A.md": GOOD.replace("MUST NOT", "Whatever")})
    ok("a defect INSIDE an adopted inventory gates regardless of backlog",
       code == inventory.VIOLATIONS, code)

    print("\ninventory self-test: %s"
          % ("all assertions passed" if not FAILURES
             else "%d FAILURE(S): %s" % (len(FAILURES), ", ".join(FAILURES))))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
