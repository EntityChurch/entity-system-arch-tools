#!/usr/bin/env python3
"""deps self-test — the declared dependency graph, asserted in both directions.

**The first section is the incident this analyzer caused, and it is asserted
rather than remembered.** `deps`' very first run reported **38 dangling
dependencies and every one was false**: the three most-depended-upon documents
in the ecosystem live in a sibling repository, so resolving `Depends` against the
inspected tree alone marked the core protocol as *a prerequisite that cannot be
installed* twenty-six times.

That is `could-not-look wearing a verdict's clothes` for the sixth time in this
toolkit — and the first introduced by an author who had the other five written
down in front of them. So the contract is pinned here: **without a namespace
root an unresolvable dependency is UNKNOWN and never dangling; with one, a name
absent from every searched root still is.**

The second thing worth its own section is the cycle normalization. One mutual
dependency between two documents surfaced as SEVEN findings, six of them the
same 2-cycle reached from different specs upstream. A reader counting findings
would have priced one defect at seven.

Every assertion runs in BOTH directions. A negative control proves the check can
fire; only the positive one shows the pass condition is right.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import deps  # noqa: E402

FAILURES = []


def ok(name, cond, extra=""):
    if cond:
        print("  ok   %s" % name)
    else:
        FAILURES.append(name)
        print("  FAIL %s %s" % (name, extra))


_CASE = [0]


def build(tmp: Path, specs: dict, sub="specs/extensions") -> Path:
    """specs: {DOC-NAME: body}. Returns the corpus root."""
    _CASE[0] += 1
    root = tmp / ("corpus%d" % _CASE[0])
    d = root / sub
    d.mkdir(parents=True, exist_ok=True)
    for name, body in specs.items():
        (d / ("%s.md" % name)).write_text(body, encoding="utf-8")
    return root


def spec(depends=None, body="", history=0):
    """A spec header with optional version-history padding above `Depends`."""
    out = ["# Title", ""]
    out += ["**v1.%d:** a changelog line." % i for i in range(history)]
    if depends is not None:
        out.append("**Depends**: %s" % depends)
    out += ["", "## 1. Body", body]
    return "\n".join(out)


def main() -> int:
    print("deps self-test")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # ---- 1. THE NAMESPACE-ROOT INCIDENT, both directions -------------
        root = build(tmp, {"EXTENSION-A": spec("ENTITY-CORE-PROTOCOL.md (v7.3+)")})
        code, res = deps.scan(root)
        ok("without --namespace-root a missing dep is UNRESOLVED",
           len(res["unresolved"]) == 1 and not res["dangling"], res)
        ok("...and the run does NOT gate on it",
           code == deps.CLEAN, code)
        ok("...and it names the root it actually searched",
           res["searched_roots"] == [str(root)], res["searched_roots"])

        sib = build(tmp, {"ENTITY-CORE-PROTOCOL": spec()}, sub="specs")
        code, res = deps.scan(root, namespace_roots=[sib])
        ok("with --namespace-root the same dep RESOLVES",
           not res["unresolved"] and not res["dangling"]
           and "ENTITY-CORE-PROTOCOL" in res["external_resolved"], res)

        # The other direction: a name absent from EVERY searched root is a real
        # finding, and the flag must not turn the check off.
        root2 = build(tmp, {"EXTENSION-A": spec("EXTENSION-NOWHERE.md")})
        code, res = deps.scan(root2, namespace_roots=[sib])
        ok("a genuinely absent dep IS dangling once roots were searched",
           len(res["dangling"]) == 1 and not res["unresolved"], res)
        ok("...and THAT gates", code == deps.VIOLATIONS, code)

        # A sibling's own dependencies must not enter this corpus's graph.
        sib2 = build(tmp, {"ENTITY-CORE-PROTOCOL": spec("SOMETHING-ELSE.md")},
                     sub="specs")
        code, res = deps.scan(root, namespace_roots=[sib2])
        ok("a sibling is a TARGET only — its own deps are not graphed here",
           "ENTITY-CORE-PROTOCOL" not in res["edges"], res["edges"])

        # ---- 2. CYCLE NORMALIZATION --------------------------------------
        # One mutual dependency reached from three upstream specs.
        root = build(tmp, {
            "SPEC-A": spec("SPEC-B.md"),
            "SPEC-B": spec("SPEC-A.md"),
            "SPEC-C": spec("SPEC-A.md"),
            "SPEC-D": spec("SPEC-C.md"),
        })
        code, res = deps.scan(root)
        ok("one mutual dependency is ONE cycle, not one per path that reaches it",
           len(res["cycles"]) == 1, res["cycles"])
        ok("the cycle names both members",
           "SPEC-A" in res["cycles"][0] and "SPEC-B" in res["cycles"][0],
           res["cycles"])
        ok("a cycle gates", code == deps.VIOLATIONS, code)

        # Negative control: an acyclic corpus reports none and exits clean.
        root = build(tmp, {"SPEC-A": spec("SPEC-B.md"), "SPEC-B": spec()})
        code, res = deps.scan(root)
        ok("an acyclic corpus reports no cycle and is CLEAN",
           not res["cycles"] and code == deps.CLEAN, res)

        # ---- 3. HEADER PARSING -------------------------------------------
        # A REGION, not a line window: sixty changelog lines above `Depends`.
        root = build(tmp, {"SPEC-A": spec("SPEC-B.md", history=60),
                           "SPEC-B": spec()})
        _, res = deps.scan(root)
        ok("sixty history lines above `Depends` do not hide it",
           res["edges"].get("SPEC-A") == ["SPEC-B"], res["edges"])

        # A `Depends`-shaped sentence in the BODY is not the field.
        root = build(tmp, {
            "SPEC-A": spec(None, body="This **Depends**: SPEC-B.md in prose.\n"),
            "SPEC-B": spec()})
        _, res = deps.scan(root)
        ok("a Depends line in the BODY is not a declaration",
           "SPEC-A" in res["undeclared"] and not res["edges"].get("SPEC-A"),
           res)

        # `.md` and the bare name are ONE node, not two.
        root = build(tmp, {"SPEC-A": spec("SPEC-B.md, SPEC-C"),
                           "SPEC-B": spec(), "SPEC-C": spec()})
        _, res = deps.scan(root)
        ok("`FOO.md` and `FOO` resolve to one node each",
           sorted(res["edges"]["SPEC-A"]) == ["SPEC-B", "SPEC-C"],
           res["edges"])

        # A version pin is CAPTURED and never compared.
        root = build(tmp, {"SPEC-A": spec("SPEC-B.md (v3.5+, for tree events)"),
                           "SPEC-B": spec()})
        _, res = deps.scan(root)
        ok("a version pin is captured",
           res["pins"].get("SPEC-A", {}).get("SPEC-B", "").startswith("v3.5"),
           res["pins"])
        ok("...and a pin never produces a finding",
           not res["dangling"] and not res["unresolved"], res)

        # Hyphenated non-documents must not become edges.
        root = build(tmp, {"SPEC-A": spec("SPEC-B.md — MUST-NOT be READ-ONLY"),
                           "SPEC-B": spec()})
        _, res = deps.scan(root)
        ok("a hyphenated non-document is not an edge",
           res["edges"]["SPEC-A"] == ["SPEC-B"], res["edges"])

        # ---- 4. CLOSURE ---------------------------------------------------
        root = build(tmp, {
            "SPEC-A": spec("SPEC-B.md"),
            "SPEC-B": spec("SPEC-C.md"),
            "SPEC-C": spec(),
            "SPEC-D": spec(),
        })
        _, res = deps.scan(root)
        ok("closure is transitive",
           res["closures"]["SPEC-A"] == ["SPEC-B", "SPEC-C"],
           res["closures"]["SPEC-A"])
        ok("an unrelated spec is not in the closure",
           "SPEC-D" not in res["closures"]["SPEC-A"], res["closures"]["SPEC-A"])
        ok("a leaf has an empty closure",
           res["closures"]["SPEC-C"] == [], res["closures"]["SPEC-C"])

        # ---- 5. THE BESIDE JOIN, all three silence cases ------------------
        many = "\n".join("SPEC-B is discussed here." for _ in range(8))
        # (a) fires: heavy citation, no edge in either direction.
        root = build(tmp, {"SPEC-A": spec(None, body=many), "SPEC-B": spec()})
        _, res = deps.scan(root)
        ok("heavy citation with no declared edge is a beside candidate",
           any(b["from"] == "SPEC-A" and b["to"] == "SPEC-B"
               for b in res["beside"]), res["beside"])

        # (b) silent: a declared edge explains the coupling.
        root = build(tmp, {"SPEC-A": spec("SPEC-B.md", body=many),
                           "SPEC-B": spec()})
        _, res = deps.scan(root)
        ok("a DECLARED edge silences the beside pair", not res["beside"],
           res["beside"])

        # (c) silent: the edge runs the other way.
        root = build(tmp, {"SPEC-A": spec(None, body=many),
                           "SPEC-B": spec("SPEC-A.md")})
        _, res = deps.scan(root)
        ok("an edge in the REVERSE direction also silences it",
           not res["beside"], res["beside"])

        # (d) silent: reachable transitively is not *beside*.
        root = build(tmp, {"SPEC-A": spec("SPEC-M.md", body=many),
                           "SPEC-M": spec("SPEC-B.md"),
                           "SPEC-B": spec()})
        _, res = deps.scan(root)
        ok("transitive reachability is not a beside pair",
           not any(b["to"] == "SPEC-B" for b in res["beside"]), res["beside"])

        # (e) silent: below the threshold.
        root = build(tmp, {"SPEC-A": spec(None, body="SPEC-B once.\n"),
                           "SPEC-B": spec()})
        _, res = deps.scan(root)
        ok("one mention is below the threshold", not res["beside"],
           res["beside"])

        # (f) the header's own Depends line must not be its own evidence.
        root = build(tmp, {"SPEC-A": spec("SPEC-B.md, SPEC-C.md"),
                           "SPEC-B": spec(), "SPEC-C": spec()})
        _, res = deps.scan(root, beside_min=1)
        ok("a Depends line is not counted as body citation evidence",
           not any(b["from"] == "SPEC-A" for b in res["beside"]),
           res["beside"])

        # ---- 6. COULD-NOT-LOOK -------------------------------------------
        empty = tmp / "empty"
        empty.mkdir()
        code, res = deps.scan(empty)
        ok("an empty root is COULD-NOT-LOOK, not a clean corpus",
           code == deps.CANNOT_LOOK and "error" in res, res)

    print()
    if FAILURES:
        print("%d FAILURE(S): %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("deps self-test: all assertions passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
