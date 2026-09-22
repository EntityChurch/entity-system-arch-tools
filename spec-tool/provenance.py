#!/usr/bin/env python3
"""provenance — the L1 gate: no normative spec edit without a proposal.

Every other analyzer checks **text**. This one checks a **change**, which is why
it could not be a corpus lint: *"was there a proposal for this edit?"* is
unanswerable from the file alone.

    spec provenance [--since REF] [--root PATH] [--json]

Why it exists. `entity-system-architecture` measured itself: **50 commits
touched `specs/` in two weeks and 34 carried no proposal**, 25 of them inside a
six-day window. The acute case was `EXTENSION-REVISION` v3.11 — folded with no
proposal in existence, two new MUSTs plus a rev bump — and its **second-order**
failure is the one that matters: because no proposal existed, **the rationale
had nowhere to go, so it went into the spec text.** One error produced the
other. The corpus's narrative-debt rules clean up the symptom; this gate is
aimed at the cause.

**The trigger is two-part, and this is the part that was got wrong first.** The
routed design keyed on the `**Version**` header changing. Measured against the
two normative folds landed the day it was written — `80d3ca2` (+2 MUSTs) and
`40586c5` (+4 MUSTs) — **both changed zero version headers**, correctly, under
arch's standing *"cohort impl findings fix the spec in place, no rev bump"*
carve-out. A version-triggered gate is **silent on precisely the class arch uses
most.** So either of these fires:

  1. the `**Version**` header of a `specs/**.md` changed, or
  2. a `specs/**.md`'s count of normative tokens (`MUST`, `MUST NOT`, `SHALL`,
     `[MUST]`) **changed** — added *or* removed; retiring a requirement is as
     normative as adding one.

**Trigger 2 counts the file, not the diff's `+` lines, and that was measured.**
Counting `+` lines reports every reworded sentence that merely *contains* a MUST
as a new requirement, so an editorial touch-up of an existing rule fires the
gate — caught by this module's own self-test before it shipped. The file-count
form distinguishes *a requirement was added or removed* from *a requirement was
rephrased*, which is the distinction L1 is about. **Residue, stated:** a rewrite
that swaps one MUST for a different MUST nets to zero and is invisible here.

and the commit must then **name a proposal that exists** under
`docs/proposals/{active,implemented,deferred,superseded}/`, or **declare a
carve-out** in a trailer.

**The carve-outs are declared and greppable, never inferred.** Two are
legitimate and both are arch's own standing rules:

    Spec-Change: hygiene          wording-only; no normative change
    Spec-Change: cohort-finding   an impl finding fixed in place, no rev bump

**An exemption nobody can audit is not an exemption** — the trailer puts the
claim in the record where a reviewer can disagree with it. Without the
cohort-finding trailer, trigger 2 would fire on every in-place fix, which is the
shape that gets a gate switched off in a week.

**Severity is `warn` by default, on purpose.** Flipping this to `error`
retroactively fails against a 34-commit backlog on contact. Land it at warn, let
the reconstruction ledger burn the backlog down, then promote — the same ratchet
that worked for the five `standards` rules.

Stdlib-only Python 3.11+. Exit **0** clean (or warn-only), **1** violations at
error severity, **2** could-not-look — no git dir, unresolvable base ref, a
shallow clone. **A gate that cannot see must never read as a pass**; this repo
learned that the expensive way (`7fd538f`).
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import config as _config

_CFG = _config.load()
_AN = _CFG.analyzer("provenance")
_RULES: Dict[str, str] = _AN.get("rules", {})
_SPEC_PREFIX: str = _AN.get("spec_prefix", "specs/")
_PROPOSAL_DIRS: List[str] = _AN.get("proposal_dirs", [])
_CARVE_OUTS: List[str] = _AN.get("carve_outs", [])
_DEFAULT_SINCE: str = _AN.get("default_since", "HEAD~1")

# A `+` line introducing a normative requirement. Deliberately NOT `SHOULD` /
# `MAY`: those are the tiers a proposal is least often written for, and folding
# them in doubles the finding count for the weakest signal.
NORMATIVE_RE = re.compile(r"\b(MUST NOT|MUST|SHALL NOT|SHALL)\b|\[MUST\]")

# `**Version**: 1.5` in the header region.
VERSION_RE = re.compile(r"^\*\*Version\*\*\s*:\s*(.*)$")

# A proposal named anywhere in the commit message. The corpus names them bare
# (`PROPOSAL-SYSTEM-DEVICE`) as often as by path, so match the stem.
PROPOSAL_NAME_RE = re.compile(r"\bPROPOSAL-[A-Z0-9][A-Z0-9-]*")

TRAILER_RE = re.compile(r"^Spec-Change:\s*(\S+)\s*$", re.MULTILINE)


class Finding:
    __slots__ = ("rule", "commit", "text")

    def __init__(self, rule: str, commit: str, text: str):
        self.rule = rule
        self.commit = commit
        self.text = text

    def severity(self) -> str:
        return _RULES.get(self.rule, "warn")


def git(root: Path, *args: str) -> Optional[str]:
    """Run git in `root`; None if git is unavailable or this is not a repo."""
    try:
        p = subprocess.run(["git", "-C", str(root), *args],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0:
        return None
    return p.stdout


def version_of(text: str) -> Optional[str]:
    for ln in text.splitlines():
        if ln.startswith("## "):
            break
        m = VERSION_RE.match(ln)
        if m:
            return m.group(1).strip()
    return None


def proposal_stems(roots: List[Path]) -> set:
    """Every proposal that exists on disk, by stem, across every searched root.
    State is the directory (`INDEX.md` §0), so existence is a listing rather
    than a parse.

    **This takes a LIST because the proposal need not live in the repo being
    inspected.** `entity-core-protocol` is a corpus whose normative folds are
    authored, ratified and filed in `entity-system-architecture` — so resolving
    stems against the inspected repo alone reports every correctly-cited fold as
    uncited. Measured 2026-09-06: all four `0.8.2.x` folds in that repo named
    their proposal and all four were reported `normative-edit-without-proposal`.
    That is could-not-look wearing a verdict's clothes, the same defect
    `address` had before `--namespace-root`."""
    out = set()
    seen = set()
    for root in roots:
        try:
            key = root.resolve()
        except OSError:
            continue
        if key in seen:
            continue
        seen.add(key)
        for d in _PROPOSAL_DIRS:
            base = root / d
            if base.is_dir():
                out.update(p.stem for p in base.rglob("PROPOSAL-*.md"))
    return out


def triggers(root: Path, sha: str, path: str) -> List[str]:
    """Why this spec change needs a proposal — empty means it does not."""
    why: List[str] = []

    old = git(root, "show", "%s^:%s" % (sha, path)) or ""
    new = git(root, "show", "%s:%s" % (sha, path)) or ""
    if old and new and version_of(old) != version_of(new):
        why.append("version %s -> %s" % (version_of(old), version_of(new)))

    # Counted over the WHOLE FILE, before and after — not over the diff's `+`
    # lines. Measured: a `+` line count reports every reworded sentence that
    # merely CONTAINS a MUST as a new requirement, so an editorial touch-up of
    # an existing rule fires the gate. Counting the file's normative tokens
    # distinguishes "a requirement was added or removed" from "a requirement was
    # rephrased", which is the distinction L1 is actually about.
    old_n = len(NORMATIVE_RE.findall(old))
    new_n = len(NORMATIVE_RE.findall(new))
    if old_n != new_n:
        why.append("normative tokens %d -> %d" % (old_n, new_n))
    return why


def analyze_commit(root: Path, sha: str, stems: set) -> List[Finding]:
    msg = git(root, "log", "-1", "--format=%B", sha) or ""

    declared = [m.group(1) for m in TRAILER_RE.finditer(msg)]
    carved = [d for d in declared if d in _CARVE_OUTS]
    mentioned = PROPOSAL_NAME_RE.findall(msg)
    named = [n for n in mentioned if n in stems]
    unresolved = [n for n in mentioned if n not in stems]

    files = [f for f in (git(root, "show", "--format=", "--name-only", sha) or "").split()
             if f.startswith(_SPEC_PREFIX) and f.endswith(".md")]

    out: List[Finding] = []
    for path in files:
        why = triggers(root, sha, path)
        if not why:
            continue
        if named or carved:
            continue

        # L1 governs NORMATIVE spec edits. `specs/` also holds informative
        # architecture references, navigation docs and the two rulebooks — the
        # `[classes]` map says which is which, and this gate triggered on the
        # PATH PREFIX alone, so an arch-doc revision was reported in the same
        # words as a wire-rule change: "the rationale has nowhere to go but the
        # spec text". For an arch-doc that is exactly backwards — an
        # architectural document is *where rationale legitimately lives*
        # (SPECIFICATION-FORMAT §11.3 row 2).
        #
        # The teeth stay where the harm is. Class only downgrades the
        # VERSION-BUMP trigger. If the file's normative-token count moved, a
        # requirement was added or removed and that is the normative finding
        # whatever the document calls itself — so MUSTs cannot be parked in an
        # arch-doc to dodge L1.
        doc_class = _CFG.doc_class(Path(path).stem)
        token_moved = any(w.startswith("normative tokens") for w in why)
        if doc_class != "canonical-spec" and not token_moved:
            out.append(Finding(
                "informative-doc-revision", sha,
                "%s (%s) is class `%s`, not a normative spec — reported, not held "
                "to L1. Its normative-token count did not move."
                % (path, "; ".join(why), doc_class)))
            continue
        # An undeclared trailer value is reported distinctly: it is a claimed
        # exemption the gate does not recognise, which is a different fact from
        # no exemption at all.
        if declared:
            out.append(Finding(
                "spec-change-trailer-unknown", sha,
                "%s (%s) declares `Spec-Change: %s`, which is not a configured "
                "carve-out %s" % (path, "; ".join(why), declared[0], _CARVE_OUTS)))
            continue
        # A message that NAMES a proposal the gate could not find is ambiguous
        # between a FABRICATED citation and one filed in a repo nobody told the
        # gate about — and it cannot tell them apart without operator input.
        # **It stays the same finding at the same severity**, because the safe
        # default is the accusing one: an earlier draft of this split demoted
        # the unresolved case to `info` and thereby made an invented proposal
        # name an escape hatch, which this file's own
        # "named but absent from disk does NOT satisfy" case caught. What
        # changes is the TEXT — it names the unresolved stem and the remedy, so
        # the could-not-look reading is in front of the reader who can act on
        # it. Measured 2026-09-06: all four `entity-core-protocol` 0.8.2.x folds
        # cited their proposal correctly and read as uncited, because those
        # proposals are filed in `entity-system-architecture`.
        if unresolved:
            out.append(Finding(
                "normative-edit-without-proposal", sha,
                "%s (%s) names `%s`, which is in none of the searched proposal "
                "roots (%d proposal(s) found). Either the citation is wrong, or "
                "this corpus's proposals are filed in another repo — pass "
                "--proposal-root <repo> before reading this as a missing "
                "proposal" % (path, "; ".join(why), unresolved[0], len(stems))))
            continue
        out.append(Finding(
            "normative-edit-without-proposal", sha,
            "%s (%s) names no proposal and declares no carve-out — the rationale "
            "has nowhere to go but the spec text" % (path, "; ".join(why))))
    return out


def run_check(root: Path, since: str, as_json: bool,
              proposal_roots: Optional[List[Path]] = None) -> int:
    if git(root, "rev-parse", "--git-dir") is None:
        print("not a git repository (or git unavailable): %s" % root, file=sys.stderr)
        print("  this gate reads CHANGES, not text — it cannot look here.", file=sys.stderr)
        return 2

    rng = git(root, "rev-list", "--no-merges", "%s..HEAD" % since)
    if rng is None:
        print("cannot resolve base ref: %s" % since, file=sys.stderr)
        print("  scanned 0 commits — this is not a pass, it is a gate that did not look.",
              file=sys.stderr)
        print("  pass --since <ref> with a ref this clone actually has"
              " (a shallow clone may not).", file=sys.stderr)
        return 2

    shas = rng.split()
    roots = [root] + list(proposal_roots or [])
    stems = proposal_stems(roots)
    findings: List[Finding] = []
    for sha in shas:
        findings.extend(analyze_commit(root, sha, stems))

    n_error = sum(1 for f in findings if f.severity() == "error")
    n_warn = sum(1 for f in findings if f.severity() == "warn")

    if as_json:
        print(json.dumps({
            "summary": {"commits": len(shas), "since": since, "proposals": len(stems),
                        "proposal_roots": [str(r) for r in roots],
                        "errors": n_error, "warnings": n_warn},
            "findings": [{"rule": f.rule, "severity": f.severity(),
                          "commit": f.commit[:7], "text": f.text} for f in findings],
        }, indent=2))
        return 1 if n_error else 0

    for f in findings:
        print("  %-6s %-32s %s  %s"
              % (f.severity().upper(), f.rule, f.commit[:7], f.text))

    # The commit count is part of the answer: 0 findings over 0 commits is a
    # range that resolved to nothing, not a clean history.
    print("\nscanned %d commit(s) since %s, %d proposal(s) on disk — %d error(s), %d warning(s)."
          % (len(shas), since, len(stems), n_error, n_warn))
    print("proposal roots searched: %s" % ", ".join(str(r) for r in roots))
    if n_warn and not n_error:
        print("warn-only: L1 is ratcheting. Promote to error in "
              "[analyzer.provenance.rules] once the reconstruction ledger burns down.")
    return 1 if n_error else 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", default=_DEFAULT_SINCE, help="base ref (default: %(default)s)")
    ap.add_argument("--root", type=Path, help="repo to inspect (default: the corpus)")
    ap.add_argument("--proposal-root", type=Path, action="append", metavar="REPO",
                    help="an ADDITIONAL repo whose docs/proposals/ files this corpus's "
                         "proposals; repeatable. Without it, a corpus whose folds are "
                         "authored in a sibling repo reports every correctly-cited "
                         "commit as uncited")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)
    return run_check(args.root or _CFG.corpus_dir, args.since, args.json,
                     args.proposal_root)


if __name__ == "__main__":
    raise SystemExit(main())
