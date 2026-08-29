# Placeholder Asset Pack — proof of concept

Procedurally generated, real, loadable `.glb` files: three character
rigs (hero, goblin, ogre — same builder, different proportions/colors)
and two props (a textured crate, a rock), plus a standalone ground
texture. Built because there's no network access or DCC tool (Blender
etc.) available in the environment this was made in — see `gen/` for
exactly how, in case you want to generate more variants yourself.

**Set expectations correctly:** these are flat-shaded boxes arranged
into a humanoid silhouette — "greybox" quality, not sculpted game art.
That's the right fidelity for proof-of-concept work (validate the
pipeline — loading, texturing, lighting, animating — before spending
money or real modeling time), not a finished look. See "Next step:
real assets" below for how to upgrade without touching client code.

## What's in `out/`

| File | What it demonstrates |
|---|---|
| `hero.glb` | Character rig: torso/head/arms/legs as named, animatable nodes |
| `goblin.glb` | Same rig, different proportions (hunched, smaller) — variant reuse |
| `ogre.glb` | Same rig, bulkier proportions — variant reuse |
| `crate.glb` | Texture mapping — a procedural wood-plank PNG baked into the material |
| `rock.glb` | Simple irregular scenery prop (a cluster of rotated boxes) |
| `ground_checker.png` | Standalone tileable texture, for texturing the battle-map floor directly |

## View them

```bash
cd rpg-assets
python3 -m http.server 8080
```
Open `http://localhost:8080/viewer.html`. It loads all five models,
arranges them on a lit, textured ground plane, and animates the three
characters (idle bob + walking limb-swing) — this is the actual answer
to "can Three.js coordinate scenery + models + textures + lighting +
animation," rendered live rather than described.

You have to serve it over HTTP, not open the file directly — opening
`viewer.html` as a `file://` URL blocks `GLTFLoader`'s fetch of the
`.glb` files in every major browser (CORS applies to local files too).

## How the animation works (read this before extending it)

There's no baked skeletal animation in these files — no armature, no
`AnimationClip`. Each limb is a two-node chain: an empty "pivot" node
positioned at the joint (shoulder/hip) with a mesh-holding child offset
to hang correctly from it. `viewer.html` finds these by name
(`*_LeftArmPivot`, `*_Hips`, etc. — see the table below) and rotates
them directly, every frame, with a sine wave. That's the whole "basic
animation" story: cheap, good enough to read as walking/idling at
tabletop scale, but it can't bend a joint mid-limb or do anything an
authored animation clip could (no run cycle with real weight shift, no
attack windup, etc.).

**Practical upside of this choice:** because there's no skin/armature,
`model.clone(true)` in Three.js just works for reusing one loaded
character across many tokens. A properly rigged, skinned character
(the kind you'd get from Mixamo) needs `SkeletonUtils.clone()` instead
— a real asset pack trades this simplicity for actual animation
quality, which is the right trade once you're past proof-of-concept.

Animatable node names on every character (prefix varies: `Hero_`,
`Goblin_`, `Ogre_`):

| Suffix | What rotating it does |
|---|---|
| `_Hips` | Whole-body pivot; `viewer.html` uses the group's Y position instead, for the idle bob |
| `_LeftLegPivot` / `_RightLegPivot` | Leg swing |
| `_LeftArmPivot` / `_RightArmPivot` | Arm swing |
| `_Head` | Head turn/tilt (not a true separate joint, but a nameable node — rotating it works fine) |

## Integrating with the existing multiplayer client

The battle-map client from earlier (`rpg-prototype-python/public/index.html`)
currently draws tokens as colored cylinders in `tokenMesh()`. Swapping
in these models means:

1. Load `hero.glb`/`goblin.glb`/`ogre.glb` once at startup with
   `GLTFLoader` (like `viewer.html` does), cache the returned
   `THREE.Group` per type.
2. In `syncScene()`, where it currently calls `tokenMesh(token.color)`
   for a new token, `clone(true)` the matching cached model instead —
   you'd need a `type` (or `monsterKind`) field on the server's token
   objects to pick which model, which isn't there yet (tokens only
   have a `color` today).
3. Keep an `animated` list like `viewer.html`'s, and drive idle/walk
   poses based on whether a token's grid position changed since the
   last frame (walking) or not (idle) — the server already broadcasts
   `x`/`y` on every move, so the client can diff position between
   `state` events to decide which pose to play.

I didn't wire this into the actual server/client yet — didn't want to
guess at how you want token "type" represented in `data.py`'s schema
before you'd seen whether these models were even the right direction.
Happy to do that integration next if this look is a fit.

## Next step: real assets

Nothing about the client code changes if you replace these with
real assets later — same `GLTFLoader.load()` call, same "find named
nodes and animate them" approach if the replacement also skips
skinning, or `AnimationMixer` + `SkeletonUtils.clone()` if you upgrade
to a properly rigged/skinned pack (e.g. Mixamo characters, or a
purchased low-poly RPG pack from itch.io/Sketchfab/Kenney.nl — Kenney's
packs in particular are free, CC0, and already sized appropriately for
exactly this kind of prototype). The node-hierarchy/pivot convention
these files use (`*_LeftArmPivot` etc.) is just a naming choice for
this placeholder pack, not a Three.js requirement — a real asset pack
will have its own (better) rig, and the client code that finds/animates
nodes would need to match whatever that pack actually calls things.

## Regenerating / making variants

Everything is in `gen/`:
- `minigltf.py` — the from-scratch `.glb` writer (no external 3D libs)
- `rig_builder.py` — the parametric humanoid builder + prop builders;
  tweak `HERO_PROPORTIONS`/`_COLORS` (and the goblin/ogre equivalents)
  or add new preset dicts for more variants
- `build_assets.py` — run this after changing presets to regenerate
  everything in `out/`
- `glb_read.py` — independent structural validator (re-parses the raw
  bytes rather than trusting the writer) — run after any change to
  `minigltf.py` itself
- `preview_render.py` — matplotlib preview renderer, for sanity-checking
  proportions without a browser

```bash
cd gen
python3 build_assets.py
python3 -c "from glb_read import validate; import os; [validate(f'../out/{f}') for f in os.listdir('../out') if f.endswith('.glb')]"
python3 preview_render.py   # writes PNGs to ../previews/
```
