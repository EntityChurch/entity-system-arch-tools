#!/usr/bin/env python3
"""spec disclose — does a core fold say which conformance cells it crosses?

    spec disclose                        # reader, exits 0
    spec disclose --gate                 # 0 clean · 1 findings · 2 could-not-look
    spec disclose --owed                 # the worklist, one path per line
    spec disclose --peer-root PATH       # the OTHER corpus this team owns
    spec disclose --binds-from 0.8.2.32  # the last revision outside the rule
    spec disclose --json

WHAT THIS GATES

`GUIDE-CONFORMANCE` §5.3a — **a proposal folding a normative change into the
core protocol MUST carry a CELL DISCLOSURE**: the cells of the conformance scope
table its deltas touch, and for each one whether a check has been DRIVEN against
it (`driven` · `named-vector-not-driven` · `no vector`).

**An undriven cell does not block the fold. An undisclosed one does.**

WHY THE RULE IS SHAPED THAT WAY, AND THEREFORE WHY THIS GATE IS

The stronger rule — *a fold lands only when its cells are driven green* — was
adopted once and is unmeetable while most cells carry no vector: it forbids
every fold, so folds land under it unnoticed and it enforces nothing. A gate
for it would be a first run of a hundred-odd reds, which is the shape this
toolkit has declined four times (`coverage` exits 0, `sdksync` warns, `inventory`
and `declare` ratchet, `pins` reads). **Hold the debt, gate the delta.**

So this gate checks the half that is mechanical and arch-side: **that the
disclosure exists and has the declared shape.**

WHAT IT DELIBERATELY DOES NOT DO

* **It does not check that a disclosed state is TRUE.** Arch does not run the
  checks and cannot observe coverage. A cell disclosed `driven` that is not is
  invisible here and is verifiable only by the seat that owns the scope table.
  That limit is §5.3a.2's, stated rather than implied.
* **It does not check that the disclosure is COMPLETE** — that the rows cover
  every cell the deltas touch. Completeness is a claim about the fold's
  normative surface against a table that lives in another tree.
* **It does not reach backwards.** §5.3a binds forward from `--binds-from`;
  revisions at or below it are out of scope by the rule, not by a baseline. A
  reconstructed disclosure is a table nobody measured.

SCOPE IS TWO RULES, AND THE SECOND ONE IS THE POINT

A **landed** fold is scoped by the revision it landed as. A **pending** one is
in scope whatever number its header currently writes: the binding line is the
head of the spec, so anything still to land lands past it. Scoping on the
written number alone under-reports in the silent direction — two live core
proposals name only the revision they CORRECT, because the target reached the
title and the `Proposes:` line and never the `Status:` line. So the worklist
this gate prints on day one is not a backlog, it is **the folds about to
land**, which is the delta the rule is for.

One consequence worth knowing before reading a red run: a proposal that folded
and was left marked DRAFT reports here as pending and owes a disclosure it
cannot usefully have. That is `spec ledger`'s `proposal-state-mismatch`
surfacing one gate over, and the fix is the `Status:` line, not a disclosure.

SCOPE, AND WHY IT TAKES TWO ROOTS

A core-protocol proposal lives in `entity-core-protocol/docs/proposals/`, and an
authoring copy may live in `entity-system-architecture/docs/proposals/`. One
team owns both trees, so a run that resolves one root grades half the channel —
the defect this toolkit has now shipped seven times. Pass `--peer-root`; the
roots searched are printed on every run, and a root that does not exist is
could-not-look, never a silent skip.

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

SCAN = ("docs/proposals",)

# `ENTITY-CORE-PROTOCOL` 0.8.2.32 is the last revision outside §5.3a. The
# binding point is CORPUS knowledge, not tool knowledge — it is a default here
# and a flag, the same way `provenance` takes its window.
DEFAULT_BINDS_FROM = "0.8.2.32"

# The closed vocabulary of §5.3a. A state outside it is a finding: the whole
# value of the column is that `no vector` and `named-vector-not-driven` are
# different claims, and a free-text column collapses them.
STATES = ("driven", "named-vector-not-driven", "no vector")

FIRST_SECTION = re.compile(r"^##\s")
HEADING = re.compile(r"^(#{2,6})\s+(.*)$")
# `## Cell disclosure`, `### 4. Cell disclosure`, `## Cell Disclosure (D1-D4)`.
DISCLOSURE_HEADING = re.compile(r"^\s*(?:\d+[.)]?\s*)?cell\s+disclosure\b", re.I)

# Has this proposal LANDED? `RATIFIED` alone is deliberately not a marker: this
# corpus separates ratified from folded on purpose, and the fold is the event
# §5.3a binds. `RULED` is not one either — one live proposal is RULED and HELD.
LANDED = re.compile(r"\b(FOLDED|IMPLEMENTED|LANDED)\b")
STATUS_LINE = re.compile(r"^\*\*Status[:*]", re.I | re.M)

READ_FROM = re.compile(r"\bread\s+from\b", re.I)
COMMITISH = re.compile(r"\b[0-9a-f]{7,40}\b")
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

SEPARATOR_CELL = re.compile(r"^:?-{2,}:?$")
MARKUP = re.compile(r"[`*_]+")


def strip_markup(s: str) -> str:
    return MARKUP.sub("", s).strip()


def header_of(text: str) -> str:
    """Everything before the first `##` section.

    A region, not a line window: two live core proposals carry their `Status:`
    line at line 7 or 8 under a revision block, and a windowed read of the first
    N lines would score them as naming no revision at all — `declare`'s lesson,
    which cost a published number.
    """
    lines = text.split("\n")
    end = next((i for i, ln in enumerate(lines) if FIRST_SECTION.match(ln)),
               len(lines))
    return "\n".join(lines[:end])


def parse_binds_from(s: str) -> Tuple[str, int]:
    m = re.fullmatch(r"(\d+\.\d+\.\d+)\.(\d+)", s.strip())
    if not m:
        raise ValueError(
            "--binds-from wants a four-component revision like 0.8.2.32, got %r"
            % s)
    return m.group(1), int(m.group(2))


def revisions_in(head: str, series: str) -> List[int]:
    """Fourth components of `<series>.N` named in the header region.

    The header is where a proposal DECLARES what it folds as. The body cites
    other revisions constantly — what it corrects, what it supersedes — and
    scanning it would put every proposal that mentions a revision in scope.
    """
    pat = re.compile(r"\b%s\.(\d+)\b" % re.escape(series))
    return [int(m.group(1)) for m in pat.finditer(head)]


def disclosure_section(text: str) -> Optional[List[str]]:
    """The lines of the `Cell disclosure` section, or None if there is none.

    Ends at the next heading of the same or higher level, so a `####`
    sub-heading inside the disclosure stays part of it.
    """
    lines = text.split("\n")
    start = None
    level = 0
    for i, ln in enumerate(lines):
        m = HEADING.match(ln)
        if m and DISCLOSURE_HEADING.match(m.group(2)):
            start, level = i + 1, len(m.group(1))
            break
    if start is None:
        return None
    out: List[str] = []
    for ln in lines[start:]:
        m = HEADING.match(ln)
        if m and len(m.group(1)) <= level:
            break
        out.append(ln)
    return out


def table_rows(lines: List[str]) -> List[Tuple[str, str]]:
    """`(cell, state)` pairs from the pipe tables in a section.

    Skips separator rows and the header row. A row needs two columns; a
    one-column pipe line is prose, not a disclosure row.
    """
    rows: List[Tuple[str, str]] = []
    for ln in lines:
        s = ln.strip()
        if not s.startswith("|"):
            continue
        cols = [c.strip() for c in s.strip("|").split("|")]
        if len(cols) < 2:
            continue
        if all(SEPARATOR_CELL.match(c) for c in cols if c):
            continue
        cell, state = strip_markup(cols[0]), strip_markup(cols[1])
        if not cell and not state:
            continue
        if state.lower() == "state" or cell.lower() == "cell":
            continue  # the header row
        rows.append((cell, state))
    return rows


def has_landed(rel: str, head: str) -> bool:
    """Did this proposal's fold already happen?

    Two signals, because neither is reliable alone: the `Status:` line's own
    word, and the `implemented/` directory. A proposal that folded and was left
    in `active/` with a DRAFT header is a live defect class here — `spec
    ledger`'s `proposal-state-mismatch` — so this reads the header first and
    treats the directory as corroboration, never as the authority.
    """
    m = STATUS_LINE.search(head)
    if m:
        line_end = head.find("\n\n", m.start())
        status = head[m.start():line_end if line_end != -1 else len(head)]
        if LANDED.search(status):
            return True
    return "/implemented/" in "/" + rel.replace("\\", "/")


def analyze(rel: str, text: str, series: str, floor: int) -> Optional[dict]:
    head = header_of(text)
    revs = revisions_in(head, series)
    if not revs:
        return None
    target = max(revs)
    landed = has_landed(rel, head)
    # A LANDED fold is scoped by the revision it landed as: §5.3a binds forward
    # and does not reach backwards.
    #
    # A PENDING one is in scope whatever number its header currently writes,
    # and this is the half a revision-only rule gets silently wrong. The
    # binding line is the head of the spec, so **anything still to land, lands
    # past it** — including a draft authored months ago, and including one
    # whose header names only the revision it CORRECTS. Two live core proposals
    # are exactly that shape: the target number reached the title and the
    # `Proposes:` line and never the `Status:` line, so scoping on the written
    # number alone under-reports by one revision, in the silent direction.
    rec = {
        "file": rel,
        "revision": "%s.%d" % (series, target),
        "landed": landed,
        "in_scope": (target > floor) if landed else True,
        "reason": "landed as %s.%d" % (series, target) if landed
                  else "pending — it lands past the binding line",
        "findings": [],
        "cells": 0,
        "by_state": {s: 0 for s in STATES},
    }
    if not rec["in_scope"]:
        return rec

    section = disclosure_section(text)
    if section is None:
        rec["findings"].append(
            ("disclosure-missing",
             "%s and carries no `Cell disclosure` section" % rec["reason"]))
        return rec

    body = "\n".join(section)
    sourced = any(
        READ_FROM.search(ln) and COMMITISH.search(ln) and ISO_DATE.search(ln)
        for ln in section)
    if not sourced:
        rec["findings"].append(
            ("disclosure-unsourced",
             "no `Read from:` line naming a commit and a date — a disclosure "
             "that cites no run is a guess with a table's formatting"))

    rows = table_rows(section)
    rec["cells"] = len(rows)
    if not rows:
        rec["findings"].append(
            ("disclosure-empty",
             "a `Cell disclosure` section with no cell rows"))
    for cell, state in rows:
        key = state.lower()
        if key in rec["by_state"]:
            rec["by_state"][key] += 1
        else:
            rec["findings"].append(
                ("disclosure-state-unknown",
                 "cell %s: state %r is outside the closed vocabulary (%s)"
                 % (cell or "?", state, " · ".join(STATES))))
    _ = body
    return rec


def iter_proposals(root: Path) -> List[Path]:
    found: List[Path] = []
    for base in SCAN:
        b = root / base
        if b.is_dir():
            found.extend(sorted(b.rglob("*.md")))
    return found


def scan(roots: List[Path], binds_from: str = DEFAULT_BINDS_FROM
         ) -> Tuple[int, dict]:
    try:
        series, floor = parse_binds_from(binds_from)
    except ValueError as exc:
        return CANNOT_LOOK, {"error": str(exc)}

    missing = [str(r) for r in roots if not r.is_dir()]
    if missing:
        return CANNOT_LOOK, {
            "error": "root(s) do not exist: %s — a named root that is absent is "
                     "could-not-look, never a silent skip" % ", ".join(missing)}

    files: List[Tuple[Path, Path]] = []
    for r in roots:
        files.extend((r, p) for p in iter_proposals(r))
    if not files:
        return CANNOT_LOOK, {
            "error": "no proposals found under %s in %s — the scope matched "
                     "nothing, which is not a clean corpus"
                     % (", ".join(SCAN), ", ".join(str(r) for r in roots))}

    results = []
    for root, p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            return CANNOT_LOOK, {"error": "unreadable proposal %s: %s" % (p, exc)}
        rec = analyze(str(p.relative_to(root)), text, series, floor)
        if rec is not None:
            results.append(rec)

    in_scope = [r for r in results if r["in_scope"]]
    findings = [r for r in in_scope if r["findings"]]
    by_state: Dict[str, int] = {s: 0 for s in STATES}
    for r in in_scope:
        for s in STATES:
            by_state[s] += r["by_state"][s]

    return (VIOLATIONS if findings else CLEAN), {
        "roots": [str(r) for r in roots],
        "binds_from": "%s.%d" % (series, floor),
        "scanned": len(files),
        "name_a_revision": len(results),
        "in_scope": len(in_scope),
        "in_scope_landed": len([r for r in in_scope if r["landed"]]),
        "in_scope_pending": len([r for r in in_scope if not r["landed"]]),
        "out_of_scope_landed": len([r for r in results if not r["in_scope"]]),
        "with_findings": len(findings),
        "cells_disclosed": sum(r["cells"] for r in in_scope),
        "by_state": by_state,
        "results": results,
    }


def report(res: dict, gate: bool, owed_only: bool) -> None:
    if "error" in res:
        print("could not look: %s" % res["error"], file=sys.stderr)
        return
    if owed_only:
        for r in res["results"]:
            if r["findings"]:
                print(r["file"])
        return

    print("roots searched: %s" % ", ".join(res["roots"]))
    print("§5.3a binds forward from %s (that revision is the last one outside "
          "the rule)." % res["binds_from"])
    print("%d proposal(s) scanned · %d name a core revision · %d in scope "
          "(%d pending, %d landed past the line) · %d landed before it."
          % (res["scanned"], res["name_a_revision"], res["in_scope"],
             res["in_scope_pending"], res["in_scope_landed"],
             res["out_of_scope_landed"]))

    for r in res["results"]:
        if not r["findings"]:
            continue
        print("\n  %s  [%s, %s]"
              % (r["file"], r["revision"],
                 "landed" if r["landed"] else "pending"))
        for code, detail in r["findings"]:
            print("    %-26s %s" % (code, detail))

    if res["in_scope"]:
        print("\ncells disclosed: %d — %s"
              % (res["cells_disclosed"],
                 " · ".join("%s %d" % (s, res["by_state"][s]) for s in STATES)))
        if res["by_state"]["no vector"]:
            print("`no vector` rows are REQUIREMENTS ON THE CHECK SET created "
                  "by these folds. They are not discharged by the fold landing.")
    print("\n%d in scope, %d with findings."
          % (res["in_scope"], res["with_findings"]))
    if res["in_scope_pending"]:
        print("a pending proposal with no disclosure reads `not ready to "
              "land`, which is the rule rather than a backlog. The disclosure "
              "is written AT the fold, from a census read taken then — one "
              "written weeks early is a stale table, the defect §5.3a exists "
              "to prevent.")
    print("this checks the SHAPE. Whether a disclosed state is TRUE is "
          "verifiable only by the seat that owns the scope table.")
    if not gate:
        print("reader mode — exits 0. Run with --gate to enforce.")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=None)
    ap.add_argument("--peer-root", type=Path, action="append", default=[],
                    help="the other corpus this team owns; repeatable")
    ap.add_argument("--binds-from", default=DEFAULT_BINDS_FROM)
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--owed", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    root = args.root
    if root is None:
        try:
            import config as _config
            root = _config.corpus_root()
        except Exception:  # noqa: BLE001
            root = Path.cwd()
    roots = [Path(root)] + [Path(p) for p in args.peer_root]

    code, res = scan(roots, args.binds_from)
    if code == CANNOT_LOOK:
        report(res, args.gate, args.owed)
        return CANNOT_LOOK
    if args.json:
        print(json.dumps(res, indent=1))
    else:
        report(res, args.gate, args.owed)
    return code if args.gate else CLEAN


if __name__ == "__main__":
    raise SystemExit(main())
