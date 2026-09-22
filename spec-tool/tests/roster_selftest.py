#!/usr/bin/env python3
"""roster_selftest — invariant checks for the roadmap-version gate.

**Every rule has a matched pair — a known-bad input must go red AND a known-good
input must go green.** A negative control alone tests a gate against its own
notion of failure and cannot see a wrong reference answer.

**The load-bearing half of this suite is the FALSE-POSITIVE side, and that is
not the usual balance.** On the live corpus there are 97 places where a spec
name sits near a version string and only 38 are roster rows; the other ~59 are
`Depends:` pins, citations and prose. **A `Depends: EXTENSION-TREE.md §3.2
(v4.0.2)` is a deliberate, dated statement of what its author reasoned against
and MUST NOT track the dependency's HEAD** — advancing it would erase the only
record of what was actually checked. So a gate that read all 97 would file
sixty-odd accusations against correct text, which is the direction that gets a
gate switched off inside a week. Those cases are asserted as *deliberate
silence* rather than left untested: an exemption nobody can audit is not an
exemption.

    python3 spec-tool/tests/roster_selftest.py   # exits non-zero on failure

Stdlib-only. Beside charter_selftest, ledger_selftest, parity.sh.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import roster  # noqa: E402

FAILURES = []


def ok(name, cond, detail=""):
    if cond:
        print("  ok   %s" % name)
    else:
        FAILURES.append(name)
        print("  FAIL %s %s" % (name, detail))


def rows(text):
    return roster.roster_rows(text)


def rules(text):
    return [n for _, n, _ in rows(text)]


# ------------------------------------------------- the version-column shape
ok("a bare version cell is read",
   rows("| `EXTENSION-TREE` | 4.3 | notes |") == [(1, "EXTENSION-TREE", "4.3")])
ok("a leading v is tolerated",
   rows("| `EXTENSION-TREE` | v4.3 | notes |") == [(1, "EXTENSION-TREE", "4.3")])
ok("an unbackticked name is read",
   rows("| EXTENSION-TREE | 4.3 | notes |") == [(1, "EXTENSION-TREE", "4.3")])
ok("a .md suffix is stripped",
   rows("| `EXTENSION-TREE.md` | 4.3 | x |") == [(1, "EXTENSION-TREE", "4.3")])
ok("three-part versions survive",
   rows("| `APP-CONVENTION-EMBED` | 0.2.3 | x |")
   == [(1, "APP-CONVENTION-EMBED", "0.2.3")])

# ------------------------------------------------- the members-table shape
ok("a version inside a status cell is read",
   rows("| `APP-CONVENTION-SHARE` | the share record | Draft v0.2 — authored |")
   == [(1, "APP-CONVENTION-SHARE", "0.2")])
ok("a bolded status version is read",
   rows("| `APP-CONVENTION-SEMANTIC-CONTENT-SITE` | c | Draft **v0.5** — x |")
   == [(1, "APP-CONVENTION-SEMANTIC-CONTENT-SITE", "0.5")])
ok("the FIRST maturity-anchored version wins, not a later mention",
   rows("| `APP-CONVENTION-SHARE` | r | Draft v0.2 — supersedes v0.1 entirely |")
   == [(1, "APP-CONVENTION-SHARE", "0.2")])

# ------------------------------------------------- DELIBERATE SILENCE
# Each of these is correct text on the live corpus. A finding here is a false
# accusation, which is the expensive direction.
ok("a Depends line is NOT a roster row",
   rules("**Depends:** `EXTENSION-TREE.md` §3.2 (v4.0.2) · `ENTITY-CORE-PROTOCOL.md` §1.4") == [])
ok("a Depends line inside a table cell is NOT a roster row",
   rules("| Depends | `EXTENSION-TREE` v4.0.2 | the version we reasoned against |") == [])
ok("prose naming a spec and a version is NOT a roster row",
   rules("SITE v0.5 corrected a layer violation (sites are now free-standing).") == [])
ok("a citation is NOT a roster row",
   rules("see `EXTENSION-REGISTRY` v1.26 §6a.3a for the tracked-prefix rule") == [])
ok("a version cell with no spec-shaped name is NOT a roster row",
   rules("| Phase 1 | 2.0 | the milestone |") == [])
ok("a lowercase name is NOT a roster row",
   rules("| `entity-core-go` | 1.2 | a repo, not a spec |") == [])
ok("a table row with no version at all is silent",
   rules("| `EXTENSION-TREE` | the tree extension | Stable |") == [])

# ------------------------------------------------- BOTH DIRECTIONS, end to end
def corpus(spec_version, roster_version, spec_name="EXTENSION-TREE"):
    """Build a throwaway corpus and return (exit_code, findings)."""
    tmp = tempfile.mkdtemp()
    root = Path(tmp)
    (root / "specs" / "extensions").mkdir(parents=True)
    (root / "specs" / "extensions" / ("%s.md" % spec_name)).write_text(
        "# %s\n\n**Version**: %s\n**Status**: Draft\n\n## 1. Body\n\n**Version**: 9.9\n"
        % (spec_name, spec_version), encoding="utf-8")
    (root / "ROADMAP-EXTENSIONS.md").write_text(
        "| Spec | Version | Notes |\n|---|---|---|\n| `%s` | %s | x |\n"
        % (spec_name, roster_version), encoding="utf-8")
    versions = roster.spec_versions(root)
    findings, n_rows, n_docs = roster.analyze(root, versions)
    return findings, n_rows, versions


f, n, v = corpus("4.8", "4.8")
ok("GREEN direction — matching versions produce no finding", f == [] and n == 1)
ok("the header REGION wins over a version restated in the body",
   v.get("EXTENSION-TREE", ("",))[0] == "4.8",
   "got %r" % (v.get("EXTENSION-TREE"),))

f, n, _ = corpus("4.8", "4.3")
ok("RED direction — a stale roster row fires", len(f) == 1 and n == 1)
ok("the finding names the drift rule",
   f and f[0][1].rule == "roster-version-drift")
ok("the message names BOTH numbers and which one wins",
   f and "4.3" in f[0][1].text and "4.8" in f[0][1].text
   and "source of truth" in f[0][1].text)

f, _, _ = corpus("4.8", "4.8", spec_name="EXTENSION-TREE")
ok("a correct row stays silent even when other rows exist", f == [])

# an unknown stem — the rename case
tmp = tempfile.mkdtemp()
root = Path(tmp)
(root / "specs").mkdir(parents=True)
(root / "specs" / "EXTENSION-TREE.md").write_text(
    "**Version**: 4.8\n", encoding="utf-8")
(root / "ROADMAP-EXTENSIONS.md").write_text(
    "| S | V | N |\n|---|---|---|\n| `EXTENSION-RENAMED-AWAY` | 1.0 | x |\n",
    encoding="utf-8")
f, n, _ = roster.analyze(root, roster.spec_versions(root))[0], 0, 0
ok("a row naming a nonexistent spec fires roster-unknown-spec",
   len(f) == 1 and f[0][1].rule == "roster-unknown-spec",
   "got %r" % ([x[1].rule for x in f],))

# a non-spec uppercase token must NOT be accused of being a missing spec
(root / "ROADMAP-EXTENSIONS.md").write_text(
    "| S | V | N |\n|---|---|---|\n| `MILESTONE-FOUR` | 1.0 | not a spec |\n",
    encoding="utf-8")
f = roster.analyze(root, roster.spec_versions(root))[0]
ok("an uppercase token that is not a spec-family name is NOT accused", f == [])

# ------------------------------------------------- COULD-NOT-LOOK
ok("a corpus with no spec headers is exit 2, never a pass",
   roster.run_check(Path("/nonexistent"), False, False, False) == 2)

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    (root / "specs").mkdir()
    (root / "specs" / "EXTENSION-TREE.md").write_text("**Version**: 4.8\n",
                                                      encoding="utf-8")
    ok("specs present but no roster document is exit 2, not a clean run",
       roster.run_check(root, False, False, False) == 2)

    (root / "ROADMAP-EXTENSIONS.md").write_text("no table here at all\n",
                                                encoding="utf-8")
    ok("a roster that parsed 0 rows is exit 2, not a clean run",
       roster.run_check(root, False, False, False) == 2)

    (root / "ROADMAP-EXTENSIONS.md").write_text(
        "| S | V | N |\n|---|---|---|\n| `EXTENSION-TREE` | 4.8 | x |\n",
        encoding="utf-8")
    ok("a clean corpus is exit 0 under --gate",
       roster.run_check(root, True, False, False) == 0)

    (root / "ROADMAP-EXTENSIONS.md").write_text(
        "| S | V | N |\n|---|---|---|\n| `EXTENSION-TREE` | 4.3 | x |\n",
        encoding="utf-8")
    ok("a drifted corpus is exit 1 under --gate",
       roster.run_check(root, True, False, False) == 1)
    ok("reader mode exits 0 even with findings",
       roster.run_check(root, False, False, False) == 0)

print("\n%d check(s) failed" % len(FAILURES) if FAILURES else "\nall checks passed")
sys.exit(1 if FAILURES else 0)
