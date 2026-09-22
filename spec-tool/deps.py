#!/usr/bin/env python3
"""spec deps — the DECLARED dependency graph, and the *beside* edges it cannot see.

    spec deps --namespace-root ../entity-core-protocol      # reader, exits 0
    spec deps --closure EXTENSION-X  # what installing one spec actually pulls in
    spec deps --beside               # heavy citation coupling with NO declared edge
    spec deps --gate                 # 0 clean · 1 findings · 2 could-not-look
    spec deps --json

⛔ PASS `--namespace-root`, AND THIS TOOL WALKED INTO THE DEFECT IT WAS WARNED ABOUT

**This analyzer's FIRST run reported 38 dangling dependencies and every one was
false.** `ENTITY-CORE-PROTOCOL`, `ENTITY-CBOR-ENCODING` and
`ENTITY-NATIVE-TYPE-SYSTEM` live in a sibling repository, so resolving `Depends`
against the inspected tree alone marks the single most-depended-upon document in
the ecosystem as *a prerequisite that cannot be installed* — **26 times.**

That is `could-not-look wearing a verdict's clothes` for the **sixth** time in
this toolkit (`address` without `--namespace-root`, `provenance` without
`--proposal-root`, `coverage` reading the class map, `pins`' composition filter,
`inbound`'s hardcoded ledger) — **and the first where it was introduced by an
author who had the other five written down in front of them.** Recorded here
rather than quietly fixed, because the generalizable half is not *"remember the
flag"*: it is that **a resolver's scope is a premise, and a premise that is
wrong produces confident findings rather than an error.**

Without the flag, an unresolvable dependency is reported as **`unresolved`** and
**never as `dangling`**, and the run says which roots it searched.

WHY THIS IS NOT `spec topology`, AND THE DISTINCTION IS THE WHOLE POINT

`topology` builds the **citation** graph: who *mentions* whom, edges harvested
from `EXTENSION-TREE §5.2` tokens in prose. That answers *what does this document
talk about.*

This builds the **declaration** graph: the `Depends:` field in each spec's header
region, which is the only place a spec states what must exist **beneath** it.
Nothing in this toolkit read that field as a graph. `declare` checks the header
*has* it; `topology` never looks at it. So the question an implementer actually
arrives with — ***what does installing this pull in?*** — was answerable by no
instrument, only by opening 26 headers by hand.

⛔ THE FINDING THIS EXISTS FOR: `Depends` ANSWERS *BENEATH*, NEVER *BESIDE*

`SYSTEM-ARCHITECTURE` §13.1b note 8 states it: a functioning content-fallback
path needs SUBSTITUTE **and** CONTENT **and** TREE **and** a substitute
convention **and** the capability system — **and none of those are `Depends`
edges between each other.** Installing any one member alone does nothing.

So the declared graph is a correct inheritance DAG and a **wrong install guide**,
and the gap is invisible from inside it: a closure that resolves cleanly still
does not tell you the set is complete.

⭐ `--beside` is the half that addresses that, and it is a JOIN rather than a new
measurement: pairs that cite each other heavily in prose while declaring no
dependency in either direction. **Those are the candidate members of an install
set** — two specs that clearly need each other and say so nowhere a machine can
read. It is a *candidate* list and is deliberately reader-level: a heavy citation
with no edge is often perfectly correct (a guide teaching a spec, a composition
document describing extensions it does not depend on), and a gate that called
those defects would be red forever.

WHAT IT DELIBERATELY DOES NOT DO

* **It does not invent edges.** An undeclared dependency is reported, never
  assumed. The `Depends` field is the fact; prose is evidence about the fact.
* **It does not check version pins.** `Depends: FOO.md (v7.3+)` records what an
  author reasoned against on a date, and it MUST NOT track the dependency's HEAD
  — advancing one erases the only record of what was actually checked. The
  version is parsed and reported and never compared. *(This is the calibration
  `roster` earned the hard way: 97 places in the corpus put a spec name near a
  version and only 38 are rosters. The other 59 are pins, and a gate that read
  them all would file sixty accusations against correct text.)*
* **It does not rank importance.** In-degree is printed because it is cheap and
  legible, not because a foundation is a more important document.

Stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

CLEAN, VIOLATIONS, CANNOT_LOOK = 0, 1, 2

# Where specs live. Same scan set as `declare`, kept separate rather than
# imported so this analyzer stays runnable against a corpus that has one and
# not the other.
SCAN = ("specs", "specs/extensions", "specs/sdk", "specs/applications",
        "specs/domains", "specs/bridge-extensions")

FIRST_SECTION = re.compile(r"^##\s")

# `**Depends**:` / `**Depends on**:` / `**Depends:**` — all three spellings are
# live in the corpus, which is the usual lesson: match the corpus's vocabulary,
# not the one the rule-writer expects.
DEPENDS_LINE = re.compile(
    r"^\*\*Depends(?:\s+on)?\*\*\s*:?\s*(.+)$|^\*\*Depends(?:\s+on)?:\*\*\s*(.+)$",
    re.I | re.M)

# A document name inside a Depends value. Anchored on the uppercase spec-name
# shape this corpus uses; the optional `.md` is stripped so `FOO` and `FOO.md`
# are one node rather than two (citation-form drift, which `topology` reports
# separately and which must not split this graph).
DOC_TOKEN = re.compile(r"\b([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)(?:\.md)?\b")

# A version pin riding along with a dependency. Captured for reporting only —
# never compared against anything. See the module docstring.
PIN = re.compile(r"\(([^)]*v[\d.]+[^)]*)\)")

# Tokens that look like a doc name and are not one. Measured against the live
# corpus rather than guessed; each is a false edge if left in.
NOT_A_DOC = {
    "MUST-NOT", "SHOULD-NOT", "MUST-IGNORE", "READ-ONLY", "WRITE-ONLY",
    "FAIL-CLOSED", "FAIL-OPEN", "END-TO-END", "CONTENT-ADDRESSED",
    "SELF-CERTIFYING", "K-OF-N", "ADR-0002", "ADR-0012", "ADR-0027",
}


def header_of(text: str) -> str:
    """Everything before the first `##`.

    A REGION, not a line window. One spec carries sixty lines of version history
    above its `Depends` line, and a 40-line read scores it as declaring nothing
    — the exact defect a hand measurement of this question already made once.
    """
    lines = text.split("\n")
    end = next((i for i, ln in enumerate(lines) if FIRST_SECTION.match(ln)),
               len(lines))
    return "\n".join(lines[:end])


def split_outside_parens(value: str) -> List[str]:
    """Split on `,` and `;` at paren depth 0 only."""
    out, buf, depth = [], [], 0
    for ch in value:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch in ";," and depth == 0:
            out.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    out.append("".join(buf))
    return out


def parse_depends(text: str) -> Tuple[List[str], Dict[str, str], bool]:
    """-> (dependency doc names, {dep: version pin}, declared-at-all)."""
    head = header_of(text)
    m = DEPENDS_LINE.search(head)
    if not m:
        return [], {}, False
    value = m.group(1) or m.group(2) or ""
    deps: List[str] = []
    pins: Dict[str, str] = {}
    # Split on the separators the corpus actually uses, but NOT on one inside a
    # parenthetical. `FOO.md (v3.5+, for tree change event semantics)` is the
    # live shape, and a naive `[;,]` split cuts the pin in half — the chunk then
    # has no closing paren, so the pin is silently dropped while the edge still
    # resolves. **A silent drop that leaves the visible half correct**, which is
    # why it took an assertion rather than a run to find.
    for chunk in split_outside_parens(value):
        names = [n for n in DOC_TOKEN.findall(chunk) if n not in NOT_A_DOC]
        if not names:
            continue
        name = names[0]
        if name in deps:
            continue
        deps.append(name)
        p = PIN.search(chunk)
        if p:
            pins[name] = p.group(1).strip()
    return deps, pins, True


def iter_specs(root: Path) -> List[Path]:
    seen: Set[Path] = set()
    found: List[Path] = []
    for base in SCAN:
        b = root / base
        if not b.is_dir():
            continue
        for f in sorted(b.glob("*.md")):
            if f.resolve() in seen:
                continue
            seen.add(f.resolve())
            found.append(f)
    return found


def canonical_cycle(path: Tuple[str, ...], node: str) -> str:
    """One string per DISTINCT cycle, whatever path reached it.

    The first version reported the whole walk, so ONE mutual dependency between
    two documents surfaced as SEVEN findings — six of them the same 2-cycle
    reached from different SDK specs upstream of it. A reader counting findings
    would have priced one defect at seven. **Normalize to the cycle itself, and
    rotate to a fixed starting point so `A -> B -> A` and `B -> A -> B` are one
    row.**
    """
    i = path.index(node)
    ring = list(path[i:])
    k = ring.index(min(ring))
    ring = ring[k:] + ring[:k]
    return " -> ".join(ring + [ring[0]])


def closure(node: str, edges: Dict[str, List[str]]) -> Tuple[List[str], List[str]]:
    """Transitive closure of `node`, plus any distinct cycles found reaching it.

    Iterative rather than recursive: a corpus with an accidental cycle should
    report the cycle, not raise RecursionError at the reader.
    """
    out: List[str] = []
    cycles: List[str] = []
    stack = [(node, (node,))]
    while stack:
        cur, path = stack.pop()
        for d in edges.get(cur, ()):
            if d in path:
                cycles.append(canonical_cycle(path, d))
                continue
            if d not in out:
                out.append(d)
            stack.append((d, path + (d,)))
    return sorted(out), cycles


def scan(root: Path, beside_min: int = 6,
         namespace_roots: Optional[List[Path]] = None) -> Tuple[int, dict]:
    files = iter_specs(root)
    if not files:
        return CANNOT_LOOK, {
            "error": "no specs found under %s (%s) — the scope matched nothing, "
                     "which is not a corpus with no dependencies"
                     % (root, ", ".join(SCAN))}

    known: Dict[str, str] = {}      # doc name -> relative path (this corpus)
    texts: Dict[str, str] = {}
    for f in files:
        known[f.stem] = str(f.relative_to(root))
        try:
            texts[f.stem] = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            texts[f.stem] = ""

    # Names this corpus may legitimately depend on that live somewhere else.
    # They are resolvable TARGETS and are never graphed as sources: a sibling
    # corpus's own dependencies are that corpus's business, and pulling them in
    # would silently widen the closure with edges nobody here declared.
    external: Dict[str, str] = {}
    searched = [str(root)]
    for nr in (namespace_roots or []):
        nr = Path(nr)
        searched.append(str(nr))
        for f in iter_specs(nr):
            if f.stem not in known:
                external[f.stem] = str(f)

    edges: Dict[str, List[str]] = {}
    pins: Dict[str, Dict[str, str]] = {}
    undeclared: List[str] = []
    dangling: List[dict] = []
    unresolved: List[dict] = []

    for name, text in texts.items():
        deps, pin, declared = parse_depends(text)
        if not declared:
            undeclared.append(name)
        edges[name] = [d for d in deps if d in known]
        pins[name] = pin
        for d in deps:
            if d in known or d in external:
                continue
            rec = {"spec": name, "missing": d, "file": known[name]}
            if namespace_roots:
                # Searched everywhere we were told to and still did not find it:
                # a DECLARED prerequisite that cannot be installed, which is
                # strictly worse than a dangling prose citation.
                dangling.append(rec)
            else:
                # We were not told where else to look. UNKNOWN, never a verdict.
                unresolved.append(rec)

    in_deg: Dict[str, int] = {k: 0 for k in known}
    for src, ds in edges.items():
        for d in ds:
            in_deg[d] = in_deg.get(d, 0) + 1

    closures: Dict[str, List[str]] = {}
    all_cycles: List[str] = []
    for name in known:
        c, cyc = closure(name, edges)
        closures[name] = c
        all_cycles.extend(cyc)

    # ---- the BESIDE join ------------------------------------------------
    # Prose citation counts between documents that declare no edge either way.
    # Counted on the BODY, not the header, so a `Depends` line is never its own
    # evidence of coupling.
    cite_counts: Dict[Tuple[str, str], int] = {}
    for name, text in texts.items():
        body = text[len(header_of(text)):]
        for other in known:
            if other == name:
                continue
            n = len(re.findall(r"\b%s\b" % re.escape(other), body))
            if n:
                cite_counts[(name, other)] = n

    beside: List[dict] = []
    for (a, b), n in cite_counts.items():
        if n < beside_min:
            continue
        if b in edges.get(a, ()) or a in edges.get(b, ()):
            continue          # a declared edge in either direction explains it
        if b in closures.get(a, ()) or a in closures.get(b, ()):
            continue          # reachable transitively; not a *beside* pair
        beside.append({"from": a, "to": b, "citations": n})
    beside.sort(key=lambda r: -r["citations"])

    res = {
        "root": str(root),
        "specs": len(known),
        "declared": len(known) - len(undeclared),
        "undeclared": sorted(undeclared),
        "edges": {k: v for k, v in sorted(edges.items()) if v},
        "pins": {k: v for k, v in sorted(pins.items()) if v},
        "dangling": dangling,
        "unresolved": unresolved,
        "external_resolved": dict(sorted(external.items())),
        "searched_roots": searched,
        "cycles": sorted(set(all_cycles)),
        "closures": closures,
        "in_degree": dict(sorted(in_deg.items(), key=lambda kv: -kv[1])),
        "beside": beside,
        "beside_min": beside_min,
    }
    # Only the two unambiguous defects gate. `undeclared` is authoring debt and
    # `beside` is a candidate list; neither is a defect on its own, and a gate
    # that fired on them would be permanently red.
    code = VIOLATIONS if (dangling or all_cycles) else CLEAN
    return code, res


def report(res: dict, gate: bool, closure_of: Optional[str],
           beside_only: bool) -> None:
    if "error" in res:
        print("could not look: %s" % res["error"], file=sys.stderr)
        return

    if closure_of:
        name = closure_of[:-3] if closure_of.endswith(".md") else closure_of
        if name not in res["closures"]:
            print("no spec named %r in this corpus" % name, file=sys.stderr)
            return
        direct = res["edges"].get(name, [])
        full = res["closures"][name]
        print("%s declares %d direct dependenc(ies) and pulls in %d in total:"
              % (name, len(direct), len(full)))
        for d in full:
            mark = "direct  " if d in direct else "indirect"
            pin = res["pins"].get(name, {}).get(d, "")
            print("  %s  %s%s" % (mark, d, (" (%s)" % pin) if pin else ""))
        if not full:
            print("  (nothing — it depends on no spec in this corpus)")
        print("\n⚠ This is what must exist BENEATH it. It is NOT an install "
              "set: `Depends` never states what must exist BESIDE it, and a "
              "clean closure does not mean the set is complete.")
        return

    if beside_only:
        for b in res["beside"]:
            print("%-40s %-40s %4d" % (b["from"], b["to"], b["citations"]))
        return

    print("%d spec(s) — %d declare a dependency field, %d do not."
          % (res["specs"], res["declared"], len(res["undeclared"])))
    print("searched: %s" % ", ".join(res["searched_roots"]))
    top = [(k, v) for k, v in res["in_degree"].items() if v][:8]
    if top:
        print("\nmost depended upon:")
        for k, v in top:
            print("  %4d  %s" % (v, k))
    if res["dangling"]:
        print("\n%d DECLARED dependenc(ies) name a document found in NONE of "
              "the searched roots — a prerequisite that cannot be installed:"
              % len(res["dangling"]))
        for d in res["dangling"]:
            print("  %s -> %s   (%s)" % (d["spec"], d["missing"], d["file"]))
    if res.get("unresolved"):
        missing = sorted({d["missing"] for d in res["unresolved"]})
        print("\n⚠ %d declared dependenc(y/ies) across %d name(s) could NOT BE "
              "RESOLVED, and that is UNKNOWN rather than dangling — no "
              "--namespace-root was given, so only %s was searched. Names: %s"
              % (len(res["unresolved"]), len(missing),
                 res["searched_roots"][0], ", ".join(missing)))
        print("  ⇒ pass --namespace-root DIR for each sibling corpus. Until "
              "then this run is not a measurement of dangling dependencies.")
    if res.get("external_resolved"):
        print("\n%d dependenc(y/ies) resolved in a sibling corpus: %s"
              % (len(res["external_resolved"]),
                 ", ".join(sorted(res["external_resolved"]))))
    if res["cycles"]:
        print("\n⛔ %d DECLARED dependency cycle(s) — mutual `Depends` edges. "
              "These make the freeze sequencing derived from the dependency DAG "
              "UNDECIDABLE for the nodes involved: neither can freeze first."
              % len(res["cycles"]))
        for c in res["cycles"]:
            print("  %s" % c)
    if res["beside"]:
        print("\n%d pair(s) cite each other %d+ times with NO declared edge "
              "either way — candidate install-set members, NOT defects:"
              % (len(res["beside"]), res["beside_min"]))
        for b in res["beside"][:12]:
            print("  %4d  %s -> %s" % (b["citations"], b["from"], b["to"]))
        if len(res["beside"]) > 12:
            print("  ... %d more (use --beside for the full list; this reader "
                  "does not hide a worklist behind an elision by default)"
                  % (len(res["beside"]) - 12))
    print("\n⛔ `Depends` answers what must exist BENEATH a spec and never what "
          "must exist BESIDE it. A clean graph is a correct inheritance DAG "
          "and a wrong install guide.")
    if not gate:
        print("reader mode — exits 0. Run with --gate to enforce "
              "(dangling + cycles only).")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", type=Path, default=None,
                    help="corpus root (default: --corpus / $SPEC_CORPUS / cwd)")
    ap.add_argument("--closure", metavar="SPEC",
                    help="what installing SPEC pulls in, transitively")
    ap.add_argument("--beside", action="store_true",
                    help="the full beside-candidate list, one pair per line")
    ap.add_argument("--beside-min", type=int, default=6, metavar="N",
                    help="citation threshold for a beside pair (default: 6)")
    ap.add_argument("--namespace-root", action="append", default=None,
                    type=Path, metavar="DIR",
                    help="a sibling corpus whose specs are legitimate "
                         "dependency TARGETS; repeatable. Without it an "
                         "unresolvable dependency is reported as UNKNOWN, "
                         "never as dangling")
    ap.add_argument("--gate", action="store_true",
                    help="exit non-zero on dangling depends or cycles")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)

    root = args.root
    if root is None:
        try:
            import config as _config
            root = _config.corpus_root()
        except Exception:  # noqa: BLE001
            root = Path.cwd()

    code, res = scan(Path(root), args.beside_min,
                     args.namespace_root)
    if args.json:
        print(json.dumps(res, indent=1))
    else:
        report(res, args.gate, args.closure, args.beside)
    if code == CANNOT_LOOK:
        return CANNOT_LOOK
    return code if args.gate else CLEAN


if __name__ == "__main__":
    raise SystemExit(main())
