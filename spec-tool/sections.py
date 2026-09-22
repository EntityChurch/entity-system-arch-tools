#!/usr/bin/env python3
"""sections — does a section number identify exactly one section?

    spec sections [--root PATH] [--gate] [--owed] [--json]

Why it exists. Every citation in this ecosystem is `DOCUMENT §N` — it is the
unit peers cite, the unit routing packets argue in, and the unit product code
carries in comments. **Nothing checked that a section number is unique inside
its own document.** `address` checks that a cited section *resolves*; it finds
the first heading that matches and stops, so a number declared twice resolves
cleanly, silently, to whichever came first. That is the same blind spot
`AGENTS.md` already records for `address` one step over — *"a citation that
resolves to the wrong real section is invisible to every gate we have."*

**The founding incidents, both live and both cited by other seats' code.**

  `GUIDE-CONFORMANCE` carried two `### §3.1` — *What each impl provides*
  (l.192) and *Run discipline* (l.265), with `§3.0` sitting between them at
  l.250, after `§3.4`. Both were cited by number across five seats: the first
  by `entity-core-go`'s `conformance.go` / `emit.go` and by the keystone
  protocol-generator's Kotlin and Rust emitters — which ripple into generated
  peers — and the second by the conformance seat as `§3.1 item 7`, eleven times
  in one document, plus its own `build-info.py` and `run.py`. Filed by
  `entity-system-conformance` as `CQ-43`: *"a citation to `§3.1` resolves, and
  resolves to a descriptive section with no `[MUST]` in it. Every instrument
  either seat has reports that as fine."*

  `EXTENSION-ROLE` carried two `### 1.5` — *Framing clarifications* (l.113,
  with children `1.5.1`–`1.5.3`) and *Relationship to the Identity Extension*
  (l.157, carrying `RI1`–`RI3`). **Nobody had reported this one**; it was found
  by widening the search that answered `CQ-43`. `entity-core-rust`'s
  `extensions/role/src/helpers.rs` cites `§1.5 RI3` (the second);
  `entity-core-go`'s handoffs cite `§1.5.1` (the first). The document's own
  `See §1.5.2` cross-reference resolved under one of two sections a reader
  could land on.

**The tell is the same in both and it is why the second rule exists:** a
section was inserted out of numeric order — `§3.0` after `§3.4`, `§1.5` before
`§1.4` — and the number it was given was already taken. Out-of-order ordering
is the cheap, early, *visible* symptom of the expensive, silent defect.

The rules:

  duplicate-section       One section number declared by two headings in one
                          document. **Error; this gates.** There is no
                          legitimate instance: the number is the citation
                          handle, and a handle that names two things names
                          neither. The fix is to renumber the section whose
                          citations are cheapest to repair — which is a
                          judgement, so the gate names the collision and does
                          not propose the winner.

  section-out-of-order    A section number that decreases relative to the
                          previous heading at its own depth. **Warning; this
                          does NOT gate**, deliberately — see the calibration
                          note below.

  placeholder-section     A heading or a citation whose number is a literal
                          placeholder — `### 4.X`, `SDK-OPERATIONS.md §X.1`.
                          **Warning.** `PROPOSAL-CORPUS-REFERENCE-INTEGRITY` §2
                          named this rule as the one genuinely new thing its
                          Class A needed — *"a literal `§X` is not a number, so
                          `stale-section`'s parser does not see it at all …
                          invisible to every analyzer"* — and it was still
                          unbuilt when this analyzer was written, two weeks on.
                          It lives here rather than in `address` for exactly the
                          reason that proposal gives: the token never reaches
                          `address`'s number parser, so the gap is in what gets
                          *recognized as a reference*, not in how one resolves.
                          Two were live as HEADINGS in `GUIDE-EXTENSION-
                          DEVELOPMENT` — `### 4.X` twice, which is why this
                          analyzer met the class at all: two placeholders
                          collide into a `duplicate-section` error, so the
                          expensive rule found the cheap one.

Calibration — what it deliberately does not flag, because a false accusation
against correct text is the expensive direction (the `vocab` and `roster`
trade, made again):

  * **Letter-suffixed insertions are first-class here and are not out of
    order.** `§7`, `§7a`, `§7b`, `§7c` is this corpus's house style for
    appending to a frozen number, and `§5.2a` after `§5.2` is the normal way an
    amendment lands. Ordering compares `(numeric, letter)` componentwise, so
    `5.2a` follows `5.2` and precedes `5.3`.

  * **Out-of-order is a WARNING and never gates.** The live corpus has
    correct-but-unordered text — `GUIDE-CONFORMANCE` reaches `§5.3` and then
    lands `§5.2c` / `§5.2d` after it, which is untidy and entirely unambiguous:
    every citation still resolves to exactly one section. Gating that would
    file accusations against text with nothing wrong with it and teach people
    to skip the gate, which is the failure mode this toolkit is built against.
    It is reported because it is the *predictor* of the defect that does gate.

  * **Headings inside fenced code blocks are not headings.** A shell comment
    reading `## 3.1 rebuild` is content. Fences are tracked (``` and ~~~).

  * **A date is not a section number.** `## 2026-09-15 …` would otherwise
    tokenize to `2026`, and two dated headings in one document would collide
    into a confident false duplicate. Four-digit year-shaped tokens with no
    dotted component are not section numbers.

  * **`#` (the title) is not a section**, and neither is a heading whose text
    does not open with a number. Prose headings are the majority of the corpus.

  * **`§X` used as a VARIABLE is not a placeholder citation**, which is why
    that rule warns and does not gate. `GUIDE-INSPECTABILITY`'s *"an extension
    spec that includes a `§X` 'Observable Surface' section"* and
    `GUIDE-IMPL-DISCIPLINE`'s quoted template *"Absorption owed in
    `SDK-EXTENSION-OPERATIONS.md §X`"* are both correct English about an
    arbitrary section, and gating them would be a false accusation against text
    doing its job. The rule surfaces the population; a reader decides which
    are unfilled blanks.

Stdlib-only Python 3.11+. Exit **0** clean, **1** findings, **2** could-not-
look — a run that parsed no headings at all has not passed; it has failed to
read, and the two are otherwise the same zero-finding output.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import config as _config

_CFG = _config.load()
_A = _CFG.analyzer("sections")
_RULES: Dict[str, str] = _A.get("rules", {})
_DIRS: List[str] = _A.get("dirs", ["specs", "guides"])

# `### §3.1 What each impl provides` / `### 1.5 Framing clarifications`.
# The `§` is optional because the corpus spells it both ways — `EXTENSION-ROLE`
# omits it and `GUIDE-CONFORMANCE` carries it, and a pattern requiring it would
# have read one of the two founding incidents as a clean file.
HEADING_RE = re.compile(r"^(#{2,6})\s+§?\s*([0-9][0-9a-zA-Z.]*?)[.):]?(?=\s|$)")

# A year standing alone. `## 2026-09-15 The round` tokenizes to `2026` under the
# pattern above; two of them in one document would be reported as a duplicate
# section with total confidence. Requires no dot, so `2026.1` stays a section.
YEAR_RE = re.compile(r"^(19|20)[0-9]{2}$")

FENCE_RE = re.compile(r"^\s*(```|~~~)")

# A section number that is a literal blank: `4.X`, `X.1`, a bare `§X`. Upper
# case only — `§4a` is a real letter-suffixed section and lower case is the
# corpus's insertion convention, so matching `[a-z]` here would accuse the
# house style. `X`/`N`/`M` are the placeholders the corpus actually writes.
PLACEHOLDER_HEAD_RE = re.compile(r"^(?:[0-9]+\.)*[XNM](?:\.[0-9XNM]+)*$")
PLACEHOLDER_REF_RE = re.compile(r"§((?:[0-9]+\.)*[XNM](?:\.[0-9XNM]+)*)\b")


class Finding:
    __slots__ = ("rule", "line", "text")

    def __init__(self, rule: str, line: int, text: str):
        self.rule = rule
        self.line = line
        self.text = text

    def severity(self) -> str:
        return _RULES.get(self.rule, "error")


def _sort_key(num: str) -> Tuple:
    """`5.2a` -> ((5,''),(2,'a')) so `5.2a` sorts after `5.2`, before `5.3`.

    Componentwise on the dotted parts, each split into its numeric prefix and
    its letter suffix. This is what makes the corpus's letter-suffix insertion
    convention read as ordered rather than as sixty findings.
    """
    key: List[Tuple[int, str]] = []
    for part in num.split("."):
        m = re.match(r"^([0-9]*)([a-zA-Z]*)$", part)
        if not m:
            return tuple(key)
        key.append((int(m.group(1)) if m.group(1) else 0, m.group(2)))
    return tuple(key)


def headings(text: str) -> List[Tuple[int, int, str, str]]:
    """`[(line, depth, number, heading-text)]`, code fences excluded."""
    out: List[Tuple[int, int, str, str]] = []
    in_fence = False
    fence_tok = ""
    for i, line in enumerate(text.splitlines(), 1):
        f = FENCE_RE.match(line)
        if f:
            tok = f.group(1)
            if not in_fence:
                in_fence, fence_tok = True, tok
            elif tok == fence_tok:
                in_fence = False
            continue
        if in_fence:
            continue
        m = HEADING_RE.match(line)
        if not m:
            continue
        num = m.group(2)
        if YEAR_RE.match(num):
            continue
        out.append((i, len(m.group(1)), num, line.strip()))
    return out


def prose_lines(text: str):
    """`(line, text)` for every line outside a fenced code block."""
    in_fence = False
    fence_tok = ""
    for i, line in enumerate(text.splitlines(), 1):
        f = FENCE_RE.match(line)
        if f:
            tok = f.group(1)
            if not in_fence:
                in_fence, fence_tok = True, tok
            elif tok == fence_tok:
                in_fence = False
            continue
        if not in_fence:
            yield i, line


def analyze_doc(text: str) -> List[Finding]:
    found: List[Finding] = []
    heads = headings(text)

    for line, _depth, num, raw in heads:
        if PLACEHOLDER_HEAD_RE.match(num):
            found.append(Finding(
                "placeholder-section", line,
                "heading is numbered §%s — a placeholder, not a number; it is "
                "uncitable and two of them collide (%s)" % (num, raw[:60])))

    for line, raw in prose_lines(text):
        if raw.lstrip().startswith("#"):
            continue
        for m in PLACEHOLDER_REF_RE.finditer(raw):
            found.append(Finding(
                "placeholder-section", line,
                "citation to §%s — a placeholder section number; either fill it "
                "in or say 'some section' in words" % m.group(1)))

    seen: Dict[str, List[Tuple[int, str]]] = {}
    for line, _depth, num, raw in heads:
        seen.setdefault(num, []).append((line, raw))
    for num, hits in seen.items():
        if len(hits) < 2:
            continue
        first = hits[0]
        for line, raw in hits[1:]:
            found.append(Finding(
                "duplicate-section", line,
                "§%s is already declared at line %d (%s) — a citation to §%s "
                "resolves to the first and is silently wrong about this one"
                % (num, first[0], first[1][:60], num)))

    # Ordering, per depth: a number that decreases against the previous heading
    # at the same depth. Compared per depth because `### 3.1` legitimately
    # follows `## 3` without decreasing anything.
    prev: Dict[int, Tuple[str, int]] = {}
    for line, depth, num, _raw in heads:
        last = prev.get(depth)
        if last is not None and _sort_key(num) < _sort_key(last[0]):
            found.append(Finding(
                "section-out-of-order", line,
                "§%s follows §%s (line %d) — inserting out of order is how a "
                "number gets reused; check it is not already taken"
                % (num, last[0], last[1])))
        prev[depth] = (num, line)
        # A deeper level restarts under its new parent.
        for d in [d for d in prev if d > depth]:
            del prev[d]

    return sorted(found, key=lambda f: (f.line, f.rule))


def analyze(root: Path) -> Tuple[List[Tuple[str, Finding]], int, int]:
    findings: List[Tuple[str, Finding]] = []
    n_docs = 0
    n_heads = 0
    for d in _DIRS:
        base = root / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.md")):
            text = p.read_text(encoding="utf-8", errors="ignore")
            heads = headings(text)
            if not heads:
                continue
            n_docs += 1
            n_heads += len(heads)
            rel = str(p.relative_to(root))
            for f in analyze_doc(text):
                findings.append((rel, f))
    return findings, n_docs, n_heads


def run_check(root: Path, gate: bool, owed: bool, as_json: bool) -> int:
    findings, n_docs, n_heads = analyze(root)

    if n_docs == 0:
        print("could-not-look: parsed 0 numbered headings under %s (root %s)"
              % (", ".join(_DIRS), root), file=sys.stderr)
        return 2

    n_err = sum(1 for _, f in findings if f.severity() == "error")
    n_warn = len(findings) - n_err

    if owed:
        for doc, f in findings:
            print("%s:%d  %s  %s" % (doc, f.line, f.rule, f.text))
        return 0

    if as_json:
        report: Dict[str, list] = {}
        for doc, f in findings:
            report.setdefault(doc, []).append(
                {"rule": f.rule, "severity": f.severity(),
                 "line": f.line, "text": f.text})
        print(json.dumps({"summary": {"errors": n_err, "warnings": n_warn,
                                      "documents": n_docs,
                                      "headings": n_heads},
                          "findings": report}, indent=2))
        return (1 if n_err else 0) if gate else 0

    by_doc: Dict[str, List[Finding]] = {}
    for doc, f in findings:
        by_doc.setdefault(doc, []).append(f)
    for doc in sorted(by_doc):
        print("\n%s  (%d finding)" % (doc, len(by_doc[doc])))
        for f in by_doc[doc]:
            print("  %-7s %-20s %s:%d  %s"
                  % (f.severity().upper(), f.rule, doc, f.line, f.text))

    print("\nscanned %d document(s), %d numbered heading(s) — %d error(s), "
          "%d warning(s)." % (n_docs, n_heads, n_err, n_warn))
    print("a section number is a citation handle; one number, one section.")
    print("out-of-order is reported and does NOT gate — it is the predictor, "
          "not the defect.")
    if not gate:
        print("reader mode — exits 0. Run with --gate to enforce.")
    return (1 if n_err else 0) if gate else 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, help="corpus root (default: configured)")
    ap.add_argument("--gate", action="store_true",
                    help="exit 1 on errors (0 clean, 1 findings, 2 could-not-look)")
    ap.add_argument("--owed", action="store_true", help="the worklist, one per line")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)
    return run_check(args.root or _CFG.corpus_dir, args.gate, args.owed, args.json)


if __name__ == "__main__":
    raise SystemExit(main())
