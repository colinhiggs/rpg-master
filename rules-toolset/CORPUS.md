# Corpora, profiles and targets

**Status: proposed. Nothing described here is built.** This document is
the shape being agreed before the code is written, per `SHARING.md` —
the adventures project's driver is written against exactly this, so it
is cheaper to agree it once than to follow it. When it lands, this
banner goes and this file becomes the reference.

## The one idea

Today the toolset compiles a **ruleset**: a directory whose documents
have three possible `kind`s, one audience tag, one data block called
`mechanics`, one book root called `rulebook`, and three output files.
Every one of those is a constant in the toolset's own source.

The proposal is that all six become a **corpus profile** — a
declaration a corpus makes about itself, which the toolset validates
against instead of against its own literals. A ruleset is then one
corpus profile among others, and the one a corpus gets when it declares
nothing is exactly today's behaviour.

That last clause is the whole safety argument. `demo` and `ico` declare
nothing, get the default profile, and compile byte-for-byte identically
— which is a testable claim, not an intention, and the test is in the
plan at the bottom.

## Where a profile lives

`<corpus>/corpus.yaml`, optional. Absent means the default profile.

The toolset reads it into a `Profile` object; a driver may also build
one directly and pass it in, which is what makes the adventures-side
compiler a configuration file plus a `main()` rather than a second
parser. The file is the ergonomic form of the object, not a separate
mechanism.

## The default profile

This is what `demo` and `ico` get today, written out in the new
vocabulary. It is here so the format can be judged against behaviour
that already exists rather than against behaviour nobody has seen.

```yaml
kinds:
  rule:     { summary: required, data: [mechanics], discovery: link }
  section:  { summary: optional, data: [mechanics], discovery: include }
  creature: { summary: required, data: [mechanics], discovery: lookup }

audiences: [book-only]

roots: [rulebook]

targets:
  book:
    shape: book
    root: rulebook
    audiences: { default: keep }
    output: build/book.html
  snippets:
    shape: snippets
    audiences: { default: drop }
    output: build/snippets.json
  mechanics:
    shape: data
    blocks: [mechanics]
    output: build/mechanics.json
```

Every field has a default, so a corpus declares only what differs. A
`corpus.yaml` containing only `audiences: [book-only, spoiler]` keeps
all three kinds, the root and the three targets.

## 1. Kinds

`KINDS = ("rule", "section", "creature")` at `rulesc.py:65` becomes the
`kinds:` map above. Three properties, each of which exists because the
current code already branches on kind somewhere:

| Property | Values | Default | What consults it today |
|---|---|---|---|
| `summary` | `required`, `optional` | `required` | `rulesc.py:125`, and `lint.check_summary_length` skips sections |
| `data` | list of block names | `[mechanics]` | see below |
| `discovery` | `link`, `include`, `lookup` | `link` | `lint.check_link_orphans` (`lint.py:168`) |

`discovery` says how a reader is expected to *find* a document, and it
is the generic form of the exemptions already hardcoded in the linter.
A `link` document is found by cross-reference, so nothing linking to it
is worth a warning. An `include` document is book structure, reached by
`{% include %}`. A `lookup` document is found in an index — which is
exactly the comment already sitting above `check_link_orphans`
explaining why creatures are exempt: "a bestiary entry is found by
looking in the bestiary".

So `kind: npc` stops being a fatal error, and an npc is `lookup` for
the same reason a creature is.

## 2. Data blocks, and my answer on `encounter:`

**You asked whether the answer is "adventures should call it
`mechanics:`". I think it is not, and that declared block names are
both the more correct and the cheaper answer.**

The model: a document carries a *map of named data blocks* rather than
one block called `mechanics`. Today every document has exactly one,
named `mechanics`, which is why the name is invisible. A kind declares
which blocks its documents may carry:

```yaml
kinds:
  npc:   { data: [mechanics] }
  scene: { data: [encounter] }
```

The first segment of an interpolation path already names the block —
`{{ mechanics.grid_size }}` — so `{{ encounter.checks.spot-ambush.dc }}`
needs no new syntax, only a lookup that does not assume the name. The
same is true of `{% table encounter.checks columns=skill,dc %}`.

Three reasons to prefer this over renaming on the adventures side:

- **`mechanics` means something.** In a rule document it is "the
  numbers this rule *is*" — the values `sim/` measures and the server
  runs on. A scene's `encounter:` is a structure of references and
  thresholds. Putting both under one key would make `mechanics.json`
  claim that an encounter is a game constant, and would make
  `based_on` (item 6) inherit encounters, which is meaningless.
- **It is what makes item 4 work at all.** `check_hardcoded_numbers`
  flattens `doc.mechanics` and compares against prose. Point it at
  every declared block instead and `dc: 14` beside "DC 14" in the ford
  scene becomes the hard error you want. Renaming the block to
  `mechanics` would also achieve that, but only by conceding the point
  above.
- **It costs one line per kind.** The toolset learns "blocks have
  names", not "there is a block called encounter".

Two details this needs, both small:

- **Lists in a path.** `checks:` is a list of maps. `_lookup_path`
  gains index support so `encounter.checks.0.dc` resolves, and — because
  each check carries an `id:` — so does `encounter.checks.spot-ambush.dc`.
  I recommend authoring with the id form and would make the positional
  form work only because it falls out for free: inserting a check at the
  front of the list must not silently repoint every interpolation in the
  prose. Addressing a list of maps by each element's `id` is the same
  convention the toolset already uses for documents themselves.
  `lint.check_hardcoded_numbers` walks into lists for the same reason.
- **`doc.mechanics` stays.** As a property returning
  `doc.data.get("mechanics", {})`, so `build_mechanics`, the linter,
  `sim/`, and every existing test keep working unchanged.

An undeclared block in frontmatter becomes an error rather than being
silently ignored, which it is today. That catches `mechanic:` for
`mechanics:`.

## 3. Audiences and targets — one mechanism, parameterised

This is the item `SHARING.md` already names, and the one you asked to
see before code. Today there is one tag with its name written into four
places: the two regexes at `rulesc.py:62-63`, the validator that knows
its name (`check_book_only_markers`, `rulesc.py:197`), and the strip and
unwrap functions (`rulesc.py:230, 235`). The two "targets" are implied
by which of the two functions the caller happens to call.

**A corpus declares its audience tags. A target declares what it does
with each of them.**

```yaml
audiences: [gm-only]

targets:
  gm-module:
    shape: book
    audiences: { default: keep }
  player-handout:
    shape: book
    select: { kind: [handout, scene] }
    audiences: { default: drop }
```

An action is `keep` (drop the markers, keep the content — today's
`unwrap_book_only`) or `drop` (remove the block entirely — today's
`strip_book_only`).

Four decisions inside that, each with a reason:

**`default:` is required on every target, and per-tag overrides are
optional.** Not "unlisted tags are kept" and not "unlisted tags are
dropped": each target picks its own safe direction. `snippets` defaults
to `drop`, so a tag added later cannot leak a design note into a
tooltip. `player-handout` defaults to `drop`, so a tag added later
cannot leak a secret to a player. `book` and `gm-module` default to
`keep`, because losing content there is the failure that matters. The
declaration is two lines and it means an author who forgets a tag gets
the conservative answer rather than a surprise.

**An unrecognised `{% word %}` becomes a build error.** You noted that
`{% gm-only %}` currently passes through as literal text, which is
worse than an error, and I agree — it is the same failure the whole
format exists to prevent, in a different costume. The check is: any
`{% ... %}` whose first word is not `include`, not `table`, and not a
declared audience tag or its `end` form is an error naming the document
and the word. I verified this is safe to add to both existing rulesets:
across all 54 documents in `demo` and `ico` exactly four directive
words occur — `include` (52), `book-only` (41), `endbook-only` (41) and
`table` (19). Nothing else exists to break.

**Same-tag nesting stays an error; different-tag nesting is allowed.**
`{% gm-only %}` inside `{% book-only %}` is meaningful and falls out of
the regex correctly provided drops are applied before keeps, which is
well defined and which I would state in a test rather than leave to
luck. Nesting a tag inside itself remains what it is today: an error,
because the close is ambiguous. The unclosed and stray-close checks
generalise per tag with no change of meaning.

**A kind may carry a default audience.** This is the generic form of
your folder conventions, and I think it belongs in the toolset:

```yaml
kinds:
  npc:  { discovery: lookup, audience: gm-only }
  note: { summary: optional, audience: gm-only }
```

meaning the whole body of such a document behaves as if wrapped in that
tag. It is stated in toolset vocabulary — a kind, an audience — and any
ruleset could use it (a supplement might make every `errata` document
`book-only`). Without it, every NPC file needs a wrapper around its
whole body, which is exactly the per-file tagging your README says is
not needed.

Note what it does *not* do: it does not make the folder meaningful. The
document says `kind: npc` in its frontmatter and happens to live in
`npcs/`. Deriving a document's kind from its location would make a
file's meaning depend on where it sits, and the flat id namespace is a
deliberate rejection of exactly that.

## 4. Build targets — three shapes, parameterised

`build.py` writes exactly three files from three hardcoded calls.
Targets become the `targets:` map above; `build.py` runs whichever the
profile declares.

The result I want to lead with, because it settles the `SHARING.md`
question about the interface: **your four targets need no new output
shape.** There are three shapes and they are the three that exist.

| Your target | Shape | Parameters |
|---|---|---|
| `gm-module` | `book` | `audiences: { default: keep }` |
| `player-handout` | `book` | `select: { kind: [handout, scene] }`, `default: drop` |
| `player-booklet` | `book` | same selection, plus `css:` |
| `engine-data` | `data` | `blocks: [mechanics, encounter]` |

A target is exactly what you described — a document filter, an audience
policy, and an output shape — plus the shape's own parameters:

- **`shape`** — `book`, `snippets` or `data`. Not extensible from a
  profile: a new shape is Python, and is a change to the interface that
  gets agreed the way this document is being agreed.
- **`select`** — `{ kind: [...] }` and `{ tags: [...] }`. Kind and tag
  are toolset vocabulary; "the `handouts/` folder" is not, and does not
  need to be, because a handout says `kind: handout`.
- **`audiences`** — as above.
- **shape parameters** — `root:` and `css:` for `book`, `blocks:` for
  `data`. `BOOK_CSS` becomes the default value of `css:` rather than a
  module constant, which is what makes `player-booklet` a parameter
  rather than a fourth shape.

**What changes in the three existing shapes: nothing.** `build_book`,
`build_snippets` and `build_mechanics` keep their bodies. What changes
is that their arguments come from a profile instead of from three
hardcoded calls, and the default profile supplies today's values. So
this item is additive and there is no collision to describe — which was
the other answer you asked for if I found one.

One internal shape does change, and it is worth naming because
`test_rules.py` touches it. Today `compiled[id]` holds two
pre-rendered forms, `linked` (unwrapped) and `html` (stripped),
because there were exactly two audience policies. With N targets they
cannot be precomputed, so `compiled[id]` holds the marked-up text once
and each target applies its own policy. That is the compiler's internal
structure, not an output shape, and no consumer outside `tools/` reads
it.

## 5. References into another corpus

The third thing you asked to see before code. `[[goblin]]` and
`[[skill-list]]` in an adventure name documents in the ruleset, and
`resolve_links` (`rulesc.py:545`) and `resolve_interpolations`
(`rulesc.py:308`) both resolve within one `docs` dict.

**A corpus may declare other corpora that join its id namespace,
loaded from their build outputs.**

```yaml
references:
  - path: ../../rules-ico/build
    href: "../rules-ico/build/book.html#rule-{id}"
```

The toolset reads `snippets.json` and `mechanics.json` from that
directory into read-only documents — id, title, kind, summary and data
blocks — and adds them to the same namespace the local documents are
in. Which means:

- `[[goblin]]`, `{{ goblin:mechanics.typical_number }}`,
  `{% table goblin:mechanics.skills %}` and `based_on: goblin` all work
  with **no new syntax at all**, because none of them ever cared where
  a document came from.
- A build output is the only thing read, so an adventure depends on
  exactly what the rules `SHARING.md` says it may depend on.

**The namespace is flat and a collision is an error.** I considered
namespacing (`[[rules:goblin]]`) and rejected it: your real documents
write `[[skill-list]]` beside `[[npc-grask]]` with no prefix, and the
toolset's existing rule is already "one flat id namespace, a duplicate
is an error". Extending that rule across the seam keeps one rule
instead of two, and it means adding a document to the ruleset whose id
an adventure already uses fails loudly at the next build instead of
quietly changing what a link means. The cost is that you cannot
deliberately shadow a ruleset document, which I think is the right
thing to be unable to do.

**Unresolvable is an error.** This already is how it works — a bad
`[[link]]` or `{{ interpolation }}` appends to `errors`, and `build.py`
writes no output when `errors` is non-empty — and it extends unchanged.
A missing or unbuilt reference directory is its own error naming the
build command that fixes it, in the shape `sim/model.py` already uses
for `RulesNotBuilt`.

**The version lands in the output**, under the `_`-prefixed convention:

```json
"_references": [
  { "name": "rules-ico", "version": "1.0.4", "source": "rules-ico/build" }
]
```

in `snippets.json` and in the `data` shape, and as a visible line in the
book shape's subtitle — a printed GM module should say which rules it
was built against without going near a repository, which is the same
argument that put the version in the subtitle to begin with. A
referenced corpus with no `_version` is a warning and records `null`;
an unversioned dependency is worth being told about. **A corpus that
declares no references emits no `_references` key**, which is what keeps
`demo` and `ico` byte-identical.

## 6. `based_on`

A document may name another whose data blocks it inherits. The merge is
what you specified: scalars replace, nested maps merge key-by-key, lists
replace wholesale. Block by block, by name — the parent's `mechanics`
merges into the child's `mechanics` — so no extra declaration is needed,
and inheriting a scene's `encounter` into a creature is not something
that can happen by accident.

I agree it belongs in the toolset rather than the driver, for the reason
you gave: a bestiary variant (a dire wolf from a wolf) wants it as much
as a named boss does. It is stated entirely in documents and data
blocks, and it is inert — a corpus in which nothing says `based_on` is
unaffected.

Four details:

- **Resolution happens at load, before lint and before interpolation.**
  So `{{ mechanics.stamina }}` in Grask's prose interpolates the
  inherited value, and — more importantly — an NPC whose prose restates
  a number it *inherited* is caught by `check_hardcoded_numbers`. If
  inheritance ran later, that drift would be invisible.
- **The emitted block is the resolved one**, because `engine-data` needs
  a whole stat block. Nothing in `demo` or `ico` uses `based_on`, so
  `mechanics.json` is unaffected in both.
- **A `based_on` naming a document that does not exist is an error**, as
  you asked. So is a cycle, detected with the same walk the include
  graph already uses.
- **It resolves across the seam**, so `based_on: goblin` reaches the
  ruleset's bestiary through item 5.

## 7. Lint against many roots, or none

`run_all(docs, root_id="rulebook")` becomes `run_all(docs, profile)`,
reading `roots:` (a list) and a `lint:` map that switches individual
checks off.

- `roots: []` **skips** `check_unincluded` and `check_duplicate_includes`
  rather than reporting a missing root. There is a real difference
  between "this corpus has no book" and "this corpus has a book and I
  cannot find its root", and only the second is worth a warning.
- Several roots: reachability is the union, and duplicate-include counts
  are per root.
- `check_hardcoded_numbers` is not switchable and stays a hard error for
  every corpus. It is the reason the format exists.

For your corpus I expect `roots: []` with `unincluded`,
`duplicate-includes` and `orphans` off, because an adventure's documents
are reached through `connections:` and `encounter:` rather than through
`{% include %}` — a graph, not a tree.

**Which raises the one place I think you are about to write driver code
that could be configuration instead.** Validating that
`connections.next` names a scene that exists is, stated generically, "a
frontmatter path holds a document id; check that it resolves". That is
expressible without any game in it:

```yaml
kinds:
  scene:
    data: [encounter]
    refs:
      - encounter.npcs
      - encounter.connections.next
      - encounter.connections.branches.*.to
```

I am not counting this as part of what you asked for and I would build
it last, but it is the single addition that most reduces the driver to a
configuration file, and it is generic — a bestiary could declare
`refs: [mechanics.variant_of]`. Say if you want it in scope.

It does **not** cover `on_success: notice-ambush-early`. That names an
outcome, not a document, and outcomes are the adventure's own schema.
Checking those belongs in the driver, and I would leave it there.

## 8. The import surface

You asked what the supported import looks like from a submodule
checkout at `rpg-master/rules-toolset/`. The honest first sentence is
that a directory has to be on `sys.path` before anything in it can be
imported, and with no network and no install step there is no way around
that. The question is only whether it is one deliberate line in the
driver or surgery repeated everywhere.

**The proposal: `rules-toolset/` gains a real package, and `tools/`
becomes thin command-line wrappers over it.**

```
rules-toolset/
  rulesc/
    __init__.py     the public API, and the only thing a driver imports
    compile.py      was tools/rulesc.py
    lint.py         was tools/lint.py
    profile.py      new — Profile, Kind, Target, parsing corpus.yaml
    targets.py      new — the three output shapes
  tools/
    build.py        CLI over rulesc
    test_rules.py   CLI over rulesc
```

and the driver, once, at the top:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "rpg-master" / "rules-toolset"))

from rulesc import Profile, compile_corpus, build_target
```

The alternative is to leave the layout alone and have the driver put
`tools/` on the path, which works today. I recommend against it: it
drops `build`, `lint` and `test_rules` into the driver's namespace, so
an adventure compiler cannot have a `build.py` of its own, and it means
the second compiler imports implementation modules rather than a stated
API. Now that there are two compilers, that API is a contract and wants
a surface of its own.

**This does move files, which is the one part of the proposal that is
not purely additive.** `git log --follow` still works, and nothing
outside `rules-toolset/` imports these modules — `rules_runtime.py` is
imported by nothing at all, and `sim/` reads only `mechanics.json`. Say
if you would rather I did not, and I will keep the flat layout and
document the `tools/` import instead.

The API, in full:

```python
profile = Profile.load(corpus_dir)              # corpus.yaml, or the default
corpus  = compile_corpus(*dirs, profile=profile)
if corpus.errors: ...                           # .errors .warnings .docs .compiled
build_target(corpus, "gm-module", out_path)     # one target, one file
```

`compile_docs(*dirs, root_id=...)` keeps its current signature and tuple
return, so nothing that calls it today has to change.

## 9. Demonstrating this in `rules/demo/`

You were right that this needs thought: most of these features are
corpus-shaped, and `demo` is one corpus with one root. My answer is
both, split by what each is good at.

**Throwaway corpora carry the behaviour**, via `with_temp_rules()` as
the suite already does for everything except the integration smoke test.
A corpus with two audience tags, a corpus with no root, a corpus whose
kinds carry two differently-named blocks, a corpus that resolves a
reference into another corpus's build output — each is three files and
asserts one thing. A permanent fixture whose whole job is to have no
book root would be a strange thing to keep.

**`rules/demo/` gains a sibling corpus for the demonstration**, because
`SHARING.md` condition 3 says a feature is *demonstrated* there, and
demonstrated means a person can read it — a passing test is not a worked
example. I propose `rules/demo-supplement/`: a small corpus with a
`corpus.yaml`, one new kind, a second audience tag, a second data block,
and a reference into `demo`'s own build output. A supplement is a
generic publishing idea rather than a game, so it stays inside the rule
that keeps the toolset shareable.

That needs a row in `SHARING.md`'s write-surface table, since it says
`rules/<other>/` belongs to nobody and names `rules/demo/` as the
exception. There would be two exceptions, for the same reason.

I would also add `corpus.yaml` to `rules/demo/` itself, spelling out the
default profile explicitly. It changes no behaviour by construction, and
it makes the claim "the default profile is today's behaviour" something
a reader can check rather than take on trust.

## 10. What I would change from what you asked for

- **`encounter:` stays `encounter:`** (item 4). Reasoning in section 2.
- **Two additions you did not ask for**, both because they are
  expressible without any game in them: a kind's default audience
  (section 3), which is the generic form of your folder conventions, and
  `refs:` (section 7), which is the one that most reduces the driver to
  configuration. The first I would build; the second only if you want it
  in scope.
- **One thing I would leave in your driver**: outcome ids
  (`on_success`, `when`) and the adventure graph's own semantics — and
  the per-adventure output layout, since the toolset takes an output
  path per target rather than templating one.
- **Ruleset lookup without `--path`** (your non-blocker): a
  `RULESET_PATH` environment variable, `os.pathsep`-separated, appended
  to the two-place search. One line in `find_ruleset`, inert when unset,
  and it serves both tools at once because `test_rules.py` already
  imports that lookup rather than repeating it.

## 11. How "nothing changes" gets proved

Not asserted — measured, the same way a PATCH release is proved by its
diff rather than by its changelog:

1. Build `demo` and `ico` on `main`; keep the six output files.
2. Build both on this branch, with no `corpus.yaml` anywhere.
3. `diff` must be empty for all six. Not equivalent — identical.
4. Then add `corpus.yaml` to `demo` spelling out the default profile,
   rebuild, and diff again. Also empty, which is what proves the
   declaration format describes the default rather than approximating
   it.
5. `python3 tools/test_rules.py` and `python3 tools/test_rules.py ico`
   both pass, and the suite grows a section per item above.

And the constraint you set, which I expect to hold: **nothing in
`rules/ico/` needs to change.** Its documents use six frontmatter keys
and four directive words, every one of which the default profile covers.
If I find myself wanting to edit it, I will stop and say what pushed me
there.
