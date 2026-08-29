---
id: movement
title: Movement
tags: [core, combat, map]
summary: >
  A move carries you a number of tiles across the grid. Difficult ground
  costs double; some ground stops you entirely.
mechanics:
  base_move_tiles: 4
  diagonal_cost: 1
  difficult_terrain_multiplier: 2
  grid_size: 14
  can_move_through_allies: true
  can_move_through_enemies: false
---

The battle map is a grid of square tiles, {{ mechanics.grid_size }} on a
side. Distance is counted in tiles, never in feet or metres — this game
does not care how big a tile "really" is, and neither should you.

## How far you go

A move carries you up to {{ mechanics.base_move_tiles }} tiles. Diagonal
steps cost {{ mechanics.diagonal_cost }} tile, the same as orthogonal
ones; this is deliberately generous and deliberately simple.

Difficult ground — rubble, deep water, a floor of broken glass — costs
{{ mechanics.difficult_terrain_multiplier }} tiles for every tile
entered. The Dungeon Master declares difficult ground when the scene is
described, not after you have committed to a route.

## Who is in the way

You may move through a tile occupied by an ally. You may not move
through one occupied by an enemy: you must go around, or remove them
from the tile first.

You get one move per turn ordinarily — see [[turn-order]].

{% book-only %}
## Design note

Diagonals costing the same as orthogonal steps is wrong and deliberate.
Charging more is more accurate and slows every turn down with
arithmetic; the generosity is the price of a grid you can move on
without counting twice.
{% endbook-only %}
