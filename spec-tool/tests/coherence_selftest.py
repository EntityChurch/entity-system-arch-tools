#!/usr/bin/env python3
"""coherence_selftest — invariant checks for the two internal-consistency rules.

Both rules were derived from defects that had already shipped, so the fixtures
here are those defects reduced to their smallest reproducing form, plus the
correct shapes that must stay quiet. **The negative cases carry the weight.** A
rule that only fires on the defect it was written for is indistinguishable from
a rule that fires on everything; the false-positive fixtures are the teeth.

    python3 spec-tool/tests/coherence_selftest.py   # exits non-zero on failure

Stdlib-only. Beside parity.sh, address_selftest, standards_selftest.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import coherence  # noqa: E402

FAILURES = []


def run(text, defs=None):
    """Findings for `text`, with the corpus definition set defaults to empty."""
    return coherence.analyze(text, defs or set())


def case(name, text, rule, want, defs=None):
    got = len([f for f in run(text, defs) if f.rule == rule])
    if got != want:
        FAILURES.append("%s: want %d, got %d" % (name, want, got))
        print("  FAIL %s (want %d, got %d)" % (name, want, got))
    else:
        print("  ok   %s" % name)


# --------------------------------------------------------------------------
# rule 1 — undefined-wire-referent
#
# The shipped defect: EXTENSION-CONTINUATION §3.6 Step 4 assigned an EXECUTE
# field from a helper defined nowhere in the corpus. Each implementation
# improvised the token; the improvisations agreed same-implementation and
# disagreed across the wire.
# --------------------------------------------------------------------------
print("undefined-wire-referent")

CONTINUATION_STEP4 = """
```
execute_dispatch(continuation, raw_result):
  if continuation.data.deliver_to != null:
    execute.deliver_to = continuation.data.deliver_to
    execute.deliver_token = generate_internal_deliver_token(continuation.data.deliver_to)
```
"""

case("continuation_step4_as_shipped", CONTINUATION_STEP4,
     "undefined-wire-referent", 1)

case("silent_once_the_helper_is_defined", CONTINUATION_STEP4,
     "undefined-wire-referent", 0, defs={"generate_internal_deliver_token"})

# A bare local is exposition, not a contract. Without this distinction the rule
# reports ~200 pseudocode helpers and gets switched off inside a week.
case("bare_local_is_not_a_field", """
```
  value = navigate(raw_result, transform.extract)
  mapped = shallow_merge(a, b)
```
""", "undefined-wire-referent", 0)

# Prose outside a fence is not pseudocode.
case("prose_is_not_pseudocode",
     "The handler calls foo.bar = make_something(x) when it feels like it.",
     "undefined-wire-referent", 0)

# A commented-out line is not an assignment.
case("comment_line_ignored", """
```
  ; execute.deliver_token = generate_internal_deliver_token(x)
```
""", "undefined-wire-referent", 0)


# --------------------------------------------------------------------------
# rule 2 — enum-value-not-declared
#
# The shipped defect: EXTENSION-REGISTRY §6a.9 declared two status values and
# §6a.9.3 — written to fix an earlier instance of exactly this — returned a
# third from `deny-request`.
# --------------------------------------------------------------------------
print("enum-value-not-declared")

REGISTRY_AS_SHIPPED = """
```
type: "system/registry/register-result"
data: {
  status:        "bound" | "pending_review",
  binding_hash?: <system/hash>,
  pending_hash?: <system/hash>
}
```

| Operation | Input | Output | Effect |
|---|---|---|---|
| `deny-request` | `{pending_hash, reason?}` | `system/registry/register-result` `{status: "denied"}` | writes a new body |
"""

case("registry_denied_as_shipped", REGISTRY_AS_SHIPPED,
     "enum-value-not-declared", 1)

case("silent_once_declared",
     REGISTRY_AS_SHIPPED.replace('"bound" | "pending_review"',
                                 '"bound" | "pending_review" | "denied"'),
     "enum-value-not-declared", 0)

# --- the false positives that must stay dead ------------------------------
# (a) Two result types in one spec, each with its own `status` vocabulary, both
#     correct. A field-keyed version of this rule reported this pair on its
#     first run against EXTENSION-RELAY.
case("two_types_one_field_name_is_not_a_defect", """
```
type: "system/relay/forward-result"
data: {
  status: "forwarded" | "queued-fallback" | "rejected"
}
```

```
type: "system/relay/put-result"
data: {
  status:    "stored",
  entry_hash: <system/hash>
}
```
""", "enum-value-not-declared", 0)

# (b) A table row that names one type and then describes a *different* entity's
#     state later in the same row. This is REGISTRY's own `approve-request` row,
#     which is correct: `register-result` carries `"bound"`, and the
#     `"approved"` forty characters along belongs to the pending-binding.
case("prose_window_does_not_bind_a_distant_value", """
```
type: "system/registry/register-result"
data: {
  status: "bound" | "pending_review" | "denied"
}
```

| `approve-request` | `{pending_hash}` | `system/registry/register-result` `{status: "bound", binding_hash}` | issues the binding, writes a new body `status: "approved"` carrying `binding_hash`, repoints |
""", "enum-value-not-declared", 0)

# (c) Free-form fields are not vocabularies. `name`, `type`, `path` and friends
#     take arbitrary values; enumerating one at one site says nothing.
case("denylisted_field_is_not_a_vocabulary", """
```
type: "system/thing"
data: {
  name: "alpha" | "beta"
}
```
The entity is stored with `system/thing` `{name: "gamma"}`.
""", "enum-value-not-declared", 0)

# (d) A single-valued literal is a constant, not an enumeration to violate.
case("single_value_is_not_an_enumeration", """
```
type: "system/thing"
data: {
  status: "only"
}
```
`system/thing` `{status: "other"}`
""", "enum-value-not-declared", 0)


# --------------------------------------------------------------------------
# The gate contract: scanning nothing is not passing.
# --------------------------------------------------------------------------
print("gate contract")
rc = coherence.run_check([Path("/nonexistent-corpus-root")], as_json=False)
if rc != 2:
    FAILURES.append("empty_corpus_must_exit_2: got %d" % rc)
    print("  FAIL empty_corpus_must_exit_2 (got %d)" % rc)
else:
    print("  ok   empty_corpus_must_exit_2")


if FAILURES:
    print("\n%d failure(s):" % len(FAILURES))
    for f in FAILURES:
        print("  - %s" % f)
    sys.exit(1)
print("\n12/12 invariants pass")
