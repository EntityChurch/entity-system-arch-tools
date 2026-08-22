#!/usr/bin/env python3
"""coverage — which specs have a guide, a proposal, and a design record.

`topology` maps spec→spec. This maps spec→**everything else**: the four layers a
spec is supposed to be surrounded by, and which of them are actually there.

    specs/          the normative surface        (the thing)
    guides/         how a human uses it          (is it teachable?)
    docs/proposals/ why it says what it says     (is it ratifiable / ratified?)
    docs/research/  the study behind it          (was the design space mapped?)

**Why this exists.** The design record had no index and no analyzer, and work was
repeatedly redone because the document that had already done it could not be
found — a landscape study named twice in a handoff went unread through three
published rulings; a networking-model guide was rediscovered only after a second
one was started. `docs/research/INDEX.md` fixed the lookup for humans. This fixes
the *coverage* question nobody could answer at all: **which specs are unsupported,
and which support documents are orphaned.**

**Linking is two-signal, and both are reported so neither is trusted alone:**

  * **cite** — the other document names the spec (`EXTENSION-RELAY`, with or
    without `.md`). Precise; misses a guide that teaches a spec without naming it.
  * **affinity** — stem alignment: `GUIDE-ROLE` ↔ `EXTENSION-ROLE`,
    `GUIDE-COMPUTE-PROGRAMMING` ↔ `EXTENSION-COMPUTE`. Catches the teaching guide;
    would over-match on its own.

A spec counts as covered by a layer if **either** signal fires. The text output
marks which one did (`c` cite · `a` affinity · `ca` both), because "the guide
never names the spec it teaches" is itself worth seeing.

**This is a READER and exits 0, deliberately.** A missing guide is not a defect —
most extensions do not need one, and cross-cutting guides serve many specs. A gate
here would be permanently red, and a gate that is always red teaches people to
ignore it, which is the failure mode this toolkit was built against (see the
`corpus`-is-not-in-`check` note in the CLI). Use it to see the shape; decide
case by case.

    spec coverage [ROOT]            # the table + the four orphan/gap lists
    spec coverage [ROOT] --gaps     # only the gaps, for a worklist
    spec coverage [ROOT] --json     # the full mapping

ROOT defaults to the corpus root. Stdlib-only 3.11+.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import config as _config

_CFG = _config.load()

# A doc name as it appears in a citation: the stem, optionally with `.md`.
# Anchored on a word boundary so `EXTENSION-RELAY` does not match inside
# `EXTENSION-RELAY-THING`.
def _cite_re(stem: str) -> re.Pattern:
    return re.compile(r"\b%s(?:\.md)?\b" % re.escape(stem))

# Layer roots, relative to the corpus. Absent directories are skipped, not fatal
# — a repo may carry specs and no research workspace.
LAYERS: List[Tuple[str, str]] = [
    ("guide", "guides"),
    ("proposal", "docs/proposals"),
    ("research", "docs/research"),
]

# A spec-shaped document name: the corpus naming convention (SPECIFICATION-FORMAT
# / STYLE-NAMING-CONVENTIONS). Used only to tell "targets a spec elsewhere" from
# "targets no spec at all".
SPECNAME_RE = re.compile(
    r"\b((?:ENTITY|EXTENSION|SDK|GUIDE|SYSTEM|APP-CONVENTION|DOMAIN|ARCHITECTURE)-[A-Z0-9][A-Z0-9-]{2,})\b")

VERSION_RE = re.compile(r"^\*\*Version\*\*:?\s*(.+)$", re.M)
STATUS_RE = re.compile(r"^\*\*Status\*\*:?\s*(.+)$", re.M)

# A spec naming its own originating proposal. "No design record" and "the record
# exists and is named but is not in this corpus" are different findings with
# different fixes — the second is a pull-in, not authoring work — and reporting
# them as one sends people to write a document that already exists.
PROPOSALNAME_RE = re.compile(r"\b(PROPOSAL-[A-Z0-9][A-Z0-9-]{2,})\b")

# A document declaring itself informative rather than normative, IN ITS OWN TEXT.
# This is the document's *self-declaration*, which is a different fact from the
# corpus-level class assignment (`config.doc_class`, below) and is kept separate
# on purpose: where the two disagree, that disagreement is the finding.
#
# Only two files in the arch corpus carry this today and both invented the field.
# SPECIFICATION-FORMAT §11.3 *does* define the class concept — it names three
# citation-target kinds (another normative spec · an architectural/guide document
# · anything else) and §11.4 the dangling dispositions. What it does not give a
# document is a way to DECLARE its own class in its header, which is why two
# files invented `Authoritative scope:` rather than reaching for a standard field.
INFORMATIVE_RE = re.compile(
    r"^\*\*Authoritative scope[^\n]*\b[Ii]nformative\b|^\*\*Status\*\*[^\n]*\b[Ii]nformative\b",
    re.M)

# Classes that are NOT held to the "should have a guide / should have a design
# record" expectation, because they are not canonical specs — they ARE the
# support layer.
#
#   guide     a rulebook or how-to (SPECIFICATION-FORMAT, STYLE-NAMING-CONVENTIONS)
#   arch-doc  a synthesis / navigation / orientation reference (ARCHITECTURE-*,
#             ENTITY-SYSTEM-REFERENCE, a domain CHARTER)
#
# Holding these to the spec expectation is a category error, and it is the one
# this analyzer made on its first run: it reported five "specs with no guide", of
# which three were a rulebook, a working reference, and a domain charter — each
# already classed non-spec in `config.default.toml`, by a map this file was not
# reading while `address.py` was. Two class systems for one question is the exact
# shape the toolkit exists to prevent.
SUPPORT_CLASSES = ("guide", "arch-doc")


class Doc:
    __slots__ = ("path", "stem", "text", "rel")

    def __init__(self, path: Path, root: Path) -> None:
        self.path = path
        self.stem = path.stem
        try:
            self.text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            self.text = ""
        try:
            self.rel = str(path.relative_to(root))
        except ValueError:
            self.rel = str(path)


def _collect(root: Path, sub: str) -> List[Doc]:
    d = root / sub
    if not d.is_dir():
        return []
    return [Doc(p, root) for p in sorted(d.rglob("*.md"))
            if "archive" not in p.parts and p.name != "INDEX.md"
            and p.name != "README.md"]


def _affinity(spec_stem: str, other_stem: str) -> bool:
    """Stem alignment across a layer's naming prefix.

    `EXTENSION-ROLE` ↔ `GUIDE-ROLE`; `EXTENSION-COMPUTE` ↔ `GUIDE-COMPUTE-PROGRAMMING`
    (the guide stem *extends* the topic). Requires the topic to be a whole
    hyphen-segment run, so `EXTENSION-ROLE` does not match `GUIDE-ROLES-OF-X`
    only by prefix accident.
    """
    topic = spec_stem.split("-", 1)[-1] if "-" in spec_stem else spec_stem
    if len(topic) < 3:
        return False
    other_topic = other_stem.split("-", 1)[-1] if "-" in other_stem else other_stem
    segs = other_topic.split("-")
    t_segs = topic.split("-")
    return segs[:len(t_segs)] == t_segs


def build(root: Path) -> Tuple[List[Doc], Dict[str, List[Doc]]]:
    scope = _CFG.scope("core-specs")
    specs_dir = root / "specs"
    specs = [Doc(p, root) for p in sorted(specs_dir.rglob("*.md"))
             if not (set(p.parts) & set(scope.exclude_dirs))] if specs_dir.is_dir() else []
    layers = {name: _collect(root, sub) for name, sub in LAYERS}
    return specs, layers


def _signals(spec: Doc, others: List[Doc]) -> List[Tuple[Doc, str]]:
    rx = _cite_re(spec.stem)
    out: List[Tuple[Doc, str]] = []
    for o in others:
        sig = ""
        if rx.search(o.text):
            sig += "c"
        if _affinity(spec.stem, o.stem):
            sig += "a"
        if sig:
            out.append((o, sig))
    return out


def _meta(text: str) -> Tuple[str, str]:
    v = VERSION_RE.search(text)
    s = STATUS_RE.search(text)
    return (v.group(1).strip() if v else "-", s.group(1).strip() if s else "-")


def analyze(root: Path) -> Dict:
    specs, layers = build(root)
    proposal_stems = {d.stem for d in layers["proposal"]}
    rows = []
    for sp in specs:
        ver, status = _meta(sp.text)
        named = sorted(set(PROPOSALNAME_RE.findall(sp.text)))
        cls = _CFG.doc_class(sp.stem)
        row: Dict = {"spec": sp.stem, "path": sp.rel, "version": ver, "status": status,
                     "class": cls,
                     "canonical": cls not in SUPPORT_CLASSES,
                     "informative": bool(INFORMATIVE_RE.search(sp.text)),
                     "names_absent_proposals": [n for n in named
                                                if n not in proposal_stems]}
        for name, _ in LAYERS:
            hits = _signals(sp, layers[name])
            row[name] = [{"doc": d.rel, "signal": s} for d, s in hits]
        rows.append(row)

    # Orphans, split two ways — because "names no spec here" has two very
    # different causes and conflating them makes the list noise.
    #
    #   external — it targets a spec-shaped name that is not in THIS corpus:
    #     a sibling repo (`ENTITY-CORE-PROTOCOL` lives in entity-core-protocol)
    #     or an archived/renamed doc. Expected, not a defect.
    #   orphan   — it names no spec-shaped target at all. Either genuinely
    #     free-standing (a cohort absorption, a process proposal) or the
    #     support document nobody can find their way to.
    spec_stems = {sp.stem for sp in specs}
    spec_res = [(sp.stem, _cite_re(sp.stem)) for sp in specs]
    orphans: Dict[str, List[str]] = {}
    external: Dict[str, List[Dict[str, str]]] = {}
    for name, _ in LAYERS:
        o: List[str] = []
        ext: List[Dict[str, str]] = []
        for d in layers[name]:
            if any(rx.search(d.text) or _affinity(stem, d.stem)
                   for stem, rx in spec_res):
                continue
            out_of_corpus = sorted({m for m in SPECNAME_RE.findall(d.text)
                                    if m not in spec_stems})
            if out_of_corpus:
                ext.append({"doc": d.rel, "targets": ", ".join(out_of_corpus[:4])})
            else:
                o.append(d.rel)
        orphans[name] = o
        external[name] = ext

    return {"root": str(root), "specs": rows, "orphans": orphans,
            "external": external,
            "counts": {n: len(layers[n]) for n, _ in LAYERS}}


def render_text(res: Dict, gaps_only: bool) -> str:
    out: List[str] = []
    rows = res["specs"]
    c = res["counts"]
    out.append("spec coverage — %d specs · %d guides · %d proposals · %d research docs"
               % (len(rows), c["guide"], c["proposal"], c["research"]))
    out.append("  signal: c=cited by name · a=stem affinity · ca=both · reader, always exits 0")
    out.append("")

    if not gaps_only:
        out.append("  %-42s %-7s %-8s %-9s %-6s %-5s %s"
                   % ("spec", "ver", "status", "class", "guide", "prop", "research"))
        for r in rows:
            def mark(k: str) -> str:
                hits = r[k]
                if not hits:
                    return "—"
                sig = "".join(sorted({h["signal"] for h in hits}))
                return "%d%s" % (len(hits), sig[:2])
            out.append("  %-42s %-7s %-8s %-9s %-6s %-5s %s"
                       % (r["spec"][:42], r["version"][:7], r["status"][:8],
                          r["class"][:9],
                          mark("guide"), mark("proposal"), mark("research")))
        out.append("")

    # The gap lists run over CANONICAL SPECS ONLY. A guide or an arch-doc is not
    # a spec missing its support layer; it IS the support layer.
    canon = [r for r in rows if r["canonical"]]
    support = [r for r in rows if not r["canonical"]]

    no_guide = [r["spec"] for r in canon if not r["guide"]]
    _recordless = [r for r in canon if not r["proposal"] and not r["research"]]
    no_record = [r["spec"] for r in _recordless
                 if not r["names_absent_proposals"]]
    record_elsewhere = [(r["spec"], ", ".join(r["names_absent_proposals"][:3]))
                        for r in _recordless if r["names_absent_proposals"]]
    # A document whose own text says "informative" while the corpus class map
    # calls it a canonical spec. The two disagree; that disagreement is the
    # finding, and it is what a header-declared class field would settle.
    class_mismatch = [r["spec"] for r in canon if r["informative"]]
    guide_no_cite = [r["spec"] for r in canon
                     if r["guide"] and all("c" not in h["signal"] for h in r["guide"])]

    out.append("gaps")
    out.append("  canonical specs with no guide (%d of %d canonical):"
               % (len(no_guide), len(canon)))
    for s in no_guide:
        out.append("    %s" % s)
    out.append("  canonical specs with NO design record and naming none (%d):"
               % len(no_record))
    for s in no_record:
        out.append("    %s" % s)
    if record_elsewhere:
        out.append("  specs whose design record is NAMED but absent — pull-in, not authoring (%d):"
                   % len(record_elsewhere))
        for s, p in record_elsewhere:
            out.append("    %-42s names %s" % (s, p))
    if support:
        out.append("  NOT canonical specs — the support layer itself, held to no")
        out.append("  guide/record expectation (%d, class per config.default.toml):"
                   % len(support))
        for r in support:
            out.append("    %-42s %s" % (r["spec"], r["class"]))
    if class_mismatch:
        out.append("  CLASS MISMATCH — the document's own text declares it informative")
        out.append("  but the corpus class map calls it a canonical spec (%d):"
                   % len(class_mismatch))
        for s in class_mismatch:
            out.append("    %s" % s)
    if guide_no_cite:
        out.append("  guide matched by affinity but never names the spec (%d):"
                   % len(guide_no_cite))
        for s in guide_no_cite:
            out.append("    %s" % s)

    for name, _ in LAYERS:
        orph = res["orphans"][name]
        if orph:
            out.append("  orphan %ss — name NO spec-shaped target at all (%d):"
                       % (name, len(orph)))
            for p in orph:
                out.append("    %s" % p)
    for name, _ in LAYERS:
        ext = res.get("external", {}).get(name, [])
        if ext:
            out.append("  %ss targeting a spec outside this corpus — expected, not a defect (%d):"
                       % (name, len(ext)))
            for e in ext:
                out.append("    %-58s -> %s" % (e["doc"], e["targets"]))
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", type=Path, default=_CFG.corpus_dir,
                    help="corpus root (default: resolved corpus)")
    ap.add_argument("--gaps", action="store_true", help="only the gap lists")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if not args.root.is_dir():
        print("not a directory: %s" % args.root, file=sys.stderr)
        return 2
    if not (args.root / "specs").is_dir():
        print("no specs/ under %s — this reader has nothing to map."
              % args.root, file=sys.stderr)
        return 2

    res = analyze(args.root)
    print(json.dumps(res, indent=2) if args.json
          else render_text(res, args.gaps))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
