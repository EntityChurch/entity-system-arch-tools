#!/usr/bin/env python3
"""spec vocab — does the application tier's TYPE VOCABULARY converge?

    spec vocab                       # reader, exits 0
    spec vocab --gate                # 0 clean · 1 findings · 2 could-not-look
    spec vocab --owed                # the worklist, one tag per line
    spec vocab --prefix share        # scope to one convention family
    spec vocab --json

WHAT THIS ANSWERS, AND WHY NOTHING ELSE COULD

`spec census` asks which normative SECTIONS the cohort cites. That works for the
core tier because the wire is self-falsifying: two peers either connect and agree
on bytes or they do not, and a conformance suite turns disagreement into a number.

**The application tier has no such oracle.** Two peers can be perfectly
wire-conformant and completely vocabulary-divergent **with no error anywhere** —
`APP-CONVENTION-SHARE` §2 states the failure exactly: a type-filtered query on the
wrong tag returns *a correct, complete, empty answer*. It never surfaces as a byte
mismatch, because the two sides never hold each other's data at all.

So the question *"do our application seats speak the same vocabulary"* was, until
this analyzer, answerable only by a person reading two trees side by side. That is
how `app/share/offer` was nearly minted into the corpus while **both** app seats
already shipped the word meaning **opposite** things — one an audience-scoped
share, the other an audience-less one. Nobody was careless. Nothing could look.

WHAT IT REPORTS

* `declared-unimplemented` — the corpus declares a tag and no seat emits it.
  Not a defect by itself; a convention may legitimately lead its implementations.
  It is a defect when the whole family is empty, because then nothing has ever
  exercised it.
* `implemented-undeclared` — a seat emits a tag no spec declares. This is the
  field ahead of the fold, which is how it is SUPPOSED to work here (the cohort
  discovers by building) — but an unfolded tag is an unpinned tag.
* `single-seat` — exactly one seat emits a declared convention tag. The
  convention's whole purpose is that two front-ends produce byte-compatible
  entities; one implementation has not tested that claim.
* `divergent-family` ⭐ — two or more seats emit tags under the SAME convention
  prefix and share **none** of them. That is the `offer` shape stated
  mechanically, and it is the finding no other instrument in this toolkit can
  reach.

DECLARED IS THREE-VALUED ON PURPOSE — `declared` · `mentioned` · absent

A tag is **declared** only in a normative-declaring form: inside a CDDL block as
`type: "TAG"`, as a `; type = TAG` comment, or as the leading cell of a type-table
row. Anything else in a spec is **mentioned** and is never counted as declared.

**This is not fastidiousness, it is the calibration defect this toolkit has now
hit five times.** `APP-CONVENTION-SHARE` §2 contains the sentence *"A tag under
one application's prefix (`app/entity-browser/share`) makes browser↔go aggregation
impossible"* — a **counter-example**. A matcher that counts occurrences reads that
as a declaration and reports the corpus as blessing the exact tag it forbids. A
first hand-run of this question also scored `app/site-manifest` as declared by
**zero** specs, because the tags in `APP-CONVENTION-SEMANTIC-CONTENT-SITE` are
written as CDDL comments (`; type = app/site-manifest`) and the matcher wanted
backticks. **Calibrate against the corpus's actual vocabulary, never against the
spelling the rule-writer expects.**

PRODUCT VS TEST IS A REAL DISTINCTION AND IS BEST-EFFORT

A tag appearing only in a test is not an emission. `entity-workbench-go` mentions
`app/share/manifest` in a subscription test as a throwaway string; reading that as
"workbench-go implements the browser's divergent share tag" would be wrong in the
most expensive direction — it would make a one-seat migration look like two.

Detection is filename-based (`*_test.go`, `*_test.rs`, `/tests/`, plus the seat's
configured `oracle_paths`) **and**, for Rust, brace-tracked `#[cfg(test)]` regions.
It is a heuristic and this tool says so on every run rather than implying a
precision it does not have.

WHAT IT DELIBERATELY DOES NOT DO

* **It does not claim a tag is implemented CORRECTLY.** A string literal is
  evidence of ATTENTION, never of conformance — `spec census`'s rule, applied one
  layer up. A seat can emit `app/share/record` and populate it wrongly.
* **It does not gate the backlog.** Reader by default. The app tier's declared
  surface is far ahead of its implemented surface and a wall of red on day one
  teaches people to skip the gate.
* **It does not read a tag out of a comment in a spec as authority.** See above.

Exit codes are three-valued: 0 clean, 1 findings, 2 could-not-look.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

CLEAN, FINDINGS, CANNOT_LOOK = 0, 1, 2

try:
    import config as _config
    _CFG = _config.load()
    _VOCAB = _CFG.analyzer("vocab")
    _CENSUS_CFG = _CFG.analyzer("census")
except Exception:  # noqa: BLE001
    _config = None
    _VOCAB = {}
    _CENSUS_CFG = {}

# A convention tag: `app/` plus at least one segment. Uppercase is excluded —
# a tag is kebab by STYLE-NAMING-CONVENTIONS, so `app/FOO` is prose, not a tag.
_TAG = r"app/[a-z0-9][a-z0-9/_-]*"
_TAG_RE = re.compile(_TAG)

# The three declaring forms. Anything else is `mentioned`.
_DECL_CDDL_FIELD = re.compile(r'type\s*:\s*"(' + _TAG + r')"')
_DECL_CDDL_NOTE = re.compile(r';.*\btype\s*=\s*(' + _TAG + r')\b')
_DECL_TABLE_ROW = re.compile(r'^\s*\|\s*`(' + _TAG + r')`\s*\|')

_LITERAL_RE = re.compile(r'"(' + _TAG + r'/?)"')

# A PARAMETRIC declaration: the spec declares a family and not an enumeration.
# `APP-CONVENTION-EMBED` is the worked case — its tag is `app/embed/{media_type}`
# and `app/embed/markdown` appears only as an example. Without this, the day a
# seat ships `app/embed/image/png` the analyzer calls it undeclared, which is
# false, and the false direction is the expensive one: it accuses a conformant
# seat of inventing vocabulary.
_DECL_PARAM = re.compile(
    r'(?:type\s*[:=]\s*)"?(app/[a-z0-9][a-z0-9/_-]*?)/(?:\{[a-z_]+\}|"\s*\.cat)')

# A PINNED TREE PATH, not a type tag. `APP-CONVENTION-FEED` §4.2 pins its index
# head at `/{peer}/app/feed/index` — a path a conformant seat MUST emit, and one
# no spec declares as vocabulary because it is not vocabulary.
#
# The defect this closes (`A-40`, browser-rust, 2026-09-11) is the EXPENSIVE
# direction: `make lint` failed a conformant seat for `app/feed/index`, a tag it
# does not emit. The existing guard keys on a trailing slash — added after a run
# read the tree prefix `"app/share/records/"` as invented vocabulary — and a
# COMPLETE path carries no trailing slash, so it is indistinguishable from a tag
# by shape alone.
#
# The corpus is the discriminator, not the shape: a pinned path is written with
# its peer-namespace prefix (`/{peer}/…`) and a type tag never is.
_DECL_PATH = re.compile(r'/\{[a-z_]+\}/(' + _TAG + r')')

_TEST_NAME = re.compile(r"(^|/)(tests?)/|_test\.(go|rs|py)$|(^|/)test_[^/]*\.py$")


def _seats() -> Dict[str, dict]:
    """Reuse `census`'s seat table — one config home for *where the seats are*.

    A second copy of that table would drift, and the drift would be invisible:
    both analyzers would keep reporting cleanly about different sets of trees.
    """
    return _VOCAB.get("seats") or _CENSUS_CFG.get("seats", {}) or {}


def _app_tier() -> List[str]:
    """Which seats are application tier. Config-driven; sensible default."""
    return _VOCAB.get("app_seats",
                      ["entity-browser-rust", "entity-workbench-go"])


def git(repo: Path, *args: str) -> str:
    try:
        r = subprocess.run(("git", "-C", str(repo)) + args, capture_output=True,
                           text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def family(tag: str) -> str:
    """The convention family a tag belongs to.

    `app/share/record` → `share`. `app/site-manifest` → `site`, because the site
    convention uses a hyphen where the others use a slash — a real inconsistency
    in the corpus, and folding it in here rather than reporting `site-manifest`
    and `site-page` as two families is the whole reason this function exists.
    """
    rest = tag[len("app/"):]
    head = rest.split("/", 1)[0]
    if "-" in head and "/" not in rest:
        return head.split("-", 1)[0]
    return head


# --------------------------------------------------------------------------
# 1. The declared side — what the corpus says
# --------------------------------------------------------------------------

def scan_corpus(corpus: Path) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]],
                                       Dict[str, Set[str]], Dict[str, Set[str]]]:
    """(declared, mentioned, parametric, pinned_paths) — tag → spec paths.

    `parametric` is keyed by the OPEN PREFIX, e.g. `app/embed`, and means the
    spec declared a family rather than an enumeration.

    `pinned_paths` is keyed by a TREE PATH the corpus pins, e.g.
    `app/feed/index`. It is not vocabulary and a seat emitting it is conformant.
    """
    declared: Dict[str, Set[str]] = defaultdict(set)
    mentioned: Dict[str, Set[str]] = defaultdict(set)
    param: Dict[str, Set[str]] = defaultdict(set)
    pinned: Dict[str, Set[str]] = defaultdict(set)
    specs = corpus / "specs"
    if not specs.is_dir():
        return declared, mentioned, param, pinned
    for p in sorted(specs.rglob("*.md")):
        rel = str(p.relative_to(corpus))
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "app/" not in text:
            continue
        for line in text.splitlines():
            if "app/" not in line:
                continue
            hits = set()
            for rx in (_DECL_CDDL_FIELD, _DECL_CDDL_NOTE):
                for m in rx.finditer(line):
                    hits.add(m.group(1))
            m = _DECL_TABLE_ROW.match(line)
            if m:
                hits.add(m.group(1))
            for t in hits:
                declared[t].add(rel)
            for m in _DECL_PARAM.finditer(line):
                param[m.group(1)].add(rel)
            for m in _DECL_PATH.finditer(line):
                pinned[m.group(1)].add(rel)
            for t in _TAG_RE.findall(line):
                if t not in hits:
                    mentioned[t].add(rel)
    # A token DECLARED as a type is a type, whatever else it looks like. A spec
    # that both declares `app/x` and writes `/{peer}/app/x` has declared it, and
    # the path form must not launder it out of the vocabulary.
    for t in list(pinned):
        if t in declared:
            del pinned[t]
    return declared, mentioned, param, pinned


def parametric_home(tag: str, param: Dict[str, Set[str]]) -> Optional[str]:
    """The open-family prefix that declares `tag`, if any."""
    for prefix in param:
        if tag.startswith(prefix + "/"):
            return prefix
    return None


# --------------------------------------------------------------------------
# 2. The implemented side — what the seats emit
# --------------------------------------------------------------------------

def _rust_test_lines(text: str) -> Set[int]:
    """1-indexed line numbers inside a `#[cfg(test)]` item, by brace depth.

    Rust puts its tests in the same file, so a filename heuristic alone would
    score every in-file test fixture as a product emission.
    """
    out: Set[int] = set()
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if "#[cfg(test)]" in lines[i]:
            depth, started = 0, False
            j = i
            while j < len(lines):
                depth += lines[j].count("{") - lines[j].count("}")
                if "{" in lines[j]:
                    started = True
                out.add(j + 1)
                if started and depth <= 0:
                    break
                j += 1
            i = j + 1
            continue
        i += 1
    return out


def scan_seat(name: str, root: Path, spec: dict) -> dict:
    globs = spec.get("source", [])
    skip = list(spec.get("skip", [])) + ["/.git/"]
    oracle = spec.get("oracle_paths", [])
    product: Dict[str, Set[str]] = defaultdict(set)
    tests: Dict[str, Set[str]] = defaultdict(set)
    # Trailing-slash literals, slash stripped. NOT tags — see the skip below —
    # but they are the only evidence a seat implements a PARAMETRIC family,
    # whose concrete tags are composed at runtime and are literals nowhere.
    prefixes: Dict[str, Set[str]] = defaultdict(set)
    files = 0
    for g in globs:
        for p in sorted(root.rglob(g)):
            try:
                rel = str(p.relative_to(root))
            except ValueError:
                continue
            if any(s in rel for s in skip):
                continue
            files += 1
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "app/" not in text:
                continue
            is_test_file = bool(_TEST_NAME.search(rel)) or any(o in rel for o in oracle)
            cfg_test = _rust_test_lines(text) if rel.endswith(".rs") else set()
            for n, line in enumerate(text.splitlines(), 1):
                if "app/" not in line:
                    continue
                for m in _LITERAL_RE.finditer(line):
                    tag = m.group(1)
                    # A TYPE TAG NEVER ENDS IN A SLASH. `"app/share/records/"` is
                    # a tree prefix (`ShareOfferPrefix`), and stripping the slash
                    # to make it look like a tag is how the first run of this
                    # analyzer reported a path as an undeclared vocabulary item.
                    #
                    # It is still recorded, because the SAME shape is how a seat
                    # implements a parametric family: `"app/embed/" + media_type`
                    # composes its concrete tag at runtime, so no literal tag
                    # exists anywhere. Discarding it unread is why the `embed`
                    # family read `implemented: 0` while a seat shipped a full
                    # §3 codec (`A-37`, browser-rust, 2026-09-11). Which of the
                    # two a prefix is, is decided by the CORPUS below — a tree
                    # prefix is declared nowhere, an open family is declared by
                    # `_DECL_PARAM` — never by its shape here.
                    if tag.endswith("/"):
                        prefixes[tag.rstrip("/")].add(rel)
                        continue
                    if tag == "app":
                        continue
                    (tests if (is_test_file or n in cfg_test) else product)[tag].add(rel)
    return {"name": name, "root": str(root), "files": files,
            "product": product, "tests": tests, "prefixes": prefixes,
            "head": git(root, "rev-parse", "--short", "HEAD"),
            "dirty": bool(git(root, "status", "--short"))}


def resolve_seats(corpus: Path) -> Tuple[List[dict], List[str]]:
    """(present, missing). A missing seat is NAMED, never silently dropped."""
    base = corpus.parent
    want = set(_app_tier())
    present, missing = [], []
    for nm, spec in _seats().items():
        if nm not in want:
            continue
        root = (base / spec.get("path", nm)).resolve()
        if root.is_dir():
            present.append({"name": nm, "root": root, "spec": spec})
        else:
            missing.append(nm)
    for nm in sorted(want - set(_seats())):
        missing.append(nm)
    return present, missing


# --------------------------------------------------------------------------
# 3. The join
# --------------------------------------------------------------------------

def scan(corpus: Path, prefix: Optional[str] = None) -> Tuple[int, dict]:
    declared, mentioned, param, pinned = scan_corpus(corpus)
    present, missing = resolve_seats(corpus)
    if not (corpus / "specs").is_dir():
        return CANNOT_LOOK, {"why": f"no specs/ under {corpus}",
                             "missing_seats": missing}
    if not present:
        return CANNOT_LOOK, {"why": "no application-tier seat tree found beside "
                                    f"{corpus} — looked for {', '.join(_app_tier())}",
                             "missing_seats": missing}

    seats = [scan_seat(s["name"], s["root"], s["spec"]) for s in present]

    def keep(t: str) -> bool:
        return prefix is None or family(t) == prefix

    impl: Dict[str, Set[str]] = defaultdict(set)   # tag -> seats, product only
    impl_test: Dict[str, Set[str]] = defaultdict(set)
    for s in seats:
        for t in s["product"]:
            impl[t].add(s["name"])
        for t in s["tests"]:
            impl_test[t].add(s["name"])

    # Only tags in a family the corpus knows about are convention tags. A seat's
    # private `app/<its-own-name>/…` namespace is explicitly legitimate and is
    # not a divergence — APP-CONVENTION-SHARE §2 says the type tag is the
    # contract and the path is the application's own business.
    known = {family(t) for t in declared} | {family(k + "/x") for k in param}
    findings: Dict[str, List[dict]] = defaultdict(list)

    for t in sorted(set(declared) | set(impl)):
        if not keep(t):
            continue
        fam = family(t)
        d, im = t in declared, sorted(impl.get(t, ()))
        if d and not im:
            findings["declared-unimplemented"].append(
                {"tag": t, "family": fam, "specs": sorted(declared[t]),
                 "tests_only": sorted(impl_test.get(t, ()))})
        elif im and not d and fam in known:
            home = parametric_home(t, param)
            if home:
                # Declared by an OPEN family. Conformant by construction; not a
                # finding, and reporting it as one would accuse a correct seat.
                continue
            if t in pinned:
                # A TREE PATH the corpus pins, not vocabulary. A seat emitting
                # it is doing what the convention requires.
                continue
            findings["implemented-undeclared"].append(
                {"tag": t, "family": fam, "seats": im,
                 "mentioned_in": sorted(mentioned.get(t, ()))})
        elif d and len(im) == 1 and len(seats) > 1:
            findings["single-seat"].append(
                {"tag": t, "family": fam, "seat": im[0],
                 "specs": sorted(declared[t])})

    # divergent-family: >1 seat inside one family, zero tags in common.
    fam_seats: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))
    for s in seats:
        for t in s["product"]:
            if family(t) in known and keep(t):
                fam_seats[family(t)][s["name"]].add(t)
    for fam, per in sorted(fam_seats.items()):
        if len(per) < 2:
            continue
        sets = list(per.values())
        common = set.intersection(*sets)
        if not common:
            findings["divergent-family"].append(
                {"family": fam,
                 "per_seat": {k: sorted(v) for k, v in sorted(per.items())}})

    families = {}
    for fam in sorted(known | {family(t) for t in impl if family(t) in known}):
        if prefix is not None and fam != prefix:
            continue
        dt = [t for t in declared if family(t) == fam]
        it = [t for t in impl if family(t) == fam]
        opens = sorted(k for k in param if family(k + "/x") == fam)
        # An OPEN family is implemented by a seat that emits its PREFIX — its
        # concrete tags are composed at runtime and are literals nowhere, so
        # counting literal tags alone reports 0 no matter who ships it.
        open_seats = sorted({s["name"] for s in seats
                             for k in opens if k in s["prefixes"]})
        families[fam] = {"declared": len(dt), "implemented": len(it),
                         "both": len([t for t in dt if t in impl]),
                         "open": opens, "open_seats": open_seats}

    res = {"corpus": str(corpus), "seats": [
        {"name": s["name"], "head": s["head"], "dirty": s["dirty"],
         "files": s["files"], "product_tags": len(s["product"]),
         "test_only_tags": len([t for t in s["tests"] if t not in s["product"]])}
        for s in seats],
        "missing_seats": missing, "families": families,
        "declared_total": len([t for t in declared if keep(t)]),
        "implemented_total": len([t for t in impl if keep(t)]),
        "findings": {k: v for k, v in findings.items() if v}}
    code = FINDINGS if res["findings"] else CLEAN
    return code, res


# --------------------------------------------------------------------------
# 4. Report
# --------------------------------------------------------------------------

_ORDER = ["divergent-family", "implemented-undeclared", "single-seat",
          "declared-unimplemented"]


def report(res: dict, gate: bool, owed: bool) -> None:
    if "why" in res:
        print(f"vocab: COULD NOT LOOK — {res['why']}")
        if res.get("missing_seats"):
            print("  seats not found: " + ", ".join(res["missing_seats"]))
        return

    f = res["findings"]
    if owed:
        for kind in _ORDER:
            for it in f.get(kind, []):
                print(it.get("tag") or ("family:" + it["family"]))
        return

    for s in res["seats"]:
        dirty = " (DIRTY)" if s["dirty"] else ""
        print(f"  {s['name']:<24} @ {s['head']}{dirty}  "
              f"{s['product_tags']} product tag(s), "
              f"{s['test_only_tags']} test-only")
    for nm in res.get("missing_seats", []):
        print(f"  {nm:<24}   NOT FOUND — named, not dropped")
    print()
    print(f"  {'family':<12} {'declared':>8} {'implemented':>12} {'both':>6}")
    for fam, c in res["families"].items():
        mark = ""
        if c.get("open"):
            mark = "  (open family — declares a PATTERN, not an enumeration)"
            # An open family's `implemented` column counts literal tags and is
            # structurally 0 — the concrete tags are composed at runtime. Say
            # who emits the prefix, or the row reads as "nobody built this".
            if c.get("open_seats"):
                mark += "; prefix emitted by " + ", ".join(c["open_seats"])
            else:
                mark += "; no seat emits the prefix"
        print(f"  {fam:<12} {c['declared']:>8} {c['implemented']:>12} "
              f"{c['both']:>6}{mark}")
    print()

    for kind in _ORDER:
        items = f.get(kind, [])
        if not items:
            continue
        print(f"{kind} — {len(items)}")
        for it in items:
            if kind == "divergent-family":
                print(f"  ⭐ app/{it['family']}/* — "
                      f"{len(it['per_seat'])} seats, ZERO tags in common:")
                for seat, tags in it["per_seat"].items():
                    print(f"       {seat:<22} {', '.join(tags)}")
            elif kind == "implemented-undeclared":
                print(f"  {it['tag']:<32} {', '.join(it['seats'])}")
            elif kind == "single-seat":
                print(f"  {it['tag']:<32} only {it['seat']}")
            else:
                extra = ""
                if it.get("tests_only"):
                    extra = "  (test-only in " + ", ".join(it["tests_only"]) + ")"
                print(f"  {it['tag']:<32} {', '.join(it['specs'])}{extra}")
        print()

    print(f"{res['declared_total']} declared tag(s) · "
          f"{res['implemented_total']} emitted in product code across "
          f"{len(res['seats'])} application seat(s).")
    print("a type-tag literal is evidence of ATTENTION, never of conformance — a "
          "seat can emit the right tag and populate it wrongly.")
    print("product-vs-test is a filename heuristic plus Rust #[cfg(test)] brace "
          "tracking. It is best-effort and this line is here so nobody reads it "
          "as exact.")
    if not gate:
        print("reader mode — exits 0. Run with --gate to enforce.")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=None)
    ap.add_argument("--prefix", default=None,
                    help="scope to one convention family, e.g. share")
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--owed", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    root = args.root
    if root is None:
        try:
            root = _config.corpus_root() if _config else Path.cwd()
        except Exception:  # noqa: BLE001
            root = Path.cwd()
    root = Path(root).resolve()

    code, res = scan(root, args.prefix)
    if code == CANNOT_LOOK:
        report(res, args.gate, args.owed)
        return CANNOT_LOOK
    if args.json:
        print(json.dumps(res, indent=1, default=list))
    else:
        report(res, args.gate, args.owed)
    return code if args.gate else CLEAN


if __name__ == "__main__":
    raise SystemExit(main())
