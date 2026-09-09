# demo-supplement

A corpus that is not a ruleset, and deliberately not a game.

`rules/demo/` is the toolset's worked example of a **ruleset**: three
document kinds, one audience tag, one data block called `mechanics`, one
book root, three outputs. This is the worked example of everything else
a corpus can declare about itself, and of the one thing a ruleset never
does — depend on another corpus.

Between them they are the two fixtures a new feature is demonstrated in.
See [`../../rules-toolset/CORPUS.md`](../../rules-toolset/CORPUS.md) for
the reference, and `corpus.yaml` here for the declaration with its
reasoning inline.

```bash
cd ../../rules-toolset
python3 tools/build.py demo              # first: this corpus reads demo's outputs
python3 tools/build.py demo-supplement
python3 tools/test_rules.py demo-supplement
```

## What each part is demonstrating

| Where | What |
|---|---|
| `corpus.yaml` `kinds` | Four kinds the toolset has never heard of — `section`, `encounter`, `foe`, `note` — with their own summary rules, data blocks and discovery |
| `corpus.yaml` `audiences` | Two tags, `book-only` and `gm-only`, against four targets |
| `corpus.yaml` `targets` | Four outputs over three shapes. `book` and `handout` are the same shape differing only in who is reading |
| `corpus.yaml` `references` | Two, and the two ways a dependency can be held. `demo` is a sibling checkout read in place; `refs/almanac/` is vendored — a committed copy of what that corpus published, with a `VENDORED.json` stamp saying which revision |
| `rules/encounters/the-crossing/encounter.md` | `id_from: directory`; a data block called `setup` rather than `mechanics`; a list addressed by each entry's `id`; a cross-corpus link and interpolation |
| `rules/goblin-captain.md` | `based_on`: a scalar replaced, a scalar inherited, a list replaced wholesale |
| `rules/gm-notes.md` | A kind whose default audience covers the whole document, with no marker in the file |
| `book.html` vs `handout.html`, "See also" | Related links are per target. The captain is linked only from inside a `gm-only` span, so the book lists it and the handout does not — a related-links line built once for every target would hand the handout the title of the document the target exists to withhold |
| `rules/encounters/the-far-bank/encounter.md` | A document with no data block at all, reached because another document's frontmatter declares a `refs` path pointing at it; and a link and interpolation into the vendored corpus, rendering without an `href` because only its data was copied and not its book |
| `refs/almanac/` | What a vendored reference is made of: the two files a reference reads, and the stamp beside them |

## Two things that look wrong and are not

**Building it prints a warning.** `demo` carries no `VERSION`, so
nothing built here can record which version of it this was built
against. That is the check working. `demo` stays unversioned on purpose:
giving it a version would change its three outputs, and those outputs
are the fixed point everything else in this toolset is measured against.

**`gm-notes` is missing from the handout entirely**, rather than present
and empty. A target that drops a document's whole audience does not
render it at all — a heading with nothing under it would tell a reader
there was something here to miss, which is the opposite of what an
audience is for.
