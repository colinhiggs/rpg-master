# profile.py - what a corpus declares about itself.
#
# The toolset used to hold six facts about a corpus as literals in its
# own source: which document kinds exist, which audience tag can be
# stripped, what a data block is called, which document the book is
# rooted at, what the linter checks, and which three files come out.
# Every one of those is a property of the corpus being compiled, not of
# the compiler, and a second corpus - an adventure rather than a
# ruleset - answers all six differently.
#
# So a corpus declares them, in <corpus>/corpus.yaml, and the compiler
# validates against the declaration. A corpus that declares nothing
# gets Profile.default(), which is exactly the behaviour the toolset
# had before this file existed; that is what keeps every existing
# ruleset compiling byte-for-byte identically.
#
# A driver may also build a Profile directly instead of writing the
# file. The file is the ergonomic form of the object, not a second
# mechanism.
#
# See CORPUS.md for the format, with worked examples.

from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

from .errors import RuleError

PROFILE_FILE = "corpus.yaml"

KEEP, DROP = "keep", "drop"
ACTIONS = (KEEP, DROP)
SHAPES = ("book", "snippets", "data")
SUMMARY_RULES = ("required", "optional")
DISCOVERY = ("link", "include", "lookup")
# Where a document's id has to come from. Either way the id is derivable
# from the path, which is the whole point: a document cannot be renamed
# on disk without its links noticing.
ID_SOURCES = ("stem", "directory")

# The lint checks a profile may switch off. check_hardcoded_numbers is
# deliberately not among them: it is the one the whole format exists to
# make possible, and a corpus that could turn it off would be a corpus
# where prose and data are allowed to disagree.
OPTIONAL_CHECKS = (
    "unexplained", "unincluded", "duplicate-includes",
    "orphans", "summary-length", "mechanics-naming",
)

DEFAULT_BLOCK = "mechanics"
DEFAULT_ROOT = "rulebook"


def _mapping(value, what: str) -> dict:
    """Accept a mapping, or nothing at all. `rule:` with no value is a
    kind that takes every default, which is worth being able to write."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise RuleError(f"{PROFILE_FILE}: {what} must be a map, not {type(value).__name__}")
    return value


def _sequence(value, what: str) -> tuple:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, (list, tuple)):
        raise RuleError(f"{PROFILE_FILE}: {what} must be a list, not {type(value).__name__}")
    return tuple(value)


def _no_unknown_keys(mapping: dict, allowed, what: str):
    unknown = set(mapping) - set(allowed)
    if unknown:
        raise RuleError(
            f"{PROFILE_FILE}: {what} does not understand "
            f"{', '.join(sorted(unknown))} (known: {', '.join(sorted(allowed))})"
        )


def _one_of(value, allowed, what: str):
    if value not in allowed:
        raise RuleError(
            f"{PROFILE_FILE}: {what} is {value!r}, which is not one of "
            f"{', '.join(repr(a) for a in allowed)}"
        )
    return value


@dataclass(frozen=True)
class Kind:
    """One document kind, and everything the toolset branches on.

    `discovery` says how a reader is expected to FIND a document, and it
    is the generic form of exemptions the linter used to hardcode. A
    `link` document is found by cross-reference, so nothing linking to
    it is worth a warning. An `include` document is book structure. A
    `lookup` document is found in an index - which is exactly why a
    bestiary creature was exempt before this was declarable.

    `audience` gives the whole document body a default audience tag, so
    that a corpus whose NPCs are wholly GM-only says that once here
    rather than wrapping every file. A target that drops that tag does
    not render the document at all, rather than rendering it empty."""

    name: str
    summary: str = "required"
    data: tuple = (DEFAULT_BLOCK,)
    discovery: str = "link"
    audience: str = None
    refs: tuple = ()
    id_from: str = "stem"

    @classmethod
    def from_mapping(cls, name: str, raw):
        raw = _mapping(raw, f"kind '{name}'")
        _no_unknown_keys(raw, ("summary", "data", "discovery", "audience", "refs",
                               "id_from"), f"kind '{name}'")
        return cls(
            name=name,
            summary=_one_of(raw.get("summary", "required"), SUMMARY_RULES,
                            f"kind '{name}' summary"),
            data=_sequence(raw.get("data", (DEFAULT_BLOCK,)), f"kind '{name}' data"),
            discovery=_one_of(raw.get("discovery", "link"), DISCOVERY,
                              f"kind '{name}' discovery"),
            audience=raw.get("audience"),
            refs=_sequence(raw.get("refs"), f"kind '{name}' refs"),
            id_from=_one_of(raw.get("id_from", "stem"), ID_SOURCES,
                            f"kind '{name}' id_from"),
        )


@dataclass(frozen=True)
class Reference:
    """Another corpus, joined to this one's id namespace, read from its
    build outputs and never from its sources - so a consumer depends on
    what the producing project says it may depend on."""

    path: str
    href: str = None
    name: str = None

    @classmethod
    def from_mapping(cls, raw):
        raw = _mapping(raw, "reference")
        _no_unknown_keys(raw, ("path", "href", "name"), "reference")
        if "path" not in raw:
            raise RuleError(f"{PROFILE_FILE}: a reference needs a 'path'")
        return cls(path=str(raw["path"]), href=raw.get("href"), name=raw.get("name"))


@dataclass(frozen=True)
class Target:
    """One output: a document filter, an audience policy, and a shape.

    `audiences` must carry a `default`, so that an audience tag added
    later gets this target's own safe answer rather than a surprise.
    Losing content from a book is the failure that matters there, so a
    book keeps by default; leaking a design note into a tooltip or a
    secret into a handout is the failure that matters in those, so they
    drop by default."""

    name: str
    shape: str
    audiences: dict = field(default_factory=lambda: {"default": KEEP})
    select: dict = None
    output: str = None
    root: str = None
    css: str = None
    blocks: tuple = None

    @classmethod
    def from_mapping(cls, name: str, raw):
        raw = _mapping(raw, f"target '{name}'")
        _no_unknown_keys(raw, ("shape", "audiences", "select", "output",
                               "root", "css", "blocks"), f"target '{name}'")
        if "shape" not in raw:
            raise RuleError(f"{PROFILE_FILE}: target '{name}' needs a 'shape'")
        shape = _one_of(raw["shape"], SHAPES, f"target '{name}' shape")

        audiences = _mapping(raw.get("audiences"), f"target '{name}' audiences")
        audiences = dict(audiences) if audiences else {}
        if "default" not in audiences:
            if shape == "data":
                # A data target carries no prose, so no audience tag can
                # leak through it and requiring a default would be
                # noise. It keeps rather than drops, because the thing
                # an audience still reaches here is a KIND's default
                # audience, and dropping those would quietly leave every
                # GM-only NPC out of the file the engine loads. A
                # consumer that genuinely wants a player-facing data
                # file says `audiences: { default: drop }` and means it.
                audiences["default"] = KEEP
            else:
                raise RuleError(
                    f"{PROFILE_FILE}: target '{name}' needs audiences.default "
                    f"({KEEP} or {DROP}), so that an audience tag added later "
                    "gets this target's own answer rather than a surprise"
                )
        for tag, action in audiences.items():
            _one_of(action, ACTIONS, f"target '{name}' audience '{tag}'")

        select = _mapping(raw.get("select"), f"target '{name}' select") or None
        if select:
            _no_unknown_keys(select, ("kind", "tags"), f"target '{name}' select")
            select = {k: _sequence(v, f"target '{name}' select.{k}")
                      for k, v in select.items()}

        blocks = raw.get("blocks")
        if shape == "data" and blocks is None:
            blocks = (DEFAULT_BLOCK,)
        return cls(
            name=name, shape=shape, audiences=audiences, select=select,
            output=raw.get("output"), root=raw.get("root"), css=raw.get("css"),
            blocks=_sequence(blocks, f"target '{name}' blocks") or None,
        )

    def action(self, tag: str) -> str:
        """What this target does with one audience tag."""
        return self.audiences.get(tag, self.audiences["default"])

    def selects(self, doc, profile) -> bool:
        """Whether a document appears in this target at all.

        Two ways it may not: the target filters by kind or tag, or the
        document's kind carries a default audience this target drops. A
        wholly GM-only NPC is absent from a player handout rather than
        present and empty."""
        if self.select:
            kinds = self.select.get("kind")
            if kinds and doc.kind not in kinds:
                return False
            tags = self.select.get("tags")
            if tags and not set(tags) & set(doc.tags or ()):
                return False
        kind = profile.kinds.get(doc.kind)
        if kind is not None and kind.audience and self.action(kind.audience) == DROP:
            return False
        return True


@dataclass
class Profile:
    kinds: dict
    audiences: tuple = ()
    roots: tuple = ()
    targets: dict = field(default_factory=dict)
    references: tuple = ()
    lint: dict = field(default_factory=dict)
    source: str = "(default)"

    # -----------------------------------------------------------------
    @classmethod
    def default(cls) -> "Profile":
        """The profile a corpus gets when it declares nothing: exactly
        the behaviour this toolset had before profiles existed."""
        return cls(
            kinds={
                "rule": Kind("rule"),
                "section": Kind("section", summary="optional", discovery="include"),
                "creature": Kind("creature", discovery="lookup"),
            },
            audiences=("book-only",),
            roots=(DEFAULT_ROOT,),
            targets={
                "book": Target("book", "book", {"default": KEEP},
                               root=DEFAULT_ROOT, output="build/book.html"),
                "snippets": Target("snippets", "snippets", {"default": DROP},
                                   output="build/snippets.json"),
                "mechanics": Target("mechanics", "data", {"default": KEEP},
                                    blocks=(DEFAULT_BLOCK,),
                                    output="build/mechanics.json"),
            },
        )

    @classmethod
    def load(cls, corpus_dir) -> "Profile":
        """Read <corpus_dir>/corpus.yaml, or return the default."""
        path = Path(corpus_dir) / PROFILE_FILE
        if not path.exists():
            return cls.default()
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            raise RuleError(f"{path}: invalid YAML - {e}")
        return cls.from_mapping(raw, source=str(path))

    @classmethod
    def from_mapping(cls, raw, source: str = "(inline)") -> "Profile":
        raw = _mapping(raw, "corpus profile")
        _no_unknown_keys(raw, ("kinds", "audiences", "roots", "targets",
                               "references", "lint"), "corpus profile")
        base = cls.default()

        if "kinds" in raw:
            kinds = {name: Kind.from_mapping(name, body)
                     for name, body in _mapping(raw["kinds"], "kinds").items()}
        else:
            kinds = base.kinds
        if not kinds:
            raise RuleError(f"{PROFILE_FILE}: a corpus needs at least one kind")

        audiences = tuple(_sequence(raw["audiences"], "audiences")) \
            if "audiences" in raw else base.audiences
        for kind in kinds.values():
            if kind.audience and kind.audience not in audiences:
                raise RuleError(
                    f"{PROFILE_FILE}: kind '{kind.name}' has audience "
                    f"'{kind.audience}', which is not in audiences"
                )

        roots = tuple(_sequence(raw["roots"], "roots")) if "roots" in raw else base.roots

        if "targets" in raw:
            targets = {name: Target.from_mapping(name, body)
                       for name, body in _mapping(raw["targets"], "targets").items()}
        else:
            targets = base.targets
        for target in targets.values():
            for tag in target.audiences:
                if tag != "default" and tag not in audiences:
                    raise RuleError(
                        f"{PROFILE_FILE}: target '{target.name}' names audience "
                        f"'{tag}', which the corpus does not declare"
                    )

        references = tuple(Reference.from_mapping(r)
                           for r in _sequence(raw.get("references"), "references"))

        lint = {}
        for name, on in _mapping(raw.get("lint"), "lint").items():
            if name not in OPTIONAL_CHECKS:
                raise RuleError(
                    f"{PROFILE_FILE}: lint check '{name}' is not one of "
                    f"{', '.join(OPTIONAL_CHECKS)}. The hardcoded-number check "
                    "cannot be switched off; it is why the format exists."
                )
            lint[name] = bool(on)

        return cls(kinds=kinds, audiences=audiences, roots=roots, targets=targets,
                   references=references, lint=lint, source=source)

    # -----------------------------------------------------------------
    def kind(self, name: str) -> Kind:
        return self.kinds[name]

    def blocks_for(self, kind_name: str) -> tuple:
        kind = self.kinds.get(kind_name)
        return kind.data if kind else (DEFAULT_BLOCK,)

    def checks(self, name: str) -> bool:
        """Whether an optional lint check runs. On unless switched off."""
        return self.lint.get(name, True)

    def target(self, name: str) -> Target:
        if name not in self.targets:
            raise RuleError(
                f"no target '{name}' in this corpus profile "
                f"(has: {', '.join(sorted(self.targets)) or 'none'})"
            )
        return self.targets[name]

    def with_roots(self, *roots) -> "Profile":
        """A copy rooted somewhere else. A driver compiling one adventure
        at a time roots each build at that adventure's own document."""
        return replace(self, roots=tuple(roots))
