---
id: the-far-bank
title: The Far Bank
kind: encounter
tags: [encounter]
summary: >
  Wet, short of arrows, and a long way from anywhere to dry out.
---

Whoever is still standing is on the far bank, and whatever they were
carrying has been in the river.

Going back across is a question about the weather rather than about the
[[river-tarn|Tarn]], which is passable at the ford below
{{ river-tarn:mechanics.ford_passable_below_inches }} inches and rises
within {{ river-tarn:mechanics.rises_after_rain_in_hours }} hours of
rain on the moor.

{% gm-only %}
## Running it

There is nothing left to fight here. What there is instead is a
decision about whether to go back for anything, and it should cost
something either way.
{% endgm-only %}

{% book-only %}
## Design note

This document carries no data block at all, which is allowed: a kind
says which blocks its documents *may* carry, not which they must. It is
here because [[the-crossing]] names it in frontmatter — `setup.leads_to`
is declared as holding a document id, so an encounter pointing at an
encounter that does not exist is a build error rather than something
discovered at the table.

It is also where the second kind of reference is used. `river-tarn` is
not a document in this corpus and is not in `demo` either: it comes from
`refs/almanac/`, a *vendored* corpus — a committed copy of what that
corpus published, rather than a path to a checkout of it. Nothing in the
paragraph above says so, which is the point. A reference is a reference,
and where the outputs came from is a question about this repository
rather than about the prose.

What differs is what gets recorded and what a link can do. Because the
copy carries a `VENDORED.json` stamp, `_references` in the built outputs
says which *revision* of 3.1.0 this was built against and not merely the
version. And because only the data was vendored and not the book, the
reference declares no `href`, so the link renders as a span carrying
`data-rule-id` rather than as an anchor into a book nobody has. A dead
anchor would be worse than no anchor.
{% endbook-only %}
