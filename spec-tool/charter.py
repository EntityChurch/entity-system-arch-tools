#!/usr/bin/env python3
"""charter — the discipline set stated in two homes, checked against itself.

    spec charter [--charter PATH] [--agents PATH] [--json]

Why it exists. This ecosystem's methodology ratchet has one law: **"if it didn't
land in the charter, it didn't land."** The discipline set is therefore written
down twice — `docs/DISCIPLINE-CHARTER.md` carries the table that declares itself
the canonical home, and `AGENTS.md` carries a summary line that is always in an
agent's context. **Neither document says it is a copy of the other**, so a reader
of either sees a flat list with no pointer, and a divergence between them is
invisible from both. That is the corpus's own L23 fourth shape, pointed at the
two documents that define L23.

**The drift is measured, not hypothetical, and it has recurred four times.**
Twice the charter was a full release behind `AGENTS.md`; the third time nine
rules including six RATIFIED ones had never reached it at all, for twelve days;
the fourth time four rows were stale two days after the third was fixed. **Every
one was found by someone who happened to be editing the file for an unrelated
reason.** The remedy each time was a habit — *"the rows land the same session the
rule is earned"* — which is the same habit that had just failed, restated as a
resolution. A discipline whose enforcement point is *remember to do it* is the
theater the ladder forbids, and the ladder had not been applied to the document
that contains it.

**The gate found a fifth instance on its first run, in the other direction:**
`AGENTS.md`'s summary line read `(candidate)` for a rule its own body section
below had ratified, and was missing two rules entirely. The charter was right and
the always-in-context document was wrong — which is the direction nobody was
watching, because the charter is the one declared canonical.

The rules:

  charter-status-divergence  A rule carries a different status in the two homes
                             (RATIFIED in one, CANDIDATE in the other). The
                             defect directly. Either the ratification did not
                             land in both places or one home is asserting a bar
                             the evidence has not met — and the ladder makes
                             that distinction load-bearing, since a candidate
                             may be honored but never claimed to generalize.

  charter-rule-missing       A rule is present in one home and absent from the
                             other. This is the twelve-day shape: `AGENTS.md`
                             grew L17–L25 and the canonical table did not, so
                             the document that answers *"what is the set?"* was
                             short by nine and said so with no hedge.

What it deliberately does NOT flag, and this is calibration rather than
laxity. **An unmarked rule in the summary line is not a claim about status.**
L1, L2, L4 and L5 carry no `(candidate)`/`(ratified)` marker there — they are
the founding set, ratified before the ladder existed and never annotated.
Firing on those would score four noise findings against three real ones on the
live corpus, and a gate whose majority output is noise gets switched off inside
a week (the `ledger` zero-count calibration, same trade). **So an absent marker
is UNMARKED, not CANDIDATE**, and it is reported in the summary count so a
silent set is visible: an unmarked rule is unguarded on the status axis, which
is a fact about coverage rather than a violation.

Nor does it check that the two homes' **prose** agrees. The charter row is one
line and `AGENTS.md` carries the worked forms; requiring them to match would
force the charter to grow the body sections it deliberately does not have. The
checkable property is the **status and the membership**, which is exactly what
the ratchet's law is about.

Stdlib-only Python 3.11+. Exit **0** clean, **1** violations, **2** could-not-
look — a run that parsed no rules out of a home has not passed, it has failed to
read, and the two are the same output otherwise.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import config as _config

_CFG = _config.load()
_A = _CFG.analyzer("charter")
_RULES: Dict[str, str] = _A.get("rules", {})
_CHARTER_DOC = _A.get("charter_doc", "docs/DISCIPLINE-CHARTER.md")
_AGENTS_DOC = _A.get("agents_doc", "AGENTS.md")

RATIFIED, CANDIDATE, UNMARKED = "RATIFIED", "CANDIDATE", "UNMARKED"

# `| **L18** | rule text | draft | **RATIFIED** 2026-09-02 — second shape |`
# Anchored to line start so an `L18` cited inside a note's prose is not read as
# a table row. The status is the LAST cell.
CHARTER_ROW_RE = re.compile(r"^\|\s*\*\*L(\d+)\*\*\s*\|.*\|\s*([^|]*?)\s*\|\s*$", re.M)

# The summary bullet in `AGENTS.md` — a single run of `**L{n}** … *(status)*`
# separated by `·`. It is found by its first member rather than by a heading,
# because the file has no heading for it.
#
# Anchoring on **any** `L{n}` rather than on `L1` specifically: an anchor keyed
# to one rule number stops matching the day the set is renumbered or the bullet
# is reordered, and a parse that matches nothing is indistinguishable from a
# document with no disagreements. That is the `unscanned reads as zero` family
# this toolkit is built against, and it is the defect the self-test's negative
# controls found in this module's own first draft.
AGENTS_ANCHOR_RE = re.compile(r"^- \*\*L\d+\*\*", re.M)

# `*(**ratified** 2026-08-17 — …)*` / `*(candidate)*`. Non-greedy to the first
# closing paren: a marker never contains one.
MARKER_RE = re.compile(r"\*\(([^)]*?)\)\*")


class Finding:
    __slots__ = ("rule", "line", "text")

    def __init__(self, rule: str, line: int, text: str):
        self.rule = rule
        self.line = line
        self.text = text

    def severity(self) -> str:
        return _RULES.get(self.rule, "error")


def _status_of(blob: str) -> str:
    """Normalize a status cell or marker to one of the three states.

    `RATIFIED` wins over `CANDIDATE` when both words appear, because the
    corpus's own idiom for a promotion is to strike the old word and keep it
    visible — `~~Candidate: one incident.~~ **Ratified 2026-08-23 …**`.
    Reading that as CANDIDATE would invert the finding.
    """
    low = blob.lower()
    if "ratified" in low:
        return RATIFIED
    if "candidate" in low:
        return CANDIDATE
    return UNMARKED


def parse_charter(text: str) -> Dict[int, Tuple[str, int]]:
    """`{L-number: (status, line)}` from the canonical table."""
    out: Dict[int, Tuple[str, int]] = {}
    for m in CHARTER_ROW_RE.finditer(text):
        n = int(m.group(1))
        # First row wins: the table is the declaration; a later mention of the
        # same rule in a note is commentary on it.
        if n not in out:
            out[n] = (_status_of(m.group(2)), text[:m.start()].count("\n") + 1)
    return out


def parse_agents(text: str) -> Dict[int, Tuple[str, int]]:
    """`{L-number: (status, line)}` from the summary bullet.

    The bullet's extent is from its first member to the first top-level entry
    that follows it. Splitting on the `**L{n}**` markers themselves means a rule
    whose text runs to several lines is still attributed correctly — the earlier
    approach of a fixed look-ahead window silently truncated the longest
    entries, which is the failure mode this module exists to catch.
    """
    am = AGENTS_ANCHOR_RE.search(text)
    if am is None:
        return {}
    i = am.start()
    # The bullet ends at the first following line starting a new top-level item.
    m = re.compile(r"^- \*\*(?!L\d+\*\*)", re.M).search(text, am.end())
    seg = text[i:m.start()] if m else text[i:]
    base = text[:i].count("\n") + 1

    out: Dict[int, Tuple[str, int]] = {}
    parts = re.split(r"\*\*L(\d+)\*\*", seg)
    # parts = [pre, num, body, num, body, ...]
    consumed = parts[0]
    for k in range(1, len(parts), 2):
        n, body = int(parts[k]), parts[k + 1]
        if n not in out:
            out[n] = (_status_of("".join(MARKER_RE.findall(body))),
                      base + consumed.count("\n"))
        consumed += "**L%d**" % n + body
    return out


def analyze(charter: Dict[int, Tuple[str, int]],
            agents: Dict[int, Tuple[str, int]]) -> List[Tuple[str, Finding]]:
    out: List[Tuple[str, Finding]] = []
    for n in sorted(set(charter) | set(agents)):
        c, a = charter.get(n), agents.get(n)
        if c is None:
            out.append((_AGENTS_DOC, Finding(
                "charter-rule-missing", a[1],
                "L%d is in %s and absent from the canonical table (%s) — "
                "the ratchet's law is that it did not land"
                % (n, _AGENTS_DOC, _CHARTER_DOC))))
            continue
        if a is None:
            out.append((_CHARTER_DOC, Finding(
                "charter-rule-missing", c[1],
                "L%d is in the canonical table and absent from %s's summary — "
                "agents carry the summary in context and will not see it"
                % (n, _AGENTS_DOC))))
            continue
        # UNMARKED is not a status claim; see the module docstring.
        if UNMARKED in (c[0], a[0]) or c[0] == a[0]:
            continue
        out.append((_CHARTER_DOC, Finding(
            "charter-status-divergence", c[1],
            "L%d is %s in %s and %s in %s" % (n, c[0], _CHARTER_DOC, a[0], _AGENTS_DOC))))
    return out


def run_check(root: Path, charter_path: Optional[Path],
              agents_path: Optional[Path], as_json: bool) -> int:
    cp = charter_path or (root / _CHARTER_DOC)
    ap = agents_path or (root / _AGENTS_DOC)

    missing = [str(p) for p in (cp, ap) if not p.is_file()]
    if missing:
        print("could-not-look: %s" % ", ".join(missing), file=sys.stderr)
        return 2

    charter = parse_charter(cp.read_text(encoding="utf-8"))
    agents = parse_agents(ap.read_text(encoding="utf-8"))

    # A home that parsed to nothing is could-not-look, never a clean run: a
    # reformatted table and a table with no disagreements produce the same
    # zero-finding output otherwise.
    empty = [str(p) for p, d in ((cp, charter), (ap, agents)) if not d]
    if empty:
        print("could-not-look: parsed 0 rules from %s" % ", ".join(empty), file=sys.stderr)
        return 2

    findings = analyze(charter, agents)
    n_err = sum(1 for _, f in findings if f.severity() == "error")
    n_unmarked = sum(1 for s, _ in agents.values() if s == UNMARKED)

    if as_json:
        report: Dict[str, list] = {}
        for doc, f in findings:
            report.setdefault(doc, []).append(
                {"rule": f.rule, "severity": f.severity(), "line": f.line, "text": f.text})
        print(json.dumps({"summary": {"errors": n_err,
                                      "charter_rules": len(charter),
                                      "agents_rules": len(agents),
                                      "unmarked": n_unmarked},
                          "findings": report}, indent=2))
        return 1 if n_err else 0

    by_doc: Dict[str, List[Finding]] = {}
    for doc, f in findings:
        by_doc.setdefault(doc, []).append(f)
    for doc in sorted(by_doc):
        print("\n%s  (%d finding)" % (doc, len(by_doc[doc])))
        for f in by_doc[doc]:
            print("  %-6s %-26s %s:%d  %s"
                  % (f.severity().upper(), f.rule, doc, f.line, f.text))

    # Both counts are part of the answer: equal totals with zero findings is the
    # only shape that means "the two homes agree", and the unmarked count says
    # how much of the set the status axis does not cover at all.
    print("\nscanned 2 home(s) — %d rule(s) in the canonical table, %d in %s's summary, "
          "%d unmarked — %d error(s)."
          % (len(charter), len(agents), _AGENTS_DOC, n_unmarked, n_err))
    return 1 if n_err else 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--charter", type=Path, help="path to DISCIPLINE-CHARTER.md")
    ap.add_argument("--agents", type=Path, help="path to AGENTS.md")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)
    return run_check(_CFG.corpus_dir, args.charter, args.agents, args.json)


if __name__ == "__main__":
    raise SystemExit(main())
