# entity-system-arch-tools — AGENTS.md

Read **AGENTS-STANDARD.md** first. This file adds entity-system-arch-tools specifics.

## Overview

The **publishable spec toolkit** — a single CLI that reads, analyzes, and gates the
Entity specification corpus: structural trees, catalogs, the corpus dependency graph,
the §11 addressing validator, and the corpus gates (naming + standards + internal coherence).
One functional core (`spec-tool/model.py`), with commands as pathways into it.

This is one slice of the architecture three-way split: it is **tooling over the spec**,
not the spec. It carries **no spec corpus of its own** — the gates and readers run
against a corpus you point them at (`--root` / a bind-mount), so the tool and the spec
repos it lints evolve independently and version-decoupled. The public repo name is
`entity-system-arch-tools` (it was split out from the former `entity-core-architecture`).

## How we work here — tier **CORE**

This repo runs the entity-OS methodology at the **Core** tier — the framework is
`METHODOLOGY.md` (injected, identical everywhere; read it once). Conformance gates the wire
here. It does **not** catch process drift, stale build-state claims, unaccounted accumulation,
or a discipline quietly eaten by a competing legitimate pressure. Those need the ratchet.

What binds today:

- **Universal disciplines D1–D12** (`METHODOLOGY.md` §4) — apply as written; nothing to re-derive.
- **The review questions** (§6) — run on every diff.
- **The Audit Doctrine A0–A12** (§7.2) — open it for *"Y is broken"* or *"something feels
  wrong,"* including when the thing that feels wrong is our own process. **A1 is the prime:
  trace a value before you theorize.** The Foundation Audit Doctrine (§7.3) when opening a new
  surface to design against.
- **The ratchet** — every audit ends by syncing what it taught into this file, same session.
  **If it didn't land here, it didn't land.**
- **The promotion ladder** (§3) — bit us once → an anti-pattern entry; a second time in a
  different shape → a ratified discipline. Candidates are applied, not yet claimed to generalize.
  **A discipline with no enforcement point is theater** — name the grep, the lint rule, or the
  gate test.

**Owed:** a standing `DISCIPLINE-*` doc with an anti-pattern catalog. This repo has already
paid for its first native discipline and it should be written down: **a gate that cannot reach
its corpus must not be readable as a pass.** Exit codes are three-valued — 0 clean, 1
violations, **2 could-not-look** — and a `2` was read as both a pass and a lint failure for
months against a corpus root left behind by the repo split (fixed in `7fd538f`). The general
form: any tool whose output gates someone else's work must make "I didn't actually look"
structurally distinguishable from "I looked and it was fine." The ratcheted-baseline pattern
this repo implements (`.spec-baseline.json`, which only ever lowers a count and refuses to
raise one) is named in `METHODOLOGY.md` §10 as the ecosystem's preferred enforcement rung —
changes to it are changes to a shared mechanism.

## Setup / environment

- **Stdlib-only Python 3.11+** — no `pip install`, no third-party deps. The CLI imports
  only its own sibling modules.
- **Hermetic via `make` + `podman`** (host needs only `make` + `podman`, per
  AGENTS-STANDARD). One container image (`spec-tool/Containerfile`, `python:3.12-slim`);
  the gates run inside it. `make build` builds the image; `make check-podman` runs it.
- You can also run host-native against `python3` (`make check`, `make tree`, …).

## Build & test

All targets are in `Makefile` (run `make help` for the live list):

```bash
make check CORPUS=<path>   # run all three gates (style + standards + coherence), host python3
make check-podman CORPUS=… # same, hermetic (one container)
make style CORPUS=<path>   # naming gate only
make standards CORPUS=…    # release-readiness gate only
make coherence CORPUS=…    # internal-consistency gate only
# CORPUS is required in practice: unset, it points at this repo, which carries no
# specs/ — the gates then exit 2 (could not look), which is the intended answer.
make tree SPEC=<spec.md>   # structural node tree of one spec (reader)
make render SPEC=<spec.md> # every catalog of one spec, --what all (reader)
make topology              # corpus dependency graph (reader)
make config                # print the resolved config
make parity                # unified CLI == golden fixtures (regression oracle)
make compile               # byte-compile the spec-tool package (sanity)
make build                 # build the podman image (entity-spec:latest)
make clean                 # remove the image
```

- **Gates exit non-zero on violations** (`check`, `style`, `standards`, `coherence`); **readers always
  exit 0** (`tree`, `render`, `topology`, `config`).
- `make parity` is the **regression oracle** — `spec-tool/tests/parity.sh verify` replays
  22 fixed cases under `spec-tool/tests/golden/` and fails on any byte/exit drift. **Run it
  after any change that could alter tool output.** Only re-baseline (`parity.sh capture`)
  for an intended, reviewed output change.
- `python3 spec-tool/tests/address_selftest.py` runs the `address` behavior invariants
  (`address` is deliberately **not** in the parity set — its output changes every
  correction pass, so its contract is pinned by the self-test instead).

## The CLI (`spec`)

Run as `python3 spec-tool/cli.py <subcommand> …` (or via the `make` targets above).
`cli.py` is the one entry point; each subcommand delegates to its module.

| command | purpose |
|---|---|
| `spec tree <file>` | structural tree of one spec (reader) |
| `spec render <file>` | catalogs of one spec (reader) |
| `spec topology [ROOT]` | corpus dependency graph (reader) |
| `spec address [ROOT]` | §11 addressing validator + worklist emitter (read-only) |
| `spec standards` | release-readiness / standards gate |
| `spec coherence` | internal-consistency gate — reads each spec against itself |
| `spec style` | naming-convention gate |
| `spec check` | run both gates (non-zero exit if either fails) |
| `spec config [CONFIG.toml]` | print the resolved config |

## Project structure (`spec-tool/`)

- `cli.py` — the one entry point; subcommands delegate to the modules.
- `model.py` — the parser: Node tree + Blocks + refs + §-attribution API (the shared core).
- `render.py`, `topology.py` — readers over the model + corpus.
- `address.py` — §11 addressing validator; emits self-contained finding packets for the
  correction pipeline. **Read-only — it never edits.**
- `standards.py`, `style.py`, `coherence.py` — the gates (non-zero exit on violations); `style` keeps its
  own lexer.
- `config.py` + `config.default.toml` — single source of truth (roots, excludes,
  vocabulary, scopes, policy). A different corpus is a different copy of this file
  (`spec --config FILE`). Lines tagged `# DELTA(phase2)` mark inconsistencies preserved
  byte-for-byte on purpose (the Phase-1 refactor is provably non-breaking).
- `Containerfile` — the one hermetic image.
- `tests/parity.sh` + `tests/golden/` — the regression oracle (output-pinning).
- `tests/address_selftest.py` — address invariant checks (behavior-pinning).

See `spec-tool/README.md` for the full module map and command flags.

## Boundaries — do NOT modify

- **This is tooling over the spec — it reads the spec, it does not define it.** The Entity
  spec corpus is upstream and lives in the spec repos; do not add spec content, wire
  formats, or normative rules here. Bugs in what the tool *reports* are tool bugs; gaps in
  what the spec *says* route upstream (AGENTS-STANDARD §Working across the polyrepo).
- **No spec corpus in this repo.** Don't vendor specs in; point the gates at a corpus via
  `--corpus PATH` / `$SPEC_CORPUS` / `CORPUS=` (host-native and bind-mount alike), or run from
  inside the corpus. The corpus root is **never** derived from the tool's own location — it was
  until the repo split, and the stale path left behind is the defect below.
- **Zero files in scope is a reader's smoke run and a gate's hard error.** `make config` /
  `topology` against this bare repo legitimately report an empty corpus. A **gate** never does:
  `standards` / `style` / `coherence` / `check` exit **2** (could not look), distinct from **1** (violations).
  The distinction is load-bearing, not cosmetic — collapsing it is what let a post-split corpus
  root survive: `standards` printed `0 error(s)` over **zero files** and exited 0, while `check`
  reported `style=fail` for a root that did not exist. Both reports named a defect that was not
  the defect. **Never reintroduce a path where a gate can pass, or report a violation, without
  having scanned anything.**
- **`spec-tool/tests/golden/` is frozen test data**, captured from the legacy standalone
  tools. Do not hand-edit it to "fix" stale strings or paths inside the fixtures — that is
  the parity oracle; only `parity.sh capture` (a reviewed re-baseline) may regenerate it.
- **`spec address` is read-only by contract** — keep it that way; it analyzes and emits
  worklists, it never edits the corpus.

## Commit & PR

Default branch **`master`**; DCO sign-off required — see AGENTS-STANDARD.

**Committing and pushing this repo is standing authorization — do not ask.** Push target is
**`origin`** (the operator's internal mirror) — plain `git push`, never `github` or `codeberg`,
which are not an agent's to publish to. Never force-push. `make test` green before the commit.
Canonical statement in `entity-system-architecture/AGENTS.md`.
