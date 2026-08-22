#!/usr/bin/env python3
"""config — the single source of truth for the spec toolkit.

Loads the bundled `config.default.toml` (and an optional `--config` override),
resolving the corpus knowledge — roots, excludes, vocabulary, document classes,
analyzer policy — that used to be hardcoded constants scattered across the five
tools. A different corpus is a different config file; the code is one.

Stdlib-only. `tomllib` is stdlib since 3.11 (the containers pin python:3.12).
"""

import fnmatch
import os
import tomllib
from pathlib import Path
from typing import Dict, List, Optional, Set

# Where the TOOL lives (spec-tool/config.py -> parents[2] == this repo's root).
# Pre-split this doubled as the corpus root, because tool and corpus shared one
# repo. They no longer do: this repo carries no corpus (see AGENTS.md), so the
# corpus root is resolved separately — see `corpus_root()`.
TOOL_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = Path(__file__).resolve().parent / "config.default.toml"

CORPUS_ENV = "SPEC_CORPUS"


def corpus_root(explicit: Optional[Path] = None) -> Path:
    """The corpus this run analyzes. Precedence: explicit > $SPEC_CORPUS > cwd.

    **You point the tool at a corpus; the tool does not know where one is.**
    Deriving it from the tool's own location was correct only while the tool
    and the corpus shared a repo, and survived the split as a path to a
    directory that exists in no checkout — which made both gates run over an
    empty file set (`standards` reported PASS on zero files; `check` reported
    `style=fail`, laundering *could not look* into *looked and failed*).
    Defaulting to the working directory matches how the gate is actually
    invoked: from inside the corpus, or with it bind-mounted at the workdir.
    """
    if explicit is not None:
        return Path(explicit).resolve()
    env = os.environ.get(CORPUS_ENV)
    if env:
        return Path(env).resolve()
    return Path.cwd().resolve()


# Backwards-compatible alias. Modules that anchor *display* paths (not
# discovery) still import this; they should prefer `Config.repo_root`.
REPO_ROOT = TOOL_ROOT


def find_markdown(root: Path, exclude_dirs: Set[str], exclude_files: Set[str]) -> List[Path]:
    """The one corpus scan. Sorted, dir-segment + filename excluded.

    Unifies spec-standards' `rglob`+parts-check, spec-topology's
    `rglob`+relative-parts-check, and spec-style's `os.walk`+prune — all three
    sorted the same set, so this reproduces every one (verified by parity).
    """
    out: List[Path] = []
    if root.is_file():
        if root.suffix == ".md" and root.name not in exclude_files:
            out.append(root)
        return out
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root).parts
        if any(seg in exclude_dirs for seg in rel[:-1]):
            continue
        if p.name in exclude_files:
            continue
        out.append(p)
    return out


class Scope:
    __slots__ = ("name", "root", "exclude_dirs", "exclude_files")

    def __init__(self, name: str, root: Path, exclude_dirs: Set[str], exclude_files: Set[str]):
        self.name = name
        self.root = root
        self.exclude_dirs = exclude_dirs
        self.exclude_files = exclude_files

    def find_markdown(self) -> List[Path]:
        return find_markdown(self.root, self.exclude_dirs, self.exclude_files)


class Config:
    def __init__(self, data: dict, repo_root: Optional[Path] = None):
        self._d = data
        self.repo_root = corpus_root() if repo_root is None else Path(repo_root).resolve()
        self.corpus_dir = (self.repo_root / data["corpus"]["repo_root"]).resolve()
        voc = data.get("vocabulary", {})
        self.type_roots: Set[str] = set(voc.get("type_roots", []))
        self.doc_families: Set[str] = set(voc.get("doc_families", []))
        self.canonical_status: Set[str] = set(voc.get("canonical_status", []))
        # Prose nickname -> canonical DOC stem ("" == self/ambiguous). (§11.2)
        self.nicknames: Dict[str, str] = dict(voc.get("nicknames", {}))
        # Doc-name family prefixes denoting a process/intent artifact (§11.3).
        self.intent_families: Set[str] = set(voc.get("intent_families", []))
        self.classes: dict = data.get("classes", {})

    def doc_class(self, stem: str) -> str:
        """Document class for a doc stem (canonical-spec | guide | arch-doc |
        intent). Glob overrides win; then the intent-family prefix; then the
        default. Grounds citation legitimacy per SPECIFICATION-FORMAT §11.3."""
        name = stem + ".md"
        for pat, cls in self.classes.items():
            if pat == "default":
                continue
            if fnmatch.fnmatch(name, pat):
                return cls
        if stem.split("-")[0] in self.intent_families:
            return "intent"
        return self.classes.get("default", "canonical-spec")

    def scope(self, name: str) -> Scope:
        s = self._d["scope"][name]
        return Scope(
            name=name,
            root=self.corpus_dir / s["root"],
            exclude_dirs=set(s.get("exclude_dirs", [])),
            exclude_files=set(s.get("exclude_files", [])),
        )

    def analyzer(self, name: str) -> dict:
        return self._d.get("analyzer", {}).get(name, {})

    def analyzer_scope(self, name: str) -> Scope:
        return self.scope(self.analyzer(name)["scope"])


def load(config_path: Optional[Path] = None, repo_root: Optional[Path] = None) -> Config:
    path = config_path or DEFAULT_CONFIG
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return Config(data, repo_root)


if __name__ == "__main__":
    import json
    import sys
    cfg = load(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
    print("repo_root  :", cfg.repo_root)
    print("corpus_dir :", cfg.corpus_dir)
    print("type_roots :", sorted(cfg.type_roots))
    for name in cfg._d.get("scope", {}):
        sc = cfg.scope(name)
        print("scope %-20s root=%s  files=%d" % (
            name, sc.root.relative_to(cfg.repo_root), len(sc.find_markdown())))
