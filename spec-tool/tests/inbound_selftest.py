#!/usr/bin/env python3
"""inbound self-test — builds a synthetic ecosystem and asserts the contract.

Fixtures rather than live counts, like `register_selftest`, so a real packet
landing in a sibling repo never makes this stale.

**Two invariants earn most of this file.**

1. **Citation is a PREFIX match.** A ledger cites `ROUTING-2026-08-20-e`; the
   file is `ROUTING-2026-08-20-e-core-go-the-fourth-pass-closes-...`. The first
   cut of this gate compared whole stems and reported **0 of 210 cited** — the
   identical defect `register` shipped twice and `ledger` once. Three tools in
   this toolkit have now made the same mistake, so it is asserted here.

2. **`unaddressed` is not `other`.** 27% of live packets carry no parseable
   `**To:**`. Folding them into "addressed elsewhere" would silently drop a
   quarter of the channel into a bucket labelled *not yours* when the truth is
   *unknown* — `could-not-look wearing a verdict's clothes`, which this toolkit
   has shipped three times on other analyzers.

Every assertion runs in BOTH directions: a packet that should be owed is owed,
AND one that should be discharged is discharged. A negative control proves the
gate can fire; only the positive one shows the pass condition is right.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import inbound  # noqa: E402

FAILURES = []


def ok(name, cond, extra=""):
    if cond:
        print("  ok   %s" % name)
    else:
        FAILURES.append(name)
        print("  FAIL %s %s" % (name, extra))


_CASE = [0]


def build(tmp: Path, ledger: str, seats: dict) -> Path:
    """seats: {repo_name: {packet_filename: body}}. Returns the peers dir.

    **A fresh tree per case, and that is not incidental.** A first version of
    this harness reused one directory, so every scenario inherited the previous
    one's packets and eleven assertions failed for a reason that had nothing to
    do with the tool. A fixture that accumulates is testing the wrong corpus.
    """
    _CASE[0] += 1
    peers = tmp / ("eco%d" % _CASE[0])
    us = peers / "entity-system-architecture" / "docs"
    us.mkdir(parents=True, exist_ok=True)
    (us / "COHORT-OPEN-ITEMS.md").write_text(ledger, encoding="utf-8")
    for repo, packets in seats.items():
        d = peers / repo / "docs" / "status"
        d.mkdir(parents=True, exist_ok=True)
        for fn, body in packets.items():
            (d / fn).write_text(body, encoding="utf-8")
    return peers


def run(tmp: Path, ledger: str, seats: dict):
    peers = build(tmp, ledger, seats)
    return inbound.scan(peers / "entity-system-architecture", peers)


TO_ARCH = "**From:** `entity-core-go`. **To:** `entity-system-architecture`.\n"
TO_ARCH_SHORT = "**To:** arch\n"
TO_OTHER = "**To:** `entity-core-rust`\n"
TO_OTHER_CC_US = "**To:** `entity-core-rust` (cc entity-system-architecture)\n"
NO_TO = "Some prose with no addressee field at all.\n"


def main() -> int:
    print("inbound self-test")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # ---- 1. the prefix-citation invariant, both directions ------------
        code, res = run(
            tmp,
            "| **X-1** | see `ROUTING-2026-08-20-e` | arch | OPEN |\n",
            {"entity-core-go": {
                "ROUTING-2026-08-20-e-the-fourth-pass-closes.md": TO_ARCH,
                "ROUTING-2026-08-21-f-something-else-entirely.md": TO_ARCH,
            }})
        owed = {Path(o["file"]).name for o in res["owed"]}
        ok("date+letter citation credits the full-title packet",
           res["cited"] == 1, res)
        ok("an uncited packet is still owed",
           owed == {"ROUTING-2026-08-21-f-something-else-entirely.md"}, owed)
        ok("gate fires on the owed one", code == inbound.VIOLATIONS)

        # ---- 2. a citation must not credit a longer sibling id ------------
        code, res = run(
            tmp,
            "cites `ROUTING-2026-08-20-e`\n",
            {"entity-core-go": {
                "ROUTING-2026-08-20-eb-a-different-packet.md": TO_ARCH,
            }})
        ok("`-e` does not credit `-eb` (separator required)",
           res["cited"] == 0 and len(res["owed"]) == 1, res)

        # ---- 3. a date-only mention is too coarse to credit ---------------
        code, res = run(
            tmp,
            "we looked at the packets from `ROUTING-2026-08-20` that week\n",
            {"entity-core-go": {
                "ROUTING-2026-08-20-e-the-fourth-pass.md": TO_ARCH,
            }})
        ok("a bare date credits nothing",
           res["cited"] == 0 and len(res["owed"]) == 1, res)

        # ---- 4. unaddressed is its own bucket, never `other` --------------
        code, res = run(
            tmp, "nothing cited\n",
            {"entity-core-go": {
                "ROUTING-2026-09-01-a-to-us.md": TO_ARCH,
                "ROUTING-2026-09-01-b-to-them.md": TO_OTHER,
                "ROUTING-2026-09-01-c-to-nobody.md": NO_TO,
            }})
        ok("addressed-elsewhere is excluded", res["addressed_elsewhere"] == 1)
        ok("unaddressed is reported separately, not as elsewhere",
           len(res["unaddressed"]) == 1, res["unaddressed"])
        ok("unaddressed is NOT counted as owed", len(res["owed"]) == 1, res)

        # ---- 5. cc is a lower obligation, counted apart -------------------
        code, res = run(
            tmp, "nothing cited\n",
            {"entity-core-go": {
                "ROUTING-2026-09-02-a-cc-only.md": TO_OTHER_CC_US,
            }})
        ok("a cc packet is not in `owed`", len(res["owed"]) == 0, res)
        ok("a cc packet is reported in cc_owed", len(res["cc_owed"]) == 1, res)
        ok("cc alone does not fire the gate", code == inbound.CLEAN)

        # ---- 6. the short aliases the ecosystem actually writes -----------
        code, res = run(
            tmp, "nothing cited\n",
            {"entity-core-go": {"ROUTING-2026-09-03-a-short-alias.md":
                                TO_ARCH_SHORT}})
        ok("`**To:** arch` is recognised as addressed to us",
           len(res["owed"]) == 1, res)

        # ---- 7. word-boundary: arch-tools must not satisfy `arch` ---------
        code, res = run(
            tmp, "nothing cited\n",
            {"entity-core-go": {"ROUTING-2026-09-03-b-other-repo.md":
                                "**To:** `entity-system-arch-tools`\n"}})
        ok("`entity-system-arch-tools` does not match the alias `arch`",
           res["addressed_elsewhere"] == 1 and not res["owed"], res)

        # ---- 8. brace expansion does not create a false match -------------
        code, res = run(
            tmp, "nothing cited\n",
            {"entity-core-go": {"ROUTING-2026-09-03-c-braces.md":
                                "**To:** `entity-core-{go,rust,py}`\n"}})
        ok("a brace list addressed elsewhere stays elsewhere",
           res["addressed_elsewhere"] == 1, res)

        # ---- 9. ambiguity is detected, and it is not silent ---------------
        code, res = run(
            tmp, "cites `ROUTING-2026-08-20-e`\n",
            {"entity-core-go": {"ROUTING-2026-08-20-e-one.md": TO_ARCH},
             "entity-core-rust": {"ROUTING-2026-08-20-e-two.md": TO_ARCH}})
        ok("one citation reaching two packets is reported",
           len(res["ambiguous_citations"]) == 1
           and len(res["ambiguous_citations"][0]["matches"]) == 2, res)

        # ---- 9a. all three inline cc spellings are cc, never to -----------
        for label, line in (
            ("paren",
             "**To:** `entity-core-go` (cc `entity-system-architecture`)\n"),
            ("em-dash",
             "**To:** `entity-core-go` — cc `entity-system-architecture`\n"),
            ("comma",
             "**To:** `entity-core-go` (`ext/network`), "
             "cc `entity-system-architecture` (§4.1)\n"),
        ):
            code, res = run(tmp, "no rows\n",
                            {"entity-core-go": {
                                "ROUTING-2026-09-09-x-%s.md" % label: line}})
            ok("inline cc (%s) is cc, never to" % label,
               not res["owed"] and len(res["cc_owed"]) == 1, res)

        # ---- 10. could-not-look is not a pass ----------------------------
        peers = build(tmp, "x\n", {"entity-core-go": {}})
        code, res = inbound.scan(peers / "entity-system-architecture", peers)
        ok("no packets anywhere is could-not-look, not clean",
           code == inbound.CANNOT_LOOK and "error" in res, res)

        peers2 = build(tmp, "x\n", {"entity-core-go": {
            "ROUTING-2026-09-01-a.md": TO_ARCH}})
        unknown = peers2 / "some-unknown-repo"
        (unknown / "docs").mkdir(parents=True, exist_ok=True)
        code, res = inbound.scan(unknown, peers2)
        ok("an unknown corpus name is could-not-look, not clean",
           code == inbound.CANNOT_LOOK, res)

        # ---- 11. a fully-reconciled channel is clean ---------------------
        code, res = run(
            tmp,
            "rows citing `ROUTING-2026-09-01-a-to-us` and "
            "`ROUTING-2026-09-01-b-also-us`\n",
            {"entity-core-go": {
                "ROUTING-2026-09-01-a-to-us.md": TO_ARCH,
                "ROUTING-2026-09-01-b-also-us.md": TO_ARCH,
                "ROUTING-2026-09-01-c-not-ours.md": TO_OTHER,
            }})
        ok("everything cited => clean, exit 0",
           code == inbound.CLEAN and not res["owed"] and res["cited"] == 2,
           res)

        # ---- an AMBIGUOUS citation discharges NOTHING --------------------
        # A `date-letter` id is unique to one repository on one day, which is
        # not unique. Until 2026-09-11 a bare one credited EVERY packet it
        # reached, and the run printed `-> N packets` in its own summary while
        # doing it: the ambiguity was reported as a note and consumed as a
        # credit. Live at the fix, SEVEN packets were discharged this way —
        # including one addressed to arch BY NAME by `entity-core-keystone`.
        # The instance that surfaced it was found by hand, not by the gate.
        TWO_C = {"entity-core-go": {
                     "ROUTING-2026-09-10-c-the-design-is-signed-off.md": TO_ARCH},
                 "entity-workbench-go": {
                     "ROUTING-2026-09-10-c-the-file-sync-pattern.md": TO_ARCH}}

        code, res = run(
            tmp, "| **X-1** | see `ROUTING-2026-09-10-c` | arch | OPEN |\n",
            TWO_C)
        amb = {Path(a["file"]).name for a in res["ambiguous_credit"]}
        ok("an ambiguous citation credits NEITHER packet",
           res["cited"] == 0, res["cited"])
        ok("both land in the ambiguous bucket",
           amb == {"ROUTING-2026-09-10-c-the-design-is-signed-off.md",
                   "ROUTING-2026-09-10-c-the-file-sync-pattern.md"}, amb)
        ok("an ambiguous packet is not silently OWED either",
           res["owed"] == [], res["owed"])
        ok("the collision is still reported as a naming finding",
           len(res["ambiguous_citations"]) == 1, res["ambiguous_citations"])

        # The other direction, and it is the half that matters: cite ONE by
        # full stem. That one is cited; its collided neighbour stays UNKNOWN
        # rather than riding on it.
        code, res = run(
            tmp,
            "see `ROUTING-2026-09-10-c-the-design-is-signed-off` and "
            "`ROUTING-2026-09-10-c`\n", TWO_C)
        amb = {Path(a["file"]).name for a in res["ambiguous_credit"]}
        ok("a FULL-STEM citation still credits its own packet",
           res["cited"] == 1, res["cited"])
        ok("its collided neighbour does not ride on it",
           amb == {"ROUTING-2026-09-10-c-the-file-sync-pattern.md"}, amb)

        # Negative control: an unambiguous ledger behaves exactly as before,
        # so the new bucket is not swallowing the ordinary case.
        code, res = run(
            tmp, "see `ROUTING-2026-09-10-c-the-design`\n",
            {"entity-core-go": {
                "ROUTING-2026-09-10-c-the-design-is-signed-off.md": TO_ARCH},
             "entity-workbench-go": {
                "ROUTING-2026-09-11-q-unrelated.md": TO_ARCH}})
        ok("an unambiguous ledger still credits normally",
           res["cited"] == 1 and res["ambiguous_credit"] == [], res)
        ok("and the genuinely uncited packet is still owed",
           {Path(o["file"]).name for o in res["owed"]}
           == {"ROUTING-2026-09-11-q-unrelated.md"}, res["owed"])

        # ---- clone collapse, and it is validated in BOTH directions ------
        # The defect: this scope is a directory of directories and several of
        # them are working clones of one repository at different tips. Measured
        # 2026-09-09, four clones of `entity-browser-rust` held 114 files, every
        # one byte-identical to a packet already counted, and the published owed
        # figure was 194 where the truth is 135.
        body_a = TO_ARCH + "the locator gap is wider than signaling\n"
        body_b = TO_ARCH + "a different finding entirely\n"
        code, res = run(
            tmp, "no citations here",
            {"entity-browser-rust": {
                "ROUTING-2026-08-20-e-arch-locator.md": body_a,
                "ROUTING-2026-08-20-g-arch-other.md": body_b,
                "ROUTING-2026-08-21-a-arch-third.md": TO_ARCH + "third\n"},
             "br-curate": {
                "ROUTING-2026-08-20-e-arch-locator.md": body_a,
                "ROUTING-2026-08-20-g-arch-other.md": body_b},
             "entity-browser-rust-apps": {
                "ROUTING-2026-08-20-e-arch-locator.md": body_a}})
        ok("byte-identical copies across clones collapse to one obligation",
           len(res["owed"]) == 3 and len(res["collapsed_clones"]) == 3, res)
        ok("the obligation attributes to the FULLEST tree, not alphabetically",
           res["by_seat"] == {"entity-browser-rust": 3}, res["by_seat"])
        ok("the collapsed copies name their seats",
           res["clone_seats"] == ["br-curate", "entity-browser-rust-apps"],
           res["clone_seats"])

        # The other direction, and it is the one that matters more: two seats
        # that genuinely file the same-named packet with DIFFERENT content are
        # two obligations, and collapsing them would be a silent drop.
        code, res = run(
            tmp, "no citations here",
            {"entity-core-go": {
                "ROUTING-2026-08-20-e-arch-thing.md": TO_ARCH + "go's\n"},
             "entity-core-rust": {
                "ROUTING-2026-08-20-e-arch-thing.md": TO_ARCH + "rust's\n"}})
        ok("same name, different bytes => two obligations, nothing collapsed",
           len(res["owed"]) == 2 and not res["collapsed_clones"], res)

        # And a clone copy must not be able to satisfy a ledger citation on its
        # own — the citation is matched against the canonical copy's stem, so
        # crediting is unchanged by the collapse.
        code, res = run(
            tmp, "we read ROUTING-2026-08-20-e-arch-locator today",
            {"entity-browser-rust": {
                "ROUTING-2026-08-20-e-arch-locator.md": body_a},
             "br-curate": {
                "ROUTING-2026-08-20-e-arch-locator.md": body_a}})
        ok("a cited packet is still cited after collapse, and counted once",
           res["cited"] == 1 and not res["owed"]
           and len(res["collapsed_clones"]) == 1, res)

    # -- a stem with an internal dot is citable ----------------------------
    # `ROUTING-2026-08-04-s10.3-seam-...` names a spec SECTION in its slug. The
    # citation regex broke the segment at the dot, matched `...-08-04-s10`, and
    # the leading-clause test then failed on `.3-seam` — so that packet was
    # UNCITABLE by any spelling and reported `owed` however correctly the ledger
    # named it. Measured on the live trees, not hypothetical.
    dotted = "ROUTING-2026-08-04-s10.3-seam-carries-the-reason-browser-rust-stake"
    ok("a citation regex reaches a stem with an internal dot",
       inbound.CITATION.findall("`%s`" % dotted) == [dotted],
       inbound.CITATION.findall(dotted))
    ok("...and the leading-clause test then credits it",
       inbound.cites(dotted, [dotted]) == dotted)

    # The mirror: the trailing character must stay alphanumeric, or a citation
    # ending a sentence swallows the full stop into the identifier and stops
    # matching the file.
    ok("a citation ending a sentence does not swallow the full stop",
       inbound.CITATION.findall("see ROUTING-2026-09-06-b-arch-thing.")
       == ["ROUTING-2026-09-06-b-arch-thing"])
    ok("the -b / -bb distinction still holds",
       inbound.CITATION.findall("ROUTING-2026-09-06-b and ROUTING-2026-09-06-bb")
       == ["ROUTING-2026-09-06-b", "ROUTING-2026-09-06-bb"])
    # The mirror of the dot fix, introduced BY the dot fix: allowing internal
    # dots made `.md` a legal continuation, so a ledger citing the FILENAME
    # produced `...-federation.md`, which reaches no packet. Caught on the same
    # live run that the dot fix was written for.
    ok("a ledger citing the FILENAME still credits the packet",
       inbound.ledger_citations("see `ROUTING-2026-09-09-a-arch-the-offer.md`")
       == ["ROUTING-2026-09-09-a-arch-the-offer"],
       inbound.ledger_citations("see `ROUTING-2026-09-09-a-arch-the-offer.md`"))

    ok("a bare leading clause still does not credit a longer sibling",
       inbound.cites("ROUTING-2026-09-06-bb-x", ["ROUTING-2026-09-06-b"]) is None)

    # ---- the alias table covers the ECOSYSTEM, not just the arch seat -----
    # `AGENTS-STANDARD.md` tells every seat to point this gate at its own tree.
    # Until 2026-09-10 the table held three repos, so every other seat got a
    # COULD-NOT-LOOK — found by running it from a cohort tree to check whether a
    # relay addressed to that seat was visible. It was not, and the packet was
    # fine.
    for seat in ("entity-core-go", "entity-core-rust", "entity-core-py",
                 "entity-core-keystone", "entity-core-formalization",
                 "entity-browser-rust", "entity-workbench-go",
                 "entity-system-generator"):
        ok("%s has addressee aliases" % seat, seat in inbound.ALIASES)

    RUST = inbound.ALIASES["entity-core-rust"]
    PY = inbound.ALIASES["entity-core-py"]
    BROWSER = inbound.ALIASES["entity-browser-rust"]

    # Both directions on the same packet: the addressee is credited AND the
    # look-alike seat is not.
    RELAY = ("**From:** `entity-core-go`. **To:** `entity-core-rust`, "
             "`entity-core-py`. **cc:** arch, `entity-core-keystone`.\n")
    ok("a relay names its addressee", inbound.classify(RELAY, RUST) == "to")
    ok("the same relay is not the look-alike seat's",
       inbound.classify(RELAY, BROWSER) == "other")

    # The substring guard, which is what makes bare short forms safe at all:
    # `rust` must not fire inside `entity-browser-rust`, and vice versa.
    ok("`rust` does not fire inside `entity-browser-rust`",
       inbound.classify("**To:** `entity-browser-rust`\n", RUST) == "other")
    ok("`browser-rust` does not fire inside a core-rust packet",
       inbound.classify("**To:** `entity-core-rust`\n", BROWSER) == "other")

    # The bare-nickname form the cohort actually writes in a cc list.
    BARE_CC = ("**To:** `entity-system-architecture`\n"
               "**cc:** `entity-core-keystone`, rust, py\n")
    ok("a bare `py` in a cc list is a cc, not silence",
       inbound.classify(BARE_CC, PY) == "cc")
    ok("a bare `rust` in a cc list is a cc, not a to",
       inbound.classify(BARE_CC, RUST) == "cc")

    print()
    if FAILURES:
        print("%d FAILURE(S): %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("inbound self-test: all assertions passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
