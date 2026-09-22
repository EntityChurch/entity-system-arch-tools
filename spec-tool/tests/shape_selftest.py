#!/usr/bin/env python3
"""shape self-test.

`shape` is an advisory reader, so the assertions here are mostly about the
*classification* being honest rather than about a gate firing. Three properties
are load-bearing and each is asserted:

  1. a DECLARATION is `type: "system/..."`; a bare mention is a CITATION and must
     not be counted. Counting citations as declarations is the exact measurement
     error that produced the withdrawn naming rule this module exists to keep
     honest.
  2. without a namespace root, core-owned segments MUST report as could-not-look
     rather than as `unresolved` — a wrong number wearing a verdict's clothes.
  3. the concentration report groups by namespace and names every declaring
     document, because ten exceptions in one namespace and ten spread evenly are
     different findings that the same count hides.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shape  # noqa: E402

FAIL = []


def ok(name, cond, detail=""):
    print("  %-4s %s%s" % ("ok" if cond else "FAIL", name,
                           "" if cond else "   <- " + str(detail)))
    if not cond:
        FAIL.append(name)


def corpus(files, core=None):
    """files: {relpath: text}. Returns (root, ns_root|None)."""
    root = Path(tempfile.mkdtemp())
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    ns = None
    if core is not None:
        ns = root / "_core"
        ns.mkdir(parents=True, exist_ok=True)
        (ns / "ENTITY-CORE-PROTOCOL.md").write_text(core, encoding="utf-8")
    return root, ns


def run(files, core=None):
    root, ns = corpus(files, core)
    types = shape.declared_types(root, ["specs"])
    stems = shape.spec_stems(root, ["specs"])
    return shape.analyze(types, stems, shape.core_segments(ns))


print("shape self-test")

# ---------------------------------------------- 1. declaration vs citation
r = run({"specs/extensions/EXTENSION-TREE.md":
         'type: "system/tree/snapshot"\n\nand see system/peer/status for the other thing\n'})
ok("a `type:` declaration is counted",
   [p for p, _ in r["by_name"]] == ["system/tree/snapshot"], r["by_name"])
ok("a bare mention is a CITATION and is NOT counted",
   all("system/peer" not in p for p in
       [q for q, _ in r["by_name"]] + [q for q, _ in r["core_owned"]] + r["unresolved"]),
   r)

# ---------------------------------------------- 2. could-not-look
files = {"specs/extensions/EXTENSION-NETWORK.md":
         'type: "system/network/ping"\ntype: "system/peer/status"\n'}
no_core = run(files)
with_core = run(files, core="the core owns system/peer/self and system/peer/alias\n")
ok("without a namespace root, a core segment lands in `unresolved`",
   [p for p in no_core["unresolved"]] == ["system/peer/status"], no_core["unresolved"])
ok("...and WITH one it is reclassified as core-owned, not unresolved",
   [p for p, _ in with_core["core_owned"]] == ["system/peer/status"]
   and with_core["unresolved"] == [], with_core)
ok("the by-name bucket is unaffected by the namespace root",
   [p for p, _ in no_core["by_name"]] == [p for p, _ in with_core["by_name"]]
   == ["system/network/ping"])

# ---------------------------------------------- 3. concentration and joint declarers
r = run({"specs/extensions/EXTENSION-NETWORK.md":
         'type: "system/peer/status"\ntype: "system/peer/session"\n',
         "specs/extensions/EXTENSION-RELAY.md":
         'type: "system/peer/inbox-relay"\n',
         "specs/extensions/EXTENSION-TREE.md":
         'type: "system/tree/snapshot"\n'},
        core="system/peer is core's\n")
conc = r["concentrations"]
ok("the unresolved paths group under one namespace",
   list(conc) == ["peer"] and len(conc["peer"]["paths"]) == 3, conc)
ok("...and every declaring document is named, because that is the finding",
   conc["peer"]["declared_by"] == ["EXTENSION-NETWORK", "EXTENSION-RELAY"],
   conc["peer"]["declared_by"])
ok("a by-name path never appears in a concentration",
   all("tree" not in k for k in conc), conc)

r2 = run({"specs/extensions/EXTENSION-QUERY.md": 'type: "system/envelope"\n',
          "specs/extensions/EXTENSION-TREE.md": 'type: "system/envelope"\n'})
ok("one path declared by two documents is reported as joint",
   r2["joint_declarers"].get("system/envelope")
   == ["EXTENSION-QUERY", "EXTENSION-TREE"], r2["joint_declarers"])

# ---------------------------------------------- 3b. the SUBJECT axis
# The first cut of `shape` knew only the topic axis and reported every
# subject-indexed path as a lookup failure. `system/peer/*` is keyed by peer id
# (`status/{peer_id}`, `transport/{peer_id}/{protocol}`) and grouping it by
# mechanism would BREAK the property that everything about one peer is one prefix.
def subj_run(files, core=None):
    root, ns = corpus(files, core)
    types = shape.declared_types(root, ["specs"])
    stems = shape.spec_stems(root, ["specs"])
    segs = {p.split("/")[1] for p in types if "/" in p[7:]}
    smap = {s: m for s in sorted(segs) if (m := shape.subject_members(root, ["specs"], s))}
    return shape.analyze(types, stems, shape.core_segments(ns),
                         is_subject=lambda s: s in smap, subject_member_map=smap)

files = {"specs/extensions/EXTENSION-NETWORK.md":
         'type: "system/peer/status"\n\nstored at `system/peer/status/{peer_id}`\n'
         'type: "system/peer/transport/quic"\n\nat `system/peer/transport/{peer_id}/{protocol}`\n'}
r = subj_run(files, core="core reserves system/peer/\n")
ok("a peer-keyed namespace lands in `subject`, not `core-owned` or `unresolved`",
   len(r["subject_indexed"]) == 2 and r["core_owned"] == [] and r["unresolved"] == [], r)
ok("...and its subject-keyed MEMBERS are named, not just the segment",
   r["subject_namespaces"]["peer"]["members"] == ["status", "transport"],
   r["subject_namespaces"])
ok("a subject namespace never appears in the concentration (failure) report",
   "peer" not in r["concentrations"], r["concentrations"])

# Member granularity: a topic namespace may carry ONE subject-keyed member, and
# reporting the whole segment as a subject index over-claims.
root, _ = corpus({"specs/extensions/EXTENSION-ROLE.md":
                  'type: "system/capability/policy"\n\n'
                  '`system/capability/policy/{peer}` and `system/capability/grants/{pattern}`\n'
                  'and `system/capability/revocations/{hash}`\n'})
ok("only the peer-keyed member is reported, not its topic-keyed siblings",
   shape.subject_members(root, ["specs"], "capability") == ["policy"],
   shape.subject_members(root, ["specs"], "capability"))

root, _ = corpus({"specs/extensions/EXTENSION-REVISION.md":
                  'type: "system/revision/entry"\n\n`system/revision/entry/{hash}`\n'})
ok("a hash-keyed member is NOT a subject index",
   shape.subject_members(root, ["specs"], "revision") == [],
   shape.subject_members(root, ["specs"], "revision"))

# ---------------------------------------------- 4. it is a READER, always
rc = shape.main([str(corpus({"specs/extensions/EXTENSION-TREE.md":
                            'type: "system/nowhere/x"\n'})[0])])
ok("exits 0 even with an unresolved path — advisory, never a gate", rc == 0, rc)
rc = shape.main([str(Path(tempfile.mkdtemp()))])
ok("an empty corpus is could-not-look and still exits 0", rc == 0, rc)

print()
if FAIL:
    print("shape self-test: %d FAILED — %s" % (len(FAIL), ", ".join(FAIL)))
    sys.exit(1)
print("shape self-test: all assertions passed")
