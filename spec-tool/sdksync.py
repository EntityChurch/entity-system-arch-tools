#!/usr/bin/env python3
"""sdksync — does the SDK tier still describe the specs it copied from?

    spec sdksync [--root DIR|FILE ...] [--json] [--update] [--unpinned]

An `SDK-*` spec is a **restatement**. It copies a schema out of an extension
spec so an SDK author has one document to read, and from that moment the copy
and the original are two artifacts with one meaning and no link between them.
Nothing in the toolkit compared them, because nothing could: `coherence` is
same-file by design, `address` checks that a citation *resolves* and not that
it is still *true*, and `standards` reads shape. A copy that silently stops
matching its source is invisible to all three.

**Measured, 2026-08-17:** 55 restated schema blocks across the three `SDK-*`
specs; **7** named the `system/` type they summarize. The first implementer to
build against the SDK tier read three sections and found four defects in them —
`SDK-OPERATIONS` §9's `list()` note, which returns nothing; the `events`
vocabulary, which produced subscriptions that are created, return an id, and
never fire; a `rate_limit` unit wrong by 60x; and a query result shape naming
fields the handler does not emit. **Three of the four failed silently.**

Not one of them was a hard question. Each was a copy whose original had moved,
or had never matched it, and nobody could tell because the copy did not say
what it was a copy *of*.

## The mechanism

A pin file — `specs/sdk/.sdk-source-map.json`, beside the specs it governs —
records, per restated block, which source span it was written against and a
digest of that span **as it read at pin time**. The gate re-derives the digest
and compares.

  sdk-source-moved      The pinned source span changed since this block was
                        written against it. **The block is not necessarily
                        wrong — it is unreviewed**, which is the state this
                        gate exists to make visible. Resolve by re-reading the
                        source, correcting the block if it drifted, then
                        `--update` to re-pin.

  sdk-source-missing    A pin names a source file or anchor that no longer
                        resolves. **A finding, never a skip** — a renamed type
                        makes a pattern-matching gate stop matching while the
                        run stays green, which is the same `unscanned reads as
                        zero` family `ledger` was built against.

  sdk-block-unpinned    A restated block with no pin. **Reported, and it does
                        NOT gate** — see below.

## Why `unpinned` does not gate

Because 48 of 55 blocks are unpinned today, and a gate whose first run is 48
reds is a gate the next contributor learns to skip. `AGENTS.md` names that
failure mode directly, and `.spec-baseline.json` already solved the same
problem the same way: hold the debt, gate the delta.

So `sdksync` gates on **`sdk-source-moved` and `sdk-source-missing` only** —
both of which mean *a pin that someone took the trouble to write is now stale*.
The unpinned count is printed on every run and is the number that ratchets
down. It is not a permanent red; it is a backlog with a visible size.

## What a pin is worth, stated honestly

A pin proves the source span is byte-identical to when a human last read it
against this block. **It does not prove the block was correct then.** Pinning a
block that already disagreed with its source records the disagreement. That is
why `--update` is explicit and never automatic: re-pinning is a claim that
someone looked.

Digest is over the **normalized** span (both edges stripped, blank lines
dropped), so a reflow or a reindent does not fire the gate while a word change
does.

**Changing `normalize()` invalidates every pin at once** — the digests are not
comparable across algorithm versions. That is a re-review, not a re-pin: run
`--update` only after deciding the mass-fire is the algorithm and not the
corpus.

Stdlib-only. Beside ledger.py, coherence.py.
"""

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import config as _config

PIN_RELPATH = "specs/sdk/.sdk-source-map.json"
DEFAULT_ROOTS = [Path("specs/sdk")]

RULES = {
    "sdk-source-moved": (
        "error",
        "the pinned source span changed; this restatement is unreviewed",
    ),
    "sdk-source-missing": (
        "error",
        "a pin names a source file or anchor that no longer resolves",
    ),
    "sdk-block-unpinned": (
        "warn",
        "a restated schema block with no recorded source",
    ),
}

# A restated block opens with `Name := {` — the same shape `coherence` keys on.
BLOCK_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9/_-]*)\s*:=\s*\{")
# An anchor may name a CDDL block in the source ...
SRC_BLOCK_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9/_-]*)\s*:=\s*\{")
# ... or a markdown heading, in which case the span runs to the next heading of
# the same or higher level.
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


class CouldNotLook(Exception):
    """Raised when the scope resolves to nothing — exit 2, never 0."""


@dataclass
class Finding:
    rule: str
    line: int
    text: str

    def severity(self) -> str:
        return RULES[self.rule][0]


def normalize(lines: List[str]) -> str:
    """Whitespace-insensitive, content-sensitive.

    A reflow of a source paragraph is not a semantic change to the schema the
    SDK copied, and firing on one trains the reader to `--update` without
    looking — which is precisely the habit that makes the pin worthless.

    **Both edges are stripped, not just the trailing one.** Indentation inside
    a CDDL block carries no meaning the SDK restates, so a reindent must stay
    quiet for the same reason a reflow does. The selftest caught this as a real
    defect in the first version of this function, which stripped only the
    right.
    """
    return "\n".join(t for ln in lines if (t := ln.strip()))


def digest(lines: List[str]) -> str:
    return "sha256:" + hashlib.sha256(
        normalize(lines).encode("utf-8")).hexdigest()[:32]


def span_for_anchor(text: str, anchor: str) -> Optional[List[str]]:
    """The source span an anchor names — a CDDL block or a heading section.

    Returns None when the anchor does not resolve, which the caller reports as
    `sdk-source-missing`. It never falls back to "the whole file": a digest
    over a whole spec would change on every unrelated edit, and a gate that
    fires on everything is read as a gate that fires on nothing.
    """
    lines = text.splitlines()

    for i, ln in enumerate(lines):
        m = SRC_BLOCK_RE.match(ln)
        if m and m.group(1) == anchor:
            depth, out = 0, []
            for ln2 in lines[i:]:
                out.append(ln2)
                depth += ln2.count("{") - ln2.count("}")
                if depth <= 0 and len(out) > 1:
                    break
            return out

    for i, ln in enumerate(lines):
        m = HEADING_RE.match(ln)
        if not m:
            continue
        level, title = len(m.group(1)), m.group(2).strip()
        if anchor not in title:
            continue
        out = [ln]
        for ln2 in lines[i + 1:]:
            m2 = HEADING_RE.match(ln2)
            if m2 and len(m2.group(1)) <= level:
                break
            out.append(ln2)
        return out

    return None


def spans_for(text: str, anchor) -> Optional[List[str]]:
    """One anchor or several, concatenated in the order given.

    A single SDK block routinely restates more than one source type —
    `SubscribeParams` carries both the request shape and the nested limits
    block, which live in two CDDL definitions. Pinning it to whichever one you
    picked first would leave the other unwatched while the run stayed green,
    which is the failure this gate exists to prevent, reintroduced one level
    down.
    """
    names = [anchor] if isinstance(anchor, str) else list(anchor)
    out: List[str] = []
    for a in names:
        span = span_for_anchor(text, a)
        if span is None:
            return None
        out.extend(span)
    return out


def blocks(text: str) -> List[Tuple[str, int]]:
    """(block name, 1-indexed line) for every restatement in an SDK spec."""
    return [(m.group(1), i + 1)
            for i, ln in enumerate(text.splitlines())
            if (m := BLOCK_RE.match(ln))]


def load_pins(corpus: Path) -> Dict[str, dict]:
    p = corpus / PIN_RELPATH
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8")).get("pins", {})


def key(sdk_rel: str, block: str) -> str:
    return "%s::%s" % (sdk_rel, block)


def analyze(sdk_rel: str, text: str, pins: Dict[str, dict],
            corpus: Path) -> List[Finding]:
    found: List[Finding] = []
    for name, line in blocks(text):
        pin = pins.get(key(sdk_rel, name))
        if pin is None:
            found.append(Finding("sdk-block-unpinned", line,
                                 "`%s` restates a schema with no recorded source"
                                 % name))
            continue
        src = corpus / pin["source"]
        if not src.exists():
            found.append(Finding("sdk-source-missing", line,
                                 "`%s` pins %s, which does not exist"
                                 % (name, pin["source"])))
            continue
        span = spans_for(src.read_text(encoding="utf-8"), pin["anchor"])
        if span is None:
            found.append(Finding("sdk-source-missing", line,
                                 "`%s` pins anchor `%s` in %s — not found "
                                 "(renamed? a rename is a finding, not a skip)"
                                 % (name, pin["anchor"], pin["source"])))
            continue
        now = digest(span)
        if now != pin.get("digest"):
            found.append(Finding("sdk-source-moved", line,
                                 "`%s` was written against %s `%s` @ %s; that "
                                 "span now digests %s — re-read it, correct "
                                 "this block if it drifted, then --update"
                                 % (name, pin["source"], pin["anchor"],
                                    pin.get("digest", "?"), now)))
    return found


def iter_sdk_specs(roots: List[Path], corpus: Path):
    out = []
    for r in roots:
        p = r if r.is_absolute() else corpus / r
        if p.is_file() and p.suffix == ".md":
            out.append(p)
        elif p.is_dir():
            out.extend(sorted(q for q in p.rglob("SDK-*.md")))
    return out


def do_update(roots: List[Path], corpus: Path) -> int:
    """Re-pin every resolvable pin. Explicit, never a side effect of a check.

    Only refreshes pins that already exist — it does not invent one for an
    unpinned block, because the mapping (which source span does this block
    restate?) is a judgment a human makes once and a machine cannot guess.
    """
    pinfile = corpus / PIN_RELPATH
    if not pinfile.exists():
        print("no pin file at %s — nothing to update" % PIN_RELPATH,
              file=sys.stderr)
        return 2
    doc = json.loads(pinfile.read_text(encoding="utf-8"))
    pins, moved = doc.get("pins", {}), 0
    for k, pin in pins.items():
        src = corpus / pin["source"]
        if not src.exists():
            continue
        span = spans_for(src.read_text(encoding="utf-8"), pin["anchor"])
        if span is None:
            continue
        d = digest(span)
        if d != pin.get("digest"):
            pin["digest"] = d
            moved += 1
    doc.setdefault("meta", {})["pins"] = len(pins)
    pinfile.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
    print("re-pinned %d of %d source span(s)" % (moved, len(pins)))
    return 0


def rel(p: Path, corpus: Path) -> str:
    try:
        return str(p.relative_to(corpus))
    except ValueError:
        return str(p)


def run_check(roots: List[Path], as_json: bool, show_unpinned: bool) -> int:
    corpus = _config.corpus_root()
    specs = iter_sdk_specs(roots, corpus)
    if not specs:
        print("could not look: no SDK-*.md under %s"
              % ", ".join(str(r) for r in roots), file=sys.stderr)
        return 2

    pins = load_pins(corpus)
    report: Dict[str, List[Finding]] = {}
    n_blocks = 0
    for s in specs:
        r = rel(s, corpus)
        text = s.read_text(encoding="utf-8")
        n_blocks += len(blocks(text))
        f = analyze(r, text, pins, corpus)
        if f:
            report[r] = f

    n_error = sum(1 for fs in report.values()
                  for x in fs if x.severity() == "error")
    n_unpinned = sum(1 for fs in report.values()
                     for x in fs if x.rule == "sdk-block-unpinned")

    if as_json:
        out = {rp: [{"rule": x.rule, "severity": x.severity(),
                     "line": x.line, "text": x.text} for x in fs]
               for rp, fs in report.items()}
        print(json.dumps({"summary": {"errors": n_error, "unpinned": n_unpinned,
                                      "blocks": n_blocks, "pins": len(pins),
                                      "scanned": len(specs)},
                          "findings": out}, indent=2))
        return 1 if n_error else 0

    for rp in sorted(report):
        shown = [x for x in report[rp]
                 if show_unpinned or x.rule != "sdk-block-unpinned"]
        if not shown:
            continue
        print("\n%s  (%d finding)" % (rp, len(shown)))
        for x in shown:
            print("  %-6s %-20s %s:%d  %s"
                  % (x.severity().upper(), x.rule, rp, x.line, x.text))

    # The block count is part of the answer for the same reason ledger prints
    # its claim count: 0 errors over 0 blocks is a pattern that stopped
    # matching, not a tier that came out clean.
    print("\nscanned %d SDK spec(s), %d restated block(s), %d pinned — "
          "%d error(s), %d unpinned."
          % (len(specs), n_blocks, len(pins), n_error, n_unpinned))
    if n_unpinned and not show_unpinned:
        print("unpinned blocks are a backlog, not a gate — list with --unpinned")
    return 1 if n_error else 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", action="append", type=Path,
                    help="SDK spec or a dir to search for SDK-*.md (repeatable)")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--unpinned", action="store_true",
                    help="list the unpinned-block backlog (non-gating)")
    ap.add_argument("--update", action="store_true",
                    help="re-pin existing pins after reviewing them")
    args = ap.parse_args(argv)
    roots = args.root or DEFAULT_ROOTS
    if args.update:
        return do_update(roots, _config.corpus_root())
    return run_check(roots, args.json, args.unpinned)


if __name__ == "__main__":
    raise SystemExit(main())
