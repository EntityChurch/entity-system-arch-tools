#!/usr/bin/env python3
"""arms_selftest — invariant checks for the block-arm / prose-enumeration reader.

**The first suite replays the FOUNDING INCIDENT in both directions**, which is
this toolkit's standing rule after `expiry` shipped with three defects that each
reported a confident clean `0` on the very incident that motivated it.

The incident, transcribed from `ENTITY-CORE-PROTOCOL` as it stood at `0.8.2.27`:

  §6.5's dispatch pseudocode carried TWO `400 hash_mismatch` arms — one for the
  ROOT entity's own hash and one for a mis-keyed `included` entry. §4.11's cause
  table carried ONE row, the `included` one. `entity-system-conformance` read
  the table and published *"no section assigns one"* about the root code.

**What this analyzer must do on that input, and what it must NOT claim.** It is
a reader. The assertion is that **both arms are surfaced with distinguishable
causes** — that is the whole mechanism by which a human sees the table is one
row short. It is emphatically NOT that the tool reports a finding: the two
causes share no vocabulary with each other *or* with the table row, a cause is
prose, and a gate keyed on the code scores this input clean because
`hash_mismatch` is present in both homes. **A test asserting a verdict here
would be asserting the wrong thing**, and the analyzer's docstring says so.

The rest is the false-positive side, which is the load-bearing half. This corpus
writes `SHA256(encoded)` in blocks (status `256`, code `format` under a naive
pattern), draws dispatch trees with `+-` and `|`, and puts normative scoping in
`;` comments. A reader that accused any of those would be switched off, so each
is asserted as **deliberate silence** rather than left untested: an exemption
nobody can audit is not an exemption.

    python3 spec-tool/tests/arms_selftest.py   # exits non-zero on failure

Stdlib-only. Beside sections_selftest, roster_selftest, charter_selftest.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import arms  # noqa: E402

FAILURES = []


def ok(label, cond):
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        FAILURES.append(label)


# ---------------------------------------------------------------- the incident

# §6.5's dispatch block as it stood — two hash_mismatch arms, different causes.
INCIDENT_BLOCK = """# ENTITY-CORE-PROTOCOL

## 4.11 Pre-admission refusal

| Pre-admission cause | `status` . `code` | Stated at |
|---|---|---|
| Resolution integrity — an `included` entry whose key is not `content_hash({type, data})` of the entity under it | **400** `hash_mismatch` | 5.2a |
| Framing — CBOR that never becomes an Envelope | **400** `invalid_request` | 4.7 |

## 6.5 Dispatch

```
  +- Validate root entity hash
  |   -> 400 hash_mismatch, coded frame; MAY then close
  |
  +- Validate each included entity hash
  |   (an `included` key that is not content_hash of its entity)
  |   -> 400 hash_mismatch, coded frame; MAY then close
```
"""


def incident_root():
    d = tempfile.mkdtemp()
    root = Path(d)
    (root / "specs").mkdir()
    (root / "specs" / "ENTITY-CORE-PROTOCOL.md").write_text(
        INCIDENT_BLOCK, encoding="utf-8")
    return root


print("\n-- the founding incident, both directions --")

_arms, _enums, _beside = arms.analyze_doc(INCIDENT_BLOCK)

root_arms = [a for a in _arms if "root" in a.cause.lower()]
incl_arms = [a for a in _arms if "included" in a.cause.lower()]

ok("the ROOT arm is surfaced from the block", len(root_arms) == 1)
ok("the INCLUDED arm is surfaced from the block", len(incl_arms) == 1)
ok("both arms carry the same code — which is WHY a code-keyed gate is blind",
   len(root_arms) == 1 and len(incl_arms) == 1
   and root_arms[0].code == incl_arms[0].code == "hash_mismatch")
ok("the two arms have DISTINGUISHABLE causes — the mechanism a human reads",
   len(root_arms) == 1 and len(incl_arms) == 1
   and root_arms[0].cause != incl_arms[0].cause)

# The negative direction that matters: the code IS enumerated, so the strong
# rule must stay silent. Reporting `code-not-enumerated` here would be a false
# accusation against a document that does carry the code.
strong = [r for (r, _a, _w) in _beside if r == "code-not-enumerated"]
ok("`code-not-enumerated` is SILENT on the incident — the code IS in prose",
   not strong)

# And the honest limit, asserted rather than left implied.
ok("the reader exits 0 on the incident — it decides nothing",
   arms.run_check(incident_root(), None, False, False) == 0)

print("\n-- after the fix: the table gains the root row --")

FIXED = INCIDENT_BLOCK.replace(
    "| Framing — CBOR that never becomes an Envelope | **400** `invalid_request` | 4.7 |",
    "| Root entity self-consistency — the root's own `content_hash` is not that of its `{type, data}` | **400** `hash_mismatch` | 1.8 |\n"
    "| Framing — CBOR that never becomes an Envelope | **400** `invalid_request` | 4.7 |")
f_arms, f_enums, f_beside = arms.analyze_doc(FIXED)
ok("both arms still surface after the fix", len(f_arms) == 2)
ok("the root cause now has an enumerated row sharing its vocabulary",
   any("root" in e.text.lower() for e in f_enums if e.code == "hash_mismatch"))
ok("`arm-cause-unmatched` does not fire on the ROOT arm once the row exists",
   not [1 for (r, a, _w) in f_beside
        if r == "arm-cause-unmatched" and "root" in a.cause.lower()])

print("\n-- deliberate silences (the false-positive side) --")

NOISE = """# D

## 1 X

```
  digest = SHA256(encoded)
  return bytes([0x00]) + digest
```
"""
n_arms, _n_enums, n_beside = arms.analyze_doc(NOISE)
ok("`SHA256(encoded)` is not an arm — status 256, code `format` under a naive "
   "pattern", not n_arms)

SINGLE_WORD = """# D

## 1 X

```
  +- Walk the chain
  |   -> 404 chain
  +- Check the writer
  |   -> 403 writer
```
"""
s_arms, _s_enums, _s_b = arms.analyze_doc(SINGLE_WORD)
ok("a no-underscore token is not a code — every real code in the corpus has one",
   all(a.code == "-" for a in s_arms))
ok("but the STATUS is still surfaced as an un-coded arm, never silently dropped",
   len(s_arms) == 2)

PROSE_ONLY = """# D

## 1 X

A responder MUST answer **400** `invalid_request` here.
"""
p_arms, p_enums, _p_b = arms.analyze_doc(PROSE_ONLY)
ok("prose outside a fence is an ENUMERATION, never an arm", not p_arms)
ok("prose enumerations are collected", len(p_enums) == 1)

HEADING = """# D

## 400 invalid_request is the code

```
  +- do a thing
  |   -> 200 ok_result
```
"""
h_arms, h_enums, _h_b = arms.analyze_doc(HEADING)
ok("a heading is not an enumeration row", not h_enums)

print("\n-- could-not-look --")
empty = Path(tempfile.mkdtemp())
(empty / "specs").mkdir()
(empty / "specs" / "E.md").write_text("# E\n\nNothing here.\n", encoding="utf-8")
ok("a corpus with no arms and no enumerations is could-not-look (exit 2)",
   arms.run_check(empty, None, False, False) == 2)

print("\n%d check(s) failed" % len(FAILURES) if FAILURES
      else "\nall checks passed")
sys.exit(1 if FAILURES else 0)
