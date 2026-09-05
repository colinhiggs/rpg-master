# rulesc.py — the rules compiler.
#
# ONE source of truth: rules/*.md and book/*.md. Each file is a single
# addressable document, with machine-readable values in YAML
# frontmatter and authored prose in the body. Everything else — the
# book, the in-game snippets, the data the server runs on — is BUILT
# from these, never edited directly.
#
# Two kinds of document, distinguished by `kind:` in frontmatter:
#   kind: rule     (default) a rule — has mechanics, appears in snippets
#   kind: creature a creature - a stat block, statted the same way a
#                  character is; behaves like a rule but is found
#                  through the bestiary rather than by cross-reference
#   kind: section  book structure — chapters, the root template
# Both live in the same id namespace and both can include either kind.
#
# Book ORDER comes from the include tree, not from a number in each
# file. book/rulebook.md includes chapters, chapters include rules, and
# a document can be included at any depth — so the flow of the book is
# readable in one place instead of reconstructed from scattered
# `spine:` values.
#
# The load-bearing constraint that makes all of this work: prose must
# never restate a number that lives in `mechanics`. It interpolates it
# with {{ mechanics.some_key }} instead. `lint.py` enforces this,
# because a hardcoded number in prose is exactly how a "single source
# of truth" silently becomes two sources that disagree.
#
# Syntax understood inside a document body:
#   {{ mechanics.key }}          value from THIS document's mechanics
#   {{ other-id:mechanics.key }} value from ANOTHER document's mechanics
#   [[other-id]]                 link (target's title used as text)
#   [[other-id|custom text]]     link with custom text
#   {% include other-id %}       splice another document in here
#   {% table mechanics.some_map columns=a,b %}
#                                a table built FROM mechanics, so that a
#                                tabulation of data cannot re-type it
#   {% table mechanics rows=dagger,sword columns=damage:Damage %}
#   {% book-only %}...{% endbook-only %}
#                                content for the long-form book ONLY --
#                                kept in book.html, dropped from the
#                                in-game snippet. Design notes and other
#                                commentary belong here: a reader wants
#                                the rule in a tooltip, not an argument
#                                about why the rule is that shape.

import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.S)
INTERP_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")
LINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]")
INCLUDE_RE = re.compile(r"\{\%\s*include\s+([A-Za-z0-9_-]+)\s*\%\}")
# Table directives may span lines, so that a long column list can stay
# inside the 72-column wrap the prose uses.
TABLE_RE = re.compile(r"\{\%\s*table\s+(.*?)\s*\%\}", re.S)
BOOK_ONLY_RE = re.compile(r"\{\%\s*book-only\s*\%\}(.*?)\{\%\s*endbook-only\s*\%\}", re.S)
BOOK_ONLY_TOKEN_RE = re.compile(r"\{\%\s*(book-only|endbook-only)\s*\%\}")

KINDS = ("rule", "section", "creature")
REQUIRED_FIELDS = ("id", "title")


class RuleError(Exception):
    pass


class IncludeCycleError(RuleError):
    """Raised when the include graph contains a loop. Carries the full
    path so the message shows exactly which chain closed on itself,
    rather than just naming one document."""

    def __init__(self, cycle_path):
        self.cycle_path = cycle_path
        chain = " -> ".join(cycle_path)
        super().__init__(
            f"include cycle detected: {chain}\n"
            f"  '{cycle_path[-1]}' is already being included further up this chain, "
            "so expanding it would never terminate."
        )


@dataclass
class Doc:
    id: str
    title: str
    body: str                       # raw markdown, uncompiled
    kind: str = "rule"
    summary: str = ""
    mechanics: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)
    source_path: str = ""

    # populated during compile
    links_out: set = field(default_factory=set)
    includes: list = field(default_factory=list)  # ordered, may repeat


def parse_doc_file(path: Path) -> Doc:
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise RuleError(f"{path.name}: missing YAML frontmatter block")
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        raise RuleError(f"{path.name}: invalid YAML frontmatter - {e}")

    for req in REQUIRED_FIELDS:
        if req not in meta:
            raise RuleError(f"{path.name}: frontmatter missing required field '{req}'")

    kind = meta.get("kind", "rule")
    if kind not in KINDS:
        raise RuleError(f"{path.name}: kind '{kind}' must be one of {KINDS}")

    # A rule with no summary has no tooltip text, which defeats half the
    # point of the format. Sections are book scaffolding, so theirs is
    # optional.
    if kind != "section" and not str(meta.get("summary", "")).strip():
        raise RuleError(f"{path.name}: frontmatter missing required field 'summary'")

    if "spine" in meta:
        raise RuleError(
            f"{path.name}: 'spine' is no longer used - book order comes from "
            "{% include %} directives in book/rulebook.md and its chapters."
        )

    stem = path.stem
    if meta["id"] != stem:
        raise RuleError(
            f"{path.name}: id '{meta['id']}' must match the filename stem '{stem}' "
            "(so links, includes and file paths can't drift apart)"
        )

    body = m.group(2)
    return Doc(
        id=meta["id"],
        title=meta["title"],
        kind=kind,
        summary=str(meta.get("summary", "")).strip(),
        body=body,
        mechanics=meta.get("mechanics", {}) or {},
        tags=meta.get("tags", []) or [],
        source_path=str(path),
        includes=INCLUDE_RE.findall(body),
    )


def load_docs(*dirs) -> dict:
    """Load every .md under the given directories into one id namespace.

    The search is recursive so that a ruleset with a lot of documents of
    one kind -- a bestiary, a spell index -- can file them in a
    subdirectory without them crowding out the rules proper. Nothing
    else changes: ids stay a single flat namespace, so where a document
    sits on disk has no bearing on how it is linked or included, and two
    documents with the same id remain an error wherever they are."""
    docs = {}
    for d in dirs:
        d = Path(d)
        if not d.exists():
            continue
        for path in sorted(d.rglob("*.md")):
            doc = parse_doc_file(path)
            if doc.id in docs:
                raise RuleError(
                    f"duplicate document id '{doc.id}' "
                    f"({docs[doc.id].source_path} and {path})"
                )
            docs[doc.id] = doc
    if not docs:
        raise RuleError(f"no documents found in {', '.join(str(d) for d in dirs)}")
    return docs


# ---------------------------------------------------------------------
# Include graph
# ---------------------------------------------------------------------
def check_include_targets(docs: dict) -> list:
    """Every {% include x %} must name a document that exists."""
    errors = []
    for doc in docs.values():
        for target in doc.includes:
            if target not in docs:
                errors.append(
                    f"{doc.id}: {{% include {target} %}} names a document that does not exist"
                )
    return errors


def check_book_only_markers(docs: dict) -> list:
    """{% book-only %} must be closed, and must not nest.

    An unclosed marker would silently swallow the rest of a document out
    of every snippet, which is exactly the kind of quiet wrong answer
    this pipeline exists to prevent -- so it is an error, not a warning."""
    errors = []
    for doc in docs.values():
        depth = 0
        broken = False
        for m in BOOK_ONLY_TOKEN_RE.finditer(doc.body):
            if m.group(1) == "book-only":
                depth += 1
                if depth > 1:
                    errors.append(
                        f"{doc.id}: {{% book-only %}} blocks cannot nest")
                    broken = True
                    break
            else:
                depth -= 1
                if depth < 0:
                    errors.append(
                        f"{doc.id}: {{% endbook-only %}} with no matching "
                        "{% book-only %} before it")
                    broken = True
                    break
        if not broken and depth != 0:
            errors.append(
                f"{doc.id}: {{% book-only %}} is never closed -- add "
                "{% endbook-only %}")
    return errors


def strip_book_only(text: str) -> str:
    """Drop book-only blocks entirely. Used for the snippet form."""
    return BOOK_ONLY_RE.sub("", text)


def unwrap_book_only(text: str) -> str:
    """Keep the content, drop the markers. Used for the book form."""
    return BOOK_ONLY_TOKEN_RE.sub("", text)


def detect_cycles(docs: dict, root_id: str = None):
    """Depth-first walk of the include graph, raising IncludeCycleError
    with the full offending chain.

    Checks EVERY document as a start point by default, not just the book
    root - a cycle in a subtree that nothing currently includes is still
    a bug, and you want it caught before someone wires that subtree into
    the book and gets an infinite expansion instead of an error.

    A document appearing twice via separate branches (a diamond) is NOT
    a cycle and is allowed here; lint.py warns about it separately,
    since duplicated content in a book is usually - but not always - a
    mistake."""
    visiting = set()   # on the current DFS path
    finished = set()   # fully explored, known cycle-free

    def walk(doc_id, path):
        if doc_id in visiting:
            # `path` already ends with this repeat, so slicing from the
            # first occurrence gives the closed loop (a -> b -> a) — do
            # NOT append doc_id again or the chain shows it twice.
            start = path.index(doc_id)
            raise IncludeCycleError(path[start:])
        if doc_id in finished:
            return
        visiting.add(doc_id)
        for target in docs[doc_id].includes:
            if target in docs:  # missing targets are reported separately
                walk(target, path + [target])
        visiting.discard(doc_id)
        finished.add(doc_id)

    starts = [root_id] if root_id else sorted(docs)
    for start in starts:
        if start in docs:
            walk(start, [start])


def include_order(docs: dict, root_id: str):
    """Flatten the include tree into [(doc_id, depth), ...] in book
    order. Call detect_cycles() first - this assumes an acyclic graph
    but still guards, so a bug here fails loudly rather than hanging."""
    out = []

    def walk(doc_id, depth, stack):
        if doc_id in stack:
            raise IncludeCycleError(stack[stack.index(doc_id):] + [doc_id])
        out.append((doc_id, depth))
        for target in docs[doc_id].includes:
            if target in docs:
                walk(target, depth + 1, stack + [doc_id])

    walk(root_id, 0, [])
    return out


# ---------------------------------------------------------------------
# Interpolation and links
# ---------------------------------------------------------------------
def _lookup_path(obj, dotted: str):
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(dotted)
        cur = cur[part]
    return cur


def resolve_interpolations(doc: Doc, docs: dict, errors: list) -> str:
    """Replace {{ ... }} with values from mechanics. This is what makes
    the prose and the machine-readable data structurally incapable of
    disagreeing - the prose does not contain the number, it contains a
    pointer to it."""

    def repl(match):
        expr = match.group(1).strip()
        if ":" in expr:
            other_id, dotted = expr.split(":", 1)
            other_id, dotted = other_id.strip(), dotted.strip()
            if other_id not in docs:
                errors.append(f"{doc.id}: {{{{ {expr} }}}} references unknown document '{other_id}'")
                return f"[?{expr}?]"
            source = {"mechanics": docs[other_id].mechanics}
        else:
            dotted = expr
            source = {"mechanics": doc.mechanics}
        try:
            value = _lookup_path(source, dotted)
        except KeyError:
            errors.append(f"{doc.id}: {{{{ {expr} }}}} does not resolve to a value")
            return f"[?{expr}?]"
        if isinstance(value, bool):
            return "yes" if value else "no"
        return str(value)

    return INTERP_RE.sub(repl, doc.body)


def _titleise(key: str) -> str:
    """goblin_boss -> 'Goblin boss'. Sentence case, not title case: the
    rules capitalise like prose, not like a spreadsheet header."""
    words = str(key).replace("_", " ").strip()
    return words[:1].upper() + words[1:]


def _spec_list(raw: str) -> list:
    """Parse 'key,other:Label' into [(key, label), ...]. A label is
    optional and defaults to the key, sentence-cased."""
    out = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        key, _, label = part.partition(":")
        key = key.strip()
        out.append((key, label.strip() or _titleise(key)))
    return out


def _table_cell(value) -> str:
    """Render one mechanics value as table-cell text. Booleans read as
    yes/no exactly as they do through interpolation, and a value a row
    simply does not have reads as a dash rather than as 'None'.

    Identifier-shaped strings lose their underscores, because a cell is
    something a reader reads: 'damage reduction of one type', not
    damage_reduction_of_one_type. Row labels are treated the same way,
    so a table is legible throughout without every value needing a
    hand-written label."""
    if value is _MISSING:
        return MISSING_CELL
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        return ", ".join(_table_cell(v) for v in value)
    if isinstance(value, str):
        return value.replace("_", " ").replace("|", r"\|")
    return str(value)


_MISSING = object()


def expand_tables(doc: Doc, docs: dict, text: str, errors: list) -> str:
    """Expand {% table ... %} into a Markdown pipe table built from
    mechanics.

    The tables in this game are tabulations of data that already exists
    in frontmatter — the weapon list, a creature's statistics — so
    authoring them by hand would re-type the values a second time and
    put them straight back in reach of the drift this whole format
    exists to prevent. Worse, the drift linter cannot catch the failure
    that matters here: it sees a number that disagrees, and is blind to
    a column that was simply left out. Generating the table from the
    map means a field cannot be forgotten, only deliberately excluded.

    Emitting Markdown rather than HTML keeps one table renderer for
    both authored and generated tables, and keeps the resolved
    document meaningful if it is ever written out as Markdown."""

    def repl(match):
        try:
            args = shlex.split(match.group(1))
        except ValueError as exc:
            errors.append(f"{doc.id}: {{% table %}} arguments do not parse - {exc}")
            return ""
        if not args:
            errors.append(f"{doc.id}: {{% table %}} needs a mechanics path to tabulate")
            return ""

        # A list that ends in a comma continues on the next line, so a
        # long column list can wrap inside the same 72 columns the prose
        # keeps to rather than running off the side of the document.
        joined = [args[0]]
        for arg in args[1:]:
            if joined and joined[-1].endswith(","):
                joined[-1] += arg
            else:
                joined.append(arg)

        source_expr, opts = joined[0], {}
        for arg in joined[1:]:
            key, sep, value = arg.partition("=")
            if not sep:
                errors.append(
                    f"{doc.id}: {{% table %}} argument '{arg}' is not key=value")
                return ""
            opts[key.strip()] = value

        unknown = set(opts) - {"rows", "columns", "header", "value_header",
                               "flags", "flag_header"}
        if unknown:
            errors.append(
                f"{doc.id}: {{% table %}} does not understand "
                f"{', '.join(sorted(unknown))}")
            return ""

        # Same addressing as interpolation: a bare path is this
        # document's mechanics, 'other:mechanics.x' is another's.
        if ":" in source_expr:
            other_id, dotted = (p.strip() for p in source_expr.split(":", 1))
            if other_id not in docs:
                errors.append(
                    f"{doc.id}: {{% table {source_expr} %}} references unknown "
                    f"document '{other_id}'")
                return ""
            source = {"mechanics": docs[other_id].mechanics}
        else:
            dotted, source = source_expr, {"mechanics": doc.mechanics}
        try:
            data = _lookup_path(source, dotted)
        except KeyError:
            errors.append(
                f"{doc.id}: {{% table {source_expr} %}} does not resolve to a value")
            return ""
        if not isinstance(data, dict):
            errors.append(
                f"{doc.id}: {{% table {source_expr} %}} is not a map, so there is "
                "nothing to tabulate")
            return ""

        columns = _spec_list(opts["columns"]) if "columns" in opts else None
        # A boolean field per column gives a wide table of mostly
        # dashes. flags= collapses several into one column that names
        # the properties a row actually has, which is how the prose
        # talks about them anyway.
        flags = _spec_list(opts["flags"]) if "flags" in opts else None
        if flags and columns is None:
            errors.append(
                f"{doc.id}: {{% table {source_expr} %}} has flags= but no columns=, "
                "and a field/value table has no column to put them in")
            return ""
        grid = columns is not None

        if "rows" in opts:
            rows = _spec_list(opts["rows"])
            missing = [k for k, _ in rows if k not in data]
            if missing:
                errors.append(
                    f"{doc.id}: {{% table {source_expr} %}} names "
                    f"{', '.join(missing)}, which {'are' if len(missing) > 1 else 'is'} "
                    "not in that map")
                return ""
            # A grid row must be a sub-map to have columns; a pairs row
            # must not be, or the cell would print a dict at the reader.
            wrong = [k for k, _ in rows if isinstance(data[k], dict) is not grid]
            if wrong:
                errors.append(
                    f"{doc.id}: {{% table {source_expr} %}} names {', '.join(wrong)}, "
                    + ("which has no fields to put in columns"
                       if grid else
                       "which is a map, so it needs columns= to tabulate"))
                return ""
        else:
            # Grid rows are the sub-maps; pairs rows are the plain
            # values. Choosing by shape means the common case needs no
            # argument at all and cannot silently include the wrong kind.
            rows = [(k, _titleise(k)) for k, v in data.items()
                    if isinstance(v, dict) is grid]
        if not rows:
            errors.append(
                f"{doc.id}: {{% table {source_expr} %}} selected no rows")
            return ""

        if grid:
            head = [opts.get("header", "Name")] + [lbl for _, lbl in columns]
            if flags:
                head.append(opts.get("flag_header", "Properties"))
            aligns = ["---"] * len(head)
            body = []
            for key, label in rows:
                cells = [label] + [_table_cell(data[key].get(f, _MISSING))
                                   for f, _ in columns]
                if flags:
                    held = [lbl for f, lbl in flags if data[key].get(f)]
                    cells.append(", ".join(held) if held else MISSING_CELL)
                body.append(cells)
        else:
            head = [opts.get("header", "Field"), opts.get("value_header", "Value")]
            aligns = ["---"] * 2
            body = [[label, _table_cell(data[key])] for key, label in rows]

        lines = ["| " + " | ".join(head) + " |",
                 "|" + "|".join(aligns) + "|"]
        lines += ["| " + " | ".join(cells) + " |" for cells in body]
        # Blank lines around it so the table is its own block whatever
        # the directive was sitting next to.
        return "\n" + "\n".join(lines) + "\n"

    return TABLE_RE.sub(repl, text)


def resolve_links(text: str, doc: Doc, docs: dict, errors: list, href_for) -> str:
    def repl(match):
        target = match.group(1).strip()
        label = (match.group(2) or "").strip()
        if target not in docs:
            errors.append(f"{doc.id}: [[{target}]] points at a document that does not exist")
            return '<span class="broken-link">' + (label or target) + "</span>"
        doc.links_out.add(target)
        text_label = label or docs[target].title
        return f'<a href="{href_for(target)}" data-rule-id="{target}">{text_label}</a>'

    return LINK_RE.sub(repl, text)


# ---------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------
CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")
DELIMITER_CELL_RE = re.compile(r"^:?-{2,}:?$")
MISSING_CELL = "—"           # em dash, for a value a row does not have


def _split_table_row(line: str) -> list:
    """Split a pipe-table row into cells. A cell may contain a literal
    pipe if it is escaped."""
    core = line.strip()
    if core.startswith("|"):
        core = core[1:]
    if core.endswith("|") and not core.endswith(r"\|"):
        core = core[:-1]
    return [c.strip().replace(r"\|", "|") for c in CELL_SPLIT_RE.split(core)]


def _is_delimiter_row(cells: list) -> bool:
    return bool(cells) and all(DELIMITER_CELL_RE.match(c.strip()) for c in cells)


def _alignment_of(cell: str):
    cell = cell.strip()
    left, right = cell.startswith(":"), cell.endswith(":")
    if left and right:
        return "center"
    if right:
        return "right"
    return None                   # left is the default; say nothing


# ---------------------------------------------------------------------
# A deliberately small Markdown subset renderer.
#
# Not using a real Markdown library because none is installable in this
# environment (no network). This handles what the documents actually
# use: ## headings, paragraphs, **bold**, `code`, and unordered lists.
# If you later add a dependency, swap this one function out for
# markdown/mistune - nothing else in the pipeline depends on it.
# ---------------------------------------------------------------------
def render_markdown(text: str, heading_offset: int = 0) -> str:
    """heading_offset shifts every heading down by N levels, so a
    document included three levels deep nests under its parents instead
    of sitting alongside them."""

    def inline(s):
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", s)
        return s

    html_parts = []
    buffer = []
    list_buffer = []
    table_buffer = []

    def flush_para():
        if buffer:
            para = " ".join(line.strip() for line in buffer).strip()
            if para:
                html_parts.append(f"<p>{inline(para)}</p>")
            buffer.clear()

    def flush_list():
        if list_buffer:
            items = "".join(f"<li>{inline(i)}</li>" for i in list_buffer)
            html_parts.append(f"<ul>{items}</ul>")
            list_buffer.clear()

    def flush_table():
        if not table_buffer:
            return
        rows = [_split_table_row(l) for l in table_buffer]
        table_buffer.clear()
        aligns = None
        if len(rows) > 1 and _is_delimiter_row(rows[1]):
            aligns = [_alignment_of(c) for c in rows[1]]
            head, body = rows[0], rows[2:]
        else:
            head, body = None, rows
        width = max(len(r) for r in ([head] if head else []) + body)

        def cells(row, tag):
            out = []
            for i in range(width):
                text = inline(row[i]) if i < len(row) else ""
                align = aligns[i] if aligns and i < len(aligns) else None
                attr = f' style="text-align:{align}"' if align else ""
                out.append(f"<{tag}{attr}>{text}</{tag}>")
            return "<tr>" + "".join(out) + "</tr>"

        parts = []
        if head:
            parts.append("<thead>" + cells(head, "th") + "</thead>")
        if body:
            parts.append("<tbody>" + "".join(cells(r, "td") for r in body) + "</tbody>")
        html_parts.append("<table>" + "".join(parts) + "</table>")

    for raw_line in text.split("\n"):
        line = raw_line.rstrip()
        if not line.strip():
            flush_para()
            flush_list()
            flush_table()
            continue
        if line.strip().startswith("|"):
            flush_para()
            flush_list()
            table_buffer.append(line.strip())
            continue
        flush_table()
        heading = re.match(r"^(#{2,4})\s+(.*)$", line)
        if heading:
            flush_para()
            flush_list()
            level = min(len(heading.group(1)) + heading_offset, 6)
            html_parts.append(f"<h{level}>{inline(heading.group(2))}</h{level}>")
            continue
        item = re.match(r"^[-*]\s+(.*)$", line)
        if item:
            flush_para()
            list_buffer.append(item.group(1))
            continue
        # An indented line beneath a list item is that item carrying on,
        # not a new paragraph. Rule prose is hard-wrapped, so most items
        # have one; treating them as paragraphs closed the list after
        # the first line and left the remainder stranded below it.
        if list_buffer and raw_line[:1].isspace():
            list_buffer[-1] += " " + line.strip()
            continue
        flush_para() if list_buffer else None
        flush_list()
        buffer.append(line)

    flush_para()
    flush_list()
    flush_table()
    return "\n".join(html_parts)


def compile_docs(*dirs, root_id: str = "rulebook"):
    """Load, validate, resolve, and render every document.

    Returns (docs, compiled, errors). Include-target problems land in
    `errors` so build.py can refuse to write output; a CYCLE raises
    immediately instead, because unlike the others it makes the graph
    unwalkable rather than merely wrong."""
    docs = load_docs(*dirs)
    errors = []

    errors.extend(check_include_targets(docs))
    errors.extend(check_book_only_markers(docs))
    # Cycles must be caught before anything walks the graph.
    detect_cycles(docs)

    compiled = {}
    for doc in docs.values():
        interpolated = resolve_interpolations(doc, docs, errors)
        # After interpolation, before links: a generated cell may hold a
        # [[link]], and nothing downstream should have to know whether a
        # table was authored or built.
        tabulated = expand_tables(doc, docs, interpolated, errors)
        linked = resolve_links(tabulated, doc, docs, errors, href_for=lambda t: f"#rule-{t}")
        compiled[doc.id] = {
            "doc": doc,
            # kept WITH include directives intact - build.py splits on
            # them so a chapter's prose can sit between its rules.
            # book-only markers are removed but their CONTENT stays:
            # the book is the consumer that wants it.
            "linked": unwrap_book_only(linked),
            # include-free form, for snippets: an in-game popup wants
            # this rule, not this rule plus everything it includes
            # offset 2: a standalone popup renders the title as <h3>,
            # so the body's `##` should land on <h4>
            "html": render_markdown(
                INCLUDE_RE.sub("", strip_book_only(linked)), heading_offset=2),
        }

    # summaries interpolate too - they show up in tooltips
    for doc in docs.values():
        fake = Doc(id=doc.id, title=doc.title, summary="", body=doc.summary,
                   mechanics=doc.mechanics, source_path=doc.source_path)
        resolved_summary = resolve_interpolations(fake, docs, errors)
        resolved_summary = LINK_RE.sub(lambda m: (m.group(2) or m.group(1)), resolved_summary)
        flat = " ".join(resolved_summary.split())
        # Two forms, because summaries have two consumers: a plain-text
        # one for anywhere HTML isn't safe or wanted (native tooltips,
        # alt text, a terminal), and an inline-rendered one for the book
        # and rich in-game popups.
        compiled[doc.id]["summary_resolved"] = re.sub(r"`([^`]+)`", r"\1", flat)
        compiled[doc.id]["summary_html"] = re.sub(r"`([^`]+)`", r"<code>\1</code>", flat)

    return docs, compiled, errors


# Backwards-compatible alias: the old entry point took a single rules
# directory and sorted by `spine`. Keeping the name pointed at the new
# function means callers that only ever passed a directory still work.
def compile_rules(rules_dir, book_dir=None, root_id: str = "rulebook"):
    dirs = [rules_dir] + ([book_dir] if book_dir else [])
    return compile_docs(*dirs, root_id=root_id)
