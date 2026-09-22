#!/usr/bin/env python3
"""sections_selftest — invariant checks for the section-identity gate.

**Every rule has a matched pair — a known-bad input goes red AND a known-good
input goes green.** A negative control alone tests a gate against its own notion
of failure and cannot see a wrong reference answer.

**The first suite here replays the two FOUNDING INCIDENTS in both directions**,
which is this toolkit's standing rule after `expiry` shipped with three defects
that each reported a confident clean `0` on the very incident that motivated it.
Both are transcribed from the live documents as they stood before the fix:

  * `GUIDE-CONFORMANCE` — `### §3.1 What each impl provides` at l.192 and
    `### §3.1 Run discipline` at l.265, with `### §3.0` between them at l.250,
    after `§3.4`. Filed by `entity-system-conformance` as `CQ-43`.
  * `EXTENSION-ROLE` — `### 1.5 Framing clarifications` (with `1.5.1`–`1.5.3`)
    and `### 1.5 Relationship to the Identity Extension`, inserted around
    `### 1.4`. **Reported by nobody**; found by widening the search that
    answered `CQ-43`. Note it carries NO `§` sigil — a pattern requiring one
    would have called this incident a clean file, which is why it is a fixture.

**The load-bearing half of the rest is the false-positive side.** This corpus
appends with letter suffixes (`§7a`, `§5.2a`, `§3.0a`) as house style, writes
`§X` as an ordinary English variable in at least two guides, and puts `##`-
looking comments inside fenced shell blocks. A gate that accused any of those
would be switched off inside a week, so each is asserted as *deliberate
silence* rather than left untested: an exemption nobody can audit is not one.

    python3 spec-tool/tests/sections_selftest.py   # exits non-zero on failure

Stdlib-only. Beside roster_selftest, charter_selftest, ledger_selftest.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sections  # noqa: E402

FAILURES = []


def ok(name, cond, detail=""):
    if cond:
        print("  ok   %s" % name)
    else:
        FAILURES.append(name)
        print("  FAIL %s %s" % (name, detail))


def rules(text):
    return [f.rule for f in sections.analyze_doc(text)]


def dups(text):
    return [f for f in sections.analyze_doc(text) if f.rule == "duplicate-section"]


# --------------------------------------------------------------------------
print("\nfounding incident 1 — GUIDE-CONFORMANCE §3.1, both directions")
# --------------------------------------------------------------------------

CQ43_BEFORE = """# Conformance

## §3 The harness

### §3.1 What each impl provides

Each conformant impl ships a small mode.

### §3.2 The Go-side build script

### §3.3 The validate-peer cross-impl category

### §3.4 Why this and not a generator-driven flow

### §3.0 Core-peer scoreboard discipline

### §3.1 Run discipline (normative for cohort closeout)
"""

CQ43_AFTER = CQ43_BEFORE.replace(
    "### §3.0 Core-peer", "### §3.5 Core-peer").replace(
    "### §3.1 Run discipline", "### §3.6 Run discipline")

d = dups(CQ43_BEFORE)
ok("CQ-43 pre-fix: the duplicate §3.1 is reported", len(d) == 1, d)
ok("CQ-43 pre-fix: it names the FIRST declaration's line so a reader can pick",
   d and "line 5" in d[0].text, d[0].text if d else "")
ok("CQ-43 pre-fix: §3.0 after §3.4 is reported as out-of-order",
   "section-out-of-order" in rules(CQ43_BEFORE))
ok("CQ-43 post-fix: clean", sections.analyze_doc(CQ43_AFTER) == [],
   [f.text for f in sections.analyze_doc(CQ43_AFTER)])

# --------------------------------------------------------------------------
print("\nfounding incident 2 — EXTENSION-ROLE 1.5, no § sigil, both directions")
# --------------------------------------------------------------------------

ROLE_BEFORE = """# Role Extension

## 1. Overview

### 1.1 Scope

### 1.2 Design Principles

### 1.3 Coherent Capability

### 1.5 Framing clarifications

#### 1.5.1 Encoding rule

#### 1.5.2 No-kernel-rejection rule

#### 1.5.3 Scope rule

### 1.4 Relationship to the Capability System

### 1.5 Relationship to the Identity Extension
"""

ROLE_AFTER = (ROLE_BEFORE
              .replace("### 1.5 Framing", "### 1.3a Framing")
              .replace("#### 1.5.", "#### 1.3a."))

d = dups(ROLE_BEFORE)
ok("ROLE pre-fix: the duplicate 1.5 is reported even with NO § sigil", len(d) == 1, d)
ok("ROLE pre-fix: the out-of-order insertion that caused it is reported",
   "section-out-of-order" in rules(ROLE_BEFORE))
ok("ROLE post-fix: clean", sections.analyze_doc(ROLE_AFTER) == [],
   [f.text for f in sections.analyze_doc(ROLE_AFTER)])

# --------------------------------------------------------------------------
print("\nfounding incident 3 — the placeholder headings the gate found itself")
# --------------------------------------------------------------------------

PLACEHOLDER = """# Guide

### 4.11 Byte-bearing domain handlers

### 4.X — Error codes: status is centralized

### 4.X Pattern menu — recommended shapes
"""
r = rules(PLACEHOLDER)
ok("two `### 4.X` headings collide into a duplicate-section ERROR",
   r.count("duplicate-section") == 1, r)
ok("and each is separately reported as a placeholder",
   r.count("placeholder-section") == 2, r)
ok("renumbered, they are clean",
   sections.analyze_doc(PLACEHOLDER.replace("### 4.X — Error", "### 4.12 — Error")
                        .replace("### 4.X Pattern", "### 4.13 Pattern")) == [])

# --------------------------------------------------------------------------
print("\ndeliberate silence — the false-positive side")
# --------------------------------------------------------------------------

ok("letter-suffixed insertion is house style, not out of order",
   sections.analyze_doc(
       "# D\n\n## §7 A\n\n## §7a B\n\n## §7b C\n\n## §7c D\n") == [])

ok("a letter suffix sorts between its parent and the next number",
   sections.analyze_doc(
       "# D\n\n### §5.2 A\n\n### §5.2a B\n\n### §5.3 C\n") == [])

ok("a deeper level restarts under its new parent",
   sections.analyze_doc(
       "# D\n\n## §1 A\n\n### §1.9 B\n\n## §2 C\n\n### §2.1 D\n") == [])

FENCED = """# D

## §1 A

```bash
## 3.1 not a heading
## 3.1 still not a heading
```

## §2 B
"""
ok("`##` inside a fenced block is content, not a duplicate heading",
   sections.analyze_doc(FENCED) == [], [f.text for f in sections.analyze_doc(FENCED)])

ok("a tilde fence is tracked too",
   sections.analyze_doc("# D\n\n~~~\n## 3.1 x\n## 3.1 y\n~~~\n\n## §1 A\n") == [])

ok("two dated headings are not a duplicate section 2026",
   sections.analyze_doc(
       "# D\n\n## 2026-09-15 The round\n\n## 2026-09-16 The next round\n") == [])

ok("`§X` as an English variable is a WARNING, never an error",
   [f.severity() for f in sections.analyze_doc(
       "# D\n\n## §1 A\n\nan extension spec that includes a §X section\n")]
   == ["warning"])

ok("the format standard's own §N.M metasyntax does not gate",
   all(f.severity() == "warning" for f in sections.analyze_doc(
       "# D\n\n## §1 A\n\ncite it as `DOC.md §N.M` where N is the section\n")))

ok("a placeholder inside a heading line is not double-counted as a citation",
   rules("# D\n\n### 4.X Thing\n").count("placeholder-section") == 1)

ok("prose headings with no number are ignored",
   sections.analyze_doc("# D\n\n## Overview\n\n## Overview\n") == [])

# --------------------------------------------------------------------------
print("\nexit codes — 0 clean, 1 findings, 2 could-not-look")
# --------------------------------------------------------------------------

with tempfile.TemporaryDirectory() as td:
    root = Path(td)

    ok("an empty root is could-not-look (2), never a clean pass",
       sections.run_check(root, True, False, False) == 2)

    specs = root / "specs"
    specs.mkdir()
    (specs / "A.md").write_text("# A\n\n## §1 One\n\n## §2 Two\n", encoding="utf-8")
    ok("a clean corpus is exit 0 under --gate",
       sections.run_check(root, True, False, False) == 0)

    (specs / "A.md").write_text("# A\n\n## §1 One\n\n## §1 Uno\n", encoding="utf-8")
    ok("a duplicate is exit 1 under --gate",
       sections.run_check(root, True, False, False) == 1)
    ok("reader mode exits 0 even with findings",
       sections.run_check(root, False, False, False) == 0)

    (specs / "A.md").write_text(
        "# A\n\n## §2 Two\n\n## §1 One\n", encoding="utf-8")
    ok("out-of-order ALONE does not gate — it is the predictor, not the defect",
       sections.run_check(root, True, False, False) == 0)

print("\n%d check(s) failed" % len(FAILURES) if FAILURES else "\nall checks passed")
sys.exit(1 if FAILURES else 0)
