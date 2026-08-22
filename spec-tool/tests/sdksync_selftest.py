#!/usr/bin/env python3
"""sdksync_selftest — invariants for the SDK-restatement staleness gate.

The defect this gate mechanizes is a copy that stopped matching its original
and stayed green for months, because nothing linked the two. **So the tests
that carry the weight are the ones asserting what was SEEN** — `blocks()` and
`span_for_anchor()` are exercised directly, not only through the findings.

That is the same reasoning `ledger_selftest` states, and for the same reason: a
detector keyed on a text pattern reports zero findings when its pattern stops
matching, and zero findings is indistinguishable from a clean corpus. Every
`ok(... == N)` on a count below is guarding that, not the finding logic.

    python3 spec-tool/tests/sdksync_selftest.py   # exits non-zero on failure

Stdlib-only. Beside ledger_selftest, coherence_selftest.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sdksync  # noqa: E402

FAILURES = []


def ok(name, cond, detail=""):
    if cond:
        print("  ok   %s" % name)
    else:
        FAILURES.append(name)
        print("  FAIL %s %s" % (name, detail))


SRC = """# EXTENSION-THING

## 2.1 The request

```
system/thing/request := {
  fields: {
    events: {type_ref: "primitive/string"}   ; "created", "deleted"
  }
}

system/thing/limits := {
  fields: {
    rate_limit: {type_ref: "primitive/uint"}  ; per minute
  }
}
```

## 2.2 Something else

Not part of any pinned span.
"""

SDK = """# SDK-THING

```
  ThingParams := {
    events: [string]?
    limits: { rate_limit: uint? }
  }

  Unpinned := {
    x: int
  }
```
"""


def corpus(tmp, pins):
    base = Path(tmp)
    (base / "specs" / "extensions").mkdir(parents=True, exist_ok=True)
    (base / "specs" / "sdk").mkdir(parents=True, exist_ok=True)
    (base / "specs" / "extensions" / "EXTENSION-THING.md").write_text(
        SRC, encoding="utf-8")
    (base / "specs" / "sdk" / "SDK-THING.md").write_text(SDK, encoding="utf-8")
    (base / "specs" / "sdk" / ".sdk-source-map.json").write_text(
        json.dumps({"meta": {}, "pins": pins}), encoding="utf-8")
    return base


def pin(anchor, dg, source="specs/extensions/EXTENSION-THING.md"):
    return {"source": source, "anchor": anchor, "digest": dg}


def rules(findings):
    return sorted(f.rule for f in findings)


def main():
    print("sdksync selftest")

    # --- what was SEEN -----------------------------------------------------
    seen = sdksync.blocks(SDK)
    ok("blocks() sees both restatements (pattern still matches)",
       [n for n, _ in seen] == ["ThingParams", "Unpinned"], repr(seen))
    ok("blocks() reports 1-indexed lines", seen[0][1] == 4, repr(seen))

    span = sdksync.span_for_anchor(SRC, "system/thing/request")
    ok("span_for_anchor finds a CDDL block", span is not None and
       any("events" in l for l in span), repr(span))
    ok("span_for_anchor stops at the block close",
       span is not None and not any("rate_limit" in l for l in span),
       repr(span))

    head = sdksync.span_for_anchor(SRC, "2.2 Something else")
    ok("span_for_anchor finds a heading section",
       head is not None and any("Not part of" in l for l in head), repr(head))

    ok("span_for_anchor returns None for an absent anchor (never the file)",
       sdksync.span_for_anchor(SRC, "system/thing/nope") is None)

    # --- multi-anchor ------------------------------------------------------
    multi = sdksync.spans_for(SRC, ["system/thing/request",
                                    "system/thing/limits"])
    ok("spans_for concatenates several anchors",
       multi is not None and any("events" in l for l in multi)
       and any("rate_limit" in l for l in multi))
    ok("spans_for is None if ANY anchor is missing — no partial pin",
       sdksync.spans_for(SRC, ["system/thing/request", "nope"]) is None)
    ok("spans_for order is significant (a reorder is a different digest)",
       sdksync.digest(sdksync.spans_for(SRC, ["system/thing/request",
                                              "system/thing/limits"]))
       != sdksync.digest(sdksync.spans_for(SRC, ["system/thing/limits",
                                                 "system/thing/request"])))

    # --- normalization: reflow quiet, content loud -------------------------
    a = sdksync.digest(["x: 1", "", "  y: 2  "])
    ok("blank lines and trailing space do not change the digest",
       a == sdksync.digest(["x: 1", "y: 2"]))
    ok("a word change DOES change the digest",
       a != sdksync.digest(["x: 1", "y: 3"]))

    # --- findings ----------------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        base = corpus(tmp, {})
        f = sdksync.analyze("specs/sdk/SDK-THING.md", SDK, {}, base)
        ok("no pins -> every block reports unpinned",
           rules(f) == ["sdk-block-unpinned"] * 2, rules(f))
        ok("unpinned is a WARN and therefore does not gate",
           all(x.severity() == "warn" for x in f))

    with tempfile.TemporaryDirectory() as tmp:
        good = sdksync.digest(sdksync.spans_for(SRC, ["system/thing/request"]))
        pins = {"specs/sdk/SDK-THING.md::ThingParams":
                pin(["system/thing/request"], good)}
        base = corpus(tmp, pins)
        f = sdksync.analyze("specs/sdk/SDK-THING.md", SDK, pins, base)
        ok("a matching digest produces no error for that block",
           rules(f) == ["sdk-block-unpinned"], rules(f))

        stale = dict(pins)
        stale["specs/sdk/SDK-THING.md::ThingParams"] = pin(
            ["system/thing/request"], "sha256:stale")
        f = sdksync.analyze("specs/sdk/SDK-THING.md", SDK, stale, base)
        ok("a moved source fires sdk-source-moved",
           "sdk-source-moved" in rules(f), rules(f))
        ok("sdk-source-moved is an ERROR and gates",
           any(x.severity() == "error" for x in f if
               x.rule == "sdk-source-moved"))

        missing_anchor = {"specs/sdk/SDK-THING.md::ThingParams":
                          pin(["system/thing/renamed"], good)}
        f = sdksync.analyze("specs/sdk/SDK-THING.md", SDK, missing_anchor, base)
        ok("a RENAMED anchor is a finding, not a silent skip",
           "sdk-source-missing" in rules(f), rules(f))

        missing_file = {"specs/sdk/SDK-THING.md::ThingParams":
                        pin(["system/thing/request"], good,
                            source="specs/extensions/GONE.md")}
        f = sdksync.analyze("specs/sdk/SDK-THING.md", SDK, missing_file, base)
        ok("an absent source file is a finding, not a silent skip",
           "sdk-source-missing" in rules(f), rules(f))

    # --- the end-to-end property the gate exists for -----------------------
    with tempfile.TemporaryDirectory() as tmp:
        good = sdksync.digest(sdksync.spans_for(SRC, ["system/thing/limits"]))
        pins = {"specs/sdk/SDK-THING.md::ThingParams":
                pin(["system/thing/limits"], good)}
        base = corpus(tmp, pins)
        edited = SRC.replace("per minute", "per hour")
        (base / "specs" / "extensions" / "EXTENSION-THING.md").write_text(
            edited, encoding="utf-8")
        f = sdksync.analyze("specs/sdk/SDK-THING.md", SDK, pins, base)
        ok("EDITING THE EXTENSION FLAGS THE SDK BLOCK THAT COPIED IT",
           "sdk-source-moved" in rules(f), rules(f))

    print("\n%d check(s) failed" % len(FAILURES) if FAILURES else "\nall ok")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
