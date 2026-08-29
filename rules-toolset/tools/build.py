# build.py — compiles a RULESET's documents into the three consumers.
#
#   <ruleset>/build/book.html      long-form, in include order
#   <ruleset>/build/snippets.json  per-document short form for in-game use
#   <ruleset>/build/mechanics.json pure data, no prose — what the server runs on
#
# The toolset (this file) is generic — it knows nothing about "demo" or
# "ico" specifically. A ruleset is any directory containing a rules/ and
# a book/ subdirectory; which one to build is a command-line argument,
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

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import lint
from rulesc import (
    INCLUDE_RE, IncludeCycleError, RuleError,
    compile_docs, include_order, render_markdown,
)

TOOLSET_ROOT = Path(__file__).parent.parent      # .../rpg-master/rules-toolset
BOOK_ROOT = "rulebook"   # the document the book is built from

# A ruleset can sit in either of two places, and the difference is what
# stage it is at rather than what it is:
#
#   INSTALLED  rpg-master/rules/<name>   dropped in to be played. This is
#                                        the plug-in directory the game
#                                        ships with, and it is inside the
#                                        software repository.
#   WORKING    ../rules/<name>           a ruleset being AUTHORED, in the
#                                        outer working directory, usually
#                                        its own repository (ico is).
#
# Installed wins when a name exists in both, so a dropped-in ruleset is
# what actually runs; --path overrides everything.
INSTALLED_RULESETS = TOOLSET_ROOT.parent / "rules"
WORKING_RULESETS = TOOLSET_ROOT.parent.parent / "rules"
RULESET_SEARCH_PATH = (INSTALLED_RULESETS, WORKING_RULESETS)


def find_ruleset(name: str):
    """Return (path, where) for a ruleset name, or (None, None)."""
    for root, where in zip(RULESET_SEARCH_PATH, ("installed", "working")):
        candidate = root / name
        if candidate.exists():
            return candidate, where
    return None, None


def resolve_ruleset_dir(args):
    if args.path:
        return Path(args.path), "path"
    return find_ruleset(args.ruleset)


BOOK_CSS = """
:root { color-scheme: dark; }
body {
  margin: 0; background: #14161c; color: #dfe1e8;
  font: 16px/1.65 Georgia, 'Iowan Old Style', serif;
}
.wrap { max-width: 720px; margin: 0 auto; padding: 48px 24px 120px; }
h1 { font-size: 34px; margin: 0 0 6px; color: #fff; }
.subtitle { color: #888; font-size: 14px; margin-bottom: 40px; font-family: system-ui, sans-serif; }
h2 { font-size: 27px; margin: 64px 0 6px; color: #fff; border-top: 1px solid #2a2c36; padding-top: 32px; }
h3 { font-size: 21px; margin: 40px 0 4px; color: #fff; }
h4 { font-size: 16px; margin: 26px 0 4px; color: #cfd2db; }
h5 { font-size: 14px; margin: 20px 0 4px; color: #aeb2bd; }
p { margin: 12px 0; }
a { color: #7aa7f0; text-decoration: none; border-bottom: 1px solid rgba(122,167,240,.35); }
a:hover { border-bottom-color: #7aa7f0; }
code { background: #1e2029; padding: 1px 5px; border-radius: 4px; font-size: 14px;
       font-family: ui-monospace, Menlo, monospace; color: #e6c07b; }
.broken-link { color: #f77; text-decoration: underline wavy; }
.doc { scroll-margin-top: 20px; }
.tags { font-family: system-ui, sans-serif; font-size: 11px; color: #6e7280;
        text-transform: uppercase; letter-spacing: .06em; margin: 6px 0 0; }
.summary { font-style: italic; color: #a8acb8; margin: 10px 0 18px;
           border-left: 2px solid #2f3341; padding-left: 14px; }
nav { font-family: system-ui, sans-serif; font-size: 14px; background: #1a1c23;
      border: 1px solid #2a2c36; border-radius: 10px; padding: 16px 20px; margin-bottom: 40px; }
nav .label { margin: 0 0 10px; font-size: 11px; text-transform: uppercase;
             letter-spacing: .06em; color: #6e7280; }
nav ol { margin: 0; padding-left: 20px; }
nav ol ol { padding-left: 18px; margin: 4px 0; }
nav li { margin: 5px 0; }
nav ol ol li { margin: 2px 0; font-size: 13px; }
.related { font-family: system-ui, sans-serif; font-size: 13px; color: #6e7280; margin-top: 18px; }
footer { margin-top: 80px; padding-top: 20px; border-top: 1px solid #2a2c36;
         font-family: system-ui, sans-serif; font-size: 12px; color: #5d616e; }
"""


def render_doc_for_book(doc_id, docs, compiled, depth, stack):
    """Render one document and everything it includes, in place.

    The document's own prose is split on {% include %} directives so a
    chapter can have an intro, then a rule, then a linking paragraph,
    then another rule — the includes are positional, not appended.

    `stack` carries the include chain purely so a cycle that somehow got
    past detect_cycles() raises here instead of recursing forever."""
    if doc_id in stack:
        raise IncludeCycleError(stack[stack.index(doc_id):] + [doc_id])

    doc = docs[doc_id]
    c = compiled[doc_id]
    parts = []

    # The root document's title becomes the book's <h1>, handled by the
    # page template — so it isn't emitted again here.
    if depth > 0:
        level = min(depth + 1, 6)
        parts.append(f'<section class="doc" id="rule-{doc.id}">')
        parts.append(f"<h{level}>{doc.title}</h{level}>")
        if doc.tags:
            parts.append(f'<p class="tags">{" · ".join(doc.tags)}</p>')
        if c["summary_resolved"]:
            parts.append(f'<p class="summary">{c["summary_html"]}</p>')

    # Split prose around the include points and interleave.
    segments = INCLUDE_RE.split(c["linked"])
    # re.split with one capture group alternates: prose, id, prose, id, ...
    for i, segment in enumerate(segments):
        if i % 2 == 0:
            if segment.strip():
                # offset = depth, so a `##` in a document at depth N
                # renders as h(2+N) — exactly one level below that
                # document's own title at h(1+N), with no gap. Skipped
                # heading levels break document outlines and screen
                # readers, so this arithmetic matters.
                parts.append(render_markdown(segment, heading_offset=depth))
        else:
            target = segment.strip()
            if target in docs:
                parts.append(
                    render_doc_for_book(target, docs, compiled, depth + 1, stack + [doc_id])
                )

    if depth > 0:
        # No mechanics table here on purpose. `mechanics:` exists to feed
        # the game server and to let the linter prove the prose has not
        # drifted from it -- both machine concerns. Every value it holds
        # is already interpolated into the prose above, so printing the
        # raw keys again would only restate the rule in a worse language.
        # mechanics.json remains the readable form for anyone who wants
        # the data itself.
        if doc.links_out:
            links = ", ".join(
                f'<a href="#rule-{t}">{docs[t].title}</a>' for t in sorted(doc.links_out)
            )
            parts.append(f'<p class="related">See also: {links}</p>')
        parts.append("</section>")

    return "\n".join(parts)


def render_toc(order, docs):
    """Nested contents list, built from the same include order as the
    body so the two can never disagree."""
    html = []
    prev_depth = 0
    for doc_id, depth in order:
        if depth == 0:
            continue  # the root is the book itself
        if depth > prev_depth:
            html.append("<ol>" * (depth - prev_depth))
        elif depth < prev_depth:
            html.append("</ol>" * (prev_depth - depth))
        html.append(f'<li><a href="#rule-{doc_id}">{docs[doc_id].title}</a></li>')
        prev_depth = depth
    html.append("</ol>" * prev_depth)
    return "".join(html)


def build_book(docs, compiled, out_path: Path, root_id=BOOK_ROOT):
    if root_id not in docs:
        raise RuleError(
            f"book root '{root_id}' not found. Expected book/{root_id}.md "
            "with the {% include %} directives that order the book."
        )
    order = include_order(docs, root_id)
    body = render_doc_for_book(root_id, docs, compiled, depth=0, stack=[])
    toc = render_toc(order, docs)
    root = docs[root_id]

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{root.title}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{BOOK_CSS}</style>
</head><body><div class="wrap">
<h1>{root.title}</h1>
<p class="subtitle">Generated from rules/ and book/ — do not edit this file directly.</p>
<nav><p class="label">Contents</p>{toc}</nav>
{body}
<footer>Compiled from {len(docs)} source documents, ordered by the include tree
rooted at <code>{root_id}</code>. Every value shown above is interpolated from the
same data the game server reads.</footer>
</div></body></html>"""

    out_path.write_text(html, encoding="utf-8")
    return len(html), order


def build_snippets(docs, compiled, out_path: Path):
    """Short form for in-game consumption: tooltips, context help,
    'what does this mean?' popups.

    Note the html here is the document WITHOUT its includes expanded —
    a popup for a chapter should not dump the whole chapter's rules into
    a tooltip. Each snippet carries `includes` so a client can offer
    them as onward links instead."""
    snippets = {}
    for doc in docs.values():
        c = compiled[doc.id]
        snippets[doc.id] = {
            "id": doc.id,
            "kind": doc.kind,
            "title": doc.title,
            "summary": c["summary_resolved"],
            "summary_html": c["summary_html"],
            "html": c["html"],
            "tags": doc.tags,
            "related": sorted(doc.links_out),
            "includes": doc.includes,
            "book_anchor": f"#rule-{doc.id}",
        }
    out_path.write_text(json.dumps(snippets, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(snippets)


def build_mechanics(docs, out_path: Path):
    """Pure machine-readable data — no prose, no HTML. This is what the
    game server loads at startup. Keeping it prose-free means the server
    never accidentally depends on wording, and a copy-editing pass can
    never change game behaviour."""
    mechanics = {
        doc.id: doc.mechanics
        for doc in sorted(docs.values(), key=lambda d: d.id)
        if doc.mechanics
    }
    payload = {
        "_generated": "Built from rules/*.md by tools/build.py - do not edit.",
        "rules": mechanics,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return len(mechanics)


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

    book_size, order = build_book(docs, compiled, build_dir / "book.html")
    n_snippets = build_snippets(docs, compiled, build_dir / "snippets.json")
    n_mech = build_mechanics(docs, build_dir / "mechanics.json")

    print(f"\nBuilt '{ruleset_dir.name}' from {len(docs)} documents"
          + (f" ({len(warnings)} warning(s))" if warnings else "")
          + f"\n  source: {ruleset_dir} ({where})")
    print(f"  {build_dir}/book.html      {book_size:,} bytes, {len(order)} documents in include order")
    print(f"  {build_dir}/snippets.json  {n_snippets} snippets")
    print(f"  {build_dir}/mechanics.json {n_mech} documents with mechanics")
    return 0


if __name__ == "__main__":
    sys.exit(main())
