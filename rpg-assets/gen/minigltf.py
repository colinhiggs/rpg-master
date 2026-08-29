# minigltf.py — a minimal, dependency-free glTF 2.0 (binary .glb) writer.
#
# This exists because the sandbox this was built in has no network access
# to install a real 3D library (trimesh, pygltflib, etc.), and no Blender/
# DCC tool available. It implements just enough of the glTF 2.0 spec to
# emit valid, GLTFLoader-compatible files: a node hierarchy with local
# transforms, box-primitive meshes, PBR materials (solid color or a
# baseColorTexture), and embedded PNG textures. No skinning, no baked
# animation — see rig_builder.py for how procedural animation is done
# instead, by naming pivot nodes and rotating them client-side.
#
# If you later get a proper toolchain (Blender + a glTF exporter, or a
# purchased asset pack), you don't need this file at all — just point
# the client's GLTFLoader at those files instead. This module's only
# job is to get real, valid .glb files into your hands without one.

import json
import struct

import numpy as np

# glTF accessor componentType constants
FLOAT = 5126
UNSIGNED_SHORT = 5123
UNSIGNED_INT = 5125

ARRAY_BUFFER = 34962          # vertex data
ELEMENT_ARRAY_BUFFER = 34963  # index data

GLB_MAGIC = 0x46546C67
GLB_VERSION = 2
CHUNK_TYPE_JSON = 0x4E4F534A
CHUNK_TYPE_BIN = 0x004E4942


class GLTFBuilder:
    def __init__(self):
        self.buffer = bytearray()
        self.bufferViews = []
        self.accessors = []
        self.meshes = []
        self.materials = []
        self.nodes = []
        self.images = []
        self.textures = []
        self.samplers = []
        self.root_node_indices = []
        self._name_to_node = {}

    # -- low-level buffer packing -------------------------------------
    def _pad4(self):
        while len(self.buffer) % 4 != 0:
            self.buffer.append(0)

    def _add_buffer_view(self, raw: bytes, target=None):
        self._pad4()
        offset = len(self.buffer)
        self.buffer.extend(raw)
        bv = {"buffer": 0, "byteOffset": offset, "byteLength": len(raw)}
        if target is not None:
            bv["target"] = target
        self.bufferViews.append(bv)
        return len(self.bufferViews) - 1

    def _add_accessor(self, arr: np.ndarray, component_type, gl_type, target=None):
        bv = self._add_buffer_view(arr.tobytes(), target=target)
        flat = arr.reshape(arr.shape[0], -1) if arr.ndim > 1 else arr.reshape(-1, 1)
        acc = {
            "bufferView": bv,
            "componentType": component_type,
            "count": int(arr.shape[0]),
            "type": gl_type,
            "min": flat.min(axis=0).tolist(),
            "max": flat.max(axis=0).tolist(),
        }
        if gl_type == "SCALAR":
            acc["min"] = [int(flat.min())]
            acc["max"] = [int(flat.max())]
        self.accessors.append(acc)
        return len(self.accessors) - 1

    # -- images / textures / materials ---------------------------------
    def add_image_png(self, png_bytes: bytes) -> int:
        bv = self._add_buffer_view(png_bytes)
        self.images.append({"bufferView": bv, "mimeType": "image/png"})
        return len(self.images) - 1

    def add_texture(self, image_index: int) -> int:
        if not self.samplers:
            self.samplers.append({"magFilter": 9728, "minFilter": 9986, "wrapS": 10497, "wrapT": 10497})
        self.textures.append({"source": image_index, "sampler": 0})
        return len(self.textures) - 1

    def add_material(self, base_color=(1, 1, 1, 1), roughness=0.8, metallic=0.0,
                      texture_index=None, double_sided=False) -> int:
        mat = {
            "pbrMetallicRoughness": {
                "baseColorFactor": list(base_color),
                "roughnessFactor": roughness,
                "metallicFactor": metallic,
            },
            "doubleSided": double_sided,
        }
        if texture_index is not None:
            mat["pbrMetallicRoughness"]["baseColorTexture"] = {"index": texture_index}
        self.materials.append(mat)
        return len(self.materials) - 1

    # -- geometry --------------------------------------------------------
    def add_box_mesh(self, size=(1.0, 1.0, 1.0), material_index=0, uv_repeat=(1.0, 1.0)) -> int:
        """A unit-ish box (24 verts, flat-shaded — 4 verts per face so
        normals aren't averaged across edges), centered on the origin,
        scaled by `size`. Includes UVs so it's texturable even though
        most parts here just use a solid-color material."""
        sx, sy, sz = (s / 2.0 for s in size)
        # 6 faces * 4 verts, positions / normals / uvs parallel arrays
        faces = [
            # (normal, 4 corner offsets in CCW winding when viewed from outside)
            ((0, 0, 1),  [(-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz)]),   # +Z front
            ((0, 0, -1), [(sx, -sy, -sz), (-sx, -sy, -sz), (-sx, sy, -sz), (sx, sy, -sz)]),  # -Z back
            ((1, 0, 0),  [(sx, -sy, sz), (sx, -sy, -sz), (sx, sy, -sz), (sx, sy, sz)]),   # +X right
            ((-1, 0, 0), [(-sx, -sy, -sz), (-sx, -sy, sz), (-sx, sy, sz), (-sx, sy, -sz)]),  # -X left
            ((0, 1, 0),  [(-sx, sy, sz), (sx, sy, sz), (sx, sy, -sz), (-sx, sy, -sz)]),   # +Y top
            ((0, -1, 0), [(-sx, -sy, -sz), (sx, -sy, -sz), (sx, -sy, sz), (-sx, -sy, sz)]),  # -Y bottom
        ]
        positions, normals, uvs, indices = [], [], [], []
        u_rep, v_rep = uv_repeat
        for normal, corners in faces:
            base = len(positions)
            for i, c in enumerate(corners):
                positions.append(c)
                normals.append(normal)
            uvs += [(0, v_rep), (u_rep, v_rep), (u_rep, 0), (0, 0)]
            indices += [base, base + 1, base + 2, base, base + 2, base + 3]

        pos_arr = np.array(positions, dtype=np.float32)
        norm_arr = np.array(normals, dtype=np.float32)
        uv_arr = np.array(uvs, dtype=np.float32)
        idx_arr = np.array(indices, dtype=np.uint16)

        pos_acc = self._add_accessor(pos_arr, FLOAT, "VEC3", target=ARRAY_BUFFER)
        norm_acc = self._add_accessor(norm_arr, FLOAT, "VEC3", target=ARRAY_BUFFER)
        uv_acc = self._add_accessor(uv_arr, FLOAT, "VEC2", target=ARRAY_BUFFER)
        idx_acc = self._add_accessor(idx_arr, UNSIGNED_SHORT, "SCALAR", target=ELEMENT_ARRAY_BUFFER)

        mesh = {
            "primitives": [{
                "attributes": {"POSITION": pos_acc, "NORMAL": norm_acc, "TEXCOORD_0": uv_acc},
                "indices": idx_acc,
                "material": material_index,
            }]
        }
        self.meshes.append(mesh)
        return len(self.meshes) - 1

    # -- node hierarchy ----------------------------------------------
    def add_node(self, name, mesh=None, translation=(0, 0, 0), rotation=(0, 0, 0, 1),
                 scale=(1, 1, 1), children=None, parent=None) -> int:
        node = {"name": name}
        if mesh is not None:
            node["mesh"] = mesh
        if translation != (0, 0, 0):
            node["translation"] = list(translation)
        if rotation != (0, 0, 0, 1):
            node["rotation"] = list(rotation)
        if scale != (1, 1, 1):
            node["scale"] = list(scale)
        if children:
            node["children"] = list(children)
        self.nodes.append(node)
        idx = len(self.nodes) - 1
        self._name_to_node[name] = idx
        if parent is not None:
            self.nodes[parent].setdefault("children", []).append(idx)
        else:
            self.root_node_indices.append(idx)
        return idx

    def node_index(self, name):
        return self._name_to_node[name]

    # -- serialize --------------------------------------------------
    def to_glb_bytes(self) -> bytes:
        gltf = {
            "asset": {"version": "2.0", "generator": "minigltf.py (procedural placeholder assets)"},
            "scene": 0,
            "scenes": [{"nodes": self.root_node_indices}],
            "nodes": self.nodes,
            "meshes": self.meshes,
            "materials": self.materials,
            "accessors": self.accessors,
            "bufferViews": self.bufferViews,
            "buffers": [{"byteLength": len(self.buffer)}],
        }
        if self.images:
            gltf["images"] = self.images
        if self.textures:
            gltf["textures"] = self.textures
        if self.samplers:
            gltf["samplers"] = self.samplers

        json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
        while len(json_bytes) % 4 != 0:
            json_bytes += b" "  # glTF spec: pad JSON chunk with spaces

        bin_bytes = bytes(self.buffer)
        while len(bin_bytes) % 4 != 0:
            bin_bytes += b"\x00"  # pad BIN chunk with zeros

        json_chunk = struct.pack("<II", len(json_bytes), CHUNK_TYPE_JSON) + json_bytes
        bin_chunk = struct.pack("<II", len(bin_bytes), CHUNK_TYPE_BIN) + bin_bytes
        total_len = 12 + len(json_chunk) + len(bin_chunk)
        header = struct.pack("<III", GLB_MAGIC, GLB_VERSION, total_len)
        return header + json_chunk + bin_chunk

    def save(self, path):
        data = self.to_glb_bytes()
        with open(path, "wb") as f:
            f.write(data)
        return len(data)
