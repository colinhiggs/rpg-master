# Sharing rpg-master

Who may change what in this repository, and how a project built on top
of it extends the toolset without breaking anybody else's build.

This repository holds two things that other projects depend on: the
game engine, and `rules-toolset/`, the generic compiler that turns any
ruleset's `rules/` and `book/` into `book.html`, `snippets.json` and
`mechanics.json`. It is developed here, and it is also checked out as a
git submodule by the projects built on it — the adventures project
first, others later.

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
| `rules-toolset/tools/` | anyone | The shared area, open by design — but see the rule below. |
| `rules/demo/` | anyone extending the toolset | The demo ruleset is the toolset's own test fixture, and a new feature is demonstrated there. |
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
3. **It is demonstrated in `rules/demo/`.** The demo ruleset is what
   proves the feature is expressible without the game that motivated
   it, and it is where the next person reads how the feature works.
4. **It is covered by `tools/test_rules.py`**, and the suite passes
   against both rulesets:

```bash
python3 tools/build.py demo && python3 tools/test_rules.py
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

In all of them, **a top-level key beginning with `_` is metadata about
the build, not a document**. That convention is what allows a stamp to
be added to a flat map without wrapping it in an envelope and changing
the shape every existing reader already handles. Use it for anything
else that has to travel alongside the data.

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
- **Never commit one here.** Only `rules/demo/` belongs to this
  repository. Committing an installed ruleset puts a second copy of
  another project's history in this one, and the two copies diverge
  immediately.

`rules/demo/` is the exception on purpose: it is not a game, it is the
toolset's worked example and test fixture.

## Building a ruleset that lives outside this repository

The two search directories are relative to the toolset, so a project
that holds this repository and a ruleset as sibling submodules finds
neither. Both tools take `--path` for exactly that case:

```bash
cd rpg-master/rules-toolset
python3 tools/build.py --path ../../rules-ico
python3 tools/test_rules.py --path ../../rules-ico
```

The ruleset name is then the directory's, so both report `rules-ico`
rather than `ico`. Only the label differs.

`test_rules.py` resolves a ruleset by importing `build.py`'s own
lookup rather than repeating it, so the two can never disagree about
where a ruleset lives — which is the shape any further work here should
take. Teaching the toolset to find rulesets in a layout like that
without being told each time — an environment variable, or a small
config file saying where to look — is the next step, and `--path` is
the floor under it.

## What is not versioned here

This repository has no `VERSION` file and no tags. A consumer's
submodule pin — a commit hash — is its version, and that is adequate
while the output shape holds, because the shape is the only thing a
consumer can depend on that it cannot see for itself.

If the toolset ever gains consumers that cannot pin it, it should adopt
the same convention the Ico rules use (`VERSION`, an annotated tag, and
tiers defined by what the consumer has to *do*). Until then, a hash is
honest and a version number would be theatre.

## Extensions already wanted

Named here so that two projects do not quietly invent two different
answers to the same question. None of these are built.

- **Document kinds are a closed list.** `KINDS` in `tools/rulesc.py` is
  `("rule", "section", "creature")` and anything else is a fatal error.
  The adventures project needs `npc`, `scene` and `adventure`.
- **Audience stripping generalises.** `{% book-only %}` is one tag
  against two targets. Adventures need `{% gm-only %}` against four
  (gm-module, player-handout, player-booklet, engine-data). This is the
  same mechanism twice and wants to be one mechanism parameterised by
  target, not two implementations.
- **Frontmatter and markdown parsing wants sharing.** `rulesc.py`
  already does it correctly, including the linter that makes a
  hardcoded number a build error. An adventure compiler should call it,
  not reimplement it.
- **Ruleset lookup without being told each time**, as above. `--path`
  on both tools is done; a project that builds the same ruleset every
  day should not have to spell out where it is every day.

## Working in a submodule checkout

A consuming project holds this repository as a submodule, which makes
three ordinary mistakes easy.

**Know which repository you are in.** A commit made inside the
submodule does not appear in the outer project's history. The outer
project records only which commit this one is pinned to.

**Never commit on a detached HEAD.** `git submodule update` leaves the
checkout detached, and a commit made there belongs to no branch and is
lost by the next update. Check out a branch first:

```bash
git -C rpg-master checkout main && git -C rpg-master pull
```

**Push this repository before pushing the pin.** If the outer project
pushes a pin to a commit that has not been pushed here, every other
checkout breaks: it is told to fetch a commit the remote does not have.
Push here first, or let git do both in the right order with
`git push --recurse-submodules=on-demand`.

Branch from an up-to-date `main`, and from a consumer project's
submodule name the branch for that project — `adv/toolset-gm-only`
rather than `gm-only` — so that two projects pushing to this one remote
can always tell whose branch is whose.
