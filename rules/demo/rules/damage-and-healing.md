---
id: damage-and-healing
title: Damage and Healing
tags: [core, combat, health]
summary: >
  Hit points measure how much harm you can absorb. At zero you are
  downed; healing never carries you above your maximum.
mechanics:
  starting_hp: 20
  min_hp: 0
  downed_at_hp: 0
  healing_caps_at_max: true
  overkill_carries_over: false
---

Every creature has **hit points**: an abstract pool covering luck,
stamina, minor wounds and sheer stubbornness. A starting character has
{{ mechanics.starting_hp }} of them.

## Taking damage

Damage subtracts from your current hit points. Damage rolls never
critical — see [[dice-rolls]]. Hit points cannot fall below
{{ mechanics.min_hp }}; excess damage is simply discarded rather than
carrying over into anything worse.

At {{ mechanics.downed_at_hp }} hit points you are **downed**: you are
out of the fight, unable to act, and stable unless the fiction says
otherwise. This game does not use death saves. Whether a downed
character dies is a question for the table, not the dice.

## Healing

Healing adds hit points back. It cannot carry you above your maximum —
surplus healing is wasted, not stored. Nothing in the base rules heals a
downed character back to acting on the same turn they fell.

Applying damage or healing is a Dungeon Master action in play; see
[[dm-tools]].
