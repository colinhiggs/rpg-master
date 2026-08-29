---
id: turn-order
title: Turn Order
tags: [core, combat]
summary: >
  Combat runs in rounds. Every combatant acts once per round, in a fixed
  initiative order set when combat begins.
mechanics:
  initiative_roll: "1d20"
  rounds_are_simultaneous: false
  actions_per_turn: 1
  moves_per_turn: 1
---

When talking stops and violence starts, time breaks into **rounds**.
Every combatant — player characters, monsters, the innkeeper who picked
the wrong side — acts exactly once per round.

## Establishing the order

At the start of combat, each combatant rolls
{{ mechanics.initiative_roll }}. Highest goes first, and that order
holds for the whole fight. Ties are broken by the Dungeon Master, who
should break them in the players' favour when it genuinely does not
matter.

## What a turn contains

On your turn you may take {{ mechanics.actions_per_turn }} action and
{{ mechanics.moves_per_turn }} move, in either order. You may always
choose to do less. Talking is free, within reason — a shouted warning
costs nothing, a monologue costs your action.

Moving is measured in tiles; see [[movement]] for what a move gets you
and what stops it. If your action is an attack, see [[attacks]].

Rounds do not resolve simultaneously. Each combatant's turn fully
finishes — damage applied, effects triggered — before the next begins.
