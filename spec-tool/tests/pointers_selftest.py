#!/usr/bin/env python3
"""pointers_selftest — invariants for the declared-pointer drift gate.

**Three of the five defects in this module were found by writing these
assertions or by running against the live corpus, not by reading the code**,
which is the standing reason a new gate here is validated against its own
motivating incident in BOTH directions before its first number is published:

  1. adjacency — without it the leftmost uppercase word on the line became the
     authority's document, and a line reading "SERVES and FETCHES … TREE §3.3a
     is the normative home" reported an authority in a document called
     `FETCHES`. It resolved nowhere, so it surfaced as UNKNOWN: a plausible,
     confident, wrong finding a reader would have answered by passing another
     --namespace-root.
  2. a bare `§N` that does not resolve locally is AMBIGUOUS, never MISSING. The
     ECF changelog names its document three clauses away from its `§`, and the
     first cut filed an ERROR against correct text.
  3. the pin unit is a (document, authority) PAIR, not a sentence. Two pointers
     in one document to one section share a pin correctly; the first run
     reported `10 pointers … 8 pinned` and read as a backlog of two.

The silence cases are asserted rather than left untested, because an exemption
nobody can audit is not an exemption: a self-declaration is an authority and
never a finding, and a resolver that cannot reach a corpus says so instead of
accusing it.

    python3 spec-tool/tests/pointers_selftest.py   # exits non-zero on failure

Stdlib-only. Beside sdksync_selftest, whose mechanism this module reuses.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as _config  # noqa: E402
import pointers  # noqa: E402

FAILURES = []


def ok(name, cond, detail=""):
    if cond:
        print("  ok   %s" % name)
    else:
        FAILURES.append(name)
        print("  FAIL %s %s" % (name, detail))


AUTHORITY_DOC = """# ENTITY-CORE-PROTOCOL

**Version**: 0.8.2.30

### 7.3 Signature Computation — NORMATIVE

The message is the target entity's `content_hash` in full.

### 7.4 Something else

Unrelated.
"""

CITING_DOC = """# ENTITY-NATIVE-TYPE-SYSTEM

**Version**: 4.3

### 10.2 system/signature

The signature is computed over the full `content_hash`.
**`ENTITY-CORE-PROTOCOL.md` §7.3 is the normative home and this sentence is a
pointer, not a second statement of the rule.**

### 10.3 Another

This section is the single normative home for the handler type.

Elsewhere, §10.3 is the normative home of the handler shape.
"""

ADJACENCY_DOC = """# EXTENSION-NETWORK

SERVES and FETCHES but does NOT own.** TREE §3.3a is the normative home here.
"""

TREE_DOC = """# EXTENSION-TREE

### 3.3a Published root

The rule.
"""

AMBIGUOUS_DOC = """# CHANGELOG

`ENTITY-CORE-PROTOCOL` 0.8.2.26 ruled what a signature signs, and §7.3 is its
single normative home.
"""

UNANCHORED_DOC = """# EXTENSION-NETWORK

- `EXTENSION-TREE` — serves the published root, whose normative home is TREE
"""


def build(tmp):
    corpus = Path(tmp) / "corpus"
    (corpus / "specs").mkdir(parents=True)
    (corpus / "specs" / "ENTITY-NATIVE-TYPE-SYSTEM.md").write_text(CITING_DOC)
    (corpus / "specs" / "EXTENSION-NETWORK.md").write_text(ADJACENCY_DOC)
    (corpus / "specs" / "CHANGELOG.md").write_text(AMBIGUOUS_DOC)
    (corpus / "specs" / "EXTENSION-TREE.md").write_text(TREE_DOC)
    sibling = Path(tmp) / "sibling"
    (sibling / "specs").mkdir(parents=True)
    (sibling / "specs" / "ENTITY-CORE-PROTOCOL.md").write_text(AUTHORITY_DOC)
    return corpus, sibling


def rules_at(report, path):
    return sorted(f.rule for f in report.get(path, []))


def main():
    print("pointers_selftest")
    with tempfile.TemporaryDirectory() as tmp:
        corpus, sibling = build(tmp)
        _config.set_corpus_root(corpus) if hasattr(
            _config, "set_corpus_root") else None

        roots = [corpus / "specs"]

        # --- the resolver's scope is a PREMISE ---------------------------
        _, _, rep, n_ptr, n_pair, n_auth = pointers.collect(roots, corpus, [])
        ok("cross-repo authority without --namespace-root is UNRESOLVED, "
           "never missing",
           "pointer-unresolved" in rules_at(
               rep, "specs/ENTITY-NATIVE-TYPE-SYSTEM.md"),
           rules_at(rep, "specs/ENTITY-NATIVE-TYPE-SYSTEM.md"))
        ok("...and unresolved never gates as an error",
           all(f.severity() != "error"
               for fs in rep.values() for f in fs
               if f.rule == "pointer-unresolved"))

        # --- with the sibling in scope -----------------------------------
        _, _, rep, n_ptr, n_pair, n_auth = pointers.collect(
            roots, corpus, [sibling])
        nts = rules_at(rep, "specs/ENTITY-NATIVE-TYPE-SYSTEM.md")
        ok("a resolvable, unpinned pointer is UNPINNED",
           nts == ["pointer-unpinned", "pointer-unpinned"], nts)

        # The pattern-stopped-matching guard: a count, not a finding.
        # 4, not 3: the wrapped declaration in CHANGELOG.md counts. This
        # assertion read 3 while the scan unit was a line, and the count going
        # UP is how the paragraph fix was confirmed to have found something
        # rather than merely stopped failing.
        ok("pointer occurrences are counted (4 across the fixture)",
           n_ptr == 4, "n_ptr=%d" % n_ptr)
        ok("authority self-declarations are counted, never flagged",
           n_auth == 1, "n_auth=%d" % n_auth)

        # --- adjacency ---------------------------------------------------
        net = rules_at(rep, "specs/EXTENSION-NETWORK.md")
        ok("adjacency: `FETCHES` is not read as the authority's document",
           net == ["pointer-unpinned"], net)
        ptrs, _, _ = pointers.find_pointers(ADJACENCY_DOC)
        ok("...the document captured is TREE",
           len(ptrs) == 1 and ptrs[0].doc == "TREE",
           str([(p.doc, p.sec) for p in ptrs]))
        ok("...and a nickname resolves to EXTENSION-TREE.md",
           (pointers.resolve_doc("TREE", corpus, [sibling]) or Path("x")).name
           == "EXTENSION-TREE.md")

        # --- ambiguity is its own bucket ---------------------------------
        chg = rules_at(rep, "specs/CHANGELOG.md")
        ok("a bare §N with no local heading is AMBIGUOUS, not source-missing",
           chg == ["pointer-ambiguous"], chg)

        # --- unanchored --------------------------------------------------
        (corpus / "specs" / "UNANCHORED.md").write_text(UNANCHORED_DOC)
        _, _, rep2, _, _, _ = pointers.collect(roots, corpus, [sibling])
        ok("a document-only declaration is UNANCHORED, and nothing is pinned",
           rules_at(rep2, "specs/UNANCHORED.md") == ["pointer-unanchored"],
           rules_at(rep2, "specs/UNANCHORED.md"))
        (corpus / "specs" / "UNANCHORED.md").unlink()

        # --- the pin, and the drift it exists to catch --------------------
        pointers.do_update(roots, corpus, [sibling])
        pins = pointers.load_pins(corpus)
        ok("--update pins the resolvable pointers", len(pins) == 3,
           "pins=%d" % len(pins))
        _, _, rep, _, _, _ = pointers.collect(roots, corpus, [sibling])
        ok("a pinned, unmoved pointer reports nothing",
           rules_at(rep, "specs/ENTITY-NATIVE-TYPE-SYSTEM.md") == [],
           rules_at(rep, "specs/ENTITY-NATIVE-TYPE-SYSTEM.md"))

        auth = sibling / "specs" / "ENTITY-CORE-PROTOCOL.md"
        auth.write_text(AUTHORITY_DOC.replace(
            "the target entity's `content_hash` in full",
            "the target entity's `content_hash` digest bytes"))
        _, _, rep, _, _, _ = pointers.collect(roots, corpus, [sibling])
        ok("⭐ THE INCIDENT: the authority moves and the pointer is flagged",
           "pointer-source-moved" in rules_at(
               rep, "specs/ENTITY-NATIVE-TYPE-SYSTEM.md"),
           rules_at(rep, "specs/ENTITY-NATIVE-TYPE-SYSTEM.md"))
        ok("...and it gates",
           any(f.severity() == "error"
               for f in rep["specs/ENTITY-NATIVE-TYPE-SYSTEM.md"]))

        # The other direction: a reflow of the authority must NOT fire, or the
        # reader learns to --update without looking, which is the habit that
        # makes a pin worthless.
        auth.write_text(AUTHORITY_DOC.replace(
            "The message is the target entity's `content_hash` in full.",
            "   The message is the target entity's `content_hash` in full.\n"))
        _, _, rep, _, _, _ = pointers.collect(roots, corpus, [sibling])
        ok("⭐ THE OTHER DIRECTION: a reindent/reflow of the authority is quiet",
           "pointer-source-moved" not in rules_at(
               rep, "specs/ENTITY-NATIVE-TYPE-SYSTEM.md"),
           rules_at(rep, "specs/ENTITY-NATIVE-TYPE-SYSTEM.md"))

        # --- a renumbered authority is a FINDING, never a skip ------------
        auth.write_text(AUTHORITY_DOC.replace("### 7.3 Signature",
                                              "### 7.5 Signature"))
        _, _, rep, _, _, _ = pointers.collect(roots, corpus, [sibling])
        ok("a renumbered authority is source-missing, not silence",
           "pointer-source-missing" in rules_at(
               rep, "specs/ENTITY-NATIVE-TYPE-SYSTEM.md"),
           rules_at(rep, "specs/ENTITY-NATIVE-TYPE-SYSTEM.md"))

        # --- the pair unit ------------------------------------------------
        two = """# D

### 1.1 A

x

Here §1.1 is the normative home.

And again, §1.1 is the normative home.
"""
        ptrs, _, _ = pointers.find_pointers(two)
        keys = {pointers.key("d.md", p.doc, p.sec) for p in ptrs}
        ok("two sentences citing one authority are 2 pointers over 1 pair",
           len(ptrs) == 2 and len(keys) == 1,
           "ptrs=%d keys=%d" % (len(ptrs), len(keys)))

        # --- the qualifier gap, both directions ---------------------------
        qual = """# D

Here §1.8 item 1 is the normative home of the rule.

And §6.3's frame rule is the normative home.

And §5.2a's enumeration is the normative home.
"""
        ptrs, _, _ = pointers.find_pointers(qual)
        ok("a SHORT qualifier between the section and the verb still matches",
           [p.sec for p in ptrs] == ["1.8", "6.3", "5.2a"],
           str([(p.doc, p.sec) for p in ptrs]))

        # The gap must not span a citation or a clause boundary, or the leftmost
        # match reaches past the section that actually owns the sentence.
        neg = """# D

See §9.1 for the list. §6.8 is the normative home.

A long qualifier that runs well past any reasonable noun phrase and keeps
going, §4.2 then several more words inserted here deliberately to overrun the
bound, is the normative home.
"""
        ptrs, _, _ = pointers.find_pointers(neg)
        ok("the gap stops at an intervening §, so the OWNING section is captured",
           ptrs and ptrs[0].sec == "6.8", str([p.sec for p in ptrs]))
        ok("...and an over-long qualifier does not match at all",
           all(p.sec != "4.2" for p in ptrs), str([p.sec for p in ptrs]))

        # --- could-not-look ------------------------------------------------
        try:
            pointers.collect([corpus / "nope"], corpus, [sibling])
            ok("an empty scope raises CouldNotLook", False, "no raise")
        except pointers.CouldNotLook:
            ok("an empty scope raises CouldNotLook (exit 2, never 0)", True)

    # --- `--floor`: UNDECLARED restatements in a conformance floor ---------
    #
    # `entity-core-keystone` `F87`, 2026-09-16: `ENTITY-CORE-PROTOCOL` §9.1
    # landed the [MUST] that a restating row names its normative home, and
    # then applied it to the two rows it was investigating.
    FLOOR = (
        "## 9. Conformance\n"
        "\n"
        "### 9.1 MUST Implement\n"
        "\n"
        "- Wire framing (§1.6)\n"
        "- Dispatch routing (§1.4) — reject an inbound EXECUTE "
        "targeting a non-self peer_id; it MUST NOT be reported as 404\n"
        "- **The handler check (§6.8).** **§6.8 is the normative "
        "home and this row is a restatement**; a handler MUST NOT emit 403\n"
        "- A row that asserts a rule but cites no section and MUST NOT drift\n"
        "\n"
        "### 9.3 Notes\n"
        "\n"
        "- Prose outside a floor: a peer MUST NOT do this (§4.2)\n")
    cands, total, asserting = pointers.floor_candidates(FLOOR)
    texts = [t for _l, t in cands]

    ok("a floor row asserting a rule with no authority is a candidate",
       any("Dispatch routing" in t for t in texts), texts)
    ok("a row naming its authority is NOT a candidate",
       not any("handler check" in t for t in texts), texts)
    # THE TRAP, and it is why the scan unit is a LIST ITEM and not a
    # paragraph: a floor is one unbroken block of `- ` lines, so splitting on
    # blank lines returns the whole floor as ONE unit and every row inherits
    # the single authority phrase in it. **That failure reports a clean
    # floor** — the silent-drop direction this module exists to close.
    ok("an authority phrase does not leak to the adjacent row",
       any("Dispatch routing" in t for t in texts), texts)
    ok("a row naming a feature and asserting nothing is not counted",
       not any("Wire framing" in t for t in texts), texts)
    ok("a row asserting a rule but citing no section is not a candidate",
       not any("cites no section" in t for t in texts), texts)
    ok("prose outside a floor heading is not scanned",
       not any("Prose outside" in t for t in texts), texts)
    ok("the denominators are reported, not just the candidate count",
       (total, asserting, len(cands)) == (4, 2, 1),
       (total, asserting, len(cands)))

    c2, t2, a2 = pointers.floor_candidates("# A doc\n\n- a list item (§1)\n")
    ok("a document with no conformance floor yields no rows",
       (t2, a2, len(c2)) == (0, 0, 0), (t2, a2, len(c2)))

    print("\n%d failure(s)" % len(FAILURES))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
