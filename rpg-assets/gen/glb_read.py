# glb_read.py — an independent GLB reader/validator + a crude matplotlib
# preview renderer, used to sanity-check the generated assets without
# needing Three.js/a browser available in this environment.
#
# "Independent" matters here: this doesn't import minigltf.py's writer
# logic, it re-parses the raw bytes per the glTF/GLB spec from scratch,
# so a bug in the writer isn't invisible to its own reader.

import json
import struct

import numpy as np

COMPONENT_DTYPES = {
    5120: np.int8, 5121: np.uint8, 5122: np.int16,
    5123: np.uint16, 5125: np.uint32, 5126: np.float32,
}
TYPE_SIZES = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_glb(path):
    with open(path, "rb") as f:
        data = f.read()

    magic, version, length = struct.unpack_from("<III", data, 0)
    assert magic == 0x46546C67, f"bad magic: {magic:#x}"
    assert version == 2, f"unexpected version: {version}"
    assert length == len(data), f"length mismatch: header says {length}, file is {len(data)}"

    offset = 12
    json_chunk = None
    bin_chunk = None
    while offset < length:
        chunk_len, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk_data = data[offset:offset + chunk_len]
        offset += chunk_len
        if chunk_type == 0x4E4F534A:
            json_chunk = chunk_data
        elif chunk_type == 0x004E4942:
            bin_chunk = chunk_data
        else:
            raise AssertionError(f"unknown chunk type {chunk_type:#x}")

    assert json_chunk is not None, "no JSON chunk found"
    gltf = json.loads(json_chunk.decode("utf-8"))
    return gltf, bin_chunk


def validate(path, verbose=True):
    gltf, bin_data = read_glb(path)
    errors = []

    buf_len = gltf["buffers"][0]["byteLength"]
    if bin_data is None:
        errors.append("no BIN chunk but buffers[0] expects one")
    elif len(bin_data) < buf_len:
        errors.append(f"BIN chunk too short: have {len(bin_data)}, need >= {buf_len}")

    for i, bv in enumerate(gltf.get("bufferViews", [])):
        end = bv["byteOffset"] + bv["byteLength"]
        if bin_data is not None and end > len(bin_data):
            errors.append(f"bufferView {i} out of range: end={end}, buffer len={len(bin_data)}")

    for i, acc in enumerate(gltf.get("accessors", [])):
        bv_idx = acc["bufferView"]
        if bv_idx >= len(gltf["bufferViews"]):
            errors.append(f"accessor {i} references missing bufferView {bv_idx}")
            continue
        bv = gltf["bufferViews"][bv_idx]
        dtype = COMPONENT_DTYPES[acc["componentType"]]
        n_components = TYPE_SIZES[acc["type"]]
        expected_bytes = acc["count"] * n_components * np.dtype(dtype).itemsize
        if expected_bytes > bv["byteLength"]:
            errors.append(
                f"accessor {i} ({acc['type']}, count={acc['count']}) needs "
                f"{expected_bytes}B but bufferView {bv_idx} only has {bv['byteLength']}B"
            )

    node_count = len(gltf.get("nodes", []))
    for i, mesh in enumerate(gltf.get("meshes", [])):
        for prim in mesh["primitives"]:
            if "indices" in prim and prim["indices"] >= len(gltf["accessors"]):
                errors.append(f"mesh {i} indices accessor out of range")
            for attr, acc_idx in prim["attributes"].items():
                if acc_idx >= len(gltf["accessors"]):
                    errors.append(f"mesh {i} attribute {attr} accessor out of range")

    for i, node in enumerate(gltf.get("nodes", [])):
        for child in node.get("children", []):
            if child >= node_count:
                errors.append(f"node {i} ('{node.get('name')}') has out-of-range child {child}")
        if "mesh" in node and node["mesh"] >= len(gltf.get("meshes", [])):
            errors.append(f"node {i} references out-of-range mesh {node['mesh']}")

    scene_nodes = gltf["scenes"][gltf["scene"]]["nodes"]
    reachable = set()

    def walk(idx):
        if idx in reachable:
            return
        reachable.add(idx)
        for c in gltf["nodes"][idx].get("children", []):
            walk(c)

    for n in scene_nodes:
        walk(n)
    orphans = set(range(node_count)) - reachable
    if orphans:
        errors.append(f"{len(orphans)} node(s) not reachable from scene root: {sorted(orphans)}")

    if verbose:
        tris = sum(
            gltf["accessors"][mesh["primitives"][0]["indices"]]["count"] // 3
            for mesh in gltf.get("meshes", [])
        )
        print(
            f"{path}: {node_count} nodes, {len(gltf.get('meshes', []))} meshes, "
            f"{len(gltf.get('materials', []))} materials, {tris} total triangles, "
            f"{len(gltf.get('images', []))} embedded image(s)"
        )
        names = [n.get("name") for n in gltf["nodes"] if n.get("name")]
        print(f"  node names: {names}")
        if errors:
            print("  ERRORS:")
            for e in errors:
                print(f"    - {e}")
        else:
            print("  OK — structurally valid")

    return errors
