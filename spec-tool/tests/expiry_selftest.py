#!/usr/bin/env python3
"""expiry self-test — real repositories, both directions.

**Every assertion here exists because the module got it wrong first.** The three
`orphaned`/`substring`/`open-state` cases are not hypotheticals: each was found by
replaying the gate against the ledger state it was built for and finding a clean
0 where a known-stale row sat. A gate that reports clean on its own founding
incident is the failure this whole toolkit is written against, so the founding
incident is a fixture.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import expiry  # noqa: E402

FAILED = []


def check(cond, msg):
    if not cond:
        FAILED.append(msg)
        print("  FAIL %s" % msg)
    else:
        print("  ok   %s" % msg)


def run(cwd, *args):
    subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, check=True)


def commit(repo, name, body="x"):
    (repo / name).write_text(body, encoding="utf-8")
    run(repo, "git", "add", "-A")
    run(repo, "git", "-c", "user.name=t", "-c", "user.email=t@t",
        "commit", "-q", "-m", name)
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def make_repo(base, name):
    repo = base / name
    repo.mkdir(parents=True)
    run(repo, "git", "init", "-q")
    return repo


def main():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        # Two sibling repos, one of which will rewrite its history — which is
        # exactly what produced the only successful manual catch on the real
        # ledger, and exactly what the first cut of this module discarded.
        owner = make_repo(base, "entity-browser-rust")
        other = make_repo(base, "entity-core-protocol")
        first = commit(owner, "a.txt")
        commit(owner, "b.txt")
        other_first = commit(other, "a.txt")

        repos = expiry.known_repos([owner, other])
        check(set(repos) == {"entity-browser-rust", "entity-core-protocol"},
              "both sibling repos are discovered")

        # --- ancestry -----------------------------------------------------
        check(expiry.ancestry(owner, first) == "ancestor",
              "a pin still on the branch reads as an ancestor")
        head = subprocess.run(["git", "-C", str(owner), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        check(expiry.commits_since(owner, first) == 1,
              "distance to HEAD is counted, not guessed")
        check(expiry.commits_since(owner, head) == 0,
              "a pin that IS head reads as zero behind")

        # Rewrite history so `first` resolves but is unreachable — the case the
        # first cut folded into UNKNOWN and therefore never reported.
        run(owner, "git", "checkout", "-q", "--orphan", "rewritten")
        commit(owner, "c.txt")
        check(expiry.ancestry(owner, first) == "orphaned",
              "a resolvable pin off the current history reads as ORPHANED, not unknown")

        # --- repo attribution --------------------------------------------
        # The real B-2 row names its owner AND quotes `site:entity-core-protocol-main`,
        # which CONTAINS another repo's name. A substring match called that two
        # repos and dropped the one row the module exists for.
        line = ("| **B-2** | cross-site links 404. `site:entity-core-protocol-main` "
                "is symbolic | `entity-browser-rust` | **OPEN** at `%s` |" % first)
        check(expiry.repos_named(line, list(repos)) == ["entity-browser-rust"],
              "a repo name inside a longer backticked token is NOT a second repo")

        v = expiry.classify(line, repos)
        check(v["state"] == "expired",
              "an OPEN row on an orphaned pin is EXPIRED (the founding incident)")
        check(v.get("orphaned") is True, "and it is reported as orphaned, not as distance")

        # --- the verdict says only what the module can KNOW ----------------
        # `P-3`, 2026-09-09: an arch-owned row about arch's own corpus, citing
        # another repo's cleanup commit as PRIOR ART — *"entity-core-protocol
        # already did this cleanup at 75c0452"*. The row asserts OPEN and its one
        # resolvable pin is orphaned, so `expired` is correct and re-taking it was
        # worth doing (the backlog it claims was `~25` and measured 58). What was
        # WRONG was the explanation: *"the history IT WAS MEASURED AGAINST was
        # rewritten"* — a claim about which tree the row measured, which this
        # module has no way to establish. A citation and a measurement are the
        # same token to it.
        run(other, "git", "checkout", "-q", "--orphan", "rewritten")
        commit(other, "c.txt")
        cite = ("| **P-3** | arch's own surface carries commit pins. "
                "`entity-core-protocol` already did this cleanup at `%s` with the "
                "reasoning to reuse | **arch** | **OPEN.** Arch-owed, cheap |"
                % other_first)
        v = expiry.classify(cite, repos)
        check(v["state"] == "expired",
              "a cited-not-measured pin still EXPIRES — the finding is not suppressed")
        check("measured against" not in v["why"],
              "and the verdict does NOT claim what the row was measured against")
        check("whatever that one was cited for" in v["why"],
              "it states only what it knows: the row carries no live pin")

        # --- the open/closed filter ---------------------------------------
        closed = line.replace("**OPEN**", "**CLOSED**")
        check(expiry.classify(closed, repos)["state"] == "discharged",
              "the same dead evidence under a CLOSED row is discharged, not a finding")

        # A gate that fires on every pinned row is noise. A row whose repo has
        # merely moved on, while the row no longer claims anything, must not fire.
        moved = ("| **X-1** | thing | `entity-core-protocol` | **CLOSED** at `%s` |"
                 % expiry.git(other, "rev-parse", "--short", "HEAD~0"))
        check(expiry.classify(moved, repos)["state"] in ("current", "discharged"),
              "a closed row pinned at head does not fire")

        # --- the buckets that must never be silent ------------------------
        check(expiry.classify("| **Y-1** | no pin at all | `entity-browser-rust` | OPEN |",
                              repos)["state"] == "unpinned",
              "a row citing no commit is UNPINNED (backlog), not clean")
        two = ("| **Y-2** | x | `entity-browser-rust` `entity-core-protocol` | OPEN at `%s` |"
               % first)
        check(expiry.classify(two, repos)["state"] == "ambiguous",
              "a row naming two repos is UNKNOWN, never a pass")
        check(expiry.classify(
            "| **Y-3** | NOT MEASURABLE FROM HERE | devops | OPEN |",
            repos)["state"] == "unmeasurable",
              "the exemption is read from the row's own declaration")
        check(expiry.classify("| **Y-4** | x | devops | OPEN at `deadbeef` |",
                              repos)["state"] == "unpinned",
              "a hex-shaped non-SHA is not a pin")

        # --- the ratchet ---------------------------------------------------
        new, raised = expiry.ratchet({"pinned": 5}, 7)
        check(new["pinned"] == 7 and raised, "pin coverage floor rises")
        new, raised = expiry.ratchet({"pinned": 9}, 4)
        check(new["pinned"] == 9 and not raised,
              "the floor REFUSES to lower — no re-baselining to green")

        # --- could-not-look is exit 2, never a pass ------------------------
        code, res = expiry.scan(base / "nope.md", repos)
        check(code == expiry.CANNOT_LOOK and "error" in res,
              "a missing ledger is could-not-look, not clean")
        code, res = expiry.scan(base / "nope.md", {})
        check(code == expiry.CANNOT_LOOK, "no sibling repos is could-not-look")

        # --- id collisions --------------------------------------------------
        led = base / "L.md"
        led.write_text(
            "| **Z-1** | a | `entity-core-protocol` | OPEN |\n"
            "| **Z-1** | b | `entity-core-protocol` | OPEN |\n", encoding="utf-8")
        code, res = expiry.scan(led, repos)
        check(res["collisions"].get("Z-1") == 2,
              "an id used by two rows is reported, not deduplicated away")

    print()
    if FAILED:
        print("%d FAILURE(S)" % len(FAILED))
        return 1
    print("expiry selftest: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
