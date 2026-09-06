# Working across the three projects

`SHARING.md` says **who may write to what**. This says **how, and from
where** — which working copy to open, which session to do it in, and
the steps for the jobs that come up often.

The two are a pair. The boundary `SHARING.md` draws is only worth
drawing if the way we work makes crossing it deliberate rather than
accidental, and most of what follows exists for that reason.

## The map

Three repositories, and — this is the part that catches people — **two
working copies of two of them**.

```
C:\Users\colin\git\
  rpg-master\                    NOT a repository; just a directory
    rpg-master\                  REPO: engine + rules-toolset
      rules\demo\                 the toolset's own test fixture
      rules-toolset\tools\        build.py, test_rules.py, rulesc.py
    rules\
      ico\                       REPO: the Ico ruleset

  ico-adventures\                REPO: adventures (no remote; local only)
    adventures\, _shared\
    rpg-master\                  SUBMODULE -> the same repo as above
    rules-ico\                   SUBMODULE -> the same repo as rules\ico
```

`rpg-master\rpg-master` and `ico-adventures\rpg-master` are two
checkouts of one GitHub repository. So are `rpg-master\rules\ico` and
`ico-adventures\rules-ico`. They can sit at different commits, and
normally do: a submodule pin lags `main` by design.

Two consequences worth holding on to:

- The outer `git\rpg-master` is not a repository. A `git status` there
  reports on whatever repository it finds by walking up, which is not
  what you meant.
- The design-side path has `rpg-master` in it twice. Paths written for
  one layout are wrong in the other, which has already produced
  documentation that told people to run commands that could not work.

## Default to separate Claude projects

One project for **rules + toolset**, opened at `git\rpg-master`. One
for **adventures**, opened at `git\ico-adventures`. That is the
default, and the reasons compound.

**The ownership boundary is already drawn, and a session that sees
everything can quietly cross it.** `SHARING.md` says a change moving a
mechanic value comes from the rules project, and that the toolset knows
about no particular game. Those are easy rules to follow deliberately
and easy to break in passing — an agent with every file in reach, asked
to make an encounter work, can adjust a weapon's damage in the ruleset
and never register that it has just moved a number measured against the
whole system. A session that cannot see the rules source cannot do that
without an obvious, deliberate step.

**Memory files are per project.** Claude's memory directory is keyed by
the project path, so conventions learned while writing rules stay with
the rules and conventions learned while writing adventures stay with
the adventures. Merge the projects and the memories merge too: prose
conventions for rule documents get applied to scene text, the bestiary
stat block format bleeds into NPC frontmatter, and neither set is quite
right for the other any more.

**Two working copies of one repository is the real hazard.** This is
the one that actually bites. An agent holding both `rules\ico` and
`ico-adventures\rules-ico` is holding two paths to the same repository
at two different commits. It can build one and test the other and
report a contradiction that does not exist; it can fix a file in one
copy that is already fixed in the other; it can commit in one, pull in
the other, and manufacture a conflict out of its own work. Nothing
about that is exotic — it is the ordinary result of two paths that look
like different projects and are not.

One session, one working copy of any given repository. That is the rule
the split enforces.

## The exception: when the task is the seam

Some work is genuinely about the join between the projects, and
splitting it makes it worse. Open one combined session deliberately
when the task is:

- the adventure compiler, which has to reuse `rulesc.py`'s frontmatter
  and markdown parsing rather than reimplement it;
- generalising `{% book-only %}` into the `{% gm-only %}` mechanism the
  adventures need — one mechanism parameterised by target, not two
  implementations of the same idea;
- anything else where the answer has to be designed on both sides at
  once, and a change to the toolset is only correct in the light of
  what the adventure needs from it.

Two things make that safe rather than a licence:

1. **It is a session, not a setting.** Close it when the feature lands.
   The combined view is for the work that needs it, and every later
   session goes back to the default.
2. **Still one working copy per repository.** Even in a combined
   session, edit the toolset in the design-side clone. The submodule
   copy is there to *consume* the result.

`SHARING.md` in this repository lists these seam tasks under
"Extensions already wanted", so that two projects do not invent two
answers to the same question.

## Hygiene: which copy is for writing

**The design-side clones are for writing.** `rpg-master\rpg-master` and
`rpg-master\rules\ico` are where the rules and the toolset are
developed, branched, released and tagged.

**Treat the `ico-adventures\` submodules as read-mostly.** Pull them,
build with them, test against them, and bump their pins. Commit inside
them only when the change is genuinely adventure-driven and belongs to
that repository — the case `SHARING.md` opens the door for is a new
creature, because writing an adventure creates monsters.

The distinction is not about permission; `SHARING.md` settles that. It
is about not having two branches of the same work in two places. A
creature written in the submodule and a creature written in the clone
are the same file in two checkouts, and reconciling them is work that
did not need doing.

When you do commit in a submodule:

- **Never on a detached HEAD.** `git submodule update` leaves the
  checkout detached and a commit made there belongs to no branch.
  `git -C rules-ico checkout main` first.
- **Name the branch for this project** — `adv/bestiary-ogre`, not
  `bestiary-ogre` — so branches from two projects on one remote are
  told apart.
- **Push the submodule before the pin.** A pin pushed ahead of the
  commit it points at breaks every other checkout.

## Why the split is cheap now

It used to cost something. The toolset looked a ruleset up by name in
two directories relative to itself, neither of which exists in the
adventures layout, so that project could not build the ruleset it
depends on without copying it somewhere.

Every tool now takes `--path`:

```bash
# from ico-adventures\rpg-master\rules-toolset
python3 tools/build.py      --path ../../rules-ico
python3 tools/test_rules.py --path ../../rules-ico

# from ico-adventures\rules-ico  (the simulator ships inside the ruleset)
python3 sim/balance.py --check
```

So the adventures project can build the ruleset, run all 114 pipeline
tests against it, and measure it, in place. The split costs nothing in
capability, which is what makes it reasonable to insist on.

Both tools report the directory's name, so from that layout they say
`rules-ico` rather than `ico`. Only the label differs.

---

# Procedures

## Extending the toolset for an adventure need

The toolset is shared, so the bar is not "does it work" but "does it
still know nothing about any particular game". `SHARING.md` states the
four conditions; this is the order to do them in.

1. **Work in the design-side clone**, `rpg-master\rpg-master`, on a
   branch. From the adventures project this is a combined-session task
   — see the seam exception above.
2. **Express it in the toolset's vocabulary.** Documents, frontmatter,
   mechanics, interpolation, includes, directives, build targets. If
   the design mentions scenes or spells, it is in the wrong repository.
3. **Demonstrate it in `rules/demo/`.** This is the step that proves
   the feature survives without the game that motivated it, and it is
   where the next person reads how it works.
4. **Cover it in `tools/test_rules.py`**, and run both rulesets:

   ```bash
   python3 tools/build.py demo && python3 tools/test_rules.py
   python3 tools/test_rules.py ico
   ```

5. **Prefer additions that are inert until used.** A new directive no
   existing document contains, or a new optional frontmatter key,
   cannot break a consumer that has not asked for it. A change to how
   an existing directive behaves can, and gets agreed before it is
   written.
6. Merge to `main` and push. Then bump the pin in `ico-adventures`.

Output shapes are the exception to all of the above: `snippets.json`
being a flat map, `mechanics.json`'s envelope, `_`-prefixed keys being
metadata. Changing one breaks every consumer at once with no version
number to warn them, so it is agreed before it is written rather than
reviewed after.

## Adding a creature from the adventures side

The one job the shared area exists for.

1. **Decide it belongs in the ruleset at all.** Could another
   adventure, written by somebody else, use this creature without
   knowing your plot? Yes → `rules/bestiary/`. Reused across this
   project's adventures but bound to its setting → `_shared/creatures/`
   here. A named villain whose stat block is a plot point → it stays an
   NPC in the adventure that owns it.
2. **Get the submodule onto a branch off an up-to-date `main`:**

   ```bash
   git -C rules-ico checkout main && git -C rules-ico pull --ff-only
   git -C rules-ico checkout -b adv/bestiary-<slug>
   ```

3. **Write `rules/bestiary/<slug>.md`**, `kind: creature`, following
   `goblin.md`. Check the id first: document ids are one flat namespace
   across the whole ruleset, so a creature called `guard` collides with
   a rule document called `guard` and the build fails. The ids in use
   are the keys of `build/snippets.json`.
4. **Rebuild and test**, so `build/` moves with the source in the same
   commit:

   ```bash
   cd rpg-master/rules-toolset
   python3 tools/build.py      --path ../../rules-ico
   python3 tools/test_rules.py --path ../../rules-ico
   ```

5. **Commit inside the submodule, push it, open it for review.** It
   lands on the rules side as a MINOR change: it adds a name and takes
   nothing away.
6. Once merged and released, bump the pin.

`challenge_level` is an author's estimate. The simulator cannot yet
load a creature and measure it against the archetype panel, so pitch it
against the goblin and expect it to move when the loader lands.

## Bumping a submodule pin

Deliberate, in a commit of its own, whose message names the version.

```bash
cd ico-adventures
git -C rules-ico  checkout main && git -C rules-ico  pull --ff-only
git -C rpg-master checkout main && git -C rpg-master pull --ff-only
git add rules-ico rpg-master
git commit -m "Bump rules-ico to 1.0.3"
```

Then check what you have actually pinned:

```bash
git submodule status
```

A line reading `rules-ico (v1.0.3)` is pinned to a released version. A
line reading `(v1.0.3-2-g1234abc)` is pinned two commits past one,
which is legal — a pin is a commit hash, not a version — but means the
adventures cannot quote a version number. If the rules side has merged
work without releasing it, that is the moment to cut the release rather
than pin past it.

Read `CHANGELOG.md` for the versions you crossed. MAJOR is the only
tier that obliges anything, and every MAJOR entry names its renames and
removals old-to-new so that revisiting is a substitution rather than a
search.

## Cutting a release

Rules project only, from the design-side clone. `VERSIONING.md` has the
full convention; this is the sequence.

```bash
cd rules/ico
git checkout main && git pull --ff-only
git checkout -b release/1.0.4

# 1. the number
printf '1.0.4\n' > VERSION

# 2. the changelog entry — name any renames and removals old-to-new

# 3. rebuild, from the toolset directory
python3 tools/build.py ico
python3 tools/test_rules.py ico

# 4. one commit: VERSION, CHANGELOG and the rebuilt build/ together
git add -A && git commit -m "Release 1.0.4"

# 5. merge, then tag on main, never on the branch
git checkout main && git merge release/1.0.4
git tag -a v1.0.4 -m "..."
git push --follow-tags origin main
git branch -d release/1.0.4
```

Committing the bump, the changelog and the rebuilt outputs together is
what keeps the tag and the stamp inseparable: there is no commit at
which the tag says one thing and `mechanics.json` says another.

Two things worth checking before you tag:

- `git diff` on the release commit. For a PATCH the three build outputs
  should show exactly one changed line each, and each one should be the
  version stamp. That makes the claim rather than asserting it.
- Any version number written in prose. A README that dates a statement
  to the version it ships in has to be updated *in* the release commit,
  or it dates itself to the previous one.

Finally, bump the pin in `ico-adventures`.

## Resolving a conflict in `build/`

`build/` is tracked on purpose — the server and the adventures read it
without the repository attached — and being generated and tracked at
once makes it where two branches most often collide.

It is also the easiest conflict there is, because the outputs are
reproducible: the same sources build byte-for-byte identical files from
any checkout. Never merge them by hand and never read the conflict.

```bash
git checkout --ours -- build/      # just to clear the markers
python3 tools/build.py ico         # from the toolset directory
git add build/
```

The rebuild overwrites whatever you took, so which side you take does
not matter. What matters is that the merged **sources** produced the
committed outputs.

The same reasoning is why `build/` is never hand-edited even when the
edit would be trivially correct: the next rebuild silently reverts it,
and until then the committed data disagrees with the rules it claims to
come from.

---

## See also

- `SHARING.md` (this repository) — the toolset's write surface, what an
  addition must satisfy, and why the output shapes are the interface.
- `SHARING.md` (the Ico rules) — that repository's write surface, how
  to add a creature, and what belongs in the bestiary.
- `VERSIONING.md` (the Ico rules) — what the three numbers mean and how
  a release is cut.
- `rules-toolset/README.md` — the document format the whole pipeline is
  built on.
