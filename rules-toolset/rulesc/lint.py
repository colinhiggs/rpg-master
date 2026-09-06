# lint.py — the checks that keep "one source of truth" actually true.
#
# The compiler will happily build a book whose prose says "you get 3
# actions" while mechanics says actions_per_turn: 1. Nothing in the
# format prevents that — only this linter does. Treat lint failures as
# build failures; that is the entire point of the architecture.

import re

# Numbers so generic that matching them means nothing. "1" appears in
# ordinary prose constantly ("one tile", "a 1 in 6 chance") and flagging
# every instance would train you to ignore the linter.
IGNORE_BARE = {0, 1}

NUMBER_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])")
INTERP_RE = re.compile(r"\{\{[^}]*\}\}")
CODE_RE = re.compile(r"`[^`]*`")


def _numeric_mechanics(mechanics, prefix=""):
    """Flatten mechanics into {dotted_key: number} for numeric leaves."""
    out = {}
    for k, v in (mechanics or {}).items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_numeric_mechanics(v, prefix=f"{key}."))
        elif isinstance(v, bool):
            continue  # bools aren't numbers for this purpose
        elif isinstance(v, (int, float)):
            out[key] = v
    return out


def _strip_uncheckable(body: str) -> str:
    """Remove regions where a literal number is legitimate: already-
    interpolated expressions, and inline code (dice notation like `XdY+Z`
    or a regex pattern is not prose restating a constant)."""
    body = INTERP_RE.sub(" ", body)
    body = CODE_RE.sub(" ", body)
    return body


def check_hardcoded_numbers(rules):
    """The core drift check: a bare number in prose that equals one of
    this rule's own mechanics values is almost always a value that
    should have been interpolated."""
    warnings = []
    for rule in rules.values():
        numeric = _numeric_mechanics(rule.mechanics)
        if not numeric:
            continue
        prose = _strip_uncheckable(rule.body)
        for match in NUMBER_RE.finditer(prose):
            raw = match.group(1)
            value = float(raw) if "." in raw else int(raw)
            if value in IGNORE_BARE:
                continue
            hits = [k for k, v in numeric.items() if v == value]
            if hits:
                line_no = prose[: match.start()].count("\n") + 1
                warnings.append(
                    f"{rule.id}:~{line_no}: prose contains the literal '{raw}', which equals "
                    f"mechanics.{hits[0]}. Interpolate it — {{{{ mechanics.{hits[0]} }}}} — "
                    "or the two will drift apart."
                )
    return warnings


def check_unexplained_numbers(rules):
    """Second tier, and a weaker signal on purpose.

    check_hardcoded_numbers() catches prose that DUPLICATES a mechanic
    ("4 tiles" where base_move_tiles is 4) — those will drift the moment
    you rebalance. It cannot catch prose that CONTRADICTS one ("6 tiles"
    where base_move_tiles is 4), because nothing in the text says which
    mechanic that 6 was meant to be; the number simply does not match
    anything, which is indistinguishable from a number that was never a
    mechanic at all.

    So this flags any remaining bare number in a rule that has numeric
    mechanics, as something a human should glance at. Expect false
    positives ("a 1 in 6 chance", "the third door") — that is the cost
    of catching a wrong constant. Kept as a warning, never an error."""
    warnings = []
    for rule in rules.values():
        numeric = _numeric_mechanics(rule.mechanics)
        if not numeric:
            continue
        values = set(numeric.values())
        prose = _strip_uncheckable(rule.body)
        for match in NUMBER_RE.finditer(prose):
            raw = match.group(1)
            value = float(raw) if "." in raw else int(raw)
            if value in IGNORE_BARE or value in values:
                continue  # in-values case is the error above, not this
            line_no = prose[: match.start()].count("\n") + 1
            warnings.append(
                f"{rule.id}:~{line_no}: prose contains '{raw}', which matches no mechanic "
                f"in this rule (has: {', '.join(sorted(numeric))}). If it is a game "
                "constant it belongs in mechanics; if it is just prose, ignore this."
            )
    return warnings


def check_unincluded(docs, root_id="rulebook"):
    """A document not reachable from the book root will not appear in the
    book at all. It still compiles into snippets — so this is a warning,
    not an error — but it is almost always an oversight: a rule written
    and then never wired into a chapter."""
    if root_id not in docs:
        return [f"book root '{root_id}' not found; skipping reachability check"]

    reachable = set()

    def walk(doc_id):
        if doc_id in reachable:
            return
        reachable.add(doc_id)
        for target in docs[doc_id].includes:
            if target in docs:
                walk(target)

    walk(root_id)
    return [
        f"{doc.id}: not included anywhere under '{root_id}' — it will not appear in the book"
        for doc in docs.values()
        if doc.id not in reachable
    ]


def check_duplicate_includes(docs, root_id="rulebook"):
    """The same document reached by two different branches is not a cycle
    (so it compiles fine) but it duplicates that content in the book.
    Occasionally intentional — a rule genuinely restated in an appendix —
    so it warns rather than fails."""
    counts = {}

    def walk(doc_id, stack):
        if doc_id in stack:
            return  # cycles are a hard error elsewhere; don't recurse here
        counts[doc_id] = counts.get(doc_id, 0) + 1
        for target in docs[doc_id].includes:
            if target in docs:
                walk(target, stack + [doc_id])

    if root_id in docs:
        walk(root_id, [])

    return [
        f"{doc_id}: included {n} times under '{root_id}' — it will appear {n} times in the book"
        for doc_id, n in sorted(counts.items())
        if n > 1
    ]


def check_link_orphans(docs):
    """A rule nothing links to is harder to find when reading. Sections
    and the book root are expected to have no inbound links, so they are
    exempt, and so are creatures: a bestiary entry is found by looking
    in the bestiary, and requiring a cross-reference to each of them
    would mean one warning per creature forever."""
    linked_to = set()
    for doc in docs.values():
        linked_to |= doc.links_out
    return [
        f"{doc.id}: no other document links to this one — is it discoverable?"
        for doc in docs.values()
        if doc.kind == "rule" and doc.id not in linked_to
    ]


def check_summary_length(rules, max_chars=240):
    """Summaries render in tooltips and hover cards. A summary that runs
    long stops being a snippet and starts being an essay."""
    warnings = []
    for rule in rules.values():
        if rule.kind == "section":
            continue  # section summaries are book scaffolding, not tooltips
        flat = " ".join(rule.summary.split())
        if len(flat) > max_chars:
            warnings.append(
                f"{rule.id}: summary is {len(flat)} chars (>{max_chars}); "
                "it will overflow in-game tooltips."
            )
    return warnings


def check_mechanics_naming(rules):
    """Consistency check: mechanics keys should be snake_case, since the
    game server reads them as identifiers."""
    warnings = []
    key_re = re.compile(r"^[a-z][a-z0-9_]*$")

    def walk(mech, rule_id, prefix=""):
        for k, v in (mech or {}).items():
            if not key_re.match(str(k)):
                warnings.append(
                    f"{rule_id}: mechanics key '{prefix}{k}' is not snake_case; "
                    "the server reads these as identifiers."
                )
            if isinstance(v, dict):
                walk(v, rule_id, prefix=f"{prefix}{k}.")

    for rule in rules.values():
        walk(rule.mechanics, rule.id)
    return warnings


def run_all(docs, root_id="rulebook"):
    """Returns (warnings, errors). Currently every lint is a warning
    except hardcoded numbers, which is the one worth failing a build
    over — it is the failure mode this whole format exists to prevent.

    Include CYCLES are not checked here: they are a hard error raised by
    the compiler itself, since an unwalkable graph stops the build
    before lint would ever run."""
    errors = check_hardcoded_numbers(docs)
    warnings = []
    warnings += check_unexplained_numbers(docs)
    warnings += check_unincluded(docs, root_id)
    warnings += check_duplicate_includes(docs, root_id)
    warnings += check_link_orphans(docs)
    warnings += check_summary_length(docs)
    warnings += check_mechanics_naming(docs)
    return warnings, errors
