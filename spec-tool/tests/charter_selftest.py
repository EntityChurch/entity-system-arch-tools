#!/usr/bin/env python3
"""charter_selftest — invariant checks for the two-homes discipline gate.

**This suite exists because of the rule the gate itself enforces.** The corpus's
own catalog records a gate recommended on the strength of its contract block,
which turned out to catch one failure mode in three; and a probe that was green
in three trees for two weeks *because its pass condition encoded the wrong
answer*. The ratified enforcement point from those two is that **a gate is
validated in BOTH directions — a known-bad input must go red AND a known-good
input must go green.** A negative control alone tests the gate against the
gate's own notion of failure and cannot see a wrong reference answer.

So every rule here has a matched pair, and the calibration cases (UNMARKED, the
strikethrough promotion idiom) are asserted as *deliberate silence* rather than
left as untested behaviour — an exemption nobody can audit is not an exemption.

    python3 spec-tool/tests/charter_selftest.py   # exits non-zero on failure

Stdlib-only. Beside ledger_selftest, address_selftest, parity.sh.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import charter  # noqa: E402

FAILURES = []


def ok(name, cond, detail=""):
    if cond:
        print("  ok   %s" % name)
    else:
        FAILURES.append(name)
        print("  FAIL %s %s" % (name, detail))


def table(rows):
    """A charter table: [(n, status_cell), ...]."""
    head = "| | Rule | Draft | Status |\n|---|---|---|---|\n"
    return head + "".join(
        "| **L%d** | some rule | — | %s |\n" % (n, s) for n, s in rows)


def summary(rows):
    """An AGENTS.md summary bullet: [(n, marker_or_None), ...]."""
    parts = []
    for n, mark in rows:
        parts.append("**L%d** the rule text%s" % (n, " *(%s)*" % mark if mark else ""))
    return "- " + " · ".join(parts) + ".\n\n- **Numbered `L`, not `A`** — trailing entry.\n"


def rules_of(findings):
    return sorted(f.rule for _, f in findings)


def run(c_rows, a_rows):
    return charter.analyze(charter.parse_charter(table(c_rows)),
                           charter.parse_agents(summary(a_rows)))


print("charter_selftest")

# ---------------------------------------------------------------- parsing
c = charter.parse_charter(table([(1, "**RATIFIED**"), (7, "**CANDIDATE** — five instances")]))
ok("charter parses number and status", {k: v[0] for k, v in c.items()}
   == {1: charter.RATIFIED, 7: charter.CANDIDATE}, c)

a = charter.parse_agents(summary([(1, None), (3, "**ratified** 2026-08-17"), (6, "candidate")]))
ok("agents parses marker and absence", {k: v[0] for k, v in a.items()}
   == {1: charter.UNMARKED, 3: charter.RATIFIED, 6: charter.CANDIDATE}, a)

# The bug this module was written after: a fixed look-ahead window truncated the
# longest entries, so L18 and L21+ silently vanished from the comparison and the
# run came out clean. Multi-line, very long bodies must still attribute.
long_body = ("- **L1** short · **L2** " + ("a very long clause with **bold** and `code` " * 12)
             + "\n  continuing onto another line entirely *(candidate)* · **L3** x "
             + "*(**ratified** 2026-01-01)*.\n\n- **Other** trailing\n")
a2 = charter.parse_agents(long_body)
ok("agents attributes across a long multi-line entry",
   {k: v[0] for k, v in a2.items()} == {1: charter.UNMARKED, 2: charter.CANDIDATE,
                                        3: charter.RATIFIED}, a2)

# The corpus's promotion idiom strikes the old word and keeps it visible.
ok("strikethrough promotion reads as RATIFIED",
   charter._status_of("~~**Candidate: one incident.**~~ **Ratified 2026-08-23**") == charter.RATIFIED)
ok("plain candidate still reads as CANDIDATE",
   charter._status_of("**CANDIDATE** — one incident, operator correction") == charter.CANDIDATE)

# An `L12` mentioned in a note's prose is not a table row.
c2 = charter.parse_charter(table([(1, "**RATIFIED**")])
                           + "\n> A note discussing **L12** and **L99** at length.\n")
ok("prose mention is not a table row", sorted(c2) == [1], sorted(c2))

# ------------------------------------------------- POSITIVE CONTROL (green)
ok("agreeing homes are silent",
   run([(1, "**RATIFIED**"), (6, "**CANDIDATE**")],
       [(1, "**ratified** 2026-01-01"), (6, "candidate")]) == [])

# The live corpus is the real known-good input and it must come out green.
root = Path(__file__).resolve().parents[3] / "entity-system-architecture"
if (root / "AGENTS.md").is_file() and (root / "docs/DISCIPLINE-CHARTER.md").is_file():
    live = charter.analyze(
        charter.parse_charter((root / "docs/DISCIPLINE-CHARTER.md").read_text(encoding="utf-8")),
        charter.parse_agents((root / "AGENTS.md").read_text(encoding="utf-8")))
    ok("live corpus is green", live == [], [f.text for _, f in live])
    ok("live corpus parsed a non-trivial set",
       len(charter.parse_charter((root / "docs/DISCIPLINE-CHARTER.md").read_text(encoding="utf-8"))) >= 20)
else:
    print("  skip live-corpus control (sibling not present)")

# ------------------------------------------------- NEGATIVE CONTROLS (red)
ok("status divergence fires",
   rules_of(run([(9, "**RATIFIED** 2026-08-20")], [(9, "candidate")]))
   == ["charter-status-divergence"])

ok("status divergence fires in the other direction too",
   rules_of(run([(20, "**CANDIDATE**")], [(20, "**ratified** 2026-09-02")]))
   == ["charter-status-divergence"])

ok("rule missing from the canonical table fires",
   rules_of(run([(1, "**RATIFIED**")], [(1, "**ratified** x"), (26, "**ratified** y")]))
   == ["charter-rule-missing"])

ok("rule missing from the agents summary fires",
   rules_of(run([(1, "**RATIFIED**"), (25, "**CANDIDATE**")], [(1, "**ratified** x")]))
   == ["charter-rule-missing"])

# The exact live defect this gate was built after: four stale rows at once.
many = run([(9, "**RATIFIED**"), (18, "**RATIFIED**"), (21, "**RATIFIED**"), (26, "**RATIFIED**")],
           [(9, "candidate"), (18, "candidate"), (21, "candidate")])
ok("the four-row live defect scores 4", len(many) == 4, [f.text for _, f in many])

# ------------------------------------------------- CALIBRATION (deliberate silence)
ok("UNMARKED never fires against RATIFIED",
   run([(1, "**RATIFIED**")], [(1, None)]) == [])
ok("UNMARKED never fires against CANDIDATE",
   run([(6, "**CANDIDATE**")], [(6, None)]) == [])

# ------------------------------------------------- COULD-NOT-LOOK
ok("an unparseable home is exit 2, never a pass",
   charter.run_check(Path("/nonexistent"), Path("/nonexistent/a.md"),
                     Path("/nonexistent/b.md"), False) == 2)

import tempfile  # noqa: E402
with tempfile.TemporaryDirectory() as tmp:
    cp, ap = Path(tmp) / "c.md", Path(tmp) / "a.md"
    cp.write_text("no table here at all\n", encoding="utf-8")
    ap.write_text(summary([(1, None)]), encoding="utf-8")
    ok("a home that parsed 0 rules is exit 2, not a clean run",
       charter.run_check(Path(tmp), cp, ap, False) == 2)

print("\n%d check(s) failed" % len(FAILURES) if FAILURES else "\nall checks passed")
sys.exit(1 if FAILURES else 0)
