#!/usr/bin/env python3
"""corpus_selftest — invariant checks for the test-vector corpus gate.

Like `address_selftest` and `standards_selftest`, this pins *behavior* against
synthetic fixtures written here in the test, not finding counts against a real
corpus — so corpus corrections never make it stale. The fixtures are built in a
temp dir and thrown away; nothing here touches a checkout.

Why this gate has a self-test at all: every rule in it is the mechanism for a
defect that shipped, sha-locked, and was declared closed. F16 was reported,
fixed in the `.cbor`, marked RESOLVED, and its `.diag` half then survived seven
more weeks in two repos under a manifest calling that `.diag` the human
source-of-truth. A rule whose whole purpose is to catch "the note says it was
fixed" needs a test that is not itself a note saying it was fixed.

    python3 spec-tool/tests/corpus_selftest.py    # exits non-zero on failure

Stdlib-only. Fourth leg of tool verification, beside parity.sh +
address_selftest + standards_selftest.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import corpus  # noqa: E402

FAILURES = []
RAN = []  # counted, not hardcoded — a hand-maintained "N/N" is one more number
          # that goes stale silently, which is the defect this whole gate is for.

# The real corpus's declared widths, so the fixtures below read like the thing
# they guard. Assert the config carries them rather than hardcoding a parallel
# copy — a self-test that redeclares the values it checks tests only itself.
DECLARED = corpus.FIXTURE_WIDTHS


def case(name, got, want):
    RAN.append(name)
    if got != want:
        FAILURES.append("%s: want %r, got %r" % (name, want, got))
        print("  FAIL %s (want %r, got %r)" % (name, want, got))
    else:
        print("  ok   %s" % name)


def diag(seed_byte, seed_width, pubkey_width, extra=""):
    """A minimal `.diag` shaped like the agility corpus."""
    return ("/ synthetic corpus /\n[\n  {\n"
            '    "id": "fixture.1",\n'
            '    "secret_seed": h\'%s\',\n'
            '    "public_key": h\'%s\',\n%s  }\n]\n'
            % ("%02x" % seed_byte * seed_width, "aa" * pubkey_width, extra))


def cbor(seed_byte, seed_width, pubkey_width):
    """A minimal `.cbor` carrying the same fixtures as raw byte runs."""
    return b"\x82" + bytes([seed_byte]) * seed_width + b"\x58" + b"\xaa" * pubkey_width


def build(tmp, dirname, stem, diag_text=None, cbor_bytes=None):
    d = Path(tmp) / dirname
    d.mkdir(parents=True, exist_ok=True)
    if diag_text is not None:
        (d / (stem + ".diag")).write_text(diag_text)
    if cbor_bytes is not None:
        (d / (stem + ".cbor")).write_bytes(cbor_bytes)
    return d


def rules(root, vendor=None):
    """Rule ids the gate reports over `root`, as a sorted list."""
    findings, _ = corpus.analyze_tree(Path(root))
    if vendor is not None:
        v, _ = corpus.analyze_tree(Path(vendor))
        findings += v + corpus.compare_vendor(Path(root), Path(vendor))
    return sorted({f.rule for f in findings})


# --- the config carries the declarations the rules enforce ------------------
# If these move, the corpus changed and the change is deliberate; the point is
# that they live in config and not in analyzer code.

case("declares_ed448_seed_57", DECLARED.get(0x42), 57)
case("declares_ed448_alt_seed_57", DECLARED.get(0x46), 57)
case("declares_ed25519_seed_32", DECLARED.get(0x43), 32)
case("declares_fixture_pubkey_64", DECLARED.get(0xAA), 64)

# --- a correct corpus is silent ---------------------------------------------

with tempfile.TemporaryDirectory() as tmp:
    build(tmp, "crypto-agility", "agility-vectors",
          diag(0x42, 57, 64), cbor(0x42, 57, 64))
    case("clean_corpus_is_silent", rules(tmp), [])

# --- F16, both halves and the shape that hid between them -------------------

with tempfile.TemporaryDirectory() as tmp:
    build(tmp, "crypto-agility", "agility-vectors",
          diag(0x42, 58, 63), cbor(0x42, 58, 63))
    case("width_defect_in_both_members",
         rules(tmp), ["corpus-fixture-width"])

with tempfile.TemporaryDirectory() as tmp:
    # THE keystone shape, live at 9292a3a: a correct .cbor beside a .diag still
    # at the pre-F16 widths. Each file is individually plausible; only the
    # comparison catches it. This is the case the gate exists for.
    build(tmp, "crypto-agility", "agility-vectors",
          diag(0x42, 58, 63), cbor(0x42, 57, 64))
    case("correct_cbor_beside_stale_diag",
         rules(tmp), ["corpus-fixture-width", "corpus-pair-disagree"])

with tempfile.TemporaryDirectory() as tmp:
    build(tmp, "crypto-agility", "agility-vectors",
          diag(0x42, 57, 64,
               extra='    "expected_peer_a": "TBD-COHORT-ROUND-TRIP",\n'),
          cbor(0x42, 57, 64))
    case("placeholder_in_diag", rules(tmp), ["corpus-placeholder"])

with tempfile.TemporaryDirectory() as tmp:
    # F16's own headline: the .diag was clean and the .cbor still carried the
    # placeholders. `grep TBD` on the source is not a substitute for reading
    # the artifact — GUIDE-CONFORMANCE §3.2.
    d = build(tmp, "crypto-agility", "agility-vectors",
              diag(0x42, 57, 64), cbor(0x42, 57, 64))
    (d / "agility-vectors.cbor").write_bytes(
        cbor(0x42, 57, 64) + b"TBD-COHORT-ROUND-TRIP")
    case("placeholder_in_cbor_only", rules(tmp), ["corpus-placeholder"])

# --- naming ------------------------------------------------------------------

with tempfile.TemporaryDirectory() as tmp:
    build(tmp, "v767", "agility-vectors", diag(0x42, 57, 64), cbor(0x42, 57, 64))
    case("revision_stamped_directory", rules(tmp), ["corpus-version-stamp"])

with tempfile.TemporaryDirectory() as tmp:
    build(tmp, "crypto-agility", "agility-vectors-v1",
          diag(0x42, 57, 64), cbor(0x42, 57, 64))
    case("artifact_version_stamp", rules(tmp), ["corpus-version-stamp"])

with tempfile.TemporaryDirectory() as tmp:
    # A release-snapshot directory is a DIFFERENT thing: there the version is
    # the identity of a vendored point-in-time cut, and it stays.
    build(tmp, "v0.8.0", "agility-vectors", diag(0x42, 57, 64), cbor(0x42, 57, 64))
    case("release_snapshot_dir_is_exempt", rules(tmp), [])

with tempfile.TemporaryDirectory() as tmp:
    # The live defect: the agility corpus wearing the conformance corpus's name.
    build(tmp, "crypto-agility", "conformance-vectors",
          diag(0x42, 57, 64), cbor(0x42, 57, 64))
    case("artifact_names_the_wrong_corpus", rules(tmp), ["corpus-name-mismatch"])

# --- pairing -----------------------------------------------------------------

with tempfile.TemporaryDirectory() as tmp:
    build(tmp, "crypto-agility", "agility-vectors", diag(0x42, 57, 64), None)
    case("diag_without_cbor", rules(tmp), ["corpus-pair-incomplete"])

with tempfile.TemporaryDirectory() as tmp:
    build(tmp, "crypto-agility", "agility-vectors", None, cbor(0x42, 57, 64))
    case("cbor_without_diag", rules(tmp), ["corpus-pair-incomplete"])

# --- vendor relation ---------------------------------------------------------

with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as ven:
    build(src, "crypto-agility", "agility-vectors", diag(0x42, 57, 64), cbor(0x42, 57, 64))
    build(ven, "v0.8.0", "agility-vectors", diag(0x42, 57, 64), cbor(0x42, 57, 64))
    case("vendor_byte_identical_is_silent", rules(src, ven), [])

with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as ven:
    build(src, "crypto-agility", "agility-vectors", diag(0x42, 57, 64), cbor(0x42, 57, 64))
    build(ven, "v0.8.0", "agility-vectors", diag(0x42, 58, 63), cbor(0x42, 57, 64))
    case("vendor_stale_diag",
         rules(src, ven),
         ["corpus-fixture-width", "corpus-pair-disagree", "vendor-drift"])

with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as ven:
    build(src, "crypto-agility", "agility-vectors", diag(0x42, 57, 64), cbor(0x42, 57, 64))
    build(ven, "v0.8.0", "locally-generated", diag(0x42, 57, 64), cbor(0x42, 57, 64))
    case("vendor_file_with_no_source", rules(src, ven), ["vendor-unmatched"])

with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as ven:
    # Two source corpora sharing a filename: the name cannot anchor the vendor
    # relation, and silently picking one reports green half the time.
    build(src, "crypto-agility", "conformance-vectors", diag(0x42, 57, 64), cbor(0x42, 57, 64))
    build(src, "ecf-conformance", "conformance-vectors", diag(0x42, 57, 64), cbor(0x42, 57, 64))
    build(ven, "v0.8.0", "conformance-vectors", diag(0x42, 57, 64), cbor(0x42, 57, 64))
    case("vendor_name_matches_two_sources",
         [r for r in rules(src, ven) if r.startswith("vendor-")],
         ["vendor-ambiguous"])

# --- it stays quiet about things that are not fixtures ----------------------

with tempfile.TemporaryDirectory() as tmp:
    # A byte pin is not a fixture and must never be second-guessed by width.
    d = build(tmp, "crypto-agility", "agility-vectors",
              diag(0x42, 57, 64), cbor(0x42, 57, 64))
    (d / "agility-vectors.diag").write_text(
        diag(0x42, 57, 64,
             extra='    "canonical_content_hash": '
                   "h'012e64bbde3c494cf7cd4fb53ae3bf6420ec6d9bfa686348729eaa687e421c01',\n"))
    case("quiet_on_a_byte_pin", rules(tmp), [])

with tempfile.TemporaryDirectory() as tmp:
    # A short repeated run is ordinary data, not a declared fixture.
    d = build(tmp, "crypto-agility", "agility-vectors",
              diag(0x42, 57, 64), cbor(0x42, 57, 64) + b"\x42" * 4)
    case("quiet_on_a_short_run", rules(tmp), [])


if FAILURES:
    print("\n%d failure(s):" % len(FAILURES))
    for f in FAILURES:
        print("  - %s" % f)
    sys.exit(1)
print("\n%d/%d invariants pass" % (len(RAN), len(RAN)))
