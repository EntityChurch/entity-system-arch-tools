#!/usr/bin/env python3
"""spec declare — can an implementer see what installing an extension touches?

    spec declare                     # reader, exits 0
    spec declare --gate              # 0 clean · 1 findings · 2 could-not-look
    spec declare --owed              # the worklist, one path per line
    spec declare --json
    spec declare --update-baseline   # raise the ratchet; it never lowers

WHAT THIS GATES

`GUIDE-EXTENSION-DEVELOPMENT` §3.3 — the dependency contract. Every extension
spec MUST state, at the top: what it depends on, who uses it, the namespaces it
owns, the `properties.kind` values it owns, the handler ops it defines, and the
extension points it exposes and consumes. Its own words: *"an implementer
scanning the spec should be able to answer 'what does installing this extension
touch' from the header alone."*

**That MUST is old, correct, and was enforced by nothing — 2 of 26 specs carry
it.** The other 24 declare `Depends` and nothing else. That is not partial
adoption; it is one field of seven.

**Why the number is not a tidiness metric.** A seat generating an extension
implementation can *transcribe* a declared contract and has to *author* an
undeclared one — which is an implementation defining the spec, the one thing
the polyrepo's contributing rules say implementations do not do. The measured
distribution says the same thing from the other side: the two specs that carry
the header are the two carrying a conformance-grade line, so **the header
arrived with a later discipline and §3.3's MUST has never once been enforced.**

WHAT IT DELIBERATELY DOES NOT DO

* **It does not check that a declaration is TRUE.** A spec can claim a namespace
  it does not use, or omit one it does. Reading the field is not verifying it,
  and this tool never claims otherwise.
* **It does not fire on the backlog.** 24 missing headers on day one is a wall
  of red that teaches people to skip the gate. The ratchet is the count of
  complete headers: it rises, and it does not fall.
* **`none` is a complete answer and is the point.** A field saying *"no
  `properties.kind` values"* carries real information; a blank is
  indistinguishable from nobody having looked. Same reasoning as `spec
  register`'s explicit marker.

Exit codes are three-valued: 0 clean, 1 findings, 2 could-not-look.

Stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

CLEAN, VIOLATIONS, CANNOT_LOOK = 0, 1, 2

BASELINE = ".spec-declare-baseline.json"
SCAN = ("specs/extensions",)

# The seven fields of §3.3, each with the spellings the corpus actually uses.
# Calibrated against the corpus's vocabulary, never against the words the
# rule-writer expects — the defect four analyzers in this toolkit have now
# shipped a first measurement on.
FIELDS: List[Tuple[str, re.Pattern]] = [
    ("depends", re.compile(r"\*\*Depends(?:\s+on)?\*\*", re.I)),
    ("used_by", re.compile(r"\*\*Used by\b", re.I)),
    ("owned_namespaces", re.compile(r"\*\*Owned namespaces\b", re.I)),
    ("owned_kinds", re.compile(r"\*\*Owned\s+`?properties\.kind`?", re.I)),
    ("owned_ops", re.compile(r"\*\*Owned handler ops\b", re.I)),
    ("points_exposed", re.compile(r"\*\*Extension points exposed\b", re.I)),
    ("points_consumed", re.compile(r"\*\*Extension points consumed\b", re.I)),
]

FIELD_LABEL = {
    "depends": "Depends on",
    "used_by": "Used by",
    "owned_namespaces": "Owned namespaces",
    "owned_kinds": "Owned `properties.kind` values",
    "owned_ops": "Owned handler ops",
    "points_exposed": "Extension points exposed",
    "points_consumed": "Extension points consumed",
}

FIRST_SECTION = re.compile(r"^##\s")


def header_of(text: str) -> str:
    """Everything before the first `##` section.

    The header region, not a fixed line count. One spec carries sixty lines of
    version history above its `Depends` line, so a windowed read reports it as
    declaring nothing — which is how a hand measurement of this same question
    scored that spec as the only one with no fields at all.
    """
    lines = text.split("\n")
    end = next((i for i, ln in enumerate(lines) if FIRST_SECTION.match(ln)),
               len(lines))
    return "\n".join(lines[:end])


def analyze(rel: str, text: str) -> dict:
    head = header_of(text)
    present = [k for k, pat in FIELDS if pat.search(head)]
    missing = [k for k, _ in FIELDS if k not in present]
    return {
        "file": rel,
        "present": present,
        "missing": missing,
        "complete": not missing,
    }


def iter_specs(root: Path) -> List[Path]:
    found: List[Path] = []
    for base in SCAN:
        b = root / base
        if b.is_dir():
            found.extend(sorted(b.glob("*.md")))
    return found


def read_baseline(root: Path) -> dict:
    p = root / BASELINE
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def scan(root: Path) -> Tuple[int, dict]:
    specs = iter_specs(root)
    if not specs:
        return CANNOT_LOOK, {
            "error": "no specs found under %s (root %s) — the scope matched "
                     "nothing, which is not a clean corpus"
                     % (", ".join(SCAN), root)}

    results = []
    for p in specs:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            return CANNOT_LOOK, {"error": "unreadable spec %s: %s" % (p, exc)}
        results.append(analyze(str(p.relative_to(root)), text))

    complete = [r for r in results if r["complete"]]
    floor = int(read_baseline(root).get("complete_floor", 0))
    regression = len(complete) < floor

    by_field: Dict[str, int] = {k: 0 for k, _ in FIELDS}
    for r in results:
        for k in r["missing"]:
            by_field[k] += 1

    return (VIOLATIONS if regression else CLEAN), {
        "root": str(root),
        "scanned": len(results),
        "complete": len(complete),
        "complete_floor": floor,
        "regression": regression,
        "missing_by_field": by_field,
        "results": results,
    }


def report(res: dict, gate: bool, owed_only: bool) -> None:
    if "error" in res:
        print("could not look: %s" % res["error"], file=sys.stderr)
        return
    if owed_only:
        for r in res["results"]:
            if not r["complete"]:
                print(r["file"])
        return

    print("missing, by field (of %d specs):" % res["scanned"])
    for k, _pat in FIELDS:
        print("  %-32s %3d missing" % (FIELD_LABEL[k], res["missing_by_field"][k]))

    incomplete = [r for r in res["results"] if not r["complete"]]
    if incomplete:
        print("\nspecs with an incomplete dependency contract (%d):"
              % len(incomplete))
        for r in incomplete:
            print("    %-46s has: %s"
                  % (r["file"].split("/")[-1],
                     ", ".join(FIELD_LABEL[k] for k in r["present"]) or "nothing"))

    print("\n%d spec(s) — %d complete header(s), floor %d."
          % (res["scanned"], res["complete"], res["complete_floor"]))
    if res["regression"]:
        print("RATCHET REGRESSION: the complete count fell below the floor.")
    print("`none` is a complete answer. A blank is not — it cannot be told "
          "apart from nobody having looked.")
    print("this reads the fields. It does not check that a declaration is TRUE.")
    if not gate:
        print("reader mode — exits 0. Run with --gate to enforce.")


def update_baseline(root: Path, res: dict) -> int:
    base = read_baseline(root)
    floor = int(base.get("complete_floor", 0))
    now = res["complete"]
    if now < floor:
        print("refusing to lower the floor: %d complete, floor is %d."
              % (now, floor), file=sys.stderr)
        return VIOLATIONS
    base["complete_floor"] = now
    base["scanned"] = res["scanned"]
    base["note"] = ("count of extension specs carrying all seven "
                    "GUIDE-EXTENSION-DEVELOPMENT §3.3 header fields. Rises only.")
    (root / BASELINE).write_text(json.dumps(base, indent=1) + "\n",
                                 encoding="utf-8")
    print("floor raised to %d of %d." % (now, res["scanned"]))
    return CLEAN


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=None)
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--owed", action="store_true")
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    root = args.root
    if root is None:
        try:
            import config as _config
            root = _config.corpus_root()
        except Exception:  # noqa: BLE001
            root = Path.cwd()
    root = Path(root)

    code, res = scan(root)
    if code == CANNOT_LOOK:
        report(res, args.gate, args.owed)
        return CANNOT_LOOK
    if args.update_baseline:
        return update_baseline(root, res)
    if args.json:
        print(json.dumps(res, indent=1))
    else:
        report(res, args.gate, args.owed)
    return code if args.gate else CLEAN


if __name__ == "__main__":
    raise SystemExit(main())
