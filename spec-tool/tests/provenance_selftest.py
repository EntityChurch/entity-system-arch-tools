#!/usr/bin/env python3
"""provenance_selftest — invariant checks for the L1 gate.

This gate reads **history**, so the fixtures are a real throwaway git repo built
commit by commit. Mocking git here would test the mock.

**The negative cases carry the weight, and one of them is the whole design.** A
version-header-only trigger would pass `no_bump_but_musts` — the shape that is
arch's *most common* normative edit under the cohort-finding carve-out, and the
reason the routed sketch was corrected before it was built.

    python3 spec-tool/tests/provenance_selftest.py   # exits non-zero on failure

Stdlib-only. Beside parity.sh, ledger_selftest, coherence_selftest.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import provenance  # noqa: E402

FAILURES = []


def ok(name, cond, detail=""):
    if cond:
        print("  ok   %s" % name)
    else:
        FAILURES.append(name)
        print("  FAIL %s %s" % (name, detail))


def run(*args, cwd):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


SPEC = """# EXTENSION-FIXTURE

**Version**: %s
**Status**: Active

## 1. Body

%s
"""


def commit(root, version, body, msg):
    (root / "specs").mkdir(exist_ok=True)
    (root / "specs" / "EXTENSION-FIXTURE.md").write_text(SPEC % (version, body),
                                                         encoding="utf-8")
    run("git", "add", "-A", cwd=root)
    run("git", "commit", "-q", "-m", msg, cwd=root)
    return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    run("git", "init", "-q", "-b", "main", cwd=root)
    run("git", "config", "user.email", "t@t", cwd=root)
    run("git", "config", "user.name", "t", cwd=root)

    # A proposal that exists on disk, so "names a proposal" can be satisfied.
    pdir = root / "docs" / "proposals" / "active" / "extensions"
    pdir.mkdir(parents=True)
    (pdir / "PROPOSAL-FIXTURE-THING.md").write_text("# p", encoding="utf-8")

    base = commit(root, "1.0", "A peer SHOULD do the thing.", "init")
    stems = provenance.proposal_stems(root)
    ok("proposal existence is a directory listing", "PROPOSAL-FIXTURE-THING" in stems)

    def case(name, version, body, msg, want_rule, want):
        sha = commit(root, version, body, msg)
        got = [f for f in provenance.analyze_commit(root, sha, stems)
               if f.rule == want_rule]
        ok(name, len(got) == want, "want %d got %d" % (want, len(got)))

    R = "normative-edit-without-proposal"

    def musts(n):
        """A body carrying exactly `n` normative tokens. Every satisfaction
        case below MUST move this count, or it passes vacuously — which two of
        them did on the first run of this file."""
        return " ".join("A peer MUST do thing %d." % i for i in range(n))

    print("triggers")
    # THE case the version-only design would have missed. Arch's two folds on
    # 2026-08-15 were exactly this: MUSTs added, version deliberately unchanged.
    case("no bump but MUSTs added still fires", "1.0", musts(1),
         "spec: add a rule", R, 1)
    case("version bump alone fires", "1.1", musts(1), "spec: bump", R, 1)
    case("a reworded MUST is not a new MUST — neither trigger fires", "1.1",
         musts(1) + " Clarified.", "spec: reword", R, 0)
    case("REMOVING a requirement fires too", "1.1", musts(0),
         "spec: drop the rule", R, 1)

    # Negative control: the satisfaction cases below must be capable of firing,
    # or they prove nothing. This is the same body-count move with a bare
    # message, and it MUST report.
    print("negative control — the guard can fire")
    case("the trigger the satisfaction cases rely on does fire unaided", "1.1",
         musts(2), "spec: land it", R, 1)

    print("satisfaction")
    case("naming an existing proposal satisfies it", "1.1", musts(3),
         "spec: land it\n\nPer PROPOSAL-FIXTURE-THING.", R, 0)
    case("the hygiene carve-out satisfies it", "1.1", musts(4),
         "spec: tidy\n\nSpec-Change: hygiene", R, 0)
    case("the cohort-finding carve-out satisfies it", "1.1", musts(5),
         "spec: fix in place\n\nSpec-Change: cohort-finding", R, 0)

    print("the exemption must be real")
    case("a proposal named but absent from disk does NOT satisfy", "1.1",
         musts(6), "spec: land\n\nPer PROPOSAL-NO-SUCH-THING.", R, 1)
    case("an unrecognised trailer is its own finding, not a pass", "1.1",
         musts(7), "spec: land\n\nSpec-Change: because-i-said-so",
         "spec-change-trailer-unknown", 1)
    case("...and does not count as the missing-proposal finding", "1.1",
         musts(8), "spec: land\n\nSpec-Change: nonsense", R, 0)

    print("document class — L1 governs NORMATIVE spec edits")
    # This gate triggered on the `specs/` PATH PREFIX alone, so revising an
    # informative architecture reference was reported in the same words as a
    # wire-rule change: "the rationale has nowhere to go but the spec text".
    # For an arch-doc that is backwards — an architectural document is where
    # rationale legitimately lives (SPECIFICATION-FORMAT §11.3 row 2).
    #
    # The teeth stay where the harm is: class downgrades the VERSION-BUMP
    # trigger only. The anti-dodge cases are why this is not a blanket
    # exemption — MUSTs cannot be parked in an arch-doc to escape L1.
    I = "informative-doc-revision"

    def arch_commit(version, body, msg):
        (root / "specs" / "ARCHITECTURE-FIXTURE.md").write_text(
            SPEC % (version, body), encoding="utf-8")
        run("git", "add", "-A", cwd=root)
        run("git", "commit", "-q", "-m", msg, cwd=root)
        return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()

    def arch_case(name, version, body, msg, want_rule, want):
        sha = arch_commit(version, body, msg)
        got = [f for f in provenance.analyze_commit(root, sha, stems)
               if f.rule == want_rule and "ARCHITECTURE-FIXTURE" in f.text]
        ok(name, len(got) == want, "want %d got %d" % (want, len(got)))

    ok("ARCHITECTURE-* is classed arch-doc, not canonical-spec",
       provenance._CFG.doc_class("ARCHITECTURE-FIXTURE") == "arch-doc",
       provenance._CFG.doc_class("ARCHITECTURE-FIXTURE"))

    arch_commit("1.0", musts(2), "arch: seed the fixture")
    arch_case("an arch-doc version bump is NOT the normative finding",
              "1.1", musts(2), "arch: revise", R, 0)
    arch_case("...it is reported as its own class, not swallowed",
              "1.2", musts(2), "arch: revise again", I, 1)
    arch_case("ANTI-DODGE: adding a MUST to an arch-doc still fires L1",
              "1.2", musts(3), "arch: sneak a rule in", R, 1)
    arch_case("...and that is NOT downgraded to the informative finding",
              "1.2", musts(4), "arch: sneak another", I, 0)
    case("a canonical spec is unaffected — its version bump still fires",
         "2.0", musts(8), "spec: bump", R, 1)

    print("scope")
    (root / "docs" / "note.md").write_text("A peer MUST do the thing.\n", encoding="utf-8")
    run("git", "add", "-A", cwd=root)
    run("git", "commit", "-q", "-m", "docs: a note with MUSTs", cwd=root)
    sha = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    ok("a non-specs/ file with MUSTs is out of scope",
       provenance.analyze_commit(root, sha, stems) == [])

    print("could-not-look")
    rc = provenance.run_check(root, "no-such-ref", as_json=False)
    ok("an unresolvable base ref exits 2, not 0", rc == 2, "got %d" % rc)

with tempfile.TemporaryDirectory() as tmp:
    rc = provenance.run_check(Path(tmp), "HEAD~1", as_json=False)
    ok("a non-repo exits 2, not 0", rc == 2, "got %d" % rc)

print()
if FAILURES:
    print("FAILED: %d" % len(FAILURES))
    raise SystemExit(1)
print("provenance self-test: all invariants hold")
