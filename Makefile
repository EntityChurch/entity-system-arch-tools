# entity-system-arch-tools — the spec toolkit, one tool with command pathways.
#
# Everything routes through the unified CLI (spec-tool/cli.py); the old
# spec-* scripts are retired (parity-proven equivalent — see
# spec-tool/tests/parity.sh). This is a standalone tool repo: it carries no spec
# corpus itself — point the gates at a corpus you bind-mount (see check-podman).
#
#   make check CORPUS=<path>   run both gates locally (style + standards)
#   make check-podman CORPUS=… run both gates hermetically (one container)
#   make style CORPUS=<path>   naming gate only
#   make standards CORPUS=…    release-readiness gate only
#   make corpus CORPUS=…       test-vector artifact gate (VENDOR=… to diff a copy)
#   make convergence CORPUS=…  spec rate-of-change + the pipeline (reader)
#   make tree SPEC=<spec.md>   structural tree of one spec
#   make render SPEC=<spec.md> all catalogs of one spec
#   make topology              corpus dependency graph
#   make config                print the resolved config
#   make parity                verify the unified CLI matches the golden fixtures

PYTHON ?= python3
SPEC   ?=
VENDOR ?=
IMAGE  ?= entity-spec:latest
CLI    := spec-tool/cli.py

# This standalone repo IS the tool root and carries NO corpus. Every gate runs
# against a corpus you name: CORPUS=<path to a spec repo> (host-native and
# hermetic alike). It defaults to this repo only so an un-parameterized run
# fails loudly with "could not look" rather than silently scanning nothing.
REPO   := $(CURDIR)
CORPUS ?= $(CURDIR)
# Base ref for `provenance`. Generic on purpose: the backlog window is CORPUS
# knowledge, not tool knowledge -- arch records its own in DISCIPLINE-CHARTER.
SINCE  ?= HEAD~1

.PHONY: help check check-podman style standards corpus convergence tree render topology config \
        parity compile build clean test lint fmt

help:
	@echo "the unified spec toolkit (one tool, command pathways)"
	@echo
	@echo "gates (exit non-zero on violations):"
	@echo "  check           spec check (style + standards), host python3"
	@echo "  check-podman    same, hermetic (one container)"
	@echo "  style           naming gate only"
	@echo "  standards       release-readiness gate only"
	@echo "  corpus          test-vector artifact gate (VENDOR=<path> diffs a vendored copy)"
	@echo "  ledger          declared counts in INDEX.md vs the directories they name"
	@echo "  provenance      L1: a normative spec edit must name a proposal (SINCE=<ref>)"
	@echo "readers (informational):"
	@echo "  convergence     spec rate-of-change + the spec->peers->generators pipeline"
	@echo "  tree SPEC=…     structural node tree"
	@echo "  render SPEC=…   every catalog (--what all)"
	@echo "  topology        corpus dependency graph"
	@echo "  config          print the resolved config"
	@echo "meta:"
	@echo "  sdksync         SDK restatements vs the extension spans they copied"
	@echo "  parity          unified CLI == golden fixtures (regression oracle)"
	@echo "  compile         byte-compile the spec package (sanity)"
	@echo "ADR-0019 Tier-1 (over the tool's own code, stdlib-only):"
	@echo "  test            compile + parity + address self-test (the tool's suite)"
	@echo "  lint            byte-compile static check (no 3rd-party linter; alias of compile)"
	@echo "  fmt             no-op — stdlib-only, no vendored autoformatter"
	@echo "  NOTE: 'check' above is the SPEC gate (style+standards), not lint+test."

# --- gates ---
# All three take CORPUS=<path to a spec repo>. With CORPUS unset they run
# against this repo, which carries no `specs/` — so they exit 2 (could not
# look), loudly, instead of reporting a gate result over an empty file set.
check:
	@$(PYTHON) $(CLI) --corpus $(CORPUS) check

style:
	@$(PYTHON) $(CLI) --corpus $(CORPUS) style

standards:
	@$(PYTHON) $(CLI) --corpus $(CORPUS) standards

# The internal-consistency gate: reads each spec against itself (a MUST naming
# an undefined referent; a value emitted for a field its declared enumeration
# omits). Part of `check` — unlike `corpus`, it gates prose and every spec repo
# has prose.
coherence:
	@$(PYTHON) $(CLI) --corpus $(CORPUS) coherence

# The artifact gate. Deliberately NOT part of `check` — see cli.py's docstring:
# `check` is the two prose gates and runs against every spec repo, while only
# entity-core-protocol carries test-vectors. VENDOR=<path> additionally gates a
# vendored copy in another tree and diffs it against the source; that read is
# read-only, because a vendor lives in another team's repo and drift there
# routes, it does not get edited from here.
corpus:
	@$(PYTHON) $(CLI) --corpus $(CORPUS) corpus $(if $(VENDOR),--vendor $(VENDOR),)

# Gates, but NOT part of `check` — each would force `check` to report
# could-not-look on a repo that legitimately has neither surface, and a gate
# that learns to shrug is the failure mode this toolkit was built against.
ledger:
	@$(PYTHON) $(CLI) --corpus $(CORPUS) ledger


# Pass SINCE=<ref> to widen the range -- and ALWAYS quote the range with the
# number: a provenance count without its window is a conformance number without
# its oracle pin. The gate prints `scanned N commit(s) since REF` for that
# reason; carry both or carry neither.
provenance:
	@$(PYTHON) $(CLI) --corpus $(CORPUS) provenance --since $(SINCE)

# Gates staleness, not correctness: a pin says the source span is byte-identical
# to when someone last reviewed this restatement against it. Unpinned blocks are
# a visible backlog and deliberately do not gate.
pins:
	@$(PYTHON) spec-tool/cli.py pins --root $(CORPUS)

sdksync:
	@$(PYTHON) $(CLI) --corpus $(CORPUS) sdksync

# Reader, not a gate: measures how much each spec is still moving, and prints
# the spec -> core-reference-peers -> generators -> community pipeline with the
# stages nobody reports yet shown as `unreported` rather than omitted.
convergence:
	@$(PYTHON) $(CLI) --corpus $(CORPUS) convergence

# Hermetic: bind-mount the corpus read-only at /work, with /work as both cwd
# and corpus root (the image stays corpus-free). Exits 1 on violations, 2 if it
# could not look.
check-podman: build
	podman run --rm -v $(CORPUS):/work:ro,Z -w /work $(IMAGE) /opt/spec-tool/cli.py --corpus /work check

build:
	podman build -t $(IMAGE) -f spec-tool/Containerfile .

# --- readers ---
tree:
	@test -n "$(SPEC)" || (echo "set SPEC=<spec.md>"; exit 2)
	@$(PYTHON) $(CLI) tree $(SPEC)

render:
	@test -n "$(SPEC)" || (echo "set SPEC=<spec.md>"; exit 2)
	@$(PYTHON) $(CLI) render $(SPEC) --what all

topology:
	@$(PYTHON) $(CLI) topology

config:
	@$(PYTHON) $(CLI) config

# --- meta ---
parity:
	@spec-tool/tests/parity.sh verify

compile:
	@$(PYTHON) -m py_compile \
		spec-tool/cli.py spec-tool/model.py spec-tool/render.py spec-tool/topology.py \
		spec-tool/standards.py spec-tool/style.py spec-tool/corpus.py \
		spec-tool/coherence.py spec-tool/ledger.py spec-tool/provenance.py \
		spec-tool/pins.py spec-tool/inbound.py \
		spec-tool/convergence.py spec-tool/config.py && echo "✓ spec-tool package compiles"

# --- ADR-0019 Tier-1 verbs (over the tool's OWN code) -----------------------
# This is a stdlib-only Python tool (no third-party deps — see AGENTS.md), so
# there is no clippy/ruff/black to wrap. `lint` is the byte-compile static check;
# `test` is the tool's own self-test suite (parity oracle + address invariants);
# `fmt` is an honest no-op (nothing vendored to autoformat). NOTE: the `check`
# target above is this tool's DOMAIN gate (spec style+standards), not the ADR's
# `check = lint+test` — reconciling that name is a separate decision.
test: compile parity
	@$(PYTHON) spec-tool/tests/address_selftest.py
	@$(PYTHON) spec-tool/tests/standards_selftest.py
	@$(PYTHON) spec-tool/tests/coherence_selftest.py
	@$(PYTHON) spec-tool/tests/corpus_selftest.py
	@$(PYTHON) spec-tool/tests/convergence_selftest.py
	@$(PYTHON) spec-tool/tests/coverage_selftest.py
	@$(PYTHON) spec-tool/tests/charter_selftest.py
	@$(PYTHON) spec-tool/tests/roster_selftest.py
	@$(PYTHON) spec-tool/tests/expiry_selftest.py
	@$(PYTHON) spec-tool/tests/vocab_selftest.py
	@$(PYTHON) spec-tool/tests/ledger_selftest.py
	@$(PYTHON) spec-tool/tests/provenance_selftest.py
	@$(PYTHON) spec-tool/tests/sdksync_selftest.py
	@$(PYTHON) spec-tool/tests/pins_selftest.py
	@$(PYTHON) spec-tool/tests/census_selftest.py
	@$(PYTHON) spec-tool/tests/register_selftest.py
	@$(PYTHON) spec-tool/tests/inbound_selftest.py
	@$(PYTHON) spec-tool/tests/inventory_selftest.py
	@$(PYTHON) spec-tool/tests/declare_selftest.py

lint: compile

fmt:
	@echo "arch-tools is stdlib-only (no vendored autoformatter); sources are"
	@echo "hand-formatted. 'make lint' runs the byte-compile static check."

clean:
	-podman rmi $(IMAGE)
