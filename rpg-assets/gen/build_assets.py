# build_assets.py — generates the actual .glb / .png files.
import os

from rig_builder import (
    HERO_PROPORTIONS, HERO_COLORS,
    GOBLIN_PROPORTIONS, GOBLIN_COLORS,
    OGRE_PROPORTIONS, OGRE_COLORS,
    build_character_glb, build_crate_glb, build_rock_glb,
    make_checker_texture, png_bytes,
)

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "out")
os.makedirs(OUT_DIR, exist_ok=True)


def main():
    results = {}

    for name, prefix, proportions, colors in [
        ("hero.glb", "Hero", HERO_PROPORTIONS, HERO_COLORS),
        ("goblin.glb", "Goblin", GOBLIN_PROPORTIONS, GOBLIN_COLORS),
        ("ogre.glb", "Ogre", OGRE_PROPORTIONS, OGRE_COLORS),
    ]:
        builder, rig = build_character_glb(prefix, proportions, colors)
        path = os.path.join(OUT_DIR, name)
        size = builder.save(path)
        results[name] = {"path": path, "size": size, "pivots": rig.pivot_names}
        print(f"{name}: {size} bytes, {len(builder.nodes)} nodes, {len(builder.meshes)} meshes")
        print(f"  animatable nodes: {list(rig.pivot_names.keys())}")

    crate = build_crate_glb()
    path = os.path.join(OUT_DIR, "crate.glb")
    size = crate.save(path)
    results["crate.glb"] = {"path": path, "size": size}
    print(f"crate.glb: {size} bytes (textured)")

    rock = build_rock_glb()
    path = os.path.join(OUT_DIR, "rock.glb")
    size = rock.save(path)
    results["rock.glb"] = {"path": path, "size": size}
    print(f"rock.glb: {size} bytes")

    # standalone ground texture, not embedded in any model — useful for
    # texturing the existing battle-map floor plane directly
    checker = make_checker_texture(size=512, cells=8, color_a=(90, 90, 96), color_b=(58, 58, 64))
    tex_path = os.path.join(OUT_DIR, "ground_checker.png")
    with open(tex_path, "wb") as f:
        f.write(png_bytes(checker))
    print(f"ground_checker.png: {os.path.getsize(tex_path)} bytes")

    return results


if __name__ == "__main__":
    main()
