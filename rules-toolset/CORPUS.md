# Corpora, profiles and targets

A **corpus** is a directory of documents this toolset compiles. A
ruleset is one shape of corpus; an adventure is another.

Six things used to be constants in this toolset's own source: which
document kinds exist, which audience tag could be stripped, what a data
block was called, where the book was rooted, what the linter checked,
and which three files came out. Every one of those is a property of the
corpus being compiled rather than of the compiler, and a corpus that is
not a ruleset answers all six differently.

So a corpus declares them, in `<corpus>/corpus.yaml`, and the compiler
validates against the declaration instead of against its own literals.

**A corpus that declares nothing gets exactly the behaviour this toolset
had before profiles existed.** That is not a stated intention but a
measured one: `demo` and `ico` build byte-identical `book.html`,
`snippets.json` and `mechanics.json` with the profile mechanism in place
and with `demo` declaring the default profile explicitly, and the test
suite checks the claim from both ends.

`rules/demo/corpus.yaml` is the default profile written out — a file
that changes nothing, kept because a format is easier to judge against
behaviour you already know. `rules/demo-supplement/` is the worked
example of a corpus that is not a ruleset.

---

## `corpus.yaml`

Every field has a default, so a corpus declares only what differs.

### `kinds`

```yaml
kinds:
  scene:
    summary: required        # required | optional
    data: [encounter]        # the frontmatter blocks this kind may carry
    discovery: include       # link | include | lookup
    refs:                    # paths inside those blocks holding document ids
      - encounter.foes
      - encounter.branches.*.to
  npc:
    data: [mechanics]
    discovery: lookup
    audience: gm-only        # the whole body carries this audience
  adventure:
    id_from: directory       # stem (default) | directory
```

| Field | Default | Means |
|---|---|---|
| `summary` | `required` | Whether a document of this kind must carry a summary. Optional also exempts it from the tooltip length warning — it is scaffolding, not tooltip text |
| `data` | `[mechanics]` | Which frontmatter blocks documents of this kind may carry. `[]` for none. A key that is neither a toolset field nor a declared block is an error rather than a field silently ignored |
| `discovery` | `link` | How a reader is expected to *find* it. Only `link` kinds are warned about when nothing links to them: an `include` document is book structure, and a `lookup` document is found in an index — which is exactly why a bestiary creature was exempt before this was declarable |
| `audience` | none | An audience tag carried by the whole body. A target that drops that tag does not render the document **at all**, rather than rendering it empty: a heading with nothing under it tells a reader there was something here to miss |
| `refs` | none | Dotted paths inside this kind's blocks that hold document ids. `*` walks every entry of a list or map. Each id must resolve, the same way a `[[link]]` must |
| `id_from` | `stem` | Which part of the path the id must equal. `directory` is for a corpus that files one document per directory — an adventure whose overview is always `adventure.md`, beside its scenes and its maps. Either way the id is derivable from where the document sits, so a file cannot be renamed without its links noticing |

The toolset owns `id`, `title`, `kind`, `summary`, `tags` and
`based_on`. Everything else in frontmatter has to be a declared block.

The default is three kinds: `rule` (link), `section` (include, summary
optional) and `creature` (lookup).

### `audiences`

```yaml
audiences: [book-only, gm-only]
```

Declaring a tag is what makes `{% tag %}…{% endtag %}` mean anything.
The default is `[book-only]`.

Blocks must be closed, must not nest inside themselves, and must not
overlap one another — `{% a %}{% b %}{% enda %}{% endb %}` leaves each
tag individually balanced while making both spans meaningless, so it is
an error too.

**A `{% directive %}` the corpus does not understand is a build error.**
Before, an undeclared tag passed through into the output as literal
text, which is the worse failure: content the tag was meant to hide gets
published, and the only evidence is a stray marker mid-paragraph.

### Links follow the audience, not the author

Everything derived from a document's links is derived **per target**,
from the links still standing once that target's audience policy has
been applied. A link written inside a span this target drops is not a
link this reader has:

- **"See also" in the book shape** lists only what this target renders.
- **`related` in the snippets shape** likewise, so a withheld id is not
  in the file at all.
- **A link pointing at a document the target does not render** — because
  it was filtered out by `select`, or its kind's audience is dropped —
  becomes the words the author wrote and nothing else: no anchor, no
  `data-rule-id`. A dead anchor is a defect, and the id in the page
  source is a trace of something the reader was not meant to be told
  about.

That last case also produces a warning from `check_target_links`, since
a cross-reference in player-facing prose to a referee-only document is
an authoring decision to revisit rather than something to paper over.

`doc.links_out` remains the whole-corpus set and is what the linter's
orphan check reads — "is this document referenced anywhere by anyone" is
a different question from "what can this reader see", and only the
second one is per target.

### `roots`

```yaml
roots: [rulebook]
```

Where a book starts, and what reachability is measured from. Several are
allowed. `roots: []` means this corpus has no book, and the reachability
checks are then **skipped** rather than reported as a missing root —
those are different situations and only the second is worth saying
anything about. The default is `[rulebook]`.

### `lint`

```yaml
lint:
  unincluded: off
  orphans: off
```

Switches off an optional check: `unexplained`, `unincluded`,
`duplicate-includes`, `orphans`, `summary-length`, `mechanics-naming`.
All are on by default.

`check_hardcoded_numbers` is not in that list and cannot be switched
off. A corpus that could turn it off would be a corpus where the prose
and the data are allowed to disagree, which is the one thing this format
exists to prevent. It applies to **every** declared block, so a
difficulty sitting in an `encounter` block drifts from the prose beside
it exactly as readily as a die size in a rule.

### `references`

```yaml
references:
  - path: ../../rules-ico/build
    href: "../rules-ico/build/book.html#rule-{id}"
    name: rules-ico          # optional; defaults to the directory's name
```

See [References into another corpus](#references-into-another-corpus).

### `targets`

A target is a document filter, an audience policy and an output shape.

```yaml
targets:
  gm-module:
    shape: book
    root: adventure-ambush-at-the-ford
    audiences: { default: keep }
    output: build/gm-module.html
  player-handout:
    shape: book
    root: adventure-ambush-at-the-ford
    select: { kind: [section, scene, handout] }
    audiences: { default: drop }
    css: "body { font: 11pt/1.4 Georgia, serif; }"
  engine-data:
    shape: data
    blocks: [mechanics, encounter]
```

| Field | Applies to | Means |
|---|---|---|
| `shape` | all | `book`, `snippets` or `data`. Not extensible from a profile: a new shape is Python, and is a change to the interface |
| `audiences` | all | `{ default: keep\|drop }`, plus per-tag overrides |
| `select` | all | `{ kind: [...] }` and `{ tags: [...] }`. Kind and tag are toolset vocabulary; a folder name is not |
| `output` | all | Where `build.py` writes it, relative to the corpus. A driver passing its own path does not need it |
| `root` | `book` | The document the book starts at. Falls back to the first of `roots` |
| `css` | `book` | Replaces the built-in stylesheet. This is what makes a printable booklet a parameter rather than a fourth shape |
| `blocks` | `data` | Which data blocks to emit. Default `[mechanics]` |

**`default` is required** on anything carrying prose. Not "unlisted tags
are kept" and not "unlisted tags are dropped": each target picks its own
safe direction, so an audience tag added a year from now gets the
conservative answer rather than a surprise. Losing content from a book
is the failure that matters there, so books keep; leaking a design note
into a tooltip or a secret into a handout is the failure that matters
there, so snippets and handouts drop.

The `data` shape needs no `default` and keeps by default. It carries no
prose, so no tag can leak through it; what an audience still reaches
there is a **kind's** default audience, and dropping those would quietly
leave every GM-only NPC out of the file the engine loads. A consumer
that genuinely wants a player-facing data file says
`audiences: { default: drop }` and means it.

The default is three targets — `book`, `snippets` and `mechanics` —
writing the three files a ruleset has always written.

---

## Data blocks

A document carries a map of named blocks. A ruleset document has exactly
one, called `mechanics`, which is why the name used to be invisible.

The first segment of an interpolation path names the block, so nothing
about the syntax changes:

```
{{ mechanics.base_move_tiles }}          this document's `mechanics`
{{ encounter.difficulty }}               this document's `encounter`
{{ goblin:mechanics.typical_number }}    another document's
{% table encounter.checks columns=skill,difficulty %}
```

Lists are addressed **by an entry's own `id`**, and by position if it
has none:

```yaml
encounter:
  checks:
    - id: spot-the-ford
      difficulty: 14
```

```
{{ encounter.checks.spot-the-ford.difficulty }}    prefer this
{{ encounter.checks.0.difficulty }}                works, but
```

Prefer the id form when writing prose: inserting a check at the top of
the list must not silently repoint every number in the paragraph below
it. The positional form exists because it costs nothing and a list of
plain values has no other handle.

`doc.mechanics` is still there in the API, meaning `doc.data["mechanics"]`
— for a ruleset that is still the whole answer.

---

## Inheritance: `based_on`

```yaml
id: npc-grask
based_on: goblin
mechanics:
  stamina: 8
  disciplines: { martial: 1 }
```

Scalars replace wholesale. Nested maps merge key by key. Lists replace
wholesale — a list is a statement about a whole set, and merging would
make it impossible to take anything away, which is most of what a
variant is for. Blocks merge by name, so a parent's `mechanics` merges
into the child's `mechanics` and nothing else.

**It resolves before anything reads the data** — before lint, before
interpolation — and that ordering is the point: a document whose prose
restates a value it *inherited* is exactly the drift this format exists
to catch, and it is invisible to a check that only sees the keys the
document declared for itself.

A `based_on` naming a document that does not exist is an error, and so
is a cycle. It resolves across a reference, so an NPC can be based on a
creature in a ruleset's bestiary.

---

## References into another corpus

```yaml
references:
  - path: ../../rules-ico/build
    href: "../rules-ico/build/book.html#rule-{id}"
```

The toolset reads that directory's `snippets.json` and `mechanics.json`
and adds their documents to **the same flat id namespace** as the local
ones. Only build outputs are read, never that corpus's sources: what a
consumer may depend on is what the producing project publishes, and
reading its `rules/*.md` would be depending on how it is written rather
than on what it ships.

Because the namespace is shared, nothing needs new syntax:

```markdown
See [[skill-list]] for how Spot resolves, and note that a band is
{{ goblin:mechanics.typical_number }} of them.
```

- **A collision is an error.** An id that exists both here and in a
  referenced corpus fails the build, naming both. That is the toolset's
  existing rule — one flat namespace, a duplicate is an error — extended
  across the seam, and it means adding a document to the ruleset whose
  id an adventure already uses fails loudly rather than quietly changing
  what a link means. You cannot deliberately shadow a referenced
  document, which is the right thing to be unable to do.
- **An external document is never rendered here.** It can be linked to,
  read from and inherited from; it does not appear in this corpus's book,
  snippets or data.
- **A link out gets the declared `href`**, with `{id}` substituted, and
  `class="external-ref"`. With no `href` it renders as a span carrying
  `data-rule-id`, so a client can still resolve it — a dead anchor into
  a book that does not contain the document would be worse.
- **An unresolvable reference is an error**, never a silent blank, the
  same as any broken `[[link]]`.
- **A missing or unbuilt reference directory** is its own error, naming
  the build command that fixes it.

### The version travels into the output

```json
"_references": [
  { "name": "rules-ico", "version": "1.0.4", "source": "../../rules-ico/build" }
]
```

in `snippets.json` and in the `data` shape, under the existing
convention that a top-level key beginning with `_` is metadata about the
build rather than a document; and as a visible line in the book shape's
subtitle, because a printed module should say which rules it holds
without going near a repository.

A referenced corpus carrying no version is a **warning** and records
`null` — an unversioned dependency is one nothing built here can record
having been built against. A corpus that declares no references emits no
`_references` at all, which is part of what keeps existing outputs
byte-identical.

---

## The output shapes

Three, and they are the interface between this toolset and everything
downstream. `SHARING.md` covers who may change them.

- **`book`** — one HTML document, in include order, with a contents list
  built from the same order so the two cannot disagree.
- **`snippets`** — a flat map of document id to short form. A document
  gains `based_on` and `external` keys only when it has them, so a
  ruleset's `snippets.json` keeps exactly the shape it always had.
  `related` holds the links this target renders, not every link in the
  document.
- **`data`** — the declared blocks, no prose, no HTML.

The `data` shape has one wrinkle worth knowing. With **one** declared
block it writes that block's contents straight in, which is what
`mechanics.json` has always looked like and what every existing reader
expects. With **several** it writes them under their names and adds
`_blocks` saying so, so a consumer can tell the two apart without being
told:

```json
{ "_generated": "...", "_blocks": ["mechanics", "setup"],
  "rules": { "goblin-captain": { "mechanics": { "threat": 4 } } } }
```

---

## The API

`rules-toolset/rulesc/` is a package, and `tools/build.py` is a command
line over it. A second compiler imports the package.

From a project holding this repository as a submodule at `rpg-master/`,
that is one line of path setup and then an ordinary import:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "rpg-master" / "rules-toolset"))

from rulesc import Profile, compile_corpus, build_target, lint
```

There is no way around the path line without an install step, and this
project deliberately has nothing to install. What the package buys is
that the line is written once and imports a stated API, rather than
putting `tools/` on the path and pulling `build`, `lint` and
`test_rules` into the caller's namespace.

### Compiling and building

```python
profile = Profile.load(corpus_dir)          # corpus.yaml, or the default
profile = Profile.from_mapping({...})       # or build one in the driver
profile = profile.with_roots("adventure-ambush-at-the-ford")

corpus = compile_corpus(scenes_dir, npcs_dir, shared_dir,
                        profile=profile,
                        base_dir=corpus_dir,   # what `references` are relative to
                        version="0.3.0")       # stamped into every output

warnings, errors = lint.run_all(corpus.docs, profile)
if corpus.errors or errors:
    ...                                     # write nothing

build_target(corpus, "gm-module", out_path)
build_target(corpus, "engine-data", out_path)
```

`Corpus` carries `docs`, `compiled`, `errors`, `warnings`, `profile`,
`references` and `version`, plus `local()` — this corpus's own
documents, in load order, excluding anything reached by reference.

`build_target` returns `(bytes, order)` for the book shape and a count
for the others. Its `out_path` defaults to the target's declared
`output` resolved against `base_dir`; a driver building one adventure at
a time passes the path instead. Where an output goes is the driver's
business — templating a path would be this toolset holding an opinion
about how a consumer lays out its build directory.

Its `root` argument overrides where a book starts, and is ignored by the
other shapes rather than refused, so a driver can loop over every target
of a corpus without knowing which of them is a book.

`compile_docs(*dirs, root_id=...)` keeps its old signature and its
`(docs, compiled, errors)` return.

### Rendering one document

`compiled[id]["marked"]` is the document resolved — interpolated,
tabulated, linked — with its audience markers still in place. Applying a
policy is a target's job, because with more than two targets there is no
single pair of forms worth precomputing:

```python
text_for(corpus, doc_id, target)      # audiences applied, includes intact
snippet_html(corpus, doc_id)          # audiences applied, includes removed, rendered
related_for(corpus, doc_id, target)   # (internal, external) ids this target shows
rendered_ids(corpus, target)          # every id this target puts before a reader
check_target_links(corpus)            # warnings: a visible link the target cannot follow
```

### Finding a corpus

`build.py` and `test_rules.py` take a name or `--path`. A name is looked
up in the installed ruleset directory, then the working one, then
anything on **`$RULESET_PATH`** (`os.pathsep`-separated) — which can add
a location but never shadow one, so a project that builds the same
corpus every day need not spell out where it is every day.

---

## The worked example

`rules/demo-supplement/` is a corpus that is not a ruleset and not a
game: four kinds of its own, two audience tags, four targets over three
shapes, a second data block called `setup`, a kind that takes its id
from its directory, `based_on` between two documents, `refs` on a
frontmatter field, and a reference into `demo`'s build outputs.

```bash
python3 tools/build.py demo              # the supplement reads demo's build
python3 tools/build.py demo-supplement
python3 tools/test_rules.py demo-supplement
```

Compare `build/book.html` with `build/handout.html`: the same corpus and
the same shape, differing only in who is reading.

Building it warns that `demo` carries no version. That is the check
working rather than a defect — `demo` is deliberately unversioned, and
an unversioned dependency is one nothing built on it can record having
been built against.
