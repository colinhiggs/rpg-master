# lint.py — the checks that keep "one source of truth" actually true.
#
# The compiler will happily build a book whose prose says "you get 3
# actions" while the data says actions_per_turn: 1. Nothing in the
# format prevents that — only this linter does. Treat lint failures as
# build failures; that is the entire point of the architecture.
#
# Which checks apply is a property of the corpus, not of this file: a
# corpus with no book has nothing useful to say about reachability from
# a book root. check_hardcoded_numbers is the exception and is not
# switchable, because a corpus that could turn it off would be a corpus
# where the prose and the data are allowed to disagree.

import re

from .profile import Profile

# Numbers so generic that matching them means nothing. "1" appears in
# ordinary prose constantly ("one tile", "a 1 in 6 chance") and flagging
# every instance would train you to ignore the linter.
IGNORE_BARE = {0, 1}

NUMBER_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])")
INTERP_RE = re.compile(r"\{\{[^}]*\}\}")
CODE_RE = re.compile(r"`[^`]*`")


def _local(docs):
    """Documents this corpus owns. A document read out of another
    corpus's build outputs has no body here and is that corpus's to
    lint."""
    return [d for d in docs.values() if not d.external]


def _numeric_leaves(node, prefix=""):
    """Flatten frontmatter data into {dotted_key: number} for numeric
    leaves.

    Lists are walked as well as maps, addressed by an entry's `id` where
    it has one and by position where it does not — the same way an
    interpolation path addresses them. That is what lets the check reach
    a threshold sitting in a list of checks rather than only one sitting
    at the top of a block."""
    out = {}
    if isinstance(node, dict):
        items = node.items()
    elif isinstance(node, (list, tuple)):
        items = []
        for i, entry in enumerate(node):
            key = entry.get("id") if isinstance(entry, dict) else None
            items.append((key if key is not None else i, entry))
    else:
        return out
    for k, v in items:
        key = f"{prefix}{k}"
        if isinstance(v, (dict, list, tuple)):
            out.update(_numeric_leaves(v, prefix=f"{key}."))
        elif isinstance(v, bool):
            continue  # bools aren't numbers for this purpose
        elif isinstance(v, (int, float)):
            out[key] = v
    return out


def _numeric_data(doc):
    """Every number in every data block a document carries, keyed the
    way prose would have to address it."""
    out = {}
    for block, body in (doc.data or {}).items():
        out.update(_numeric_leaves(body, prefix=f"{block}."))
    return out


def _strip_uncheckable(body: str) -> str:
    """Remove regions where a literal number is legitimate: already-
    interpolated expressions, and inline code (dice notation like `XdY+Z`
    or a regex pattern is not prose restating a constant)."""
    body = INTERP_RE.sub(" ", body)
    body = CODE_RE.sub(" ", body)
    return body


def check_hardcoded_numbers(docs):
    """The core drift check: a bare number in prose that equals one of
    this document's own data values is almost always a value that should
    have been interpolated.

    This one is never switched off. It applies to every data block a
    document carries, whatever the block is called — a difficulty in an
    encounter block drifts from the prose beside it exactly as readily
    as a die size in a rule."""
    warnings = []
    for doc in _local(docs):
        numeric = _numeric_data(doc)
        if not numeric:
            continue
        prose = _strip_uncheckable(doc.body)
        for match in NUMBER_RE.finditer(prose):
            raw = match.group(1)
            value = float(raw) if "." in raw else int(raw)
            if value in IGNORE_BARE:
                continue
            hits = [k for k, v in numeric.items() if v == value]
            if hits:
                line_no = prose[: match.start()].count("\n") + 1
                warnings.append(
                    f"{doc.id}:~{line_no}: prose contains the literal '{raw}', which equals "
                    f"{hits[0]}. Interpolate it — {{{{ {hits[0]} }}}} — "
                    "or the two will drift apart."
                )
    return warnings


def check_unexplained_numbers(docs):
    """Second tier, and a weaker signal on purpose.

    check_hardcoded_numbers() catches prose that DUPLICATES a value
    ("4 tiles" where base_move_tiles is 4) — those will drift the moment
    you rebalance. It cannot catch prose that CONTRADICTS one ("6 tiles"
    where base_move_tiles is 4), because nothing in the text says which
    key that 6 was meant to be; the number simply does not match
    anything, which is indistinguishable from a number that was never a
    game value at all.

    So this flags any remaining bare number in a document that has
    numeric data, as something a human should glance at. Expect false
    positives ("a 1 in 6 chance", "the third door") — that is the cost
    of catching a wrong constant. Kept as a warning, never an error."""
    warnings = []
    for doc in _local(docs):
        numeric = _numeric_data(doc)
        if not numeric:
            continue
        values = set(numeric.values())
        prose = _strip_uncheckable(doc.body)
        for match in NUMBER_RE.finditer(prose):
            raw = match.group(1)
            value = float(raw) if "." in raw else int(raw)
            if value in IGNORE_BARE or value in values:
                continue  # in-values case is the error above, not this
            line_no = prose[: match.start()].count("\n") + 1
            warnings.append(
                f"{doc.id}:~{line_no}: prose contains '{raw}', which matches no value "
                f"in this document (has: {', '.join(sorted(numeric))}). If it is a game "
                "constant it belongs in frontmatter; if it is just prose, ignore this."
            )
    return warnings


def _reachable(docs, roots):
    reachable = set()

    def walk(doc_id):
        if doc_id in reachable:
            return
        reachable.add(doc_id)
        for target in docs[doc_id].includes:
            if target in docs:
                walk(target)

    for root in roots:
        if root in docs:
            walk(root)
    return reachable


def check_unincluded(docs, roots=("rulebook",)):
    """A document not reachable from any book root will not appear in
    any book. It still compiles into snippets — so this is a warning,
    not an error — but it is almost always an oversight: a rule written
    and then never wired into a chapter.

    A corpus with no roots at all does not run this check; that case is
    handled by the caller, because "there is no book" and "there is a
    book and its root is missing" are different situations and only the
    second is worth saying anything about."""
    missing = [r for r in roots if r not in docs]
    if missing:
        return [f"book root '{r}' not found; skipping reachability check" for r in missing]

    reachable = _reachable(docs, roots)
    named = "', '".join(roots)
    return [
        f"{doc.id}: not included anywhere under '{named}' — it will not appear in the book"
        for doc in _local(docs)
        if doc.id not in reachable
    ]


def check_duplicate_includes(docs, roots=("rulebook",)):
    """The same document reached by two different branches is not a cycle
    (so it compiles fine) but it duplicates that content in the book.
    Occasionally intentional — a rule genuinely restated in an appendix —
    so it warns rather than fails."""
    warnings = []
    for root in roots:
        counts = {}

        def walk(doc_id, stack):
            if doc_id in stack:
                return  # cycles are a hard error elsewhere; don't recurse here
            counts[doc_id] = counts.get(doc_id, 0) + 1
            for target in docs[doc_id].includes:
                if target in docs:
                    walk(target, stack + [doc_id])

        if root in docs:
            walk(root, [])
        warnings += [
            f"{doc_id}: included {n} times under '{root}' — it will appear {n} times in the book"
            for doc_id, n in sorted(counts.items())
            if n > 1
        ]
    return warnings


def check_link_orphans(docs, profile):
    """A document nothing links to is harder to find when reading.

    Only kinds whose `discovery` is `link` are checked. Structural
    documents are reached by inclusion and the book root by nothing at
    all; a document reached by lookup — a bestiary entry, an NPC — is
    found by looking in the index it belongs to, and requiring a
    cross-reference to each of them would mean one warning per creature
    forever."""
    linked_to = set()
    for doc in docs.values():
        linked_to |= doc.links_out
    return [
        f"{doc.id}: no other document links to this one — is it discoverable?"
        for doc in _local(docs)
        if profile.kinds[doc.kind].discovery == "link" and doc.id not in linked_to
    ]


def check_summary_length(docs, profile, max_chars=240):
    """Summaries render in tooltips and hover cards. A summary that runs
    long stops being a snippet and starts being an essay.

    A kind whose summary is optional is scaffolding rather than tooltip
    text, so it is exempt."""
    warnings = []
    for doc in _local(docs):
        if profile.kinds[doc.kind].summary == "optional":
            continue
        flat = " ".join(doc.summary.split())
        if len(flat) > max_chars:
            warnings.append(
                f"{doc.id}: summary is {len(flat)} chars (>{max_chars}); "
                "it will overflow in-game tooltips."
            )
    return warnings


def check_data_naming(docs):
    """Consistency check: data keys should be snake_case, since the game
    server reads them as identifiers."""
    warnings = []
    key_re = re.compile(r"^[a-z][a-z0-9_]*$")

    def walk(node, doc_id, block, prefix=""):
        if isinstance(node, (list, tuple)):
            for entry in node:
                walk(entry, doc_id, block, prefix)
            return
        if not isinstance(node, dict):
            return
        for k, v in node.items():
            if not key_re.match(str(k)):
                warnings.append(
                    f"{doc_id}: {block} key '{prefix}{k}' is not snake_case; "
                    "the server reads these as identifiers."
                )
            walk(v, doc_id, block, prefix=f"{prefix}{k}.")

    for doc in _local(docs):
        for block, body in (doc.data or {}).items():
            walk(body, doc.id, block)
    return warnings


# Kept under its old name: this was the only naming check when a
# document had exactly one data block and it was always called
# mechanics.
check_mechanics_naming = check_data_naming


def run_all(docs, profile: Profile = None, roots=None):
    """Returns (warnings, errors). Currently every lint is a warning
    except hardcoded numbers, which is the one worth failing a build
    over — it is the failure mode this whole format exists to prevent.

    Include CYCLES are not checked here: they are a hard error raised by
    the compiler itself, since an unwalkable graph stops the build
    before lint would ever run."""
    profile = profile or Profile.default()
    roots = tuple(profile.roots if roots is None else roots)

    errors = check_hardcoded_numbers(docs)
    warnings = []
    if profile.checks("unexplained"):
        warnings += check_unexplained_numbers(docs)
    # No roots is not a missing root. A corpus whose documents are
    # reached by reference rather than by inclusion has nothing to say
    # here, and saying it anyway would be one warning per document.
    if roots:
        if profile.checks("unincluded"):
            warnings += check_unincluded(docs, roots)
        if profile.checks("duplicate-includes"):
            warnings += check_duplicate_includes(docs, roots)
    if profile.checks("orphans"):
        warnings += check_link_orphans(docs, profile)
    if profile.checks("summary-length"):
        warnings += check_summary_length(docs, profile)
    if profile.checks("mechanics-naming"):
        warnings += check_data_naming(docs)
    return warnings, errors
