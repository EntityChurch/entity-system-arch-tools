# Extension: Narrative — synthetic fixture for the narrative rules

**Version**: 1.0
**Status**: Active
**Depends**: ENTITY-CORE-PROTOCOL.md (v7.0+)

This fixture carries the same four process-narrative shapes as
`ARCHITECTURE-NOTES.md`, but under an `EXTENSION-*` name so it classifies as a
**canonical-spec**. That is the whole point of it existing: the narrative rules
score architecture's *output* and spare the docs describing how the work is
*organized*, and both halves of that split need a parity fixture or the split is
only asserted, never exercised.

Without this file the rules would still have a fixture — `ARCHITECTURE-NOTES.md`
— but that fixture became an `arch-doc` when the split landed, so a plain
re-capture would have shown four fewer errors and quietly retired parity coverage
of four rules while looking like a routine golden update.

## 1. Provenance

This document folds in Amendment 1 and Amendment 2 of the example stack, which
the standards gate flags as amendment-provenance notes.

It graduated from `proposals/example-widget.md`, a process-routing citation
the standards gate flags as a proposal-citation.

The convergence work was carried by the godot and raylib reference cohorts,
implementation references the standards gate flags as impl-team-ref.

## Document History

- v0.9: initial synthetic draft for the test corpus
- v1.0: folded provenance notes

This whole section is process history, which the standards gate flags as a
document-history-section.
