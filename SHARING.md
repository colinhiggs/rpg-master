# Sharing rpg-master

Who may change what in this repository, and how a project built on top
of it extends the toolset without breaking anybody else's build.

This repository holds two things that other projects depend on: the
game engine, and `rules-toolset/`, the generic compiler that turns any
ruleset's `rules/` and `book/` into `book.html`, `snippets.json` and
`mechanics.json`. It is developed here, and it is also cloned by the
projects built on it — the adventures project first, others later.

Those projects are not read-only consumers. An adventure is a document
with frontmatter, prose, interpolation and audience-dependent sections,
which is what this toolset already compiles; the sensible thing is to
extend it rather than to write a second one that drifts. So the toolset
has to be writeable from outside.

That is deliberate, and it is the reason this document exists. What
makes a shared compiler safe to share is not that people are careful
with it: it is that it holds no opinions about any one game, and that
its output shape stays put.

Its companion is `SHARING.md` in the Ico rules repository, which says
the same kind of thing about a ruleset. `WORKING.md`, beside this file,
is the other half of the pair: this document says who may write to
what, and that one says how and from where — which working copy to
open, which session to do it in, and the steps for the jobs that come
up often.

## The write surface

| Area | Who writes it | Why |
|---|---|---|
| `rules-toolset/rulesc/`, `rules-toolset/tools/` | anyone | The shared area, open by design — but see the rule below. `rulesc/` is the compiler and the API a second compiler imports; `tools/` is the command lines over it. |
| `rules/demo/` | anyone extending the toolset | The demo ruleset is the toolset's own test fixture, and a new feature is demonstrated there. |
| `rules/demo-supplement/` | anyone extending the toolset | The second fixture: a corpus that is *not* a ruleset. Same reason, different shape. |
| `rules/<other>/` | nobody | Another repository's content. See "Installed rulesets" below. |
| `server.py`, `data.py`, `public/` | the engine | A consumer changing the engine should say what it needed and why. |
| `rpg-assets/` | the engine | Placeholder art, replaced wholesale rather than edited. |

## The rule that keeps the toolset shareable

**Nothing in `rules-toolset/` may know about any particular game.**

It does not know that Ico exists, it does not know what a domain or a
stance is, and it must not learn. The moment it does, every other
ruleset is compiling through code written for someone else's game, and
the next change to that game is a change to everybody's compiler.

In practice, an addition qualifies when all four of these hold:

1. **It is expressed in the toolset's own vocabulary** — documents,
   frontmatter, mechanics, interpolation, includes, directives, build
   targets. Not spells, scenes or hit points.
2. **Any ruleset could use it.** A new document `kind`, directive or
   frontmatter key is offered to all of them, not switched on for one.
3. **It is demonstrated in a demo corpus.** `rules/demo/` is the
   ruleset-shaped fixture and `rules/demo-supplement/` the one that is
   not a ruleset; between them they prove a feature is expressible
   without the game that motivated it, and they are where the next
   person reads how it works. A test passing is not a demonstration —
   somebody has to be able to read it.
4. **It is covered by `tools/test_rules.py`**, and the suite passes
   against every corpus:

```bash
python3 tools/build.py demo && python3 tools/test_rules.py
python3 tools/build.py demo-supplement && python3 tools/test_rules.py demo-supplement
python3 tools/test_rules.py ico
```

Both tools take `--path` for a ruleset the name lookup cannot reach —
see below.

Prefer additions that are inert until used. A new directive that no
existing document contains, or a new optional frontmatter key, changes
no existing output and cannot break a consumer that has not asked for
it. A change to how an existing directive behaves can, and needs
saying out loud before it is made.

## The output shape is the interface

Three files are the contract between this toolset and everything
downstream — the game server, the in-game help, the balance simulator,
the adventures:

- `snippets.json` — a flat map of document id to object.
- `mechanics.json` — `_generated`, then `_version`, then `rules`.
- `book.html` — for people, not for parsing.

Which of them a corpus writes, and under what names, is now declared in
its `corpus.yaml` rather than fixed here; but there are still exactly
three *shapes*, and a fourth is Python rather than a declaration. See
`rules-toolset/CORPUS.md`.

In all of them, **a top-level key beginning with `_` is metadata about
the build, not a document**. That convention is what allows a stamp to
be added to a flat map without wrapping it in an envelope and changing
the shape every existing reader already handles. Use it for anything
else that has to travel alongside the data — `_references` (which corpora
this one was built against) and `_blocks` (the data shape's block names,
present only when there is more than one) were both added that way, and
neither appears in an output that does not need it.

Changing these shapes breaks every consumer simultaneously, and unlike
a ruleset change there is no version number that warns them. It is the
one change that has to be agreed before it is written rather than
reviewed after.

## Installed rulesets

A ruleset is a plug-in: to be played it is dropped into `rules/<name>/`
here, and the build looks a name up in `rules/` first and in the outer
working directory `../rules/` second, so **the installed copy wins**.

Two things follow, and both have bitten somebody:

- **Never edit an installed ruleset in place.** It is a copy of another
  repository. The edit is invisible to that repository, will be
  overwritten by the next install, and in the meantime shadows the real
  source so that changes made properly appear to do nothing.
- **Never commit one here.** Only the demo corpora belong to this
  repository. Committing an installed ruleset puts a second copy of
  another project's history in this one, and the two copies diverge
  immediately.

`rules/demo/` and `rules/demo-supplement/` are the exceptions on
purpose: neither is a game, both are the toolset's worked examples and
test fixtures. A third fixture needs the same justification — that it
demonstrates something about the toolset which the existing two cannot.

## Building a ruleset that lives outside this repository

The two search directories are relative to the toolset, so a project
that holds this repository and a ruleset as sibling clones finds
neither. Both tools take `--path` for exactly that case:

```bash
cd rpg-master/rules-toolset
python3 tools/build.py --path ../../rules-ico
python3 tools/test_rules.py --path ../../rules-ico
```

The ruleset name is then the directory's, so both report `rules-ico`
rather than `ico`. Only the label differs.

Both tools resolve a corpus by importing one lookup from `rulesc/`
rather than each repeating it, so they cannot disagree about where a
corpus lives — which is the shape any further work here should take.

For a layout you build every day, `$RULESET_PATH` holds extra
directories to search (`os.pathsep`-separated). It is appended to the
two built-in places rather than inserted before them, so it can add a
location but never shadow one, and `--path` remains the floor under
it.

## What is not versioned here

This repository has no `VERSION` file and no tags, and its one consumer
records nothing at all about which revision of it built anything.

That used to be justified by the pin — a submodule pin is a commit hash,
and a hash is honest. The adventures project dropped its pin in
September 2026, and the better argument turned out to be underneath it
all along. **This is a tool dependency.** Nothing in a consumer's
content depends on which revision compiled it, and a mismatch — a corpus
using a directive this revision does not have, an output shape that
moved — fails loudly at build time rather than producing quietly wrong
output. A data dependency needs a version because you cannot see the
difference from the outside. A tool dependency announces it.

What that rests on is the output shape holding, which is the section
above, and on a consumer being able to rebuild from source whenever it
likes. If either stops being true — the shape moves, or the toolset
gains a consumer shipping compiled output it cannot reproduce — it
should adopt the convention the Ico rules use: `VERSION`, an annotated
tag, and tiers defined by what the consumer has to *do*. Until then,
silence is honest and a version number would be theatre.

## Extensions that were wanted, and landed

All four are built. They are named here because the reasoning still
applies to the next extension: two projects should not quietly invent
two different answers to one question.

- **Document kinds were a closed list** in the toolset's own source. A
  corpus now declares its kinds, and the old tuple is the declaration a
  corpus gets when it says nothing.
- **Audience stripping generalised.** `{% book-only %}` was one tag
  against two implied targets. A corpus now declares its tags and each
  target says what it does with each of them; `book-only` against a book
  and a snippet file is that mechanism with one thing declared.
- **Frontmatter and markdown parsing is shared.** The compiler is a
  package, `rules-toolset/rulesc/`, and `tools/` is command lines over
  it. A second compiler imports it rather than reimplementing it.
- **Ruleset lookup takes `$RULESET_PATH`**, appended to the two-place
  search, so a project that builds the same corpus every day need not
  spell out where it is every day.

`rules-toolset/CORPUS.md` is the reference for all of it, and the API a
second compiler calls.

## Extensions wanted next

- **A fourth output shape**, if one is ever genuinely needed. Three
  cover a book, a keyed map and a data file, and the four targets the
  adventures project needs turned out to be those three parameterised.
  A fourth is a change to the interface and is agreed before it is
  written.
- **A resolved-Markdown output**, so a consumer can run the compiled
  text through a real typesetter rather than through `book.html`.
- **Version the toolset**, if it ever gains a consumer that cannot pin
  it. See below.

## Working in a consumer's clone

A consuming project keeps its own clone of this repository — the
adventures project has one at `ico-adventures/rpg-master`, gitignored
there, imported for `rulesc`. Until September 2026 that clone was a git
submodule, and what changed is worth stating rather than leaving as a
gap.

**Know which repository you are in.** A commit made inside that clone is
a commit to *this* repository, on a branch of this repository's remote.
It does not appear in the outer project's history — and now that the
gitlink is gone, the outer project does not record it in any form.
Nothing over there will tell you the clone has moved, or is dirty, or
is on somebody's half-finished branch.

**Two rules are retired.** "Never commit on a detached HEAD" existed
because `git submodule update` left the checkout detached; that command
is not run any more and a plain clone is on a branch. "Push before the
pin" existed because a gitlink could name a commit the remote did not
have; there is no gitlink. Both are named here rather than deleted, so
that a reader who remembers them knows they went with the submodules
and does not wonder whether the omission is an oversight.

Branch from an up-to-date `main`, and from a consumer project's clone
name the branch for that project — `adv/toolset-gm-only` rather than
`gm-only` — so that two projects pushing to this one remote can always
tell whose branch is whose.
