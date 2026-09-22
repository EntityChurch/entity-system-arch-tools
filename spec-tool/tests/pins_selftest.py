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


def commit_resolvable(d: Path, msg: str, **files) -> str:
    """A commit whose SHORT sha also passes the composition heuristic.

    Why this exists, and it is not a convenience: the unresolvable case is the
    one place composition still decides an outcome, because a token that
    resolves in no repository has no other evidence. About 1 short SHA in 26 is
    all-digits or all-hex-letters, so a fixture SHA landed there roughly one run
    in twenty and `pins` correctly classified a REAL commit as noise — the
    assertion below then failed for no visible reason.

    **The tool is right and the fixture was underspecified.** Amending until the
    short SHA is composition-passing states what the assertion is actually
    about (an unresolvable citation the gate CAN see) instead of re-rolling the
    dice until green. The dropped-as-noise residue is real, unavoidable without
    more information, and is now COUNTED AND REPORTED by `pins` rather than
    discarded silently — which is the half that was the actual defect.
    """
    sha = commit(d, msg, **files)
    for n in range(64):
        if pins.looks_like_sha(sha):
            return sha
        g(d, "commit", "-q", "--amend", "-m", "%s (%d)" % (msg, n))
        sha = subprocess.run(["git", "-C", str(d), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True).stdout.strip()
    raise AssertionError("could not mint a composition-passing short sha")


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    home, sib = tmp / "home", tmp / "sib"
    mkrepo(home)
    mkrepo(sib)

    # sib: one public commit on master, one dev-only commit.
    sib_public = commit(sib, "public", **{"a.txt": "1"})
    g(sib, "checkout", "-q", "-b", "dev")
    sib_dev = commit_resolvable(sib, "dev only", **{"a.txt": "2"})
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

    print("\nnoise is DROPPED but never SILENT")
    # The residue this counter exists for: a token that resolves nowhere and
    # fails composition is discarded, and until it was counted the run reported
    # its surface as fully measured. `20260716` is the honest case; a real short
    # SHA citing a repo nobody configured is the ~1-in-26 case that looks
    # identical from here. Reporting the count is what keeps "we did not look"
    # from reading as "there was nothing to see".
    commit(home, "seedy", **{"D.md": "# D\n\nseed `20260716` and `1000000`.\n"})
    code, res = run(home, [sib])
    ok("a seed resolving nowhere is not a finding",
       code == pins.CLEAN, "got %r" % res.get("findings"))
    ok("...and it is COUNTED as dropped noise, not silently discarded",
       res.get("noise_dropped", 0) >= 1, "noise_dropped=%r" % res.get("noise_dropped"))
    ok("dropped noise is excluded from tokens_considered",
       res["tokens_considered"] == 0, "considered=%r" % res["tokens_considered"])

    print("\ncontent hashes are the fix, never the finding")
    sha256 = "b5484e84dd2cddfa7d3cc8a041deba92cb29615aedb2180e31d8b6910ac5b648"
    commit(home, "content hash", **{"D.md": "# D\n\nartifact `%s`.\n" % sha256})
    code, res = run(home, [sib])
    ok("a 64-hex sha256 is never flagged",
       code == pins.CLEAN, "got %r" % res.get("findings"))

    print("\ncomposition is a noise filter, and it runs LAST")
    # The hole this closes: `looks_like_sha` requires both a digit and a hex
    # letter, on a docstring claim that a real hash failing that is "~1 in 10^8".
    # That is the figure for a FULL 40-char SHA; the corpus cites SHORT ones,
    # where the true rate is (10/16)^7 + (6/16)^7 — about 1 in 26. Applied
    # before resolution, it discarded real citations unread and called the
    # surface measured. It also made this very file flake at roughly that rate:
    # the fixtures build real repos, so ~1 run in 20 produced a rejected SHA.
    ok("an all-digit short SHA fails the composition heuristic",
       not pins.looks_like_sha("1234567"))
    ok("an all-letter short SHA fails it too",
       not pins.looks_like_sha("abcdefa"))
    ok("...but a NAMED hex word is excluded at any stage",
       pins.never_a_sha("deadbeef") and pins.never_a_sha("0b11100"))

    _real = pins.resolve_in
    try:
        # A token git CAN look up is a commit whatever it is made of. Forced
        # rather than generated, because a fixture cannot choose its own SHA.
        pins.resolve_in = lambda repo, tok: tok == "1234567" or _real(repo, tok)
        commit(home, "all-digit pin", **{
            "D.md": "# D\n\nsee `1234567`\n", "NOTDECLARED.md": "x\n"})
        code, res = run(home, [sib])
        ok("a resolvable all-digit SHA is NOT discarded as noise",
           any(f["sha"] == "1234567" for f in res["findings"]),
           "got %r" % res["findings"])
    finally:
        pins.resolve_in = _real

    # And the filter still does its job on what resolves nowhere.
    commit(home, "a seed is not a pin", **{
        "D.md": "# D\n\nseed `20260716`, count `1000000`\n"})
    code, res = run(home, [sib])
    ok("an unresolvable digits-only token is still suppressed",
       code == pins.CLEAN, "got %r" % res.get("findings"))

    print("\nscope is the keep-list, not the tree")
    commit(home, "undeclared file carries a dev SHA", **{
        "D.md": "# D\n\nclean.\n", "NOTDECLARED.md": "see `%s`\n" % sib_dev})
    code, res = run(home, [sib])
    ok("a dev SHA in an UNdeclared file is not a defect",
       code == pins.CLEAN and res["docs_scanned"] == 1,
       "scanned=%r findings=%r" % (res.get("docs_scanned"), res.get("findings")))

    print("\nkeep_tree — a declared DIRECTORY publishes, and must be scanned")
    # The defect this covers: `[[keep_tree]] path = "docs/proposals"` uses the
    # same key as a file declaration, so `is_file()` dropped it silently and the
    # gate reported clean over 169 unread published documents.
    commit(home, "declare a tree", **{
        "CANONICAL-DOCS.toml": 'path = "D.md"\npath = "tree"\n',
        "D.md": "# D\n\nclean.\n",
        "tree__a.md": "# A\n\npinned at `%s`.\n" % sib_dev,
        "tree__nested__b.md": "# B\n\nalso `%s`.\n" % sib_dev,
        "tree__archive__old.md": "# old\n\n`%s`\n" % sib_dev,
        "tree__notes.txt": "`%s`\n" % sib_dev})
    code, res = run(home, [sib])
    files = {f["file"] for f in res["findings"]}
    ok("a keep_tree directory is expanded, not skipped",
       code == pins.VIOLATIONS and "tree/a.md" in files,
       "scanned=%r findings=%r" % (res.get("docs_scanned"), res.get("findings")))
    ok("expansion is recursive", "tree/nested/b.md" in files, "got %r" % files)
    ok("dev-history dirs under a keep_tree stay out",
       "tree/archive/old.md" not in files, "got %r" % files)
    ok("non-prose files are not scanned", "tree/notes.txt" not in files,
       "got %r" % files)
    ok("the declared count reflects FILES, not declarations",
       res["docs_declared"] == 3 and res["docs_scanned"] == 3,
       "declared=%r scanned=%r" % (res.get("docs_declared"),
                                   res.get("docs_scanned")))
    # The positive control. A gate is validated in BOTH directions — a known-bad
    # input must go red AND a known-good one must go green — because a negative
    # control alone cannot tell you the pass condition is right.
    commit(home, "tree is clean", **{
        "tree__a.md": "# A\n\nclean.\n",
        "tree__nested__b.md": "# B\n\nclean.\n"})
    code, res = run(home, [sib])
    ok("a clean keep_tree passes, and is still counted as scanned",
       code == pins.CLEAN and res["docs_scanned"] == 3,
       "scanned=%r findings=%r" % (res.get("docs_scanned"), res.get("findings")))
    commit(home, "restore single-file declaration", **{
        "CANONICAL-DOCS.toml": 'path = "D.md"\n'})

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
