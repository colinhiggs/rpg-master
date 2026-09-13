# test_rules.py — tests for the guarantees the format is supposed to give.
#
# Run: python3 tools/test_rules.py
#
# These test the PIPELINE, not the game balance. The thing worth
# protecting is the invariant "a value exists in exactly one place";
# each test below is a way that invariant could quietly break.

import argparse
import dataclasses
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import rulesc
from rulesc import (
    IncludeCycleError, RuleError, lint,
    compile_docs, detect_cycles, include_order, render_markdown,
)
from rulesc.compile import collapses

TOOLSET_ROOT = Path(__file__).parent.parent       # .../rpg-master/rules-toolset

# Which ruleset the "real rules" section below exercises against. The
# pipeline tests themselves (interpolation, links, includes, cycles,
# drift detection) build throwaway rulesets with with_temp_rules() and
# don't depend on this — this only picks which real content acts as an
# integration smoke test.
#
# The lookup is the rulesc package's, imported rather than repeated, so
# no two tools can disagree about where a ruleset lives. A name is found
# in the installed directory and then in the outer authoring one;
# --path reaches a ruleset that is in neither, which is the case for a
# project holding the toolset and a ruleset as sibling submodules.
_parser = argparse.ArgumentParser(
    description="Run the pipeline tests. Most build their own throwaway rulesets; "
                "the 'real rules' and 'build outputs' sections run against one real one.",
)
_parser.add_argument(
    "ruleset", nargs="?", default="demo",
    help="Ruleset name, looked up in %s then %s (e.g. 'demo', 'ico'). "
         "Default: demo." % rulesc.RULESET_SEARCH_PATH,
)
_parser.add_argument(
    "--path", default=None,
    help="Explicit path to a ruleset directory (containing rules/ and book/), overrides the name.",
)
_args = _parser.parse_args()

RULESET_DIR, RULESET_WHERE = rulesc.resolve_ruleset_dir(_args)
if RULESET_DIR is None:
    sys.exit("no ruleset '%s' in %s\nUse --path to test a ruleset somewhere else entirely."
             % (_args.ruleset, rulesc.RULESET_SEARCH_PATH))
if not RULESET_DIR.exists():
    sys.exit("no ruleset directory at %s" % RULESET_DIR)
# From --path the name is the directory's, the same way build.py reports
# it, so a ruleset checked out under another name says so in the output.
RULESET_NAME = RULESET_DIR.name
RULES_DIR = RULESET_DIR / "rules"
BOOK_DIR = RULESET_DIR / "book"

passed, failed = 0, 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


def with_temp_rules(files: dict):
    """Build a throwaway docs dir from {filename: content}."""
    tmp = Path(tempfile.mkdtemp())
    for fname, content in files.items():
        path = tmp / fname
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return tmp


def corpus_of(*dirs, profile=None, base_dir=None):
    """Compile a throwaway corpus, and attach the two forms most of the
    tests below want to talk about: `html` is the snippet form (every
    audience block dropped, includes removed, rendered) and `linked` is
    the book form (every audience block kept, includes intact). The
    compiler itself keeps one marked-up form and lets each target apply
    its own policy, which is the only thing that works once there are
    more than two targets; these two are the default profile's."""
    corpus = rulesc.compile_corpus(*dirs, profile=profile, base_dir=base_dir)
    book = corpus.profile.targets.get("book")
    snippets = corpus.profile.targets.get("snippets")
    for doc_id in corpus.compiled:
        if snippets is not None:
            corpus.compiled[doc_id]["html"] = rulesc.snippet_html(corpus, doc_id, snippets)
        if book is not None:
            corpus.compiled[doc_id]["linked"] = rulesc.text_for(corpus, doc_id, book)
    return corpus


def compile_rules(d, root_id="rulebook", profile=None):
    corpus = corpus_of(d, profile=profile)
    return corpus.docs, corpus.compiled, corpus.errors


# ---------------------------------------------------------------------
print(f"\nReal rule set ('{RULESET_NAME}', {RULESET_WHERE}):")

if not RULES_DIR.exists() and not BOOK_DIR.exists():
    print(f"  SKIPPED — {RULESET_DIR} has no rules/ or book/ yet "
          "(expected for an empty ruleset like a freshly-created 'ico').")
    rules = {}
else:
    # Whatever the named corpus declares about itself, rather than what
    # a ruleset happens to declare -- so this section is an integration
    # test for any corpus, not only for one shaped like demo.
    REAL_PROFILE = rulesc.Profile.load(RULESET_DIR)
    real = corpus_of(RULES_DIR, BOOK_DIR, profile=REAL_PROFILE, base_dir=RULESET_DIR)
    rules, compiled, errors = real.docs, real.compiled, real.errors
    check("real rules compile with no errors", not errors, str(errors))

    warnings, lint_errors = lint.run_all(rules, REAL_PROFILE)
    check("real rules pass lint", not lint_errors, str(lint_errors))

    check("every document whose kind requires a summary has one",
          all(r.summary.strip() for r in real.local()
              if REAL_PROFILE.kinds[r.kind].summary == "required"))

    if REAL_PROFILE.roots:
        root = REAL_PROFILE.roots[0]
        check("book root exists", root in rules)

        order = include_order(rules, root)
        check("include order covers every document", len(order) == len(real.local()),
              f"{len(order)} in order vs {len(real.local())} docs")
        check("root is first in include order", order[0] == (root, 0), str(order[:1]))
        check("documents nest two deep (root > chapter > document)",
              any(d == 2 for _, d in order), str(order))
    else:
        print("  (no book root declared, so the include-order checks do not apply)")

    check("no unresolved interpolation leaks into output",
          all("{{" not in c["html"] for c in compiled.values()))

    check("no [?...?] error markers in output",
          all("[?" not in c["html"] for c in compiled.values()))


# ---------------------------------------------------------------------
print("\nInterpolation:")

tmp = with_temp_rules({
    "a.md": """---
id: a
title: Alpha
summary: A test rule.
mechanics:
  speed: 7
---
Speed is {{ mechanics.speed }} tiles.
""",
})
r, c, e = compile_rules(tmp)
check("own-file interpolation resolves", "7 tiles" in c["a"]["html"], c["a"]["html"])
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "a.md": """---
id: a
title: Alpha
summary: A.
mechanics:
  speed: 7
---
Alpha body.
""",
    "b.md": """---
id: b
title: Beta
summary: B.
---
Beta borrows {{ a:mechanics.speed }} from Alpha.
""",
})
r, c, e = compile_rules(tmp)
check("cross-file interpolation resolves", "borrows 7 from" in c["b"]["html"], c["b"]["html"])
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "a.md": """---
id: a
title: Alpha
summary: A.
mechanics:
  domains: [healing, death]
  stance: full_defence
  quick: true
---
It answers to {{ mechanics.domains }} from a {{ mechanics.stance }},
and that is {{ mechanics.quick }}.
""",
})
r, c, e = compile_rules(tmp)
check("a list interpolates as a phrase, not a repr",
      "to healing, death from" in c["a"]["html"], c["a"]["html"])
check("an identifier-shaped string interpolates verbatim, formulas being strings too",
      "a full_defence," in c["a"]["html"], c["a"]["html"])
check("a boolean still interpolates as yes",
      "is yes." in c["a"]["html"], c["a"]["html"])
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "a.md": """---
id: a
title: Alpha
summary: A.
mechanics:
  speed: 7
---
Missing {{ mechanics.nope }} here.
""",
})
r, c, e = compile_rules(tmp)
check("unresolvable interpolation is an error", any("does not resolve" in x for x in e), str(e))
shutil.rmtree(tmp)


# ---------------------------------------------------------------------
print("\nLinks:")

tmp = with_temp_rules({
    "a.md": """---
id: a
title: Alpha
summary: A.
---
See [[b]] and [[b|the other one]].
""",
    "b.md": """---
id: b
title: Beta
summary: B.
---
Beta.
""",
})
r, c, e = compile_rules(tmp)
check("link renders target title by default", ">Beta<" in c["a"]["html"], c["a"]["html"])
check("link honours custom label", ">the other one<" in c["a"]["html"], c["a"]["html"])
check("link edge recorded", "b" in r["a"].links_out)
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "a.md": """---
id: a
title: Alpha
summary: A.
---
See [[ghost]].
""",
})
r, c, e = compile_rules(tmp)
check("broken link is an error", any("does not exist" in x for x in e), str(e))
shutil.rmtree(tmp)


# ---------------------------------------------------------------------
print("\nSchema enforcement:")

tmp = with_temp_rules({"a.md": "no frontmatter here\n"})
try:
    compile_rules(tmp)
    check("missing frontmatter rejected", False)
except RuleError:
    check("missing frontmatter rejected", True)
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "a.md": """---
id: a
title: Alpha
---
No summary field.
""",
})
try:
    compile_rules(tmp)
    check("missing required field rejected", False)
except RuleError as ex:
    check("missing required field rejected", "summary" in str(ex), str(ex))
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "a.md": """---
id: not-a
title: Alpha
summary: A.
---
Body.
""",
})
try:
    compile_rules(tmp)
    check("id/filename mismatch rejected", False)
except RuleError as ex:
    check("id/filename mismatch rejected", "must match" in str(ex), str(ex))
shutil.rmtree(tmp)


# ---------------------------------------------------------------------
print("\nDrift detection (the core guarantee):")

tmp = with_temp_rules({
    "a.md": """---
id: a
title: Alpha
summary: A.
mechanics:
  speed: 7
---
Speed is 7 tiles.
""",
})
r, c, e = compile_rules(tmp)
_, lint_errs = lint.run_all(r)
check("prose duplicating a mechanic value is a lint ERROR",
      any("speed" in x for x in lint_errs), str(lint_errs))
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "a.md": """---
id: a
title: Alpha
summary: A.
mechanics:
  speed: 7
---
Speed is {{ mechanics.speed }} tiles.
""",
})
r, c, e = compile_rules(tmp)
_, lint_errs = lint.run_all(r)
check("interpolated value is NOT flagged", not lint_errs, str(lint_errs))
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "a.md": """---
id: a
title: Alpha
summary: A.
mechanics:
  speed: 7
---
Speed is 9 tiles.
""",
})
r, c, e = compile_rules(tmp)
lint_warns, lint_errs = lint.run_all(r)
check("prose contradicting a mechanic is at least a WARNING",
      any("matches no value" in x for x in lint_warns), str(lint_warns))
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "a.md": """---
id: a
title: Alpha
summary: A.
mechanics:
  pattern_re: "^\\\\d{4}$"
  speed: 7
---
The code `4` is inline code, not a constant. Roll `2d6` freely.
""",
})
r, c, e = compile_rules(tmp)
lint_warns, lint_errs = lint.run_all(r)
check("numbers inside inline code are not flagged", not lint_errs, str(lint_errs))
shutil.rmtree(tmp)


# ---------------------------------------------------------------------
print("\nIncludes:")

tmp = with_temp_rules({
    "root.md": """---
id: root
title: Root
kind: section
summary: R.
---
Intro prose.

{% include child %}

Closing prose.
""",
    "child.md": """---
id: child
title: Child
summary: C.
---
Child body.
""",
})
r, c, e = compile_rules(tmp, root_id="root")
check("include target resolves", not e, str(e))
order = include_order(r, "root")
check("include order is [root, child]", order == [("root", 0), ("child", 1)], str(order))
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "root.md": """---
id: root
title: Root
kind: section
summary: R.
---
{% include mid %}
""",
    "mid.md": """---
id: mid
title: Mid
kind: section
summary: M.
---
{% include leaf %}
""",
    "leaf.md": """---
id: leaf
title: Leaf
summary: L.
---
Leaf body.
""",
})
r, c, e = compile_rules(tmp, root_id="root")
order = include_order(r, "root")
check("nested includes recurse to depth 2",
      order == [("root", 0), ("mid", 1), ("leaf", 2)], str(order))
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "root.md": """---
id: root
title: Root
kind: section
summary: R.
---
{% include ghost %}
""",
})
r, c, e = compile_rules(tmp, root_id="root")
check("include of a missing document is an error",
      any("does not exist" in x for x in e), str(e))
shutil.rmtree(tmp)


# ---------------------------------------------------------------------
print("\nInclude cycles (must never hang):")

tmp = with_temp_rules({
    "a.md": """---
id: a
title: A
kind: section
summary: A.
---
{% include a %}
""",
})
try:
    compile_rules(tmp, root_id="a")
    check("self-include raises", False)
except IncludeCycleError as ex:
    check("self-include raises", ex.cycle_path == ["a", "a"], str(ex.cycle_path))
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "a.md": """---
id: a
title: A
kind: section
summary: A.
---
{% include b %}
""",
    "b.md": """---
id: b
title: B
kind: section
summary: B.
---
{% include a %}
""",
})
try:
    compile_rules(tmp, root_id="a")
    check("two-document cycle raises", False)
except IncludeCycleError as ex:
    check("two-document cycle raises", ex.cycle_path[0] == ex.cycle_path[-1], str(ex.cycle_path))
    check("cycle message names the whole chain",
          set(ex.cycle_path) == {"a", "b"}, str(ex.cycle_path))
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "a.md": """---
id: a
title: A
kind: section
summary: A.
---
{% include b %}
""",
    "b.md": """---
id: b
title: B
kind: section
summary: B.
---
{% include c %}
""",
    "c.md": """---
id: c
title: C
kind: section
summary: C.
---
{% include a %}
""",
})
try:
    compile_rules(tmp, root_id="a")
    check("three-deep cycle raises", False)
except IncludeCycleError as ex:
    check("three-deep cycle raises", len(ex.cycle_path) == 4, str(ex.cycle_path))
    check("cycle path closes on itself",
          ex.cycle_path[0] == ex.cycle_path[-1], str(ex.cycle_path))
shutil.rmtree(tmp)

# A cycle nothing includes is still a bug — catch it before someone
# wires that subtree into the book.
tmp = with_temp_rules({
    "root.md": """---
id: root
title: Root
kind: section
summary: R.
---
Nothing included here.
""",
    "x.md": """---
id: x
title: X
kind: section
summary: X.
---
{% include y %}
""",
    "y.md": """---
id: y
title: Y
kind: section
summary: Y.
---
{% include x %}
""",
})
try:
    compile_rules(tmp, root_id="root")
    check("cycle in an unreachable subtree still raises", False)
except IncludeCycleError as ex:
    check("cycle in an unreachable subtree still raises",
          set(ex.cycle_path) == {"x", "y"}, str(ex.cycle_path))
shutil.rmtree(tmp)

# A diamond is NOT a cycle: it must compile, and warn instead.
tmp = with_temp_rules({
    "root.md": """---
id: root
title: Root
kind: section
summary: R.
---
{% include left %}
{% include right %}
""",
    "left.md": """---
id: left
title: Left
kind: section
summary: L.
---
{% include shared %}
""",
    "right.md": """---
id: right
title: Right
kind: section
summary: R.
---
{% include shared %}
""",
    "shared.md": """---
id: shared
title: Shared
summary: S.
---
Shared body.
""",
})
try:
    r, c, e = compile_rules(tmp, root_id="root")
    check("diamond include is not treated as a cycle", True)
    warns, errs = lint.run_all(r, roots=("root",))
    check("diamond include produces a duplicate warning",
          any("included 2 times" in w for w in warns), str(warns))
except IncludeCycleError as ex:
    check("diamond include is not treated as a cycle", False, str(ex))
shutil.rmtree(tmp)


# ---------------------------------------------------------------------
print("\nSpine removal:")

tmp = with_temp_rules({
    "a.md": """---
id: a
title: A
summary: A.
spine: 10
---
Body.
""",
})
try:
    compile_rules(tmp, root_id="a")
    check("leftover 'spine:' field is rejected", False)
except RuleError as ex:
    check("leftover 'spine:' field is rejected", "spine" in str(ex), str(ex))
shutil.rmtree(tmp)


# ---------------------------------------------------------------------
print("\nBook-only sections:")

# The point of the marker: commentary belongs in the long-form book, not
# in a tooltip. If these two ever agree, the feature has stopped working.
tmp = with_temp_rules({
    "a.md": """---
id: a
title: A
summary: A rule.
---
The mechanic itself.

{% book-only %}
## Design note

Why it is shaped this way.
{% endbook-only %}
""",
})
r, c, e = compile_rules(tmp, root_id="a")
check("book-only content stays in the book form",
      "Why it is shaped this way." in c["a"]["linked"], c["a"]["linked"])
check("book-only content is dropped from the snippet form",
      "Why it is shaped this way." not in c["a"]["html"], c["a"]["html"])
check("book-only heading is dropped from the snippet form",
      "Design note" not in c["a"]["html"], c["a"]["html"])
check("ordinary content survives in both",
      "The mechanic itself." in c["a"]["html"]
      and "The mechanic itself." in c["a"]["linked"])
check("book-only markers never leak into the book form",
      "book-only" not in c["a"]["linked"], c["a"]["linked"])
check("book-only sections compile without errors", not e, str(e))
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "a.md": """---
id: a
title: A
summary: A rule.
---
Body.

{% book-only %}
Never closed.
""",
})
r, c, e = compile_rules(tmp, root_id="a")
check("unclosed book-only block is an error",
      any("never closed" in x for x in e), str(e))
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "a.md": """---
id: a
title: A
summary: A rule.
---
Body.

{% endbook-only %}
""",
})
r, c, e = compile_rules(tmp, root_id="a")
check("stray endbook-only is an error",
      any("no matching" in x for x in e), str(e))
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "a.md": """---
id: a
title: A
summary: A rule.
---
Body.

{% book-only %}
Outer.
{% book-only %}
Inner.
{% endbook-only %}
{% endbook-only %}
""",
})
r, c, e = compile_rules(tmp, root_id="a")
check("nested book-only blocks are an error",
      any("cannot nest" in x for x in e), str(e))
shutil.rmtree(tmp)

# Drift detection must still see inside a book-only block: a design note
# quoting a mechanic value goes stale exactly like any other prose.
tmp = with_temp_rules({
    "a.md": """---
id: a
title: A
summary: A rule.
mechanics:
  base_move_tiles: 7
---
A move carries you {{ mechanics.base_move_tiles }} tiles.

{% book-only %}
## Design note

We picked 7 because it felt right.
{% endbook-only %}
""",
})
r, c, e = compile_rules(tmp, root_id="a")
lint_errs = lint.check_hardcoded_numbers(r)
check("drift detection still reads inside book-only blocks",
      any("base_move_tiles" in x for x in lint_errs), str(lint_errs))
shutil.rmtree(tmp)
# ---------------------------------------------------------------------
print("\nCreatures:")

tmp = with_temp_rules({
    "root.md": """---
id: root
title: Root
kind: section
summary: R.
---
{% include goblin %}
""",
    "bestiary/goblin.md": """---
id: goblin
title: Goblin
kind: creature
summary: Small, mean, numerous.
mechanics:
  core_hit_points: 4
---
A goblin has {{ mechanics.core_hit_points }} core hit points.
""",
})
r, c, e = compile_rules(tmp, root_id="root")
check("kind: creature is accepted", not e, str(e))
warnings, lint_errs = lint.run_all(r, roots=("root",))
check("a creature nothing links to is not an orphan warning",
      not any("discoverable" in w for w in warnings), str(warnings))
check("a creature still gets the drift check", not lint_errs, str(lint_errs))
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "bestiary/goblin.md": """---
id: goblin
title: Goblin
kind: creature
---
No summary.
""",
})
try:
    compile_rules(tmp, root_id="goblin")
    check("a creature still needs a summary", False)
except RuleError as ex:
    check("a creature still needs a summary", "summary" in str(ex), str(ex))
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "bestiary/goblin.md": """---
id: goblin
title: Goblin
kind: monster
summary: S.
---
Body.
""",
})
try:
    compile_rules(tmp, root_id="goblin")
    check("an unknown kind is still rejected", False)
except RuleError as ex:
    check("an unknown kind is still rejected", "is not declared by this corpus" in str(ex),
          str(ex))
shutil.rmtree(tmp)
# ---------------------------------------------------------------------
print("\nTables:")

check("a pipe table renders as a table",
      "<table>" in render_markdown("| A | B |\n|---|---|\n| 1 | 2 |"))
check("the delimiter row becomes a header row",
      "<th>A</th>" in render_markdown("| A | B |\n|---|---|\n| 1 | 2 |"))
check("a table with no delimiter row has no header",
      "<th>" not in render_markdown("| A | B |\n| 1 | 2 |"))
check("alignment comes from the delimiter row",
      'text-align:right' in render_markdown("| A |\n|--:|\n| 1 |"))
check("prose either side of a table stays in paragraphs",
      render_markdown("Before.\n\n| A |\n|---|\n| 1 |\n\nAfter.").startswith("<p>Before.</p>"))
check("a table does not swallow the list before it",
      render_markdown("- item\n\n| A |\n|---|\n| 1 |").startswith("<ul>"))

TABLE_DOC = """---
id: w
title: Weapons
summary: S.
mechanics:
  finesse_size: S
  dagger:
    accuracy: 2
    damage: 5
    quick: true
  great_axe:
    accuracy: -1
    damage: 12
---
%s
"""

tmp = with_temp_rules({"w.md": TABLE_DOC % (
    "{% table mechanics columns=accuracy,damage,quick header=Weapon %}")})
r, c, e = compile_rules(tmp, root_id="w")
html = c["w"]["html"]
check("a table directive builds a table", not e and "<table>" in html, str(e))
check("its rows are the sub-maps, not the loose values",
      "<td>Dagger</td>" in html and "Finesse size" not in html, html)
check("a key becomes a sentence-cased label", "<td>Great axe</td>" in html, html)
check("a boolean cell reads as yes", "<td>yes</td>" in html, html)
check("a field a row lacks reads as a dash", chr(8212) in html, html)
check("the first column header is settable", "<th>Weapon</th>" in html, html)
_, lint_errs = lint.run_all(r, roots=("w",))
check("a generated table does not trip the drift linter", not lint_errs, str(lint_errs))
shutil.rmtree(tmp)

tmp = with_temp_rules({"w.md": TABLE_DOC % (
    "{% table mechanics columns=damage flags=quick:quick %}")})
r, c, e = compile_rules(tmp, root_id="w")
html = c["w"]["html"]
check("flags= collapses booleans into one column",
      not e and "<th>Properties</th>" in html, str(e) + html)
check("a row with the flag names it", "<td>quick</td>" in html, html)
check("a row without it gets a dash", chr(8212) in html, html)
shutil.rmtree(tmp)

tmp = with_temp_rules({"w.md": """---
id: w
title: W
summary: S.
mechanics:
  bulwark:
    protects: mastery_hit_points
    schools: [life_force, influence_and_command]
---
{% table mechanics columns=protects,schools %}
"""})
r, c, e = compile_rules(tmp, root_id="w")
html = c["w"]["html"]
check("an identifier-shaped cell reads as words",
      not e and "mastery hit points" in html, str(e) + html)
check("every item of a list cell is humanised too",
      "life force, influence and command" in html, html)
shutil.rmtree(tmp)

tmp = with_temp_rules({"w.md": TABLE_DOC % "{% table mechanics flags=quick %}"})
r, c, e = compile_rules(tmp, root_id="w")
check("flags= without columns= is an error",
      any("no column to put them in" in x for x in e), str(e))
shutil.rmtree(tmp)

tmp = with_temp_rules({"w.md": TABLE_DOC % (
    "{% table mechanics\n   columns=accuracy:Accuracy,\n           damage:Damage %}")})
r, c, e = compile_rules(tmp, root_id="w")
check("a list ending in a comma continues on the next line",
      not e and "<th>Accuracy</th>" in c["w"]["html"]
      and "<th>Damage</th>" in c["w"]["html"], str(e) + c["w"]["html"])
shutil.rmtree(tmp)

tmp = with_temp_rules({"w.md": TABLE_DOC % "{% table mechanics.dagger header=Stat %}"})
r, c, e = compile_rules(tmp, root_id="w")
check("a map with no columns= renders as field/value pairs",
      not e and "<th>Stat</th>" in c["w"]["html"] and "<th>Value</th>" in c["w"]["html"],
      str(e) + c["w"]["html"])
shutil.rmtree(tmp)

tmp = with_temp_rules({"w.md": TABLE_DOC % (
    "{% table mechanics\n   rows=dagger:\"The dagger\"\n   columns=damage:\"Damage per hit\" %}")})
r, c, e = compile_rules(tmp, root_id="w")
check("a directive may span lines and carry quoted labels",
      not e and "The dagger" in c["w"]["html"]
      and "Damage per hit" in c["w"]["html"], str(e) + c["w"]["html"])
shutil.rmtree(tmp)

for bad, why in [
    ("{% table mechanics.nope columns=damage %}", "does not resolve"),
    ("{% table mechanics rows=ghost columns=damage %}", "not in that map"),
    ("{% table mechanics columns=damage banana=1 %}", "does not understand"),
    ("{% table mechanics.finesse_size %}", "not a map"),
    ("{% table mechanics rows=dagger %}", "needs columns="),
    ("{% table mechanics rows=finesse_size columns=damage %}", "no fields"),
]:
    tmp = with_temp_rules({"w.md": TABLE_DOC % bad})
    r, c, e = compile_rules(tmp, root_id="w")
    check(f"table error: {why}", any(why in x for x in e), str(e))
    shutil.rmtree(tmp)




# ---------------------------------------------------------------------
print("\nSubdirectories:")

tmp = with_temp_rules({
    "root.md": """---
id: root
title: Root
kind: section
summary: R.
---
{% include goblin %}
""",
    "bestiary/goblin.md": """---
id: goblin
title: Goblin
summary: Small, mean, numerous.
mechanics:
  core_hit_points: 4
---
A goblin has {{ mechanics.core_hit_points }} core hit points.
""",
})
r, c, e = compile_rules(tmp, root_id="root")
check("a document in a subdirectory is found", "goblin" in r, str(sorted(r)))
check("a subdirectory document can be included by bare id", not e, str(e))
check("interpolation works in a subdirectory document",
      "4 core hit points" in c.get("goblin", {}).get("html", ""),
      str(c.get("goblin", {}).get("html", "")))
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "a.md": """---
id: a
title: Alpha
summary: One.
---
One.
""",
    "bestiary/a.md": """---
id: a
title: Alpha Again
summary: Two.
---
Two.
""",
})
try:
    compile_rules(tmp, root_id="a")
    check("a duplicate id across subdirectories is rejected", False)
except RuleError as ex:
    check("a duplicate id across subdirectories is rejected",
          "duplicate document id" in str(ex), str(ex))
shutil.rmtree(tmp)




# ---------------------------------------------------------------------
print("\nMarkdown rendering:")

# Rule prose is hard-wrapped, so nearly every list item runs to a second
# line. Treating those as new paragraphs used to close the list after the
# first line and strand the rest underneath it, which rendered as a very
# short bullet, a gap, and then loose text.
wrapped = render_markdown(
    "- **Storytelling.** The rules should push the group towards\n"
    "  descriptive narration rather than away from it.\n"
    "- **Fun.** It should be fun to play.\n"
)
check("a continuation does not split one list into two",
      wrapped.count("<ul>") == 1 and wrapped.count("<li>") == 2,
      wrapped)
check("a wrapped list item keeps its continuation inside the item",
      "descriptive narration" in wrapped.split("</ul>")[0]
      and "<p>descriptive" not in wrapped,
      wrapped)

# A line back at the left margin after a list is still a new paragraph.
after = render_markdown("- one\n- two\nand both of those are boosts:\n")
check("an unindented line after a list still ends it",
      after.count("<ul>") == 1 and "<p>and both of those" in after,
      after)

# ---------------------------------------------------------------------
# ---------------------------------------------------------------------
print("\nRuleset lookup:")

check("a ruleset name is found in the search path",
      rulesc.find_ruleset("demo")[0] is not None)
check("a name that is nowhere is not found",
      rulesc.find_ruleset("no-such-ruleset") == (None, None))

# The case --path exists for: a project that holds the toolset and a
# ruleset as sibling submodules, where the ruleset is in neither search
# directory and so cannot be named at all.
tmp = with_temp_rules({
    "rules/a.md": """---
id: a
title: Alpha
summary: A.
mechanics:
  speed: 7
---
Alpha body.
""",
})
check("a ruleset outside both search directories is unreachable by name",
      rulesc.find_ruleset(tmp.name) == (None, None))
resolved, where = rulesc.resolve_ruleset_dir(
    argparse.Namespace(ruleset="demo", path=str(tmp)))
check("--path overrides the name", resolved == tmp and where == "path",
      f"{resolved} ({where})")
r, c, e = compile_rules(resolved / "rules")
check("a ruleset reached by path compiles like any other", r and not e, str(e))
shutil.rmtree(tmp)


# ---------------------------------------------------------------------
# ---------------------------------------------------------------------
print("\nVersioning:")

tmpdir = Path(tempfile.mkdtemp())
check("a ruleset with no VERSION file is unversioned",
      rulesc.read_version(tmpdir) is None)
(tmpdir / "VERSION").write_text("1.2.3\n", encoding="utf-8")
check("VERSION is read and stripped", rulesc.read_version(tmpdir) == "1.2.3")
(tmpdir / "VERSION").write_text("one point two\n", encoding="utf-8")
try:
    rulesc.read_version(tmpdir)
    check("a version that is not MAJOR.MINOR.PATCH is fatal", False, "no error raised")
except RuleError as e:
    check("a version that is not MAJOR.MINOR.PATCH is fatal", "comparable" in str(e), str(e))
shutil.rmtree(tmpdir)

tmp = with_temp_rules({
    "a.md": """---
id: a
title: Alpha
summary: A.
mechanics:
  speed: 7
---
Alpha body.
""",
})
corpus = corpus_of(tmp)
r, c, e = corpus.docs, corpus.compiled, corpus.errors
stamped = dataclasses.replace(corpus, version="2.0.1")
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    rulesc.build_target(stamped, "mechanics", td / "m.json")
    rulesc.build_target(stamped, "snippets", td / "s.json")
    m = json.loads((td / "m.json").read_text())
    sn = json.loads((td / "s.json").read_text())
    check("mechanics.json is stamped", m["_version"] == "2.0.1", str(list(m)))
    check("the stamp does not join the rules", "_version" not in m["rules"])
    check("snippets.json is stamped", sn["_version"] == "2.0.1", str(list(sn)))
    check("a stamp is told from a document by its leading underscore",
          all(k.startswith("_") or "id" in sn[k] for k in sn), str(list(sn)))

    rulesc.build_target(corpus, "mechanics", td / "m2.json")
    rulesc.build_target(corpus, "snippets", td / "s2.json")
    check("an unversioned build carries no stamp at all",
          "_version" not in json.loads((td / "m2.json").read_text())
          and "_version" not in json.loads((td / "s2.json").read_text()))
shutil.rmtree(tmp)


print("\nBuild outputs:")

if not rules:
    print(f"  SKIPPED — no '{RULESET_NAME}' ruleset content to build outputs from.")
else:
    # By shape rather than by name: a corpus names its targets, and only
    # a ruleset happens to call them book, snippets and mechanics.
    def target_named(shape):
        return next((n for n, t in REAL_PROFILE.targets.items() if t.shape == shape), None)

    DATA_T, SNIP_T, BOOK_T = (target_named(s) for s in ("data", "snippets", "book"))

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        if DATA_T:
            target = REAL_PROFILE.targets[DATA_T]
            n = rulesc.build_target(real, DATA_T, td / "m.json")
            payload = json.loads((td / "m.json").read_text())
            check("the data output contains no prose",
                  all(not isinstance(v, str) or "<p>" not in v
                      for doc in payload["rules"].values() for v in doc.values()))
            check("the data output covers every document that has data",
                  set(payload["rules"]) == {
                      d.id for d in real.local()
                      if target.selects(d, REAL_PROFILE)
                      and any(d.data.get(b) for b in target.blocks)})

        if SNIP_T:
            target = REAL_PROFILE.targets[SNIP_T]
            n2 = rulesc.build_target(real, SNIP_T, td / "s.json")
            snips = json.loads((td / "s.json").read_text())
            entries = {k: v for k, v in snips.items() if not k.startswith("_")}
            check("the snippet output has one entry per document it carries",
                  len(entries) == len([d for d in real.local()
                                       if target.selects(d, REAL_PROFILE)]))
            check("every snippet carries a book anchor",
                  all(s["book_anchor"].startswith("#rule-") for s in entries.values()))
            check("every snippet has both plain and html summary",
                  all(s.get("summary") and s.get("summary_html")
                      for k, s in entries.items()
                      if REAL_PROFILE.kinds[real.docs[k].kind].summary == "required"))

        if BOOK_T and REAL_PROFILE.roots:
            target = REAL_PROFILE.targets[BOOK_T]
            root = target.root or REAL_PROFILE.roots[0]
            size, book_order = rulesc.build_target(real, BOOK_T, td / "b.html")
            book = (td / "b.html").read_text()
            rendered = [d for d in real.local() if target.selects(d, REAL_PROFILE)]
            # The root document's title becomes the book's <h1>, so it gets no
            # section anchor of its own — every OTHER document must have one.
            check("book contains an anchor for every non-root document",
                  all(f'id="rule-{d.id}"' in book for d in rendered if d.id != root))
            check("book TOC is nested (chapters contain documents)",
                  "<ol><ol>" in book or "</li><ol>" in book,
                  "expected nested <ol> in contents")
            check("book renders documents in include order",
                  [d for d, _ in book_order]
                  == [d for d, _ in include_order(rules, root)
                      if target.selects(rules[d], REAL_PROFILE)])
            check("book has no unresolved templates", "{{" not in book)
            check("book has no unresolved directives", "{%" not in book)
            rulesc.build_target(dataclasses.replace(real, version="9.9.9"),
                                BOOK_T, td / "bv.html")
            check("the book shows the version to a reader",
                  "Version 9.9.9" in (td / "bv.html").read_text(encoding="utf-8"))
            # A data block is a machine concern -- the server reads it and
            # the linter proves the prose matches it. The book prints the
            # prose, which already carries every value by interpolation.
            check("book does not print a data table",
                  "Mechanics reference" not in book and 'class="mechanics"' not in book)
            check("data values still reach the book through the prose",
                  any(str(v) in book
                      for d in rendered
                      for block in d.data.values()
                      if isinstance(block, dict)
                      for v in block.values()
                      if isinstance(v, int) and not isinstance(v, bool)))


# ---------------------------------------------------------------------
print("\nCorpus profiles:")

check("a corpus with no corpus.yaml gets the default profile",
      rulesc.Profile.load(Path(tempfile.gettempdir())) == rulesc.Profile.default())
check("the default profile is the old built-in behaviour",
      sorted(rulesc.Profile.default().kinds) == ["creature", "rule", "section"]
      and rulesc.Profile.default().audiences == ("book-only",)
      and sorted(rulesc.Profile.default().targets) == ["book", "mechanics", "snippets"])

ADVENTURE = rulesc.Profile.from_mapping({
    "kinds": {
        "section": {"summary": "optional", "data": [], "discovery": "include"},
        "scene": {"data": ["encounter"], "discovery": "include",
                  "refs": ["encounter.foes", "encounter.branches.*.to"]},
        "npc": {"data": ["mechanics"], "discovery": "lookup", "audience": "gm-only"},
    },
    "audiences": ["gm-only"],
    "roots": [],
    "lint": {"unincluded": False, "orphans": False},
    "targets": {
        "module": {"shape": "book", "root": "top", "audiences": {"default": "keep"}},
        "handout": {"shape": "book", "root": "top",
                    "select": {"kind": ["section", "scene"]},
                    "audiences": {"default": "drop"}},
        "engine": {"shape": "data", "blocks": ["mechanics", "encounter"]},
    },
})
check("a corpus can declare kinds the toolset has never heard of",
      sorted(ADVENTURE.kinds) == ["npc", "scene", "section"])

BY_DIR = rulesc.Profile.from_mapping({
    "kinds": {"part": {"summary": "optional", "data": [], "discovery": "include",
                       "id_from": "directory"}},
    "audiences": [],
    "roots": [],
})
tmp = with_temp_rules({
    "the-ford/part.md": """---
id: the-ford
title: The Ford
kind: part
---
Body.
""",
})
corpus = rulesc.compile_corpus(tmp, profile=BY_DIR)
check("id_from: directory takes the id from the containing directory",
      not corpus.errors and "the-ford" in corpus.docs, str(corpus.errors))
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "the-ford/part.md": """---
id: something-else
title: The Ford
kind: part
---
Body.
""",
})
try:
    rulesc.compile_corpus(tmp, profile=BY_DIR)
    check("an id that does not match its directory is an error", False)
except RuleError as ex:
    check("an id that does not match its directory is an error",
          "containing directory's name 'the-ford'" in str(ex), str(ex))
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "a.md": """---
id: not-a
title: A
summary: A rule.
---
Body.
""",
})
try:
    rulesc.compile_corpus(tmp)
    check("the filename stem rule is untouched by default", False)
except RuleError as ex:
    check("the filename stem rule is untouched by default",
          "filename stem 'a'" in str(ex), str(ex))
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "s.md": """---
id: s
title: S
kind: scene
summary: A scene.
encounter:
  foes: [n]
---
Body.
""",
    "n.md": """---
id: n
title: N
kind: npc
summary: An NPC.
mechanics:
  threat: 3
---
Stat block.
""",
})
corpus = rulesc.compile_corpus(tmp, profile=ADVENTURE)
check("documents of a declared kind compile", not corpus.errors, str(corpus.errors))
check("a kind's declared block lands under its own name",
      list(corpus.docs["s"].data) == ["encounter"], str(corpus.docs["s"].data))
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "s.md": """---
id: s
title: S
kind: scene
summary: A scene.
mechanics:
  threat: 3
---
Body.
""",
})
try:
    rulesc.compile_corpus(tmp, profile=ADVENTURE)
    check("a block the kind does not declare is an error", False)
except RuleError as ex:
    check("a block the kind does not declare is an error",
          "is not a data block of kind" in str(ex), str(ex))
shutil.rmtree(tmp)

for bad, why in (
    ({"targets": {"t": {"shape": "leaflet"}}}, "an unknown shape"),
    ({"targets": {"t": {"shape": "book"}}}, "a prose target with no audience default"),
    ({"audiences": ["a"], "targets": {"t": {"shape": "book",
                                           "audiences": {"default": "maybe"}}}},
     "an audience action that is not keep or drop"),
    ({"kinds": {"r": {"audience": "gm-only"}}}, "a kind audience the corpus never declared"),
    ({"lint": {"hardcoded": False}}, "switching off the hardcoded-number check"),
):
    try:
        rulesc.Profile.from_mapping(bad)
        check(f"{why} is rejected", False)
    except RuleError as ex:
        check(f"{why} is rejected", True)


# ---------------------------------------------------------------------
print("\nAudiences against several targets:")

tmp = with_temp_rules({
    "top.md": """---
id: top
title: Top
kind: section
---
{% include s %}
{% include n %}
""",
    "s.md": """---
id: s
title: S
kind: scene
summary: A scene.
---
Read this aloud.

{% gm-only %}
And this only if you are running it.
{% endgm-only %}
""",
    "n.md": """---
id: n
title: N
kind: npc
summary: An NPC.
---
A whole document for the GM.
""",
})
corpus = rulesc.compile_corpus(tmp, profile=ADVENTURE)
check("a corpus with two audiences compiles", not corpus.errors, str(corpus.errors))
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    rulesc.build_target(corpus, "module", td / "module.html")
    rulesc.build_target(corpus, "handout", td / "handout.html")
    module = (td / "module.html").read_text(encoding="utf-8")
    handout = (td / "handout.html").read_text(encoding="utf-8")
    check("a target that keeps a tag keeps its content",
          "only if you are running it" in module)
    check("a target that drops a tag drops its content",
          "only if you are running it" not in handout)
    check("content outside any tag survives in both",
          "Read this aloud" in module and "Read this aloud" in handout)
    check("no audience markers leak into either output",
          "{%" not in module and "{%" not in handout)
    check("a kind's default audience carries the whole document",
          "A whole document for the GM" in module
          and "A whole document for the GM" not in handout)
    check("a document dropped by its kind's audience is absent, not empty",
          'id="rule-n"' in module and 'id="rule-n"' not in handout)
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "a.md": """---
id: a
title: A
summary: A rule.
---
Body.

{% gm-only %}
Not a tag this corpus declares.
{% endgm-only %}
""",
})
r, c, e = compile_rules(tmp, root_id="a")
check("an undeclared audience tag is an error, not literal text",
      any("not a directive this corpus understands" in x for x in e), str(e))
check("and the error names the directive it did not understand",
      any("{% gm-only %}" in x for x in e), str(e))
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "a.md": """---
id: a
title: A
summary: A rule.
---
{% book-only %}
{% gm-only %}
{% endbook-only %}
{% endgm-only %}
""",
})
two_tags = rulesc.Profile.from_mapping({"audiences": ["book-only", "gm-only"]})
corpus = rulesc.compile_corpus(tmp, profile=two_tags)
check("audience blocks that overlap rather than nest are an error",
      any("still open" in x for x in corpus.errors), str(corpus.errors))
shutil.rmtree(tmp)


# ---------------------------------------------------------------------
print("\nRelated links are per target:")

# A link that lives only inside a span one target drops. Before this was
# per target, "See also" was built once from the whole body and rendered
# in every target -- handing a player-facing output the title of the one
# document the target exists to withhold, with a dead anchor on it.
tmp = with_temp_rules({
    "top.md": """---
id: top
title: Top
kind: section
---
{% include s %}
{% include n %}
""",
    "s.md": """---
id: s
title: S
kind: scene
summary: A scene.
---
Read this aloud.

{% gm-only %}
The one who matters is [[n]].
{% endgm-only %}
""",
    "n.md": """---
id: n
title: The innkeeper is the traitor
kind: npc
summary: An NPC.
---
A whole document for the GM.
""",
})
corpus = rulesc.compile_corpus(tmp, profile=ADVENTURE)
check("a corpus linking into a dropped document compiles", not corpus.errors, str(corpus.errors))
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    rulesc.build_target(corpus, "module", td / "module.html")
    rulesc.build_target(corpus, "handout", td / "handout.html")
    module = (td / "module.html").read_text(encoding="utf-8")
    handout = (td / "handout.html").read_text(encoding="utf-8")
    check("the keeping target still lists the link under See also",
          "See also" in module and "The innkeeper is the traitor" in module)
    check("the dropping target does not list it",
          "The innkeeper is the traitor" not in handout, handout)
    check("and leaves no dead anchor to it",
          "#rule-n" not in handout and 'data-rule-id="n"' not in handout, handout)
    check("the dropping target has no See also line at all here",
          "See also" not in handout, handout)

s_related, _ = rulesc.related_for(corpus, "s", ADVENTURE.targets["module"])
h_related, _ = rulesc.related_for(corpus, "s", ADVENTURE.targets["handout"])
check("related_for reports what each target actually shows",
      s_related == ["n"] and h_related == [], f"{s_related} / {h_related}")
check("doc.links_out is still the whole-corpus answer, for lint",
      corpus.docs["s"].links_out == {"n"}, str(corpus.docs["s"].links_out))

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    snips = dataclasses.replace(ADVENTURE, targets={
        "open": rulesc.Target("open", "snippets", {"default": "keep"}),
        "closed": rulesc.Target("closed", "snippets", {"default": "drop"}),
    })
    c2 = rulesc.compile_corpus(tmp, profile=snips)
    rulesc.build_target(c2, "open", td / "open.json")
    rulesc.build_target(c2, "closed", td / "closed.json")
    opened = json.loads((td / "open.json").read_text(encoding="utf-8"))
    closed = json.loads((td / "closed.json").read_text(encoding="utf-8"))
    check("a snippet's related list is per target too",
          opened["s"]["related"] == ["n"] and closed["s"]["related"] == [],
          f'{opened["s"]["related"]} / {closed["s"]["related"]}')
    check("and the withheld id is nowhere in the closed output",
          '"n"' not in json.dumps(closed["s"]), json.dumps(closed["s"]))
shutil.rmtree(tmp)

# A link a reader CAN see, pointing at a document the target does not
# render. It cannot be a working anchor, so it is rendered as the words
# the author wrote and nothing else -- and the author is warned.
tmp = with_temp_rules({
    "top.md": """---
id: top
title: Top
kind: section
---
{% include s %}
{% include n %}
""",
    "s.md": """---
id: s
title: S
kind: scene
summary: A scene.
---
Ask for [[n|the landlord]] by name.
""",
    "n.md": """---
id: n
title: The innkeeper is the traitor
kind: npc
summary: An NPC.
---
A whole document for the GM.
""",
})
corpus = rulesc.compile_corpus(tmp, profile=ADVENTURE)
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    rulesc.build_target(corpus, "handout", td / "handout.html")
    handout = (td / "handout.html").read_text(encoding="utf-8")
    check("a visible link to an unrendered document keeps the author's words",
          "the landlord" in handout, handout)
    check("but becomes no anchor and leaves no id behind",
          "#rule-n" not in handout and 'data-rule-id="n"' not in handout
          and "The innkeeper is the traitor" not in handout, handout)
warns = rulesc.check_target_links(corpus)
check("and the author is warned rather than left to notice",
      any("'handout' does not render" in w and w.startswith("s:") for w in warns), str(warns))
check("a link the target does render warns about nothing",
      not any("'module' does not render" in w for w in warns), str(warns))
shutil.rmtree(tmp)


# ---------------------------------------------------------------------
print("\nData blocks other than mechanics:")

tmp = with_temp_rules({
    "s.md": """---
id: s
title: S
kind: scene
summary: A scene.
encounter:
  foes: []
  difficulty: 14
  checks:
    - id: spot
      target: 12
    - id: swim
      target: 9
---
Look first against {{ encounter.checks.spot.target }}, then wade
against {{ encounter.checks.swim.target }}. The whole thing is
difficulty {{ encounter.difficulty }}, and the first of those is
also reachable as {{ encounter.checks.0.target }}.
""",
})
corpus = rulesc.compile_corpus(tmp, profile=ADVENTURE)
check("a block named something other than mechanics interpolates",
      not corpus.errors, str(corpus.errors))
html = rulesc.snippet_html(corpus, "s", ADVENTURE.targets["module"])
check("a list entry is addressed by its own id",
      "against 12" in html and "against 9" in html, html)
check("positional addressing works too", "also reachable as 12" in html, html)
_, lint_errs = lint.run_all(corpus.docs, ADVENTURE)
check("a block named something else is still free of drift", not lint_errs, str(lint_errs))
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "s.md": """---
id: s
title: S
kind: scene
summary: A scene.
encounter:
  foes: []
  checks:
    - id: spot
      target: 14
---
Roll against DC 14 to spot them.
""",
})
corpus = rulesc.compile_corpus(tmp, profile=ADVENTURE)
_, lint_errs = lint.run_all(corpus.docs, ADVENTURE)
check("drift detection reaches a number inside a list in any block",
      any("encounter.checks.spot.target" in x for x in lint_errs), str(lint_errs))
shutil.rmtree(tmp)


# ---------------------------------------------------------------------
print("\nInheritance (based_on):")

tmp = with_temp_rules({
    "base.md": """---
id: base
title: Base
kind: npc
summary: A base.
mechanics:
  threat: 2
  attack: 5
  skills: { stealth: 4, spot: 2 }
  gear: [sling]
---
Base body.
""",
    "child.md": """---
id: child
title: Child
kind: npc
summary: A child.
based_on: base
mechanics:
  threat: 4
  skills: { spot: 6 }
  gear: [sword]
---
Child body.
""",
})
corpus = rulesc.compile_corpus(tmp, profile=ADVENTURE)
merged = corpus.docs["child"].mechanics
check("based_on: a declared scalar replaces", merged["threat"] == 4)
check("based_on: an undeclared scalar is inherited", merged["attack"] == 5)
check("based_on: nested maps merge key by key",
      merged["skills"] == {"stealth": 4, "spot": 6}, str(merged["skills"]))
check("based_on: a list replaces wholesale", merged["gear"] == ["sword"], str(merged["gear"]))
check("based_on: the parent is not modified",
      corpus.docs["base"].mechanics["threat"] == 2)
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "child.md": """---
id: child
title: Child
kind: npc
summary: A child.
based_on: nobody
---
Body.
""",
})
corpus = rulesc.compile_corpus(tmp, profile=ADVENTURE)
check("based_on naming a document that does not exist is an error",
      any("based_on names 'nobody'" in x for x in corpus.errors), str(corpus.errors))
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "a.md": """---
id: a
title: A
kind: npc
summary: A.
based_on: b
---
A.
""",
    "b.md": """---
id: b
title: B
kind: npc
summary: B.
based_on: a
---
B.
""",
})
corpus = rulesc.compile_corpus(tmp, profile=ADVENTURE)
check("a based_on cycle is an error rather than a hang",
      any("based_on is a cycle" in x for x in corpus.errors), str(corpus.errors))
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "base.md": """---
id: base
title: Base
kind: npc
summary: A base.
mechanics:
  stamina: 7
---
Base.
""",
    "child.md": """---
id: child
title: Child
kind: npc
summary: A child.
based_on: base
---
It has 7 stamina.
""",
})
corpus = rulesc.compile_corpus(tmp, profile=ADVENTURE)
_, lint_errs = lint.run_all(corpus.docs, ADVENTURE)
check("drift detection catches prose restating an INHERITED value",
      any(x.startswith("child:") for x in lint_errs), str(lint_errs))
shutil.rmtree(tmp)


# ---------------------------------------------------------------------
print("\nDeclared frontmatter references (refs):")

tmp = with_temp_rules({
    "s.md": """---
id: s
title: S
kind: scene
summary: A scene.
encounter:
  foes: [n, nobody]
  branches:
    - when: x
      to: elsewhere
---
Body.
""",
    "n.md": """---
id: n
title: N
kind: npc
summary: An NPC.
---
Body.
""",
})
corpus = rulesc.compile_corpus(tmp, profile=ADVENTURE)
check("a declared ref that does not resolve is an error",
      any("encounter.foes names 'nobody'" in x for x in corpus.errors), str(corpus.errors))
check("a wildcard reaches into a list of maps",
      any("encounter.branches.*.to names 'elsewhere'" in x for x in corpus.errors),
      str(corpus.errors))
check("a declared ref that does resolve is not an error",
      not any("names 'n'" in x for x in corpus.errors), str(corpus.errors))
shutil.rmtree(tmp)

tmp = with_temp_rules({
    "s.md": """---
id: s
title: S
kind: scene
summary: A scene.
encounter:
  foes: []
---
Body.
""",
})
corpus = rulesc.compile_corpus(tmp, profile=ADVENTURE)
check("a declared ref path that is simply absent is not an error",
      not corpus.errors, str(corpus.errors))
shutil.rmtree(tmp)


# ---------------------------------------------------------------------
print("\nReferences into another corpus:")


def built_corpus(files, into: Path, version=None):
    """Build a throwaway corpus's outputs into `into`, the way a
    referenced corpus arrives: through its build directory."""
    src = with_temp_rules(files)
    c = rulesc.compile_corpus(src, version=version)
    assert not c.errors, c.errors
    into.mkdir(parents=True, exist_ok=True)
    rulesc.build_target(c, "snippets", into / "snippets.json")
    rulesc.build_target(c, "mechanics", into / "mechanics.json")
    shutil.rmtree(src)


with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    built_corpus({
        "goblin.md": """---
id: goblin
title: Goblin
kind: creature
summary: A goblin.
mechanics:
  typical_number: 6
  stamina: 5
---
A goblin.
""",
    }, td / "other" / "build", version="1.2.3")

    referring = rulesc.Profile.from_mapping({
        "kinds": {"npc": {"data": ["mechanics"], "discovery": "lookup"}},
        "audiences": [],
        "roots": [],
        "lint": {"unincluded": False, "orphans": False},
        "references": [{"path": "other/build",
                        "href": "../other/book.html#rule-{id}"}],
        "targets": {"snippets": {"shape": "snippets", "audiences": {"default": "drop"}},
                    "data": {"shape": "data", "blocks": ["mechanics"]}},
    })

    src = with_temp_rules({
        "boss.md": """---
id: boss
title: Boss
kind: npc
summary: A boss.
based_on: goblin
mechanics:
  stamina: 9
---
It leads {{ goblin:mechanics.typical_number }} of them, and it is a
[[goblin]] underneath.
""",
    })
    corpus = rulesc.compile_corpus(src, profile=referring, base_dir=td)
    check("a corpus compiles against another corpus's build outputs",
          not corpus.errors, str(corpus.errors))
    check("an external document joins the same flat id namespace",
          "goblin" in corpus.docs and corpus.docs["goblin"].external)
    check("interpolation reaches across the seam with no new syntax",
          "leads 6 of them" in rulesc.snippet_html(
              corpus, "boss", referring.targets["snippets"]))
    html = rulesc.snippet_html(corpus, "boss", referring.targets["snippets"])
    check("a cross-corpus link uses the declared href",
          'href="../other/book.html#rule-goblin"' in html, html)
    check("a cross-corpus link is marked as external",
          'class="external-ref"' in html, html)
    check("based_on reaches across the seam",
          corpus.docs["boss"].mechanics == {"typical_number": 6, "stamina": 9},
          str(corpus.docs["boss"].mechanics))
    check("the referenced version is recorded",
          corpus.references[0]["version"] == "1.2.3", str(corpus.references))

    with tempfile.TemporaryDirectory() as out:
        out = Path(out)
        rulesc.build_target(corpus, "snippets", out / "s.json")
        rulesc.build_target(corpus, "data", out / "d.json")
        s = json.loads((out / "s.json").read_text(encoding="utf-8"))
        d = json.loads((out / "d.json").read_text(encoding="utf-8"))
        check("the output says which version it was built against",
              s["_references"][0]["version"] == "1.2.3"
              and d["_references"][0]["version"] == "1.2.3")
        check("an external document is never emitted as one of ours",
              "goblin" not in s and "goblin" not in d["rules"])
        check("a document records what it was based on",
              s["boss"]["based_on"] == "goblin")
        check("a document records the external documents it links to",
              s["boss"]["external"] == ["goblin"])
    shutil.rmtree(src)

    src = with_temp_rules({
        "boss.md": """---
id: boss
title: Boss
kind: npc
summary: A boss.
---
Nothing here is [[missing-entirely]].
""",
    })
    corpus = rulesc.compile_corpus(src, profile=referring, base_dir=td)
    check("an unresolvable cross-corpus reference is an error, not a blank",
          any("does not exist" in x for x in corpus.errors), str(corpus.errors))
    shutil.rmtree(src)

    src = with_temp_rules({
        "goblin.md": """---
id: goblin
title: Our Own Goblin
kind: npc
summary: A goblin of our own.
---
Body.
""",
    })
    corpus = rulesc.compile_corpus(src, profile=referring, base_dir=td)
    check("an id in both corpora is an error rather than a silent shadow",
          any("duplicate document id 'goblin'" in x for x in corpus.errors),
          str(corpus.errors))
    shutil.rmtree(src)

    unbuilt = rulesc.Profile.from_mapping({
        "references": [{"path": "nowhere/build"}],
    })
    src = with_temp_rules({
        "rulebook.md": """---
id: rulebook
title: Book
kind: section
---
Body.
""",
    })
    try:
        rulesc.compile_corpus(src, profile=unbuilt, base_dir=td)
        check("a reference to something unbuilt says so", False)
    except RuleError as ex:
        check("a reference to something unbuilt says so",
              "has not been built" in str(ex), str(ex))
    shutil.rmtree(src)


# ---------------------------------------------------------------------
print("\nA vendored reference, and its provenance stamp:")


def with_stamp(where: Path, stamp):
    (where / "VENDORED.json").write_text(
        json.dumps(stamp) if isinstance(stamp, (dict, list)) else stamp,
        encoding="utf-8")


with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    outputs = td / "other" / "build"
    built_corpus({
        "goblin.md": """---
id: goblin
title: Goblin
kind: creature
summary: A goblin.
mechanics:
  typical_number: 6
---
A goblin.
""",
    }, outputs, version="1.2.3")

    vendored = rulesc.Profile.from_mapping({
        "kinds": {"npc": {"data": ["mechanics"], "discovery": "lookup"}},
        "audiences": [],
        "roots": [],
        "lint": {"unincluded": False, "orphans": False},
        "references": [{"path": "other/build", "name": "other"}],
        "targets": {"snippets": {"shape": "snippets",
                                 "audiences": {"default": "drop"}}},
    })
    files = {
        "boss.md": """---
id: boss
title: Boss
kind: npc
summary: A boss.
---
It leads {{ goblin:mechanics.typical_number }} of them.
""",
    }

    src = with_temp_rules(files)
    corpus = rulesc.compile_corpus(src, profile=vendored, base_dir=td)
    check("an unstamped reference records exactly what it always did",
          corpus.references[0] == {"name": "other", "version": "1.2.3",
                                   "source": "other/build"},
          str(corpus.references))
    shutil.rmtree(src)

    with_stamp(outputs, {"version": "1.2.3", "commit": "abc123",
                         "describe": "v1.2.3-2-gabc123",
                         "vendored_by": "somebody else's script"})
    src = with_temp_rules(files)
    corpus = rulesc.compile_corpus(src, profile=vendored, base_dir=td)
    check("a stamp carries the revision through to the reference record",
          corpus.references[0].get("commit") == "abc123"
          and corpus.references[0].get("describe") == "v1.2.3-2-gabc123",
          str(corpus.references))
    check("a stamp agreeing with the outputs is silent",
          not corpus.warnings, str(corpus.warnings))
    check("a field the toolset does not read is left alone, not copied",
          "vendored_by" not in corpus.references[0],
          str(corpus.references))
    with tempfile.TemporaryDirectory() as out:
        rulesc.build_target(corpus, "snippets", Path(out) / "s.json")
        s = json.loads((Path(out) / "s.json").read_text(encoding="utf-8"))
        check("the built output says which revision, not just which version",
              s["_references"][0]["commit"] == "abc123", str(s["_references"]))
    shutil.rmtree(src)

    # The outputs govern: they are what was actually built against, so a
    # stamp disagreeing with them is the half of the pair that lies.
    with_stamp(outputs, {"version": "9.9.9", "commit": "abc123"})
    src = with_temp_rules(files)
    corpus = rulesc.compile_corpus(src, profile=vendored, base_dir=td)
    check("a stamp disagreeing with the outputs warns and names both",
          any("9.9.9" in w and "1.2.3" in w for w in corpus.warnings),
          str(corpus.warnings))
    check("the version recorded is still the outputs', not the stamp's",
          corpus.references[0]["version"] == "1.2.3", str(corpus.references))
    shutil.rmtree(src)

    # A consumer whose vendoring tool names its fields something else
    # gets told, rather than silently recording nothing.
    with_stamp(outputs, {"sha": "abc123", "tag": "v1.2.3"})
    src = with_temp_rules(files)
    corpus = rulesc.compile_corpus(src, profile=vendored, base_dir=td)
    check("a stamp carrying none of the fields read says which fields those are",
          any("commit, describe" in w for w in corpus.warnings),
          str(corpus.warnings))
    shutil.rmtree(src)

    with_stamp(outputs, "{not json at all")
    src = with_temp_rules(files)
    try:
        rulesc.compile_corpus(src, profile=vendored, base_dir=td)
        check("an unreadable stamp is an error rather than a shrug", False)
    except RuleError as ex:
        check("an unreadable stamp is an error rather than a shrug",
              "VENDORED.json" in str(ex), str(ex))
    shutil.rmtree(src)

    with_stamp(outputs, ["a", "list"])
    src = with_temp_rules(files)
    try:
        rulesc.compile_corpus(src, profile=vendored, base_dir=td)
        check("a stamp that is not an object is an error", False)
    except RuleError as ex:
        check("a stamp that is not an object is an error",
              "not an object" in str(ex), str(ex))
    shutil.rmtree(src)


# ---------------------------------------------------------------------
print("\nCollapsible sections:")

check("a heading matches its own name", collapses("Design note", ["Design note"]))
check("matching ignores case", collapses("DESIGN NOTE", ["design note"]))
check("a suffix after a colon still matches",
      collapses("Design note: why the axe is the cheap one", ["Design note"]))
check("a suffix after an em dash still matches",
      collapses("Design note \u2014 the ladder", ["Design note"]))
# The reason a bare prefix match is not enough: this heading starts with
# the declared name and is a different section.
check("a longer word starting with the name does not match",
      not collapses("Design notes we abandoned", ["Design note"]))
check("an unrelated heading does not match", not collapses("Example", ["Design note"]))
check("an empty declared name matches nothing rather than everything",
      not collapses("Example", [""]))

folded = render_markdown("## Design note\n\nWhy it is so.\n", collapse=["Design note"])
check("a folded section renders as a closed details",
      folded.startswith('<details class="aside"><summary><h2>Design note</h2></summary>'),
      folded)
check("its body is inside it", "<p>Why it is so.</p>" in folded and folded.endswith("</details>"),
      folded)
check("nothing is folded when the target names nothing",
      "<details" not in render_markdown("## Design note\n\nWhy it is so.\n"))

# The extent rule: to the next heading at the same level or higher.
two = render_markdown("## Design note\n\nA.\n\n## Example\n\nB.\n",
                      collapse=["Design note"])
check("a sibling heading closes the fold",
      two.index("</details>") < two.index("<h2>Example</h2>"), two)
check("what follows the fold is outside it", two.count("<details") == 1, two)

nested = render_markdown("## Design note\n\nA.\n\n### Deeper\n\nB.\n\n## After\n\nC.\n",
                         collapse=["Design note"])
check("a deeper heading stays inside the fold",
      nested.index("<h3>Deeper</h3>") < nested.index("</details>"), nested)
check("the next sibling still closes it",
      nested.index("</details>") < nested.index("<h2>After</h2>"), nested)

trailing = render_markdown("## Rule\n\nA.\n\n## Design note\n\nB.\n",
                           collapse=["Design note"])
check("a fold running to the end of the document is closed",
      trailing.endswith("</details>") and trailing.count("<details") == 1, trailing)

offset = render_markdown("## Design note\n\nA.\n", heading_offset=2,
                         collapse=["Design note"])
check("the heading inside the summary carries the offset",
      "<summary><h4>Design note</h4></summary>" in offset, offset)

# A folded section is content, not a container: lists and tables inside
# it must still be flushed before it closes.
rich = render_markdown("## Design note\n\n- one\n- two\n\n## After\n\nB.\n",
                       collapse=["Design note"])
check("a list inside a fold is closed before the fold is",
      rich.index("</ul>") < rich.index("</details>"), rich)

# A profile check: the field is book-only, and says so rather than
# silently doing nothing.
try:
    rulesc.Profile.from_mapping({
        "targets": {"snippets": {"shape": "snippets", "audiences": {"default": "drop"},
                                 "collapse": ["Design note"]}}})
    check("collapse on a non-book target is refused", False, "no error raised")
except RuleError as e:
    check("collapse on a non-book target is refused", "Only a book renders headings" in str(e), str(e))
try:
    rulesc.Profile.from_mapping({
        "targets": {"book": {"shape": "book", "root": "rulebook",
                             "audiences": {"default": "keep"}, "collapse": [" "]}}})
    check("an empty collapse name is refused", False, "no error raised")
except RuleError as e:
    check("an empty collapse name is refused", "empty heading" in str(e), str(e))

profile = rulesc.Profile.from_mapping({
    "targets": {"book": {"shape": "book", "root": "rulebook",
                         "audiences": {"default": "keep"},
                         "collapse": "Design note"}}})
check("a single collapse name may be written without a list",
      profile.targets["book"].collapse == ("Design note",),
      str(profile.targets["book"].collapse))
check("a book target declaring no collapse gets an empty one",
      rulesc.Profile.default().targets["book"].collapse == ())


# ---------------------------------------------------------------------
print("\nLint against many roots, or none:")

tmp = with_temp_rules({
    "one.md": """---
id: one
title: One
kind: scene
summary: A scene.
---
Body.
""",
    "two.md": """---
id: two
title: Two
kind: scene
summary: A scene.
---
Body.
""",
})
corpus = rulesc.compile_corpus(tmp, profile=ADVENTURE)
warns, errs = lint.run_all(corpus.docs, ADVENTURE)
check("a corpus with no roots is not told its book root is missing",
      not any("book root" in w for w in warns), str(warns))
check("a corpus with no roots gets no reachability warnings at all",
      not any("not included anywhere" in w for w in warns), str(warns))
check("the hardcoded-number check still runs with no roots", errs == [], str(errs))

# The same corpus with the reachability check left on, to show that
# "no roots" is what skips it rather than the check being gone.
CHECKED = dataclasses.replace(ADVENTURE, lint={"orphans": False})
warns, _ = lint.run_all(corpus.docs, CHECKED, roots=("one", "two"))
check("reachability from several roots is their union",
      not any("not included anywhere" in w for w in warns), str(warns))
warns, _ = lint.run_all(corpus.docs, CHECKED, roots=("one",))
check("a document under no root is still reported",
      any(w.startswith("two:") for w in warns), str(warns))
shutil.rmtree(tmp)


# ---------------------------------------------------------------------
print("\nThe supplement corpus (the worked example):")

SUPPLEMENT = rulesc.find_ruleset("demo-supplement")[0]
if SUPPLEMENT is None or not (SUPPLEMENT / "build" / "data.json").exists():
    print("  SKIPPED — demo-supplement is not built; run "
          "python3 tools/build.py demo && python3 tools/build.py demo-supplement")
else:
    profile = rulesc.Profile.load(SUPPLEMENT)
    corpus = rulesc.compile_corpus(SUPPLEMENT / "rules", SUPPLEMENT / "book",
                                   profile=profile, base_dir=SUPPLEMENT)
    check("the supplement compiles with no errors", not corpus.errors, str(corpus.errors))
    _, lint_errs = lint.run_all(corpus.docs, profile)
    check("the supplement passes lint", not lint_errs, str(lint_errs))
    check("it declares kinds of its own",
          sorted(profile.kinds) == ["encounter", "foe", "note", "section"])
    check("one of them takes its id from its directory",
          profile.kinds["encounter"].id_from == "directory"
          and "the-crossing" in corpus.docs)
    check("it declares two audiences and four targets",
          len(profile.audiences) == 2 and len(profile.targets) == 4)
    data = json.loads((SUPPLEMENT / "build" / "data.json").read_text(encoding="utf-8"))
    check("a multi-block data output names its blocks",
          data["_blocks"] == ["mechanics", "setup"], str(data.get("_blocks")))
    check("a multi-block data output keys each document by block name",
          set(data["rules"]["the-crossing"]) == {"setup"},
          str(data["rules"]["the-crossing"]))
    book = (SUPPLEMENT / "build" / "book.html").read_text(encoding="utf-8")
    handout = (SUPPLEMENT / "build" / "handout.html").read_text(encoding="utf-8")
    check("the book keeps GM material", "Running it" in book)
    check("the handout keeps none of it", "Running it" not in handout)
    check("the handout omits whole GM documents",
          'id="rule-gm-notes"' in book and 'id="rule-gm-notes"' not in handout)
    check("no directive markers survive into either", "{%" not in book and "{%" not in handout)
    check("the book folds away the sections the target names",
          book.count('<details class="aside">') == 6, book.count('<details class="aside">'))
    check("every folded section is closed",
          book.count('<details class="aside">') == book.count("</details>"))
    check("a folded section is closed, not open -- the reader opens it",
          "<details open" not in book and 'class="aside" open' not in book)
    check("the heading survives inside the summary, so the outline does",
          "<summary><h4>Running it</h4></summary>" in book)
    check("a name matches a heading that carries a suffix",
          "<summary><h3>Design note: inheritance, and when it is resolved</h3></summary>"
          in book)
    check("a target that names none folds none",
          "<details" not in handout)


print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
