---
id: dice-rolls
title: Rolling Dice
tags: [core, resolution]
summary: >
  Uncertain actions resolve by rolling dice in `XdY+Z` notation and
  comparing the total against a target number.
mechanics:
  notation_pattern: "^(\\d*)d(\\d+)([+-]\\d+)?$"
  default_roll: "1d20"
  max_dice_per_roll: 100
  max_sides: 1000
  critical_success: 20
  critical_failure: 1
---

When the outcome of an action is genuinely in doubt, you roll dice for
it. Everything in this game resolves the same way, whether you are
picking a lock, swinging an axe, or convincing a guard to look the
other way.

## Notation

Rolls are written as `XdY+Z`: roll `X` dice with `Y` sides each, sum
them, then add `Z`. Writing the die alone (`d20`) means a single die.
The modifier is optional and may be negative.

A single roll may use at most {{ mechanics.max_dice_per_roll }} dice,
with at most {{ mechanics.max_sides }} sides each. If you find yourself
needing more than that, you are solving the wrong problem.

## The standard die

Most checks use {{ mechanics.default_roll }}. Rolling
{{ mechanics.critical_success }} on that die is a critical success and
always succeeds regardless of modifiers or target number. Rolling
{{ mechanics.critical_failure }} is a critical failure and always
fails, however capable the character.

Only the standard die produces criticals. Damage rolls, healing rolls,
and other quantity rolls have no critical range at all — see
[[damage-and-healing]].
