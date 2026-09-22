#!/usr/bin/env python3
"""arms — what does the pseudocode refuse, and does the table enumerating that
class list it?

    spec arms [--root PATH] [--doc NAME] [--owed] [--json]

Why it exists. `L23`'s **pseudocode axis** says a code block is a normative home
that shares none of its rule's vocabulary, so neither an enumerate-by-subject
sweep nor a literal grep reaches it. Three shapes of that axis were ratified
before this analyzer: the block a sentence-sweep misses, the control path *to*
the rule's site, and the **mood axis** — the same obligation written as
pseudocode where it is implemented and as prose where it is obliged.

**The fourth shape is why this file exists, and it is the polarity that makes a
reader confidently wrong rather than merely blind.**

  `ENTITY-CORE-PROTOCOL` §6.5's dispatch pseudocode routed a corrupted ROOT
  entity hash to `400 hash_mismatch` from `0.8.2.25`, and the ruling that put it
  there was delivered to `entity-system-conformance` in `CQ-37`. §4.11's cause
  table — **the prose home a reader consults for pre-admission refusal codes** —
  carried a row for a mis-keyed `included` entry and **no row for the root**.

  On 2026-09-16 that seat published, in `CQ-45`: *"the code stays unasserted,
  because **no section assigns one** and inventing one is prohibition 2."*
  Correct about the table. False about the corpus. **And exactly the right call
  on their part** — they refused to invent a code they could not find a home
  for, which is the discipline working.

  The other shapes leave a reader finding nothing and *knowing* they found
  nothing. This one has a reader consult the **right** home and get the **wrong**
  answer, so it manufactures a published **absence** claim instead of a miss.

**This is a READER and it exits 0, deliberately — it does not gate, and the
reason is that the defect it was built for is not mechanically decidable.**
That is worth stating plainly, because the tempting version of this tool is a
gate, and the tempting version would have scored its own founding incident
clean. The unit of the defect is the `(cause, code)` **arm**, and a cause is
prose: *"Validate root entity hash"* and *"an `included` entry whose key is not
`content_hash({type, data})`"* share no token, no structure and no length. A
gate keyed on the CODE cannot see it — `hash_mismatch` appears in both homes, so
every code-level check reports clean on the incident. A gate keyed on arm COUNTS
would fire on every document where a block and a table legitimately differ,
which is most of them, and a gate that cries wolf teaches people to skip it
(the `coverage` and `deps --beside` trade, made again).

So the honest instrument is the one that makes the comparison **cheap**, and
leaves the judgement where it belongs. What this prints, per document:

  * every **refusal arm** in a fenced block — the `→ NNN code` line, with the
    nearest preceding cause line, which in this corpus's block style is the
    branch label (`+- Validate root entity hash`);
  * every **`(status, code)` pair enumerated in prose** — tables and sentences;
  * a **BESIDE** column flagging arms whose code+cause the enumerations do not
    obviously cover, and enumerated pairs no block drives.

Both columns are *candidates for a human*, never verdicts. `code-not-enumerated`
is the strong one — a code assigned in a block and appearing in no prose at all
in its document. `arm-cause-unmatched` is the weak one and is where the founding
incident lands: the code is enumerated, but no enumerated row's text shares
meaningful vocabulary with this arm's cause. **That heuristic has false
positives by construction** and is reported last, under its own heading, with
its own caveat printed on every run.

Calibration — what it deliberately does not report:

  * **A `→` line with no status** (`→ continue`, `→ DENY`) is control flow, not
    a refusal arm. Only `[1-5]NN` with a snake_case code beside it counts.
  * **A code inside a block comment line** (`;` or `#` leading) still counts:
    this corpus writes normative scoping in block comments, which is exactly
    what the control-flow shape was ratified about.
  * **A pair is matched in BOTH orders.** `§4.11`'s table writes
    `| ... | **400** `hash_mismatch` |` and `§4.7`'s writes
    `| `incompatible_protocol` | 400 |`. A status-first pattern alone misses
    every row of the one table in this corpus that calls itself *"a normative
    MUST-emit contract"* — and misses it **silently**, while the run still
    prints arms and a plausible total. That was found by the self-test, not by
    a run.

  * **Prose occurrence is document-scoped**, never corpus-scoped. A code
    enumerated in a sibling document does not discharge this document's block —
    `§4.7` is a per-document registry and the whole point of the incident is
    that a reader consults the document they are in.
  * **A code with no underscore is not a code.** Measured: every error code in
    the core corpus is snake_case with at least one `_`, and every underscore-
    free match is English (`admit`, `bytes`, `cannot`, `default`, `rows`,
    `with`) or a digest width (`SHA256(encoded)` reads as status `256`, code
    `format`). Three false positives on the first run, zero real losses.

  * **A status with no code** (`→ 501`) is reported with code `-` rather than
    dropped, because an arm that names no code is its own finding for a reader
    and silently dropping it would be the elision this toolkit keeps catching
    (`L7`'s reader axis).

Stdlib-only Python 3.11+. Exit **0** always, except **2** could-not-look when a
run parsed no fenced blocks at all under the configured dirs — a run that read
nothing has not passed, it has failed to read.
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
_A = _CFG.analyzer("arms")
_DIRS: List[str] = _A.get("dirs", ["specs", "guides"])

FENCE_RE = re.compile(r"^\s*(```|~~~)")

# `→ 400 hash_mismatch`, `-> 400 `invalid_request``, `400 non_canonical_ecf`.
# The status must be 3 digits in 1xx-5xx; the code is snake_case, optionally
# backticked, and must be at least 4 chars so `400 ok` style noise stays out.
# The code MUST carry an underscore. Measured against the live core corpus:
# EVERY error code in it is snake_case with at least one `_` —
# `hash_mismatch`, `invalid_request`, `non_canonical_ecf`, `path_required`,
# `unsupported_content_hash_format`, all 30-odd of them. And every match
# WITHOUT an underscore is English noise: `admit`, `bytes`, `cannot`,
# `carries`, `default`, `formats`, `rows`, `space`, `with`. Requiring the
# underscore removed three false positives from the first run and cost nothing
# real — including `SHA256(encoded)`, which otherwise reads as status `256`
# code `format`. If a single-word code is ever minted this under-reports, which
# is the safe direction for a reader: a false accusation is the expensive one.
ARM_RE = re.compile(
    r"(?:[→]|->)?\s*\b([1-5][0-9]{2})\b[\s*`,:|]{0,6}([a-z][a-z0-9]*_[a-z0-9_]{2,})`?")

# The SAME pair written the other way round. `§4.7`'s table is
# `| `incompatible_protocol` | 400 |` — code first, status second — and the
# status-first pattern above misses every row of the one table in the corpus
# that declares itself "a normative MUST-emit contract". Found by the self-test
# (`prose enumerations are collected` returned 0), not by a run: a run still
# printed arms and a plausible summary, and only the missing half was wrong.
# Same silent-drop shape `deps` hit when its chunk splitter dropped a pin while
# the edge still resolved.
REV_RE = re.compile(
    r"`([a-z][a-z0-9]*_[a-z0-9_]{2,})`[\s*`,:|]{0,6}\b([1-5][0-9]{2})\b")
# A status with no code at all on the line.
BARE_STATUS_RE = re.compile(r"(?:[→]|->)\s*\b([1-5][0-9]{2})\b")

# A block's branch label. This corpus draws dispatch trees with `+-` / `|`.
LABEL_RE = re.compile(r"^\s*[|+\\]?[-+\s]*([A-Za-z][^\n]*)$")

STOPWORDS = {
    "the", "a", "an", "is", "not", "of", "to", "and", "or", "in", "on", "for",
    "its", "it", "that", "this", "with", "by", "at", "as", "be", "any", "no",
    "entity", "request", "frame", "bytes", "code", "error", "each", "own",
    "from", "which", "when", "than", "into", "under", "over", "per",
}


def _words(s: str) -> set:
    return {w for w in re.findall(r"[a-z]{3,}", s.lower()) if w not in STOPWORDS}


class Arm:
    __slots__ = ("line", "status", "code", "cause", "raw")

    def __init__(self, line: int, status: str, code: str, cause: str, raw: str):
        self.line, self.status, self.code = line, status, code
        self.cause, self.raw = cause, raw


class Enum:
    __slots__ = ("line", "status", "code", "text")

    def __init__(self, line: int, status: str, code: str, text: str):
        self.line, self.status, self.code, self.text = line, status, code, text


def split_fences(text: str) -> Tuple[List[Tuple[int, str]], List[Tuple[int, str]]]:
    """Return (in_block_lines, prose_lines) as (1-indexed line, raw)."""
    inside: List[Tuple[int, str]] = []
    outside: List[Tuple[int, str]] = []
    in_fence = False
    for i, raw in enumerate(text.splitlines(), 1):
        if FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        (inside if in_fence else outside).append((i, raw))
    return inside, outside


def block_arms(inside: List[Tuple[int, str]]) -> List[Arm]:
    """Refusal arms inside fenced blocks, each with its nearest cause label.

    The cause is the nearest preceding non-arm line that reads like a branch
    label. In this corpus's dispatch-tree style that is `+- Validate root
    entity hash`; in flatter blocks it is the preceding statement. Where no
    label is found the arm's own line stands as its cause, which is honest
    rather than empty.
    """
    arms: List[Arm] = []
    recent: List[str] = []
    for line, raw in inside:
        m = ARM_RE.search(raw)
        if m:
            cause = ""
            for cand in reversed(recent):
                lm = LABEL_RE.match(cand)
                if lm and not ARM_RE.search(cand):
                    cause = lm.group(1).strip()
                    break
            arms.append(Arm(line, m.group(1), m.group(2),
                            cause or raw.strip(), raw.strip()))
            recent.append(raw)
            continue
        bs = BARE_STATUS_RE.search(raw)
        if bs:
            cause = ""
            for cand in reversed(recent):
                lm = LABEL_RE.match(cand)
                if lm and not BARE_STATUS_RE.search(cand):
                    cause = lm.group(1).strip()
                    break
            arms.append(Arm(line, bs.group(1), "-",
                            cause or raw.strip(), raw.strip()))
        recent.append(raw)
        if len(recent) > 12:
            recent.pop(0)
    return arms


def prose_enums(outside: List[Tuple[int, str]]) -> List[Enum]:
    """`(status, code)` pairs stated in prose — table rows and sentences."""
    out: List[Enum] = []
    for line, raw in outside:
        if raw.lstrip().startswith("#"):
            continue
        seen = set()
        for m in ARM_RE.finditer(raw):
            if (m.group(1), m.group(2)) not in seen:
                seen.add((m.group(1), m.group(2)))
                out.append(Enum(line, m.group(1), m.group(2), raw.strip()))
        for m in REV_RE.finditer(raw):
            if (m.group(2), m.group(1)) not in seen:
                seen.add((m.group(2), m.group(1)))
                out.append(Enum(line, m.group(2), m.group(1), raw.strip()))
    return out


def prose_codes(outside: List[Tuple[int, str]]) -> set:
    """Every snake_case code token appearing anywhere outside a fence."""
    seen = set()
    for _line, raw in outside:
        for m in re.finditer(r"`([a-z][a-z0-9]*_[a-z0-9_]{2,})`", raw):
            seen.add(m.group(1))
        for m in ARM_RE.finditer(raw):
            seen.add(m.group(2))
        for m in REV_RE.finditer(raw):
            seen.add(m.group(1))
    return seen


def analyze_doc(text: str) -> Tuple[List[Arm], List[Enum], List[Tuple[str, Arm, str]]]:
    inside, outside = split_fences(text)
    arms = block_arms(inside)
    enums = prose_enums(outside)
    pcodes = prose_codes(outside)

    beside: List[Tuple[str, Arm, str]] = []
    for a in arms:
        if a.code == "-":
            beside.append(("arm-names-no-code", a,
                           "arm emits %s with no code beside it — a reader "
                           "cannot key error handling off a status" % a.status))
            continue
        if a.code not in pcodes:
            beside.append(("code-not-enumerated", a,
                           "`%s` is assigned in a block and appears nowhere in "
                           "this document's prose — the enumeration a reader "
                           "consults does not carry it" % a.code))
            continue
        cw = _words(a.cause)
        if not cw:
            continue
        rows = [e for e in enums if e.code == a.code]
        if rows and not any(_words(e.text) & cw for e in rows):
            where = ", ".join(str(e.line) for e in rows[:3])
            beside.append(("arm-cause-unmatched", a,
                           "`%s` is enumerated (line %s) but no enumerated row "
                           "shares vocabulary with this arm's cause — check the "
                           "class list has a row for THIS cause" % (a.code, where)))
    return arms, enums, beside


def analyze(root: Path, only: Optional[str]):
    docs = []
    for d in _DIRS:
        base = root / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.md")):
            if only and only.lower() not in p.name.lower():
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            arms, enums, beside = analyze_doc(text)
            if not arms and not enums:
                continue
            docs.append((str(p.relative_to(root)), arms, enums, beside))
    return docs


def run_check(root: Path, only: Optional[str], owed: bool, as_json: bool) -> int:
    docs = analyze(root, only)
    n_arms = sum(len(a) for _, a, _, _ in docs)
    n_enum = sum(len(e) for _, _, e, _ in docs)
    beside_all = [(d, r, a, why) for d, _, _, b in docs for (r, a, why) in b]

    if not docs:
        print("could-not-look: parsed no refusal arms or code enumerations "
              "under %s (root %s)" % (", ".join(_DIRS), root), file=sys.stderr)
        return 2

    if owed:
        for doc, rule, a, why in beside_all:
            print("%s:%d  %s  %s %s  [cause: %s]  %s"
                  % (doc, a.line, rule, a.status, a.code, a.cause[:60], why))
        return 0

    if as_json:
        print(json.dumps({
            "summary": {"documents": len(docs), "arms": n_arms,
                        "enumerated": n_enum, "beside": len(beside_all)},
            "beside": [{"doc": d, "rule": r, "line": a.line, "status": a.status,
                        "code": a.code, "cause": a.cause, "why": why}
                       for d, r, a, why in beside_all],
        }, indent=2))
        return 0

    for doc, arms, enums, _ in docs:
        if not arms:
            continue
        print("\n%s  — %d arm(s) in blocks, %d enumerated pair(s) in prose"
              % (doc, len(arms), len(enums)))
        for a in arms:
            print("    %s:%-5d %3s %-28s  %s"
                  % (doc.split("/")[-1][:24], a.line, a.status, a.code,
                     a.cause[:56]))

    strong = [x for x in beside_all if x[1] != "arm-cause-unmatched"]
    weak = [x for x in beside_all if x[1] == "arm-cause-unmatched"]

    if strong:
        print("\n== a code driven by a block that its document's prose never "
              "carries ==")
        for doc, rule, a, why in strong:
            print("  %-22s %s:%d  %s %s — %s"
                  % (rule, doc, a.line, a.status, a.code, why))

    if weak:
        print("\n== CANDIDATES ONLY — an arm whose cause no enumerated row "
              "obviously covers ==")
        print("   ⚠ heuristic, false positives by construction. It compares "
              "WORDS, and a cause is prose.")
        print("   Read each one; the question it is asking is *does the class "
              "list have a row for THIS cause*.")
        for doc, _rule, a, why in weak:
            print("  %s:%d  %s %s  [cause: %s]"
                  % (doc, a.line, a.status, a.code, a.cause[:56]))

    print("\nscanned %d document(s), %d refusal arm(s) in blocks, %d "
          "(status, code) pair(s) in prose." % (len(docs), n_arms, n_enum))
    print("a block ASSIGNS a code; a table ENUMERATES the class. This reader "
          "puts them side by side and decides nothing.")
    print("it does NOT gate, and that is deliberate: the unit of the defect is "
          "the (cause, code) arm, and a cause is prose.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, help="corpus root (default: configured)")
    ap.add_argument("--doc", help="scope to documents whose name contains this")
    ap.add_argument("--owed", action="store_true",
                    help="the candidate list, one per line")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)
    return run_check(args.root or _CFG.corpus_dir, args.doc, args.owed, args.json)


if __name__ == "__main__":
    raise SystemExit(main())
