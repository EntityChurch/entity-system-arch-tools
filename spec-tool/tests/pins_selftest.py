#!/usr/bin/env python3
"""pins self-test — builds real git repos in a temp dir and asserts the contract.

Everything here is a git-level fact, so the fixtures are real repositories
rather than mocks: the whole point of the gate is *reachability from a branch*,
and a mock cannot be wrong about that in the way a repo can.

The invariant that earns most of this file is the **cross-repo** one. Resolving
a sibling's SHA against the citing repo reports a false clean; resolving it
against only the citing repo reports a false failure. Both mistakes were made by
hand before this gate existed, so both get a test.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pins  # noqa: E402

FAILURES = []


def ok(name, cond, extra=""):
    if cond:
        print("  ok   %s" % name)
    else:
        FAILURES.append(name)
        print("  FAIL %s %s" % (name, extra))


def g(d, *a):
    subprocess.run(["git", "-C", str(d), *a], check=True,
                   capture_output=True, text=True)


def mkrepo(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    g(d, "init", "-q", "-b", "master")
    g(d, "config", "user.email", "t@t")
    g(d, "config", "user.name", "t")


def commit(d: Path, msg: str, **files) -> str:
    for n, c in files.items():
        p = d / n.replace("__", "/")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(c, encoding="utf-8")
    g(d, "add", "-A")
    g(d, "commit", "-q", "-m", msg)
    return subprocess.run(["git", "-C", str(d), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def run(root, sibs=(), branch="master"):
    return pins.scan(Path(root), branch, [Path(s) for s in sibs])


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    home, sib = tmp / "home", tmp / "sib"
    mkrepo(home)
    mkrepo(sib)

    # sib: one public commit on master, one dev-only commit.
    sib_public = commit(sib, "public", **{"a.txt": "1"})
    g(sib, "checkout", "-q", "-b", "dev")
    sib_dev = commit(sib, "dev only", **{"a.txt": "2"})
    g(sib, "checkout", "-q", "master")

    # home: a public commit, then a dev-only one, plus the declared doc.
    home_public = commit(home, "public", **{"seed.txt": "x"})
    g(home, "checkout", "-q", "-b", "dev")

    print("looks_like_sha — the noise filter")
    ok("a seed of digits only is not a SHA", not pins.looks_like_sha("20260716"))
    ok("a hex word with no digit is not a SHA", not pins.looks_like_sha("deadbeef"))
    ok("ed25519 is a curve, not a commit", not pins.looks_like_sha("ed25519"))
    ok("a real short SHA passes", pins.looks_like_sha("c1b0708"))
    # EXTENSION-TREE §5 derives a bitmap position from the first 5 bits of a
    # hash and writes the literals in backticks; both were reported as commits.
    ok("a binary literal is not a SHA", not pins.looks_like_sha("0b11100"))
    ok("a longer binary literal is not a SHA either",
       not pins.looks_like_sha("0b11100011"))
    ok("the 0b rule does not eat a SHA that merely starts with 0b",
       pins.looks_like_sha("0b11100a3"))

    print("\nreachability — the core property")
    doc = "# D\n\nsee `%s` and `%s`.\n" % (home_public, sib_public)
    home_dev = commit(home, "docs", **{
        "CANONICAL-DOCS.toml": 'path = "D.md"\n', "D.md": doc})
    code, res = run(home, [sib])
    ok("a commit on master and a sibling's public commit both pass",
       code == pins.CLEAN and not res["findings"],
       "findings=%r" % res.get("findings"))

    print("\ncross-repo resolution — the mistake this gate exists to not make")
    doc = "# D\n\npinned at `%s`.\n" % sib_dev
    commit(home, "cite sibling dev", **{"D.md": doc})
    code, res = run(home, [sib])
    ok("a sibling's dev-only SHA is caught, and attributed to the SIBLING",
       code == pins.VIOLATIONS and len(res["findings"]) == 1
       and res["findings"][0]["rule"] == "pin-unreachable"
       and res["findings"][0]["repo"] == "sib",
       "got %r" % res.get("findings"))
    code, res = run(home, [])   # sibling withheld
    ok("without the sibling it is unresolvable, NOT silently clean",
       code == pins.VIOLATIONS
       and res["findings"][0]["rule"] == "pin-unresolvable",
       "got %r" % res.get("findings"))

    print("\ncontent hashes are the fix, never the finding")
    sha256 = "b5484e84dd2cddfa7d3cc8a041deba92cb29615aedb2180e31d8b6910ac5b648"
    commit(home, "content hash", **{"D.md": "# D\n\nartifact `%s`.\n" % sha256})
    code, res = run(home, [sib])
    ok("a 64-hex sha256 is never flagged",
       code == pins.CLEAN, "got %r" % res.get("findings"))

    print("\nscope is the keep-list, not the tree")
    commit(home, "undeclared file carries a dev SHA", **{
        "D.md": "# D\n\nclean.\n", "NOTDECLARED.md": "see `%s`\n" % sib_dev})
    code, res = run(home, [sib])
    ok("a dev SHA in an UNdeclared file is not a defect",
       code == pins.CLEAN and res["docs_scanned"] == 1,
       "scanned=%r findings=%r" % (res.get("docs_scanned"), res.get("findings")))

    print("\nthree-valued contract — scanning nothing is not passing")
    code, res = run(home, [sib], branch="no-such-branch")
    ok("an absent published branch is 2, not a wall of red",
       code == pins.CANNOT_LOOK and "error" in res, "got %d" % code)
    bare = tmp / "bare"
    bare.mkdir()
    code, res = run(bare)
    ok("a non-repo is 2", code == pins.CANNOT_LOOK)
    mkrepo(tmp / "nodecl")
    commit(tmp / "nodecl", "x", **{"f.md": "hi"})
    code, res = run(tmp / "nodecl")
    ok("a repo with no CANONICAL-DOCS.toml is 2 — the surface is undeclared",
       code == pins.CANNOT_LOOK, "got %d" % code)

print()
if FAILURES:
    print("FAILED: %d" % len(FAILURES))
    raise SystemExit(1)
print("pins self-test: all invariants hold")
