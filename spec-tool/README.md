# `spec` — the unified spec toolkit (v2)

One tool, one functional core, commands as pathways into it. The five former
standalone scripts (`tools/spec-*/`) are **retired** — folded into this package,
proven byte-for-byte equivalent by `tests/parity.sh` before removal.

## Layout

```
  config.py / config.default.toml  ── single source of truth (roots, excludes, vocabulary, scopes, policy)
  model.py                         ── the parser: Node tree + Blocks + refs + §-attribution API
  render.py topology.py            ── readers over the model + corpus
  address.py                       ── §11 addressing validator + worklist emitter
  standards.py style.py            ── gates (exit non-zero on violations); style keeps its own lexer
  corpus.py                        ── gate over test-vector ARTIFACTS (.diag/.cbor), not prose
  cli.py                           ── one entry point; subcommands delegate to the modules
  Containerfile                    ── the one hermetic image
  tests/parity.sh + tests/golden/  ── the regression oracle (output-pinning)
  tests/address_selftest.py        ── address invariant checks (behavior-pinning)
  tests/corpus_selftest.py         ── corpus gate invariant checks (behavior-pinning)
```

## Commands

    spec tree <file> [--symbols|--refs|--json|--level N]   structural tree (reader)
    spec render <file> [--what …|--format …|--output …]    catalogs (reader)
    spec topology [ROOT] [--json|--dot]                    corpus graph (reader)
    spec address [ROOT] [--worklist OUT|--gate|--json|--batch-by U]   §11 addressing validator
    spec standards [--root …|--refine|--json]              release-readiness gate
    spec style [--root …|--all|--json|--config …]          naming gate
    spec corpus [--root …|--vendor …|--json]               test-vector artifact gate
    spec check                                             run both gates
    spec config [CONFIG.toml]                              print the resolved config

Run as `python3 tools/spec/cli.py <subcommand> …`, or via `make` from `tools/`
(`make check`, `make topology`, `make render SPEC=…`, …). One podman image;
`make check-podman` runs the gates hermetically.

### `spec corpus` — the artifact gate

The other gates read prose. This one reads the `.diag` source and the `.cbor`
build product implementations actually load. It exists because `test-vectors` is
in `exclude_dirs` for *every* prose scope, so the corpus was not merely unlinted
— it was **unreachable**, and every defect it ever carried was outside the
toolkit by construction.

It checks: version stamps in corpus directory and artifact names; an artifact
filed under the wrong corpus noun; an incomplete `.diag`/`.cbor` pair;
placeholder text (`TBD-…`) surviving into either member; declared fixture widths
(`agility-SEEDS.md` §2's own declarations, moved into config) in **both**
members; and the two members disagreeing with each other.

`--vendor PATH` gates a vendored copy in another tree and diffs it against the
source, byte for byte, matching by filename. It is **read-only** and takes an
explicit path — a vendor lives in another team's repo, so drift there routes, it
is never edited from here. A filename that matches two source files is reported
as ambiguous rather than silently paired against one of them.

`corpus` is deliberately **not** part of `check`: `check` is the two prose gates
and runs against every spec repo, while only `entity-core-protocol` carries
test-vectors. It joins `check` when the corpus is de-versioned to one tree.

## Status — unified tool built; standalones retired

Done:
- **Phase 0** — `tests/parity.sh` + `tests/golden/`: the regression oracle. 22
  cases (per-spec readers × 3 representative specs + the corpus commands), each
  freezing exact stdout + exit code. `verify` fails on any byte/exit drift.
- **Phase 1** — `config.py` + `config.default.toml`: one source of truth for
  roots, excludes, and vocabulary (was scattered constants).
- **Phases 3+4 (built together)** — `model.py` is the one parser; `render` /
  `topology` read it; `standards` / `style` are gates; `cli.py` dispatches. The
  golden was captured from the five standalone tools; the unified CLI reproduces
  every case **byte-for-byte** (`tests/parity.sh verify`), so the standalones
  were removed. Config still encodes today's three-way scope reality as distinct
  profiles (`DELTA(phase2)` markers) — output is unchanged.

Deliberately deferred: start with **standalone configs**; config composition
(`extends`, the spec-format ⊂ core-protocol ⊂ entity-system layering) is a later
feature.

## Next

- **Phase 2** — reconcile the `DELTA(phase2)` calls (changes output; per-delta
  review against the parity oracle).
- **Phase 3 (deeper)** — observation→policy layer + suppressions;
  block bodies/extents in the model so `render` reads the model, not source.
- **Phase 5** — `spec report` (release pipeline); then the spec cleanup worklist
  runs on the unified tool.

## Addressing validator (`spec address`)

Enforces `SPECIFICATION-FORMAT.md` **§11** (Addressing and Cross-References):
canonical external citation is `DOC.md §N.M`; a bare `§N.M` is same-document; a
prose name (`V7`) is not a citation. It finds, classifies, and gates deviations,
and emits **self-contained finding packets** (`--worklist OUT.jsonl`) for the
multi-pass correction pipeline. Classes: `drift` / `nickname` (mechanical) and
`bare-internal` / `leak` / `stale-section` / `dangling` (judgment). It resolves
targets against a wide *namespace* scope but is strict over the *analysis* scope,
and uses document **class** (§11.3) to tell a leak (normative→process artifact)
from permitted provenance (arch-doc→exploration). **Read-only** — it never edits.

`--gate` is the **G1** mechanical re-run (exit non-zero on any deviation) the
correction pipeline verifies against.

`address` is intentionally **not** in `parity.sh` — its output changes every
correction pass. Its contract is pinned by `address_selftest.py` instead.

## Running the oracle

```sh
bash tests/parity.sh verify           # unified CLI still matches golden (regression gate)
bash tests/parity.sh capture          # re-baseline — only for an intended, reviewed output change
python3 tests/address_selftest.py     # address behavior invariants (14 checks)
python3 tests/corpus_selftest.py      # corpus gate behavior invariants (synthetic fixtures)
```
