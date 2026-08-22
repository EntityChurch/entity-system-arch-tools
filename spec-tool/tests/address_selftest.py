#!/usr/bin/env python3
"""address_selftest — invariant checks for the §11 addressing validator.

Unlike `parity.sh`, this does NOT pin finding *counts* (those change as the
corpus is corrected). It pins the validator's *behavior* against synthetic
fixtures — the contract the downstream passes rely on. Re-run any time:

    python3 tools/spec/tests/address_selftest.py     # exits non-zero on failure

Stdlib-only. Lives beside parity.sh as the second leg of tool verification.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # tools/spec
import address  # noqa: E402
import config as _config  # noqa: E402

CFG = _config.load()
FAKE = Path("MEM.md")


def env_for(stems, source_class, namespace=None):
    nick_map = {k.lower(): v for k, v in CFG.nicknames.items()}
    import re
    keys = sorted(nick_map, key=len, reverse=True)
    nick_re = re.compile(r"\b(" + "|".join(re.escape(k) for k in keys) + r")\b", re.I)
    return {
        "nick_re": nick_re, "nick_map": nick_map,
        "stems": set(stems), "prefixes": {s.split("-")[0] for s in stems},
        "families": CFG.doc_families, "cfg": CFG,
        "namespace": set(namespace if namespace is not None else stems),
        "source_class": source_class,
    }


def run(host_stem, text, stems, source_class="canonical-spec", docs=None, namespace=None):
    """Analyze `text` as host_stem against a synthetic corpus; return findings."""
    host = address.build_doc(host_stem, FAKE, text=text)
    corpus = {host_stem: host}
    for s in stems:
        if s not in corpus:
            corpus[s] = address.build_doc(s, FAKE, text="# t\n\n## 5. s\n### 5.2 x\n")
    if docs:
        corpus.update(docs)
    env = env_for(set(corpus), source_class, namespace)
    env["source_class"] = source_class
    return address.analyze_doc(host, corpus, env)


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def nickname_fires_on_governed_sec():
    f = run("HOST", "# t\n\n## 1. a\n\nSee V7 §5.2 for detail.\n",
            {"ENTITY-CORE-PROTOCOL"})
    nk = [x for x in f if x.cls == "nickname"]
    assert nk and nk[0].edit_new == "ENTITY-CORE-PROTOCOL.md", nk


@case
def nickname_silent_on_bare_prose():
    # "V7" with no governing § must NOT be flagged (it's prose, not a citation).
    f = run("HOST", "# t\n\n## 1. a\n\nThe V7 era and v7.75 shipped.\n",
            {"ENTITY-CORE-PROTOCOL"})
    assert not [x for x in f if x.cls == "nickname"], f


@case
def code_fence_excluded():
    f = run("HOST", "# t\n\n## 1. a\n\n```\nsee V7 §5.2 and EXTENSION-X §3\n```\n",
            {"ENTITY-CORE-PROTOCOL", "EXTENSION-X"})
    assert not f, f


@case
def depends_line_excluded():
    f = run("HOST", "# t\n**Depends**: EXTENSION-X §3\n\n## 1. a\n\nbody.\n",
            {"EXTENSION-X"})
    assert not f, f


@case
def path_artifact_excluded():
    f = run("HOST", "# t\n\n## 1. a\n\nAt `core/specs/EXTENSION-X.md` line.\n",
            {"EXTENSION-X"})
    assert not [x for x in f if x.cls == "drift"], f


@case
def drift_bare_token_gets_md():
    f = run("HOST", "# t\n\n## 1. a\n\nDefined in EXTENSION-X §5.2 here.\n",
            {"EXTENSION-X"})
    dr = [x for x in f if x.cls == "drift"]
    assert dr and dr[0].edit_new == "EXTENSION-X.md", dr
    # span replacement is surgical: only the token changes
    line = "Defined in EXTENSION-X §5.2 here."
    s, e = dr[0].edit_span
    assert line[s:e] == "EXTENSION-X", (line[s:e], dr[0].edit_span)


@case
def conformant_external_not_flagged():
    f = run("HOST", "# t\n\n## 1. a\n\nDefined in EXTENSION-X.md §5.2 here.\n",
            {"EXTENSION-X"})
    assert not f, f


@case
def nick_nested_in_doctoken_not_flagged():
    # The "V7" inside ENTITY-CORE-PROTOCOL.md is part of the filename, not a
    # prose nickname; the citation is already canonical -> no finding at all.
    f = run("HOST", "# t\n\n## 1. a\n\nopen types (ENTITY-CORE-PROTOCOL.md §5.2) here.\n",
            {"ENTITY-CORE-PROTOCOL"})
    assert not [x for x in f if x.cls == "nickname"], f
    assert not f, f


@case
def bare_internal_unresolved_flagged():
    f = run("HOST", "# t\n\n## 1. a\n\nSee §9.9 below.\n", set())
    bi = [x for x in f if x.cls == "bare-internal"]
    assert bi and bi[0].sec == "9.9", bi


@case
def bare_internal_resolved_not_flagged():
    f = run("HOST", "# t\n\n## 1. a\n### 1.1 b\n\nSee §1.1 above.\n", set())
    assert not [x for x in f if x.cls == "bare-internal"], f


@case
def leak_from_normative_spec():
    # normative spec citing a process artifact present in the namespace = leak.
    f = run("EXTENSION-X", "# t\n\n## 1. a\n\nPer PROPOSAL-FOO §2 we do this.\n",
            set(), source_class="canonical-spec",
            namespace={"EXTENSION-X", "PROPOSAL-FOO"})
    assert [x for x in f if x.cls == "leak"], f


@case
def arch_doc_citing_proposal_permitted():
    # same citation from an arch-doc is permitted provenance (§11.3) — no finding.
    f = run("ARCHITECTURE-X", "# t\n\n## 1. a\n\nPer PROPOSAL-FOO §2 we do this.\n",
            set(), source_class="arch-doc",
            namespace={"ARCHITECTURE-X", "PROPOSAL-FOO"})
    assert not [x for x in f if x.cls in ("leak", "dangling")], f


@case
def true_dangling_when_absent_everywhere():
    f = run("EXTENSION-X", "# t\n\n## 1. a\n\nSee EXTENSION-GHOST §3.\n",
            set(), namespace={"EXTENSION-X"})
    assert [x for x in f if x.cls == "dangling"], f


@case
def stale_section_when_doc_resolves_but_section_absent():
    target = address.build_doc("EXTENSION-Y", FAKE, text="# t\n\n## 1. a\n")
    f = run("HOST", "# t\n\n## 1. a\n\nSee EXTENSION-Y.md §9.9 here.\n",
            set(), docs={"EXTENSION-Y": target})
    assert [x for x in f if x.cls == "stale-section"], f


@case
def chained_sec_carries_antecedent():
    f = run("HOST", "# t\n\n## 1. a\n\nSee EXTENSION-X.md §5 / §5.2 here.\n",
            {"EXTENSION-X"})
    # both §5 and §5.2 resolve in EXTENSION-X (built with those) -> conformant,
    # and neither should be misread as a bare-internal self-ref.
    assert not [x for x in f if x.cls == "bare-internal"], f


@case
def path_prefixed_intent_is_leak():
    # A dir-prefixed PROCESS-artifact citation is NOT a filesystem-artifact
    # exemption — it is a §11.3 leak the `/` prefix used to swallow.
    f = run("EXTENSION-X", "# t\n\n## 1. a\n\nPer `explorations/EXPLORATION-FOO.md §1` here.\n",
            set(), source_class="canonical-spec",
            namespace={"EXTENSION-X", "EXPLORATION-FOO"})
    assert [x for x in f if x.cls == "leak"], f


@case
def path_prefixed_real_spec_still_exempt():
    # A dir-prefixed citation to a REAL spec stays exempt (it is a genuine path).
    f = run("HOST", "# t\n\n## 1. a\n\nAt `core/specs/EXTENSION-X.md §5.2` line.\n",
            {"EXTENSION-X"})
    assert not [x for x in f if x.cls in ("leak", "drift", "dangling")], f


@case
def forward_planned_permitted():
    # §11.4 Forward: a spec-shaped, author-marked (planned) citation to a not-yet-
    # landed sibling extension is permitted — not a dangling finding.
    #
    # CORRECTED 2026-08-17. This case used to place the citation in ordinary
    # normative prose and assert it was permitted, which encoded HALF of §11.4:
    # the rule reads "permitted ONLY when explicitly marked `(planned)` **and
    # confined to non-normative notes or an Extension Points section**." The
    # confinement clause was never implemented, and the test froze the gap in
    # place — so the shelter is now a blockquote note, which is what §11.4
    # actually grants.
    f = run("EXTENSION-X", "# t\n\n## 1. a\n\n> See EXTENSION-GHOST.md §3 (planned) here.\n",
            set(), namespace={"EXTENSION-X"})
    assert not [x for x in f if x.cls == "dangling"], f


@case
def forward_marker_does_not_mask_process_leak():
    # The (planned) marker only forgives spec-shaped names; a process artifact
    # cited as (planned) is still a §11.3 leak.
    f = run("EXTENSION-X", "# t\n\n## 1. a\n\nPer PROPOSAL-FOO §2 (planned) here.\n",
            set(), source_class="canonical-spec",
            namespace={"EXTENSION-X", "PROPOSAL-FOO"})
    assert [x for x in f if x.cls == "leak"], f


@case
def section_style_paragraph_heading_resolves():
    # `## §N` headings (used by EXTENSION-ROUTE / EXTENSION-RELAY) must register as
    # sections, else valid external citations to them read as stale-section.
    target = address.build_doc("EXTENSION-RLY", FAKE,
                               text="# t\n\n## §3 Types\n### §3.1 Forward\n#### §3.1.1 Next-hop\n")
    assert "3.1.1" in target.sections, target.sections
    f = run("HOST", "# t\n\n## 1. a\n\nNo RELAY to receive (EXTENSION-RLY.md §3.1.1).\n",
            set(), docs={"EXTENSION-RLY": target})
    assert not [x for x in f if x.cls == "stale-section"], f


# --- multi-root namespace resolution ----------------------------------------
# Why these exist: `namespace` decides whether a citation to a document outside
# the analysis scope resolves or is reported `dangling`. It was built from one
# corpus root while this corpus spans two repos, so every citation to
# ENTITY-CORE-PROTOCOL (495 of them), ENTITY-NATIVE-TYPE-SYSTEM (24), and
# ENTITY-CBOR-ENCODING (4) reported as "target absent from corpus" — ~523 of 574
# `dangling` findings were unreachable, not absent. That is could-not-look
# rendered as a verdict, in the analyzer built to catch that, and it is why
# `address` could not be gated. Measured after the fix: 574 -> 5.


@case
def extra_namespace_root_makes_a_sibling_doc_resolvable():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "ENTITY-CORE-PROTOCOL.md").write_text("# core\n")
        ns = address.extra_namespace([root])
        assert "ENTITY-CORE-PROTOCOL" in ns, ns


@case
def sibling_doc_no_longer_reports_dangling():
    env = env_for(["EXTENSION-SUBSCRIPTION"], "canonical-spec",
                  namespace={"EXTENSION-SUBSCRIPTION", "ENTITY-CORE-PROTOCOL"})
    out = address._dispose_external("ENTITY-CORE-PROTOCOL", "5.5", "canonical-spec", env)
    assert out is None, out


@case
def unreachable_sibling_doc_still_reports_dangling_without_the_root():
    env = env_for(["EXTENSION-SUBSCRIPTION"], "canonical-spec",
                  namespace={"EXTENSION-SUBSCRIPTION"})
    out = address._dispose_external("ENTITY-CORE-PROTOCOL", "5.5", "canonical-spec", env)
    assert out is not None and out[0] == "dangling", out


@case
def missing_namespace_root_is_could_not_look_not_a_verdict():
    try:
        address._namespace_roots([Path("/definitely/not/a/real/root")])
    except address.CouldNotLook:
        return
    raise AssertionError("a configured-but-absent root must raise CouldNotLook, not resolve to empty")


@case
def no_namespace_root_configured_is_not_an_error():
    assert address._namespace_roots([]) == [] or isinstance(address._namespace_roots([]), list)


# ---------------------------------------------------------------------------
# Analysis scope — WHOSE citations get graded.
#
# `address` rooted at `specs/` for its whole life, so all 34 guides were loaded
# as citation TARGETS and graded as SOURCES by nothing. That asymmetry is
# invisible from the output: a scope that is never read reports the same zero
# findings as a scope that is clean. These invariants are the enforcement point
# — they assert the published surface is the analysis set, and that the
# agent-guidance files sharing its root stay out.
# ---------------------------------------------------------------------------


def _tree(base, files):
    for rel, body in files.items():
        p = Path(base) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return Path(base)


@case
def analysis_scope_includes_guides_not_only_specs():
    scope = CFG.scope("addressing-analysis")
    assert scope.root.name != "specs", (
        "the analysis root is still specs/ — guides would be graded by nothing")
    assert "guides" not in scope.exclude_dirs, scope.exclude_dirs


@case
def analysis_scope_excludes_the_intent_workspace():
    scope = CFG.scope("addressing-analysis")
    for d in ("docs", "proposals", "research", "status"):
        assert d in scope.exclude_dirs, (
            "%r must stay out of the analysis set — drafts and immutable dated "
            "snapshots cannot be corrected, so gating them is a permanent red" % d)


@case
def load_corpus_grades_a_guide_and_skips_agent_guidance():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        base = _tree(tmp, {
            "specs/EXTENSION-ALPHA.md": "# a\n\n## 1. s\n",
            "guides/GUIDE-ALPHA.md": "# g\n\n## 1. s\n",
            "AGENTS.md": "# agents\n\n## 1. s\n",
            "docs/proposals/PROPOSAL-X.md": "# p\n\n## 1. s\n",
        })
        scope = CFG.scope("addressing-analysis")
        docs = address.load_corpus(base, set(scope.exclude_dirs),
                                   set(scope.exclude_files))
        assert "GUIDE-ALPHA" in docs, ("a guide must be an analysis SOURCE; "
                                       "got %s" % sorted(docs))
        assert "EXTENSION-ALPHA" in docs, sorted(docs)
        assert "AGENTS" not in docs, ("agent guidance is not governed by §11 and "
                                      "must not be graded; got %s" % sorted(docs))
        assert "PROPOSAL-X" not in docs, sorted(docs)


@case
def a_guide_citing_an_absent_document_still_reports_dangling():
    # The class that matters in a guide. §11.3 row 2 lets a guide cite intent
    # artifacts as provenance, so those are NOT findings — but a citation to a
    # document absent from the whole corpus is, and that is exactly what
    # survived unseen in the networking guide's status board.
    env = env_for(["EXTENSION-ALPHA"], "guide", namespace={"EXTENSION-ALPHA"})
    out = address._dispose_external("PROPOSAL-NEVER-WRITTEN", "1.1", "guide", env)
    assert out is not None and out[0] == "dangling", out


@case
def a_guide_citing_a_present_intent_artifact_is_permitted_provenance():
    env = env_for(["EXTENSION-ALPHA"], "guide",
                  namespace={"EXTENSION-ALPHA", "PROPOSAL-REAL"})
    out = address._dispose_external("PROPOSAL-REAL", "1.1", "guide", env)
    assert out is None, ("a guide citing a real proposal is informational "
                         "provenance under §11.3, not a leak; got %r" % (out,))


@case
def absent_doc_fires_on_a_named_document_with_no_section():
    # THE 2026-08-17 defect, verbatim in shape. `EXTENSION-NETWORK` §6.5.3.1's
    # `MANIFEST_GET` MUST said its revocation primitive "is defined in
    # PROPOSAL-PEER-MANIFEST-STATIC-HANDSHAKE" — a document that has never
    # existed in any repo. Two app-tier seats built a static publishing surface
    # against it. `address` never saw the sentence, because the scan skipped
    # every line carrying no `§`.
    f = run("HOST", "# t\n\n## 1. a\n\n- **Rule (MUST).** Its primitive is "
                    "defined in `PROPOSAL-NEVER-WRITTEN`.\n",
            {"EXTENSION-ALPHA"})
    ad = [x for x in f if x.cls == "absent-doc"]
    assert ad and ad[0].target == "PROPOSAL-NEVER-WRITTEN", f


@case
def absent_doc_silent_on_a_document_that_exists():
    f = run("HOST", "# t\n\n## 1. a\n\nSee `EXTENSION-ALPHA` for the shape.\n",
            {"EXTENSION-ALPHA"})
    assert not [x for x in f if x.cls == "absent-doc"], f


@case
def absent_doc_silent_in_a_cross_references_section():
    # §11.3 row 2: provenance lists are where naming a document the corpus does
    # not hold is *allowed*. Measured 2026-08-17: without this shelter the rule
    # opens 228 red on this corpus, ~200 of them legitimate provenance — and a
    # gate that opens 228 red is a gate people learn to skip.
    f = run("HOST", "# t\n\n## 9. Cross-references\n\n"
                    "- `PROPOSAL-NEVER-WRITTEN` — provenance.\n",
            {"EXTENSION-ALPHA"})
    assert not [x for x in f if x.cls == "absent-doc"], f


@case
def absent_doc_silent_in_a_blockquote_note():
    f = run("HOST", "# t\n\n## 1. a\n\n> Note: `EXTENSION-FUTURE` (planned) "
                    "will carry this.\n",
            {"EXTENSION-ALPHA"})
    assert not [x for x in f if x.cls == "absent-doc"], f


@case
def forward_marked_citation_in_normative_text_is_not_exempt():
    # §11.4 has TWO clauses — marked `(planned)` AND confined to a
    # non-normative note or an Extension Points section. The analyzer
    # implemented only the first, so a `(planned)` pointer sat inside a MUST
    # bullet in `EXTENSION-NETWORK` §6.5.6 and gated nothing.
    f = run("HOST", "# t\n\n## 1. a\n\n- **Rule (MUST).** Per "
                    "`EXTENSION-FUTURE.md` §1.1 (planned) the walk holds.\n",
            {"EXTENSION-ALPHA"})
    dg = [x for x in f if x.cls == "dangling"]
    assert dg and "normative text" in dg[0].note, f


def main():
    failed = 0
    for fn in CASES:
        try:
            fn()
            print("  ok   %s" % fn.__name__)
        except AssertionError as exc:
            failed += 1
            print("  FAIL %s — %s" % (fn.__name__, exc))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("  ERR  %s — %r" % (fn.__name__, exc))
    print("\n%d/%d invariants pass" % (len(CASES) - failed, len(CASES)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
