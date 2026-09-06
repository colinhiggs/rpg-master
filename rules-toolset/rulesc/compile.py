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

import functools
import json
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import IncludeCycleError, RuleError
from .profile import DROP, KEEP, Profile

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.S)
INTERP_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")
LINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]")
INCLUDE_RE = re.compile(r"\{\%\s*include\s+([A-Za-z0-9_-]+)\s*\%\}")
# Table directives may span lines, so that a long column list can stay
# inside the 72-column wrap the prose uses.
TABLE_RE = re.compile(r"\{\%\s*table\s+(.*?)\s*\%\}", re.S)
# Every {% directive %}, whatever it turns out to be. An audience tag
# the corpus has not declared used to pass through as literal text,
# which is the quiet wrong answer this pipeline exists to prevent - so
# anything this matches and nothing understands is an error.
DIRECTIVE_RE = re.compile(r"\{\%\s*([A-Za-z][A-Za-z0-9_-]*)")
BUILTIN_DIRECTIVES = ("include", "table")

REQUIRED_FIELDS = ("id", "title")
# Frontmatter keys the toolset owns. Anything else has to be a data
# block the document's kind declares, so that `mechanic:` for
# `mechanics:` is an error rather than a key silently ignored.
DOC_FIELDS = ("id", "title", "kind", "summary", "tags", "based_on")


@functools.lru_cache(maxsize=None)
def audience_block_re(tag: str):
    """{% tag %}...{% endtag %}, content captured."""
    t = re.escape(tag)
    return re.compile(r"\{\%\s*" + t + r"\s*\%\}(.*?)\{\%\s*end" + t + r"\s*\%\}", re.S)


@functools.lru_cache(maxsize=None)
def audience_token_re(tag: str):
    """Either marker of an audience tag, on its own."""
    t = re.escape(tag)
    return re.compile(r"\{\%\s*(" + t + r"|end" + t + r")\s*\%\}")


@dataclass
class Doc:
    id: str
    title: str
    body: str                       # raw markdown, uncompiled
    kind: str = "rule"
    summary: str = ""
    data: dict = field(default_factory=dict)   # block name -> block contents
    tags: list = field(default_factory=list)
    based_on: str = None
    source_path: str = ""
    # An external document comes from another corpus's build outputs
    # rather than from a source file here. It can be linked to and read
    # from; it is never rendered into this corpus's own output.
    external: bool = False
    href: str = None

    # populated during compile
    links_out: set = field(default_factory=set)
    # Links that landed in another corpus. Kept apart from links_out so
    # that "See also" and a snippet's `related` stay within this corpus
    # and never render an anchor that does not exist in its book.
    links_external: set = field(default_factory=set)
    includes: list = field(default_factory=list)  # ordered, may repeat

    @property
    def mechanics(self) -> dict:
        """The block called `mechanics`.

        A document used to have exactly one data block and this was it,
        so a great deal reads `doc.mechanics` - the linter, the data
        target, the simulator by way of mechanics.json. A corpus whose
        documents carry differently-named blocks reaches them through
        `data`; this stays because for a ruleset it is still the whole
        answer."""
        return self.data.get("mechanics", {})


def parse_doc_file(path: Path, profile: Profile = None) -> Doc:
    profile = profile or Profile.default()
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

    known = ", ".join(sorted(profile.kinds))
    kind = meta.get("kind")
    if kind is None:
        kind = "rule" if "rule" in profile.kinds else None
        if kind is None:
            raise RuleError(
                f"{path.name}: frontmatter needs a 'kind' - this corpus declares "
                f"{known} and none of them is the default"
            )
    if kind not in profile.kinds:
        raise RuleError(f"{path.name}: kind '{kind}' is not declared by this corpus "
                        f"(it declares {known})")
    spec = profile.kinds[kind]

    # A document with no summary has no tooltip text, which defeats half
    # the point of the format. Structural documents are scaffolding, so
    # their kind can declare the summary optional.
    if spec.summary == "required" and not str(meta.get("summary", "")).strip():
        raise RuleError(f"{path.name}: frontmatter missing required field 'summary'")

    if "spine" in meta:
        raise RuleError(
            f"{path.name}: 'spine' is no longer used - book order comes from "
            "{% include %} directives in book/rulebook.md and its chapters."
        )

    # An id is always derivable from where the document sits, so that a
    # file cannot be renamed without its links noticing. Which part of
    # the path it comes from is the kind's business: a corpus that files
    # one document per directory -- an adventure whose overview is always
    # called adventure.md, alongside its scenes and its maps -- takes the
    # directory's name, and the guarantee is the same either way.
    if spec.id_from == "directory":
        expected, what = path.parent.name, "the containing directory's name"
    else:
        expected, what = path.stem, "the filename stem"
    if meta["id"] != expected:
        raise RuleError(
            f"{path.name}: id '{meta['id']}' must match {what} '{expected}' "
            "(so links, includes and file paths can't drift apart)"
        )

    # Anything left over has to be a data block this kind declares. A
    # key that is neither was silently ignored before, which is how
    # `mechanic:` for `mechanics:` used to cost an afternoon.
    data = {}
    for key, value in meta.items():
        if key in DOC_FIELDS:
            continue
        if key not in spec.data:
            declared = ", ".join(spec.data) or "no data blocks"
            raise RuleError(
                f"{path.name}: frontmatter key '{key}' is not a data block of "
                f"kind '{kind}', which declares {declared}"
            )
        data[key] = value or {}

    body = m.group(2)
    return Doc(
        id=meta["id"],
        title=meta["title"],
        kind=kind,
        summary=str(meta.get("summary", "")).strip(),
        body=body,
        data=data,
        tags=meta.get("tags", []) or [],
        based_on=meta.get("based_on"),
        source_path=str(path),
        includes=INCLUDE_RE.findall(body),
    )


def load_docs(*dirs, profile: Profile = None) -> dict:
    """Load every .md under the given directories into one id namespace.

    The search is recursive so that a ruleset with a lot of documents of
    one kind -- a bestiary, a spell index -- can file them in a
    subdirectory without them crowding out the rules proper. Nothing
    else changes: ids stay a single flat namespace, so where a document
    sits on disk has no bearing on how it is linked or included, and two
    documents with the same id remain an error wherever they are."""
    profile = profile or Profile.default()
    docs = {}
    for d in dirs:
        d = Path(d)
        if not d.exists():
            continue
        for path in sorted(d.rglob("*.md")):
            doc = parse_doc_file(path, profile)
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


def audience_token_pattern(profile: Profile):
    """One regex matching either marker of any declared audience tag.

    Longest tag first, so that a corpus declaring both `only` and
    `book-only` cannot have the shorter one win a prefix match."""
    if not profile.audiences:
        return None
    tags = sorted(profile.audiences, key=len, reverse=True)
    alt = "|".join(re.escape(t) for t in tags)
    return re.compile(r"\{\%\s*(end)?(" + alt + r")\s*\%\}")


def check_audience_markers(docs: dict, profile: Profile) -> list:
    """Audience blocks must be closed, must not nest inside themselves,
    and must not interleave with each other.

    An unclosed marker would silently swallow the rest of a document out
    of every target that drops the tag, which is exactly the kind of
    quiet wrong answer this pipeline exists to prevent -- so it is an
    error, not a warning. Interleaving is checked for the same reason:
    {% a %}{% b %}{% enda %}{% endb %} leaves each tag individually
    balanced while making the spans meaningless, and stripping one of
    them would leave the other's marker behind in the output."""
    token = audience_token_pattern(profile)
    if token is None:
        return []
    errors = []
    for doc in docs.values():
        if doc.external:
            continue
        stack, broken = [], False
        for m in token.finditer(doc.body):
            closing, tag = m.group(1), m.group(2)
            if not closing:
                if tag in stack:
                    errors.append(f"{doc.id}: {{% {tag} %}} blocks cannot nest")
                    broken = True
                    break
                stack.append(tag)
            elif not stack:
                errors.append(
                    f"{doc.id}: {{% end{tag} %}} with no matching "
                    f"{{% {tag} %}} before it")
                broken = True
                break
            elif stack[-1] != tag:
                errors.append(
                    f"{doc.id}: {{% end{tag} %}} closes while {{% {stack[-1]} %}} "
                    "is still open -- audience blocks may nest, but not overlap")
                broken = True
                break
            else:
                stack.pop()
        if not broken and stack:
            errors.append(
                f"{doc.id}: {{% {stack[-1]} %}} is never closed -- add "
                f"{{% end{stack[-1]} %}}")
    return errors


def check_directives(docs: dict, profile: Profile) -> list:
    """A {% directive %} nothing understands is an error.

    Before this existed, an audience tag the corpus had not declared --
    {% gm-only %} in a ruleset, say -- passed straight through into the
    output as literal text. That is worse than a failure: the content it
    was meant to hide is published, and the only evidence is a stray
    marker in the middle of a paragraph."""
    known = set(BUILTIN_DIRECTIVES)
    for tag in profile.audiences:
        known.add(tag)
        known.add("end" + tag)
    errors = []
    for doc in docs.values():
        if doc.external:
            continue
        for word in sorted(set(DIRECTIVE_RE.findall(doc.body))):
            if word not in known:
                errors.append(
                    f"{doc.id}: {{% {word} %}} is not a directive this corpus "
                    f"understands (it has {', '.join(sorted(known))}). If it is "
                    "an audience tag, declare it in the corpus profile.")
    return errors


def apply_audiences(text: str, target, profile: Profile) -> str:
    """Resolve every audience block in `text` for one target.

    Drops run before keeps, so that a kept block sitting inside a
    dropped one goes with it instead of leaving its markers stranded in
    the output."""
    for tag in profile.audiences:
        if target.action(tag) == DROP:
            text = audience_block_re(tag).sub("", text)
    for tag in profile.audiences:
        if target.action(tag) == KEEP:
            text = audience_token_re(tag).sub("", text)
    return text


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
def _index_sequence(seq, part: str, dotted: str):
    """Address one element of a list: by its `id` first, by position
    second."""
    for item in seq:
        if isinstance(item, dict) and str(item.get("id", "")) == part:
            return item
    if part.lstrip("-").isdigit():
        try:
            return seq[int(part)]
        except IndexError:
            raise KeyError(dotted)
    raise KeyError(dotted)


def _lookup_path(obj, dotted: str):
    """Walk a dotted path into a document's frontmatter data.

    A map is addressed by key. A list is addressed by the `id` of one of
    its entries -- `checks.spot-ambush.dc` -- or, failing that, by
    position -- `checks.0.dc`. Prefer the id form when writing prose:
    inserting an entry at the front of a list must not silently repoint
    every interpolation that follows it. The positional form exists
    because it costs nothing, and because a list of plain values has no
    other handle."""
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict):
            if part not in cur:
                raise KeyError(dotted)
            cur = cur[part]
        elif isinstance(cur, (list, tuple)):
            cur = _index_sequence(cur, part, dotted)
        else:
            raise KeyError(dotted)
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
            source = docs[other_id].data
        else:
            dotted = expr
            source = doc.data
        try:
            value = _lookup_path(source, dotted)
        except KeyError:
            errors.append(f"{doc.id}: {{{{ {expr} }}}} does not resolve to a value")
            return f"[?{expr}?]"
        return _render_value(value)

    return INTERP_RE.sub(repl, doc.body)


def _render_value(value, as_words: bool = False) -> str:
    """Render one mechanics value as something a reader reads.

    A list becomes a comma-separated phrase rather than a Python repr,
    wherever it appears: a mechanic that holds several tags is a phrase
    in the prose that points at it, not a fragment of source code.

    Underscores are a different matter and are left alone unless asked
    for, because a string in mechanics is not always a name. It may be a
    formula, where the underscores are the identifiers it is written in
    and taking them out would be a lie about the arithmetic."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        return ", ".join(_render_value(v, as_words) for v in value)
    if isinstance(value, str):
        return value.replace("_", " ") if as_words else value
    return str(value)


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

    Otherwise a cell reads as the same value reads through
    interpolation, with two differences. A cell asks for identifiers as
    words -- 'damage reduction of one type', not
    damage_reduction_of_one_type -- because a cell is scanned rather
    than read, and unlike prose it has no author to write the words out.
    And a pipe is escaped, which would otherwise end the cell early."""
    if value is _MISSING:
        return MISSING_CELL
    return _render_value(value, as_words=True).replace("|", r"\|")


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
            source = docs[other_id].data
        else:
            dotted, source = source_expr, doc.data
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


# A resolved link carries the document id it points at, so what a text
# actually links to can be read back off it rather than re-derived from
# the source. That matters once audiences exist: the links a reader can
# follow are the ones still standing after the target's policy is
# applied, which is not the same set the author wrote.
ANCHOR_ID_RE = re.compile(r'data-rule-id="([^"]+)"')
LOCAL_ANCHOR_RE = re.compile(
    r'<a href="#rule-([A-Za-z0-9_-]+)" data-rule-id="[^"]*">(.*?)</a>', re.S)


def links_in(text: str) -> set:
    """Every document a resolved text links to, as the text now stands."""
    return set(ANCHOR_ID_RE.findall(text))


def strip_absent_links(text: str, present) -> str:
    """Turn a link into its own words when the target does not render
    the document it points at.

    An anchor to a document that is not in this output is dead, and its
    id in the page source is a trace of something the reader was not
    meant to be told about. Neither is left behind: what remains is the
    text the author wrote and nothing else, so the page reads as though
    the link had never been one."""
    return LOCAL_ANCHOR_RE.sub(
        lambda m: m.group(0) if m.group(1) in present else m.group(2), text)


def resolve_links(text: str, doc: Doc, docs: dict, errors: list, href_for) -> str:
    def repl(match):
        target = match.group(1).strip()
        label = (match.group(2) or "").strip()
        if target not in docs:
            errors.append(f"{doc.id}: [[{target}]] points at a document that does not exist")
            return '<span class="broken-link">' + (label or target) + "</span>"
        other = docs[target]
        text_label = label or other.title
        if other.external:
            # Another corpus's document. It has no anchor in this
            # corpus's book, so it is never given one: either the
            # reference declared where that corpus is published, or the
            # id travels on its own for a client to resolve.
            doc.links_external.add(target)
            if other.href:
                return (f'<a href="{other.href}" data-rule-id="{target}" '
                        f'class="external-ref">{text_label}</a>')
            return f'<span class="external-ref" data-rule-id="{target}">{text_label}</span>'
        doc.links_out.add(target)
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


# ---------------------------------------------------------------------
# Inheritance
# ---------------------------------------------------------------------
def merge_block(parent: dict, child: dict) -> dict:
    """Merge one inherited data block.

    Scalars replace wholesale, nested maps merge key by key, lists
    replace wholesale.

    A list replaces rather than merging because a list is a statement
    about a whole set: a variant that lists two powers has two powers,
    not two plus whatever it inherited. Merging them would make it
    impossible to take anything away, which is most of what a variant is
    for."""
    out = dict(parent)
    for key, value in (child or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge_block(out[key], value)
        else:
            out[key] = value
    return out


def resolve_inheritance(docs: dict) -> list:
    """Fold `based_on` into each document's data blocks.

    This runs before anything reads those blocks -- before lint, before
    interpolation -- and that ordering is the point. A document whose
    prose restates a value it INHERITED is exactly the drift this format
    exists to catch, and it is invisible to a check that only sees the
    keys the document declared for itself."""
    errors = []
    done = set()

    def walk(doc_id, stack):
        if doc_id in done:
            return
        doc = docs[doc_id]
        parent_id = doc.based_on
        if not parent_id:
            done.add(doc_id)
            return
        if parent_id not in docs:
            errors.append(
                f"{doc.id}: based_on names '{parent_id}', which is not a document "
                "here or in a referenced corpus")
            done.add(doc_id)
            return
        if parent_id in stack:
            errors.append(
                f"{doc.id}: based_on is a cycle: "
                + " -> ".join(stack + [doc_id, parent_id]))
            done.add(doc_id)
            return
        walk(parent_id, stack + [doc_id])
        parent = docs[parent_id]
        doc.data = {
            name: merge_block(parent.data.get(name, {}), doc.data.get(name, {}))
            for name in set(parent.data) | set(doc.data)
        }
        done.add(doc_id)

    for doc_id in sorted(docs):
        walk(doc_id, [])
    return errors


# ---------------------------------------------------------------------
# References into another corpus
# ---------------------------------------------------------------------
def load_reference(ref, base_dir: Path):
    """Load another corpus's build outputs as read-only documents.

    Only the outputs are read, never that corpus's sources. What a
    consumer may depend on is what the producing project publishes, and
    reading its rules/*.md directly would be depending on how it is
    written rather than on what it ships.

    Returns (docs, metadata). The metadata travels into every output
    under the `_`-prefixed convention, so a built adventure says which
    rules version it was built against."""
    root = Path(ref.path)
    if not root.is_absolute():
        root = Path(base_dir) / root
    snippets_path = root / "snippets.json"
    mechanics_path = root / "mechanics.json"
    missing = [p.name for p in (snippets_path, mechanics_path) if not p.exists()]
    if missing:
        raise RuleError(
            f"reference '{ref.path}' has no {' and no '.join(missing)} in {root}.\n"
            "  That corpus has not been built, or the path is wrong. Build it with\n"
            f"  python3 tools/build.py --path {root.parent}")
    try:
        snippets = json.loads(snippets_path.read_text(encoding="utf-8"))
        mechanics = json.loads(mechanics_path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise RuleError(f"reference '{ref.path}': {e}")

    # A single-block producer writes that block's contents straight in,
    # which is what mechanics.json has always looked like. One that
    # declares several names them, and says so with `_blocks`.
    named = mechanics.get("_blocks")
    blocks = mechanics.get("rules", {})

    docs = {}
    for doc_id, entry in snippets.items():
        if doc_id.startswith("_"):
            continue
        raw = blocks.get(doc_id)
        if raw is None:
            data = {}
        elif named:
            data = {name: body for name, body in raw.items()}
        else:
            data = {"mechanics": raw}
        docs[doc_id] = Doc(
            id=doc_id,
            title=entry.get("title", doc_id),
            body="",
            kind=entry.get("kind", "rule"),
            summary=entry.get("summary", "") or "",
            data=data,
            tags=entry.get("tags", []) or [],
            source_path=str(snippets_path),
            external=True,
            href=ref.href.format(id=doc_id) if ref.href else None,
        )
    meta = {
        "name": ref.name or root.parent.name,
        "version": snippets.get("_version") or mechanics.get("_version"),
        "source": ref.path,
    }
    return docs, meta


def _collect_refs(node, parts):
    """Every string a declared ref path reaches.

    A path that is not present yields nothing rather than an error: a
    frontmatter field may legitimately be optional, and `branches` is.
    A value that IS present and is not a document id is the thing worth
    failing over."""
    if not parts:
        if isinstance(node, str):
            return [node]
        if isinstance(node, (list, tuple)):
            return [v for v in node if isinstance(v, str)]
        return []
    head, rest = parts[0], parts[1:]
    if head == "*":
        if isinstance(node, dict):
            children = list(node.values())
        elif isinstance(node, (list, tuple)):
            children = list(node)
        else:
            return []
        out = []
        for child in children:
            out += _collect_refs(child, rest)
        return out
    if isinstance(node, dict):
        return _collect_refs(node[head], rest) if head in node else []
    if isinstance(node, (list, tuple)):
        try:
            return _collect_refs(_index_sequence(node, head, head), rest)
        except KeyError:
            return []
    return []


def check_refs(docs: dict, profile: Profile) -> list:
    """A frontmatter field declared to hold document ids must hold ids
    that resolve.

    Prose references are checked already -- a bad [[link]] fails the
    build. A document id sitting in frontmatter had nothing checking it,
    which is how a scene comes to point at a scene that was renamed."""
    errors = []
    for doc in docs.values():
        if doc.external:
            continue
        spec = profile.kinds.get(doc.kind)
        if spec is None or not spec.refs:
            continue
        for path in spec.refs:
            for value in _collect_refs(doc.data, path.split(".")):
                if value not in docs:
                    errors.append(
                        f"{doc.id}: {path} names '{value}', which is not a document "
                        "in this corpus or in one it references")
    return errors


# ---------------------------------------------------------------------
# Compiling
# ---------------------------------------------------------------------
@dataclass
class Corpus:
    """Everything a target needs, and nothing about any one target.

    `compiled[id]["marked"]` is the document resolved -- interpolated,
    tabulated, linked -- with its audience markers still in place.
    Applying an audience policy is a target's job, because with more
    than two targets there is no single pair of forms to precompute."""

    docs: dict
    compiled: dict
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    profile: Profile = None
    references: list = field(default_factory=list)
    version: str = None

    def local(self):
        """The documents this corpus owns, in id order. Documents pulled
        in from a referenced corpus are readable and linkable but are
        never rendered into this corpus's own output."""
        return [d for d in self.docs.values() if not d.external]


def compile_corpus(*dirs, profile: Profile = None, base_dir=None, version: str = None):
    """Load, validate, resolve and render a corpus.

    Include-target and reference problems land in `errors` so a caller
    can refuse to write output; a CYCLE raises immediately instead,
    because unlike the others it makes the graph unwalkable rather than
    merely wrong."""
    profile = profile or Profile.default()
    if base_dir is None:
        base_dir = Path(dirs[0]).parent if dirs else Path(".")

    docs = load_docs(*dirs, profile=profile)
    errors, warnings, references = [], [], []

    for ref in profile.references:
        external, meta = load_reference(ref, base_dir)
        for doc_id, doc in external.items():
            if doc_id in docs:
                errors.append(
                    f"duplicate document id '{doc_id}': it is a document here "
                    f"({docs[doc_id].source_path}) and also one in the referenced "
                    f"corpus '{meta['name']}'. The two share one flat namespace, "
                    "so rename this one.")
                continue
            docs[doc_id] = doc
        if meta["version"] is None:
            warnings.append(
                f"referenced corpus '{meta['name']}' carries no version, so nothing "
                "built here can record which of its versions it was built against")
        references.append(meta)

    errors.extend(resolve_inheritance(docs))
    errors.extend(check_include_targets(docs))
    errors.extend(check_audience_markers(docs, profile))
    errors.extend(check_directives(docs, profile))
    errors.extend(check_refs(docs, profile))
    # Cycles must be caught before anything walks the graph.
    detect_cycles(docs)

    compiled = {}
    for doc in docs.values():
        if doc.external:
            continue
        interpolated = resolve_interpolations(doc, docs, errors)
        # After interpolation, before links: a generated cell may hold a
        # [[link]], and nothing downstream should have to know whether a
        # table was authored or built.
        tabulated = expand_tables(doc, docs, interpolated, errors)
        linked = resolve_links(tabulated, doc, docs, errors,
                               href_for=lambda t: f"#rule-{t}")
        # Include directives are kept: a target splits on them so a
        # chapter's prose can sit between its rules. Audience markers
        # are kept too, and resolved per target.
        compiled[doc.id] = {"doc": doc, "marked": linked}

    # summaries interpolate too - they show up in tooltips
    for doc in docs.values():
        if doc.external:
            continue
        fake = Doc(id=doc.id, title=doc.title, summary="", body=doc.summary,
                   data=doc.data, source_path=doc.source_path)
        resolved_summary = resolve_interpolations(fake, docs, errors)
        resolved_summary = LINK_RE.sub(lambda m: (m.group(2) or m.group(1)), resolved_summary)
        flat = " ".join(resolved_summary.split())
        # Two forms, because summaries have two consumers: a plain-text
        # one for anywhere HTML isn't safe or wanted (native tooltips,
        # alt text, a terminal), and an inline-rendered one for the book
        # and rich in-game popups.
        compiled[doc.id]["summary_resolved"] = re.sub(r"`([^`]+)`", r"\1", flat)
        compiled[doc.id]["summary_html"] = re.sub(r"`([^`]+)`", r"<code>\1</code>", flat)

    return Corpus(docs=docs, compiled=compiled, errors=errors, warnings=warnings,
                  profile=profile, references=references, version=version)


def compile_docs(*dirs, root_id: str = "rulebook", profile: Profile = None):
    """The older entry point: same work, returning (docs, compiled,
    errors) rather than a Corpus. Kept because a good deal calls it."""
    corpus = compile_corpus(*dirs, profile=profile)
    return corpus.docs, corpus.compiled, corpus.errors


# Backwards-compatible alias: the oldest entry point took a single rules
# directory and sorted by `spine`. Keeping the name pointed at the new
# function means callers that only ever passed a directory still work.
def compile_rules(rules_dir, book_dir=None, root_id: str = "rulebook"):
    dirs = [rules_dir] + ([book_dir] if book_dir else [])
    return compile_docs(*dirs, root_id=root_id)
