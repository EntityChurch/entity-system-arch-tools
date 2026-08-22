#!/usr/bin/env python3
"""coherence — the internal-consistency gate for the entity-core spec corpus.

`standards` checks a spec's *shape* (header, status, dates, citations) and
`style` checks its *naming*. Neither reads a spec against itself, and that is
the gap this module closes: every rule here compares two normative artifacts
**inside the corpus** and fires when they disagree.

    spec coherence [--root DIR|FILE ...] [--json]

Why it exists — the two rules below were derived from measured defects, not
from taste. Both defect families had the same career: they passed every prose
review, shipped, and were then found by an implementer building the section,
after the divergence had already been routed at an innocent peer.

**undefined-wire-referent.** `EXTENSION-CONTINUATION` §3.6 Step 4 read

    execute.deliver_token = generate_internal_deliver_token(continuation.data.deliver_to)

and `generate_internal_deliver_token` was defined **nowhere in the corpus** —
one call site, no definition, no prose. So each implementation improvised the
token, the improvisations agreed same-implementation and disagreed across the
wire, and the resulting cross-impl failure was routed at the wrong peer twice
across two cycles. `EXTENSION-REGISTRY` §6a.9's `pending_hash` was the same
shape one layer up (a `MUST` naming an entity with no schema), which is where
the rule was first written as prose: *a `MUST` may not name a referent the
corpus does not define*. Writing it as prose beside one instance did not stop
the next instance; this does.

The rule is deliberately narrow. Pseudocode is allowed local helpers whose
meaning is evident (`shallow_merge`, `trim_prefix`, `read_dir`) — a corpus-wide
"every called name must be defined" rule reports ~200 of those and would be
switched off within a week. The discriminator is **what the value becomes**: a
helper whose return value is assigned to a *field* is producing something an
entity or a wire frame carries, which another peer will read and verify. That
one is a contract; the rest are exposition. Measured over the corpus this rule
scored **one finding and zero false positives** — the one being the defect
above.

*What it does not see, stated so nobody reads a green run as more than it is.*
`EXTENSION-REVISION` §5.2 dispatched `lww` through `lww_resolve(...)`, defined
nowhere, over a comparison basis the same spec says is unspecified — the same
family, found by hand rather than by this rule, because the value flows into a
**returned merge outcome** rather than into a field. The obvious extension
(flag `key: helper(...)` inside a construction) was measured before being
rejected: three hits on this corpus, two of them plainly benign local helpers
(`shallow_copy`, `re2_full_match`). Two false positives out of three is the
trade that gets a gate switched off, so the rule stays narrow and this paragraph
carries the residue. **A cross-peer-observable value that is not a wire field is
still a contract; nothing checks those.**

**enum-value-not-declared.** `EXTENSION-REGISTRY` §6a.9 declared
`status: "bound" | "pending_review"` and §6a.9.3, written *to fix* an earlier
instance of exactly this, returned `{status: "denied"}` from `deny-request`.
Three implementations emitted the undeclared value (correctly — the operations
table is the more specific artifact) while the declaration sat two screens up
saying otherwise. The prior instance of the same shape produced **three
different carriers in three implementations** for one 202 response, because
`pending_hash` appeared in step-5 pseudocode and in no return type.

Both rules gate (`error`): each of the four instances above became a
cross-implementation divergence, and none is editorial.

Stdlib-only Python 3.11+. Exit **0** clean, **1** violations, **2** could-not-
look — a gate that scanned nothing has not passed.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import config as _config

_CFG = _config.load()
_SCOPE = _CFG.scope("core-specs-strict")
DEFAULT_ROOT = _SCOPE.root
EXCLUDE_DIRS = _SCOPE.exclude_dirs
EXCLUDE_FILES = _SCOPE.exclude_files

RULES = {
    "undefined-wire-referent": (
        "error",
        "a field is assigned from a helper the corpus never defines",
    ),
    "enum-value-not-declared": (
        "error",
        "a value is emitted for a field whose declared enumeration omits it",
    ),
}

# ---- rule 1: undefined-wire-referent ----------------------------------------
# A pseudocode definition: `name(args):` alone on its line.
DEF_RE = re.compile(r"^\s*([a-z][a-z0-9_]*)\s*\([^)]*\)\s*:\s*$")
# An assignment whose LHS is a *dotted* target (a field on an entity or frame)
# and whose RHS is a snake_case call. The dot is the whole discriminator: a
# bare local (`value = navigate(...)`) is exposition, `execute.deliver_token =`
# is a wire contract.
FIELD_ASSIGN_RE = re.compile(
    r"^\s*([a-z_][a-z0-9_]*(?:\.[a-z0-9_]+)+)\s*=\s*"
    r"([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\s*\("
)

# ---- rule 2: enum-value-not-declared ----------------------------------------
# A declaration line inside a type block: `field: "a" | "b" | "c"` (>= 2 alts,
# so a single-valued constant is not mistaken for an enumeration).
ENUM_DECL_RE = re.compile(
    r"^\s*([a-z][a-z0-9_]*)\??\s*:\s*"
    r"((?:\"[a-z0-9_-]+\"\s*\|\s*)+\"[a-z0-9_-]+\")"
)
ENUM_ALT_RE = re.compile(r"\"([a-z0-9_-]+)\"")
# A use site: `{field: "value"}` or `field: "value"` in prose/tables/pseudocode.
ENUM_USE_RE = re.compile(r"\b([a-z][a-z0-9_]*)\s*:\s*\"([a-z0-9_-]+)\"")
# The enclosing type of a block — `type: "system/x/y"` or `system/x/y := {`.
TYPE_CTX_RE = re.compile(r"^\s*type\s*:\s*\"([a-z0-9/_{}-]+)\"")
TYPE_DEF_RE = re.compile(r"^\s*([a-z][a-z0-9/_{}-]*)\s*:=")
# A type name mentioned on a prose/table line, which is how a use site outside
# a code block declares which type it is talking about.
TYPE_MENTION_RE = re.compile(r"`?(system/[a-z0-9/_-]+)`?")
# How far after a prose type mention a `field: "value"` may sit and still be
# read as belonging to it. See `check_enum_values`.
PROSE_SCOPE_WINDOW = 40
# Fields whose values are free-form data, not a closed vocabulary. Enumerating
# a `name` or a `type` at one site says nothing about the next site.
ENUM_FIELD_DENYLIST = {
    "name", "type", "uri", "path", "target", "operation", "handler", "id",
    "kind", "value", "key", "field", "resource", "reason", "message", "code",
    "format", "encoding", "scheme", "host", "url", "prefix", "suffix",
}


class Finding:
    __slots__ = ("rule", "line", "text")

    def __init__(self, rule: str, line: int, text: str):
        self.rule = rule
        self.line = line
        self.text = text

    def severity(self) -> str:
        return RULES[self.rule][0]


class CouldNotLook(Exception):
    pass


def iter_specs(root: Path):
    if root.is_file():
        yield root
        return
    for p in sorted(root.rglob("*.md")):
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        if p.name in EXCLUDE_FILES:
            continue
        yield p


def fenced_lines(text: str):
    """Yield (lineno, line, in_fence) for every line, tracking ``` fences."""
    in_fence = False
    for i, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            yield i, line, "fence-marker"
            continue
        yield i, line, in_fence


def collect_definitions(specs: List[Tuple[Path, str]]) -> Set[str]:
    """Every pseudocode helper the corpus defines, corpus-wide.

    Corpus-wide and not per-file on purpose: a helper defined in the SDK spec
    and invoked from an extension is defined. The rule is about a name with no
    definition *anywhere*, which is the only version of it that is certainly a
    defect.
    """
    defs: Set[str] = set()
    for _, text in specs:
        for _, line, fence in fenced_lines(text):
            if fence is not True:
                continue
            m = DEF_RE.match(line)
            if m:
                defs.add(m.group(1))
    return defs


def check_undefined_referents(text: str, defs: Set[str]) -> List[Finding]:
    out: List[Finding] = []
    for i, line, fence in fenced_lines(text):
        if fence is not True:
            continue
        s = line.lstrip()
        if s.startswith(";") or s.startswith("#"):   # pseudocode comment
            continue
        m = FIELD_ASSIGN_RE.match(line)
        if not m:
            continue
        target, helper = m.group(1), m.group(2)
        if helper in defs:
            continue
        out.append(Finding(
            "undefined-wire-referent", i,
            "`%s` is assigned from `%s()`, which the corpus never defines — "
            "define it or name the section that does" % (target, helper)))
    return out


def collect_enum_declarations(text: str) -> Dict[Tuple[str, str], Set[str]]:
    """(type, field) -> declared values, from the type blocks in this file.

    **Keyed by type, not by field alone**, and that is load-bearing. One spec
    routinely declares `status` on several result types with disjoint
    vocabularies — `system/relay/forward-result` has
    `"forwarded" | "queued-fallback" | "rejected"` while
    `system/relay/put-result` has `"stored"`, and neither is wrong. A
    field-keyed version of this rule reports that pair, and a gate whose first
    output is a false positive on a correct spec is a gate that gets switched
    off. Type-scoping costs some reach (see `check_enum_values`) and buys the
    precision the rule needs to survive.

    Same-file only, for the same reason: a `status` in one extension says
    nothing about a `status` in another.
    """
    decls: Dict[Tuple[str, str], Set[str]] = {}
    current: Optional[str] = None
    for _, line, fence in fenced_lines(text):
        if fence == "fence-marker":
            current = None          # a new block starts with no type context
            continue
        if fence is not True:
            continue
        m = TYPE_CTX_RE.match(line) or TYPE_DEF_RE.match(line)
        if m:
            current = m.group(1)
            continue
        if current is None:
            continue
        m = ENUM_DECL_RE.match(line)
        if not m:
            continue
        field = m.group(1)
        if field in ENUM_FIELD_DENYLIST:
            continue
        decls.setdefault((current, field), set()).update(ENUM_ALT_RE.findall(m.group(2)))
    return decls


def check_enum_values(text: str, decls: Dict[Tuple[str, str], Set[str]]) -> List[Finding]:
    """Flag a `field: "value"` whose (type, field) declaration omits `value`.

    A use site's type comes from the enclosing block's `type:` line, or — for
    prose and tables, which is where operation tables live — from a type name
    mentioned on the same line. The table row that produced the defect this
    rule was built for reads

        | `deny-request` | … | `system/registry/register-result` `{status: "denied"}` | … |

    so the mention *is* the scope. A use site naming no type is not checked:
    guessing its type is how the field-keyed version generated its false
    positives.
    """
    if not decls:
        return []
    out: List[Finding] = []
    seen: Set[Tuple[str, str, str]] = set()
    current: Optional[str] = None
    for i, line, fence in fenced_lines(text):
        if fence == "fence-marker":
            current = None
            continue
        if fence is True:
            m = TYPE_CTX_RE.match(line) or TYPE_DEF_RE.match(line)
            if m:
                current = m.group(1)
                continue
            if ENUM_DECL_RE.match(line):    # the declaration itself
                continue
            scoped = ([(current, m.group(1), m.group(2))
                       for m in ENUM_USE_RE.finditer(line)] if current else [])
        else:
            # Prose / table line: the type mention scopes only the values that
            # sit next to it. `…register-result` `{status: "bound"}` binds; the
            # `status: "approved"` forty characters further along the same row
            # is describing a *different* entity and must not bind to it. The
            # window is what keeps this path at zero false positives on the
            # corpus — without it the §6a.9.3 operations table reports its own
            # correct `approved` effect as a violation.
            scoped = []
            for tm in TYPE_MENTION_RE.finditer(line):
                for um in ENUM_USE_RE.finditer(line):
                    gap = um.start() - tm.end()
                    if 0 <= gap <= PROSE_SCOPE_WINDOW:
                        scoped.append((tm.group(1), um.group(1), um.group(2)))
        for scope, field, value in scoped:
            allowed = decls.get((scope, field))
            if not allowed or value in allowed:
                continue
            if (scope, field, value) in seen:
                continue
            seen.add((scope, field, value))
            out.append(Finding(
                "enum-value-not-declared", i,
                "`%s` emits `%s: \"%s\"`, but its declared enumeration is "
                "%s — extend the declaration or correct the emission"
                % (scope, field, value,
                   " | ".join('"%s"' % v for v in sorted(allowed)))))
    return out


def analyze(text: str, defs: Set[str]) -> List[Finding]:
    findings = check_undefined_referents(text, defs)
    findings += check_enum_values(text, collect_enum_declarations(text))
    return sorted(findings, key=lambda f: (f.line, f.rule))


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(Path.cwd()))
    except ValueError:
        return str(p)


def run_check(roots: List[Path], as_json: bool) -> int:
    specs: List[Tuple[Path, str]] = []
    for root in roots:
        for spec in iter_specs(root):
            try:
                specs.append((spec, spec.read_text(encoding="utf-8")))
            except Exception as exc:  # noqa: BLE001
                print("unreadable: %s: %s" % (rel(spec), exc), file=sys.stderr)

    # A gate that scanned nothing has not passed — it did not look. Same
    # three-valued contract as `standards` and `style`; 2 is not 0 and not 1.
    if not specs:
        print("no spec found under: %s" % ", ".join(str(r) for r in roots), file=sys.stderr)
        print("  scanned 0 files — this is not a pass, it is a gate that did not look.",
              file=sys.stderr)
        print("  point it at a corpus: --root PATH, `spec --corpus PATH coherence`,"
              " $SPEC_CORPUS, or run from the corpus root.", file=sys.stderr)
        return 2

    defs = collect_definitions(specs)
    report: Dict[str, List[Finding]] = {}
    for spec, text in specs:
        f = analyze(text, defs)
        if f:
            report[rel(spec)] = f

    n_error = sum(1 for fs in report.values() for x in fs if x.severity() == "error")

    if as_json:
        out = {rp: [{"rule": x.rule, "severity": x.severity(), "line": x.line, "text": x.text}
                    for x in fs] for rp, fs in report.items()}
        print(json.dumps({"summary": {"errors": n_error, "files": len(report),
                                      "scanned": len(specs), "definitions": len(defs)},
                          "findings": out}, indent=2))
        return 1 if n_error else 0

    for rp in sorted(report):
        print("\n%s  (%d error)" % (rp, len(report[rp])))
        for x in report[rp]:
            print("  ERROR  %-26s %s:%d  %s" % (x.rule, rp, x.line, x.text))

    print("\nscanned %d spec(s), %d pseudocode definition(s) — %d file(s) flagged, %d error(s)."
          % (len(specs), len(defs), len(report), n_error))
    return 1 if n_error else 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", action="append", type=Path,
                    help="spec dir or single .md file (repeatable)")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)
    return run_check(args.root or [DEFAULT_ROOT], args.json)


if __name__ == "__main__":
    raise SystemExit(main())
