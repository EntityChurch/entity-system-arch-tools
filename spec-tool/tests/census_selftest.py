#!/usr/bin/env python3
"""census_selftest — invariant checks for the corpus-against-consumers census.

**Every test here was written from a defect this analyzer actually produced
during its first hour**, which is the only reason to trust the list. The
attribution rules look obvious and are not: four separate over-eager matches
each produced a confident, specific, wrong finding about a named seat, and a
tool that publishes to five seats at once has to be wrong in the quiet
direction, never the loud one.

The four, in the order they were caught:

  529 orphans   Bare-citation inference attributed every `§` in any file whose
                path contained the token to that document. An *inferred*
                attribution that fails to resolve is a defect in the inference,
                not evidence the implementer cited a missing section — so only
                a QUALIFIED citation may accuse.

   16 orphans   `test-vectors/crypto-agility/CHANGELOG.md` was loaded as a
                document, deriving the token `changelog`.

   12 orphans   `\\bTYPE\\b` matched the `TYPE` inside `TYPE-SYSTEM`, because a
                hyphen is a regex word boundary. Twelve wrong findings about
                one seat, each naming a real file and a real line.

  431 more      An unrestricted uppercase qualifier matched `TODO`, `HTTP`,
                `PUT`. Ambiguity went UP: a matched qualifier that names no
                document is worse than none, because it consumes the citation
                and blocks the inference that would have resolved it.

    python3 spec-tool/tests/census_selftest.py   # exits non-zero on failure

Stdlib-only. Beside the other analyzer self-tests.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import census  # noqa: E402

FAILURES = []

DOCS = {
    "EXTENSION-RELAY": Path("/x/EXTENSION-RELAY.md"),
    "EXTENSION-TYPE": Path("/x/EXTENSION-TYPE.md"),
    "EXTENSION-NETWORK": Path("/x/EXTENSION-NETWORK.md"),
    "ENTITY-NATIVE-TYPE-SYSTEM": Path("/x/ENTITY-NATIVE-TYPE-SYSTEM.md"),
    "ENTITY-CORE-PROTOCOL": Path("/x/ENTITY-CORE-PROTOCOL.md"),
    "APP-CONVENTION-SEMANTIC-CONTENT-SITE": Path("/x/APP-CONVENTION-SEMANTIC-CONTENT-SITE.md"),
}


def ok(name, cond, detail=""):
    if cond:
        print("  ok   %s" % name)
    else:
        FAILURES.append(name)
        print("  FAIL %s %s" % (name, detail))


def attributions(line, relpath, aliases=None):
    aliases = aliases or census.derived_aliases(DOCS)
    tokens = census.stem_tokens(DOCS)
    qre = census.qualified_re(aliases, DOCS)
    return census.attribute(line, census.path_segments(relpath), DOCS,
                            tokens, aliases, qre)


# ---------------------------------------------------------------- attribution

def test_qualified_wins():
    got = attributions("// per EXTENSION-RELAY §6.2.1 the relay MAY store",
                       "ext/tree/tree.go")
    ok("a qualified citation beats the path hint",
       got == [("EXTENSION-RELAY", "6.2.1", True)], got)


def test_bare_name_is_a_qualifier():
    """`NETWORK §6.5.2b` is how the cohort actually writes it. Matching only
    the `EXTENSION-` form sent thousands of clear citations to ambiguous."""
    got = attributions("// NETWORK §6.5.2b carries server->client push",
                       "cmd/peer/main.go")
    ok("a derived bare name qualifies",
       got == [("EXTENSION-NETWORK", "6.5.2b", True)], got)


def test_hyphen_is_not_a_name_boundary():
    """The 12-orphan bug. `TYPE-SYSTEM spec §9.4` must never resolve to
    `EXTENSION-TYPE`; the matched name has to be the whole hyphenated token."""
    got = attributions("    Per TYPE-SYSTEM spec §9.4.1.", "types/definitions.py")
    ok("TYPE does not match inside TYPE-SYSTEM",
       all(stem != "EXTENSION-TYPE" for stem, _, _ in got), got)


def test_unknown_uppercase_does_not_consume():
    """`TODO`, `HTTP`, `PUT` are not documents. A qualifier that names nothing
    must not swallow the citation — it blocks the inference that would have
    resolved it."""
    got = attributions("// TODO §6.2 revisit", "ext/relay/store.go")
    ok("an unknown uppercase token leaves the citation inferrable",
       got == [("EXTENSION-RELAY", "6.2", False)], got)


def test_bare_infers_from_a_whole_path_segment():
    got = attributions("// see §4.2 for poll visibility", "ext/relay/store.go")
    ok("a bare citation infers from a path segment",
       got == [("EXTENSION-RELAY", "4.2", False)], got)


def test_substring_segment_does_not_infer():
    """`composite/` must not match `site`; segment equality, not containment."""
    got = attributions("// see §4.2", "ui/composite/widget.rs")
    ok("a substring path match does not infer",
       got == [(None, "4.2", False)], got)


def test_ambiguous_is_never_guessed():
    got = attributions("// see §4.2", "core/util/helpers.go")
    ok("an unattributable citation stays None",
       got == [(None, "4.2", False)], got)


# ------------------------------------------------------------------- filtering

def test_line_numbers_are_not_sections():
    ok("a 3+ digit head is a line number, not a section",
       not census.is_section_ref("2688") and not census.is_section_ref("975"))
    ok("a real section still passes",
       census.is_section_ref("6.5.2b") and census.is_section_ref("4.2")
       and census.is_section_ref("11"))


def test_placeholders_are_not_sections():
    ok("`§6.x` and `§4.3.x` are deliberate placeholders",
       not census.is_section_ref("6.x") and not census.is_section_ref("4.3.x"))


def test_doc_stem_filter():
    """`CHANGELOG` and `README` are not spec documents. Loading one derives a
    token that then claims every bare citation under a matching path."""
    ok("CHANGELOG is not a document stem", not census.DOC_STEM_RE.match("CHANGELOG"))
    ok("README is not a document stem", not census.DOC_STEM_RE.match("README"))
    ok("EXTENSION-RELAY is", bool(census.DOC_STEM_RE.match("EXTENSION-RELAY")))
    ok("GUIDE-GC is", bool(census.DOC_STEM_RE.match("GUIDE-GC")))


def test_tokens_are_extension_only():
    """`APP-CONVENTION-SEMANTIC-CONTENT-SITE` yields `site`, which matches half
    of every front-end tree. Only `EXTENSION-*` earns a path token."""
    toks = census.stem_tokens(DOCS)
    ok("site is not a path token", "site" not in toks, sorted(toks))
    ok("relay is", toks.get("relay") == "EXTENSION-RELAY", sorted(toks))


def test_bare_alias_requires_uniqueness():
    """If two documents reduce to the same bare name, neither claims it —
    the citation stays ambiguous rather than going to whichever sorted first."""
    docs = dict(DOCS)
    docs["GUIDE-RELAY"] = Path("/x/GUIDE-RELAY.md")
    al = census.derived_aliases(docs)
    ok("a contested bare name is awarded to nobody", "RELAY" not in al, al.get("RELAY"))


# ------------------------------------------------------------------- sections

def test_section_sign_headings_are_read():
    """`EXTENSION-SUBSTITUTE` writes `### §9.1`. A pattern demanding the bare
    form measured a present, RULED section as absent."""
    ok("`### §9.1 Title` parses", census.HEADING_RE.match("### §9.1 Title") is not None)
    ok("`## 9.1 Title` parses", census.HEADING_RE.match("## 9.1 Title") is not None)


def test_normative_counting():
    body = "\n".join([
        "## 4. Ops", "A relay MUST honor it.", "It MUST NOT surface.",
        "### 4.1 Sub", "Nothing normative here.",
    ])
    p = Path("/tmp/.census_selftest_fixture.md")
    p.write_text(body, encoding="utf-8")
    try:
        secs = dict((s, n) for s, _, _, n in census.sections_of(p))
        ok("MUST and MUST NOT both count, MUST NOT once", secs.get("4") == 2, secs)
        ok("a section with no normative token scores 0", secs.get("4.1") == 0, secs)
    finally:
        p.unlink(missing_ok=True)


# ----------------------------------------------------------------- drift

def test_fingerprint_ignores_rationale():
    """Rewording the prose around a MUST must not read as the MUST moving.
    The blame-based first draft could not tell those apart and reported 2,174
    findings off a single corpus-wide prose sweep."""
    a = census.normative_fingerprint("## 4.2 Poll\nBecause it is cheap, an entry MUST NOT surface.\n")
    b = census.normative_fingerprint("## 4.2 Poll\nFor reasons of honesty:\nBecause it is cheap, an entry MUST NOT surface.\n")
    ok("rationale-only edits do not move the fingerprint", a == b, (a, b))


def test_fingerprint_catches_a_changed_must():
    a = census.normative_fingerprint("## 4.2 Poll\nAn entry MUST NOT surface.\n")
    b = census.normative_fingerprint("## 4.2 Poll\nAn entry MUST surface.\n")
    ok("changing the obligation moves the fingerprint", a != b, (a, b))


def test_collapsed_history_detection():
    """[ADR-0027] re-authors published commits at the boundary, so nine of
    `ENTITY-CORE-PROTOCOL`'s ten commits carry one date. Measuring through
    that produced 176 findings that were all boundary artifacts."""
    day = 86400
    nine_of_ten = [100 * day] * 9 + [37 * day]
    ok("one date holding 90% is collapsed",
       census.history_is_collapsed(nine_of_ten))
    ok("two distinct days is collapsed",
       census.history_is_collapsed([1 * day, 1 * day, 5 * day]))
    ok("an empty history is collapsed, not clean",
       census.history_is_collapsed([]))
    spread = [1 * day, 9 * day, 20 * day, 31 * day, 44 * day]
    ok("a genuinely spread history is usable",
       not census.history_is_collapsed(spread))


def main():
    print("census_selftest")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    if FAILURES:
        print("\n%d failure(s): %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("\nall census invariants hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
