#!/usr/bin/env python3
"""declare self-test — the §3.3 dependency contract, both directions.

Fixtures rather than corpus counts, so a corpus conversion never makes this
stale.

**The invariant that earns most of this file is the header REGION.** The
contract is "at the top", and one spec in the live corpus carries sixty lines of
version history above its `Depends` line. A windowed read of the first N lines
scores that spec as declaring nothing at all — which is exactly what a hand
measurement of this question did, and it published the wrong number for one
spec. The region ends at the first `##`, whatever that costs in line count.

**The mirror defect is over-crediting from prose**, and it is the more
dangerous one because it reports a false clean: a sentence like *"the
integration point used by the history extension"* contains `used by`, and a
whole-file grep counts it as the field. A hand measurement made that mistake
too, in the same pass, in the opposite direction.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import declare  # noqa: E402

FAILURES = []


def ok(name, cond, extra=""):
    if cond:
        print("  ok   %s" % name)
    else:
        FAILURES.append(name)
        print("  FAIL %s %s" % (name, extra))


FULL = """# X — Normative Specification

**Version**: 1.0
**Status**: Active
**Depends**: ENTITY-CORE-PROTOCOL.md (v7.19+)

**Used by (informative):** none yet.

**Owned namespaces (closed):**
- `system/x/` — the whole subtree.

**Owned `properties.kind` values:** none.

**Owned handler ops:**
- `system/x:go`

**Extension points exposed:** none.

**Extension points consumed:** the emit pathway.

---

## 1. Overview

Words.
"""


def run(specs):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "corpus"
        d = root / "specs" / "extensions"
        d.mkdir(parents=True, exist_ok=True)
        for n, b in specs.items():
            (d / n).write_text(b, encoding="utf-8")
        return declare.scan(root)


def result(res, fname):
    return next(r for r in res["results"] if r["file"].endswith(fname))


def main() -> int:
    print("declare self-test")

    code, res = run({"EXTENSION-A.md": FULL})
    r = result(res, "EXTENSION-A.md")
    ok("all seven fields is a complete header", r["complete"], r["missing"])
    ok("...and is counted", res["complete"] == 1, res["complete"])
    ok("a complete corpus exits 0", code == declare.CLEAN, code)

    # `none` is an ANSWER. This is the whole reason the fields are required
    # rather than inferred: a spec owning no `kind` values has said so.
    ok("`none` counts as a declaration",
       "owned_kinds" not in r["missing"], r["missing"])

    # --- each field is really required ------------------------------------
    for field, marker in [
            ("used_by", "**Used by (informative):** none yet.\n"),
            ("owned_namespaces", "**Owned namespaces (closed):**\n"),
            ("owned_kinds", "**Owned `properties.kind` values:** none.\n"),
            ("owned_ops", "**Owned handler ops:**\n"),
            ("points_exposed", "**Extension points exposed:** none.\n"),
            ("points_consumed",
             "**Extension points consumed:** the emit pathway.\n")]:
        _c, res = run({"EXTENSION-A.md": FULL.replace(marker, "")})
        r = result(res, "EXTENSION-A.md")
        ok("dropping `%s` makes the header incomplete" % field,
           field in r["missing"], r["missing"])

    # --- the header REGION, not a line window -----------------------------
    long_history = FULL.replace(
        "**Depends**:",
        "\n".join("**v0.%d:** a paragraph of version history." % i
                  for i in range(1, 60)) + "\n**Depends**:")
    _c, res = run({"EXTENSION-A.md": long_history})
    r = result(res, "EXTENSION-A.md")
    ok("sixty lines of version history above the fields does not hide them",
       r["complete"], r["missing"])

    # --- prose after the first section must NOT be credited ---------------
    prose = """# X

**Version**: 1.0
**Depends**: core

## 1. Overview

The emit pathway is the integration point **Used by** the history extension,
and the **Owned namespaces** discussion appears in this paragraph too.
"""
    _c, res = run({"EXTENSION-A.md": prose})
    r = result(res, "EXTENSION-A.md")
    ok("a field name occurring in BODY prose is not credited",
       "used_by" in r["missing"] and "owned_namespaces" in r["missing"],
       r["present"])
    ok("...and `Depends` in the header still is",
       "depends" in r["present"], r["present"])

    # --- the ratchet -------------------------------------------------------
    _c, res = run({"EXTENSION-A.md": FULL, "EXTENSION-B.md": prose})
    ok("a backlog alone does not gate — the floor is 0",
       res["complete"] == 1 and not res["regression"], res)
    ok("per-field counts are reported, not just a total",
       res["missing_by_field"]["owned_kinds"] == 1,
       res["missing_by_field"])

    # --- could-not-look is not a pass --------------------------------------
    with tempfile.TemporaryDirectory() as td:
        code, res = declare.scan(Path(td))
    ok("an empty root is could-not-look, not clean",
       code == declare.CANNOT_LOOK, code)

    print("\ndeclare self-test: %s"
          % ("all assertions passed" if not FAILURES
             else "%d FAILURE(S): %s" % (len(FAILURES), ", ".join(FAILURES))))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
