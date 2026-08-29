# rig_builder.py — parametric "blockout" humanoid rigs and simple props,
# built on top of minigltf.py.
#
# Design choice: no skinning, no baked animation. Each limb is a small
# two-node chain instead — a zero-geometry "pivot" node positioned at
# the joint (shoulder/hip), whose child node holds the actual box mesh
# offset so it hangs/extends correctly from that pivot. That's enough
# to get correct-looking rotation for a walk/idle cycle animated
# client-side in Three.js (rotate the pivot node's .rotation each
# frame) without needing a rigged/skinned asset pipeline. Trade-off:
# no per-vertex deformation (no bending elbows/knees, no cloth/muscle
# jiggle) — fine for tabletop-scale proof-of-concept characters, not
# what you'd want for a hero shot.
#
# Because there's no skin, THREE.Object3D.clone() works normally for
# reusing one loaded character across many tokens — you do NOT need
# SkeletonUtils.clone() the way you would for a rigged Mixamo-style
# model. That's a real simplicity win for a prototype, at the cost of
# coarser animation.

import io
import math

from PIL import Image, ImageDraw

from minigltf import GLTFBuilder


def _identity_quat():
    return (0, 0, 0, 1)


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_checker_texture(size=256, cells=8, color_a=(235, 235, 235), color_b=(60, 60, 65)):
    """Simple procedural checker texture — used both as a generic UV/
    texture-mapping demo and as a stand-in ground texture."""
    img = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(img)
    cell = size // cells
    for j in range(cells):
        for i in range(cells):
            color = color_a if (i + j) % 2 == 0 else color_b
            draw.rectangle([i * cell, j * cell, (i + 1) * cell - 1, (j + 1) * cell - 1], fill=color)
    return img


def make_wood_crate_texture(size=256, base=(120, 78, 45), plank_line=(70, 42, 22), border=(40, 24, 12)):
    """Procedural crate texture: horizontal plank lines + a border frame
    + an X brace, so a single textured box actually reads as "crate"
    rather than "brown box" — cheap way to demo baseColorTexture."""
    img = Image.new("RGB", (size, size), base)
    draw = ImageDraw.Draw(img)
    planks = 4
    for p in range(1, planks):
        y = size * p // planks
        draw.line([(0, y), (size, y)], fill=plank_line, width=3)
    border_w = size // 16
    draw.rectangle([0, 0, size - 1, size - 1], outline=border, width=border_w)
    draw.line([(border_w, border_w), (size - border_w, size - border_w)], fill=border, width=border_w // 2)
    draw.line([(size - border_w, border_w), (border_w, size - border_w)], fill=border, width=border_w // 2)
    return img


def make_skin_texture(size=64, color=(210, 170, 140)):
    """Flat color as a texture (rather than a material baseColorFactor)
    only where we specifically want to demonstrate texture mapping on
    an organic-ish part; characters mostly use solid materials, which
    is the more common choice for stylized low-poly characters anyway."""
    return Image.new("RGB", (size, size), color)


class HumanoidRig:
    """Builds a named node hierarchy for a blocky humanoid into a shared
    GLTFBuilder. Returns the names of the pivot nodes worth animating so
    a caller (or the README's JS snippet) doesn't have to guess them."""

    def __init__(self, builder: GLTFBuilder, prefix: str, proportions: dict, colors: dict):
        self.b = builder
        self.prefix = prefix
        self.p = proportions
        self.c = colors
        self.pivot_names = {}
        self._materials = {}

    def _mat(self, key, color):
        if key not in self._materials:
            self._materials[key] = self.b.add_material(base_color=(*color, 1.0), roughness=0.75)
        return self._materials[key]

    def _limb(self, name, parent_node, pivot_translation, size, color_key, mesh_offset_sign=-1):
        """One pivot + one mesh child. mesh_offset_sign=-1 hangs the box
        below the pivot (arms/legs); +1 would extend it upward if ever
        needed (not used currently, kept for reuse/clarity)."""
        pivot_name = f"{self.prefix}_{name}Pivot"
        pivot = self.b.add_node(pivot_name, translation=pivot_translation, parent=parent_node)
        w, h, d = size
        mat = self._mat(color_key, self.c[color_key])
        mesh = self.b.add_box_mesh(size=size, material_index=mat)
        self.b.add_node(
            f"{self.prefix}_{name}Mesh",
            mesh=mesh,
            translation=(0, mesh_offset_sign * h / 2, 0),
            parent=pivot,
        )
        self.pivot_names[name] = pivot_name
        return pivot

    def build(self, root_translation=(0, 0, 0)):
        p, c = self.p, self.c
        root = self.b.add_node(f"{self.prefix}_Root", translation=root_translation)

        hips_y = p["leg_len"]
        hips = self.b.add_node(f"{self.prefix}_Hips", translation=(0, hips_y, 0), parent=root)
        self.pivot_names["Hips"] = f"{self.prefix}_Hips"

        # --- legs: hang below the hips ---
        leg_x = p["torso_w"] / 2 - p["leg_w"] / 2
        self._limb("LeftLeg", hips, (-leg_x, 0, 0), (p["leg_w"], p["leg_len"], p["leg_d"]), "pants")
        self._limb("RightLeg", hips, (leg_x, 0, 0), (p["leg_w"], p["leg_len"], p["leg_d"]), "pants")

        # --- torso: sits on top of hips ---
        torso_mat = self._mat("shirt", c["shirt"])
        torso_mesh = self.b.add_box_mesh(size=(p["torso_w"], p["torso_h"], p["torso_d"]), material_index=torso_mat)
        torso = self.b.add_node(
            f"{self.prefix}_Torso", mesh=torso_mesh,
            translation=(0, p["torso_h"] / 2 + p.get("torso_lean_z", 0) * 0, 0),
            rotation=_quat_from_x(p.get("torso_lean", 0.0)),
            parent=hips,
        )

        # --- head: on top of torso ---
        head_mat = self._mat("skin", c["skin"])
        head_mesh = self.b.add_box_mesh(size=(p["head_size"],) * 3, material_index=head_mat)
        head_y = p["torso_h"] + p["head_size"] / 2
        self.b.add_node(
            f"{self.prefix}_Head", mesh=head_mesh,
            translation=(0, head_y, p.get("head_forward", 0.0)),
            parent=torso,
        )
        self.pivot_names["Head"] = f"{self.prefix}_Head"  # not a true pivot (no separate joint), but nameable/animatable directly

        # --- arms: hang from shoulder height on the torso ---
        shoulder_y = p["torso_h"] - p["arm_w"] * 0.6
        arm_x = p["torso_w"] / 2 + p["arm_w"] / 2 * 0.7
        self._limb("LeftArm", torso, (-arm_x, shoulder_y, 0), (p["arm_w"], p["arm_len"], p["arm_d"]), "skin")
        self._limb("RightArm", torso, (arm_x, shoulder_y, 0), (p["arm_w"], p["arm_len"], p["arm_d"]), "skin")

        self.pivot_names["Root"] = f"{self.prefix}_Root"
        return root


def _quat_from_x(angle_rad):
    """Quaternion for a rotation about the X axis (used for a slight
    forward lean on hunched monster proportions)."""
    if angle_rad == 0.0:
        return _identity_quat()
    half = angle_rad / 2.0
    return (math.sin(half), 0.0, 0.0, math.cos(half))


# ---------------------------------------------------------------------
# Character presets — tweak these, not the rig code, to get variants.
# Units are arbitrary "meters"; roughly human-scale (~1.8 tall) for the
# hero, scaled down/up for monster variants. All feed the same rig.
# ---------------------------------------------------------------------
HERO_PROPORTIONS = dict(
    torso_w=0.42, torso_h=0.62, torso_d=0.24,
    head_size=0.30,
    arm_w=0.14, arm_len=0.60, arm_d=0.14,
    leg_w=0.17, leg_len=0.78, leg_d=0.17,
    torso_lean=0.0, head_forward=0.0,
)
HERO_COLORS = dict(shirt=(0.20, 0.45, 0.85), pants=(0.30, 0.25, 0.20), skin=(0.85, 0.68, 0.55))

GOBLIN_PROPORTIONS = dict(
    torso_w=0.34, torso_h=0.40, torso_d=0.20,
    head_size=0.28,
    arm_w=0.11, arm_len=0.42, arm_d=0.11,
    leg_w=0.13, leg_len=0.36, leg_d=0.13,
    torso_lean=0.35, head_forward=0.08,  # hunched forward
)
GOBLIN_COLORS = dict(shirt=(0.35, 0.28, 0.18), pants=(0.25, 0.20, 0.14), skin=(0.35, 0.55, 0.25))

OGRE_PROPORTIONS = dict(
    torso_w=0.72, torso_h=0.85, torso_d=0.46,
    head_size=0.34,
    arm_w=0.24, arm_len=0.80, arm_d=0.24,
    leg_w=0.28, leg_len=0.62, leg_d=0.28,
    torso_lean=0.12, head_forward=0.03,
)
OGRE_COLORS = dict(shirt=(0.42, 0.30, 0.22), pants=(0.30, 0.22, 0.16), skin=(0.55, 0.42, 0.32))


def build_character_glb(prefix, proportions, colors) -> GLTFBuilder:
    b = GLTFBuilder()
    rig = HumanoidRig(b, prefix, proportions, colors)
    rig.build()
    return b, rig


# ---------------------------------------------------------------------
# Simple static props — for the "scenery" and "texture mapping" asks.
# ---------------------------------------------------------------------
def build_crate_glb() -> GLTFBuilder:
    b = GLTFBuilder()
    tex_img = make_wood_crate_texture()
    image_idx = b.add_image_png(png_bytes(tex_img))
    tex_idx = b.add_texture(image_idx)
    mat = b.add_material(base_color=(1, 1, 1, 1), roughness=0.9, texture_index=tex_idx)
    mesh = b.add_box_mesh(size=(0.9, 0.9, 0.9), material_index=mat, uv_repeat=(1, 1))
    b.add_node("Crate_Root", mesh=mesh, translation=(0, 0.45, 0))
    return b


def build_rock_glb() -> GLTFBuilder:
    """A handful of overlapping, irregularly-scaled/rotated boxes reads
    as a rough boulder at a glance — no need for real noise-displaced
    geometry at this fidelity level."""
    b = GLTFBuilder()
    mat = b.add_material(base_color=(0.45, 0.44, 0.43, 1.0), roughness=1.0)
    root = b.add_node("Rock_Root", translation=(0, 0, 0))
    chunks = [
        # (size, translation, y-rotation radians)
        ((0.7, 0.5, 0.65), (0, 0.25, 0), 0.3),
        ((0.45, 0.35, 0.4), (0.22, 0.42, 0.05), -0.5),
        ((0.4, 0.3, 0.42), (-0.2, 0.4, -0.08), 0.9),
        ((0.3, 0.25, 0.3), (0.05, 0.55, 0.15), 1.3),
    ]
    for i, (size, translation, yrot) in enumerate(chunks):
        mesh = b.add_box_mesh(size=size, material_index=mat)
        half = yrot / 2.0
        rotation = (0, math.sin(half), 0, math.cos(half))
        b.add_node(f"Rock_Chunk{i}", mesh=mesh, translation=translation, rotation=rotation, parent=root)
    return b
