#!/usr/bin/env python3
"""spec — the unified spec toolkit CLI.

One functional core, commands as pathways into it. Replaces the five separate
scripts in `tools/spec-*/`. Each subcommand delegates to an analyzer module
that reads the one shared model (`model.py`) and the one config
(`config.py` / `config.default.toml`).

    spec tree <file> [--symbols|--refs|--json|--level N]   structural tree (reader)
    spec render <file> [--what …|--format …|--output …]    catalogs (reader)
    spec topology [ROOT] [--json|--dot]                    corpus graph (reader)
    spec coverage [ROOT] [--gaps|--json]                   spec -> guide/proposal/research (reader)
    spec address [ROOT] [--worklist …|--gate|--json]       §11 addressing validator
    spec standards [--root …|--refine|--json]              release-readiness gate
    spec style [--root …|--all|--json|--config …]          naming gate
    spec coherence [--root …|--json]                       internal-consistency gate
    spec corpus [--root …|--vendor …|--json]               test-vector artifact gate
    spec convergence [--window N|--json]                   spec rate-of-change + pipeline
    spec charter [--charter …|--agents …|--json]           the discipline set, both homes
    spec expiry  [--gate|--owed|--json]                    tracker rows whose EVIDENCE died
    spec ledger [--root …|--json]                          declared counts vs the directories
    spec register [--gate|--owed|--json]                   design docs findable by the QUESTION
    spec inbound [--gate|--owed|--peers D|--json]          packets addressed to us vs our ledger
    spec inventory [--gate|--owed|--update-baseline]        conformance rows: addressable, or only quotable
    spec declare [--gate|--owed|--update-baseline]          the §3.3 dependency contract, all seven fields
    spec census [--doc …|--drift|--gaps|--json]            normative surface vs the cohort's own citations
    spec sdksync [--root …|--json|--unpinned|--update]      SDK restatements vs their sources
    spec provenance [--since REF|--proposal-root R|--json] L1: normative spec edit needs a proposal
    spec check                                             run all three gates (style + standards + coherence)
    spec config [CONFIG.toml]                              print the resolved config

Any invocation may lead with `--corpus PATH` to name the corpus to analyze
(equivalently `$SPEC_CORPUS`; default: the working directory). This repo ships
no corpus — you always point the tool at one.

Gates (`standards`, `style`, `corpus`, `check`) exit **1** on violations and **2**
when they could not look (empty corpus / bad root); readers always exit 0. Those
two are not the same result and are not reported as the same result.

`corpus` is deliberately NOT part of `check`. `check` is the two prose gates, run
against every spec repo; `corpus` gates binary artifacts and only
`entity-core-protocol` has any. Folding it in would either force `check` to
report could-not-look on a prose repo, or teach it to shrug at an absent scope —
and a gate that learns to shrug is the failure mode this toolkit was built
against. It joins `check` when the corpus is de-versioned to one tree and every
spec repo can answer for it.

Stdlib-only Python 3.11+. Run as `python3 tools/spec/cli.py <subcommand> …`.
"""

import os
import sys
from pathlib import Path

import config as _config

# `--corpus PATH` is honoured BEFORE the analyzer modules are imported: each of
# them resolves its default scope root at import time, so an env var set later
# (in main) would arrive after the decision it governs. Reading argv here is the
# price of that import-time resolution; the alternative is making four modules'
# scope defaults lazy, which is the phase-2 cleanup.
if len(sys.argv) > 2 and sys.argv[1] == "--corpus":
    os.environ[_config.CORPUS_ENV] = sys.argv[2]

import address
import coherence
import convergence
import corpus
import coverage
import census
import charter
import expiry
import ledger
import inbound
import inventory
import declare
import register
import sdksync
import pins
import provenance
import model
import render
import standards
import style
import topology

# subcommand -> the module main(argv) it delegates to. Args after the
# subcommand are passed through verbatim, so each command behaves exactly as
# its former standalone script did.
DELEGATES = {
    "tree": model.main,
    "render": render.main,
    "topology": topology.main,
    "address": address.main,
    "standards": standards.main,
    "coherence": coherence.main,
    "style": style.main,
    "corpus": corpus.main,
    "convergence": convergence.main,
    "coverage": coverage.main,
    "census": census.main,
    "charter": charter.main,
    "expiry": expiry.main,
    "ledger": ledger.main,
    "inbound": inbound.main,
    "inventory": inventory.main,
    "declare": declare.main,
    "register": register.main,
    "sdksync": sdksync.main,
    "provenance": provenance.main,
    "pins": pins.main,
}


def cmd_check(argv):
    """Run the three corpus gates (style + standards + coherence), like `make check`.

    Non-zero exit if any gate reports violations. Output is each gate's own
    report, in order, separated by a banner — a convenience over running the
    subcommands by hand; the per-gate output is byte-identical to running them
    individually.

    `coherence` joined on 2026-08-14. `style` reads a spec's names and
    `standards` reads its shape; neither reads a spec against *itself*, which
    is where the expensive defects were living — a `MUST` naming a helper the
    corpus never defines, a value emitted for a field whose declared
    enumeration omits it. Both families shipped, passed prose review, and were
    found by an implementer building the section, after the divergence had been
    routed at an innocent peer.

    Exit codes are three-valued, and the distinction is load-bearing:
    0 = every gate looked and found nothing; 1 = a gate found violations;
    2 = a gate could not look (empty corpus). Collapsing 2 into "fail" is how
    a stale corpus root read as a lint failure for a year — the report named
    the wrong defect, so nobody went looking for the right one."""
    if argv:
        print("spec check takes no arguments", file=sys.stderr)
        return 2
    print("=== spec style ===")
    rc_style = style.main([])
    print("\n=== spec standards ===")
    rc_standards = standards.main([])
    print("\n=== spec coherence ===")
    rc_coherence = coherence.main([])

    def verdict(rc):
        return "could-not-look" if rc == 2 else ("fail" if rc else "pass")

    rcs = (rc_style, rc_standards, rc_coherence)
    summary = ("style=%s standards=%s coherence=%s"
               % (verdict(rc_style), verdict(rc_standards), verdict(rc_coherence)))

    if 2 in rcs:
        print("\n✗ a gate could not look — %s" % summary)
        print("  This is NOT a lint failure: a gate scanned zero files. Fix the corpus")
        print("  root (`spec --corpus PATH check`, $SPEC_CORPUS, or run from the corpus)")
        print("  and re-run before reading anything into any of the results.")
        return 2

    rc = 1 if any(rcs) else 0
    print("\n%s — %s"
          % ("✓ all gates passed" if rc == 0 else "✗ a gate failed", summary))
    return rc


def cmd_config(argv):
    """Print the resolved config (which root, excludes, vocabulary, scopes).

    Transparency / debugging — answers "what corpus does the tool actually see
    with this config?". Optional positional: a config.toml to resolve instead
    of the bundled default."""
    if len(argv) > 1:
        print("usage: spec config [CONFIG.toml]", file=sys.stderr)
        return 2
    cfg = _config.load(Path(argv[0]) if argv else None)
    print("repo_root  :", cfg.repo_root)
    print("corpus_dir :", cfg.corpus_dir)
    print("type_roots :", sorted(cfg.type_roots))
    print("doc_families : %d" % len(cfg.doc_families))
    print("classes    :", cfg.classes)
    for name in cfg._d.get("scope", {}):
        sc = cfg.scope(name)
        print("scope %-20s root=%s  files=%d" % (
            name, sc.root.relative_to(cfg.repo_root), len(sc.find_markdown())))
    return 0


EXTRA = {"check": cmd_check, "config": cmd_config}


def usage(stream=sys.stdout):
    print(__doc__.strip(), file=stream)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # `--corpus PATH` may lead any invocation: it names the corpus this run
    # analyzes. It is set into the environment before the analyzer modules read
    # their scope defaults, which they do at import time. Precedence is
    # --corpus > $SPEC_CORPUS > cwd (see config.corpus_root).
    if argv and argv[0] == "--corpus":
        if len(argv) < 2:
            print("--corpus needs a PATH", file=sys.stderr)
            return 2
        os.environ[_config.CORPUS_ENV] = argv[1]
        argv = argv[2:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        usage()
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd in DELEGATES:
        return DELEGATES[cmd](rest)
    if cmd in EXTRA:
        return EXTRA[cmd](rest)
    print("unknown command: %s" % cmd, file=sys.stderr)
    print("commands: %s" % ", ".join(list(DELEGATES) + list(EXTRA)), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
