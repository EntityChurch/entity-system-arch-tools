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

Scope: `CANONICAL-DOCS.toml` is a **keep-list** — the release pipeline drops
every doc not declared there. So the published surface is
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
import tomllib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# A backticked hex run. 7..40 is git's short-to-full range; 64 is a sha256
# content hash and is deliberately outside it.
TOKEN = re.compile(r"`([0-9a-f]{7,40})`")

# CANONICAL-DOCS.toml declares paths as `path = "..."` or `file = "..."`.
# A declaration is a FILE or a DIRECTORY: `[[keep_tree]]` declares a whole
# directory as product, and everything prose under it publishes. Both spellings
# use `path`, so the two are indistinguishable BY KEY and must both be honoured —
# see `expand_decl`.
#
# WHICH TABLE THE KEY IS IN IS NOT OPTIONAL, and reading this file with a regex
# is what made it look optional. [ADR-0021] added `[[area]]` and `[[living]]` on
# 2026-09-17 — blocks that say what a directory IS and which docs are durable —
# and both use `path`. A whole-file regex reads them as publish declarations, so
# the moment a repo declared `[[area]] path = "docs/outbox"` this gate started
# scanning 42 routing packets and reporting 60 unreachable pins in a corpus that
# by rule NEVER PUBLISHES. Internal docs cite SHAs freely ([ADR-0012] Am. 1);
# every one of those findings was a false red, and a false red is what gets a
# gate switched off.
#
# So the parse is a PARSE. `DECL` is kept for the fallback path only — a manifest
# TOML cannot decode is a could-not-look, and losing the scope entirely there
# would be worse than over-reading it.
PUBLISHING_TABLES = ("doc", "keep_tree")
DECL = re.compile(r'(?:path|file)\s*=\s*"([^"]+)"')

# Directories that never publish even under a `keep_tree`, matching the promote
# pipeline: dev history, scratch, and vendored trees.
DECL_SKIP_DIRS = {".git", "__pycache__", "node_modules", "archive", "archived",
                  "deprecated", "status"}

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


def never_a_sha(tok: str) -> bool:
    """Shapes that are hex but are known not to be commits, at any length.

    A named word (`deadbeef`), or a binary literal (`0b11100`) — every character
    of which is a hex digit, so `TOKEN` matches it and the letter/digit test
    below passes it. Found in a spec section deriving a sparse-bitmap position
    from the first bits of a hash; `0b11100011` was reported as an unresolvable
    commit. `0x` prefixes need no rule: `x` is not a hex digit, so `TOKEN` never
    matches them.
    """
    return tok in NOT_A_SHA or bool(BINARY_LITERAL.match(tok))


def looks_like_sha(tok: str) -> bool:
    """The NOISE FILTER for a token that resolves in no repository.

    `20260716` is a seed; `1000000` is a number; neither is a commit anyone can
    look up. Requiring both a digit and a hex letter removes the bulk of that
    noise — **but it is a heuristic and it is applied last, never first.**

    **A token that resolves to a commit in some repository IS a commit**, whatever
    it is made of, so composition is not consulted for one. That ordering is the
    fix for a real hole: this function's own docstring used to claim a real hash
    with no letter or no digit is *"~1 in 10^8"*, which is the figure for a FULL
    40-character SHA. **The corpus cites SHORT ones.** For a 7-character short
    SHA the true rate is `(10/16)^7 + (6/16)^7` ≈ **3.8%, or about 1 in 26** —
    so on a corpus with 686 short-SHA citations this filter was discarding on the
    order of twenty-five of them *before* anything tried to resolve them, and
    reporting the surface as measured.

    **A citation the gate cannot see is not a clean citation**, and a filter
    tuned on an estimate three orders of magnitude out is the same could-not-look
    defect this toolkit has now found in four analyzers, arriving as arithmetic
    instead of as scope. It surfaced as a flaky self-test: the fixtures build real
    repositories, so roughly one run in twenty produced a short SHA this function
    rejected, and the assertions that depend on it failed for no visible reason.
    """
    if never_a_sha(tok):
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


def manifest_paths(text: str) -> Tuple[List[str], bool]:
    """The declared paths, and whether they came from a real TOML parse.

    Only `[[doc]]` and `[[keep_tree]]` declare a PUBLISHED path. `[[area]]` says
    what a directory is; `[[living]]` says a doc is durable and, with
    `internal = true`, that it must NEVER publish. Reading either as a keep-list
    entry inverts its meaning.

    Falls back to the whole-file regex only when the manifest does not parse —
    over-reading the scope is a false red, but losing it entirely is a gate that
    reports clean over nothing.
    """
    try:
        data = tomllib.loads(text)
    except Exception:
        return DECL.findall(text), False
    out: List[str] = []
    for table in PUBLISHING_TABLES:
        for entry in data.get(table, []) or []:
            if not isinstance(entry, dict):
                continue
            rel = entry.get("path") or entry.get("file")
            if isinstance(rel, str) and rel:
                out.append(rel)
    return out, True


def declared_docs(root: Path) -> Optional[List[str]]:
    c = root / "CANONICAL-DOCS.toml"
    if not c.is_file():
        return None
    try:
        raw, _parsed = manifest_paths(c.read_text(encoding="utf-8"))
    except OSError:
        return None
    out: List[str] = []
    seen = set()
    for rel in raw:
        for p in expand_decl(root, rel):
            if p not in seen:
                seen.add(p)
                out.append(p)
    return out


def expand_decl(root: Path, rel: str) -> List[str]:
    """One declaration -> the prose files it publishes.

    A `[[keep_tree]]` declares a DIRECTORY as product; everything prose under it
    survives the release filter without a per-file entry. It is written with the same
    `path = "..."` key as a single-file declaration, so a scanner that tests
    `is_file()` and moves on **silently drops the whole tree** — and reports the
    result as a pass, because the skip is invisible in a count of findings.

    That is exactly what this gate did until 2026-09-07: `docs/proposals` and
    `docs/research/explorations` are two declarations holding **169 published
    documents**, and the run said `95 declared, 93 scanned` with no indication
    that the two unscanned entries were the largest part of the surface. The
    L24 gate had never read most of the surface it was built to check — the
    could-not-look-as-clean shape this toolkit keeps re-earning, this time in
    the tool written against it.
    """
    p = root / rel
    if p.is_file():
        return [rel]
    if not p.is_dir():
        return []
    found = []
    for f in sorted(p.rglob("*.md")):
        if any(part in DECL_SKIP_DIRS for part in f.relative_to(root).parts):
            continue
        found.append(str(f.relative_to(root)))
    return found


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
    scanned = considered = noise_dropped = 0
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
                # Resolve FIRST, filter on composition only for what resolves
                # nowhere. A token git can look up is a commit whatever it is
                # made of; the letter/digit rule is noise suppression for the
                # rest, and running it first silently dropped ~1 short SHA in 26.
                if never_a_sha(tok):
                    continue
                v = verdict_cache.get(tok)
                if v is None:
                    home = next((r for r in repos if resolve_in(r, tok)), None)
                    if home is None:
                        if not looks_like_sha(tok):
                            # Resolves nowhere AND fails composition. Almost
                            # always real noise (`20260716`, `1000000`) — but
                            # for a token that resolves nowhere, composition is
                            # the ONLY evidence there is, so ~1 real short SHA
                            # in 26 citing an unconfigured repo lands here too.
                            # That residue is unavoidable; making it SILENT is
                            # not. Counted and reported, never just dropped.
                            verdict_cache[tok] = {"rule": None, "home": None,
                                                  "noise": True}
                            noise_dropped += 1
                            continue
                        v = {"rule": "pin-unresolvable", "home": None}
                    else:
                        ok = reachable_from(home, tok, branch)
                        v = {"rule": None if ok else "pin-unreachable",
                             "home": home.name} if ok is not None else \
                            {"rule": "pin-unreachable", "home": home.name}
                    verdict_cache[tok] = v
                if v.get("noise"):
                    noise_dropped += 1
                    continue
                considered += 1
                if v["rule"]:
                    findings.append({"file": rel, "line": lineno, "sha": tok,
                                     "rule": v["rule"], "repo": v["home"]})

    return (VIOLATIONS if findings else CLEAN), {
        "root": str(root), "branch": branch,
        "repos_searched": [r.name for r in repos],
        "docs_declared": len(decl), "docs_scanned": scanned,
        "tokens_considered": considered, "noise_dropped": noise_dropped,
        "findings": findings,
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
    nd = res.get("noise_dropped", 0)
    if nd:
        print("%d token(s) dropped as noise — resolve in no repo searched AND "
              "fail the composition heuristic. Mostly seeds and round numbers; "
              "a real short SHA citing an UNCONFIGURED repo lands here about 1 "
              "time in 26. Add the repo rather than loosen the filter." % nd)
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
