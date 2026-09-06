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
    IncludeCycleError, Profile, RuleError,
    build_target, check_target_links, compile_corpus, lint, read_version,
    resolve_ruleset_dir, search_path,
)


def main():
    parser = argparse.ArgumentParser(
        description="Compile a ruleset into the outputs its corpus profile declares "
                    "(by default book.html, snippets.json and mechanics.json)."
    )
    parser.add_argument(
        "ruleset", nargs="?", default="demo",
        help="Ruleset name, looked up in the installed and working ruleset "
             "directories and in anything on $RULESET_PATH (e.g. 'demo', 'ico'). "
             "Default: demo.",
    )
    parser.add_argument(
        "--path", default=None,
        help="Explicit path to a ruleset directory (containing rules/ and book/), overrides the name.",
    )
    parser.add_argument(
        "--target", action="append", default=None, metavar="NAME",
        help="Build only this target. Repeatable. Default: every target the "
             "corpus profile declares.",
    )
    args = parser.parse_args()

    ruleset_dir, where = resolve_ruleset_dir(args)
    if ruleset_dir is None:
        print("FATAL: no ruleset '%s' found. Looked in:" % args.ruleset)
        for root, label in search_path():
            print("  %s (%s)" % (root, label))
        print("Use --path to build a ruleset somewhere else entirely, or put its "
              "parent directory on $RULESET_PATH.")
        return 1
    rules_dir = ruleset_dir / "rules"
    book_dir = ruleset_dir / "book"

    if not ruleset_dir.exists():
        print(f"FATAL: ruleset directory not found: {ruleset_dir}")
        return 1
    if not rules_dir.exists() and not book_dir.exists():
        print(f"FATAL: {ruleset_dir} has neither a rules/ nor a book/ subdirectory — "
              "is this a ruleset directory?")
        return 1

    try:
        version = read_version(ruleset_dir)
        profile = Profile.load(ruleset_dir)
    except RuleError as e:
        print(f"FATAL: {e}")
        return 1

    unknown = set(args.target or ()) - set(profile.targets)
    if unknown:
        print("FATAL: no target %s in this corpus (it has %s)"
              % (", ".join(sorted(unknown)), ", ".join(sorted(profile.targets))))
        return 1
    wanted = args.target or list(profile.targets)

    try:
        corpus = compile_corpus(rules_dir, book_dir, profile=profile,
                                base_dir=ruleset_dir, version=version)
    except IncludeCycleError as e:
        # Loud and specific: this one can't be worked around, and the
        # message names the exact chain to break.
        print(f"FATAL: {e}")
        return 1
    except RuleError as e:
        print(f"FATAL: {e}")
        return 1

    lint_warnings, lint_errors = lint.run_all(corpus.docs, profile)
    warnings = corpus.warnings + lint_warnings + check_target_links(corpus)
    all_errors = corpus.errors + lint_errors

    for w in warnings:
        print(f"  warning: {w}")
    for e in all_errors:
        print(f"  ERROR:   {e}")

    if all_errors:
        print(f"\nBuild FAILED: {len(all_errors)} error(s). No output written.")
        return 1

    written = []
    for name in wanted:
        target = profile.targets[name]
        if not target.output:
            print(f"  skipped '{name}': the profile declares no output path for it")
            continue
        out_path = ruleset_dir / target.output
        try:
            result = build_target(corpus, name, out_path=out_path)
        except RuleError as e:
            print(f"FATAL: target '{name}': {e}")
            return 1
        if target.shape == "book":
            size, order = result
            detail = f"{size:,} bytes, {len(order)} documents in include order"
        elif target.shape == "snippets":
            detail = f"{result} snippets"
        else:
            detail = f"{result} documents with data"
        written.append((out_path, detail))

    n_local = len(corpus.local())
    print(f"\nBuilt '{ruleset_dir.name}' {version or '(unversioned)'} from {n_local} documents"
          + (f" ({len(warnings)} warning(s))" if warnings else "")
          + f"\n  source: {ruleset_dir} ({where})")
    for meta in corpus.references:
        print("  against: %s %s (%s)"
              % (meta["name"], meta["version"] or "unversioned", meta["source"]))
    width = max((len(str(p)) for p, _ in written), default=0)
    for out_path, detail in written:
        print(f"  {str(out_path).ljust(width)}  {detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
