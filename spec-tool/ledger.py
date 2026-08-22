#!/usr/bin/env python3
"""ledger — the declared-count gate for tracking documents.

Every other analyzer reads prose or artifacts against a *rule*. This one reads
a number a human wrote against the **directory it claims to describe**.

    spec ledger [--root DIR|FILE ...] [--json]

Why it exists. `docs/proposals/INDEX.md` states how many proposals are in each
state, in two forms — a section heading (`## 1. Active — 25 files (ext 14 ·
app 5 · process 6 · core 0)`) and a per-tier line (``**`active/extensions/` —
18**``). **The count drifted three times in one file, twice inside one day**,
and each time it drifted the same way: a proposal was moved between directories
and one of the several places stating a total was updated while another was
not. The file is the corpus's own answer to "what is in motion", so a wrong
number there is not cosmetic — it is the instrument reporting on itself.

**Nothing checked it, because a count is not a rule.** `standards` reads
headers, `style` reads names, `coherence` reads two normative artifacts against
each other — and `docs/` is outside all three scopes by design (proposals are
drafts; dated status docs are immutable snapshots that cannot be corrected, so
gating them would be a permanent red). A living ledger is neither: `INDEX.md`
says of itself *"Update on every state change"*. It is the one document in
`docs/` whose correctness is checkable by machine and whose drift is a defect.

The rules:

  declared-count-mismatch    A declared count disagrees with the number of
                             `.md` files under the directory it names. The
                             defect above, directly.

  declared-count-dangling    A declaration names a directory that does not
                             exist **and claims a non-zero count**. This is the
                             **`unscanned reads as zero`** family and it is why
                             the rule is not just an equality check: rename
                             `active/extensions/` and a pattern-matching gate
                             simply stops matching, so the count it used to
                             guard becomes unguarded and the run stays green.
                             **A declaration the gate cannot resolve is a
                             finding, never a skip** — when a tool reports on a
                             set, the set it actually read is part of the
                             answer.

                             The non-zero qualifier was **measured, not
                             assumed**. On this gate's first run against the
                             live corpus it scored 3 findings, and 2 were
                             ``**`active/core/` — 0**`` — a declared zero over
                             a directory git cannot track while it is empty,
                             where "0" and "absent" are the same observation.
                             That is consistent, not drifted. Two noise
                             findings out of three is the trade that gets a
                             gate switched off in a week, so a zero-count
                             declaration over an absent directory passes; it
                             was guarding nothing to begin with.

What it does NOT read, stated so a green run is not read as more than it is.
Only counts **anchored to a directory** are checkable: the backticked-path form
and the heading form whose state word names a directory (plus that heading's
parenthetical, via the configured aliases). A total written in prose with no
directory anchor — *"seventeen of them landed in a 13-day window"* — is
invisible here, and there are several. **This gate makes the anchored counts
true; it does not make the document true.**

Counting is `.md` files **recursively** under the named directory, which makes
the two forms agree by construction: `active/` counts 25 because
`active/extensions/` counts 14, `active/applications/` 5 and `active/process/`
6. No file is excluded — a ledger directory holds proposals and nothing else,
and a rule that quietly skipped a file would reintroduce the defect it exists
to catch.

Stdlib-only Python 3.11+. Exit **0** clean, **1** violations, **2** could-not-
look — a gate that scanned nothing has not passed.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import config as _config

_CFG = _config.load()
_LEDGER = _CFG.analyzer("ledger")
_RULES: Dict[str, str] = _LEDGER.get("rules", {})
_ALIASES: Dict[str, str] = _LEDGER.get("aliases", {})
_DOCUMENTS: List[str] = _LEDGER.get("documents", [])

DEFAULT_ROOTS = [(_CFG.corpus_dir / d) for d in _DOCUMENTS]

# ``**`active/extensions/` — 18**`` — a backticked relative path ending in `/`,
# then an em-dash (or hyphen), then the count. The trailing `/` is required: it
# is what distinguishes a directory being counted from a file being cited.
PATH_COUNT_RE = re.compile(r"`([A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*/)`\s*[—–-]\s*(\d+)")

# `## 1. Active — 25 files (ext 14 · app 5 · process 6 · core 0)` — the section
# heading. The state word is matched case-insensitively against a directory.
HEAD_COUNT_RE = re.compile(r"^#{1,6}\s*\d+[a-z]?\.\s*([A-Za-z][A-Za-z-]*)\s*[—–-]\s*(\d+)")

# `(ext 14 · app 5 · process 6 · core 0)` — the per-tier breakdown riding on a
# heading. Each token is resolved through `[analyzer.ledger.aliases]`.
PAREN_RE = re.compile(r"\(([^)]*)\)")
PAREN_ITEM_RE = re.compile(r"([A-Za-z][A-Za-z-]*)\s+(\d+)")


class Finding:
    __slots__ = ("rule", "line", "text")

    def __init__(self, rule: str, line: int, text: str):
        self.rule = rule
        self.line = line
        self.text = text

    def severity(self) -> str:
        return _RULES.get(self.rule, "error")


def count_md(directory: Path) -> int:
    """`.md` files under `directory`, recursively. See the module docstring on
    why nothing is excluded."""
    return sum(1 for _ in directory.rglob("*.md"))


def resolve(base: Path, name: str) -> Optional[Path]:
    p = (base / name).resolve()
    return p if p.is_dir() else None


def claims(text: str, base: Path) -> List[Tuple[int, str, str, int]]:
    """Every (line, raw-token, directory-name, declared-count) in the document.

    Extraction is separate from adjudication so the self-test can assert what
    was *seen* — a rule that silently sees nothing is the failure this module
    is named after.
    """
    out: List[Tuple[int, str, str, int]] = []
    for i, line in enumerate(text.splitlines(), 1):
        for m in PATH_COUNT_RE.finditer(line):
            out.append((i, m.group(1), m.group(1).rstrip("/"), int(m.group(2))))

        hm = HEAD_COUNT_RE.match(line)
        if not hm:
            continue
        word = hm.group(1).lower()
        # A heading whose word names no directory is prose, not a claim
        # ("## 4. Peer-implementation — MEASURED …" never matches the count
        # form anyway). Only an existing directory promotes it to a claim.
        if resolve(base, word) is None:
            continue
        out.append((i, hm.group(1), word, int(hm.group(2))))

        pm = PAREN_RE.search(line)
        if not pm:
            continue
        for im in PAREN_ITEM_RE.finditer(pm.group(1)):
            tier = _ALIASES.get(im.group(1).lower())
            if tier is None:
                continue
            out.append((i, "%s %s" % (im.group(1), im.group(2)),
                        "%s/%s" % (word, tier), int(im.group(2))))
    return out


def analyze(text: str, base: Path) -> List[Finding]:
    findings: List[Finding] = []
    for line, token, dirname, declared in claims(text, base):
        directory = resolve(base, dirname)
        if directory is None:
            # A declared ZERO over an absent directory is consistent, not
            # drifted — git does not track an empty directory, so "0" and
            # "not there" are the same observation. Calibrated against the
            # live corpus, where this shape was 2 of 3 findings: firing on it
            # would have made the gate mostly-noise on its first run, and a
            # gate that cries wolf is switched off within a week.
            if declared == 0:
                continue
            findings.append(Finding(
                "declared-count-dangling", line,
                "`%s` declares %d for `%s/`, which is not a directory — "
                "the count is unguarded, not satisfied (rename? moved?)"
                % (token, declared, dirname)))
            continue
        actual = count_md(directory)
        if actual != declared:
            findings.append(Finding(
                "declared-count-mismatch", line,
                "`%s` declares %d; `%s/` holds %d .md file(s) — "
                "the directory is the fact, the sentence is the copy"
                % (token, declared, dirname, actual)))
    return sorted(findings, key=lambda f: (f.line, f.rule))


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(Path.cwd()))
    except ValueError:
        return str(p)


def iter_docs(root: Path) -> List[Path]:
    if root.is_file():
        return [root] if root.suffix == ".md" else []
    if root.is_dir():
        return sorted(root.rglob("INDEX.md"))
    return []


def run_check(roots: List[Path], as_json: bool) -> int:
    docs: List[Tuple[Path, str]] = []
    for root in roots:
        for doc in iter_docs(root):
            try:
                docs.append((doc, doc.read_text(encoding="utf-8")))
            except Exception as exc:  # noqa: BLE001
                print("unreadable: %s: %s" % (rel(doc), exc), file=sys.stderr)

    if not docs:
        print("no ledger document found at: %s"
              % ", ".join(str(r) for r in roots), file=sys.stderr)
        print("  scanned 0 files — this is not a pass, it is a gate that did not look.",
              file=sys.stderr)
        print("  a repo with no `docs/proposals/INDEX.md` has nothing for this gate;"
              " that is why `ledger` is not part of `spec check`.", file=sys.stderr)
        return 2

    report: Dict[str, List[Finding]] = {}
    n_claims = 0
    for doc, text in docs:
        n_claims += len(claims(text, doc.parent))
        f = analyze(text, doc.parent)
        if f:
            report[rel(doc)] = f

    n_error = sum(1 for fs in report.values() for x in fs if x.severity() == "error")

    if as_json:
        out = {rp: [{"rule": x.rule, "severity": x.severity(), "line": x.line,
                     "text": x.text} for x in fs] for rp, fs in report.items()}
        print(json.dumps({"summary": {"errors": n_error, "files": len(report),
                                      "scanned": len(docs), "claims": n_claims},
                          "findings": out}, indent=2))
        return 1 if n_error else 0

    for rp in sorted(report):
        print("\n%s  (%d finding)" % (rp, len(report[rp])))
        for x in report[rp]:
            print("  %-6s %-24s %s:%d  %s"
                  % (x.severity().upper(), x.rule, rp, x.line, x.text))

    # The claim count is part of the answer: 0 findings over 0 claims is a
    # pattern that stopped matching, not a document that came out true.
    print("\nscanned %d ledger doc(s), %d anchored claim(s) — %d file(s) flagged, %d error(s)."
          % (len(docs), n_claims, len(report), n_error))
    return 1 if n_error else 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", action="append", type=Path,
                    help="ledger doc or a dir to search for INDEX.md (repeatable)")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)
    return run_check(args.root or DEFAULT_ROOTS, args.json)


if __name__ == "__main__":
    raise SystemExit(main())
