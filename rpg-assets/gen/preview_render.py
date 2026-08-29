# preview_render.py — crude but honest 3D preview of a .glb, rendered
# with matplotlib since there's no Three.js/browser available here to
# actually load and view the file. This walks the SAME node hierarchy
# a real glTF loader would, applying each node's local TRS to get
# world-space triangles, so what you see here is a fair proxy for what
# Three.js will show (minus real lighting/materials/textures).

import json
import struct

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from glb_read import read_glb, COMPONENT_DTYPES, TYPE_SIZES


def _read_accessor(gltf, bin_data, acc_idx):
    acc = gltf["accessors"][acc_idx]
    bv = gltf["bufferViews"][acc["bufferView"]]
    dtype = COMPONENT_DTYPES[acc["componentType"]]
    n = TYPE_SIZES[acc["type"]]
    offset = bv["byteOffset"]
    count = acc["count"]
    raw = bin_data[offset: offset + count * n * np.dtype(dtype).itemsize]
    arr = np.frombuffer(raw, dtype=dtype).reshape(count, n) if n > 1 else np.frombuffer(raw, dtype=dtype)
    return arr


def _quat_to_matrix(q):
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def _node_local_matrix(node):
    t = np.array(node.get("translation", [0, 0, 0]), dtype=np.float64)
    q = node.get("rotation", [0, 0, 0, 1])
    s = np.array(node.get("scale", [1, 1, 1]), dtype=np.float64)
    R = _quat_to_matrix(q)
    M = np.eye(4)
    M[:3, :3] = R * s  # scale then rotate (columns scaled)
    M[:3, 3] = t
    return M


def collect_world_triangles(path):
    gltf, bin_data = read_glb(path)
    nodes = gltf["nodes"]
    materials = gltf.get("materials", [])

    def material_color(mat_idx):
        if mat_idx is None or mat_idx >= len(materials):
            return (0.6, 0.6, 0.6)
        pbr = materials[mat_idx].get("pbrMetallicRoughness", {})
        if "baseColorTexture" in pbr:
            return (0.75, 0.65, 0.5)  # textured — approximate with a neutral tan for preview
        c = pbr.get("baseColorFactor", [0.6, 0.6, 0.6, 1])
        return tuple(c[:3])

    triangles = []  # (verts(3,3) world space, color)

    def walk(idx, parent_matrix):
        node = nodes[idx]
        world = parent_matrix @ _node_local_matrix(node)
        if "mesh" in node:
            mesh = gltf["meshes"][node["mesh"]]
            for prim in mesh["primitives"]:
                pos = _read_accessor(gltf, bin_data, prim["attributes"]["POSITION"]).astype(np.float64)
                idx_arr = _read_accessor(gltf, bin_data, prim["indices"])
                color = material_color(prim.get("material"))
                pos_h = np.hstack([pos, np.ones((pos.shape[0], 1))])
                world_pos = (world @ pos_h.T).T[:, :3]
                for i in range(0, len(idx_arr), 3):
                    a, b, c_ = idx_arr[i], idx_arr[i + 1], idx_arr[i + 2]
                    triangles.append((world_pos[[a, b, c_]], color))
        for child in node.get("children", []):
            walk(child, world)

    for root in gltf["scenes"][gltf["scene"]]["nodes"]:
        walk(root, np.eye(4))

    return triangles


def render_preview(path, out_png, title=None, elev=18, azim=35):
    triangles = collect_world_triangles(path)
    fig = plt.figure(figsize=(4, 5))
    ax = fig.add_subplot(111, projection="3d")

    light_dir = np.array([0.4, 0.8, 0.6])
    light_dir = light_dir / np.linalg.norm(light_dir)

    polys, colors = [], []
    all_pts = []
    for verts, base_color in triangles:
        v0, v1, v2 = verts
        normal = np.cross(v1 - v0, v2 - v0)
        norm_len = np.linalg.norm(normal)
        if norm_len > 1e-9:
            normal = normal / norm_len
        shade = 0.4 + 0.6 * max(0.0, float(np.dot(normal, light_dir)))
        shaded = tuple(min(1.0, c * shade) for c in base_color)
        # matplotlib uses (x, z, y) swap here so "up" (glTF +Y) renders as up on screen
        polys.append([(p[0], p[2], p[1]) for p in verts])
        colors.append(shaded)
        all_pts.append(verts)

    coll = Poly3DCollection(polys, facecolor=colors, edgecolor=(0, 0, 0, 0.15), linewidths=0.3)
    ax.add_collection3d(coll)

    all_pts = np.concatenate(all_pts, axis=0)
    center = (all_pts.max(axis=0) + all_pts.min(axis=0)) / 2
    radius = max((all_pts.max(axis=0) - all_pts.min(axis=0)).max() / 2, 0.05) * 1.15
    ax.set_xlim(center[0] - radius, center[0] + radius)
    ax.set_ylim(center[2] - radius, center[2] + radius)
    ax.set_zlim(max(0, center[1] - radius), center[1] + radius)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    if title:
        ax.set_title(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150, transparent=True)
    plt.close(fig)


if __name__ == "__main__":
    import os
    out_dir = "../out"
    preview_dir = "../previews"
    os.makedirs(preview_dir, exist_ok=True)
    jobs = [
        ("hero.glb", "Hero"),
        ("goblin.glb", "Goblin"),
        ("ogre.glb", "Ogre"),
        ("crate.glb", "Crate (textured)"),
        ("rock.glb", "Rock"),
    ]
    for fname, title in jobs:
        src = os.path.join(out_dir, fname)
        dst = os.path.join(preview_dir, fname.replace(".glb", ".png"))
        render_preview(src, dst, title=title)
        print(f"rendered {dst}")
