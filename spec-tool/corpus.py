#!/usr/bin/env python3
"""corpus — the test-vector corpus gate.

The other four analyzers read prose. This one reads the **artifacts**: the
`.diag` source and the `.cbor` build product that implementations actually
load. It exists because those files sat outside every analysis scope
(`test-vectors` is in `exclude_dirs` for `core-specs`, `core-specs-strict` and
`naming-surface`), so every defect the corpus has ever carried was not *missed*
by the toolkit — it was **unreachable** by it.

    spec corpus [--root PATH] [--vendor PATH] [--json]

What it checks, and the defect each rule is the mechanism for:

  corpus-version-stamp    A corpus directory or artifact stem carrying a
                          spec-revision stamp (`v767`) or a bare `-vN` stamp.
                          `v767` = revision v7.67, the revision that birthed the
                          corpus; the corpus has since been re-stamped under
                          v7.77 rules and the release is v0.8.0. A name that was
                          true when written and is now false. The `-vN` stamp has
                          never once been incremented in any repo.

  corpus-name-mismatch    The artifact stem names a different corpus than its
                          directory does — `v767/conformance-vectors-v1.*` is the
                          *agility* corpus wearing the *conformance* corpus's
                          filename, two directories from the real one.

  corpus-pair-incomplete  A `.diag` with no `.cbor`, or the reverse. The pair IS
                          the corpus: `SEEDS.md` §4.2's two gates (`verify` =
                          artifact-is-expected, `-check` = source-produces-
                          artifact) both need both members.

  corpus-placeholder      A `TBD-…`/`PENDING` placeholder surviving into an
                          artifact. F16: the corpus sha-locked, and was declared
                          Phase-2 LOCKED, over twelve `"TBD-COHORT-ROUND-TRIP"`
                          strings.

  corpus-fixture-width    A declared fixture fill-byte run at the wrong width.
                          F16 again, the half that survived seven weeks longer:
                          58-byte Ed448 seeds (RFC 8032 says 57) and 63-byte
                          `0xAA` pubkeys (the fixture is `0xAA×64`).
                          `agility-SEEDS.md` §2 *declares* those widths in prose;
                          nothing ever checked that the artifacts honour the
                          declaration. The config now carries the declaration and
                          this rule is the check.

  corpus-pair-disagree    `.diag` and `.cbor` disagree on the fixture widths.
                          This is the shape that hid the longest, because each
                          file is individually plausible: keystone `9292a3a`
                          carries a *correct* `.cbor` (57/64) beside a `.diag`
                          still at 58/63, under a MANIFEST calling the `.diag`
                          the "human source-of-truth".

`--vendor PATH` runs every content rule over a vendored copy in another tree and
reports, per file, whether the source has a same-named file and whether the bytes
match. It is **read-only** and takes an explicit path: vendors live in other
teams' repos, so the tool reads them and routes, it never edits them. It does not
guess a name mapping — a vendor whose files are named differently from the source
is reported as unmatched, not silently paired.

Exit codes are three-valued, like every other gate here: 0 clean, 1 violations,
2 could-not-look. "Could not look" and "there is no corpus here" are DIFFERENT
results and are reported differently — the corpus root missing entirely is a 2,
while a corpus root that simply holds no test-vector tree (this is true of
`entity-system-architecture`, which is prose) is a 0 with an explicit
not-applicable line. Collapsing those two is how a gate reports green over
nothing.

Stdlib-only, like the rest of the package.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import config as _config

_CFG = _config.load()
_A = _CFG.analyzer("corpus")
_SCOPE = _CFG.scope(_A.get("scope", "test-vector-corpus"))
DEFAULT_ROOT = _SCOPE.root

RULES: Dict[str, str] = dict(_A.get("rules", {}))

# Fill byte (as written in config, "0x42") -> the width in bytes that fixture
# MUST have. Corpus knowledge, so it lives in config: a different corpus is a
# different config file, the code is one.
FIXTURE_WIDTHS: Dict[int, int] = {
    int(k, 16): int(v) for k, v in (_A.get("fixture_widths", {}) or {}).items()
}
# Runs shorter than this are ordinary data, not a fixture. The fixtures this
# guards are 32/57/64 bytes; 8 is comfortably below the floor and far above the
# length at which a repeated byte occurs by chance in CBOR.
MIN_RUN = int(_A.get("min_fixture_run", 8))

PLACEHOLDERS: List[str] = list(_A.get("placeholders", []) or [])

# A spec-revision stamp (`v767`, `v7.67`, `V7-67`) or a bare artifact version
# (`-v1`, `_v2`). Release-snapshot directories (`v0.8.0/`) are a DIFFERENT thing
# and are exempted by config: there the version IS the identity of a vendored
# point-in-time snapshot, which is legitimate and stays.
REVISION_STAMP_RE = re.compile(r"[vV]\d{3}\b|[vV]\d+[._-]\d{2}\b")
ARTIFACT_STAMP_RE = re.compile(r"[-_][vV]\d+$")
SNAPSHOT_RE = re.compile(r"^[vV]\d+\.\d+\.\d+$")

# Corpus words: the noun a corpus directory and its artifacts must agree on.
CORPUS_WORDS = tuple(_A.get("corpus_words", []) or [])

ARTIFACT_SUFFIXES = (".diag", ".cbor")


class Finding:
    __slots__ = ("rule", "where", "text")

    def __init__(self, rule: str, where: str, text: str):
        self.rule = rule
        self.where = where
        self.text = text

    def severity(self) -> str:
        return RULES.get(self.rule, "warn")


# --------------------------------------------------------------------------
# Measurement. Both members are measured by the SAME function over the SAME
# unit (fill byte -> width), which is what lets `corpus-pair-disagree` compare
# them at all. The `.diag` is hex text and the `.cbor` is bytes; normalising to
# one shape here is the whole trick.
# --------------------------------------------------------------------------

_HEX_RUN_RE = re.compile(r"h'((?:[0-9a-fA-F]{2})+)'")


def runs_in_diag(text: str) -> Dict[Tuple[int, int], int]:
    """Fill-byte runs in a `.diag`, as {(byte, width_bytes): count}.

    Only *homogeneous* hex strings count — `h'424242…42'` is a fixture, a hash
    pin is not. That is deliberate: this rule guards declared fixtures, and a
    byte pin is exactly the thing it must never second-guess.
    """
    out: Dict[Tuple[int, int], int] = {}
    for m in _HEX_RUN_RE.finditer(text):
        hexstr = m.group(1).lower()
        first = hexstr[:2]
        if len(hexstr) // 2 < MIN_RUN:
            continue
        if hexstr != first * (len(hexstr) // 2):
            continue
        out[(int(first, 16), len(hexstr) // 2)] = out.get((int(first, 16), len(hexstr) // 2), 0) + 1
    return out


def runs_in_cbor(blob: bytes) -> Dict[Tuple[int, int], int]:
    """Maximal fill-byte runs in a `.cbor`, as {(byte, width_bytes): count}.

    This decodes nothing. A structural CBOR decode would be better and is what
    `GUIDE-CONFORMANCE.md` §3.2 asks an implementation to do; a run scan is what
    a stdlib-only tool can do without vendoring a CBOR library, and it is
    sufficient for exactly the defect class F16 was: a fixture emitted one byte
    too wide or too narrow. Where the two disagree, §3.2 wins — this is a gate,
    not the oracle.
    """
    out: Dict[Tuple[int, int], int] = {}
    watched = set(FIXTURE_WIDTHS)
    i, n = 0, len(blob)
    while i < n:
        b = blob[i]
        j = i
        while j < n and blob[j] == b:
            j += 1
        width = j - i
        if width >= MIN_RUN and b in watched:
            out[(b, width)] = out.get((b, width), 0) + 1
        i = j
    return out


def corpus_word(name: str) -> Optional[str]:
    low = name.lower()
    for w in CORPUS_WORDS:
        if w in low:
            return w
    return None


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------

def check_naming(directory: Path, stems: List[str], rel_dir: str) -> List[Finding]:
    out: List[Finding] = []
    dname = directory.name

    if not SNAPSHOT_RE.match(dname) and REVISION_STAMP_RE.search(dname):
        out.append(Finding(
            "corpus-version-stamp", rel_dir,
            "corpus directory carries a spec-revision stamp: %r. The corpus is named"
            " for what it tests, not for the revision that birthed it." % dname))

    dword = corpus_word(dname)
    for stem in sorted(stems):
        if REVISION_STAMP_RE.search(stem):
            out.append(Finding(
                "corpus-version-stamp", "%s/%s" % (rel_dir, stem),
                "artifact stem carries a spec-revision stamp: %r." % stem))
        if ARTIFACT_STAMP_RE.search(stem):
            out.append(Finding(
                "corpus-version-stamp", "%s/%s" % (rel_dir, stem),
                "artifact stem carries a version stamp (%r) that has never been"
                " incremented. Corpus history belongs in a CHANGELOG beside it."
                % ARTIFACT_STAMP_RE.search(stem).group(0)))
        sword = corpus_word(stem)
        if dword and sword and dword != sword:
            out.append(Finding(
                "corpus-name-mismatch", "%s/%s" % (rel_dir, stem),
                "artifact names the %r corpus inside the %r directory." % (sword, dword)))
    return out


def check_pair(rel_dir: str, stem: str, members: Dict[str, Path]) -> List[Finding]:
    """Every content rule, for one `.diag`/`.cbor` pair."""
    out: List[Finding] = []
    where = "%s/%s" % (rel_dir, stem)

    if len(members) != len(ARTIFACT_SUFFIXES):
        have = ", ".join(sorted(members))
        missing = ", ".join(s for s in ARTIFACT_SUFFIXES if s not in members)
        out.append(Finding(
            "corpus-pair-incomplete", where,
            "corpus member(s) missing: have %s, missing %s." % (have, missing)))

    measured: Dict[str, Dict[Tuple[int, int], int]] = {}
    for suffix, path in sorted(members.items()):
        try:
            blob = path.read_bytes()
        except Exception as exc:  # noqa: BLE001
            out.append(Finding("corpus-pair-incomplete", where + suffix,
                               "unreadable: %s" % exc))
            continue

        for token in PLACEHOLDERS:
            n = blob.count(token.encode())
            if n:
                out.append(Finding(
                    "corpus-placeholder", where + suffix,
                    "%d placeholder(s) %r survive into the artifact." % (n, token)))

        if suffix == ".diag":
            measured[suffix] = runs_in_diag(blob.decode("utf-8", "replace"))
        else:
            measured[suffix] = runs_in_cbor(blob)

        for (byte, width), count in sorted(measured[suffix].items()):
            want = FIXTURE_WIDTHS.get(byte)
            if want is not None and width != want:
                out.append(Finding(
                    "corpus-fixture-width", where + suffix,
                    "fixture 0x%02x is %d bytes wide (x%d); the declared width is %d."
                    % (byte, width, count, want)))

    if len(measured) == len(ARTIFACT_SUFFIXES):
        d, c = measured[".diag"], measured[".cbor"]
        watched_d = {k: v for k, v in d.items() if k[0] in FIXTURE_WIDTHS}
        watched_c = {k: v for k, v in c.items() if k[0] in FIXTURE_WIDTHS}
        if watched_d != watched_c:
            out.append(Finding(
                "corpus-pair-disagree", where,
                ".diag and .cbor disagree on fixture widths — .diag %s, .cbor %s."
                % (_fmt_runs(watched_d), _fmt_runs(watched_c))))
    return out


def _fmt_runs(runs: Dict[Tuple[int, int], int]) -> str:
    if not runs:
        return "{}"
    return "{" + ", ".join("0x%02x:%dB x%d" % (b, w, n)
                           for (b, w), n in sorted(runs.items())) + "}"


# --------------------------------------------------------------------------
# Discovery + run
# --------------------------------------------------------------------------

def find_corpus_dirs(root: Path) -> Dict[Path, Dict[str, Dict[str, Path]]]:
    """{corpus_dir: {stem: {suffix: path}}} for every dir holding artifacts."""
    found: Dict[Path, Dict[str, Dict[str, Path]]] = {}
    if not root.exists():
        return found
    for p in sorted(root.rglob("*")):
        if p.suffix not in ARTIFACT_SUFFIXES or not p.is_file():
            continue
        found.setdefault(p.parent, {}).setdefault(p.stem, {})[p.suffix] = p
    return found


def rel(path: Path) -> str:
    for anchor in (_CFG.repo_root, _config.TOOL_ROOT):
        try:
            return str(path.relative_to(anchor))
        except ValueError:
            continue
    return str(path)


def analyze_tree(root: Path) -> Tuple[List[Finding], int]:
    findings: List[Finding] = []
    n = 0
    for directory, stems in sorted(find_corpus_dirs(root).items()):
        rel_dir = rel(directory)
        findings += check_naming(directory, list(stems), rel_dir)
        for stem, members in sorted(stems.items()):
            n += len(members)
            findings += check_pair(rel_dir, stem, members)
    return findings, n


def compare_vendor(source: Path, vendor: Path) -> List[Finding]:
    """Byte relation between a vendored copy and the source corpus.

    Matched by identical filename only. A vendor is a copy; if it has been
    renamed on the way in, that is a derivation, and a derivation that nothing
    checks is how a corrected `.cbor` came to sit beside an uncorrected `.diag`
    for seven weeks.
    """
    out: List[Finding] = []
    src_by_name: Dict[str, List[Path]] = {}
    for _d, stems in find_corpus_dirs(source).items():
        for _s, members in stems.items():
            for _suf, p in members.items():
                src_by_name.setdefault(p.name, []).append(p)

    for _d, stems in sorted(find_corpus_dirs(vendor).items()):
        for _s, members in sorted(stems.items()):
            for _suf, p in sorted(members.items()):
                srcs = src_by_name.get(p.name, [])
                if not srcs:
                    out.append(Finding(
                        "vendor-unmatched", str(p),
                        "no file of this name in the source corpus — the vendor"
                        " relation cannot be checked by name."))
                    continue
                if len(srcs) > 1:
                    # Two source corpora sharing one filename. Picking either is
                    # a coin-flip that reports green half the time, which is
                    # worse than reporting that the name does not identify a
                    # corpus. This is the `conformance-vectors-v1` collision.
                    out.append(Finding(
                        "vendor-ambiguous", str(p),
                        "the name matches %d source files (%s) — a filename that"
                        " does not identify one corpus cannot anchor a vendor"
                        " relation." % (len(srcs), ", ".join(sorted(rel(s) for s in srcs)))))
                    continue
                src = srcs[0]
                if src.read_bytes() != p.read_bytes():
                    out.append(Finding(
                        "vendor-drift", str(p),
                        "differs from source %s — the vendored artifact is not the"
                        " artifact the corpus publishes." % rel(src)))
    return out


def run(root: Path, vendor: Optional[Path], as_json: bool) -> int:
    # Could-not-look vs nothing-to-look-at. See the module docstring: these are
    # different results and are never reported as the same result.
    if not _CFG.corpus_dir.exists():
        print("corpus root does not exist: %s" % _CFG.corpus_dir, file=sys.stderr)
        print("  scanned 0 files — this is not a pass, it is a gate that did not look.",
              file=sys.stderr)
        print("  point it at a corpus: --root PATH, `spec --corpus PATH corpus`,"
              " $SPEC_CORPUS, or run from the corpus root.", file=sys.stderr)
        return 2

    findings, n_files = analyze_tree(root)

    if vendor is not None:
        if not vendor.exists():
            print("vendor path does not exist: %s" % vendor, file=sys.stderr)
            return 2
        v_findings, v_files = analyze_tree(vendor)
        findings += v_findings
        findings += compare_vendor(root, vendor)
        n_files += v_files

    if n_files == 0:
        msg = ("no test-vector corpus under %s — not applicable to this repo."
               % rel(root))
        if as_json:
            print(json.dumps({"summary": {"errors": 0, "warnings": 0, "files": 0,
                                          "applicable": False}, "findings": []}, indent=2))
        else:
            print(msg)
            print("(a prose corpus has no artifacts to gate; this is a 0, not a pass"
                  " over an empty set — the root exists and holds no test-vectors.)")
        return 0

    n_error = sum(1 for f in findings if f.severity() == "error")
    n_warn = sum(1 for f in findings if f.severity() == "warn")

    if as_json:
        print(json.dumps({
            "summary": {"errors": n_error, "warnings": n_warn, "files": n_files,
                        "applicable": True},
            "findings": [{"rule": f.rule, "severity": f.severity(),
                          "where": f.where, "text": f.text} for f in findings],
        }, indent=2))
        return 1 if n_error else 0

    by_where: Dict[str, List[Finding]] = {}
    for f in findings:
        by_where.setdefault(f.where, []).append(f)
    for where in sorted(by_where):
        fs = by_where[where]
        print("\n%s" % where)
        for f in sorted(fs, key=lambda x: (x.severity() != "error", x.rule)):
            label = "ERROR" if f.severity() == "error" else "warn "
            print("  %s  %-22s %s" % (label, f.rule, f.text))

    print("\n%d artifact(s) scanned — %d error(s), %d warning(s)."
          % (n_files, n_error, n_warn))
    return 1 if n_error else 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=None,
                    help="test-vector tree to gate (default: the configured scope)")
    ap.add_argument("--vendor", type=Path, default=None,
                    help="a vendored copy in another tree: gate it and diff it "
                         "against the source (read-only)")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)
    return run(args.root or DEFAULT_ROOT, args.vendor, args.json)


if __name__ == "__main__":
    raise SystemExit(main())
