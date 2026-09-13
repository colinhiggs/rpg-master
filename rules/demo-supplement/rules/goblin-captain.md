---
id: goblin-captain
title: Captain
kind: foe
tags: [foe]
summary: >
  The one that has to die before the rest of them will run.
based_on: goblin-scout
mechanics:
  threat: 4
  hit_points: 13
  gear: [shield, sword]
---

A captain is a scout that has survived long enough to take something
better off somebody. It keeps the scout's reflexes and loses the
scout's willingness to leave.

{% table mechanics rows=threat,attack,hit_points,speed_tiles %}

Its attack of {{ mechanics.attack }} is inherited rather than declared —
this document's frontmatter says nothing about it, and changing the
scout changes it here. Its {{ mechanics.gear }} replace the scout's
outright, because a list is a statement about a whole set: a captain
carrying a shield and a sword is not also still carrying a sling.

{% book-only %}
## Design note: inheritance, and when it is resolved

`based_on` merges block by block. Scalars replace, nested maps merge key
by key, lists replace wholesale. It is resolved before anything reads
the data, which is why the drift linter catches prose here restating an
INHERITED value as readily as a declared one — try writing the attack
value out as a literal and the build fails.
{% endbook-only %}
