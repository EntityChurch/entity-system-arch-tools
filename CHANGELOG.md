# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`spec disclose` — does a core fold say which conformance cells it crosses?** The
  enforcement point for `GUIDE-CONFORMANCE` §5.3a: a proposal folding a normative change
  into the core protocol carries a `Cell disclosure` naming the cells its deltas touch and
  each one's drive state, read from the conformance anchor's scope table and cited as
  `(repo, commit, date)`. **An undriven cell does not block a fold; an undisclosed one
  does.** Four findings: `disclosure-missing`, `disclosure-unsourced`, `disclosure-empty`,
  `disclosure-state-unknown`.

  It checks the **shape** and never the truth of a state — whether a cell disclosed
  `driven` really is verifiable only by the party that runs the checks, and the rule says so
  rather than implying otherwise.

  **Scope is two rules.** A *landed* fold is scoped by the revision it landed as
  (`--binds-from`, default `0.8.2.32`), so revisions predating the rule are out of scope by
  the rule rather than by a baseline. A *pending* fold is in scope whatever revision its
  header currently writes, because the binding line is the head of the spec and anything
  still to land lands past it — and two live core proposals name only the revision they
  *correct*, so scoping on the written number alone under-reports in the silent direction.

  Takes `--peer-root` and prints the roots it searched: the proposals for one corpus may be
  authored in the other, and a run resolving one root grades half the channel. A named root
  that does not exist is could-not-look, never a silent skip. Validated against the incident
  that motivated the rule in both directions before publishing a number.

## [0.8.1] — 2026-08-22

Seven new analyzers, a corpus-resolution fix that made the existing gates honest, and the
first release cut on this project's own version line.

**Versioning note.** `entity-system-arch-tools` tracks its own version from `0.8.1` onward.
It shares no release cadence with `entity-core-protocol`; the two lines are independent, and
matching third components between them are coincidence, not correspondence.

### Fixed

- **The gates could not reach any corpus, and did not say so.** The corpus root was derived
  from the tool's own location plus a path (`docs/architecture/v7.0-core-revision`) that
  exists in no post-split checkout, so `standards` scanned zero files and reported
  `0 error(s)` / exit 0, while `check` reported `style=fail` for a root that was absent.
  The corpus now resolves as `--corpus PATH` → `$SPEC_CORPUS` → the working directory, and
  the default scopes match the post-split layout (`specs/` at the corpus root) shared by
  `entity-core-protocol` and `entity-system-architecture`.
- **A gate that scans zero files no longer passes.** `standards` exits **2** (could not look)
  instead of 0, and `check` reports `could-not-look` distinctly from `fail` — a gate cannot
  report a result about a corpus it never opened.
- Findings print relative to the **corpus** root (`specs/extensions/X.md`) rather than to
  wherever the tool happens to be checked out.

### Added

- **`spec corpus` — a gate over test-vector artifacts** (`make corpus CORPUS=… [VENDOR=…]`).
  The other analyzers read prose; this one reads the `.diag` source and the `.cbor` build
  product implementations actually load. It exists because `test-vectors` sits in
  `exclude_dirs` for **every** prose scope (`core-specs`, `core-specs-strict`,
  `naming-surface`) — the corpus was not unlinted, it was *unreachable*, so a version-stamped
  directory name, a seven-week `SEEDS.md` gap, and a `.diag` carrying 58-byte Ed448 seeds
  beside a correct `.cbor` all sat outside the toolkit by construction. Rules:
  `corpus-version-stamp`, `corpus-name-mismatch`, `corpus-pair-incomplete`,
  `corpus-placeholder`, `corpus-fixture-width`, `corpus-pair-disagree`, plus `vendor-drift` /
  `vendor-ambiguous` / `vendor-unmatched` under `--vendor`. Declared fixture widths move from
  `agility-SEEDS.md` §2's prose into `[analyzer.corpus.fixture_widths]`, so what the gate
  enforces is the corpus's own declaration. Both checks the corpus's `SEEDS.md` already
  recorded as owed — *"worth a build-time assertion rather than a reader's diligence"* and
  *"if the two `.cbor` shas ever differ after this, that is the defect, and it is worth a
  check"* — are now the mechanism rather than a note. `--vendor` is read-only by design: a
  vendored copy lives in another team's tree, so drift there routes rather than being edited
  from here.
- `[scope.test-vector-corpus]` — the one scope that reaches into `test-vectors/`. The prose
  scopes still exclude it, and should: a `.diag` is not a spec and must not be graded as one.
- `tests/corpus_selftest.py` — 21 behavior invariants over synthetic fixtures built in a temp
  dir, including the shape that hid longest: a **correct `.cbor` beside a stale `.diag`**,
  where each member is individually plausible and only the comparison catches it.
- `--corpus PATH` on any invocation, `$SPEC_CORPUS`, and `CORPUS=` on every host-native gate
  target (previously only `check-podman` honoured a corpus).

### Notes

- `spec corpus` is **not** wired into `spec check`. `check` is the two prose gates and runs
  against every spec repo; only `entity-core-protocol` carries test-vectors, so folding it in
  would either make `check` report could-not-look on a prose repo or teach it to shrug at an
  absent scope. A gate that learns to shrug is the failure mode this toolkit was built
  against. It joins `check` when the corpus is de-versioned to one tree.
- `corpus` distinguishes **could-not-look** (corpus root absent → exit 2) from **not
  applicable** (root present, no `test-vectors/` → exit 0, stated explicitly). Collapsing
  those two is the same defect as collapsing could-not-look into fail.

## [0.8.0] — 2026-06-21

- Initial public research-preview release.
