#!/usr/bin/env python3
"""spec register — is every design document findable by the QUESTION it answers?

    spec register                    # reader, exits 0
    spec register --gate             # 0 clean · 1 findings · 2 could-not-look
    spec register --json
    spec register --owed             # just the worklist

WHAT THIS GATES, AND WHY IT IS NOT ANOTHER COUNTER

A corpus this size already has three ways to find a document and none of them
answer the question a session actually asks. You can find a document **by name**
(an index), **by subject** (a grep, or a subject map), and **by state** (which
directory it sits in, whether its header agrees). What none of those answer is
***does this question already have an answer?*** — and that is the one that
decides whether the next session re-derives.

The failure is measured, not hypothetical. In a single arc six settled
conclusions were re-derived from scratch — a serving rule, an ownership rule, a
supply-chain case, a refresh loop, an audience-control rule and a reader cost
model — and every one of them was already written down in the same repository.

**The asymmetry that makes proposals the expensive half:** an exploration reads
as an open question, so it gets re-opened. **A proposal's conclusion reads as
SETTLED, so it is the last place anyone re-searches** — which means the
documents with the strongest answers are the ones least likely to be found.

THE RULE

Every design document is either **cited by a row in the design register** — so
its conclusion is reachable from the question side — or it **declares that it
has no design conclusion to record**, with the marker:

    Design-Conclusions: none

The marker is deliberately an explicit act. A blank is indistinguishable from
*"nobody has looked at this one yet"*, and that ambiguity is precisely what let
99 proposals sit at 9 cited without anyone being able to say how many of the
other 90 mattered.

**Citation is matched on the document's distinctive stem**, not its full
filename, because the register cites `THE-REDUCTION §4.4` rather than
`EXPLORATION-THE-REDUCTION-MONOTONICITY-IS-THE-PATTERN-...`. Matching on the
full name reports 0 where the truth is 2 — a count of one spelling is not a
census of the thing, and this tool would have shipped that number as a finding.

WHAT IT DELIBERATELY DOES NOT DO

* **It does not check that a register row is CORRECT**, or current, or that
  anyone read the document. A row is evidence of *attention*, never of accuracy
  — the same disclaimer `census` prints on every run.
* **It does not require a row per document.** One row may cite several; a
  document may be cited by several. The unit is *reachability*, not bookkeeping.
* **It never writes.** Adding the marker or the row is a judgment call about
  whether a conclusion exists, and a tool that guessed would fill the register
  with rows nobody stands behind.

**Reader by default.** The first run against a live corpus scores in the
hundreds. A gate that is red on day one teaches people to skip it — the same
reasoning that keeps `pins` a reader, `sdksync`'s backlog non-gating and
`coverage` at exit 0. Burn it down, then `--gate` in CI.

Exit codes are three-valued like every gate here: 0 clean, 1 findings, 2
could-not-look. **A missing register, or a scope that matches no document, is a
2** — never a pass over an unread set.

Stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

CLEAN, VIOLATIONS, CANNOT_LOOK = 0, 1, 2

REGISTER = "docs/DESIGN-REGISTER.md"

# Directories of design documents this gate covers, and the class prefixes whose
# stems the register is expected to cite.
SCAN = ("docs/proposals", "docs/research")
SKIP_DIRS = {"archive", "archived", "deprecated", ".git", "__pycache__",
             "node_modules", "status"}
SKIP_FILES = {"INDEX.md", "README.md"}

# A class prefix carries no information about the question a document answers,
# so the register cites the tail. Stripping them is what makes stem matching
# work at all.
#
# THIS LIST GOES STALE BY CONSTRUCTION and has now done so five times: the
# corpus mints a new document class, the register cites it in house style
# (tail only), and the gate reports a document that IS cited as owed. ABSORPTION
# cost 13 false owed before it was noticed; WALKTHROUGH cost one, caught the day
# the class was minted (2026-09-13).
#
# The failure is quiet in the expensive direction -- a FALSE OWED reads as
# "nobody has looked at this", so the honest response to an owed document whose
# row you can see is to check HERE before writing the row again.
CLASS_PREFIX = re.compile(
    r"^(PROPOSAL|EXPLORATION|ANALYSIS|REVIEW|REFERENCE|ARCH-RESPONSE"
    r"|ARCH-RULINGS|ABSORPTION|PLAN|CRITIQUE|SYNTHESIS|WALKTHROUGH)-")

MARKER = re.compile(r"^\s*Design-Conclusions:\s*none\s*$", re.M | re.I)

# The shortest tail we will accept as a citation. Below this a match is noise —
# a three-character stem would hit inside unrelated prose and report a false
# clean, which is the direction that costs the most.
MIN_STEM = 8

# What a filename carries in front of its subject, and a register row does not.
# A row cites a document by what it is ABOUT, so every one of these is noise on
# the left that breaks the prefix test in `is_cited`:
#
#   EXPLORATION-THE-P2P-COVERAGE-AUDIT-...  cited as  P2P-COVERAGE-AUDIT
#   REVIEW-2026-09-01-THE-KEYSTONE-AUDIT    cited as  THE-KEYSTONE-AUDIT
#
# Stripped iteratively and in any order, because the corpus writes them in any
# order. Measured here: 2 documents missed on the article alone, 11 more on the
# date and the absorption class prefix.
STEM_NOISE = re.compile(r"^(?:THE|A|AN|\d{4}-\d{2}-\d{2}|\d{4}-\d{2}|\d{4})-")


def stem_of(name: str) -> str:
    return CLASS_PREFIX.sub("", name[:-3] if name.endswith(".md") else name)


def spellings_of(stem: str) -> List[str]:
    """The stem as the register might actually spell it.

    One form per prefix the house style drops. New forms go in `STEM_NOISE`
    rather than into `is_cited`, so the prefix discipline stays in one place and
    stays testable: every spelling is still a PREFIX of the real stem, never a
    substring of it.
    """
    out = [stem]
    cur = stem
    while True:
        nxt = STEM_NOISE.sub("", cur, count=1)
        if nxt == cur or not nxt:
            break
        out.append(nxt)
        cur = nxt
    return out


# A citable token as the register actually writes one: SCREAMING-KEBAB, long
# enough that a match means something.
REG_TOKEN = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+")


def register_tokens(reg_text: str) -> List[str]:
    """Every SCREAMING-KEBAB token the register mentions, longest first.

    Matching has to run in BOTH directions and the reason is the house style:
    the register cites `THE-REDUCTION`, while the file is
    `EXPLORATION-THE-REDUCTION-MONOTONICITY-IS-THE-PATTERN`. Testing only
    `stem in register` misses every truncated citation, and a first hand-run of
    exactly that comparison reported "0 of 97 cited" where the truth was 2.

    Tokens are ALSO recorded with the class prefix stripped, because the
    stripping was one-sided: `stem_of` removes `SYNTHESIS-`/`EXPLORATION-` from
    the FILENAME, so a register that cites the prefix **and truncates** — e.g.
    `SYNTHESIS-THE-FIVE-LOOKUPS-REDUCE-TO-ONE-LOOP` for a file two clauses
    longer — matched on neither side and was reported owed. The full-length
    form already worked (it contains the stripped stem as a substring), so this
    only ever fired on prefix-plus-truncation. Measured on this corpus 2026-09-13:
    one document, cited eight times, reported owed.

    Stripping here is safe in the direction that matters: `is_cited` still
    requires the stem to START WITH a token, so a shorter token cannot credit an
    unrelated document — only one whose stem it genuinely prefixes.
    """
    seen = set()
    for t in REG_TOKEN.findall(reg_text):
        if len(t) >= MIN_STEM:
            seen.add(t)
        bare = CLASS_PREFIX.sub("", t)
        if bare != t and len(bare) >= MIN_STEM:
            seen.add(bare)
    return sorted(seen, key=len, reverse=True)


def is_cited(stem: str, reg_text: str, tokens: List[str]) -> bool:
    """True when the register reaches this document under any spelling.

    Either it names the stem outright, or it cites a **leading clause** of it —
    a prefix, which is what truncation produces. A prefix is required rather
    than a bare substring: `EXTENSION-TREE` appearing anywhere in the register
    would otherwise credit every proposal whose name contains it, which is
    over-crediting in the direction that reports a false clean.

    The prefix is tested against every spelling of the stem, because dropping a
    leading article is truncation too. Measured on this corpus: two documents
    reported owed with a register row already pointing at each — the same
    "a count of one spelling is not a census" defect that produced the first
    0-of-97, recurring one article over.
    """
    for spelling in spellings_of(stem):
        if len(spelling) >= MIN_STEM and spelling in reg_text:
            return True
        if any(spelling.startswith(t) for t in tokens):
            return True
    return False


def iter_docs(root: Path) -> List[Path]:
    found: List[Path] = []
    for base in SCAN:
        b = root / base
        if not b.is_dir():
            continue
        for p in sorted(b.rglob("*.md")):
            rel = p.relative_to(root)
            if any(part in SKIP_DIRS for part in rel.parts):
                continue
            if p.name in SKIP_FILES:
                continue
            found.append(p)
    return found


def scan(root: Path) -> Tuple[int, dict]:
    reg = root / REGISTER
    if not reg.is_file():
        return CANNOT_LOOK, {
            "error": "no %s under %s — there is nothing to resolve citations "
                     "against, which is a could-not-look and not a pass"
                     % (REGISTER, root)}
    try:
        reg_text = reg.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return CANNOT_LOOK, {"error": "unreadable register: %s" % exc}

    docs = iter_docs(root)
    if not docs:
        return CANNOT_LOOK, {
            "error": "no design documents found under %s — the scope matched "
                     "nothing, which is not a clean corpus"
                     % ", ".join(SCAN)}

    tokens = register_tokens(reg_text)
    cited: List[str] = []
    declared: List[str] = []
    owed: List[dict] = []
    for p in docs:
        rel = str(p.relative_to(root))
        stem = stem_of(p.name)
        if is_cited(stem, reg_text, tokens):
            cited.append(rel)
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            text = ""
        if MARKER.search(text):
            declared.append(rel)
            continue
        owed.append({"file": rel, "stem": stem})

    res = {
        "root": str(root),
        "register": REGISTER,
        "scanned": len(docs),
        "cited": len(cited),
        "declared_none": len(declared),
        "owed": owed,
    }
    return (VIOLATIONS if owed else CLEAN), res


def report(res: dict, gate: bool, owed_only: bool) -> None:
    if "error" in res:
        print("could not look: %s" % res["error"], file=sys.stderr)
        return
    if owed_only:
        for o in res["owed"]:
            print(o["file"])
        return
    by_dir: Dict[str, int] = {}
    for o in res["owed"]:
        d = os.path.dirname(o["file"])
        by_dir[d] = by_dir.get(d, 0) + 1
    for d in sorted(by_dir, key=lambda k: -by_dir[k]):
        print("  %-46s %4d owed" % (d, by_dir[d]))
    print("\n%d design doc(s) — %d cited by %s, %d declaring no design "
          "conclusion, %d owed."
          % (res["scanned"], res["cited"], res["register"],
             res["declared_none"], len(res["owed"])))
    print("a citation is evidence of ATTENTION, never that the row is correct.")
    if not gate:
        print("reader mode — exits 0. Run with --gate to enforce.")
    print("to discharge one: add a register row pointing at it, or put "
          "`Design-Conclusions: none` in the document.")


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
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)

    root = args.root
    if root is None:
        try:
            import config as _config
            root = _config.corpus_root()
        except Exception:  # noqa: BLE001
            root = Path.cwd()

    code, res = scan(Path(root))
    if args.json:
        print(json.dumps(res, indent=1))
    else:
        report(res, args.gate, args.owed)
    if code == CANNOT_LOOK:
        return CANNOT_LOOK
    return code if args.gate else CLEAN


if __name__ == "__main__":
    raise SystemExit(main())
