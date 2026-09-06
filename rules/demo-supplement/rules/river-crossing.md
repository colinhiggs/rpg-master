---
id: river-crossing
title: The Crossing
kind: encounter
tags: [encounter]
summary: >
  A wide ford, watched from the reeds by people who chose it first.
setup:
  foes: [goblin-scout, goblin-scout, goblin-captain]
  checks:
    - id: spot-the-ford
      difficulty: 14
      on_success: cross-unseen
    - id: keep-your-footing
      difficulty: 9
  leads_to: aftermath
---

The water is slow and shallow enough to wade and the far bank is a long
way off. Both of those are why the reeds are worth watching.

Anyone crossing may look at the banks first, against a difficulty of
{{ setup.checks.spot-the-ford.difficulty }}. Anyone hurrying across
instead is keeping their footing against
{{ setup.checks.keep-your-footing.difficulty }}, and the streambed
counts as difficult ground under [[movement]] — each tile entered costs
{{ movement:mechanics.difficult_terrain_multiplier }}.

{% gm-only %}
## Running it

The scouts open and the captain does not, until somebody is in the
water. If the party spotted the reeds, reverse that: the captain has
nothing to gain by waiting for an ambush that is not going to happen.
{% endgm-only %}

Whichever way it ends, it ends at [[aftermath]].

{% book-only %}
## Design note

Two things here have no equivalent in a ruleset. The block is called
`setup` rather than `mechanics`, and the prose interpolates out of it by
name; a block is addressed by the name its kind declares, so the toolset
never has to be told what an encounter is.

And the checks are a list, addressed by each entry's own `id` rather
than by position — write `setup.checks.spot-the-ford.difficulty`, not
`setup.checks.0.difficulty`, so that adding a check at the top of the
list does not silently repoint every number in the paragraph below it.

Both difficulties are covered by the drift check exactly as a rule's
values are: write one of them out as a digit and the build fails.
{% endbook-only %}
