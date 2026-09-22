#!/usr/bin/env python3
"""standards_selftest — invariant checks for `hash-width-pin`, proposal-citation
resolution, and the baseline ratchet.

Like `address_selftest`, this pins *behavior* against synthetic fixtures rather
than finding counts, so corpus corrections never make it stale.

Why this rule has a self-test at all: §8.4.5 shipped as a corpus-wide
prohibition enforced by a documented grep, in the same packet whose §5.2b
concluded that a discipline is exactly what fails. A deliberate one-pass sweep
by two parties then left nine survivors, two of them normative and one deriving
an encryption key. The rule exists to move the invariant into the mechanism;
this file is what keeps the rule honest.

    python3 spec-tool/tests/standards_selftest.py    # exits non-zero on failure

Stdlib-only. Third leg of tool verification, beside parity.sh + address_selftest.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import standards  # noqa: E402

FAKE = Path("MEM.md")
FAILURES = []
# Every case that ran, so the summary counts itself. It used to be a hardcoded
# "48/48" and was already off by one before anyone noticed — a literal copy of a
# number that changes every time a case is added is drift with a countdown on it.
PASSED = []


def widths(text):
    """Return hash-width-pin findings for `text`."""
    return [f for f in standards.analyze(FAKE, text) if f.rule == "hash-width-pin"]


def case(name, text, want):
    PASSED.append(name)
    got = len(widths(text))
    if got != want:
        FAILURES.append(f"{name}: want {want} finding(s), got {got}")
        print(f"  FAIL {name} (want {want}, got {got})")
    else:
        print(f"  ok   {name}")


# --- it fires on the shapes that actually shipped ---------------------------
# Each of these is a real defect found on 2026-08-10, reduced to one line.

case("network_hex_width_pinned",
     "- **Hash hex = 66, format-code included (MUST).** The content hash in the URL.", 1)

case("encryption_hkdf_info_fixed",
     "`recipient_pubkey_hash` is the **full 33-byte content_hash** — prefix + digest.", 1)

case("relay_cddl_bstr_fixed",
     "  envelope_inner:  <bstr, 33 bytes>      ; the content hash of the inner", 1)

case("tree_link_fixed",
     "  CBOR major type 2 (byte string) -> Link: 33-byte system/hash of a sub-node", 1)

case("registry_bare_hash_fixed",
     "are **bare `system/hash`** values (33 bytes, `0x00`+digest), NOT wrapped.", 1)

case("hex33_is_a_lockin_by_name",
     "The consumer fetches with `CONTENT_GET /content/{hex33(H)}` (§6.5.3 step 5).", 1)

case("ffi_style_length_gate",
     "Reject the request when `content_hash` hex len() != 66 (strict wire form).", 1)

# --- fences are NOT a hiding place ------------------------------------------
# Every instance the SHA-384 run could not reach was inside a CDDL or
# pseudocode block, which is precisely where an implementer reads a width.
case("fires_inside_a_code_fence",
     "```\ncontent_hash: <33 bytes>   ; the entity hash\n```", 1)

# --- it stays quiet where the text says why the width is safe ---------------

case("exempt_when_length_follows_the_format_byte",
     "The `content_hash` hex length follows its own format byte — never assumed.", 0)

case("exempt_when_citing_the_rule",
     "  envelope_inner: <bstr>   ; content hash, length per format byte (§8.4.5)", 0)

case("exempt_worked_instance_guarded_by_format",
     "`{peer_id_hex}` is lowercase hex of `system/hash`; under SHA-256 that is 66 chars.", 0)

case("exempt_pinned_format_derive_to_meet",
     "`prefix_hash` is pinned to the ECFv1-SHA-256 floor: 66 chars, on every peer.", 0)

case("exempt_text_arguing_against_a_width",
     "`system/hash` is variable-length per §1.2 — \"33 bytes\" is only today's size.", 0)

case("exempt_historical_note_that_a_lockin_was_removed",
     "**`hex33` removed** — it re-locked SHA-256; the system is encoding-agnostic.", 0)

# The acknowledgement may sit a few lines away — CDDL comments wrap.
case("exemption_reaches_across_nearby_lines",
     "  envelope_inner:  <bstr>\n"
     "     ; the content hash of the carried inner envelope, 33 B under SHA-256,\n"
     "     ; its length following the format byte — never fixed (§8.4.5)", 0)

case("exemption_does_not_reach_across_a_whole_section",
     "The hash is a **33-byte content_hash** value.\n" + "\n" * 12 +
     "Elsewhere: the length follows the format byte (§8.4.5).", 1)

# --- it does not fire on widths that have nothing to do with hashes ---------

case("quiet_on_unrelated_numbers",
     "The bucket holds at most 33 entries and the bitmap is 66 bits wide.", 0)

case("quiet_on_a_key_length",
     "An Ed25519 public key is 32 bytes; a signature is 64 bytes.", 0)


# --- proposal-citation resolution -------------------------------------------
# Why this half exists: the editorial `proposal-citation` warn fired correctly on
# a citation that pointed at nothing, for two months, and told nobody — because
# it says "internal routing", not "this resolves to no file". A search then
# concluded the document did not exist without opening the pre-split archive, and
# four green conformance checks were proposed for retraction on that basis. These
# cases pin the resolution behavior, and especially the three-valued part: the
# tool must not call a name dangling when it was never given somewhere to look.

import tempfile  # noqa: E402


def rule_hits(text, rule):
    return [f for f in standards.analyze(FAKE, text) if f.rule == rule]


def rcase(name, text, rule, want):
    PASSED.append(name)
    got = len(rule_hits(text, rule))
    if got != want:
        FAILURES.append(f"{name}: want {want} {rule}, got {got}")
        print(f"  FAIL {name} (want {want} {rule}, got {got})")
    else:
        print(f"  ok   {name}")


ARCHIVE = tempfile.TemporaryDirectory()
_ap = Path(ARCHIVE.name)
(_ap / "PROPOSAL-CONVERGENT-MIRRORING.md").write_text("archived proposal\n")
(_ap / "PROPOSAL-ROLE-V1.2.md").write_text("suffixed filename\n")
(_ap / "PROPOSAL-STAGE-5-POSITIONS-cgid-10-214.md").write_text("stamped filename\n")

CITE = "See `proposals/implemented/%s.md` for the derivation."

# (1) No archive configured: unresolvable is a WARN, never an error. This is the
#     honest-uncertainty case — absence of evidence is not evidence of absence.
standards.set_proposal_archives([])
rcase("no_archive__unknown_name_is_warn_not_error",
      CITE % "PROPOSAL-DEFINITELY-NOT-A-REAL-DOCUMENT",
      "proposal-citation-unresolved", 1)
rcase("no_archive__never_errors",
      CITE % "PROPOSAL-DEFINITELY-NOT-A-REAL-DOCUMENT",
      "proposal-citation-dangling", 0)

# (2) Archive configured: a name that resolves is silent on both new rules; a
#     name that resolves nowhere is an ERROR, because now we did look.
standards.set_proposal_archives([_ap])
rcase("archived_name_resolves__no_dangling",
      CITE % "PROPOSAL-CONVERGENT-MIRRORING", "proposal-citation-dangling", 0)
rcase("archived_name_resolves__no_unresolved",
      CITE % "PROPOSAL-CONVERGENT-MIRRORING", "proposal-citation-unresolved", 0)
rcase("archive_configured__truly_absent_name_is_error",
      CITE % "PROPOSAL-DEFINITELY-NOT-A-REAL-DOCUMENT",
      "proposal-citation-dangling", 1)

# (3) Prefix matching. Citations routinely drop a version suffix or a cgid stamp;
#     16 of this corpus's 104 citations resolve only this way.
rcase("citation_may_drop_a_version_suffix",
      CITE % "PROPOSAL-ROLE-V1", "proposal-citation-dangling", 0)
rcase("citation_may_drop_a_cgid_stamp",
      CITE % "PROPOSAL-STAGE-5-POSITIONS", "proposal-citation-dangling", 0)

# (4) The editorial warn is unchanged — this rule adds resolution, it does not
#     replace the existing "not normative" signal.
rcase("editorial_warn_still_fires_for_a_resolvable_name",
      CITE % "PROPOSAL-CONVERGENT-MIRRORING", "proposal-citation", 1)

# (4a) An entity-tree path with a `proposals/` segment is NOT a citation, and
#      this fired for real: the rule matched a bare `\bproposals/`, so
#      EXTENSION-IDENTITY §5.1's `system/identity/internal/proposals/{kind}-{id}`
#      — normative spec content naming a staging subtree — was reported as
#      internal routing noise, and it gated. **A directory name is not a
#      citation.** Both directions are pinned here: the entity path stays silent,
#      the document path still fires.
rcase("entity_tree_path_with_proposals_segment_is_not_a_citation",
      "Draft attestations stage at `system/identity/internal/proposals/{kind}-{id}`.",
      "proposal-citation", 0)
rcase("a_proposals_segment_in_any_tree_path_is_silent",
      "Bind under `system/vc/proposals/pending` and sweep on commit.",
      "proposal-citation", 0)
rcase("docs_proposals_path_still_fires",
      "See `docs/proposals/active/extensions/whatever.md` for the derivation.",
      "proposal-citation", 1)
rcase("proposals_state_dir_path_still_fires",
      "Recorded in `proposals/implemented/core/the-thing.md`.",
      "proposal-citation", 1)
# The first fix for this was too tight and the parity golden caught it: a
# lowercase filename under a bare `proposals/` is a real citation and stopped
# firing. **A document reference ends in `.md`; an entity path does not** — that
# is the discriminator, not the capitalisation of the stem.
rcase("lowercase_proposal_filename_still_fires",
      "It graduated from `proposals/example-widget.md`, a process-routing citation.",
      "proposal-citation", 1)

# (5) `[PROPOSAL-FIRST]` is the lifecycle tag, not a filename. Reporting the
#     corpus's own process vocabulary as a missing document is an error nobody
#     can fix, which is how a gate trains its readers to ignore it.
rcase("lifecycle_tag_is_not_a_citation",
      "- `[PROPOSAL-FIRST]` **A4** — ingest-completeness guardrail (loud-reject).",
      "proposal-citation-dangling", 0)

# (6) A configured root that does not exist is could-not-look, not a verdict.
standards.set_proposal_archives([_ap / "no-such-directory"])
try:
    standards.analyze(FAKE, CITE % "PROPOSAL-CONVERGENT-MIRRORING")
    FAILURES.append("missing_archive_root_must_raise_CouldNotLook: no exception")
    print("  FAIL missing_archive_root_must_raise_CouldNotLook")
except standards.CouldNotLook:
    print("  ok   missing_archive_root_must_raise_CouldNotLook")

standards.set_proposal_archives([])


# --- the baseline ratchet ---------------------------------------------------
# Five rules were promoted warn → error. On the arch corpus that is 573 findings
# across 26 of 40 specs, so severity ALONE would have turned the gate red on
# contact and been switched off inside a day. The ratchet is what makes the
# promotion survivable: known debt is held, new debt gates.
#
# Every invariant below is about the ASYMMETRY. A baseline that can be raised is
# not a ratchet — the next contaminated commit re-baselines itself green and the
# run looks clean, which is strictly worse than the warn it replaced.
import tempfile as _tf  # noqa: E402

B = standards.Baseline


def r_case(name, ok):
    PASSED.append(name)
    if ok:
        print(f"  ok   {name}")
    else:
        FAILURES.append(name)
        print(f"  FAIL {name}")


# (1) The promoted rules really are errors — pins against a silent demotion,
#     since the whole mechanism rests on these gating.
r_case("promoted_rules_are_errors",
       all(standards.RULES[r][0] == "error" for r in standards.BASELINE_RULES))

# (2) A baseline survives to_json → load with its counts intact.
_b = B({("a.md", "date-in-body"): 3, ("b.md", "impl-team-ref"): 1})
_p = Path(_tf.mkdtemp()) / "bl.json"
_p.write_text(_b.to_json())
r_case("baseline_round_trips", B.load(_p).counts == _b.counts)

# (3)/(4) Within budget → held. Beyond budget → gates.
_f = [standards.Finding("date-in-body", 10, "x"),
      standards.Finding("date-in-body", 11, "y")]
_rep = {"a.md": _f}
_new, _known, _ = standards.apply_baseline(_rep, B({("a.md", "date-in-body"): 2}))
r_case("within_baseline_does_not_gate", _new == {} and _known == 2)

_new, _known, _ = standards.apply_baseline(_rep, B({("a.md", "date-in-body"): 1}))
r_case("beyond_baseline_gates", len(_new.get("a.md", [])) == 1 and _known == 1)

# (5) A file absent from the baseline is not silently exempt.
_new, _known, _ = standards.apply_baseline(_rep, B({}))
r_case("absent_file_is_all_new", len(_new.get("a.md", [])) == 2 and _known == 0)

# (6) THE load-bearing one: the ratchet refuses to raise.
_old = B({("a.md", "date-in-body"): 1})
_r, _refused = standards.ratchet_baseline(_old, {("a.md", "date-in-body"): 5})
r_case("ratchet_refuses_to_raise",
       len(_refused) == 1 and _r.counts[("a.md", "date-in-body")] == 1)

# (7) A wholly new file is refused, not absorbed.
_r, _refused = standards.ratchet_baseline(_old, {("zz.md", "impl-team-ref"): 1})
r_case("ratchet_refuses_new_file", len(_refused) == 1)

# (8) It does lower when the debt was actually paid.
_r, _refused = standards.ratchet_baseline(
    B({("a.md", "date-in-body"): 4}), {("a.md", "date-in-body"): 1})
r_case("ratchet_lowers_when_paid",
       not _refused and _r.counts[("a.md", "date-in-body")] == 1)

# (9) Paid debt is REPORTED as retired, never silently rewritten — an oracle
#     that edits the file it is measured against has stopped being one.
_new, _known, _retired = standards.apply_baseline({}, B({("a.md", "date-in-body"): 2}))
r_case("paid_debt_reported_retired", _retired == {("a.md", "date-in-body"): 2})

# (9a) A file that MOVED keeps its accepted debt. In this corpus a rename is the
#      normal lifecycle — folding a proposal moves it active/ → implemented/ — so
#      a path-keyed baseline would report every fold as a wall of new errors.
_moved_rep = {"docs/proposals/implemented/x/P-ONE.md":
              [standards.Finding("impl-team-ref", 3, "seat"),
               standards.Finding("impl-team-ref", 9, "seat")]}
_moved_base = B({("docs/proposals/active/x/P-ONE.md", "impl-team-ref"): 2})
_scanned = {"docs/proposals/implemented/x/P-ONE.md"}
_new, _known, _ret = standards.apply_baseline(_moved_rep, _moved_base, _scanned)
r_case("moved_file_keeps_its_baselined_debt",
       _new == {} and _known == 2 and _ret == {})

#      …and the ratchet re-keys it rather than refusing the new path forever.
_r, _refused = standards.ratchet_baseline(
    _moved_base, {("docs/proposals/implemented/x/P-ONE.md", "impl-team-ref"): 2},
    _scanned)
r_case("ratchet_follows_a_move",
       not _refused
       and _r.counts.get(("docs/proposals/implemented/x/P-ONE.md",
                          "impl-team-ref")) == 2)

#      NEGATIVE CONTROL — following a move must not launder an increase.
_new, _known, _ = standards.apply_baseline(
    {"docs/proposals/implemented/x/P-ONE.md":
     [standards.Finding("impl-team-ref", i, "seat") for i in range(5)]},
    _moved_base, _scanned)
r_case("a_move_does_not_launder_new_debt",
       len(_new.get("docs/proposals/implemented/x/P-ONE.md", [])) == 3
       and _known == 2)

#      NEGATIVE CONTROL — ambiguity is left alone, never guessed at. Two files of
#      the same basename moving at once could be transplanted onto each other.
_amb_base = B({("a/P-TWO.md", "impl-team-ref"): 2,
               ("b/P-TWO.md", "impl-team-ref"): 2})
_amb_scanned = {"c/P-TWO.md"}
r_case("ambiguous_move_is_not_inferred",
       standards.resolve_moves(_amb_base, _amb_scanned) == {})

#      NEGATIVE CONTROL — an unrelated new file is still all-new debt.
r_case("unrelated_new_file_is_not_a_move",
       standards.resolve_moves(_moved_base, {"docs/proposals/active/x/P-ONE.md",
                                             "docs/proposals/active/x/P-NEW.md"})
       == {})

#      A caller that does not say what it read is told nothing about moves.
r_case("no_scanned_set_means_no_move_inference",
       standards.resolve_moves(_moved_base, None) == {})

# (10) Only the five narrative rules are ratchetable; everything else gates
#      whatever the baseline says.
r_case("non_baseline_rule_unaffected",
       "title-not-h1" not in standards.BASELINE_RULES
       and standards.RULES["title-not-h1"][0] == "error")

# (11) THE SPEC/WORKFLOW SPLIT. `specs/` holds two kinds of document. The
#      normative specs are architecture's OUTPUT and must not name a repo or a
#      date. The informative architecture docs and charters describe how the work
#      is ORGANIZED, and naming the reference implementations there is their job.
#      Same sentence, opposite verdicts — which is the whole point.
_NARRATIVE = "> Ruled 2026-08-15 after `entity-core-go` routed it.\n"
r_case("narrative_rules_score_a_normative_spec",
       len([f for f in standards.analyze(Path("EXTENSION-GADGET.md"), _NARRATIVE)
            if f.rule in standards.BASELINE_RULES]) > 0)
r_case("narrative_rules_spare_an_arch_doc",
       len([f for f in standards.analyze(Path("SYSTEM-ARCHITECTURE.md"), _NARRATIVE)
            if f.rule in standards.BASELINE_RULES]) == 0)
r_case("narrative_rules_spare_a_charter",
       len([f for f in standards.analyze(Path("CHARTER.md"), _NARRATIVE)
            if f.rule in standards.BASELINE_RULES]) == 0)
# Structural rules are NOT class-scoped — an arch doc still owes a clean header.
# Class drives disposition, not discovery.
r_case("structural_rules_still_apply_to_an_arch_doc",
       any(f.rule == "title-not-h1"
           for f in standards.analyze(Path("SYSTEM-ARCHITECTURE.md"), _NARRATIVE)))

# (12) THE BLIND SPOT, pinned deliberately rather than discovered later.
#      Entries are keyed (file, rule) → count, so a SWAP is invisible: delete one
#      violation, add a different one in the same file, and the gate stays green.
#      That is the documented cost of not keying on line numbers, which move on
#      every edit above a finding — a line-keyed baseline reports whole files as
#      new debt on unrelated changes and gets deleted. This gate catches
#      ACCUMULATION, not SUBSTITUTION. If this test ever fails the key shape
#      changed, and the module docstring must change with it.
_swapped = [standards.Finding("date-in-body", 99, "a different violation"),
            standards.Finding("date-in-body", 100, "another one")]
_new, _known, _ = standards.apply_baseline({"a.md": _swapped},
                                           B({("a.md", "date-in-body"): 2}))
r_case("known_blind_spot_swap_is_invisible", _new == {} and _known == 2)

# (13) A FILE NOT READ IS NOT A FILE WITH NO DEBT.
#      `--root ONE-FILE --update-baseline` used to lower every unscanned entry to
#      zero — the ratchet only ever lowers, so no refusal fired and the run
#      reported success while erasing the record it exists to keep. The same
#      unscanned-reads-as-zero mistake made the report claim "80 entries
#      over-count — debt was paid" after opening one file, and pointed the reader
#      at the command that would act on it.
_old = B({("a.md", "date-in-body"): 5, ("b.md", "date-in-body"): 7})
_seen_partial = {("a.md", "date-in-body"): 2}          # only a.md was read
_ratched, _refused = standards.ratchet_baseline(_old, _seen_partial, scanned={"a.md"})
r_case("ratchet_carries_unscanned_entries_forward",
       _ratched.counts[("b.md", "date-in-body")] == 7 and not _refused)
r_case("ratchet_still_lowers_what_it_read",
       _ratched.counts[("a.md", "date-in-body")] == 2)
# Without the scanned set the old behaviour is reproduced exactly — this is the
# injected fault, so the test above cannot pass vacuously.
_wiped, _ = standards.ratchet_baseline(_old, _seen_partial)
r_case("negative_control_unscoped_ratchet_would_wipe",
       _wiped.counts[("b.md", "date-in-body")] == 0)
# `retired` (the "debt was paid" report) is likewise scoped to what was read.
_, _, _ret = standards.apply_baseline({"a.md": [standards.Finding("date-in-body", 1, "x")]},
                                      _old, scanned={"a.md"})
r_case("retired_ignores_unscanned_files",
       list(_ret) == [("a.md", "date-in-body")])

# (13) EVERY SEAT, NOT MOST SEATS. `impl-team-ref` carried an alternation that
#      caught every implementation team except one: `entity-browser-rust` is
#      neither an `entity-core-*` repo nor a one-word product name, so the two
#      patterns that cover everyone else (`keystone`, `workbench`) both missed
#      it — and a seat name reached normative spec text while the gate ran green.
#      A rule blind to exactly one member of a known, enumerable set is worse
#      than no rule, because its silence reads as a pass. The set is pinned here
#      by enumeration: adding a repo to the polyrepo means adding it to this
#      list and watching it fail first.
def _team_hit(text):
    return any(f.rule == "impl-team-ref"
               for f in standards.analyze(Path("EXTENSION-GADGET.md"), text + "\n"))


for _seat in ("entity-core-go", "entity-core-rust", "entity-core-py",
              "entity-browser-rust", "entity-workbench-go", "entity-core-keystone"):
    r_case("impl_team_ref_catches_" + _seat.replace("-", "_"),
           _team_hit("Reported by `" + _seat + "` during the review."))

# The bare form appears in prose as often as the repo name.
r_case("impl_team_ref_catches_bare_browser_rust",
       _team_hit("browser-rust raised this against §4.5.1."))

# NEGATIVE CONTROLS — these keep the alternation from being widened into noise.
# `Rust` is a language and appears legitimately in normative text; a rule that
# flagged it would be re-baselined into irrelevance within a release.
r_case("impl_team_ref_spares_the_language_rust",
       not _team_hit("Implementations in Rust MUST preserve the received bytes."))
r_case("impl_team_ref_spares_the_word_browser",
       not _team_hit("A browser peer hands these to `RTCIceServer.urls` verbatim."))

# (14) THE PUBLISHED-SURFACE RULES. `docs/proposals` and
#      `docs/research/explorations` are declared `[[keep_tree]]` — they publish —
#      and the narrative rules never read one of them, because narrative scoring
#      was keyed on document CLASS and those documents are class `intent`. The
#      class was a proxy for "will a stranger read this", correct until the day
#      the keep_trees were declared. These rules score only when the SCOPE is the
#      publication declaration, so they are exercised with that flag set.
def _pub(text, rule):
    """Findings of `rule` for `text` under the published-surface scope."""
    prev = standards.PUBLISHED_SURFACE_SCOPE
    standards.PUBLISHED_SURFACE_SCOPE = True
    try:
        return [f for f in standards.analyze(Path("PROPOSAL-THING.md"), text + "\n")
                if f.rule == rule]
    finally:
        standards.PUBLISHED_SURFACE_SCOPE = prev


def p_case(name, cond):
    PASSED.append(name)
    if not cond:
        FAILURES.append(name)
        print(f"  FAIL {name}")
    else:
        print(f"  ok   {name}")


print("\npublished-surface leak rules")
p_case("operator_quote_is_caught",
       _pub("**Operator-directed, 2026-09-06:** *\"pull the research together\"*",
            "operator-quote"))
p_case("operator_possessive_is_caught",
       _pub("the operator's own read is that it could be a site", "operator-quote"))
p_case("bracketed_operator_note_is_caught",
       _pub("`[operator, 2026-08-21, paraphrased: arch can manage core]`",
            "operator-quote"))
# THIS FILE PUBLISHES, so the meta-repo branch of INTERNAL_PATH_RE is exercised
# from the rule's OWN alternation rather than from a hand-typed literal — a real
# internal tree name written here is precisely the defect the rule exists to
# catch, and a fixture that commits it is not a fixture, it is an instance.
# Deriving it also means the case cannot silently stop covering this branch when
# the alternation changes, which a literal would.
#
# Fails closed on its own input: if the pattern is reshaped so the alternation
# cannot be read, this raises instead of quietly testing nothing. An empty
# derived set would otherwise loop zero times and print exactly like a pass.
_meta_alt = __import__("re").search(r"entity-\(\?:([^)]+)\)-meta", standards.INTERNAL_PATH_RE.pattern)
if _meta_alt is None:
    raise SystemExit("standards_selftest: cannot read INTERNAL_PATH_RE's meta-repo "
                     "alternation — refusing to report a pass on an untested branch")
_meta_names = [f"entity-{alt}-meta" for alt in _meta_alt.group(1).split("|")]
if not _meta_names:
    raise SystemExit("standards_selftest: INTERNAL_PATH_RE's meta-repo alternation is "
                     "empty — refusing to report a pass on an untested branch")
for _i, _name in enumerate(_meta_names):
    # Numbered, not named: this runs in public CI, and printing the derived name
    # would put back on a log the thing the derivation just took out of the file.
    p_case(f"internal_meta_path_is_caught[{_i}]",
           _pub(f"see `{_name}/entity-core-architecture/docs`", "internal-path-ref"))
p_case("agent_guidance_file_is_caught",
       _pub("`AGENTS.md` L16 names the region to search", "internal-path-ref"))
p_case("status_dir_is_caught",
       _pub("recorded in `docs/status/HANDOFF-2026-09-01-b.md`", "internal-path-ref"))
p_case("discipline_letter_is_caught",
       _pub("This is L23 on the document axis.", "discipline-letter-ref"))
p_case("discipline_letter_possessive_is_caught",
       _pub("L8's fifteenth form applies here.", "discipline-letter-ref"))

# NEGATIVE CONTROLS. Each of these is legitimate published prose, and a rule
# that fired on them would be re-baselined into irrelevance inside a release.
print("  -- negative controls --")
p_case("layer_names_L0_to_L5_are_published_vocabulary",
       not _pub("the L5 application conventions sit above L1", "discipline-letter-ref"))
p_case("L5_is_not_a_discipline_letter",
       not _pub("An L5 convention MUST NOT assume a transport.",
                "discipline-letter-ref"))
p_case("the_word_operators_is_not_an_operator_quote",
       not _pub("Comparison operators evaluate left to right.", "operator-quote"))
# "operator" is ALSO this corpus's word for the deployment role — 465 occurrences
# across specs/ and guides/. The compound adjectives are certain noise and are
# exempt; everything ambiguous still fires, because for a LEAK rule a false
# positive costs one baseline line and a miss is published to a stranger.
for _noise in ("Bounds are operator-configurable; defaults conservative.",
               "a narrower path with operator-class authority",
               "consult specific operator-authored sources without signatures",
               "surfaced to the peer operator via an observable mechanism",
               "an operator-supplied handle — a URL query, a QR code"):
    p_case("deployment_sense_%s" % _noise.split()[-1].strip(".,—"),
           not _pub(_noise, "operator-quote"))
# ...and the ambiguous forms deliberately still fire. Each of these is a real
# leak that a tightened, attribution-only pattern dropped when it was measured.
for _leak in ("From an operator question about store-and-forward under churn",
              "Direction: confirmed by the operator (2026-07-20)",
              "Authored in the arch workspace at the operator's request",
              "the payoff the operator named in the bridge doc"):
    p_case("still_fires_%s" % _leak.split()[1], _pub(_leak, "operator-quote"))
p_case("an_ordinary_spec_path_is_not_an_internal_path",
       not _pub("defined in `specs/extensions/EXTENSION-TREE.md` §3.3a",
                "internal-path-ref"))
p_case("a_guides_path_is_not_an_internal_path",
       not _pub("see `guides/GUIDE-CONFORMANCE.md` §5.1", "internal-path-ref"))

# A seat token inside OUR OWN DOCUMENT NAME is a citation, not a seat reference.
# `guides/GUIDE-ENTITY-WORKBENCH-APP.md` is a published guide cited by name in
# seven other published guides, and `workbench` caught every one — an accusation
# the author cannot fix, because the citation IS the document's name.
#
# Asserted in BOTH directions: an exemption that also silences the real finding
# is worse than the false positive it fixes.
print("  -- a seat token inside a document name is a citation --")
p_case("doc_name_workbench_is_a_citation",
       not standards.impl_team_hit(
           "see `GUIDE-ENTITY-WORKBENCH-APP` §5.4 rule 3 for the carve-out"))
p_case("doc_name_alone_on_a_table_row_is_silent",
       not standards.impl_team_hit("| `GUIDE-ENTITY-WORKBENCH-APP.md` §5.4 | the rule |"))
#      ...and every real reference still fires, including beside a document name:
#      the exemption strips a SPAN, it is never a line-level pardon.
p_case("seat_beside_a_doc_name_still_fires",
       standards.impl_team_hit(
           "`GUIDE-ENTITY-WORKBENCH-APP` says so; `entity-core-rust` disagrees"))
for _seat in ("workbench-go ships this today",
              "`entity-workbench-go` measured it",
              "keystone is the conformance anchor",
              "browser-rust shipped the arm",
              "the cohort agreed on Tuesday",
              "guides/guide-entity-workbench-app.md"):   # lowercase is not a doc name
    p_case("seat_still_fires__" + _seat.split()[0].strip("`/."),
           standards.impl_team_hit(_seat))

# The scope gate itself: outside a published-surface scope these three are
# silent, so adding them cannot make an already-baselined corpus jump.
print("  -- the new rules do not fire outside a published scope --")
for _r in ("operator-quote", "internal-path-ref", "discipline-letter-ref"):
    p_case("silent_in_default_scope__" + _r.replace("-", "_"),
           not [f for f in standards.analyze(
               Path("EXTENSION-GADGET.md"),
               "the operator said L23 in `AGENTS.md`\n") if f.rule == _r])

# (15) A BASELINE FILE DESCRIBES THE RULES IT CAN ACTUALLY HOLD. `meta.rules`
#      was written from `BASELINE_RULES`, the eligibility UNION — correct for the
#      gating logic, wrong for the file: the default scope filters the three
#      published-only rules out before scoring (the block above pins that), so
#      the default baseline claimed accepted debt for rules it can never carry,
#      directly beneath a note reading "NORMATIVE specs only". Caught by running
#      the documented ratchet, which rewrote the field as a side effect.
print("  -- meta.rules describes the scope that wrote the file --")


def _meta_rules(published):
    """`meta.rules` as written under a given scope."""
    prev = standards.PUBLISHED_SURFACE_SCOPE
    standards.PUBLISHED_SURFACE_SCOPE = published
    try:
        return set(json.loads(
            standards.Baseline({}, {}, {}).to_json())["meta"]["rules"])
    finally:
        standards.PUBLISHED_SURFACE_SCOPE = prev


_only_pub = set(standards.PUBLISHED_LEAK_RULES) - set(standards.NARRATIVE_RULES)
p_case("default_scope_meta_omits_the_published_only_rules",
       not (_meta_rules(False) & _only_pub))
p_case("default_scope_meta_keeps_every_narrative_rule",
       set(standards.NARRATIVE_RULES) <= _meta_rules(False))
# The other direction, so the fix cannot degrade into "drop them everywhere":
# in a published scope all eight ARE eligible and all eight must be listed.
p_case("published_scope_meta_lists_the_full_union",
       _meta_rules(True) == set(standards.BASELINE_RULES))
# And the gating set itself is untouched — narrowing it would silently stop
# holding real debt, which is the failure this whole mechanism exists to refuse.
p_case("gating_eligibility_set_is_still_the_union",
       set(standards.BASELINE_RULES)
       == set(standards.NARRATIVE_RULES) | set(standards.PUBLISHED_LEAK_RULES))

# (16) THE DECLARATION IS THE SCOPE. `published-narrative` scored every `.md`
#      under `docs/` that was not on a hardcoded name list, so each NEW
#      undeclared root-level document arrived as a pile of false leaks — an
#      internal vision document opened at 25 errors against a file that
#      publishes nowhere. The config already stated the correct rule
#      (*"an undeclared file is out of a published-narrative scope by
#      construction"*) and implemented it as a list of the filenames that
#      existed the day it was written.
#
#      Asserted in BOTH directions, because the dangerous failure here is the
#      OTHER one: a scope that reads the keep-list wrongly (wrong base path,
#      unexpanded keep_tree) yields the empty set and reports a serene 0
#      errors over a surface it never opened.
print("\n  -- the publication declaration is the scope --")

import tempfile  # noqa: E402

with tempfile.TemporaryDirectory() as _td:
    _root = Path(_td)
    (_root / "docs" / "proposals").mkdir(parents=True)
    (_root / "CANONICAL-DOCS.toml").write_text(
        '[[keep_tree]]\npath = "docs/proposals"\n', encoding="utf-8")
    # declared, via a keep_tree -> must be scanned
    (_root / "docs" / "proposals" / "PROPOSAL-A.md").write_text("x\n",
                                                               encoding="utf-8")
    # undeclared, sitting at docs/ root -> must NOT be scanned
    (_root / "docs" / "VISION-INTERNAL.md").write_text("x\n", encoding="utf-8")

    _prev_scope = standards.PUBLISHED_SURFACE_SCOPE
    _prev_excl_d, _prev_excl_f = standards.EXCLUDE_DIRS, standards.EXCLUDE_FILES
    standards.PUBLISHED_SURFACE_SCOPE = True
    standards.EXCLUDE_DIRS, standards.EXCLUDE_FILES = set(), set()
    try:
        _seen = {p.name for p in standards.iter_specs(_root / "docs")}
    finally:
        standards.PUBLISHED_SURFACE_SCOPE = _prev_scope
        standards.EXCLUDE_DIRS, standards.EXCLUDE_FILES = _prev_excl_d, _prev_excl_f

p_case("a_keep_tree_member_is_in_scope", "PROPOSAL-A.md" in _seen)
p_case("an_undeclared_docs_root_file_is_not", "VISION-INTERNAL.md" not in _seen)
# The anti-vacuity guard: if the keep-list resolution broke, `_seen` would be
# empty and the assertion above would pass for the wrong reason.
p_case("the_declared_scope_is_not_empty", len(_seen) == 1)

# And with no scope flag, nothing is filtered — the default scope must not
# silently inherit a publication filter it never asked for.
with tempfile.TemporaryDirectory() as _td2:
    _r2 = Path(_td2)
    (_r2 / "docs").mkdir(parents=True)
    (_r2 / "CANONICAL-DOCS.toml").write_text("", encoding="utf-8")
    (_r2 / "docs" / "ANYTHING.md").write_text("x\n", encoding="utf-8")
    _prev_excl_d, _prev_excl_f = standards.EXCLUDE_DIRS, standards.EXCLUDE_FILES
    standards.EXCLUDE_DIRS, standards.EXCLUDE_FILES = set(), set()
    try:
        _seen2 = {p.name for p in standards.iter_specs(_r2 / "docs")}
    finally:
        standards.EXCLUDE_DIRS, standards.EXCLUDE_FILES = _prev_excl_d, _prev_excl_f
p_case("default_scope_applies_no_publication_filter", "ANYTHING.md" in _seen2)

# ---------------------------------------------------------------------------
# D14 — a proposal names the artifact it proposes.
#
# The rule exists because a reader could not classify a proposal's sentence
# title as an extension name, a process name or a document name, and asked which
# it was before asking what it said. **Two satisfying forms**, because a title
# that already names the artifact owes nothing — so the cases below assert the
# SILENCE as hard as the finding. An exemption nobody can audit is not an
# exemption, and a rule that fires on correct documents teaches people to skip
# the gate.
from pathlib import Path as _P  # noqa: E402

def _d14(name, body):
    """Score under the published-narrative scope, which is the only one that
    runs this rule — `analyze` drops the published-surface rules outright in the
    default scope, so a fixture that forgets the flag scores every case SILENT
    and the whole block passes vacuously. It did, on the first run of this file."""
    prev = standards.PUBLISHED_SURFACE_SCOPE
    standards.PUBLISHED_SURFACE_SCOPE = True
    try:
        return [f for f in standards.analyze(_P(name), body)
                if f.rule == "proposal-artifact-unnamed"]
    finally:
        standards.PUBLISHED_SURFACE_SCOPE = prev

_SENTENCE = "# PROPOSAL — keeping a copy current is one mechanism\n\n**Status:** DRAFT\n"

p_case("d14_fires_on_a_sentence_title_with_no_artifact",
       len(_d14("PROPOSAL-X.md", _SENTENCE)) == 1)

# Both header spellings are live in this corpus — specs write `**Name**:` and
# proposals write `**Name:**`. A matcher that knows only one reports a
# correctly-declared document as undeclared, which is this toolkit's own
# most-repeated defect (a matcher calibrated against the spelling the
# rule-writer expects rather than the corpus's actual vocabulary). Both are
# asserted; neither is assumed.
p_case("d14_silent_when_Proposes_uses_the_proposal_spelling",
       _d14("PROPOSAL-X.md",
            "# PROPOSAL — a sentence\n\n**Proposes:** `EXTENSION-CURRENT-COPY`\n") == [])
p_case("d14_silent_when_Proposes_uses_the_spec_spelling",
       _d14("PROPOSAL-X.md",
            "# PROPOSAL — a sentence\n\n**Proposes**: EXTENSION-CURRENT-COPY\n") == [])
p_case("d14_silent_when_the_title_carries_an_artifact_token",
       _d14("PROPOSAL-X.md", "# PROPOSAL — EXTENSION-RELAY completes the mode set\n") == [])
p_case("d14_silent_when_the_title_carries_a_backticked_identifier",
       _d14("PROPOSAL-X.md", "# PROPOSAL — `system/device`: host introspection\n") == [])

# An EMPTY field is not a declaration. Without this, `**Proposes:**` with
# nothing after it satisfies the rule and the gate certifies a blank.
p_case("d14_fires_on_an_empty_Proposes_field",
       len(_d14("PROPOSAL-X.md", "# PROPOSAL — a sentence\n\n**Proposes:**\n")) == 1)

# Scope: the rule is about PROPOSALS. A spec, a guide or an exploration with a
# sentence title owes nothing, and firing there would bury the signal in the
# scope that has to stay readable.
p_case("d14_does_not_fire_outside_proposals",
       _d14("EXPLORATION-SOMETHING.md", _SENTENCE) == [])
p_case("d14_does_not_fire_on_a_spec", _d14("EXTENSION-TREE.md", _SENTENCE) == [])

# The header region ends at the first `##`. A `Proposes:` line BELOW it is not a
# header field — the same region defect that scored a spec as declaring nothing
# because its declaration sat under sixty lines of version history, running the
# other way.
p_case("d14_ignores_a_Proposes_line_below_the_header_region",
       len(_d14("PROPOSAL-X.md",
                "# PROPOSAL — a sentence\n\n## Body\n\n**Proposes:** `EXTENSION-X`\n")) == 1)

# And it must actually be REACHABLE: a rule absent from the scope's rule set is
# a rule that never runs, however correct its logic.
p_case("d14_is_scored_by_the_published_narrative_scope",
       "proposal-artifact-unnamed" in standards.SCOPE_RULES["published-narrative"])
p_case("d14_gates_rather_than_warns",
       standards.RULES["proposal-artifact-unnamed"][0] == "error")

# ...and it MUST stay out of the default scope, where the corpus debt is
# baselined separately. A rule that leaks across scopes makes the other
# baseline jump, and the reflex fix for a jumping ratchet is to re-baseline —
# the one move the mechanism exists to refuse.
_prev_pss = standards.PUBLISHED_SURFACE_SCOPE
standards.PUBLISHED_SURFACE_SCOPE = False
try:
    _default_scope = [f for f in standards.analyze(_P("PROPOSAL-X.md"), _SENTENCE)
                      if f.rule == "proposal-artifact-unnamed"]
finally:
    standards.PUBLISHED_SURFACE_SCOPE = _prev_pss
p_case("d14_is_silent_in_the_default_scope", _default_scope == [])

if FAILURES:
    print(f"\n{len(FAILURES)} failure(s):")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
print(f"\n{len(PASSED)}/{len(PASSED)} invariants pass")
