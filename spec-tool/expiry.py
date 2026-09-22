#!/usr/bin/env python3
"""expiry — a build-state row expires when the repo it measured moves.

**The defect this exists for, measured four times on one table.** A tracker row
that says *"OPEN — verified in their tree at `abc1234`"* is a **build-state
claim**, and a build-state claim expires exactly like one: it was true when
written, it stays plausible forever, and nothing about reading it reveals that
the tree moved on. On one publication-gate of four rows, **every row the author
could reach turned out to be CLOSED by the time anyone looked** — two found only
because an unrelated history rewrite invalidated a SHA by accident, and a third
found sixteen days late, having been fixed **the day after** the measurement
that declared it open.

The remedy written after the first two was a habit — *"re-measure a row at the
moment it is quoted"* — and the third row went stale under that habit. A habit
is not an enforcement point. **This is the enforcement point.**

**What it asserts, and the wording is the whole design.** Not *"this row is
wrong"* — the tool has no idea whether the item is open. It asserts **the row's
EVIDENCE has expired**: the commit it pins is no longer the owning repo's HEAD,
so whatever was read there is a statement about a tree that no longer exists.
The correct disposition of an expired row is **UNKNOWN, never OPEN and never
CLOSED**, and re-taking it is one `git log`.

**Six states, and keeping them apart is the whole design:**

- `expired`      — the row **still asserts an open state** and its freshest pin is
                   dead: either the owning repo has moved past it, or — the
                   stronger form — the pin resolves but is no longer reachable
                   from HEAD, meaning the history it was measured against was
                   rewritten. **THE FINDING**, and the only one that gates.
- `discharged`   — same dead evidence, but the row no longer claims anything.
                   Inert: nobody will act on it. **Not a finding, deliberately** —
                   gating it would make this permanently red, and a gate that is
                   always red teaches people to skip it.
- `current`      — the freshest pin IS the owning repo's HEAD.
- `unpinned`     — the row cites no commit anyone can resolve. **The backlog**,
                   held by a ratchet on pin coverage, never gated per-row.
- `unmeasurable` — the row DECLARES the tree is not readable from here (another
                   party's private tree). **Declared, never inferred** — an
                   inferred exemption cannot be told apart from a bug.
- `ambiguous`    — pins resolve but the row names no known repo, or several, so
                   there is no single tree to measure. **Not a credit and not a
                   finding: UNKNOWN.** This is the toolkit's fifth
                   `could-not-look wearing a verdict's clothes`, and the first one
                   designed out in advance rather than found in production.
**A CITATION IS NOT EVIDENCE, AND THIS MODULE CANNOT TELL THEM APART — so it no
longer says which one it found `[2026-09-09]`.** The gate reported of `P-3` that
*"the history **it was measured against** was rewritten."* `P-3` is arch-owned,
its claim is about arch's own corpus, and the pin it carries is quoted as prior
art: *"`entity-core-protocol` already did this cleanup at `75c0452`."* Every test
fired correctly and that sentence was still false — **a verdict wearing
could-not-look's clothes**, the inverse of the failure the docstring above was
written against, in the module written against it.

**The verdict was right and only its explanation was wrong**, which is why the
fix is one sentence and not a mechanism. `P-3` *does* assert OPEN, it *does*
carry no live pin, and re-taking it was worth doing — the backlog it claims was
`~25` and measured **58**. So the finding stays and the wording drops the claim
about what was measured: *the row carries no live pin, whatever that one was
cited for.*

***Two mechanisms were built for this first and both were wrong; the replay is
what showed it, and that is the transferable half.*** ① A suppressing
`foreign-pin` state dropped `P-3` off `--owed` entirely — **it would have hidden
the true positive that started this.** ② Owner detection mapped `arch` to one
tree, so four rows whose evidence is arch's own fold landing in
`entity-core-protocol` (`FM-1a` @ `76dbd87`, `PD-1a` @ `ba2f5a3`) read as
somebody else's commit; **`arch` owns three repos** (`AGENTS.md`, *"This team's
repos — three, not one"*). Corrected, the detector then fired on **zero rows in
223** — because the row it was built for cites a repo arch *does* own, so the
discriminator never discriminated. **A mechanism that fires zero times is not an
enforcement point, it is a mistake being discharged by adding code** (`AGENTS.md`
L0 rule 4). It was deleted rather than shipped.

**Calibration note, and it is the toolkit's most-repeated lesson.** Three
analyzers here have shipped a matcher tuned to the spelling their author
expected rather than the corpus's actual vocabulary, and each reported a
confident wrong number (`0 of 97` where the truth was 2; `6` where a hand count
found 9; `0 of 210`). So this module matches a repo name **and** a commit
anywhere in the row rather than in a fixed position, takes the **freshest**
resolvable pin when a row carries several (rows routinely carry the original
finding's SHA and a later re-measurement's), and **hand-audit a sample before
publishing any count it produces.**
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

CLEAN, VIOLATIONS, CANNOT_LOOK = 0, 1, 2

# A markdown tracker row: `| **B-2** | …`. The id is the anchor a human cites.
ROW = re.compile(r"^\|\s*\*{0,2}~*\*{0,2}([A-Z]{1,4}-[0-9]+[a-z]?)\*{0,2}~*\*{0,2}\s*\|")

# A backticked hex run. Same window as `pins`: 7..40 is git's short-to-full
# range, and 64 is a sha256 content hash, deliberately outside it.
TOKEN = re.compile(r"`([0-9a-f]{7,40})`")

# Hex-shaped and never a commit. Extend as the corpus teaches; every entry
# should be a false positive somebody actually hit.
NOT_A_SHA = {"ed25519", "ed448", "deadbeef", "cafebabe", "feedface", "decade"}
BINARY_LITERAL = re.compile(r"0b[01]+$")

# The declared exemption. Matched case-insensitively on the row's own words,
# because the alternative — inferring "arch cannot read this tree" from the
# owner column — makes a permanent fact indistinguishable from a missing pin.
UNMEASURABLE = re.compile(r"not\s+measurable\s+from\s+here", re.I)

# Does the row still ASSERT something about the other tree?
#
# **This filter is the difference between a gate and noise, and the first cut of
# this module did not have it.** A pin is `current` only while it is literally
# the owning repo's HEAD, so "the repo moved past the pin" fires on almost every
# pinned row that exists — the first run reported `10 expired · 0 current`, which
# is not a worklist, it is a permanent red. **A gate that is always red teaches
# people to ignore it**, which is the failure this toolkit was built against.
#
# An expired pin under a row that says CLOSED costs nothing: the claim is
# discharged and nobody will act on its evidence again. The damage is done by a
# row that **still reads OPEN** on evidence from a tree that has moved — which is
# exactly the measured incident: four publication-gate rows, every reachable one
# already fixed, one of them found sixteen days late having been closed the day
# after the measurement that declared it open.
CLOSED_STATE = re.compile(
    r"(?<!\bnot )\b(closed|resolved|discharged|landed|withdrawn|superseded|moot)\b|✅",
    re.I)
OPEN_STATE = re.compile(r"\bopen\b|\bowed\b|\bblocked\b|\bunconfirmed\b|⛔|⚠|⬜", re.I)

DEFAULT_LEDGER = "docs/COHORT-OPEN-ITEMS.md"
BASELINE = ".spec-expiry-baseline.json"


def git(root: Path, *args: str) -> Optional[str]:
    """Run git in `root`; None if git is unavailable or this is not a repo."""
    try:
        p = subprocess.run(["git", "-C", str(root), *args],
                           capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout.strip() if p.returncode == 0 else None


def is_repo(d: Path) -> bool:
    return (d / ".git").exists()


def never_a_sha(tok: str) -> bool:
    return tok in NOT_A_SHA or bool(BINARY_LITERAL.match(tok))


def resolve_in(repo: Path, tok: str) -> bool:
    return git(repo, "cat-file", "-e", "%s^{commit}" % tok) is not None


def ancestry(repo: Path, tok: str) -> str:
    """`"ancestor"` · `"orphaned"` · `"unknown"` — and the middle one is the point.

    **A pin that RESOLVES but is no longer reachable from HEAD is the strongest
    expiry signal there is**, not a weaker one: the history it was measured
    against has been rewritten or abandoned, so the tree that was read is gone in
    the most literal sense available. The first cut of this module folded that
    case into `ambiguous`/UNKNOWN — `could-not-look wearing a verdict's clothes`,
    **in the module whose own docstring claims to design that out**, and it was
    caught only by replaying the gate against the ledger state it was built for
    and finding it reported a clean 0.

    The case is not hypothetical and it is not rare. The one time anybody DID
    re-measure this ledger's publication gate, the trigger was exactly this: an
    unrelated history rewrite in the owning tree invalidated a row's evidence SHA
    by accident. **The accident that produced the only successful catch is the
    signal the first cut discarded.**

    `git()` collapses a non-zero exit to `None`, so `--is-ancestor` — which
    answers by exit code, 1 meaning *no* — cannot be read through it. It is run
    directly here.
    """
    try:
        p = subprocess.run(["git", "-C", str(repo), "merge-base",
                            "--is-ancestor", tok, "HEAD"],
                           capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if p.returncode == 0:
        return "ancestor"
    if p.returncode == 1:
        return "orphaned"
    return "unknown"


def commits_since(repo: Path, tok: str) -> Optional[int]:
    """How far `repo`'s HEAD has moved past an ANCESTOR pin. 0 means it is HEAD."""
    out = git(repo, "rev-list", "--count", "%s..HEAD" % tok)
    if out is None:
        return None
    try:
        return int(out)
    except ValueError:
        return None


def known_repos(siblings: List[Path]) -> Dict[str, Path]:
    return {s.name: s for s in siblings if is_repo(s)}


CODE_SPAN = re.compile(r"`([^`]+)`")

# Short owner names the ledger uses beside full repo names, mapped to the tree
# each one means. Calibrated by counting the ledger's actual owner cells, not by
# guessing the spelling — the lesson `register`, `ledger` and `inbound` each paid
# for separately.
def repos_named(line: str, names: List[str]) -> List[str]:
    """Repos the row names, as WHOLE backticked tokens. Substrings do not count.

    **A plain substring search gets this wrong on real rows and the failure is
    silent.** One publication-gate row names its owner `entity-browser-rust` and
    also quotes a site identifier, `site:entity-core-protocol-main` — which
    contains `entity-core-protocol`, a real repository in this checkout. A
    substring match therefore reports *"names 2 known repositories"* and drops
    the row into UNKNOWN, so **the single row this whole module was built for was
    the one row it could not classify.** Caught by replaying the gate against the
    ledger state it was built for, which is the only reason it is not shipping.

    House style backticks a repo name, so requiring a whole code span is both
    precise and true to the corpus's actual vocabulary rather than to the
    spelling a rule-writer expects — the calibration lesson three other analyzers
    here paid for.
    """
    known = set(names)
    found: List[str] = []
    for span in CODE_SPAN.findall(line):
        if span in known and span not in found:
            found.append(span)
    return found


def classify(line: str, repos: Dict[str, Path]) -> dict:
    """One row → one verdict. Every branch names why, so a reader can argue."""
    named = repos_named(line, list(repos))
    toks = [t for t in TOKEN.findall(line) if not never_a_sha(t)]

    if UNMEASURABLE.search(line):
        return {"state": "unmeasurable",
                "why": "the row declares this tree is not readable from here"}

    if not toks:
        return {"state": "unpinned",
                "why": "cites no commit — the claim rests on a date, and a date "
                       "does not say which tree was read"}

    if len(named) != 1:
        return {"state": "ambiguous", "repos": named,
                "why": "names %d known repositories, so there is no single tree "
                       "to measure against. UNKNOWN, never a pass" % len(named)}

    name = named[0]
    repo = repos[name]
    resolvable = [t for t in toks if resolve_in(repo, t)]
    if not resolvable:
        return {"state": "unpinned", "repo": name,
                "why": "no cited token resolves to a commit in %s" % name}

    asserting_open = bool(OPEN_STATE.search(line)) and not CLOSED_STATE.search(line)

    # A row routinely carries the original finding's SHA and a later
    # re-measurement's. The FRESHEST is the one the row's current claim rests
    # on, so the smallest distance to HEAD is the honest reading.
    anc = {t: ancestry(repo, t) for t in resolvable}
    dists = [(d, t) for t in resolvable if anc[t] == "ancestor"
             and (d := commits_since(repo, t)) is not None]

    if not dists:
        # Every pin resolves and none is reachable from HEAD. See `ancestry`:
        # this is MORE expired than a moved-ahead pin, never less.
        orphans = [t for t in resolvable if anc[t] == "orphaned"]
        if orphans and asserting_open:
            return {"state": "expired", "repo": name, "pin": orphans[0],
                    "behind": None, "orphaned": True,
                    "why": "still reads OPEN, and `%s` — its freshest resolvable "
                           "pin, in %s — is NOT reachable from that repo's HEAD, "
                           "so the history it names was rewritten or abandoned. "
                           "**The row carries no live pin, whatever that one was "
                           "cited for**" % (orphans[0], name)}
        if orphans:
            return {"state": "discharged", "repo": name, "pin": orphans[0],
                    "orphaned": True,
                    "why": "pin is unreachable from %s's HEAD, but the row no "
                           "longer asserts an open state" % name}
        return {"state": "ambiguous", "repos": named, "pins": resolvable,
                "why": "pins resolve in %s but git cannot answer their ancestry "
                       "— UNKNOWN, never a pass" % name}

    dist, tok = min(dists)
    if dist == 0:
        return {"state": "current", "repo": name, "pin": tok, "behind": 0,
                "why": "the pin is %s's HEAD" % name}

    # The repo has moved. Whether that MATTERS depends on what the row still
    # claims — see CLOSED_STATE. A discharged row's stale evidence is inert.
    if not asserting_open:
        return {"state": "discharged", "repo": name, "pin": tok, "behind": dist,
                "why": "%s has moved %d commit(s) past `%s`, but the row no "
                       "longer asserts an open state" % (name, dist, tok)}
    return {"state": "expired", "repo": name, "pin": tok, "behind": dist,
            "why": "still reads OPEN, and `%s` — its freshest resolvable pin, in "
                   "%s — is %d commit(s) behind that repo's HEAD. **The row "
                   "carries no live pin, whatever that one was cited for.** "
                   "UNKNOWN until re-taken" % (tok, name, dist)}


def scan(ledger: Path, repos: Dict[str, Path]) -> Tuple[int, dict]:
    if not ledger.is_file():
        return CANNOT_LOOK, {"error": "no ledger at %s — there is nothing to "
                                      "measure, which is not the same as clean" % ledger}
    if not repos:
        return CANNOT_LOOK, {"error": "no sibling repositories found — every row "
                                      "would report repo-missing, which would be a "
                                      "statement about this checkout, not the ledger"}

    rows: List[dict] = []
    seen: Dict[str, int] = {}
    for lineno, line in enumerate(ledger.read_text(encoding="utf-8",
                                                   errors="ignore").splitlines(), 1):
        m = ROW.match(line)
        if not m:
            continue
        rid = m.group(1)
        seen[rid] = seen.get(rid, 0) + 1
        v = classify(line, repos)
        v.update({"id": rid, "line": lineno})
        rows.append(v)

    # An id used by two different item sets in one file makes every citation of
    # it unresolvable by the reader — the same defect as a date-letter packet id,
    # and it is reported rather than deduplicated away.
    collisions = {k: n for k, n in seen.items() if n > 1}
    res = {"ledger": str(ledger), "rows": rows, "collisions": collisions,
           "repos": sorted(repos)}
    code = VIOLATIONS if any(r["state"] == "expired" for r in rows) else CLEAN
    return code, res


def counts(res: dict) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in res.get("rows", []):
        out[r["state"]] = out.get(r["state"], 0) + 1
    return out


def read_baseline(root: Path) -> Optional[dict]:
    f = root / BASELINE
    if not f.is_file():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def ratchet(old: Optional[dict], observed: int) -> Tuple[dict, bool]:
    """The floor RISES and never falls, so nobody re-baselines their way to green."""
    floor = (old or {}).get("pinned", 0)
    if observed >= floor:
        return {"pinned": observed}, True
    return {"pinned": floor}, False


def report(res: dict, gate: bool, root: Path) -> None:
    if "error" in res:
        print("could-not-look: %s" % res["error"])
        return
    c = counts(res)
    rows = res["rows"]

    for r in rows:
        if r["state"] == "expired":
            print("  EXPIRED  %-8s line %-5d %s" % (r["id"], r["line"], r["why"]))
    for r in rows:
        if r["state"] in ("ambiguous",):
            print("  UNKNOWN  %-8s line %-5d %s" % (r["id"], r["line"], r["why"]))

    if res["collisions"]:
        print("\nid(s) used by more than one row in this file — a citation of one "
              "cannot be resolved by a reader:")
        for k, n in sorted(res["collisions"].items()):
            print("    %s -> %d rows" % (k, n))

    total = len(rows)
    print("\n%d row(s) — %d EXPIRED (open, dead evidence) · %d discharged · "
          "%d current · %d unpinned · %d unmeasurable · %d ambiguous"
          % (total, c.get("expired", 0), c.get("discharged", 0),
             c.get("current", 0), c.get("unpinned", 0),
             c.get("unmeasurable", 0), c.get("ambiguous", 0)))
    pinned = c.get("expired", 0) + c.get("current", 0) + c.get("discharged", 0)
    base = read_baseline(root)
    if base is not None:
        print("pin coverage %d, floor %d — the floor only rises." % (pinned, base.get("pinned", 0)))
    print("an EXPIRED row is UNKNOWN, never open and never closed. Re-take it: "
          "one `git log` in the owning tree.")
    if not gate:
        print("reader mode — exits 0. Run with --gate to enforce.")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path.cwd(),
                    help="repo holding the ledger (default: cwd)")
    ap.add_argument("--ledger", type=Path, default=None,
                    help="the tracker to read (default: %s)" % DEFAULT_LEDGER)
    ap.add_argument("--sibling", action="append", type=Path, default=None,
                    help="a repo to measure rows against (repeatable; defaults "
                         "to --root's sibling directories)")
    ap.add_argument("--gate", action="store_true",
                    help="exit 1 on an expired row (default is reader mode)")
    ap.add_argument("--owed", action="store_true",
                    help="print expired row ids, one per line — the worklist")
    ap.add_argument("--update-baseline", action="store_true",
                    help="raise the pin-coverage floor; it refuses to lower one")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)

    root = args.root.resolve()
    ledger = args.ledger if args.ledger else root / DEFAULT_LEDGER
    sibs = args.sibling
    if sibs is None:
        sibs = ([d for d in sorted(root.parent.iterdir())
                 if d.is_dir()] if root.parent.is_dir() else [])
    repos = known_repos([Path(s).resolve() for s in sibs] + [root])

    code, res = scan(Path(ledger), repos)
    if code == CANNOT_LOOK:
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            report(res, args.gate, root)
        return CANNOT_LOOK

    if args.update_baseline:
        c = counts(res)
        new, raised = ratchet(read_baseline(root),
                              c.get("expired", 0) + c.get("current", 0)
                              + c.get("discharged", 0))
        (root / BASELINE).write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8")
        print("pin coverage floor %s %d" % ("raised to" if raised else "held at",
                                               new["pinned"]))
        return CLEAN

    if args.owed:
        for r in res["rows"]:
            if r["state"] == "expired":
                print(r["id"])
        return CLEAN

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        report(res, args.gate, root)
    return VIOLATIONS if (code == VIOLATIONS and args.gate) else CLEAN


if __name__ == "__main__":
    sys.exit(main())
