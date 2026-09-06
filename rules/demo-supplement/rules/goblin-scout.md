---
id: goblin-scout
title: Scout
kind: foe
tags: [foe]
summary: >
  Fast, cowardly, and there to be seen a moment too late.
mechanics:
  threat: 2
  attack: 5
  hit_points: 6
  speed_tiles: 7
  gear: [sling, knife]
---

A scout is the cheapest thing that can still make a crossing expensive.
It carries {{ mechanics.gear }} and no armour worth the name.

{% table mechanics rows=threat,attack,hit_points,speed_tiles %}

It moves {{ mechanics.speed_tiles }} tiles, which is further than the
{{ movement:mechanics.base_move_tiles }} tiles a character gets under
[[movement]] — so a scout that decides to leave has left.

{% book-only %}
## Design note

This document is the base of an inheritance chain: the captain below
declares only what differs. Note also the two references reaching into
the `demo` corpus — a link and an interpolation — neither of which needs
any syntax of its own. A document is addressed the same way whether it
is in this corpus or in one this corpus references.
{% endbook-only %}
