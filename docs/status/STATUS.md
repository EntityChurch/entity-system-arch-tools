# entity-system-arch-tools — status

_Updated: 2026-08-22 · public: v0.8.1 (master)_

## Where it is

The **publishable spec toolkit** for the Entity ecosystem — a single, stdlib-only
Python 3.11+ CLI (`spec`) that reads, analyzes, and gates the Entity specification
corpus. One functional core (`spec-tool/model.py`: a node tree + typed blocks +
refs + a `§N.M`-attribution API) is parsed once per spec, and every subcommand is a
pathway into that one model:

- **Readers** (always exit 0): `tree` (structural node tree of one spec), `render`
  (its type / algorithm / constants / conformance catalogs), `topology` (the
  cross-spec dependency graph — in/out-degree, dangling citations, form drift,
  stale section refs).
- **Gates** (non-zero exit on violations): `standards` (release-readiness — clean
  header, declared Status/Depends, no process narrative fossilized into normative
  text, reported with `file:line`) and `style` (the identifier naming gate, which
  keeps its own lexer for `~~~` fences + inline spans the structural model doesn't
  track). `check` runs both.
- **Analyzer**: `address`, the `SPECIFICATION-FORMAT.md` **§11** addressing
  validator (see below).
- `config` prints the resolved configuration.

It carries **no spec corpus of its own** — the readers and gates run against a
corpus you point them at (`--root`, or a `podman` bind-mount at `/work`), so the
tool and the spec repos it lints evolve **independently and version-decoupled**.
It runs **hermetically** via `make` + `podman` (one container image,
`spec-tool/Containerfile`) or **host-native** against `python3` — no `pip install`,
no third-party deps.

**How it got here.** The toolkit is the *unification* of five former standalone
scripts (the separate tree / render / topology / standards / style tools) into one
package. The merge was done behind a regression oracle: `tests/parity.sh` froze the
exact stdout + exit code of the old tools across **22 golden cases** (the per-spec
readers over three representative fixture specs + the corpus-wide commands), the
unified CLI was proven **byte-for-byte equivalent**, and only then were the
standalones retired. Build order on the record: Phase 0 = the parity oracle; Phase 1
= `config.py` + `config.default.toml` as the single source of truth (roots,
excludes, vocabulary, scopes, policy — was scattered constants); Phases 3+4 (built
together) = the shared `model.py` parser, the readers and gates over it, and the
`cli.py` dispatcher.

The `address` analyzer is the most specialized piece. It enforces §11's citation
form (canonical external citation `DOC.md §N.M`; a bare `§N.M` is same-document; a
prose name is not a citation), classifying deviations into **mechanical** classes
(`drift`, `nickname`) and **judgment** classes (`bare-internal`, `leak`,
`stale-section`, `dangling`) — resolving targets against a wide *namespace* scope
while gating strictly over the *analysis* scope, and using document **class** to
distinguish a real leak (normative spec → process artifact) from permitted
provenance. It emits **self-contained finding packets** (`--worklist OUT.jsonl`) to
drive a multi-pass correction pipeline, and `--gate` is the mechanical re-run that
pipeline verifies against. It is **read-only by contract** — it never edits the
corpus. Because its output changes on every correction pass it is deliberately
**not** in the parity set; its contract is pinned by `tests/address_selftest.py`
instead. The `standards` gate also ships a `--refine` mode: a *safe* auto-fixer
that collapses a changelog-blob Version header to a bare version and drops a
trailing Document History section, never touches inline prose, and writes a cleaned
**copy** (source untouched).

**Maturity: public research-preview, v0.8.1.** The CLI, the readers, the addressing
validator, the parity oracle (`make parity`) and the per-analyzer self-tests are all in
place and exercised. `0.8.1` adds seven analyzers — `coherence`, `convergence`, `corpus`,
`ledger`, `provenance`, `coverage` and `sdksync` — each with its own self-test and `make`
target, and fixes the corpus-resolution defect described below. The tool has already been used
in anger to drive real release-readiness cleanup over multi-spec corpora — producing
authoritative `file:line` worklists rather than hand-grep — which is what hardened
the gate rules and the addressing classifier.

## Where we left off

**`0.8.1` is cut.** The headline of it is a correctness fix, not the new surface: the gates
could not reach any corpus and did not say so — the corpus root was derived from a path that
exists in no post-split checkout, so `standards` scanned zero files and reported `0 error(s)`
with exit 0. A gate that passes because it is looking at nothing is worse than one that
fails. `standards` now exits **2** (could-not-look) rather than 0 when it cannot reach a
corpus, and `check` reports `could-not-look` distinctly from `fail`.

`entity-system-arch-tools` tracks its **own** version line from `0.8.1` onward. It shares no
release cadence with `entity-core-protocol`; a matching third component between the two is
coincidence, not correspondence.

## Backlog

- ⛔ **A `§9` conformance-floor row and the `§1.4` rule it restates drifted TWICE in TWO folds — a
  co-change check is owed, and it has two known-positive validation inputs.** `ENTITY-CORE-PROTOCOL`'s
  §9 core-floor list restates normative rules defined elsewhere in the same document, and **neither end
  said it was a copy**, so a fold that corrected §1.4 left §9 publishing the superseded rule. Twice, at
  the same row: the two-arm PD-2 opener (caught by `entity-core-go`) and the multi-signature conditional
  (caught by `entity-core-keystone`). **Both were found by seats reading the floor, because the floor is
  what an implementation builds from — never by us.**
  **The check is mechanical and needs no NLP:** a commit touching the §1.4 PD-2 region while leaving the
  §9 row untouched is a finding — the `provenance` two-part-trigger pattern, applied within one document.
  **Validate against both instances in `entity-core-protocol`'s history — the two-arm PD-2 opener fold
  and the multi-signature conditional fold — and against the one fold that DID move both §1.4 and its
  §9 restatement together, so it is exercised in both directions** before its first number is published.
  *Interim, already landed: the row now names §1.4 as its authority and states that §1.4 wins on
  disagreement — `L23`'s prescribed form. That makes the drift greppable; it does not gate it.*
- ⛔ **`address` — `_bare_internal` never resolves a section against a document named on
  the same line, and the false NEGATIVE is the expensive half.** `spec-tool/address.py`
  `_bare_internal()` returns clean whenever `sec in doc.sections` — *"conformant
  same-document section ref"* — **without ever checking the document the line actually
  names.** So a cross-doc citation whose section number happens to also exist in the host
  document is graded against the wrong document and reported clean. That is the mechanism
  behind the limit already recorded in the arch repo's `AGENTS.md` (*"a citation that
  resolves to the wrong real section is invisible to every gate we have"*) — now located in
  code rather than described.
  **Live false POSITIVE, which is how it was found:** `ENTITY-CORE-PROTOCOL.md:322` cites
  `EXTENSION-CONTINUATION.md §3.6b` — adjacent, qualified, and **the target exists**
  (*Advance authority*, normative v1.22, opened and read before citing). It is reported as
  `§3.6b not a section of host doc — broken self-ref`. The spec text was **left correct and
  the finding filed**, rather than reworded to green the gate.
  **Not a simple adjacency bug — a probe line of the identical shape
  (`EXTENSION-CONTINUATION.md §97.5`, absent from both documents) produces NO finding**, so
  binding to an external sibling doc works in the simple case and something about line 322's
  shape defeats the antecedent (a bare `§6.8` precedes the doc token; suspect the
  `governed_docs` / `ante` handling, not `SEC_RE`, which already accepts the `[a-z]?`
  suffix).
  **Validate any fix in BOTH directions against these three inputs** — the false positive,
  the silent false negative (cite `SIBLING.md §X` where `§X` exists in both), and the
  working probe — per the standing rule that a gate is replayed against the incident that
  motivated it before its next number is published.
- **Cut a versioned `CHANGELOG.md` entry for v0.8.0** — it is still under
  `[Unreleased]` as "Initial public research-preview release."
- **Phase 2 — reconcile the `# DELTA(phase2)` carry-overs** in
  `spec-tool/config.default.toml` (3 marked lines). These are intentional
  byte-for-byte hold-overs from the pre-unification configs that let the Phase-1
  refactor stay provably non-breaking; removing them is a reviewed, **output-affecting**
  change and must be re-baselined against the parity oracle per delta.
- **Phase 3 (deeper)** — an observation→policy layer with suppressions; modelling
  block bodies/extents so `render` reads the model rather than re-reading source.
- **Phase 5 — `spec report`** (a release pipeline command); then run the spec
  cleanup worklist on the unified tool end-to-end.
- **Extend the `standards` rule catalog** — it flags inline ISO dates but not other
  stamped provenance tokens that also must be stripped before publish; adding those
  to `RULES` lets the gate enforce the full "no dates / no provenance stamps"
  release rule mechanically instead of by hand.
- **Reconcile the `make check` name** — the domain gate `check` (style + standards)
  collides with the ecosystem-standard `check = lint + test`; the `Makefile` flags
  this as a separate, deliberate naming decision rather than papering over it.

## Waiting on

- **No hard blockers.** Meaningful gate/reader runs need a spec corpus to point at
  (a spec checkout supplied via `--root` / `CORPUS=`). Against this bare repo,
  `make config` / `make check` is a **zero-files smoke run** — that is expected, not
  a failure (the repo deliberately vendors no specs; the test fixtures under
  `spec-tool/tests/fixtures/corpus/` are the only specs present, and they exist to
  feed the parity oracle).
- **Operator decision** — which spec corpus is the canonical lint target for
  published gate runs.

## Done recently

- Public **v0.8.0** source release of the unified `spec` toolkit (the five former
  standalone tools folded into one parity-verified package; standalones retired).

## Next

1. Cut the `v0.8.0` `CHANGELOG.md` entry out of `[Unreleased]`.
2. Pick a canonical lint-target corpus and run `check` / `standards` / `address` as
   a published gate demonstration.
3. When prioritized: Phase 2 `DELTA(phase2)` reconciliation, each delta re-baselined
   against `make parity`.
