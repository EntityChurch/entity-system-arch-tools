#!/usr/bin/env python3
"""vocab self-test — the app-tier vocabulary join, both directions.

Fixture corpora and fixture seat trees, so a live-corpus conversion never makes
this stale.

**Four of these assertions exist because the first working build of the analyzer
got them wrong on the live trees, and each is a shape this toolkit has now been
bitten by more than once.**

1. **A path prefix is not a type tag.** `entity-workbench-go` declares
   `ShareOfferPrefix = "app/share/records/"` — a TREE PATH. The first run
   stripped the trailing slash and reported `app/share/records` as an undeclared
   vocabulary item, i.e. accused a seat of inventing a tag out of its own
   directory name. A type tag never ends in a slash.

2. **A parametric declaration declares a FAMILY.** `APP-CONVENTION-EMBED`'s tag
   is `app/embed/{media_type}`; `app/embed/markdown` appears only as an example.
   Without open-family support the analyzer calls a conformant
   `app/embed/image/png` undeclared — **a false accusation against a correct
   seat, which is the expensive direction.**

3. **A counter-example is not a declaration.** `APP-CONVENTION-SHARE` §2 says
   *"a tag under one application's prefix (`app/entity-browser/share`) makes
   browser↔go aggregation impossible"*. An occurrence-counting matcher reads
   that as the corpus blessing the exact tag it forbids.

4. **A test fixture is not an emission.** A throwaway `"app/share/manifest"` in a
   subscription test must not make a one-seat migration look like two.

And the finding the analyzer exists for — `divergent-family` — is asserted in
**both** directions: it fires when two seats share no tags in a family, and it
stays silent the moment they share one.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vocab  # noqa: E402

FAILURES = []


def ok(name, cond, extra=""):
    if cond:
        print("  ok   %s" % name)
    else:
        FAILURES.append(name)
        print("  FAIL %s %s" % (name, extra))


SHARE_SPEC = """# APP-CONVENTION-SHARE

## 2. Type vocabulary

| Type | Role |
|---|---|
| `app/share/record` | the share itself |
| `app/share/publication` | a share with no audience |

A tag under one application's prefix (`app/entity-browser/share`) makes
cross-impl aggregation impossible even with a perfect mirror.

```cddl
share-record = {
  type: "app/share/record",
  data: { title: tstr }
}
```
"""

SITE_SPEC = """# APP-CONVENTION-SEMANTIC-CONTENT-SITE

```cddl
site-manifest = {                            ; type = app/site-manifest
  title: tstr
}
```
"""

EMBED_SPEC = """# APP-CONVENTION-EMBED

```cddl
; type = "app/embed/" .cat media-type        ; e.g. app/embed/image/png
```
"""


def build(specs, seats):
    """(corpus_root, cleanup) with sibling seat trees beside it."""
    tmp = tempfile.TemporaryDirectory()
    base = Path(tmp.name)
    corpus = base / "corpus"
    (corpus / "specs" / "applications").mkdir(parents=True)
    for name, text in specs.items():
        (corpus / "specs" / "applications" / name).write_text(text)
    for seat, files in seats.items():
        for rel, text in files.items():
            p = base / seat / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
    return corpus, tmp


def run(specs, seats, app_seats=("seat-a", "seat-b"), prefix=None):
    corpus, tmp = build(specs, seats)
    old_seats, old_app = vocab._seats, vocab._app_tier
    vocab._seats = lambda: {                                  # noqa: SLF001
        "seat-a": {"path": "seat-a", "source": ["*.rs"], "skip": []},
        "seat-b": {"path": "seat-b", "source": ["*.go"], "skip": []},
    }
    vocab._app_tier = lambda: list(app_seats)                 # noqa: SLF001
    try:
        return vocab.scan(corpus, prefix)
    finally:
        vocab._seats, vocab._app_tier = old_seats, old_app    # noqa: SLF001
        tmp.cleanup()


def kinds(res):
    return res.get("findings", {})


def tags(res, kind):
    return sorted(i.get("tag", "") for i in kinds(res).get(kind, []))


def main() -> int:
    print("vocab self-test")

    # -- 1. the divergent-family finding, POSITIVE ---------------------------
    _c, res = run(
        {"SHARE.md": SHARE_SPEC},
        {"seat-a": {"share.rs": 'pub const T: &str = "app/share/manifest";'},
         "seat-b": {"share.go": 'const T = "app/share/record"'}})
    div = kinds(res).get("divergent-family", [])
    ok("divergent-family fires when two seats share no tags in a family",
       len(div) == 1 and div[0]["family"] == "share", div)

    # -- 2. the same finding, NEGATIVE --------------------------------------
    _c, res = run(
        {"SHARE.md": SHARE_SPEC},
        {"seat-a": {"share.rs": 'const A: &str = "app/share/record";'},
         "seat-b": {"share.go": 'const B = "app/share/record"\nconst C = "app/share/publication"'}})
    ok("divergent-family stays SILENT the moment one tag is shared",
       not kinds(res).get("divergent-family"), kinds(res))

    # -- 3. a path prefix is not a type tag ---------------------------------
    _c, res = run(
        {"SHARE.md": SHARE_SPEC},
        {"seat-a": {"share.rs": 'const T: &str = "app/share/record";'},
         "seat-b": {"share.go": 'const P = "app/share/records/"\nconst T = "app/share/record"'}})
    ok("a trailing-slash literal is a TREE PATH and is never a tag",
       "app/share/records" not in tags(res, "implemented-undeclared"),
       tags(res, "implemented-undeclared"))

    # -- 4. a parametric declaration declares the family --------------------
    _c, res = run(
        {"EMBED.md": EMBED_SPEC},
        {"seat-a": {"e.rs": 'const T: &str = "app/embed/image/png";'},
         "seat-b": {"e.go": 'const T = "app/embed/image/png"'}})
    ok("an open family (`app/embed/{media_type}`) declares its members",
       "app/embed/image/png" not in tags(res, "implemented-undeclared"),
       tags(res, "implemented-undeclared"))
    ok("the open family is REPORTED as open, not silently absorbed",
       bool(res["families"].get("embed", {}).get("open")), res["families"])

    # -- 5. a counter-example in prose is not a declaration -----------------
    _c, res = run(
        {"SHARE.md": SHARE_SPEC},
        {"seat-a": {"s.rs": 'const T: &str = "app/entity-browser/share";'},
         "seat-b": {"s.go": 'const T = "app/share/record"'}})
    ok("the tag a spec forbids by example is not counted as declared",
       "app/entity-browser/share" not in tags(res, "declared-unimplemented"),
       tags(res, "declared-unimplemented"))

    # -- 6. a private application namespace is not a divergence -------------
    ok("a seat's own `app/<its-name>/*` namespace raises no finding",
       "app/entity-browser/share" not in tags(res, "implemented-undeclared"),
       tags(res, "implemented-undeclared"))

    # -- 7. a test fixture is not an emission -------------------------------
    _c, res = run(
        {"SHARE.md": SHARE_SPEC},
        {"seat-a": {"s.rs": 'const T: &str = "app/share/record";'},
         "seat-b": {"sub_test.go": 'x := "app/share/manifest"'}})
    ok("a tag only in `*_test.go` does not count as implemented",
       "app/share/manifest" not in tags(res, "implemented-undeclared"),
       tags(res, "implemented-undeclared"))

    _c, res = run(
        {"SHARE.md": SHARE_SPEC},
        {"seat-a": {"s.rs": 'const T: &str = "app/share/record";\n'
                            '#[cfg(test)]\nmod tests {\n'
                            '  const X: &str = "app/share/manifest";\n}\n'},
         "seat-b": {"s.go": 'const T = "app/share/record"'}})
    ok("a tag only inside a Rust `#[cfg(test)]` module does not count",
       "app/share/manifest" not in tags(res, "implemented-undeclared"),
       tags(res, "implemented-undeclared"))

    # -- 8. CDDL-comment declarations are found -----------------------------
    _c, res = run(
        {"SITE.md": SITE_SPEC},
        {"seat-a": {"s.rs": 'const T: &str = "app/site-manifest";'},
         "seat-b": {"s.go": 'const T = "app/site-manifest"'}})
    ok("`; type = app/site-manifest` counts as a declaration",
       "app/site-manifest" not in tags(res, "implemented-undeclared"),
       tags(res, "implemented-undeclared"))
    ok("a hyphenated site tag lands in the `site` family, not `site-manifest`",
       "site" in res["families"], list(res["families"]))

    # -- 9. single-seat ------------------------------------------------------
    _c, res = run(
        {"SHARE.md": SHARE_SPEC},
        {"seat-a": {"s.rs": 'const T: &str = "app/share/record";'},
         "seat-b": {"s.go": '// nothing here'}})
    ok("single-seat fires on a declared tag only one seat emits",
       "app/share/record" in tags(res, "single-seat"), kinds(res))

    # -- 10. could-not-look is not a clean run ------------------------------
    code, res = run({"SHARE.md": SHARE_SPEC}, {}, app_seats=("seat-nowhere",))
    ok("an absent seat tree is COULD-NOT-LOOK (2), never a clean 0",
       code == vocab.CANNOT_LOOK, code)
    ok("the missing seat is NAMED rather than dropped",
       "seat-nowhere" in res.get("missing_seats", []), res)

    # -- 11. --prefix scoping -----------------------------------------------
    _c, res = run(
        {"SHARE.md": SHARE_SPEC, "SITE.md": SITE_SPEC},
        {"seat-a": {"s.rs": 'const T: &str = "app/share/manifest";'},
         "seat-b": {"s.go": 'const T = "app/share/record"'}},
        prefix="site")
    ok("--prefix scopes the run to one family",
       not kinds(res).get("divergent-family"), kinds(res))

    print()
    if FAILURES:
        print("FAILED: %s" % ", ".join(FAILURES))
        return 1
    print("vocab self-test: all assertions pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
