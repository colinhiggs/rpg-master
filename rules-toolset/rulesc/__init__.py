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
    INCLUDE_RE, Corpus, Doc, IncludeCycleError, RuleError,
    apply_audiences, compile_corpus, compile_docs, compile_rules,
    detect_cycles, include_order, links_in, load_docs, load_reference,
    merge_block, render_markdown, strip_absent_links,
)
from .profile import DROP, KEEP, Kind, Profile, Reference, Target
from .lookup import (
    INSTALLED_RULESETS, RULESET_PATH_ENV, RULESET_SEARCH_PATH, TOOLSET_ROOT,
    WORKING_RULESETS, find_ruleset, read_version, resolve_ruleset_dir, search_path,
)
from .runtime import Mechanics, RulesNotBuilt, load_ruleset
from .targets import (
    BOOK_CSS, BOOK_ROOT,
    build_book, build_data, build_snippets, build_target, check_target_links,
    related_for, rendered_ids, snippet_html, text_for,
)

__all__ = [
    "lint",
    # documents and compiling
    "INCLUDE_RE", "Corpus", "Doc", "IncludeCycleError", "RuleError",
    "apply_audiences", "compile_corpus", "compile_docs", "compile_rules",
    "detect_cycles", "include_order", "links_in", "load_docs", "load_reference",
    "merge_block", "render_markdown", "strip_absent_links",
    # what a corpus declares about itself
    "DROP", "KEEP", "Kind", "Profile", "Reference", "Target",
    # finding a ruleset on disk
    "INSTALLED_RULESETS", "RULESET_PATH_ENV", "RULESET_SEARCH_PATH", "TOOLSET_ROOT",
    "WORKING_RULESETS", "find_ruleset", "read_version", "resolve_ruleset_dir",
    "search_path",
    # reading a built ruleset back, for something that plays it
    "Mechanics", "RulesNotBuilt", "load_ruleset",
    # writing output
    "BOOK_CSS", "BOOK_ROOT", "build_book", "build_data", "build_snippets",
    "build_target", "check_target_links", "related_for", "rendered_ids",
    "snippet_html", "text_for",
]
