#!/usr/bin/env python3
"""convergence_selftest — invariants for the rate-of-change classifier.

Builds a throwaway git repo in a temp dir with commits at known ages, so the
classifier is pinned against real `git log` output rather than a mock of it —
the measurement path is the part that can be wrong.

Why this exists: the first version derived trajectory from **recency alone**, so
a corpus imported wholesale at a release commit read as `active` across forty
files at once ("last changed 53 days ago" < the 60-day settle window). Recency
and rate are different questions. That bug produced a plausible-looking table
that said nothing, which is the failure mode the whole maturity proposal is
about — a number that is present, wrong, and unchecked.

    python3 spec-tool/tests/convergence_selftest.py    # exits non-zero on failure

Stdlib-only. Skips cleanly if `git` is unavailable rather than reporting a pass.
"""
import os
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import convergence  # noqa: E402

FAILURES = []
RAN = []


def case(name, got, want):
    RAN.append(name)
    if got != want:
        FAILURES.append("%s: want %r, got %r" % (name, want, got))
        print("  FAIL %s (want %r, got %r)" % (name, want, got))
    else:
        print("  ok   %s" % name)


def have_git():
    try:
        return subprocess.run(["git", "--version"], capture_output=True).returncode == 0
    except OSError:
        return False


if not have_git():
    print("git unavailable — SKIPPING (this is a skip, not a pass)")
    sys.exit(0)


def commit(repo, path, day_offset, body):
    f = Path(repo) / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(body)
    when = (date.today() - timedelta(days=day_offset)).isoformat() + "T12:00:00"
    env = dict(os.environ,
               GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when,
               GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    subprocess.run(["git", "-C", repo, "add", path], check=True, capture_output=True)
    subprocess.run(["git", "-C", repo, "commit", "-m", "c", "--no-gpg-sign"],
                   check=True, capture_output=True, env=env)


HEADER = "# T\n\n**Version**: %s\n**Status**: %s\n\nbody %d\n"

with tempfile.TemporaryDirectory() as repo:
    subprocess.run(["git", "-C", repo, "init", "-q"], check=True, capture_output=True)

    # imported once at the release and never touched again — the 40-file case
    commit(repo, "settled.md", 53, HEADER % ("1.0", "Active", 1))
    # touched a while back, more than once — moving, but not now
    commit(repo, "active.md", 40, HEADER % ("1.1", "Active", 1))
    commit(repo, "active.md", 30, HEADER % ("1.2", "Active", 2))
    # changed within the active window
    commit(repo, "volatile.md", 20, HEADER % ("2.0", "Draft", 1))
    commit(repo, "volatile.md", 2, HEADER % ("2.1", "Draft", 2))

    root = Path(repo)
    paths = sorted(root.glob("*.md"))
    rows = {r.path: r for r in convergence.measure(root, paths, 90)}

    case("repo_is_measurable", convergence.repo_is_measurable(root), True)

    # THE REGRESSION. One commit, 53 days ago, inside the 60-day settle window:
    # recency alone called this `active`. It is untouched.
    case("imported_once_and_untouched_is_settling",
         rows["settled.md"].trajectory, "settling")
    case("settled_commit_count", rows["settled.md"].commits, 1)

    case("moving_but_not_recently_is_active", rows["active.md"].trajectory, "active")
    case("active_commit_count", rows["active.md"].commits, 2)
    case("active_has_no_recent_commits", rows["active.md"].recent, 0)

    case("changed_inside_the_window_is_volatile",
         rows["volatile.md"].trajectory, "volatile")
    case("volatile_recent_is_counted", rows["volatile.md"].recent, 1)

    # header fields are read independently of git
    case("reads_version_header", rows["volatile.md"].version, "2.1")
    case("reads_status_header", rows["volatile.md"].status, "Draft")

    # every stage after `spec` is someone else's to report, and none publish yet
    later = [s["name"] for s in convergence.STAGES if s["name"] != "spec"]
    case("pipeline_has_later_stages", len(later) >= 1, True)
    case("later_stages_are_unreported_not_absent",
         {rows["settled.md"].stages[n] for n in later}, {convergence.UNREPORTED})

# --- a directory that is not a repo is UNMEASURED, never "no changes" --------

with tempfile.TemporaryDirectory() as plain:
    p = Path(plain) / "x.md"
    p.write_text(HEADER % ("1.0", "Active", 1))
    case("non_repo_is_not_measurable", convergence.repo_is_measurable(Path(plain)), False)
    r = convergence.measure(Path(plain), [p], 90)[0]
    case("non_repo_trajectory_is_unmeasured", r.trajectory, convergence.UNMEASURED)
    case("non_repo_commits_is_none_not_zero", r.commits, None)
    case("non_repo_still_reads_headers", r.version, "1.0")


if FAILURES:
    print("\n%d failure(s):" % len(FAILURES))
    for f in FAILURES:
        print("  - %s" % f)
    sys.exit(1)
print("\n%d/%d invariants pass" % (len(RAN), len(RAN)))
