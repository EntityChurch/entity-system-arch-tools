#!/usr/bin/env python3
"""pins — does every commit citation in the PUBLISHED surface resolve for its reader?

    spec pins [--root DIR] [--branch master] [--sibling DIR ...] [--gate] [--json]

Every other analyzer asks whether a document is *correct*. This one asks
whether its citations are **reachable by the audience the document is
published to** — a property of the (citation, reader) pair, not of the
citation.

Why it exists, measured. [ADR-0027] decides the shape of published history:
each published commit is **authored fresh at the boundary**, so public
`master` is a *different history* from `dev`. `dev` is never rewritten and
`master` advances fast-forward only — this is not a force-push story. The
consequence is simply that **a `dev` SHA has never resolved on `master` and
never will.** It is not degraded by the release; it was never valid for the
reader it ships to.

[ADR-0012] meanwhile requires the opposite: *"keep oracle-commit pinning —
every published count is `N·0F @ <oracle-commit>`"*, and calls reproducible
oracle-pinned conformance *"our single strongest credibility artifact."* The
two ADRs are each correct in their own frame and **jointly unsatisfiable**;
ADR-0027 even lists ADR-0012 among the constraints it *"works within"* and
never noticed it had invalidated its central identifier.

**This has already fired, twice, and one instance is live.** The
`CONFORMANCE-MATRIX.md` on published `master` reads `665·0F @ e8524ed`, and
`e8524ed` — with `33f35fd`, `b30a589`, `75c532e` — exists in **no repo in the
checkout**. They died in a mirror history rewrite on 2026-07-10.
`entity-core-keystone` diagnosed that correctly at the time and built the
durable anchor (`core_gate_fingerprint`: the normalized category set + type
floor, comment- and format-invariant, which they named **mirror-stable**).
Their `oracle-pin.env` carries the proof in one line —
`retired_ref_4 = e8524ed (unreproducible after mirror history rewrite; same
fingerprint)`. The commit died; the fingerprint carried the verdict across its
death. **That fix stayed a local practice in one seat and never reached the
rule**, which is why the pin later regressed from `cc1970f` (on public
`master`) to a `dev`-only commit with nothing objecting.

Scope: `CANONICAL-DOCS.toml` is a **keep-list** — the promote pipeline's
`canon-filter` drops every doc not declared there. So the published surface is
exactly the declared set, and that is what this reads. A `dev`-only hash in a
git-ignored scratch note is not a defect; the same hash in a declared doc is.

The rules:

  pin-unreachable      A token resolves to a real commit in some repo, but is
                       **not reachable from that repo's published branch**. The
                       defect above, directly: the reader clones `master`,
                       runs `git show`, and gets nothing.

  pin-unresolvable     A token has the shape of a short SHA and resolves to a
                       commit in **no** repo searched. Either regex noise or an
                       already-dead pin, and the tool does **not** guess which
                       — it reports the class and leaves the judgment, because
                       the two have opposite remedies (delete the sentence vs.
                       re-derive the claim).

What it deliberately does NOT flag, because these are the *fix*:

  * **64-hex content hashes** — sha256 of an artifact, `core_gate_fingerprint`,
    `check_set_digest`. Content-addressed identifiers do not care about
    history and are the model this gate exists to push people toward. There
    are ~4,000 of them across the ecosystem and every one is immune.
  * Tokens with no hex letters (`20260716` — a corpus seed) or no digits, and
    known non-SHA words. A short-SHA candidate must look like one.

**Cross-repo resolution is the load-bearing detail, and getting it wrong is
how this gate would ship its own worst bug.** Keystone's matrix cites
`entity-core-go` commits; resolving them against *keystone* reports a clean
zero, and resolving them against nothing-but-the-home-repo reports every one
as broken. Both are wrong for the same reason — *"does not resolve in repo B"*
is not a finding unless the citation was **to** repo B. So every token is
resolved against the home repo **and every sibling given**, and reachability is
then checked in whichever repo actually holds it. `--sibling` defaults to the
sibling directories of `--root`.

Exit codes are three-valued, like every gate here: 0 clean, 1 violations, 2
could-not-look. **A missing `master`, a missing `CANONICAL-DOCS.toml`, or no
git at all is a 2** — never a pass over an unread set, and never a wall of red
that is really one absent ref.

**Reader by default; `--gate` to enforce.** The first run against the live
corpus scores in the hundreds, nearly all of it in rolling `STATUS.md` files
that are declared canonical. A gate that is red on day one teaches people to
skip it — the same reasoning that keeps `sdksync`'s unpinned backlog
non-gating and `coverage` at exit 0. Burn the backlog down, then turn on
`--gate` in CI.

Stdlib-only, like the rest of the package. Requires `git` on PATH; its absence
is a 2.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# A backticked hex run. 7..40 is git's short-to-full range; 64 is a sha256
# content hash and is deliberately outside it.
TOKEN = re.compile(r"`([0-9a-f]{7,40})`")

# CANONICAL-DOCS.toml declares paths as `path = "..."` or `file = "..."`.
DECL = re.compile(r'(?:path|file)\s*=\s*"([^"]+)"')

# Words that are hex-shaped but never SHAs. Extend as the corpus teaches; each
# entry should be a real false positive someone actually hit.
NOT_A_SHA = {"ed25519", "ed448", "deadbeef", "cafebabe", "feedface", "decade"}

# A binary literal: `0b` then nothing but 0s and 1s. Every character of `0b11100`
# is a hex digit and the token carries both a digit and a letter, so it satisfies
# `looks_like_sha` exactly. Found in EXTENSION-TREE §5, which derives a sparse
# bitmap position from the first 5 bits of a hash — `0b11100011` and `0b11100`
# were reported as unresolvable commits. `0x` prefixes need no rule: `x` is not a
# hex digit, so TOKEN never matches them.
BINARY_LITERAL = re.compile(r"0b[01]+$")

CLEAN, VIOLATIONS, CANNOT_LOOK = 0, 1, 2


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


def looks_like_sha(tok: str) -> bool:
    """A short-SHA candidate has both a digit and a hex letter, and is not a word.

    `20260716` is a seed; `deadbeef` is a joke; `1000000` is a number. Requiring
    both classes removes the bulk of the noise without ever suppressing a real
    hash, since a real one with no letter or no digit is ~1 in 10^8 and would
    be reported by the resolver anyway if it existed.

    A binary literal (`0b11100`) passes every one of those tests and is not a
    commit, so it is excluded by shape. The suppression it costs is a short SHA
    beginning `0b` with only 0s and 1s after — roughly 1 in 10^7, the same order
    as the letter/digit rule above already accepts.
    """
    if tok in NOT_A_SHA:
        return False
    if BINARY_LITERAL.match(tok):
        return False
    return any(c.isdigit() for c in tok) and any(c in "abcdef" for c in tok)


def resolve_in(repo: Path, tok: str) -> bool:
    return git(repo, "cat-file", "-e", "%s^{commit}" % tok) is not None


def reachable_from(repo: Path, tok: str, branch: str) -> Optional[bool]:
    """True/False, or None if `branch` does not exist in this repo (a 2)."""
    if git(repo, "rev-parse", "--verify", "--quiet", branch) is None:
        return None
    try:
        p = subprocess.run(
            ["git", "-C", str(repo), "merge-base", "--is-ancestor", tok, branch],
            capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.returncode == 0


def declared_docs(root: Path) -> Optional[List[str]]:
    c = root / "CANONICAL-DOCS.toml"
    if not c.is_file():
        return None
    try:
        return DECL.findall(c.read_text(encoding="utf-8"))
    except OSError:
        return None


def scan(root: Path, branch: str, siblings: List[Path]) -> Tuple[int, dict]:
    if not is_repo(root):
        return CANNOT_LOOK, {"error": "not a git repository: %s" % root}

    decl = declared_docs(root)
    if decl is None:
        return CANNOT_LOOK, {
            "error": "no CANONICAL-DOCS.toml in %s — the published surface is "
                     "undeclared, so there is nothing to scope this to" % root}

    repos = [root] + [s for s in siblings if is_repo(s) and s != root]
    if reachable_from(root, "HEAD", branch) is None:
        return CANNOT_LOOK, {
            "error": "branch %r does not exist in %s — cannot tell what the "
                     "published surface contains" % (branch, root)}

    findings: List[dict] = []
    scanned = considered = 0
    verdict_cache: Dict[str, dict] = {}

    for rel in decl:
        f = root / rel
        if not f.is_file():
            continue
        scanned += 1
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for tok in TOKEN.findall(line):
                if not looks_like_sha(tok):
                    continue
                considered += 1
                v = verdict_cache.get(tok)
                if v is None:
                    home = next((r for r in repos if resolve_in(r, tok)), None)
                    if home is None:
                        v = {"rule": "pin-unresolvable", "home": None}
                    else:
                        ok = reachable_from(home, tok, branch)
                        v = {"rule": None if ok else "pin-unreachable",
                             "home": home.name} if ok is not None else \
                            {"rule": "pin-unreachable", "home": home.name}
                    verdict_cache[tok] = v
                if v["rule"]:
                    findings.append({"file": rel, "line": lineno, "sha": tok,
                                     "rule": v["rule"], "repo": v["home"]})

    return (VIOLATIONS if findings else CLEAN), {
        "root": str(root), "branch": branch,
        "repos_searched": [r.name for r in repos],
        "docs_declared": len(decl), "docs_scanned": scanned,
        "tokens_considered": considered, "findings": findings,
    }


def report(res: dict, gate: bool) -> None:
    if "error" in res:
        print("\n  COULD NOT LOOK: %s" % res["error"])
        return
    f = res["findings"]
    by_file: Dict[str, List[dict]] = {}
    for x in f:
        by_file.setdefault(x["file"], []).append(x)

    for path in sorted(by_file, key=lambda p: -len(by_file[p])):
        rows = by_file[path]
        unreach = sum(1 for r in rows if r["rule"] == "pin-unreachable")
        unres = len(rows) - unreach
        print("\n%s  (%d citation(s) a reader cannot resolve)" % (path, len(rows)))
        if unreach:
            ex = ", ".join(sorted({r["sha"] for r in rows
                                   if r["rule"] == "pin-unreachable"})[:6])
            print("  pin-unreachable   x%-4d not on `%s` — e.g. %s"
                  % (unreach, res["branch"], ex))
        if unres:
            ex = ", ".join(sorted({r["sha"] for r in rows
                                   if r["rule"] == "pin-unresolvable"})[:6])
            print("  pin-unresolvable  x%-4d resolves in no repo searched — e.g. %s"
                  % (unres, ex))

    print("\n%d declared doc(s), %d scanned, %d short-SHA citation(s) considered "
          "— %d unreachable by a reader of `%s`."
          % (res["docs_declared"], res["docs_scanned"], res["tokens_considered"],
             len(f), res["branch"]))
    print("repos searched for cross-repo citations: %s"
          % ", ".join(res["repos_searched"]))
    if f and not gate:
        print("reader mode — exits 0. Run with --gate to enforce.")
    print("content hashes (64 hex) are never flagged: they are the fix, not the defect.")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path.cwd(),
                    help="repo whose published surface to read (default: cwd)")
    ap.add_argument("--branch", default="master",
                    help="the published branch a reader would clone (default: master)")
    ap.add_argument("--sibling", action="append", type=Path, default=None,
                    help="another repo to resolve cross-repo citations against "
                         "(repeatable; defaults to --root's sibling directories)")
    ap.add_argument("--gate", action="store_true",
                    help="exit 1 on findings (default is reader mode, exit 0)")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)

    root = args.root.resolve()
    sibs = args.sibling
    if sibs is None:
        sibs = [d for d in sorted(root.parent.iterdir())
                if d.is_dir() and d != root] if root.parent.is_dir() else []
    sibs = [Path(s).resolve() for s in sibs]

    code, res = scan(root, args.branch, sibs)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        report(res, args.gate)
    if code == CANNOT_LOOK:
        return CANNOT_LOOK
    return VIOLATIONS if (code == VIOLATIONS and args.gate) else CLEAN


if __name__ == "__main__":
    sys.exit(main())
