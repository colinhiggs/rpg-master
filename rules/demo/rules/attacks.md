---
id: attacks
title: Attacks
tags: [core, combat]
summary: >
  Roll to hit against the target's defence, then roll damage. Melee
  reaches one tile; ranged attacks have a listed range.
mechanics:
  attack_roll: "1d20"
  base_defence: 10
  melee_range_tiles: 1
  default_damage: "1d6"
  critical_damage_multiplier: 2
---

An attack is an action, so ordinarily you get one per turn — see
[[turn-order]].

## Resolving an attack

Roll {{ mechanics.attack_roll }} and add your relevant modifier. If the
total meets or beats the target's defence, you hit. An unmodified
defence is {{ mechanics.base_defence }}; armour, cover and magic adjust
it from there.

A critical success on the attack roll (see [[dice-rolls]]) hits
automatically and multiplies the damage dice by
{{ mechanics.critical_damage_multiplier }}. Multiply the dice, not the
modifier.

## Range

Melee attacks reach {{ mechanics.melee_range_tiles }} tile. Ranged
attacks list their own range; beyond it you simply cannot make the
attack, rather than suffering a penalty.

## Damage

On a hit, roll the weapon's damage — {{ mechanics.default_damage }} if
the weapon has nothing listed — and apply it as described in
[[damage-and-healing]].
