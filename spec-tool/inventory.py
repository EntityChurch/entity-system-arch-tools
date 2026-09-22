#!/usr/bin/env python3
"""spec inventory — is a conformance requirement addressable, or only quotable?

    spec inventory                   # reader, exits 0
    spec inventory --gate            # 0 clean · 1 findings · 2 could-not-look
    spec inventory --owed            # the worklist, one path per line
    spec inventory --json
    spec inventory --update-baseline # raise the ratchet; it never lowers

WHAT THIS GATES

`SPECIFICATION-FORMAT` §8.5a: a conformance inventory is a table of
individually identified requirements — a declared id prefix, one row per
requirement, a per-row `Level` from a closed vocabulary, and a stable
`<PREFIX>-R<n>` id that is allocated once and never reused.

**The defect it exists for is not untidiness.** A citation of the form
`SPEC §9.1` names a *section*, and a conformance section routinely holds a
dozen independently failable obligations. So the two questions a check set has
to answer cannot be asked at all:

  * which requirements does no conformance item drive?  (a rule the ecosystem
    believes it enforces and does not)
  * which items drive nothing declared?  (a check asserting a private opinion —
    and a check asserting the wrong thing passes exactly as green as one
    asserting the right thing)

Both become mechanical the moment a row has a name. Neither is answerable
without one, however carefully anybody reads.

**The shape was already declared and enforced by nothing.** §5.1 prescribed a
conformance section's form from the first version of the format standard, and
a measured 19 of 26 extension specs follow it — the corpus was never disorderly,
it was unaddressable. Restating a rule that is already correct changes nothing;
this is the enforcement point that was missing.

WHAT IT DELIBERATELY DOES NOT DO

* **It does not say a requirement is right**, or complete, or that the level on
  it is the level it should carry. It reads the shape. A row saying the wrong
  thing under a stable id is exactly as parseable as a row saying the right one.
* **It does not fire on a legacy-shaped inventory by default.** Nineteen specs
  in the declared-but-superseded form is a backlog, and a gate red on day one
  teaches people to skip it. The ratchet is the count of conformant inventories,
  which may rise and may not fall.
* **It never writes a spec.** Converting an inventory can surface a requirement
  that is really two — a finding to file, not a thing for a tool to guess at.

**`drives` findings are counts, not errors.** The annotation is a `SHOULD`
because the two sides have different authors and land at different times; an
item authored before its requirement rows exist is not a defect.

Exit codes are three-valued: 0 clean, 1 findings, 2 could-not-look. **No spec
directory, or a scope that matches no file, is a 2** — never a pass over an
unread set.

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

BASELINE = ".spec-inventory-baseline.json"

# Where inventories live. Extensions only for now, on purpose: the application
# and SDK tiers have conformance surfaces too, and widening the scope before the
# extension tier has run with the scheme would report a backlog nobody agreed to.
SCAN = ("specs/extensions",)

# §8.5a's closed vocabulary. Six values, no others. `IMPL-DEFINED` is a row like
# any other — a deliberate statement that the spec declines to constrain a named
# surface, which a check set must NOT test.
LEVELS = ("MUST", "MUST NOT", "SHOULD", "SHOULD NOT", "MAY", "IMPL-DEFINED")

# A conformance section heading, at `##` level, in either numbering style the
# corpus uses (`## 9. Conformance`, `## §11 Cross-impl conformance`).
CONF_HEAD = re.compile(r"^##\s+.*\bconformance\b", re.I)
ANY_H2 = re.compile(r"^##\s")

PREFIX_DECL = re.compile(r"^\*\*Requirement id prefix:\*\*\s*`([A-Z][A-Z0-9]*)`",
                         re.M)

# A requirement row: `| `HIST-R7` | text | SHOULD | §3.3 |`. The id is required
# to be backticked because an unquoted token in a table cell is prose far more
# often than it is an identifier, and over-crediting here reports a false clean.
ROW = re.compile(r"^\|\s*`([A-Z][A-Z0-9]*)-R(\d+)`\s*\|(.*)$")

# `**Drives:** `ROUTE-R2`, `ROUTE-R3`.`
DRIVES = re.compile(r"\*\*Drives:\*\*\s*((?:\s*`[A-Z][A-Z0-9]*-R\d+`\s*,?)+)")
DRIVEN_ID = re.compile(r"`([A-Z][A-Z0-9]*-R\d+)`")


def conformance_section(text: str) -> Optional[Tuple[int, List[str]]]:
    """The LAST `##`-level conformance section, with its start line.

    The last, not the first: at least one spec's first heading containing the
    word is a §1.3 definitions section, and scoring against it mis-classifies
    the file. A census that matched the first heading reported ten specs with
    "no recognizable shape" where the true number is four.
    """
    lines = text.split("\n")
    starts = [i for i, ln in enumerate(lines) if CONF_HEAD.match(ln)]
    if not starts:
        return None
    s = starts[-1]
    e = next((i for i in range(s + 1, len(lines)) if ANY_H2.match(lines[i])),
             len(lines))
    return s, lines[s:e]


def analyze(rel: str, text: str) -> dict:
    """One spec's inventory, as findings plus the facts behind them."""
    out = {
        "file": rel,
        "conformant": False,
        "prefix": None,
        "rows": 0,
        "findings": [],       # shape defects — these gate
        "notes": [],          # counts and review prompts — these do not
    }
    sec = conformance_section(text)
    if sec is None:
        out["findings"].append({
            "rule": "no-conformance-section",
            "detail": "no `##`-level conformance section — nothing states what "
                      "an implementation must do to claim this spec"})
        return out

    start, body = sec
    blob = "\n".join(body)

    m = PREFIX_DECL.search(blob)
    rows: List[Tuple[str, int, str, int]] = []   # prefix, n, cells, lineno
    for off, ln in enumerate(body):
        rm = ROW.match(ln)
        if rm:
            rows.append((rm.group(1), int(rm.group(2)), rm.group(3),
                         start + off + 1))

    if not rows:
        out["findings"].append({
            "rule": "legacy-shape",
            "detail": "conformance section carries no `<PREFIX>-R<n>` "
                      "requirement rows — a citation of it names a section, not "
                      "a requirement (SPECIFICATION-FORMAT §8.5a)"})
        return out

    out["rows"] = len(rows)

    if not m:
        out["findings"].append({
            "rule": "undeclared-prefix",
            "detail": "requirement rows are present but no `**Requirement id "
                      "prefix:**` line declares the prefix — a reader must not "
                      "have to infer it, and a tool inferring it is guessing"})
    else:
        out["prefix"] = m.group(1)
        wrong = sorted({p for p, _n, _c, _l in rows if p != m.group(1)})
        if wrong:
            out["findings"].append({
                "rule": "prefix-mismatch",
                "detail": "rows use %s; the declared prefix is `%s`"
                          % (", ".join("`%s`" % w for w in wrong), m.group(1))})

    seen: Dict[Tuple[str, int], int] = {}
    for p, n, _cells, lineno in rows:
        key = (p, n)
        if key in seen:
            out["findings"].append({
                "rule": "duplicate-id",
                "line": lineno,
                "detail": "`%s-R%d` appears twice (first at line %d) — an id "
                          "reaching two rows cannot be cited" % (p, n, seen[key])})
        else:
            seen[key] = lineno

    for p, n, cells, lineno in rows:
        parts = [c.strip() for c in cells.split("|")]
        # cells = ` Requirement | Level | § |` -> parts[0] req, parts[1] level
        level = parts[1] if len(parts) > 1 else ""
        level = level.replace("`", "").replace("*", "").strip()
        if level not in LEVELS:
            out["findings"].append({
                "rule": "bad-level",
                "line": lineno,
                "detail": "`%s-R%d` has Level %r — §8.5a's vocabulary is %s"
                          % (p, n, level, " · ".join(LEVELS))})

    declared = {"%s-R%d" % (p, n) for p, n, _c, _l in rows}
    driven = set()
    for dm in DRIVES.finditer(text):
        driven |= set(DRIVEN_ID.findall(dm.group(1)))

    undriven = sorted(declared - driven)
    orphan_drives = sorted(driven - declared)
    if undriven:
        out["notes"].append({
            "rule": "undriven-requirement",
            "count": len(undriven),
            "detail": "%d requirement(s) named by no conformance item: %s"
                      % (len(undriven), ", ".join(undriven[:6])
                         + (" …" if len(undriven) > 6 else ""))})
    if orphan_drives:
        out["notes"].append({
            "rule": "drives-undeclared",
            "count": len(orphan_drives),
            "detail": "item(s) drive ids this spec does not declare: %s"
                      % ", ".join(orphan_drives)})

    out["conformant"] = not out["findings"]
    return out


def iter_specs(root: Path) -> List[Path]:
    found: List[Path] = []
    for base in SCAN:
        b = root / base
        if not b.is_dir():
            continue
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

    conformant = [r for r in results if r["conformant"]]
    base = read_baseline(root)
    floor = int(base.get("conformant_floor", 0))

    # Two independent gate conditions, and they answer different questions.
    # `hard` is a defect in a spec that HAS adopted the scheme — a duplicate id,
    # a level outside the vocabulary — and it fires whatever the backlog is.
    # `regression` is the ratchet: the count went DOWN.
    hard = [r for r in results
            if any(f["rule"] not in ("legacy-shape", "no-conformance-section")
                   for f in r["findings"])]
    regression = len(conformant) < floor

    res = {
        "root": str(root),
        "scanned": len(results),
        "conformant": len(conformant),
        "conformant_floor": floor,
        "regression": regression,
        "legacy": [r["file"] for r in results
                   if any(f["rule"] == "legacy-shape" for f in r["findings"])],
        "no_section": [r["file"] for r in results
                       if any(f["rule"] == "no-conformance-section"
                              for f in r["findings"])],
        "results": results,
    }
    return (VIOLATIONS if (hard or regression) else CLEAN), res


def report(res: dict, gate: bool, owed_only: bool) -> None:
    if "error" in res:
        print("could not look: %s" % res["error"], file=sys.stderr)
        return
    if owed_only:
        for r in res["results"]:
            if not r["conformant"]:
                print(r["file"])
        return

    for r in res["results"]:
        if not r["findings"] and not r["notes"]:
            continue
        head = "%s  (%d row(s))" % (r["file"], r["rows"])
        printed = False
        for f in r["findings"]:
            if f["rule"] in ("legacy-shape", "no-conformance-section"):
                continue
            if not printed:
                print("\n" + head)
                printed = True
            print("  ERROR  %-22s %s" % (f["rule"], f["detail"]))
        for n in r["notes"]:
            if not printed:
                print("\n" + head)
                printed = True
            print("  note   %-22s %s" % (n["rule"], n["detail"]))

    if res["no_section"]:
        print("\nno conformance section at all — nothing states what claiming "
              "the spec requires:")
        for f in res["no_section"]:
            print("    %s" % f)
    if res["legacy"]:
        print("\nlegacy shape, held by the ratchet (%d):" % len(res["legacy"]))
        for f in res["legacy"]:
            print("    %s" % f)

    print("\n%d spec(s) — %d conformant inventory(ies), floor %d."
          % (res["scanned"], res["conformant"], res["conformant_floor"]))
    if res["regression"]:
        print("RATCHET REGRESSION: the conformant count fell below the floor. "
              "The floor only rises; --update-baseline refuses to lower it.")
    print("a stable id makes a requirement citable. It says nothing about "
          "whether the requirement is right.")
    if not gate:
        print("reader mode — exits 0. Run with --gate to enforce.")


def update_baseline(root: Path, res: dict) -> int:
    """Raise the floor. Never lower it.

    The same discipline the narrative baselines carry, pointed the other way:
    there the number is debt and only falls, here it is coverage and only
    rises. Re-baselining your way to green is not available in either
    direction — that is the whole value of a ratchet.
    """
    base = read_baseline(root)
    floor = int(base.get("conformant_floor", 0))
    now = res["conformant"]
    if now < floor:
        print("refusing to lower the floor: %d conformant, floor is %d. "
              "Fix the regression rather than the baseline." % (now, floor),
              file=sys.stderr)
        return VIOLATIONS
    base["conformant_floor"] = now
    base["scanned"] = res["scanned"]
    base["note"] = ("count of extension specs whose conformance inventory "
                    "follows SPECIFICATION-FORMAT §8.5a. Rises only.")
    (root / BASELINE).write_text(json.dumps(base, indent=1) + "\n",
                                 encoding="utf-8")
    print("floor raised to %d of %d." % (now, res["scanned"]))
    return CLEAN


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=None,
                    help="corpus root (default: --corpus / $SPEC_CORPUS / cwd)")
    ap.add_argument("--gate", action="store_true",
                    help="exit non-zero on findings (default: reader, exits 0)")
    ap.add_argument("--owed", action="store_true",
                    help="print only the worklist, one path per line")
    ap.add_argument("--update-baseline", action="store_true",
                    help="raise the conformant floor to the current count")
    ap.add_argument("--json", action="store_true", help="emit JSON")
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
