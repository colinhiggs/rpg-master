# rulesc - the rules compiler, as an importable package.
#
# This module is the public surface. A second compiler - the adventure
# compiler in the ico-adventures project is the first - imports from
# here rather than reaching into the modules below, so that the layout
# inside the package can change without breaking it.
#
# From a project holding this repository as a submodule at
# rpg-master/, that is one line of path setup and then an ordinary
# import:
#
#     import sys
#     from pathlib import Path
#     sys.path.insert(0, str(Path(__file__).resolve().parents[1]
#                            / "rpg-master" / "rules-toolset"))
#
#     from rulesc import Profile, compile_corpus, build_target
#
# There is no way around the path line without an install step, and
# this project deliberately has no dependencies to install. What the
# package buys is that the line is written once and imports a stated
# API, rather than putting tools/ on the path and pulling build, lint
# and test_rules into the caller's namespace.
#
# See CORPUS.md for the profile format and the compile/build calls.

from . import lint
from .compile import (
    INCLUDE_RE, Doc, IncludeCycleError, RuleError,
    compile_docs, compile_rules, detect_cycles, include_order,
    load_docs, render_markdown,
)
from .lookup import (
    INSTALLED_RULESETS, RULESET_SEARCH_PATH, TOOLSET_ROOT, WORKING_RULESETS,
    find_ruleset, read_version, resolve_ruleset_dir,
)
from .targets import (
    BOOK_CSS, BOOK_ROOT,
    build_book, build_mechanics, build_snippets,
)

__all__ = [
    "lint",
    "INCLUDE_RE", "Doc", "IncludeCycleError", "RuleError",
    "compile_docs", "compile_rules", "detect_cycles", "include_order",
    "load_docs", "render_markdown",
    "INSTALLED_RULESETS", "RULESET_SEARCH_PATH", "TOOLSET_ROOT", "WORKING_RULESETS",
    "find_ruleset", "read_version", "resolve_ruleset_dir",
    "BOOK_CSS", "BOOK_ROOT",
    "build_book", "build_mechanics", "build_snippets",
]
