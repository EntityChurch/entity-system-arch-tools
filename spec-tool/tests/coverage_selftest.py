#!/usr/bin/env python3
"""coverage_selftest — invariants for the spec→guide/proposal/research mapper.

`coverage` is a reader, so it cannot fail a build — which means a silent
mis-link is invisible unless the tests assert **what was SEEN**, not merely
that the run completed. Same discipline as ledger_selftest: a matcher that
stops matching reports "no coverage" and looks exactly like an honest gap.

The two failure directions this guards:

  * **under-linking** — the guide exists and is not credited (`—` where a
    document is right there). Produces phantom "specs with no guide" work.
  * **over-linking** — affinity matches a stem it should not, so an unsupported
    spec looks supported. Worse, because it hides the gap the tool exists to
    surface.

    python3 spec-tool/tests/coverage_selftest.py   # exits non-zero on failure

Stdlib-only. Beside ledger_selftest, provenance_selftest.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import coverage  # noqa: E402

FAILURES = []


def ok(name, cond, detail=""):
    if cond:
        print("  ok   %s" % name)
    else:
        FAILURES.append(name)
        print("  FAIL %s %s" % (name, detail))


def fixture(tmp, files):
    """files: {"specs/extensions/EXTENSION-FOO.md": "body", ...}"""
    base = Path(tmp)
    for rel, body in files.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return base


def row(res, stem):
    for r in res["specs"]:
        if r["spec"] == stem:
            return r
    return None


print("affinity")
ok("GUIDE-ROLE matches EXTENSION-ROLE",
   coverage._affinity("EXTENSION-ROLE", "GUIDE-ROLE"))
ok("GUIDE-COMPUTE-PROGRAMMING matches EXTENSION-COMPUTE (guide extends topic)",
   coverage._affinity("EXTENSION-COMPUTE", "GUIDE-COMPUTE-PROGRAMMING"))
ok("EXTENSION-ROLE does NOT match GUIDE-ROLLBACK (segment, not prefix)",
   not coverage._affinity("EXTENSION-ROLE", "GUIDE-ROLLBACK"))
ok("EXTENSION-TREE does NOT match GUIDE-TRANSACTION",
   not coverage._affinity("EXTENSION-TREE", "GUIDE-TRANSACTION"))

print("citation matching")
ok("a bare stem is a citation",
   coverage._cite_re("EXTENSION-RELAY").search("see EXTENSION-RELAY §9") is not None)
ok("a stem with .md is a citation",
   coverage._cite_re("EXTENSION-RELAY").search("`EXTENSION-RELAY.md`") is not None)
ok("a longer name is NOT a citation of the shorter one",
   coverage._cite_re("EXTENSION-RELAY").search("EXTENSION-RELAYED-THING") is None)

with tempfile.TemporaryDirectory() as tmp:
    print("end-to-end — what was SEEN")
    base = fixture(tmp, {
        "specs/extensions/EXTENSION-ALPHA.md": "**Version**: 1.2\n**Status**: Active\n",
        "specs/extensions/EXTENSION-BETA.md": "**Version**: 0.1\n**Status**: Draft\n",
        # cites ALPHA by name, and has no stem affinity with it
        "guides/GUIDE-THINGS.md": "how to use EXTENSION-ALPHA well\n",
        # affinity only: teaches BETA without ever naming it
        "guides/GUIDE-BETA.md": "conceptual overview, names nothing\n",
        "docs/proposals/active/PROPOSAL-ALPHA-FIX.md": "amends EXTENSION-ALPHA §3\n",
        "docs/research/explorations/EXPLORATION-ALPHA.md": "EXTENSION-ALPHA design space\n",
        # names a spec-shaped target that is not in this corpus
        "docs/research/reviews/REVIEW-ELSEWHERE.md": "about ENTITY-CORE-PROTOCOL §5.2\n",
        # names nothing spec-shaped at all
        "docs/research/reviews/REVIEW-FREESTANDING.md": "a cohort process note\n",
    })
    res = coverage.analyze(base)

    a = row(res, "EXTENSION-ALPHA")
    b = row(res, "EXTENSION-BETA")
    ok("both specs are seen", a is not None and b is not None)
    ok("version is parsed", a and a["version"] == "1.2", a and a["version"])
    ok("status is parsed", b and b["status"] == "Draft", b and b["status"])

    ok("ALPHA credited a guide by citation",
       a and [h for h in a["guide"] if h["signal"] == "c"])
    ok("ALPHA credited its proposal", a and len(a["proposal"]) == 1)
    ok("ALPHA credited its research", a and len(a["research"]) == 1)

    ok("BETA credited its guide by AFFINITY though never named",
       b and [h for h in b["guide"] if "a" in h["signal"]])
    ok("BETA has no proposal — the gap is reported, not papered over",
       b and b["proposal"] == [])

    ok("over-linking guard: GUIDE-BETA is not credited to ALPHA",
       a and all("GUIDE-BETA" not in h["doc"] for h in a["guide"]))
    ok("over-linking guard: GUIDE-THINGS is not credited to BETA",
       b and all("GUIDE-THINGS" not in h["doc"] for h in b["guide"]))

    print("orphan vs external — the distinction that keeps the list usable")
    orph = res["orphans"]["research"]
    ext = [e["doc"] for e in res["external"]["research"]]
    ok("a doc naming NO spec-shaped target is an orphan",
       any("REVIEW-FREESTANDING" in p for p in orph), orph)
    ok("a doc naming an out-of-corpus spec is EXTERNAL, not an orphan",
       any("REVIEW-ELSEWHERE" in p for p in ext), ext)
    ok("...and is not also listed as an orphan",
       not any("REVIEW-ELSEWHERE" in p for p in orph), orph)

    print("record-absent vs record-missing — the distinction that inverted a finding")
    base2 = fixture(Path(tmp) / "b", {
        # names its originating proposal; that proposal is NOT in this corpus
        "specs/EXTENSION-GAMMA.md":
            "**Version**: 1.0\n**Status**: Active\n"
            "Originating artifact: PROPOSAL-GAMMA-ORIGIN.md\n",
        # names nothing and has nothing
        "specs/EXTENSION-DELTA.md": "**Version**: 1.0\n**Status**: Active\n",
        # informative synthesis doc: no proposal, no guide, and that is correct
        "specs/ARCHITECTURE-THING.md":
            "**Version**: 1.0\n"
            "**Authoritative scope:** Informative architecture reference.\n",
        "docs/proposals/active/PROPOSAL-UNRELATED.md": "about nothing\n",
    })
    r2 = coverage.analyze(base2)
    g = row(r2, "EXTENSION-GAMMA")
    d = row(r2, "EXTENSION-DELTA")
    arch = row(r2, "ARCHITECTURE-THING")
    ok("a spec naming an absent proposal records it",
       g and g["names_absent_proposals"] == ["PROPOSAL-GAMMA-ORIGIN"],
       g and g["names_absent_proposals"])
    ok("a spec naming no proposal records none",
       d and d["names_absent_proposals"] == [])
    ok("an in-corpus proposal is NOT reported as absent",
       all("PROPOSAL-UNRELATED" not in r["names_absent_proposals"]
           for r in r2["specs"]))
    ok("a self-declared informative doc is flagged as such",
       arch and arch["informative"] is True)
    ok("a normative spec is NOT flagged informative",
       g and g["informative"] is False)

    print("could-not-look is not a pass")
    empty = Path(tmp) / "empty"
    empty.mkdir()
    ok("a root with no specs/ exits 2, not 0",
       coverage.main([str(empty)]) == 2)

if FAILURES:
    print("\ncoverage self-test FAILED: %s" % ", ".join(FAILURES))
    sys.exit(1)
print("\ncoverage self-test: all invariants hold")
