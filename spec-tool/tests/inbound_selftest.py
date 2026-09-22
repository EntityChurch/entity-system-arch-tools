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


def build_raw(tmp: Path, own_files: dict, seats: dict) -> Path:
    """Like `build`, but the own-tree files are given explicitly.

    `build` always writes `docs/COHORT-OPEN-ITEMS.md`, which makes the
    hardcoded-ledger defect untestable through it — the fixture supplied the
    very file whose absence WAS the bug. Keys are corpus-relative paths.
    """
    _CASE[0] += 1
    peers = tmp / ("eco%d" % _CASE[0])
    us = peers / "entity-system-architecture"
    us.mkdir(parents=True, exist_ok=True)
    for rel, body in own_files.items():
        f = us / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body, encoding="utf-8")
    for repo, files in seats.items():
        d = peers / repo / "docs" / "status"
        d.mkdir(parents=True, exist_ok=True)
        for fn, body in files.items():
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

        # ---- 7. word-boundary: a long name must not satisfy a short alias --
        #
        # ⚠ **This case used `entity-system-arch-tools` against the alias
        # `arch` until 2026-09-17, and the SEAT model made that example
        # invalid rather than wrong** — arch-tools is now genuinely one of this
        # seat's repositories, so a packet addressed to it IS ours, by its own
        # name and not by a substring of `arch`.
        #
        # **The guard it was protecting is untouched and must never regress**,
        # so it is asserted twice: here through `scan` against a genuine third
        # party whose name contains a short alias, and directly on `names_us`
        # below for the original pair. Re-pointing a case is legitimate;
        # deleting one because the fixture moved is how a real defect comes
        # back.
        ok("the alias `arch` still does not fire inside `arch-tools`",
           not inbound.names_us("entity-system-arch-tools", ("arch",)))
        ok("the alias `rust` still does not fire inside `browser-rust`",
           not inbound.names_us("entity-browser-rust", ("rust",)))

        code, res = run(
            tmp, "nothing cited\n",
            {"entity-core-go": {"ROUTING-2026-09-03-b-other-repo.md":
                                "**To:** `entity-browser-rust`\n"}})
        ok("a third party whose name contains a short alias is not ours",
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


        # ---- 9. THE HARDCODED LEDGER, both directions --------------------
        # `LEDGERS` was a one-element tuple, so this gate answered
        # COULD-NOT-LOOK for every seat that does not keep a file at that exact
        # path — i.e. every seat but one, while the ecosystem standard tells
        # all of them to run it. Reported with the file:line by the seat it
        # broke for, who correctly declined to widen it themselves.
        PKT = {"entity-core-go": {
            "ROUTING-2026-09-01-a-a-real-packet.md": TO_ARCH}}

        # (a) NEGATIVE CONTROL — no reconciled view of any kind.
        pr = build_raw(tmp, {"README.md": "nothing here\n"}, PKT)
        code, res = inbound.scan(pr / "entity-system-architecture", pr)
        ok("no ledger and no tracker is COULD-NOT-LOOK",
           code == inbound.CANNOT_LOOK and "error" in res, res)
        ok("the could-not-look names --ledger as the way out",
           "--ledger" in res.get("error", ""), res.get("error"))

        # (b) a seat keeping ONLY per-counterpart trackers HAS a ledger.
        pr = build_raw(
            tmp,
            {"docs/status/TRACKER-entity-core-go.md":
                "| **A-1** | see `ROUTING-2026-09-01-a` | OPEN |\n"},
            PKT)
        code, res = inbound.scan(pr / "entity-system-architecture", pr)
        ok("own-tree TRACKER-*.md counts as a reconciled view",
           code != inbound.CANNOT_LOOK, res)
        ok("a citation inside an own tracker discharges the packet",
           res.get("cited") == 1 and not res.get("owed"), res)
        ok("the tracker is reported among the surfaces actually read",
           any("TRACKER-entity-core-go.md" in x for x in res["ledgers"]),
           res.get("ledgers"))

        # (c) ...and it still FIRES when that tracker cites nothing.
        pr = build_raw(
            tmp,
            {"docs/status/TRACKER-entity-core-go.md": "nothing cited here\n"},
            PKT)
        code, res = inbound.scan(pr / "entity-system-architecture", pr)
        ok("an own tracker citing nothing leaves the packet owed",
           code == inbound.VIOLATIONS and len(res["owed"]) == 1, res)

        # (d) --ledger wins OUTRIGHT; the default is not silently appended.
        pr = build_raw(
            tmp,
            {"docs/COHORT-OPEN-ITEMS.md": "cites `ROUTING-2026-09-01-a`\n",
             "docs/other/MY-LEDGER.md": "cites nothing\n"},
            PKT)
        code, res = inbound.scan(pr / "entity-system-architecture", pr,
                                 ["docs/other/MY-LEDGER.md"])
        ok("--ledger overrides rather than appends",
           res["ledgers"] == ["docs/other/MY-LEDGER.md"], res.get("ledgers"))
        ok("so a citation in the DEFAULT file no longer credits",
           code == inbound.VIOLATIONS and len(res["owed"]) == 1, res)
        ok("ledger_default_used records which mode ran",
           res.get("ledger_default_used") is False, res)

        # (e) THE SAFETY DIRECTION: trackers STAND IN for a missing ledger,
        # they never SUPPLEMENT a present one. Widening what counts as a
        # discharge is the dangerous direction for an inbox gate.
        pr = build_raw(
            tmp,
            {"docs/COHORT-OPEN-ITEMS.md": "cites nothing\n",
             "docs/status/TRACKER-entity-core-go.md":
                 "cites `ROUTING-2026-09-01-a`\n"},
            PKT)
        code, res = inbound.scan(pr / "entity-system-architecture", pr)
        ok("an own tracker does NOT supplement a ledger that exists",
           res["ledgers"] == ["docs/COHORT-OPEN-ITEMS.md"], res.get("ledgers"))
        ok("so the packet stays owed rather than being credited by it",
           code == inbound.VIOLATIONS and len(res["owed"]) == 1, res)

        # ---- 10. A PEER TRACKER IS A SURFACE, NEVER A DISCHARGE ----------
        # Two application seats recovered unread packets by reconciling against
        # a counterpart's tracker, one of them in about two minutes. The glob
        # is `ROUTING-*`, so the surface that actually worked was invisible to
        # every run this gate had ever done.
        pr = build_raw(
            tmp,
            {"docs/COHORT-OPEN-ITEMS.md": "nothing cited\n"},
            {"entity-core-go": {
                "ROUTING-2026-09-01-a-a-real-packet.md": TO_ARCH,
                "TRACKER-entity-system-architecture.md": "what we carry\n",
                "TRACKER-entity-core-rust.md": "not about us\n",
            }})
        code, res = inbound.scan(pr / "entity-system-architecture", pr)
        names = {Path(t["file"]).name for t in res["peer_trackers"]}
        ok("a peer TRACKER naming us is reported",
           names == {"TRACKER-entity-system-architecture.md"}, names)
        ok("a peer TRACKER naming someone else is NOT reported",
           "TRACKER-entity-core-rust.md" not in names, names)
        ok("the tracker's seat is attributed",
           res["peer_trackers"][0]["seat"] == "entity-core-go",
           res["peer_trackers"])
        # THE LOAD-BEARING NEGATIVE: an index must not discharge a delivery.
        ok("a peer tracker does NOT discharge the packet beside it",
           code == inbound.VIOLATIONS and len(res["owed"]) == 1, res)
        ok("and it is not folded into the packet count",
           res["scanned"] == 1, res["scanned"])

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

    # ---- the RECENCY WINDOW -------------------------------------------
    #
    # The load-bearing assertion is the third one. `--since` filters the
    # REPORT, and the obvious implementation filters the SCAN — which would
    # reintroduce, one feature later, the exact defect this gate shipped in
    # 2026-09-11: a `date-letter` token reaching several packets discharging
    # all of them. Filter first and the out-of-window twin disappears, the
    # token looks unique, and the in-window packet is silently credited.
    ok("`7d` resolves to an absolute date",
       len(inbound.resolve_since("7d")) == 10)
    ok("an ISO date passes through",
       inbound.resolve_since("2026-09-10") == "2026-09-10")
    try:
        inbound.resolve_since("last tuesday")
        ok("a garbage window is rejected", False)
    except ValueError:
        ok("a garbage window is rejected", True)

    ok("a packet is dated from its own id",
       inbound.packet_date("ROUTING-2026-09-16-h-arch-thing.md")
       == "2026-09-16")
    ok("a packet with no date in its name is UNKNOWN, not old",
       inbound.packet_date("ROUTING-arch-no-date.md") is None)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        SEATS = {"entity-core-go": {
            "ROUTING-2026-09-16-a-arch-recent.md": TO_ARCH,
            "ROUTING-2026-08-01-a-arch-ancient.md": TO_ARCH,
            "ROUTING-arch-undated.md": TO_ARCH,
        }}
        peers = build(tmp, "nothing is cited here\n", SEATS)
        root = peers / "entity-system-architecture"

        code, res = inbound.scan(root, peers)
        ok("without a window every packet is owed", len(res["owed"]) == 3,
           res["owed"])

        code, res = inbound.scan(root, peers, None, "2026-09-10")
        stems = sorted(r["stem"] for r in res["owed"])
        ok("the window drops the older packet",
           not any("ancient" in s for s in stems), stems)
        ok("the window keeps the recent one",
           any("recent" in s for s in stems), stems)
        ok("an UNDATED packet stays in the window — unknown is not old",
           any("undated" in s for s in stems), stems)
        ok("what the window excluded is counted, not dropped",
           res["excluded_by_window"]["owed"] == 1, res["excluded_by_window"])
        ok("the window is named in the result so a run is quotable",
           res["since"] == "2026-09-10")

        # THE NEGATIVE CONTROL. One ledger row cites `ROUTING-2026-09-10-c`.
        # Two packets in different repos carry that id — one inside the
        # window, one outside. The citation resolves to neither, and the
        # window must not make it resolve to the survivor.
        AMBIG = {
            "entity-core-go": {
                "ROUTING-2026-09-10-c-arch-one.md": TO_ARCH},
            "entity-workbench-go": {
                "ROUTING-2026-09-10-c-arch-two.md": TO_ARCH,
                "ROUTING-2026-09-16-z-arch-filler.md": TO_ARCH},
        }
        peers = build(tmp, "we cite ROUTING-2026-09-10-c and nothing else\n",
                      AMBIG)
        root = peers / "entity-system-architecture"
        code, res = inbound.scan(root, peers, None, "2026-09-16")
        ok("an ambiguous citation stays ambiguous inside a window",
           res["cited"] == 0, res["cited"])
        ok("the out-of-window twin still blocks the credit",
           len(res["ambiguous_citations"]) == 1, res["ambiguous_citations"])

    # ---- NAME-ADDRESSED DOCUMENTS OUTSIDE `docs/status` ----------------
    #
    # Measured 2026-09-17: `entity-core-keystone` files `HANDOFF-TO-ARCH-*`
    # into `research/stewardship/`, and their own tracker cites those files
    # as the Packet column for 14 of their 18 open asks against arch. Every
    # one was invisible to this gate — wrong directory AND wrong filename,
    # either alone sufficient. `entity-core-go` files four more under
    # `docs/validation/reports/`.
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        peers = build_raw(
            tmp,
            # The ROUTING filler is cited too, so the ONLY thing that could
            # move the exit code is the new class — which is the assertion.
            {"docs/COHORT-OPEN-ITEMS.md":
                 "we cite HANDOFF-TO-ARCH-2026-09-08-seen and "
                 "ROUTING-2026-09-16-a-arch-filler\n"},
            {"entity-core-keystone": {
                "ROUTING-2026-09-16-a-arch-filler.md": TO_ARCH}})
        ks = peers / "entity-core-keystone"
        deep = ks / "research" / "stewardship"
        deep.mkdir(parents=True)
        (deep / "HANDOFF-TO-ARCH-2026-09-08-seen.md").write_text("x")
        (deep / "HANDOFF-TO-ARCH-2026-09-09-unseen.md").write_text("x")
        # A slug that merely MENTIONS us is not an addressee. The signal is
        # `to-<alias>`, with a separator in front of it.
        (deep / "NOTES-2026-09-09-thoughts-on-arch-and-others.md").write_text("x")
        # Build output holds byte-copies of real documents; counting those is
        # the clone defect arriving by a different road.
        staging = ks / ".publish-staging" / "buildset-abc"
        staging.mkdir(parents=True)
        (staging / "HANDOFF-TO-ARCH-2026-09-09-unseen.md").write_text("x")

        root = peers / "entity-system-architecture"
        code, res = inbound.scan(root, peers)
        stems = sorted(r["stem"] for r in res["name_addressed"])
        ok("a HANDOFF-TO-US outside docs/status is found",
           stems == ["HANDOFF-TO-ARCH-2026-09-08-seen",
                     "HANDOFF-TO-ARCH-2026-09-09-unseen"], stems)
        ok("a slug that merely mentions the alias is not an addressee",
           not any("NOTES" in s for s in stems), stems)
        ok("build staging is pruned, not counted",
           len(res["name_addressed"]) == 2, res["name_addressed"])
        by_stem = {r["stem"]: r for r in res["name_addressed"]}
        ok("one cited by full stem is credited",
           by_stem["HANDOFF-TO-ARCH-2026-09-08-seen"]["cited"])
        ok("...and the uncited one is not",
           not by_stem["HANDOFF-TO-ARCH-2026-09-09-unseen"]["cited"])
        ok("a name-addressed document is dated from its filename",
           by_stem["HANDOFF-TO-ARCH-2026-09-09-unseen"]["date"]
           == "2026-09-09")
        ok("the seat is the REPO, not the first directory under it",
           {r["seat"] for r in res["name_addressed"]}
           == {"entity-core-keystone"},
           {r["seat"] for r in res["name_addressed"]})
        ok("this class does not gate on introduction",
           code == inbound.CLEAN, code)

        # A `ROUTING-…-to-arch-…` is the overwhelmingly common spelling. It
        # is already counted as a packet; counting it again here would make
        # one document two obligations and roughly double the estate.
        ok("a ROUTING packet is not counted a second time",
           not any(s.startswith("ROUTING") for s in stems), stems)

    ok("a deep path attributes to the repo, not to `docs`",
       inbound.seat_of(Path("/e/entity-core-go/docs/validation/reports/x.md"),
                       Path("/e")) == "entity-core-go")
    ok("...and without a peer root the old rule still applies",
       inbound.seat_of(Path("/e/entity-core-go/docs/status/x.md"))
       == "entity-core-go")

    # ---- TRACKER RECIPROCITY -------------------------------------------
    #
    # `entity-core-keystone`'s ask, 2026-09-16, which they had taken from
    # `entity-system-conformance` against themselves first: twelve asks that
    # never arrived because the receiving seat kept no tracker for the
    # sending one. Both directions, because a check that only ever reports
    # a gap cannot show that the pass condition is right.
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        peers = build_raw(
            tmp,
            {"docs/COHORT-OPEN-ITEMS.md":
                 # BOTH packets are cited, so the only thing left that could
                 # move the exit code is the missing tracker. That is the
                 # point of the assertion at the end of this block.
                 "rows for ROUTING-2026-09-16-a-arch-x and "
                 "ROUTING-2026-09-16-b-arch-y\n",
             "docs/status/TRACKER-entity-core-go.md": "we track go\n",
             # A tracker for a SUBJECT, not a seat. It must not be read as
             # reciprocity with a repository that does not exist.
             "docs/status/TRACKER-THE-EXCHANGE-ARC.md": "a subject\n"},
            {"entity-core-go": {
                "ROUTING-2026-09-16-a-arch-x.md": TO_ARCH,
                "TRACKER-entity-system-architecture.md": "go tracks us\n"},
             "entity-core-keystone": {
                 "ROUTING-2026-09-16-b-arch-y.md": TO_ARCH,
                 "TRACKER-entity-system-architecture.md": "ks tracks us\n"}})
        root = peers / "entity-system-architecture"
        code, res = inbound.scan(root, peers)
        rec = res["tracker_reciprocity"]
        ok("a seat aiming a tracker at us with no counterpart is named",
           rec["not_reciprocated"] == ["entity-core-keystone"],
           rec["not_reciprocated"])
        ok("a seat we DO keep one for is not named",
           "entity-core-go" not in rec["not_reciprocated"])
        ok("a tracker naming a subject is not counted as a seat",
           rec["we_keep_for_them"] == ["entity-core-go"],
           rec["we_keep_for_them"])
        ok("an unreciprocated tracker is REPORTED and never gates",
           code == inbound.CLEAN and not res["owed"]
           and rec["not_reciprocated"], (code, res["owed"]))

    # ------------------------------------------------------------------
    # A SEAT IS NOT A REPOSITORY `[2026-09-17]`
    #
    # Replayed against the incident that motivated it, in BOTH directions —
    # the standing rule for a new or widened gate here, and the one that has
    # caught three defects in `expiry` and two in `deps`.
    #
    # The incident: arch owns three trees and `self_name = root.name` graded
    # one. A packet addressed to `entity-core-protocol` scored
    # `addressed-elsewhere` — indistinguishable in every published number from
    # mail for another seat. Live, that hid two owed packets and a standing
    # nine-ask tracker.
    # ------------------------------------------------------------------
    TO_PROTOCOL = "**To:** `entity-core-protocol`\n"
    TO_TOOLS = "**To:** `entity-system-arch-tools`\n"

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # --- DIRECTION 1: it now FIRES on what it used to miss ---
        code, res = run(tmp, "No citations here.\n", {
            "entity-core-formalization": {
                "ROUTING-2026-09-16-f-entity-core-protocol-n5.md": TO_PROTOCOL,
            },
        })
        ok("a packet addressed to a SECOND repo of this seat is owed",
           code == inbound.VIOLATIONS and len(res["owed"]) == 1, res["owed"])
        ok("the founding incident is a REGRESSION test, not a story",
           res["addressed_to_us"] == 1 and res["addressed_elsewhere"] == 0,
           (res["addressed_to_us"], res["addressed_elsewhere"]))

        # --- DIRECTION 2: it does NOT fire on a genuine third party ---
        # The dangerous direction for a widening: pulling somebody else's mail
        # into our inbox. `entity-core-rust` is not us and never becomes us.
        code, res = run(tmp, "No citations here.\n", {
            "entity-core-go": {"ROUTING-2026-09-16-a-rust.md": TO_OTHER},
        })
        ok("a third party's packet is still not ours",
           code == inbound.CLEAN and res["addressed_elsewhere"] == 1,
           (code, res["addressed_elsewhere"]))

        # --- the breakdown is the falsifiable half of the count ---
        code, res = run(tmp, "No citations here.\n", {
            "entity-core-formalization": {
                "ROUTING-2026-09-16-e-entity-core-protocol-a.md": TO_PROTOCOL,
                "ROUTING-2026-09-16-f-entity-core-protocol-b.md": TO_PROTOCOL,
            },
            "entity-core-go": {
                "ROUTING-2026-09-16-c-arch.md": TO_ARCH,
                "ROUTING-2026-09-16-d-tools.md": TO_TOOLS,
            },
        })
        ok("addressed-here breaks down by which repo was named",
           res["addressed_by_repo"] == {"entity-core-protocol": 2,
                                        "entity-system-architecture": 1,
                                        "entity-system-arch-tools": 1},
           res["addressed_by_repo"])
        ok("with no overlap, attribution sums to the total",
           sum(res["addressed_by_repo"].values()) == res["addressed_to_us"]
           and res["addressed_multi_named"] == 0,
           (res["addressed_by_repo"], res["addressed_to_us"]))

        # ⚠ **The assertion above passed on a fixture with no multi-match
        # packet, and live it was 316 attributions over 308 packets.** A sum
        # rule asserted only where it holds is not asserted. So: a packet
        # naming TWO of our repos is ONE obligation attributed twice, and the
        # overlap must be COUNTED rather than silently making the table wrong.
        code, res = run(tmp, "No citations here.\n", {
            "entity-core-go": {
                "ROUTING-2026-09-16-m-both.md":
                    "**To:** `entity-system-architecture`, "
                    "`entity-core-protocol`\n",
            },
        })
        ok("a packet naming two of our repos is ONE owed obligation",
           len(res["owed"]) == 1, res["owed"])
        ok("...attributed to both, and the overlap is counted not hidden",
           res["addressed_by_repo"] == {"entity-system-architecture": 1,
                                        "entity-core-protocol": 1}
           and res["addressed_multi_named"] == 1,
           (res["addressed_by_repo"], res["addressed_multi_named"]))

        # A packet that only CCs us is keyed `(cc)` — not `unattributed`.
        # The first cut published `unattributed 30` for thirty packets whose
        # addressee parsed perfectly and simply was not us.
        code, res = run(tmp, "Rowed: `ROUTING-2026-09-16-n-cc`.\n", {
            "entity-core-go": {"ROUTING-2026-09-16-n-cc.md":
                               TO_OTHER_CC_US},
        })
        ok("a cc-only packet is attributed `(cc)`, never to a repo",
           res["addressed_by_repo"] == {"(cc)": 1},
           res["addressed_by_repo"])

        # A citation still discharges, whichever of our repos was addressed —
        # one seat, one ledger, and the ledger is in the OTHER repository.
        code, res = run(
            tmp,
            "Rowed: `ROUTING-2026-09-16-f-entity-core-protocol-n5`.\n",
            {"entity-core-formalization": {
                "ROUTING-2026-09-16-f-entity-core-protocol-n5.md": TO_PROTOCOL,
            }})
        ok("one ledger discharges mail to any repo of the seat",
           code == inbound.CLEAN and res["cited"] == 1, res)

        # --- running from the OTHER member resolves the same channel ---
        # Symmetry is the property that makes the fix a seat model rather than
        # a special case: `--root ../entity-core-protocol` must grade the same
        # mail against the same ledger, which lives one directory over.
        peers = build(tmp, "No citations here.\n", {
            "entity-core-formalization": {
                "ROUTING-2026-09-16-f-entity-core-protocol-n5.md": TO_PROTOCOL,
            },
        })
        (peers / "entity-core-protocol" / "docs" / "status").mkdir(
            parents=True, exist_ok=True)
        code, res = inbound.scan(peers / "entity-core-protocol", peers)
        ok("running from a seat member with NO ledger is not could-not-look",
           code != inbound.CANNOT_LOOK, res.get("error"))
        ok("it finds the seat's ledger in the sibling repo",
           res.get("ledgers") == ["docs/COHORT-OPEN-ITEMS.md"],
           res.get("ledgers"))
        ok("and it reports the same owed packet",
           len(res["owed"]) == 1, res["owed"])

        # --- our own repos are not scanned as peers ---
        # Otherwise arch's own OUTBOUND packets, sitting in `entity-core-
        # protocol/docs/status/`, would be read as inbound mail to ourselves.
        peers = build(tmp, "No citations here.\n", {
            "entity-core-go": {"ROUTING-2026-09-16-y.md": TO_OTHER},
        })
        d = peers / "entity-core-protocol" / "docs" / "status"
        d.mkdir(parents=True, exist_ok=True)
        (d / "ROUTING-2026-09-16-z-ours.md").write_text(TO_ARCH,
                                                        encoding="utf-8")
        code, res = inbound.scan(peers / "entity-system-architecture", peers)
        ok("our own tree is not scanned as a peer's outbox",
           not any("entity-core-protocol" in o["file"] for o in res["owed"]),
           res["owed"])

        # --- a peer's TRACKER aimed at our other repo is an inbound surface ---
        peers = build(tmp, "No citations here.\n", {
            "entity-core-go": {"ROUTING-2026-09-16-y.md": TO_OTHER},
        })
        t = peers / "entity-core-formalization" / "docs" / "status"
        t.mkdir(parents=True, exist_ok=True)
        (t / "TRACKER-entity-core-protocol.md").write_text(
            "asks P-2..P-10\n", encoding="utf-8")
        code, res = inbound.scan(peers / "entity-system-architecture", peers)
        ok("a peer tracker naming our OTHER repo is reported",
           [r["seat"] for r in res["peer_trackers"]]
           == ["entity-core-formalization"], res["peer_trackers"])
        ok("a tracker is still never a discharge and never gates",
           code == inbound.CLEAN and not res["owed"], (code, res["owed"]))

        # --- a single-repo seat is completely unaffected ---
        # Every seat but arch. The widening must be invisible to them.
        peers = build(tmp, "No citations here.\n", {
            "entity-core-go": {"ROUTING-2026-09-16-y.md": TO_OTHER},
        })
        kd = peers / "entity-core-keystone" / "docs"
        (kd / "status").mkdir(parents=True, exist_ok=True)
        (kd / "COHORT-OPEN-ITEMS.md").write_text("empty\n", encoding="utf-8")
        code, res = inbound.scan(peers / "entity-core-keystone", peers)
        ok("a single-repo seat resolves to exactly itself",
           res["seat_repos"] == ["entity-core-keystone"], res["seat_repos"])

    print()
    if FAILURES:
        print("%d FAILURE(S): %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("inbound self-test: all assertions passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
