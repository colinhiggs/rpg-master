# Working across the three projects

`SHARING.md` says **who may write to what**. This says **how, and from
where** — which working copy to open, which session to do it in, and
the steps for the jobs that come up often.

The two are a pair. The boundary `SHARING.md` draws is only worth
drawing if the way we work makes crossing it deliberate rather than
accidental, and most of what follows exists for that reason.

## The map

Four repositories, and — this is the part that catches people — **two
working copies of two of them**.

```
rpg-master-workarea/         REPO: the work area, tracking only the
                             guidance that spans both projects
  rpg-master/                REPO: engine + rules-toolset
    rules/demo/                the toolset's own test fixture
    rules-toolset/tools/       build.py, test_rules.py, rulesc.py
  rules/
    ico/                     REPO: the Ico ruleset

ico-adventures/              REPO: adventures
  adventures/, _shared/
  refs/rules-ico/            VENDORED and committed: snippets.json,
                             mechanics.json, VENDORED.json
  rpg-master/                clone, gitignored
  rules-ico/                 clone, gitignored
```

`rpg-master-workarea/rpg-master` and `ico-adventures/rpg-master` are two
checkouts of one GitHub repository. So are
`rpg-master-workarea/rules/ico` and `ico-adventures/rules-ico`. They can
sit at different commits, and normally do.

### Neither of those clones is recorded any more

They were git submodules until September 2026. They are now plain clones
that `ico-adventures/.gitignore` ignores, and `.gitmodules` is gone.
What that project commits instead is `refs/rules-ico/`: a copy of the
two build outputs an adventure actually reads, with a `VENDORED.json`
beside them naming the version, the commit and the `git describe` of the
clone they came from.

The two dependencies were different in kind and the pin treated them the
same. `rules-ico` is a **data** dependency, version-sensitive, and that
sensitivity is the whole subject of `VERSIONING.md` — worth recording.
`rpg-master` is a **tool** dependency, imported for `rulesc`; nothing in
an adventure's content depends on which revision compiled it, and a
mismatch fails loudly at build time rather than producing quietly wrong
output. So the first is recorded and the second is not.

Vendoring records the version-sensitive one better than the pin did. A
re-vendor's diff shows which mechanic values moved, which is what an
adventure author has to read anyway; a bumped pin was one line of
changed hash that needed a prose commit beside it to say the same thing.
It also drops three standing hazards: the detached HEAD after `git
submodule update`, a pin pushed ahead of the commit it named, and
`modified: rules-ico (new commits)` on every pull.

Two things were given up knowingly. You cannot bisect into the rule
*prose* from an old adventure commit any more — you get the old mechanic
values, which are what govern the content, but not the document they
were written in. And `book.html` is not vendored, so the `href` that
links a compiled module back into the rulebook resolves for a reader who
has the clone or the published book and dangles for one who has neither.

Two consequences worth holding on to:

- The work area is a repository, but only for the few documents that
  belong to neither project — this file's siblings, `README.md`,
  `CLAUDE.md`, `notes.md`. A `git status` there says nothing whatever
  about the state of the rules or the toolset. Always `git -C` a
  specific repository, or `cd` into one.
- The design-side path has `rpg-master` in it twice, once as a
  directory and once as the repository inside it. Paths written for one
  layout are wrong in the other, which has already produced
  documentation that told people to run commands that could not work.

## Default to separate Claude projects

One project for **rules + toolset**, opened at `rpg-master-workarea`.
One for **adventures**, opened at `ico-adventures`. That is the default,
and the reasons compound.

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
the one that actually bites. An agent holding both `rules/ico` and
`ico-adventures/rules-ico` is holding two paths to the same repository
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
   session, edit the toolset in the design-side clone. The adventures
   project's clone is there to *consume* the result.

`SHARING.md` in this repository lists these seam tasks under
"Extensions already wanted", so that two projects do not invent two
answers to the same question.

## Hygiene: which copy is for writing

**The design-side clones are for writing.**
`rpg-master-workarea/rpg-master` and `rpg-master-workarea/rules/ico` are
where the rules and the toolset are developed, branched, released and
tagged.

**Treat the `ico-adventures/` clones as read-mostly.** Pull them, build
with them, test against them, and vendor from them. Commit inside them
only when the change is genuinely adventure-driven and belongs to that
repository — the case `SHARING.md` opens the door for is a new creature,
because writing an adventure creates monsters.

Dropping the submodules strengthens this rather than relaxing it. The
adventures project no longer records what revision its clones are at, so
a shared working copy left on somebody's half-finished branch is now
nobody else's problem — and equally, nothing over there will tell you it
has drifted.

The distinction is not about permission; `SHARING.md` settles that. It
is about not having two branches of the same work in two places. A
creature written in the adventures project's clone and a creature
written in the design-side one are the same file in two checkouts, and
reconciling them is work that did not need doing.

When you do commit in one of those clones:

- **Name the branch for this project** — `adv/bestiary-ogre`, not
  `bestiary-ogre` — so branches from two projects on one remote are
  told apart. Unaffected by any of this, and it stays.
- **Push before you vendor.** The old form was "push the submodule
  before the pin", and a pin pushed ahead of the commit it named broke
  every other checkout outright. Vendoring is gentler, because the
  outputs are copied and so nothing dangles — but a `VENDORED.json`
  naming a commit nobody else can fetch records a provenance that
  cannot be checked. `vendor_rules.py` warns about exactly that.
- **The detached-HEAD rule is retired.** It existed because `git
  submodule update` left the checkout detached. That command is not run
  any more and a plain clone is on a branch. It is written down here as
  retired rather than simply deleted, because a reader who remembers it
  should know it went away with the submodules and not wonder whether
  the omission is an oversight.

## Why the split is cheap now

It used to cost something. The toolset looked a ruleset up by name in
two directories relative to itself, neither of which exists in the
adventures layout, so that project could not build the ruleset it
depends on without copying it somewhere.

Every tool now takes `--path`:

```bash
# from ico-adventures/rpg-master/rules-toolset
python3 tools/build.py      --path ../../rules-ico
python3 tools/test_rules.py --path ../../rules-ico

# from ico-adventures/rules-ico  (the simulator ships inside the ruleset)
python3 sim/balance.py --check
```

So the adventures project can build the ruleset, run all 209 pipeline
tests against it, and measure it, in place. The split costs nothing in
capability, which is what makes it reasonable to insist on.

That build is also the step that feeds the vendor: `vendor_rules.py`
copies `rules-ico/build/`, so a pull that has not been built is a vendor
of the previous version's numbers.

Both tools report the directory's name, so from that layout they say
`rules-ico` rather than `ico`. Only the label differs.

---

# Procedures

## Extending the toolset for an adventure need

The toolset is shared, so the bar is not "does it work" but "does it
still know nothing about any particular game". `SHARING.md` states the
four conditions; this is the order to do them in.

1. **Work in the design-side clone**,
   `rpg-master-workarea/rpg-master`, on a branch. From the adventures
   project this is a combined-session task — see the seam exception
   above.
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
6. Merge to `main` and push. Then pull it in `ico-adventures` — the
   toolset is not vendored, so there is nothing to capture and a plain
   `git -C rpg-master pull --ff-only` is the whole step.

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
2. **Get the clone onto a branch off an up-to-date `main`:**

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

5. **Commit inside the clone, push it, open it for review.** It lands
   on the rules side as a MINOR change: it adds a name and takes
   nothing away.
6. Once merged and released, **rebuild and re-vendor**. This is the step
   that changed. A new creature always needed the ruleset rebuilt before
   an adventure could see it — the reference has always been the build
   outputs and never the sources — but under submodules that rebuild was
   enough, because the build read `rules-ico/build/` in place. It now
   needs a vendor as well. One more step, and a more honest one: the
   creature is not available to a consumer until it has been
   published.

`challenge_level` is an author's estimate. The simulator cannot yet
load a creature and measure it against the archetype panel, so pitch it
against the goblin and expect it to move when the loader lands.

## Re-vendoring the rules into the adventures project

This replaces "bumping a submodule pin", which no longer exists. Still
deliberate, still in a commit of its own, whose message names the
version.

```bash
cd ico-adventures
git -C rules-ico checkout main && git -C rules-ico pull --ff-only

cd rpg-master/rules-toolset
python3 tools/build.py --path ../../rules-ico
cd ../..

python3 tools/vendor_rules.py
python3 tools/build_adventure.py            # must be clean
git add refs/rules-ico
git commit -m "Vendor rules-ico 2.5.0"
```

The rebuild in the middle is the step people skip, and skipping it
vendors the previous version's numbers under the new version's name.

Then check what you actually captured, in `refs/rules-ico/VENDORED.json`.
A `describe` reading `v2.5.0` is a released version. One reading
`v2.5.0-2-g1234abc` is two commits past a release, which is legal — a
commit is a commit, not a version — but means the adventures cannot
quote a version number. If the rules side has merged work without
releasing it, that is the moment to cut the release rather than vendor
past it. `vendor_rules.py --check` is the automated form of the same
question, and it also warns when the commit it is about to record has
not been pushed.

Read `CHANGELOG.md` for the versions you crossed. That is still the most
important line in this procedure. MAJOR is the only tier that obliges
anything, and every MAJOR entry names its renames and removals
old-to-new so that revisiting is a substitution rather than a search.

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

Finally, re-vendor in `ico-adventures`, per the procedure above.

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

`refs/rules-ico/` in the adventures project conflicts the same way, when
two branches vendor different versions, and takes the same answer for
the same reason. Never merge the JSON and never read the conflict.
Decide which version should win, re-vendor from it, and commit that.

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
