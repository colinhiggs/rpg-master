# Placeholder asset pack (embedded copy)

The `.glb`/`.png` files in `models/` and `textures/` here are the same
placeholder character/prop pack described in full in the
[`../../rpg-assets/`](../../rpg-assets/) project, which sits alongside
this client (procedurally generated — see that project's README and
`gen/` scripts for exactly how, and for a live `viewer.html` that
demonstrates them outside this game client).

**Set expectations correctly:** flat-shaded boxes arranged into a
humanoid silhouette — "greybox" quality, for validating the pipeline
(load → texture → light → animate), not a finished look.

## What's here

- `models/hero.glb` — the player character shape (everyone gets this
  one for now — see the client section of `../../TODO.md`)
- `models/goblin.glb`, `models/ogre.glb` — the two monster shapes the
  DM can currently spawn
- `models/crate.glb`, `models/rock.glb` — simple props (not currently
  placed by the game client, but loadable the same way if you want
  static scenery — see "Adding scenery" below)
- `textures/ground_checker.png` — tiles across the battle-map floor

## Animatable node names

Every character (`Hero_*`/`Goblin_*`/`Ogre_*`) has the same relative
node names, which is how `index.html` finds them regardless of which
kind a token is:

| Suffix | Used for |
|---|---|
| `_LeftLegPivot` / `_RightLegPivot` | Walk-cycle leg swing |
| `_LeftArmPivot` / `_RightArmPivot` | Walk-cycle arm swing |
| `_Head` | Idle head turn |

There's no baked animation in the files — `index.html`'s render loop
rotates these nodes directly with a sine wave, switching between a
walk cycle and an idle sway based on whether the token's rendered
position still differs from its server-reported grid position. See
the main README's "3D models and animation" section.

## Adding scenery (crate/rock aren't wired in yet)

The two props exist in the pack but nothing in `index.html` places
them — the DM tools only spawn characters right now. To add static
scenery, the shape is: load `crate.glb`/`rock.glb` once alongside the
character models, then `clone()` and position instances directly in
the scene (no server round-trip needed unless you want players to see
the *same* scenery layout — in which case it belongs in server state
like tokens do, not just placed client-side).

## Swapping in real assets later

Nothing in `index.html` cares that these are procedurally generated —
it just calls `GLTFLoader.load()` on a path and clones the result. A
real pack (Mixamo characters, or a free CC0 pack from Kenney.nl) drops
in by replacing the files here and updating `MODEL_URLS` in
`index.html`. The one thing that changes: a properly rigged/skinned
pack needs `THREE.SkeletonUtils.clone()` instead of the plain
`.clone(true)` used now, and the walk/idle animation would move from
"rotate named pivot nodes" to `THREE.AnimationMixer` playing that
pack's actual animation clips — a bigger change than swapping files,
worth budgeting real time for.
