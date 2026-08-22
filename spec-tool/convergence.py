#!/usr/bin/env python3
"""convergence — how much is each spec still moving, and how far along the pipeline is it.

The maturity question has two halves with two different owners. **Architecture owns
one half and can measure it today: how much a spec is still changing.** The other
half — is it implemented, generated, used — is owned by the repos that do those
things, and arch's job is to aggregate what they report, not to assert it.

This command measures arch's half from git and declares a slot for the rest, so the
pipeline is visible with honest holes rather than invisible until it is complete.

    spec convergence [--root PATH] [--window N] [--json] [--stages]

**The pipeline** (`[maturity] stages` in config) is this project's standard sequence:

    spec  ->  core reference peers  ->  generators  ->  community

Each stage after `spec` names a source file that the owning repo publishes. Nothing
publishes one yet, so those stages report **unreported** — which is the point. A
column that is absent reads as a question nobody asked; a column that says
`unreported` reads as a question with no answer yet, which is the true state.

**Rate of change, not a hand-set flag.** The current maturity doc carries a
trajectory flag (stable / active / volatile) set by hand. This derives it:

    settling   no change in the settle window
    active     changing, but not in the last active window
    volatile   changed within the active window

The thresholds are config, not code, because "settled" means something different for
a corpus nine days from a release than for one a year in.

**Git is the source and its absence is reported, not guessed.** `check-podman`
bind-mounts a corpus read-only with no `.git`; there the honest answer is
**unmeasured**, distinct from "measured, zero commits". Collapsing those two is the
same defect this toolkit exists against, one axis over.

Stdlib-only. `git` is invoked through `subprocess` — the first use of it in this
package, and confined to this module.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import config as _config

_CFG = _config.load()
_M = _CFG._d.get("maturity", {}) if hasattr(_CFG, "_d") else {}

SCOPE = _M.get("scope", "naming-surface")
WINDOW = int(_M.get("window_days", 90))
ACTIVE_DAYS = int(_M.get("active_days", 14))
SETTLE_DAYS = int(_M.get("settle_days", 60))
STAGES: List[dict] = list(_M.get("stages", []) or [])

UNMEASURED = "unmeasured"   # we could not look
UNREPORTED = "unreported"   # nobody has published this yet


def _today() -> date:
    """Today, honouring SOURCE_DATE_EPOCH so a run is reproducible in a build."""
    sde = os.environ.get("SOURCE_DATE_EPOCH")
    if sde and sde.isdigit():
        return datetime.fromtimestamp(int(sde), timezone.utc).date()
    return datetime.now(timezone.utc).date()


def _git(root: Path, *args: str) -> Optional[str]:
    """Run git in `root`; None if git is unavailable or this is not a repo."""
    try:
        p = subprocess.run(["git", "-C", str(root), *args],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0:
        return None
    return p.stdout


def repo_is_measurable(root: Path) -> bool:
    return _git(root, "rev-parse", "--git-dir") is not None


def header_field(text: str, name: str) -> Optional[str]:
    """`**Version**: 1.2` / `**Status**: Active` from the doc header."""
    needle = "**%s**" % name
    for line in text.splitlines()[:40]:
        s = line.strip()
        if s.lower().startswith(needle.lower()):
            _, _, rest = s.partition(":")
            return rest.strip().split()[0] if rest.strip() else None
    return None


class Row:
    __slots__ = ("path", "version", "status", "last", "days", "commits",
                 "recent", "trajectory", "stages")

    def __init__(self, path: str):
        self.path = path
        self.version = self.status = None
        self.last = None
        self.days = None
        self.commits = None
        self.recent = None
        self.trajectory = UNMEASURED
        self.stages: Dict[str, str] = {}

    def as_dict(self) -> dict:
        return {
            "path": self.path, "version": self.version, "status": self.status,
            "last_change": self.last, "days_since": self.days,
            "commits_in_window": self.commits, "commits_recent": self.recent,
            "trajectory": self.trajectory, "stages": self.stages,
        }


def measure(root: Path, paths: List[Path], window: int) -> List[Row]:
    measurable = repo_is_measurable(root)
    today = _today()
    since = "%d days ago" % window
    rows: List[Row] = []

    for p in paths:
        try:
            rel = str(p.relative_to(root))
        except ValueError:
            rel = str(p)
        r = Row(rel)

        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            r.version = header_field(text, "Version")
            r.status = header_field(text, "Status")
        except Exception:  # noqa: BLE001
            pass

        # Every stage after `spec` is someone else's to report. None of them
        # publish a source yet; say so per stage rather than omitting the column.
        for st in STAGES:
            if st.get("name") == "spec":
                continue
            src = st.get("source")
            r.stages[st["name"]] = UNREPORTED if not src or not (root / src).exists() \
                else "declared"

        if not measurable:
            rows.append(r)
            continue

        out = _git(root, "log", "--format=%cs", "--since", since, "--", rel)
        alltime = _git(root, "log", "-1", "--format=%cs", "--", rel)
        if out is None or alltime is None:
            rows.append(r)
            continue

        dates = [d for d in out.split() if d]
        r.commits = len(dates)
        r.last = alltime.strip() or None
        if r.last:
            try:
                r.days = (today - date.fromisoformat(r.last)).days
            except ValueError:
                r.days = None
        r.recent = sum(1 for d in dates
                       if _age(d, today) is not None and _age(d, today) <= ACTIVE_DAYS)

        # Recency alone is not the signal, and using it alone was the first
        # version's bug: on a corpus imported wholesale at the release commit,
        # "last changed 53 days ago, 1 commit ever" is UNTOUCHED, and reading it
        # as `active` because 53 < settle_days told us nothing about 40 files at
        # once. Rate and recency are different questions and both are needed:
        # how recently did it move, and has it been moving.
        if r.days is None:
            r.trajectory = UNMEASURED
        elif r.days <= ACTIVE_DAYS:
            r.trajectory = "volatile"
        elif (r.commits or 0) >= 2:
            r.trajectory = "active"
        else:
            r.trajectory = "settling"
        rows.append(r)

    return rows


def _age(d: str, today: date) -> Optional[int]:
    try:
        return (today - date.fromisoformat(d)).days
    except ValueError:
        return None


def run(root: Path, window: int, as_json: bool, show_stages: bool) -> int:
    scope = _CFG.scope(SCOPE)
    paths = scope.find_markdown()
    if not paths:
        print("no documents under: %s" % scope.root, file=sys.stderr)
        print("  scanned 0 files — this is not a measurement, it is a run that did"
              " not look.", file=sys.stderr)
        return 2

    rows = measure(root, paths, window)
    measurable = repo_is_measurable(root)

    if as_json:
        print(json.dumps({
            "measured": measurable,
            "as_of": _today().isoformat(),
            "window_days": window,
            "active_days": ACTIVE_DAYS,
            "settle_days": SETTLE_DAYS,
            "pipeline": [s.get("name") for s in STAGES],
            "documents": [r.as_dict() for r in rows],
        }, indent=2))
        return 0

    if not measurable:
        print("git is unavailable or %s is not a repository." % root)
        print("Rate of change is UNMEASURED — not zero. Header fields below are still read.\n")

    print("spec convergence — as of %s · window %dd · volatile <=%dd · settling >%dd"
          % (_today().isoformat(), window, ACTIVE_DAYS, SETTLE_DAYS))
    print("  %-52s %-7s %-9s %-10s %5s %5s  %s"
          % ("document", "ver", "status", "trajectory", "chg", "recent", "last"))
    # Most-recently-moved first: a roadmap reader wants the moving edge at the
    # top, not the settled tail.
    for r in sorted(rows, key=lambda x: (x.days is None, x.days or 0, x.path)):
        print("  %-52s %-7s %-9s %-10s %5s %5s  %s"
              % (r.path[:52], r.version or "-", (r.status or "-")[:9], r.trajectory,
                 "-" if r.commits is None else r.commits,
                 "-" if r.recent is None else r.recent, r.last or "-"))

    if measurable:
        buckets: Dict[str, int] = {}
        for r in rows:
            buckets[r.trajectory] = buckets.get(r.trajectory, 0) + 1
        print("\n  %d documents — %s" % (
            len(rows), " · ".join("%s %d" % (k, buckets[k]) for k in sorted(buckets))))

    if show_stages or True:
        print("\npipeline (this project's standard sequence)")
        for st in STAGES:
            name = st.get("name", "?")
            if name == "spec":
                state = "measured here" if measurable else UNMEASURED
            else:
                src = st.get("source")
                state = "declared: %s" % src if src and (root / src).exists() else UNREPORTED
            print("  %-22s %-28s %s" % (name, state, st.get("owner", "-")))
        print("\n  `unreported` is not `absent`: the stage exists and nobody has"
              " published a source for it yet.")
        print("  Arch measures the spec stage. Every later stage is reported by the"
              " repo that owns it.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=None,
                    help="corpus root (default: the resolved corpus)")
    ap.add_argument("--window", type=int, default=WINDOW,
                    help="commit-count window in days (default %d)" % WINDOW)
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--stages", action="store_true", help="(always shown)")
    args = ap.parse_args(argv)
    return run(args.root or _CFG.repo_root, args.window, args.json, args.stages)


if __name__ == "__main__":
    raise SystemExit(main())
