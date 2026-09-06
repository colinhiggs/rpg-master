# rules-toolset — single-source rules pipeline

This is the **toolset only** — it contains no game content. It compiles
a *ruleset* (a directory with `rules/*.md` and `book/*.md`) into three
consumers, and the same toolset works for every ruleset:

| Output | For |
|---|---|
| `<ruleset>/build/book.html` | The long-form rulebook — assembled by the include tree, readable start to finish |
| `<ruleset>/build/snippets.json` | In-game context help: tooltips, popups, "what does this mean?" panels |
| `<ruleset>/build/mechanics.json` | Pure data, no prose — what the game server actually runs on |

The three are for different readers, and only the book is for a person
reading start to finish. `mechanics:` never appears in it as a table of
raw keys: it exists to feed the server and to let the linter prove the
prose has not drifted from it, and every value it holds is already in
the prose by interpolation. Anyone who wants the data itself wants
`mechanics.json`, which is the readable form of it.

Change a rule file, rebuild, and all three move together. Nothing
downstream is ever hand-edited.

## Where the rulesets live

The toolset ships as part of the game, and a ruleset is a **plug-in**:
a directory with `rules/` and `book/` in it, dropped into the game's
`rules/` folder. Nothing about a ruleset is special-cased here.

```
rpg-master/                    working directory for software AND rulesets
  rpg-master/                  the SOFTWARE (its own git repository)
    server.py, data.py …
    rules-toolset/             ← you are here — generic, no game content
    rules/                     installed rulesets, dropped in to be played
      demo/                    worked example: six rules, three chapters
  rules/                       rulesets being AUTHORED
    ico/                       its own git repository, developed separately
```

A ruleset name is looked up in the installed directory first, then in
the outer authoring directory, so `build.py ico` finds ico whether it is
still being written next door or has been dropped in to play. Installed
wins if a name exists in both, because that is the copy the game would
actually run. `--path` overrides both.

The split is deliberate: `demo` exists to exercise this toolset and
ships with it, while `ico` is a ruleset with its own history that
happens to be built by it. Neither knows about the other.

An installed ruleset is a copy of another repository. Never edit one in
place — the edit is invisible to the repository that owns it, and
because installed wins, it shadows the real source so that changes made
properly appear to do nothing. `../SHARING.md` has the rest of the
rules for working on a toolset that several projects write to.

## Quick start

```bash
python3 tools/build.py demo        # compile the installed demo ruleset
python3 tools/build.py ico         # compile ico, wherever it lives
python3 tools/test_rules.py        # 55 tests, defaults to the demo ruleset
python3 tools/test_rules.py ico    # same tests, against ico instead

python3 -m http.server 8000        # from rpg-master/rpg-master/
# → localhost:8000/rules/demo/build/book.html        the demo rulebook
# → localhost:8000/rules-toolset/snippet-demo.html   in-game help, working
```

## The rule that makes this work

**A value may exist in exactly one place.** Prose never restates a
number that lives in `mechanics:` — it interpolates it:

```markdown
---
id: movement
title: Movement
summary: A move carries you a number of tiles across the grid.
tags: [core, combat]
mechanics:
  base_move_tiles: 4
  difficult_terrain_multiplier: 2
---

A move carries you up to {{ mechanics.base_move_tiles }} tiles.
Difficult ground costs {{ mechanics.difficult_terrain_multiplier }}
tiles per tile entered. See [[turn-order]] for how many moves you get.
```

Write `A move carries you up to 4 tiles` instead and **the build
fails** — see "What the linter catches" below. That check is the whole
architecture; without it this is just three files that happen to agree
today.

### Frontmatter fields

| Field | Required | Purpose |
|---|---|---|
| `id` | yes | Stable identifier; must match the filename stem. Links, includes and snippet keys use it |
| `title` | yes | Heading in the book, title in tooltips |
| `kind` | no | `rule` (default) or `section`. Sections are book scaffolding — chapters, the root — and skip the summary requirement |
| `summary` | rules only | One-or-two sentences. This is the tooltip text — keep it under ~240 chars |
| `mechanics` | no | Machine-readable values. Goes to the server verbatim; no prose here ever |
| `tags` | no | Grouping/filtering; shown in the book, passed through to snippets |

`spine:` no longer exists. Book order comes from the include tree
(below); leaving a stale `spine:` in a file is a hard error rather than
a silently-ignored field.

### Body syntax

| Syntax | Does |
|---|---|
| `{{ mechanics.key }}` | Insert a value from this document's mechanics |
| `{{ other-id:mechanics.key }}` | Insert a value from another document's mechanics |
| `[[other-id]]` | Link, using the target's title as the text |
| `[[other-id\|custom text]]` | Link with custom text |
| `{% include other-id %}` | Splice another document in at this point |
| `{% book-only %}…{% endbook-only %}` | Content for the book only; dropped from the snippet |

### Keeping commentary out of tooltips

A rule document usually wants to say more than a player looking it up
mid-game wants to read — why a value is what it is, what an earlier
draft got wrong, which other rule it is balanced against. Wrapping that
in `{% book-only %}` keeps it in `book.html` and drops it from
`snippets.json`:

```markdown
A move carries you up to {{ mechanics.base_move_tiles }} tiles.

{% book-only %}
## Design note

Diagonals costing the same as orthogonal steps is wrong and deliberate.
{% endbook-only %}
```

The block is removed before the snippet is rendered, so a tooltip shows
the rule and nothing else, while the book reads in full. `mechanics.json`
is unaffected either way — it never contained prose.

The **linter still reads inside the block**, deliberately: a design note
that quotes a mechanic value goes stale exactly like any other prose, so
drift detection applies there too.

Markers must be closed and must not nest; either mistake fails the
build rather than silently swallowing the rest of a document.

## The include tree

The book's structure lives in `book/`, not scattered across rule files.
`book/rulebook.md` is the root; it includes chapters, and chapters
include rules:

```markdown
---
id: ch-combat
title: Fighting
kind: section
summary: Moving, attacking, and taking harm.
---

Combat is deliberately mechanical — grid, tiles, hit points — because
the fiction around it is not.

{% include movement %}

{% include attacks %}

{% include damage-and-healing %}
```

Includes are **positional**: prose before, between and after the
include directives is preserved, so a chapter can introduce a rule,
present it, then link into the next one. Includes **nest to any depth**
— a chapter can include a section which includes a rule — and heading
levels shift automatically so an included document always sits exactly
one level below its parent, with no skipped levels.

Reading order, the table of contents, and heading depth all derive
from this one tree, so they cannot disagree with each other.

### Cycles are a hard error

A loop in the include graph would expand forever, so it stops the build
immediately with the exact chain to break:

```
FATAL: include cycle detected: ch-basics -> rulebook -> ch-basics
  'ch-basics' is already being included further up this chain, so
  expanding it would never terminate.
```

Every document is checked as a possible start point, not just the book
root — a cycle sitting in a subtree that nothing currently includes is
still a bug, and you want it caught before wiring that subtree in.

A **diamond** (two chapters both including the same rule) is *not* a
cycle: it compiles, and warns that the content will appear twice.

Markdown support is deliberately minimal (`##` headings, paragraphs,
`**bold**`, `` `code` ``, `-` lists) because it's rendered by a
~40-line function in `rulesc.py` rather than a dependency. If you want
full Markdown, replace `render_markdown()` with `markdown` or
`mistune` — nothing else in the pipeline touches it.

## What the linter catches

`tools/lint.py`, run automatically by the build:

- **Prose duplicating a mechanic value** → **error, build fails.**
  Writing "4 tiles" where `base_move_tiles: 4` means the next rebalance
  changes one and not the other. Interpolate instead.
- **Prose contradicting a mechanic** → warning. If a rule has numeric
  mechanics and the prose contains some *other* number, you get a
  nudge to check it. This is a weaker signal on purpose — see
  "Honest limits."
- **Documents not included anywhere** → warning. It compiles into
  snippets but will never appear in the book — usually a rule written
  and then never wired into a chapter.
- **Documents included more than once** → warning, with the count.
- **Rules nothing links to** → warning. Harder to find when reading.
- **Over-long summaries** → warning. They'll overflow in-game tooltips.
- **Non-snake_case mechanics keys** → warning. The server reads these
  as identifiers.

Structural problems are hard errors from the compiler itself: missing
frontmatter, missing required field, `id` not matching the filename, a
leftover `spine:`, an unknown `kind:`, a broken `[[link]]`, an
unresolvable `{{ interpolation }}`, and `{% include %}` naming a
document that does not exist. An include **cycle** is fatal and raises
before anything else runs.

## Wiring the game server to it

`tools/rules_runtime.py` is the server-side reader. Copy it next to
`server.py`, and point it at the **installed** ruleset's
`build/mechanics.json` and `build/snippets.json` — i.e.
`rules/<name>/build/*.json` relative to the server, filled by a build
step rather than by hand. Point it at the ruleset the game is actually
running, not at `demo`: `demo` exists to develop and test the toolset
itself.

```python
import rules_runtime as R
R.load_mechanics()          # at startup; raises loudly if not built

R.starting_hp()             # 20 — from damage-and-healing
R.grid_size()               # 14 — from movement
R.dice_notation_pattern()   # the regex, from dice-rolls
R.mech("attacks", "base_defence")   # anything else
```

The point is that `data.py` should stop carrying its own copies. It
currently hardcodes `"hp": 20`, `GRID_SIZE = 14`, and a dice regex —
each of those is a second source of truth that can silently disagree
with the printed rules. Replacing them with `R.starting_hp()`,
`R.grid_size()`, `R.dice_notation_pattern()` closes the loop, and
`mech()` raises on a missing key rather than returning a default, so a
typo fails at startup instead of producing a rules-violating game.

**I have not made that edit to `data.py` in the game project** — it
touches the module you may still be actively changing, and it needs a
decision from you first: whether the server reads `mechanics.json`
directly from the rules repo, or whether a build step copies it in.
Both are fine; they differ in how you deploy.

## Serving snippets to the client

`snippet-demo.html` is a working demonstration — hover for a tooltip,
click for the full rule, with links between rules and out to the book.
Each snippet carries:

```json
{
  "id": "movement",
  "title": "Movement",
  "summary": "plain text, for native tooltips or alt text",
  "summary_html": "same but with <code> rendered, for rich popups",
  "html": "the full rule body, rendered",
  "tags": ["core", "combat", "map"],
  "related": ["turn-order"],
  "book_anchor": "#rule-movement"
}
```

In the actual game client, the natural integration is to serve
`snippets.json` as a static file and attach `data-rule="..."` to any
UI element that corresponds to a rule — the dice roller to
`dice-rolls`, the HP control to `damage-and-healing`, the end-turn
button to `turn-order`.

## Honest limits

- **The linter catches duplication, not contradiction.** It can tell
  that prose saying "4" duplicates `base_move_tiles: 4`. It cannot tell
  that prose saying "6 tiles" *contradicts* it, because nothing in the
  text says which mechanic that 6 was meant to be — a wrong number is
  indistinguishable from a number that was never a mechanic. The
  second-tier warning flags leftover numbers for a human to eyeball,
  and it will produce false positives ("a 1 in 6 chance"). There is no
  way around this short of annotating every number in prose.
- **Mechanics are data, not logic.** `mechanics.json` can say
  `critical_damage_multiplier: 2`; it cannot express "unless the target
  is undead, in which case…". Conditional rules still live in server
  code. When you hit that wall, the options are a small rules DSL
  (large undertaking) or accepting that the *values* are single-source
  while the *logic* isn't — the second is usually right for a long
  time.
- **Nothing verifies the server obeys the rules.** Loading
  `starting_hp` from the same file the book prints guarantees they
  agree on the *number*. It does not guarantee the server actually
  applies it. That needs tests in the game project asserting behaviour
  against `mechanics.json` — worth adding once rules start changing
  regularly.
- **No versioning or changelog.** If you publish rules that players
  reference between sessions, "what changed since last week" becomes a
  real need. Since the source is plain text files, `git log` on
  `rules/` covers this well; a `version:` frontmatter field and a
  generated changelog page would be the next step if you want it in
  the book itself.
- **Markdown support is a subset**, as described above.
- **Rulesets share nothing but the toolset.** Cross-ruleset references
  (`{{ demo:mechanics.x }}` from within `ico`, or an `[[link]]` across
  rulesets) aren't supported — `compile_docs()` only resolves ids within
  the directories it was given. A shared "house rules" layer that one
  ruleset extends would be new work, not something already wired up.
- **A ruleset carries its own `build/` output.** Dropping a ruleset into
  the installed directory does not build it; that is a separate step,
  and a ruleset shipped without its `build/` will not run until someone
  runs `build.py` against it.

## Files

```
rpg-master/rules-toolset/   (generic, no game content — ships with the game)
  tools/
    rulesc.py          parser, includes, cycle detection, interpolation,
                       links, markdown rendering
    lint.py            the drift and structure checks
    build.py           walks the include tree, writes the three outputs;
                       takes a ruleset name/path as its argument
    rules_runtime.py   server-side reader (copy into the game project)
    test_rules.py      55 tests on the pipeline's guarantees; takes an
                       optional ruleset name (defaults to 'demo')
  snippet-demo.html    working in-game context help demo, wired to the
                       demo ruleset specifically (see its own note)
  README.md            this file

../rules/demo/              (installed ruleset — exercises the toolset)
  book/
    rulebook.md        the root: intro prose + {% include %} per chapter
    ch-basics.md       \
    ch-combat.md        |  chapters: intro prose + includes of rules
    ch-running.md      /
  rules/
    dice-rolls.md      \
    turn-order.md       |  six example rules covering what the
    movement.md         |  prototype server already implements
    damage-and-healing.md
    attacks.md          |
    dm-tools.md        /
  build/               generated by `build.py demo` — never edit

../../rules/ico/            (authored separately, its own git repository;
                            see its own README.md)
```
