"""Read a VRM/GLB without changing it."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def read_glb(path):
    blob = Path(path).read_bytes()
    if len(blob) < 20:
        raise ValueError("Truncated GLB header")
    magic, version, size = struct.unpack_from("<4sII", blob)
    if magic != b"glTF" or version != 2 or size != len(blob):
        raise ValueError("Expected a valid glTF 2 binary")
    offset = 12
    document = None
    binary = b""
    while offset < len(blob):
        if len(blob) - offset < 8:
            raise ValueError("Truncated GLB chunk header")
        size, kind = struct.unpack_from("<II", blob, offset)
        offset += 8
        chunk = blob[offset:offset + size]
        if len(chunk) != size:
            raise ValueError("Truncated GLB chunk")
        if kind == 0x4E4F534A:
            document = json.loads(chunk)
        elif kind == 0x004E4942:
            binary = chunk
        offset += size
    if document is None:
        raise ValueError("Missing GLB JSON")
    return document, binary


def write_glb(path, document, binary):
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf8")
    payload += b" " * (-len(payload) % 4)
    binary += b"\0" * (-len(binary) % 4)
    chunks = struct.pack("<II", len(payload), 0x4E4F534A) + payload
    if binary:
        chunks += struct.pack("<II", len(binary), 0x004E4942) + binary
    Path(path).write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(chunks)) + chunks)


def primitive_triangles(document, primitive):
    count = document["accessors"][primitive.get("indices", primitive["attributes"]["POSITION"])]["count"]
    mode = primitive.get("mode", 4)
    if mode == 4:
        return count // 3
    if mode in (5, 6):
        return max(count - 2, 0)
    raise ValueError(f"VRM mesh uses non-triangle primitive mode {mode}")


def humanoid_map(document):
    extensions = document.get("extensions", {})
    if "VRMC_vrm" in extensions:
        return {key: item["node"] for key, item in
                extensions["VRMC_vrm"]["humanoid"]["humanBones"].items()}
    if "VRM" in extensions:
        result = {item["bone"]: item["node"] for item in extensions["VRM"]["humanoid"]["humanBones"]}
        for side in ("left", "right"):
            proximal, intermediate = side + "ThumbProximal", side + "ThumbIntermediate"
            if proximal in result:
                result[side + "ThumbMetacarpal"] = result.pop(proximal)
            if intermediate in result:
                result[proximal] = result.pop(intermediate)
        return result
    raise ValueError("VRM humanoid metadata is required")


def inspect(path):
    document, _ = read_glb(path)
    human_bones = humanoid_map(document)
    required = ("hips", "spine", "head", "leftUpperArm", "rightUpperArm", "leftLowerArm", "rightLowerArm",
                "leftHand", "rightHand", "leftUpperLeg", "rightUpperLeg", "leftLowerLeg", "rightLowerLeg", "leftFoot", "rightFoot")
    missing = set(required) - set(human_bones)
    if missing:
        raise ValueError("Required humanoid bones missing: " + ", ".join(sorted(missing)))
    for resource in document.get("buffers", []) + document.get("images", []):
        if "uri" in resource and not resource["uri"].startswith("data:"):
            raise ValueError("VRM must embed its textures and buffers; external resources are unsupported")
    scene = document.get("scenes", [{}])[document.get("scene", 0)]
    active = set()

    def visit(index):
        if index in active:
            return
        active.add(index)
        for child in document["nodes"][index].get("children", []):
            visit(child)

    for index in scene.get("nodes", range(len(document["nodes"]))):
        visit(index)
    total_triangles = sum(primitive_triangles(document, primitive) for index in active
                          if "mesh" in document["nodes"][index]
                          for primitive in document["meshes"][document["nodes"][index]["mesh"]]["primitives"])
    return {
        "source": str(Path(path).resolve()),
        "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        "generator": document.get("asset", {}).get("generator"),
        "total_triangles": total_triangles,
        "humanoid": {key: document["nodes"][index].get("name", str(index))
                     for key, index in humanoid_map(document).items()},
        "meshes": [{"name": mesh.get("name"),
                    "vertices": sum(document["accessors"][prim["attributes"]["POSITION"]]["count"]
                                    for prim in mesh["primitives"]),
                    "triangles": sum(primitive_triangles(document, prim) for prim in mesh["primitives"]),
                    "morphs": max(len(prim.get("targets", [])) for prim in mesh["primitives"])}
                   for mesh in document.get("meshes", [])],
        "materials": document.get("materials", []),
        "vrm_meta": document.get("extensions", {}).get("VRMC_vrm", {}).get("meta", {})
                    or document.get("extensions", {}).get("VRM", {}).get("meta", {}),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.dumps(inspect(args.source), ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report)
