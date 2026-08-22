# Entity System Architecture Tools

**The publishable spec toolkit.** A single CLI that reads, analyzes, and gates the Entity
specification corpus — structural trees, catalogs, the corpus dependency graph, the §11
addressing validator, and the corpus gates (naming + standards + internal coherence). It ships as its own
repo, decoupled from any spec version, so the spec repos and the tool that lints them evolve
independently.

> **No system usage.** Like every repo in the project, the toolkit runs **hermetically via
> `make` + `podman`** — there is no `pip install`, no system-Python dependency. One container
> image; the gates run inside it.

## What it does

One functional core, commands as pathways into it:

| command | purpose |
|---|---|
| `spec tree <file>` | structural tree of one spec (reader) |
| `spec render <file>` | catalogs of one spec (reader) |
| `spec topology` | corpus dependency graph (reader) |
| `spec address` | §11 addressing validator |
| `spec standards` | release-readiness / standards gate (**baseline-ratcheted** — see below) |
| `spec coherence` | internal-consistency gate — reads each spec against itself |
| `spec style` | naming-convention gate |
| `spec check` | run both gates (exits non-zero on violations) |

Stdlib-only Python; the reader commands always exit 0, the gates exit non-zero on violations.

### The standards baseline ratchet

Five `standards` rules flag process narrative fossilized into normative text — which
implementation built a thing, on what date, argued by whom. They are the difference between a
spec and a lab notebook.

All five were `warn` for months and were firing correctly the whole time: on the arch corpus,
**573 findings across 26 of 40 specs, in runs that printed `✓ all gates passed`.** They are now
`error`, with a ratchet so the promotion is survivable:

```
spec standards                  # known debt held; anything NEW is an error
spec standards --init-baseline  # accept today's debt (one-time)
spec standards --update-baseline  # lower the baseline; REFUSES to raise it
spec standards --no-baseline    # the full un-ratcheted state
```

The baseline lives with the corpus it describes (`<corpus>/.spec-baseline.json`), not in this
repo. `--update-baseline` may only ever lower a count and refuses atomically to raise one —
without that asymmetry the next contaminated commit re-baselines itself green and the run looks
clean.

**Known blind spot:** entries are keyed `(file, rule) → count`, so a *swap* is invisible — remove
one violation, add a different one in the same file, and the count is unchanged. Line numbers
were rejected as a key because every edit above a finding moves it. This catches **accumulation,
not substitution**; a reviewer still reads the diff.

## Usage

```
make check CORPUS=/path/to/spec-repo         # run both gates locally
make check-podman CORPUS=/path/to/spec-repo  # run both gates hermetically (one container)
make topology CORPUS=…                       # corpus graph
make render SPEC=…                           # catalogs for one spec
```

Or straight from inside the corpus, which is where you usually are:

```
cd /path/to/spec-repo && python3 /path/to/spec-tool/cli.py check
```

It lints a **target spec repo** (`entity-core-protocol` / `entity-system-architecture`), supplied
as the corpus root. The corpus resolves as `--corpus PATH` → `$SPEC_CORPUS` → the working
directory — **never** from the tool's own location, which this repo shares with no corpus.

Gate exit codes are three-valued, and the third one matters: **0** looked and found nothing,
**1** found violations, **2** could not look (empty corpus / bad root). A gate that scanned zero
files has not passed.

## License

Tooling is code: **Apache-2.0** (the project's code license). Distinct from the spec corpora it
operates on (which are dual-licensed CC-BY-ND-4.0 / Apache-2.0).

---

## Supporting the project

This project is developed in the open. If it's useful to you, the best support is
to use it, report issues, and contribute back — see
[CONTRIBUTING.md](CONTRIBUTING.md).

To support the work directly, see the project's funding page.
