#!/usr/bin/env python3
"""shape — holding a path, can a reader find the document that specifies it?

**This is an ADVISORY READER and it always exits 0. It is a linter in the ordinary
sense: it brings something to light, and there are legitimate exceptions to every
line it prints.** Nothing here is derived from the mathematics, nothing here is a
rule, and a finding is an invitation to a judgment rather than a defect. Treating
its output as a decree is the failure this module was written in the aftermath of.

**The question, and it is the reader's question rather than a tidiness question.**
A person or an agent holds a type path — `system/revision/commit-params`,
`system/peer/transport/quic` — and wants the document that specifies it. The
corpus's habit of naming an extension after a namespace it owns is what makes that
lookup work *without* an index, a search, or a model of the system already in
hand. So the measurement is not "does the name match the namespace" (a fact about
us) but "**does the first segment resolve to a document**" (a fact about the
reader's cost).

⚠ **And there are TWO organizing axes in this corpus, which the first cut of this
module did not know about — it measured one and reported the other's paths as
failures.** A namespace can group **by topic** (`system/registry/*` — *what
mechanism is this*) or **by subject** (`system/peer/{peer_id}/...` — *who is this
about*). `system/peer/*` is a **subject index**: `status/{peer_id}`,
`session/{peer}`, `transport/{peer_id}/{protocol}`, `published-root/{peer}`,
`identity/{peer_id}`, with `self` as the slot for *me* in an index otherwise keyed
by others. **The same type is deliberately stored on both axes** — a peer's own
transports at `system/transport/{protocol}` and a remote peer's at
`system/peer/transport/{peer_id}/{protocol}`, which the core protocol states
outright. **So a subject-indexed path is not a lookup failure; it is a different and
legitimate axis, and grouping it by topic instead would break the property that
everything known about one peer lives under one prefix.** It gets its own bucket.

Four buckets, and the middle two are the whole point:

  * **by-name** — the first segment names a spec in this corpus. The reader
    navigates with nothing held.
  * **core-owned** — the first segment is a namespace the core protocol owns.
    Legitimate, and it costs the reader one piece of prior knowledge: *the core
    owns these*. One sentence, learned once.
  * **subject-indexed** — the namespace is keyed by a subject (a peer id) rather
    than by a mechanism. The reader's question here is *what do I know about P*,
    and the answer is *one prefix*. **Reported, never counted as a failure.**
  * **unresolved** — neither. The reader needs an index that does not exist.

**What it does NOT claim.** That a `by-name` corpus is better than a grouped one;
that depth is bad (122 three-segment paths are in live use and load-bearing); that
an exception is wrong. Two extensions have asked "should this name move?" and
answered it *differently*, each correctly — one because a rename would rebind the
hash of every encrypted entity at rest, one because the prefix was actively
misleading implementers. **A guideline that cannot be broken is not a guideline.**

**Why the concentration report matters more than the count.** Seventeen exceptions
spread evenly across the corpus is noise a reader absorbs. Ten of them in ONE
namespace, specified by FOUR documents, is a place where the lookup reliably
fails — and that is a finding a count alone hides. Same discipline as publishing
the surface a census ranges over rather than the census.

    spec shape [ROOT]              # the three buckets, the concentrations, the joint definers
    spec shape [ROOT] --json       # the same, machine-readable
    spec shape [ROOT] --paths      # every path with its resolution, for grepping

ROOT defaults to the cwd. `--namespace-root` points at the core-protocol corpus so
core-owned segments can be told from unresolved ones; without it every core
namespace reports as unresolved, which is could-not-look wearing a verdict's
clothes, so its absence is stated in the output rather than assumed away.
Stdlib-only 3.11+.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# `type: "system/x/y"` in a schema block — the declaration form the corpus uses.
# Deliberately NOT a bare `system/...` grep: a bare occurrence is a citation, and
# counting citations as declarations was the measurement error that produced the
# claim this module exists to keep honest.
TYPE_RE = re.compile(r'type:\s*"(system/[a-z0-9/_-]+)"')

# A core-owned namespace is any `system/<seg>` the core corpus mentions at all.
# Broad on purpose: the cost of over-crediting core is a path filed as
# `core-owned` when it is really unresolved, which understates a finding; the
# cost of under-crediting is a false accusation against a correct path, which is
# the expensive direction.
CORE_SEG_RE = re.compile(r"system/([a-z0-9-]+)")


# A subject-indexed namespace parameterizes its members by a subject key rather
# than naming a mechanism. Matched on the KEY rather than on a list of namespaces,
# so a second subject axis (a group id, a session id) is recognized without this
# module being edited — and so the recognition is falsifiable rather than a
# hardcoded exemption for the one case that motivated it.
SUBJECT_KEY_RE = re.compile(
    r"\{(?:[a-z_]*peer(?:_id)?(?:_hex)?|remote_id|publisher_peer_id|local_peer_id)\}")


def subject_members(root: Path, dirs: List[str], seg: str) -> List[str]:
    """Which `system/<seg>/<member>/{key}` forms are keyed by a SUBJECT.

    Returns the member names, not a boolean, because the axis is a property of a
    MEMBER and not of a whole first-level segment: `system/capability/policy/{peer}`
    is subject-keyed while `grants/{pattern}` and `revocations/{hash}` beside it are
    not. Reporting at segment granularity over-claims, which is the calibration the
    first cut of this module got wrong in the other direction.
    """
    pat = re.compile(r"system/" + re.escape(seg) + r"/([a-z0-9-]+)/(\{[a-z_]+\})")
    found: Set[str] = set()
    for d in dirs:
        base = root / d
        if not base.is_dir():
            continue
        for p in base.rglob("*.md"):
            text = p.read_text(encoding="utf-8", errors="ignore")
            for member, key in pat.findall(text):
                if SUBJECT_KEY_RE.fullmatch(key):
                    found.add(member)
    return sorted(found)


def _norm(stem: str) -> str:
    """`EXTENSION-TYPE` -> `type`; `SYSTEM-DATA-EXCHANGE` -> `dataexchange`."""
    tail = stem.split("-", 1)[-1] if "-" in stem else stem
    return tail.lower().replace("-", "")


def spec_stems(root: Path, spec_dirs: List[str]) -> Dict[str, str]:
    """`{normalized-name: stem}` for every spec document."""
    out: Dict[str, str] = {}
    for d in spec_dirs:
        base = root / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.md")):
            out.setdefault(_norm(p.stem), p.stem)
    return out


def declared_types(root: Path, spec_dirs: List[str]) -> Dict[str, Set[str]]:
    """`{type-path: {declaring stems}}`."""
    out: Dict[str, Set[str]] = defaultdict(set)
    for d in spec_dirs:
        base = root / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.md")):
            text = p.read_text(encoding="utf-8", errors="ignore")
            for t in set(TYPE_RE.findall(text)):
                out[t].add(p.stem)
    return out


def core_segments(ns_root: Optional[Path]) -> Optional[Set[str]]:
    """First-level segments the core corpus names, or None if not looked at."""
    if ns_root is None or not ns_root.is_dir():
        return None
    segs: Set[str] = set()
    for p in ns_root.rglob("*.md"):
        segs |= set(CORE_SEG_RE.findall(p.read_text(encoding="utf-8", errors="ignore")))
    return segs or None


def analyze(types: Dict[str, Set[str]], stems: Dict[str, str],
            core: Optional[Set[str]],
            is_subject=lambda seg: False,
            subject_member_map: Optional[Dict[str, List[str]]] = None) -> dict:
    subject_member_map = subject_member_map or {}
    by_name: List[Tuple[str, str]] = []
    core_owned: List[Tuple[str, str]] = []
    subject: List[Tuple[str, str]] = []
    unresolved: List[str] = []
    for path in sorted(types):
        parts = path.split("/")
        if len(parts) < 2:
            unresolved.append(path)
            continue
        seg = parts[1]
        doc = stems.get(seg.replace("-", ""))
        if doc:
            by_name.append((path, doc))
        elif is_subject(seg):
            # A different axis, not a failure. Checked BEFORE core-owned, because a
            # subject index is usually core-reserved and the axis is the more
            # informative fact about it.
            subject.append((path, seg))
        elif core and seg in core:
            core_owned.append((path, seg))
        else:
            unresolved.append(path)

    # Concentration: a namespace whose paths are NOT resolvable by name, grouped,
    # with every document that declares into it. The multi-declarer case is what
    # makes a lookup fail rather than merely cost one fact.
    conc: Dict[str, dict] = {}
    for path, seg in core_owned:
        e = conc.setdefault(seg, {"paths": [], "declared_by": set()})
        e["paths"].append(path)
        e["declared_by"] |= types[path]
    for path in unresolved:
        seg = path.split("/")[1] if "/" in path[7:] + "/" else path
        e = conc.setdefault(seg, {"paths": [], "declared_by": set()})
        e["paths"].append(path)
        e["declared_by"] |= types[path]

    joint = {p: sorted(d) for p, d in types.items() if len(d) > 1}
    subj: Dict[str, dict] = {}
    for path, seg in subject:
        e = subj.setdefault(seg, {"paths": [], "declared_by": set(),
                                  "members": subject_member_map.get(seg, [])})
        e["paths"].append(path)
        e["declared_by"] |= types[path]

    return {
        "total": len(types),
        "by_name": by_name,
        "core_owned": core_owned,
        "subject_indexed": subject,
        "subject_namespaces": {
            k: {"paths": sorted(v["paths"]),
                "declared_by": sorted(v["declared_by"]),
                "members": v.get("members", [])}
            for k, v in sorted(subj.items())},
        "unresolved": unresolved,
        "concentrations": {
            k: {"paths": sorted(v["paths"]), "declared_by": sorted(v["declared_by"])}
            for k, v in sorted(conc.items(),
                               key=lambda kv: -len(kv[1]["paths"]))
        },
        "joint_declarers": joint,
    }


def report(r: dict, looked_at_core: bool, show_paths: bool) -> None:
    n = r["total"]
    print("spec shape — %d declared type path(s); can a reader find the document?" % n)
    print()
    print("  by-name     %4d   the first segment names a spec here — nothing held"
          % len(r["by_name"]))
    print("  core-owned  %4d   the core protocol owns the segment — one fact, learned once"
          % len(r["core_owned"]))
    print("  subject     %4d   a SUBJECT index, keyed by peer rather than by mechanism"
          % len(r.get("subject_indexed", [])))
    print("  unresolved  %4d   neither; the reader needs an index that does not exist"
          % len(r["unresolved"]))
    if not looked_at_core:
        print()
        print("  ⚠ could-not-look on the core namespace: no --namespace-root was given or it")
        print("    is absent, so EVERY core-owned segment is counted as unresolved above.")
        print("    That is not a measurement of this corpus. Pass --namespace-root.")

    for seg, v in r.get("subject_namespaces", {}).items():
        print()
        print("  system/%s/ carries SUBJECT-INDEXED members — keyed by peer, not by" % seg)
        print("  mechanism, so the reader's question is *what do I know about P* and the")
        print("  answer is one prefix. Grouping these by mechanism would break that.")
        print("    subject-keyed members: %s" % ", ".join(v.get("members") or ["(unnamed)"]))
        print("    %d declared path(s), from: %s"
              % (len(v["paths"]), ", ".join(v["declared_by"])))
        print("  NOT a finding. The open question is which facts belong on which axis —")
        print("  and a segment may legitimately carry members on both.")

    conc = {k: v for k, v in r["concentrations"].items() if v["paths"]}
    if conc:
        print()
        print("  where the lookup does not resolve, by namespace — read this, not the count:")
        for seg, v in conc.items():
            many = len(v["declared_by"]) > 1
            print("    system/%-14s %3d path(s)   declared by %d document(s)%s"
                  % (seg, len(v["paths"]), len(v["declared_by"]),
                     "  <-- multiple" if many else ""))
            if many:
                print("        %s" % ", ".join(v["declared_by"]))
    if r["joint_declarers"]:
        print()
        print("  one path, several declaring documents (a citation may look like a declaration):")
        for p, docs in sorted(r["joint_declarers"].items()):
            print("    %-44s %s" % (p, ", ".join(docs)))
    if show_paths:
        print()
        for path, doc in r["by_name"]:
            print("  by-name     %-46s -> %s" % (path, doc))
        for path, seg in r["core_owned"]:
            print("  core-owned  %-46s -> core owns system/%s" % (path, seg))
        for path in r["unresolved"]:
            print("  unresolved  %s" % path)

    print()
    print("advisory, exits 0 — these are guidelines with legitimate exceptions, not rules.")
    print("a concentration is a place a reader's lookup reliably fails; a rename is priced")
    print("separately, and a path segment inside something signed or independently derived")
    print("is expensive to move.")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="spec shape", add_help=True,
                                 description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--namespace-root", default=None,
                    help="the core-protocol corpus, so core-owned segments are "
                         "distinguishable from unresolved ones")
    ap.add_argument("--spec-dir", action="append", default=None,
                    help="spec directory to scan (repeatable; default: specs)")
    ap.add_argument("--paths", action="store_true", help="list every path")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    root = Path(a.root).resolve()
    spec_dirs = a.spec_dir or ["specs"]
    types = declared_types(root, spec_dirs)
    if not types:
        print("could-not-look: 0 declared type paths under %s in %s"
              % (", ".join(spec_dirs), root), file=sys.stderr)
        return 0
    stems = spec_stems(root, spec_dirs)
    ns = Path(a.namespace_root).resolve() if a.namespace_root else None
    core = core_segments(ns)
    segs = {p.split("/")[1] for p in types if "/" in p[7:]}
    smap = {s: m for s in sorted(segs)
            if (m := subject_members(root, spec_dirs, s))}
    r = analyze(types, stems, core, is_subject=lambda seg: seg in smap,
                subject_member_map=smap)
    if a.json:
        print(json.dumps({k: (v if not isinstance(v, list) else v)
                          for k, v in r.items()}, indent=2, default=list))
    else:
        report(r, core is not None, a.paths)
    return 0


if __name__ == "__main__":
    sys.exit(main())
