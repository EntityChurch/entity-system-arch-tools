#!/usr/bin/env python3
"""ledger_selftest — invariant checks for the declared-count rules.

The defect these rules mechanize is a number that drifted three times in one
file, twice inside one day. It is a cheap rule to write and an easy one to
write *wrongly*, in one specific direction: a count-checker that silently stops
matching reports zero findings and looks exactly like a clean run. **So the
tests that carry the weight here are the ones asserting what was SEEN**, not
only what was flagged — `claims()` is exercised directly for that reason.

    python3 spec-tool/tests/ledger_selftest.py   # exits non-zero on failure

Stdlib-only. Beside parity.sh, address_selftest, coherence_selftest.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ledger  # noqa: E402

FAILURES = []


def ok(name, cond, detail=""):
    if cond:
        print("  ok   %s" % name)
    else:
        FAILURES.append(name)
        print("  FAIL %s %s" % (name, detail))


def fixture(tmp, layout):
    """Build a proposal-tree fixture: {"active/extensions": 3, ...}."""
    base = Path(tmp)
    for relpath, n in layout.items():
        d = base / relpath
        d.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            (d / ("PROPOSAL-%d.md" % i)).write_text("x", encoding="utf-8")
    return base


def count(text, base, rule):
    return len([f for f in ledger.analyze(text, base) if f.rule == rule])


TREE = {"active/extensions": 14, "active/applications": 5, "active/process": 6,
        "implemented/extensions": 17}

with tempfile.TemporaryDirectory() as tmp:
    base = fixture(tmp, TREE)

    # ----------------------------------------------------------------------
    # Extraction. A rule that sees nothing reports nothing and reads green —
    # this is the failure the module is named after, so it is asserted first.
    # ----------------------------------------------------------------------
    print("claim extraction")
    doc = ("## 1. Active — 25 files (ext 14 · app 5 · process 6)\n"
           "**`active/extensions/` — 14**\n")
    seen = ledger.claims(doc, base)
    ok("heading, parenthetical and path forms are all seen", len(seen) == 5,
       "saw %d: %r" % (len(seen), [s[1] for s in seen]))
    ok("the backticked-path form resolves to its directory",
       ("active/extensions", 14) in [(s[2], s[3]) for s in seen])
    ok("the parenthetical resolves through the alias map",
       ("active/applications", 5) in [(s[2], s[3]) for s in seen])

    # ----------------------------------------------------------------------
    # declared-count-mismatch — the shipped defect, reduced.
    # `active/extensions/ — 18` sat in INDEX.md while the directory held 14.
    # ----------------------------------------------------------------------
    print("declared-count-mismatch")
    ok("the shipped defect fires",
       count("**`active/extensions/` — 18**", base, "declared-count-mismatch") == 1)
    ok("the corrected count is quiet",
       count("**`active/extensions/` — 14**", base, "declared-count-mismatch") == 0)
    ok("a heading total is checked against the recursive count",
       count("## 1. Active — 25 files\n", base, "declared-count-mismatch") == 0)
    ok("a wrong heading total fires",
       count("## 1. Active — 24 files\n", base, "declared-count-mismatch") == 1)
    ok("one wrong tier in a parenthetical fires alone",
       count("## 1. Active — 25 files (ext 14 · app 4 · process 6)\n",
             base, "declared-count-mismatch") == 1)

    # ----------------------------------------------------------------------
    # False positives — the teeth. Every fixture below is CORRECT text that a
    # careless pattern would flag; each one, flagged, is a reason to switch
    # the gate off.
    # ----------------------------------------------------------------------
    print("negative cases")
    for name, text in [
        ("a path citation without a count", "see `active/extensions/` for the roster"),
        ("a file citation, not a directory", "`INDEX.md` — 3 sections"),
        ("a table row describing a state", "| `implemented/` | **Folded** — the spec edit landed |"),
        ("prose with a number and no directory anchor",
         "**Why there are 23.** Creation dates: 17 landed in a 13-day window"),
        ("a heading whose word names no directory", "## 4. Peer-implementation — 3 seats"),
        ("an unknown parenthetical token is skipped, not guessed",
         "## 1. Active — 25 files (sdk 9)"),
    ]:
        ok(name, ledger.analyze(text, base) == [], "flagged: %r" % text)

    # ----------------------------------------------------------------------
    # declared-count-dangling — the `unscanned reads as zero` half.
    # ----------------------------------------------------------------------
    print("declared-count-dangling")
    ok("a renamed directory with a live count fires rather than going quiet",
       count("**`active/extensions-old/` — 14**", base, "declared-count-dangling") == 1)
    ok("a declared ZERO over an absent directory is consistent, not drifted",
       count("**`active/core/` — 0**", base, "declared-count-dangling") == 0)
    ok("a zero declaration does not fire as a mismatch either",
       count("**`active/core/` — 0**", base, "declared-count-mismatch") == 0)

    # ----------------------------------------------------------------------
    # The three-valued contract: scanning nothing is not passing.
    # ----------------------------------------------------------------------
    print("could-not-look")
    rc = ledger.run_check([base / "no-such-file.md"], as_json=False)
    ok("an absent ledger document exits 2, not 0", rc == 2, "got %d" % rc)

print()
if FAILURES:
    print("FAILED: %d" % len(FAILURES))
    raise SystemExit(1)
print("ledger self-test: all invariants hold")
