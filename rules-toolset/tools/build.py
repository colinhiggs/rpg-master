# build.py - the command line over rulesc.
#
#   <ruleset>/build/book.html      long-form, in include order
#   <ruleset>/build/snippets.json  per-document short form for in-game use
#   <ruleset>/build/mechanics.json pure data, no prose - what the server runs on
#
# A ruleset may carry a VERSION file (MAJOR.MINOR.PATCH) at its root.
# If it does, all three outputs are stamped with it, so that anything
# built on the ruleset can record which version it was checked against.
#
# The toolset is generic - it knows nothing about "demo" or "ico"
# specifically. A ruleset is any directory containing a rules/ and a
# book/ subdirectory; which one to build is a command-line argument,
# not something hardcoded here, because the whole point of splitting
# rules-toolset/ from rules/<name>/ is that one toolset serves every
# ruleset.
#
# Usage, from rules-toolset/:
#   python3 tools/build.py demo          # builds the installed demo ruleset
#   python3 tools/build.py ico           # finds ico wherever it lives
#   python3 tools/build.py --path /any/other/ruleset/dir
#
# Run this after ANY edit to a ruleset's rules/ or book/. Nothing
# downstream is hand-edited; if you find yourself wanting to tweak
# book.html directly, the change belongs in a source document instead.
#
# The compiler itself lives in the rulesc package beside this
# directory, so a second compiler can import it without importing this
# file. See CORPUS.md.

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rulesc import (
    IncludeCycleError, RuleError,
    RULESET_SEARCH_PATH, BOOK_ROOT,
    compile_docs, lint, read_version, resolve_ruleset_dir,
    build_book, build_mechanics, build_snippets,
)

def main():
    parser = argparse.ArgumentParser(
        description="Compile a ruleset's rules/ + book/ into book.html, snippets.json, mechanics.json."
    )
    parser.add_argument(
        "ruleset", nargs="?", default="demo",
        help="Ruleset name, looked up in %s then %s (e.g. 'demo', 'ico'). "
             "Default: demo." % RULESET_SEARCH_PATH,
    )
    parser.add_argument(
        "--path", default=None,
        help="Explicit path to a ruleset directory (containing rules/ and book/), overrides the name.",
    )
    args = parser.parse_args()

    ruleset_dir, where = resolve_ruleset_dir(args)
    if ruleset_dir is None:
        print("FATAL: no ruleset '%s' found. Looked in:" % args.ruleset)
        for root in RULESET_SEARCH_PATH:
            print("  %s" % root)
        print("Use --path to build a ruleset somewhere else entirely.")
        return 1
    rules_dir = ruleset_dir / "rules"
    book_dir = ruleset_dir / "book"
    build_dir = ruleset_dir / "build"

    if not ruleset_dir.exists():
        print(f"FATAL: ruleset directory not found: {ruleset_dir}")
        return 1
    if not rules_dir.exists() and not book_dir.exists():
        print(f"FATAL: {ruleset_dir} has neither a rules/ nor a book/ subdirectory — "
              "is this a ruleset directory?")
        return 1

    build_dir.mkdir(exist_ok=True)

    try:
        version = read_version(ruleset_dir)
    except RuleError as e:
        print(f"FATAL: {e}")
        return 1

    try:
        docs, compiled, errors = compile_docs(rules_dir, book_dir, root_id=BOOK_ROOT)
    except IncludeCycleError as e:
        # Loud and specific: this one can't be worked around, and the
        # message names the exact chain to break.
        print(f"FATAL: {e}")
        return 1
    except RuleError as e:
        print(f"FATAL: {e}")
        return 1

    warnings, lint_errors = lint.run_all(docs, root_id=BOOK_ROOT)
    all_errors = errors + lint_errors

    for w in warnings:
        print(f"  warning: {w}")
    for e in all_errors:
        print(f"  ERROR:   {e}")

    if all_errors:
        print(f"\nBuild FAILED: {len(all_errors)} error(s). No output written.")
        return 1

    book_size, order = build_book(docs, compiled, build_dir / "book.html", version=version)
    n_snippets = build_snippets(docs, compiled, build_dir / "snippets.json", version=version)
    n_mech = build_mechanics(docs, build_dir / "mechanics.json", version=version)

    print(f"\nBuilt '{ruleset_dir.name}' {version or '(unversioned)'} from {len(docs)} documents"
          + (f" ({len(warnings)} warning(s))" if warnings else "")
          + f"\n  source: {ruleset_dir} ({where})")
    print(f"  {build_dir}/book.html      {book_size:,} bytes, {len(order)} documents in include order")
    print(f"  {build_dir}/snippets.json  {n_snippets} snippets")
    print(f"  {build_dir}/mechanics.json {n_mech} documents with mechanics")
    return 0


if __name__ == "__main__":
    sys.exit(main())
