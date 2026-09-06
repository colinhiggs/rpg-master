# targets.py - the output shapes.
#
# Three of them, and they are the interface between this toolset and
# everything downstream, so they are changed by agreement rather than
# in passing. See SHARING.md and CORPUS.md.
#
#   book      a long-form HTML document, in include order
#   snippets  a flat map of document id to short form, for in-game use
#   data      pure data - the declared blocks, no prose, no HTML
#
# A target names a shape and parameterises it. Which targets a corpus
# has is its profile's business, not this module's.

import json
from pathlib import Path

from .compile import (
    INCLUDE_RE, IncludeCycleError, RuleError,
    apply_audiences, include_order, render_markdown,
)

BOOK_ROOT = "rulebook"   # the document the book is built from, by default

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
table { border-collapse: collapse; margin: 18px 0; font-family: system-ui, sans-serif;
        font-size: 14px; width: 100%; display: block; overflow-x: auto; }
th, td { padding: 6px 12px 6px 0; border-bottom: 1px solid #2a2c36; text-align: left;
         vertical-align: top; white-space: nowrap; }
thead th { color: #fff; font-size: 11px; text-transform: uppercase;
           letter-spacing: .06em; border-bottom-color: #3a3d4a; }
tbody tr:last-child td { border-bottom: none; }
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


def _renderable(corpus, target):
    """This corpus's own documents that this target renders, in load
    order. Documents pulled in from a referenced corpus are readable and
    linkable but never rendered here, and a document its target filters
    out - or whose kind carries an audience this target drops - is not
    rendered either."""
    return [d for d in corpus.docs.values()
            if not d.external and target.selects(d, corpus.profile)]


def text_for(corpus, doc_id, target):
    """One document's resolved text with this target's audience policy
    applied, include directives still in place."""
    return apply_audiences(corpus.compiled[doc_id]["marked"], target, corpus.profile)


def snippet_html(corpus, doc_id, target=None):
    """The include-free, audience-resolved HTML a snippet carries.

    Offset 2: a standalone popup renders the title as <h3>, so the
    body's `##` should land on <h4>."""
    target = target or corpus.profile.target("snippets")
    return render_markdown(
        INCLUDE_RE.sub("", text_for(corpus, doc_id, target)), heading_offset=2)


def render_doc_for_book(doc_id, corpus, target, depth, stack):
    """Render one document and everything it includes, in place.

    The document's own prose is split on {% include %} directives so a
    chapter can have an intro, then a rule, then a linking paragraph,
    then another rule — the includes are positional, not appended.

    `stack` carries the include chain purely so a cycle that somehow got
    past detect_cycles() raises here instead of recursing forever."""
    if doc_id in stack:
        raise IncludeCycleError(stack[stack.index(doc_id):] + [doc_id])

    docs = corpus.docs
    doc = docs[doc_id]
    c = corpus.compiled[doc_id]
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
    segments = INCLUDE_RE.split(text_for(corpus, doc_id, target))
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
            include_id = segment.strip()
            if include_id in docs and target.selects(docs[include_id], corpus.profile) \
                    and not docs[include_id].external:
                parts.append(
                    render_doc_for_book(include_id, corpus, target, depth + 1,
                                        stack + [doc_id])
                )

    if depth > 0:
        # No mechanics table here on purpose. A data block exists to feed
        # the game server and to let the linter prove the prose has not
        # drifted from it -- both machine concerns. Every value it holds
        # is already interpolated into the prose above, so printing the
        # raw keys again would only restate the rule in a worse language.
        # The data target remains the readable form for anyone who wants
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


def _built_against(corpus) -> str:
    """A visible note naming every corpus this one was built against.

    A printed module should say which rules it holds without going near
    a repository, which is the same argument that put the version in the
    subtitle. A corpus that references nothing says nothing."""
    if not corpus.references:
        return ""
    named = ", ".join(f"{r['name']} {r['version'] or '(unversioned)'}"
                      for r in corpus.references)
    return f"Built against {named}. "


def build_book(corpus, target, out_path: Path, root: str = None):
    docs = corpus.docs
    root_id = root or target.root or (corpus.profile.roots[0] if corpus.profile.roots else None)
    if root_id is None:
        raise RuleError(
            f"target '{target.name}' is a book and has no root. Give the target a "
            "'root', give the corpus a 'roots', or pass one to build_target()."
        )
    if root_id not in docs:
        raise RuleError(
            f"book root '{root_id}' not found. Expected a document with that id "
            "carrying the {% include %} directives that order the book."
        )
    selected = {d.id for d in _renderable(corpus, target)}
    order = [(d, depth) for d, depth in include_order(docs, root_id) if d in selected]
    body = render_doc_for_book(root_id, corpus, target, depth=0, stack=[])
    toc = render_toc(order, docs)
    root_doc = docs[root_id]
    # Visible rather than buried in a comment: a Dungeon Master with the
    # book open should be able to see which rules they are reading
    # without going near a repository.
    stamp = f"Version {corpus.version}. " if corpus.version else ""

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{root_doc.title}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{target.css or BOOK_CSS}</style>
</head><body><div class="wrap">
<h1>{root_doc.title}</h1>
<p class="subtitle">{stamp}{_built_against(corpus)}Generated from rules/ and book/ — do not edit this file directly.</p>
<nav><p class="label">Contents</p>{toc}</nav>
{body}
<footer>Compiled from {len(selected)} source documents, ordered by the include tree
rooted at <code>{root_id}</code>. Every value shown above is interpolated from the
same data the game server reads.</footer>
</div></body></html>"""

    out_path.write_text(html, encoding="utf-8")
    return len(html), order


def build_snippets(corpus, target, out_path: Path):
    """Short form for in-game consumption: tooltips, context help,
    'what does this mean?' popups.

    Note the html here is the document WITHOUT its includes expanded —
    a popup for a chapter should not dump the whole chapter's rules into
    a tooltip. Each snippet carries `includes` so a client can offer
    them as onward links instead.

    The version sits at the top level beside the documents rather than
    in a wrapper, because wrapping would change the shape every existing
    consumer reads. The convention that pays for that is simple and
    applies to all the outputs: a top-level key beginning with `_` is
    metadata about the build, not a document. No document id can collide
    with one, because an id is a filename stem."""
    snippets = {}
    for doc in _renderable(corpus, target):
        c = corpus.compiled[doc.id]
        entry = {
            "id": doc.id,
            "kind": doc.kind,
            "title": doc.title,
            "summary": c["summary_resolved"],
            "summary_html": c["summary_html"],
            "html": snippet_html(corpus, doc.id, target),
            "tags": doc.tags,
            "related": sorted(doc.links_out),
            "includes": doc.includes,
            "book_anchor": f"#rule-{doc.id}",
        }
        # Both are absent unless the corpus uses them, so a ruleset's
        # snippets.json keeps exactly the shape it has always had.
        if doc.based_on:
            entry["based_on"] = doc.based_on
        if doc.links_external:
            entry["external"] = sorted(doc.links_external)
        snippets[doc.id] = entry
    payload = {"_version": corpus.version} if corpus.version else {}
    if corpus.references:
        payload["_references"] = corpus.references
    payload.update(snippets)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(snippets)


def build_data(corpus, target, out_path: Path):
    """Pure machine-readable data — no prose, no HTML. This is what the
    game server loads at startup. Keeping it prose-free means the server
    never accidentally depends on wording, and a copy-editing pass can
    never change game behaviour.

    One declared block is written straight in, which is what
    mechanics.json has always looked like and what every existing reader
    expects. Several are written under their names, and `_blocks` says
    so, so that a consumer reading this file can tell the two apart
    without being told."""
    blocks = tuple(target.blocks or ("mechanics",))
    single = len(blocks) == 1
    rules = {}
    for doc in sorted(corpus.docs.values(), key=lambda d: d.id):
        if doc.external or not target.selects(doc, corpus.profile):
            continue
        present = {name: doc.data[name] for name in blocks if doc.data.get(name)}
        if not present:
            continue
        rules[doc.id] = present[blocks[0]] if single else present

    payload = {"_generated": "Built from rules/*.md by tools/build.py - do not edit."}
    if corpus.version:
        payload["_version"] = corpus.version
    if not single:
        payload["_blocks"] = list(blocks)
    if corpus.references:
        payload["_references"] = corpus.references
    payload["rules"] = rules
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return len(rules)


SHAPES = {"book": build_book, "snippets": build_snippets, "data": build_data}


def build_target(corpus, name: str, out_path=None, base_dir=None, **kwargs):
    """Write one target of a corpus.

    `out_path` defaults to the target's declared `output`, resolved
    against `base_dir`. A driver that builds one adventure at a time
    passes the path instead: where an output goes is the driver's
    business, and templating a path would be this toolset holding an
    opinion about how a consumer lays out its build directory."""
    target = corpus.profile.target(name)
    if out_path is None:
        if not target.output:
            raise RuleError(
                f"target '{name}' declares no output path, so build_target() "
                "needs one passed to it")
        out_path = Path(base_dir or ".") / target.output
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return SHAPES[target.shape](corpus, target, out_path, **kwargs)
