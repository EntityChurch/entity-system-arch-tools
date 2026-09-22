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
    # proposal-state-mismatch — the blind spot the count rules cannot see.
    #
    # The count rules AGREE about a folded proposal left in `active/`: the file
    # is there and it is counted, so both totals are right and the backlog is
    # still wrong. Every test here is about the DISAGREEMENT between a file's
    # own status and its directory, and the two that carry weight are the
    # negative directions — a declared hold that must stay quiet, and the house
    # idiom that must not be missed.
    # ----------------------------------------------------------------------
    print("proposal-state-mismatch")

    def state(status):
        return ledger.state_finding("# T\n\n**Status:** %s\n" % status, Path("PROPOSAL-X.md"))

    ok("a plain DRAFT is silent", state("DRAFT (2026-08-17)") is None)
    ok("a folded status in active/ fires",
       state("DRAFT — folded at authoring. `EXTENSION-HISTORY` v1.6 → v1.7") is not None)

    # The regression for this rule's own first-run miss. A hand count found 9;
    # the rule found 6, and all three misses were this one sentence — the
    # corpus's standard phrasing for a proposal recording an already-landed
    # fold. Matching the participle and not the noun was the whole bug, and it
    # is the reason the marker list is calibrated against the corpus's actual
    # vocabulary rather than a rule-writer's expectation of it.
    ok("the house idiom `written after the fold` fires (first-run miss)",
       state("DRAFT — reference proposal, written after the fold. See §0.") is not None)

    # L3: a PARTIAL fold must stay active. The hold is declared, not inferred,
    # so these are exemptions the gate can be audited on.
    print("  holds are declared, not inferred")
    for held in ("DRAFT — folded provisionally at §2.4. Stays active until the cohort answers",
                 "PARTIALLY EXECUTED (2026-08-22) — stays in `active/`; read §8 first.",
                 "DRAFT — partially folded ahead of this document. R4–R11 are open",
                 "DRAFT — folded, then reopened; the pin is withdrawn"):
        ok("held: %s" % held[:46], state(held) is None, "fired on a declared hold")

    # The mirror of the first-run miss, found 2026-09-06 when the rule fired on
    # a brand-new DRAFT that said, in terms, that it had NOT landed. A negated
    # marker is not a marker; a substring test cannot tell a claim from its
    # denial. HOLD_MARKERS cannot absorb these — a hold declares "landed, and it
    # stays here anyway", which is a different statement from "not landed".
    print("  a negated fold marker is not a fold marker")
    for denied in ("DRAFT — 2026-09-06. First pass. **Not ratified, not folded.**",
                   "DRAFT (2026-09-06) — not yet implemented",
                   "DRAFT (2026-09-06) — never folded",
                   "DRAFT (2026-09-06) — not executed"):
        ok("denial: %s" % denied[:46], state(denied) is None,
           "read a denial as a declaration")

    # The other direction, and it is the one that keeps the fix honest: a
    # negation that does NOT govern the marker must leave the finding intact.
    ok("a negation elsewhere in the line still fires",
       state("FOLDED (2026-09-06) — folded, but the cohort has not confirmed")
       is not None)

    print("  scope and provenance")
    ok("a `Status:` quoted mid-prose is not read as this file's own state",
       ledger.state_finding(
           "# T\n\n**Status:** DRAFT\n\nwe cite it: **Status:** folded at authoring\n",
           Path("P.md")) is None)
    ok("status_of takes the FIRST status only",
       ledger.status_of("**Status:** DRAFT\n**Status:** folded\n") == "DRAFT")
    ok("a file with no status header is silent, never a guess",
       ledger.state_finding("# T\n\nno header here\n", Path("P.md")) is None)

    # `implemented/` holding a DRAFT header is NOT a defect — a reference
    # proposal written after its own fold says exactly that, correctly. Only
    # `active/` carries a meaning a status can contradict.
    with tempfile.TemporaryDirectory() as t2:
        b2 = Path(t2)
        (b2 / "active" / "extensions").mkdir(parents=True)
        (b2 / "implemented" / "extensions").mkdir(parents=True)
        (b2 / "active" / "extensions" / "A.md").write_text(
            "**Status:** DRAFT — folded at authoring.\n", encoding="utf-8")
        (b2 / "implemented" / "extensions" / "B.md").write_text(
            "**Status:** DRAFT — reference proposal, written after the fold.\n",
            encoding="utf-8")
        found = ledger.analyze_states(b2)
        # Assert the set of adjudicated FILES, not the count of findings — the
        # intent is "implemented/ is never adjudicated", and one file may raise
        # more than one rule. The count form broke the day a second rule was
        # added, which is the tell that it was measuring the wrong thing.
        ok("only `active/` is adjudicated; implemented/ is not a defect",
           {p.name for p, _ in found} == {"A.md"},
           "got %r" % sorted(p.name for p, _ in found))
        ok("the finding is reported against the proposal, not the index",
           found and found[0][1].rule == "proposal-state-mismatch")

    # proposal-moot-in-active — the FOURTH disposition, and the fourth time a
    # marker list in this toolkit was calibrated against the rule-writer's
    # vocabulary instead of the corpus's. Found by a peer reading the tree, not
    # by this gate: `SUPERSEDED BY EVENTS` sat in `active/` while this module
    # reported a clean 0, and that 0 was quoted as "gates green" in a commit.
    print("proposal-moot-in-active")

    def state(status, name="PROPOSAL-X.md"):
        return ledger.state_finding("# T\n\n**Status:** %s\n" % status, Path(name))

    ok("the exact spelling that escaped — SUPERSEDED BY EVENTS",
       state("SUPERSEDED BY EVENTS (2026-09-08)") is not None)
    ok("...and it names the moot rule, not the landed-edit one",
       state("SUPERSEDED BY EVENTS (2026-09-08)").rule == "proposal-moot-in-active")
    ok("WITHDRAWN is moot too", state("WITHDRAWN (2026-08-02)") is not None)
    ok("RETRACTED is moot too", state("RETRACTED — the premise was false") is not None)

    # The moot test must NOT sit behind FOLD_MARKERS: a superseded proposal
    # declares no fold, so routing it through the landed-edit path would silence
    # it exactly as before. This is the regression that matters.
    ok("moot fires with NO fold marker present at all",
       state("SUPERSEDED — nothing landed and nothing will").rule
       == "proposal-moot-in-active")

    # ...and a hold cannot excuse it. "stays active" claims work is still owed;
    # a moot proposal owes none, so the hold escape hatch must not apply.
    ok("a hold marker does not excuse a moot status",
       state("SUPERSEDED BY EVENTS — stays active for now") is not None)

    # The other direction, which is where a too-eager matcher does its damage:
    # an open proposal that merely MENTIONS superseding something else.
    ok("a DRAFT that supersedes ANOTHER document is not itself moot",
       state("DRAFT (2026-09-09) — supersedes PROPOSAL-Y") is None)
    # The regression the first cut of this rule actually caused: the thing
    # withdrawn is a PIN, not the proposal, and the proposal is reopened —
    # a hold. A bare substring test took it out of `active/`.
    ok("`the pin is withdrawn` in a REOPENED proposal is a hold, not moot",
       state("DRAFT — folded, then reopened; the pin is withdrawn") is None)
    ok("a moot word in the explanation, not the declaration, does not fire",
       state("DRAFT (2026-09-09) — the earlier approach is obsolete") is None)
    ok("an ordinary open DRAFT is untouched", state("DRAFT (2026-09-09)") is None)
    ok("a folded proposal still raises the ORIGINAL rule, not the new one",
       state("FOLDED 2026-09-08 as v1.8").rule == "proposal-state-mismatch")

    # proposal-undated-status — the cheap rung under the rule above, and the
    # reason it exists: five folded REGISTRY proposals sat in `active/` while
    # the state gate reported zero, because every one read exactly
    # `**Status:** DRAFT` and a rule that reads a DECLARATION cannot see a
    # header that declares nothing.
    print("proposal-undated-status")

    def undated(status):
        return ledger.undated_finding("# T\n\n**Status:** %s\n" % status,
                                      Path("PROPOSAL-X.md"))

    ok("a bare DRAFT is undated", undated("DRAFT") is not None)
    ok("...and the finding names the rule",
       undated("DRAFT").rule == "proposal-undated-status")
    ok("a parenthesised ISO date satisfies it", undated("DRAFT (2026-08-21)") is None)
    ok("an em-dashed one does too", undated("DRAFT — 2026-07-13.") is None)
    ok("a date anywhere in the line counts, not just at the end",
       undated("DRAFT 2026-09-04 · living document") is None)
    ok("prose with no date does NOT satisfy it — the exact five-proposal shape",
       undated("DRAFT — fourth pass, refined on a peer's answers (`8cd3010`)") is not None)
    ok("a commit-ish hex is not a date", undated("DRAFT (8cd3010)") is not None)
    ok("no status header is silent, never a guess",
       ledger.undated_finding("# T\n\nno header here\n", Path("P.md")) is None)

    # It is INDEPENDENT of the state rule: a folded-and-undated proposal must
    # raise both, or fixing one would silence the other.
    with tempfile.TemporaryDirectory() as t3:
        b3 = Path(t3)
        (b3 / "active" / "extensions").mkdir(parents=True)
        (b3 / "active" / "extensions" / "C.md").write_text(
            "**Status:** DRAFT — folded at authoring.\n", encoding="utf-8")
        (b3 / "active" / "extensions" / "D.md").write_text(
            "**Status:** DRAFT (2026-09-06)\n", encoding="utf-8")
        rules = sorted(f.rule for _, f in ledger.analyze_states(b3))
        ok("a folded+undated proposal raises BOTH rules, not one",
           rules == ["proposal-state-mismatch", "proposal-undated-status"],
           "got %r" % rules)
        ok("...and a dated, honestly-open proposal raises neither",
           not [f for pth, f in ledger.analyze_states(b3) if pth.name == "D.md"])

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
