# test_rules.py — tests for the guarantees the format is supposed to give.
#
# Run: python3 tools/test_rules.py
#
# These test the PIPELINE, not the game balance. The thing worth
# protecting is the invariant "a value exists in exactly one place";
# each test below is a way that invariant could quietly break.

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import lint
from rulesc import (
    IncludeCycleError, RuleError,
    compile_docs, detect_cycles, include_order,
)

TOOLSET_ROOT = Path(__file__).parent.parent       # .../rpg-master/rules-toolset
# Same two-place search as build.py: rulesets installed into the game,
# then rulesets being authored in the outer working directory.
RULESET_SEARCH_PATH = (TOOLSET_ROOT.parent / "rules",
                       TOOLSET_ROOT.parent.parent / "rules")

# Which ruleset the "real rules" section below exercises against. The
# pipeline tests themselves (interpolation, links, includes, cycles,
# drift detection) build throwaway rulesets with with_temp_rules() and
# don't depend on this — this only picks which real content acts as an
# integration smoke test. Override with a CLI arg: `test_rules.py ico`.
RULESET_NAME = sys.argv[1] if len(sys.argv) > 1 else "demo"
RULESET_DIR = next((r / RULESET_NAME for r in RULESET_SEARCH_PATH
                    if (r / RULESET_NAME).exists()), None)
if RULESET_DIR is None:
    sys.exit("no ruleset '%s' in %s" % (RULESET_NAME, RULESET_SEARCH_PATH))
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
        (tmp / fname).write_text(content, encoding="utf-8")
    return tmp


def compile_rules(d, root_id="rulebook"):
    return compile_docs(d, root_id=root_id)


# ---------------------------------------------------------------------
print(f"\nReal rule set ('{RULESET_NAME}'):")

if not RULES_DIR.exists() and not BOOK_DIR.exists():
    print(f"  SKIPPED — {RULESETS_DIR / RULESET_NAME} has no rules/ or book/ yet "
          "(expected for an empty ruleset like a freshly-created 'ico').")
    rules = {}
else:
    rules, compiled, errors = compile_docs(RULES_DIR, BOOK_DIR)
    check("real rules compile with no errors", not errors, str(errors))

    warnings, lint_errors = lint.run_all(rules)
    check("real rules pass lint", not lint_errors, str(lint_errors))

    check("every rule (kind=rule) has a non-empty summary",
          all(r.summary.strip() for r in rules.values() if r.kind == "rule"))

    check("book root exists", "rulebook" in rules)

    order = include_order(rules, "rulebook")
    check("include order covers every document", len(order) == len(rules),
          f"{len(order)} in order vs {len(rules)} docs")
    check("root is first in include order", order[0] == ("rulebook", 0), str(order[:1]))
    check("rules nest two deep (root > chapter > rule)",
          any(d == 2 for _, d in order), str(order))

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
      any("matches no mechanic" in x for x in lint_warns), str(lint_warns))
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
    warns, errs = lint.run_all(r, root_id="root")
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
print("\nBuild outputs:")

sys.path.insert(0, str(Path(__file__).parent))
import build as build_mod

if not rules:
    print(f"  SKIPPED — no '{RULESET_NAME}' ruleset content to build outputs from.")
else:
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        n = build_mod.build_mechanics(rules, td / "m.json")
        payload = json.loads((td / "m.json").read_text())
        check("mechanics.json contains no prose",
              all(not isinstance(v, str) or "<p>" not in v
                  for rule in payload["rules"].values() for v in rule.values()))
        check("mechanics.json covers every rule that has mechanics",
              set(payload["rules"]) == {r.id for r in rules.values() if r.mechanics})

        n2 = build_mod.build_snippets(rules, compiled, td / "s.json")
        snips = json.loads((td / "s.json").read_text())
        check("snippets.json has one entry per rule", len(snips) == len(rules))
        check("every snippet carries a book anchor",
              all(s["book_anchor"].startswith("#rule-") for s in snips.values()))
        check("every snippet has both plain and html summary",
              all(s.get("summary") and s.get("summary_html") for s in snips.values()))

        size, book_order = build_mod.build_book(rules, compiled, td / "b.html")
        book = (td / "b.html").read_text()
        # The root document's title becomes the book's <h1>, so it gets no
        # section anchor of its own — every OTHER document must have one.
        check("book contains an anchor for every non-root document",
              all(f'id="rule-{r.id}"' in book for r in rules.values() if r.id != "rulebook"))
        check("book TOC is nested (chapters contain rules)", "<ol><ol>" in book or "</li><ol>" in book,
              "expected nested <ol> in contents")
        check("book renders documents in include order",
              [d for d, _ in book_order] == [d for d, _ in include_order(rules, "rulebook")])
        check("book has no unresolved templates", "{{" not in book)


print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
