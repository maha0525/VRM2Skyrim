"""VRM facial expressions -> Skyrim SE HeadPart (BSDynamicTriShape + .tri + FaceGeom)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
import sys
import numpy as np

LOG = logging.getLogger("converter")

ROOT = Path(__file__).resolve().parent

# Standard Skyrim SE expression/phoneme/blink morph names (verified against femalehead.tri
# and PyNifly's skyrimDict.expression_filter).
SKYRIM_EXPRESSION_MORPHS = (
    "Aah", "BigAah", "I", "Eee", "Eh", "Oh", "OohQ", "W", "BMP",
    "FV", "ChJSh", "DST", "K", "N", "R", "Th",
    "BlinkLeft", "BlinkRight", "SquintLeft", "SquintRight",
    "MoodHappy", "DialogueHappy",
    "MoodAnger", "DialogueAnger", "CombatAnger", "CombatShout",
    "MoodSad", "DialogueSad",
    "MoodSurprise", "DialogueSurprise",
    "MoodFear", "DialogueFear",
    "MoodDisgusted", "DialogueDisgusted",
    "MoodPuzzled", "DialoguePuzzled",
    "BrowUpLeft", "BrowUpRight",
    "BrowDownLeft", "BrowDownRight",
    "BrowInLeft", "BrowInRight",
    "LookDown",
)

# Canonical VRM 0.x presetName -> VRM 1.0 preset name.
VRM0_PRESET_MAP = {
    "a": "aa",
    "i": "ih",
    "u": "ou",
    "e": "ee",
    "o": "oh",
    "blink": "blink",
    "blink_l": "blinkLeft",
    "blink_r": "blinkRight",
    "joy": "happy",
    "angry": "angry",
    "sorrow": "sad",
    "fun": "relaxed",
    "surprised": "surprised",
    "neutral": "neutral",
    "lookup": "lookUp",
    "lookdown": "lookDown",
    "lookleft": "lookLeft",
    "lookright": "lookRight",
}

EXTRA_HDPT_BASE_ID = 0x01000900


def extract_vrm_expressions(document):
    """Parse VRM 1.0 or VRM 0.x expression bindings from a glTF document.

    Returns dict:
        {
            "expressions": {expr_name: [(node_index, target_index, weight), ...]},
            "nodes": sorted list of node indices that carry mapped expression targets,
            "vrm_version": "1.0" | "0.x" | None,
        }
    """
    nodes = document.get("nodes", [])
    meshes = document.get("meshes", [])
    mesh_to_nodes: dict[int, list[int]] = {}
    for node_idx, node in enumerate(nodes):
        mesh_idx = node.get("mesh")
        if mesh_idx is not None:
            mesh_to_nodes.setdefault(mesh_idx, []).append(node_idx)

    extensions = document.get("extensions", {})
    expressions: dict[str, list[tuple[int, int, float]]] = {}
    version = None

    vrm1 = extensions.get("VRMC_vrm")
    if isinstance(vrm1, dict) and isinstance(vrm1.get("expressions"), dict):
        version = "1.0"
        expr_root = vrm1["expressions"]
        for bucket in ("preset", "custom"):
            for name, entry in (expr_root.get(bucket) or {}).items():
                if not isinstance(entry, dict):
                    continue
                binds = []
                for bind in entry.get("morphTargetBinds") or ():
                    node_idx = bind.get("node")
                    target_idx = bind.get("index")
                    weight = float(bind.get("weight", 1.0))
                    if node_idx is None or target_idx is None or abs(weight) < 1e-6:
                        continue
                    mesh_idx = nodes[node_idx].get("mesh") if 0 <= node_idx < len(nodes) else None
                    if mesh_idx is None or not (0 <= mesh_idx < len(meshes)):
                        continue
                    prims = meshes[mesh_idx].get("primitives", [])
                    if not any(len(p.get("targets", ())) > target_idx for p in prims):
                        continue
                    binds.append((int(node_idx), int(target_idx), weight))
                if binds:
                    expressions[name] = binds
    elif isinstance(extensions.get("VRM"), dict):
        version = "0.x"
        groups = extensions["VRM"].get("blendShapeMaster", {}).get("blendShapeGroups", [])
        for group in groups:
            if not isinstance(group, dict):
                continue
            raw_preset = str(group.get("presetName") or "").strip().lower()
            raw_name = str(group.get("name") or "").strip()
            name = VRM0_PRESET_MAP.get(raw_preset) or raw_name
            if not name or name.lower() == "unknown":
                continue
            binds = []
            for bind in group.get("binds") or ():
                mesh_idx = bind.get("mesh")
                target_idx = bind.get("index")
                weight = float(bind.get("weight", 100.0)) / 100.0
                if mesh_idx is None or target_idx is None or abs(weight) < 1e-6:
                    continue
                if not (0 <= mesh_idx < len(meshes)):
                    continue
                prims = meshes[mesh_idx].get("primitives", [])
                if not any(len(p.get("targets", ())) > target_idx for p in prims):
                    continue
                for node_idx in mesh_to_nodes.get(mesh_idx, ()):
                    binds.append((int(node_idx), int(target_idx), weight))
            if binds:
                expressions[name] = binds

    # Check if at least one core facial expression maps to Skyrim.
    core_keys = {"aa", "ih", "ou", "ee", "oh", "blink", "blinkLeft", "blinkRight",
                 "happy", "angry", "sad", "surprised"}
    has_core = any(k in expressions for k in core_keys)
    expr_nodes = sorted({node_idx for binds in expressions.values() for node_idx, _, _ in binds}) if has_core else []
    return {
        "expressions": expressions if has_core else {},
        "nodes": expr_nodes,
        "vrm_version": version if has_core else None,
    }


def _smooth_lr_masks(x_coords: np.ndarray, half_band: float = 0.25):
    """Return (left_mask, right_mask) in Skyrim actor space (+X is actor right, -X is actor left)."""
    t = np.clip((x_coords + half_band) / (2.0 * half_band), 0.0, 1.0)
    right = t * t * (3.0 - 2.0 * t)
    left = 1.0 - right
    return left[:, None], right[:, None]


def synthesize_skyrim_morph_deltas(
    basis_points: np.ndarray,
    target_deltas: dict[int, np.ndarray],
    vrm_expressions: dict[str, list[tuple[int, int, float]]],
    node_index: int,
) -> dict[str, np.ndarray]:
    """Build Skyrim SE 43-morph delta arrays (N, 3) in posed Skyrim space for one mesh node.

    basis_points: (N, 3) float64 posed Basis vertex coordinates in Skyrim space.
    target_deltas: {target_index: (N, 3) float64 delta from Basis in posed Skyrim space}.
    vrm_expressions: parsed expressions dict from extract_vrm_expressions().
    node_index: glTF node index of this mesh.
    """
    n_verts = len(basis_points)
    zeros = np.zeros((n_verts, 3), dtype=np.float64)

    expr_delta: dict[str, np.ndarray] = {}
    for expr_name, binds in vrm_expressions.items():
        acc = np.zeros((n_verts, 3), dtype=np.float64)
        used = False
        for bind_node, target_idx, weight in binds:
            if bind_node != node_index:
                continue
            delta = target_deltas.get(target_idx)
            if delta is not None:
                acc += delta * weight
                used = True
        if used:
            expr_delta[expr_name] = acc

    # Lowercase lookup helper for custom expressions (e.g. brow_angry, eye_happy).
    expr_lower = {k.lower(): v for k, v in expr_delta.items()}

    def get(*names: str) -> np.ndarray | None:
        for name in names:
            if name in expr_delta:
                return expr_delta[name]
            low = name.lower()
            if low in expr_lower:
                return expr_lower[low]
        return None

    def blend(*terms: tuple[str | tuple[str, ...], float]) -> np.ndarray:
        out = np.zeros((n_verts, 3), dtype=np.float64)
        for key, weight in terms:
            val = get(*key) if isinstance(key, tuple) else get(key)
            if val is not None:
                out += val * weight
        return out

    left_mask, right_mask = _smooth_lr_masks(basis_points[:, 0])

    blink_l = get("blinkLeft")
    if blink_l is None:
        blink = get("blink")
        blink_l = blink * left_mask if blink is not None else zeros
    blink_r = get("blinkRight")
    if blink_r is None:
        blink = get("blink")
        blink_r = blink * right_mask if blink is not None else zeros

    squint_src = get("eye_happy", "happy_eye", "eye_smile", "blink_smile", "relaxed")
    if squint_src is not None:
        squint_l = squint_src * left_mask * 0.75
        squint_r = squint_src * right_mask * 0.75
    else:
        squint_l = blink_l * 0.35
        squint_r = blink_r * 0.35

    brow_up = get("brow_surprised", "brow_up")
    brow_down = get("brow_angry", "brow_down")
    brow_in = get("brow_sad", "brow_in")

    morphs: dict[str, np.ndarray] = {
        # Lip-sync phonemes
        "Aah": blend(("aa", 0.85)),
        "BigAah": blend(("aa", 1.0)),
        "I": blend(("ih", 1.0)),
        "Eee": blend(("ee", 1.0)),
        "Eh": blend(("ee", 0.65), ("aa", 0.35)),
        "Oh": blend(("oh", 1.0)),
        "OohQ": blend(("ou", 1.0)),
        "W": blend(("ou", 0.85)),
        "BMP": zeros.copy(),
        "FV": blend(("ih", 0.35), ("ou", 0.20)),
        "ChJSh": blend(("ih", 0.50), ("ou", 0.35)),
        "DST": blend(("ih", 0.45), ("ee", 0.20)),
        "K": blend(("aa", 0.40), ("ih", 0.25)),
        "N": blend(("ih", 0.30), ("ee", 0.20)),
        "R": blend(("ou", 0.50), ("oh", 0.25)),
        "Th": blend(("ee", 0.40), ("ih", 0.25)),
        # Blink & squint
        "BlinkLeft": blink_l,
        "BlinkRight": blink_r,
        "SquintLeft": squint_l,
        "SquintRight": squint_r,
        # Dialogue / Mood / Combat expressions
        "MoodHappy": blend(("happy", 0.85)),
        "DialogueHappy": blend(("happy", 1.0)),
        "MoodAnger": blend(("angry", 0.85)),
        "DialogueAnger": blend(("angry", 1.0)),
        "CombatAnger": blend(("angry", 1.0)),
        "CombatShout": blend(("aa", 0.85), ("angry", 0.60)),
        "MoodSad": blend(("sad", 0.85)),
        "DialogueSad": blend(("sad", 1.0)),
        "MoodSurprise": blend(("surprised", 0.85)),
        "DialogueSurprise": blend(("surprised", 1.0)),
        "MoodFear": blend(("surprised", 0.55), ("sad", 0.55)),
        "DialogueFear": blend(("surprised", 0.65), ("sad", 0.65)),
        "MoodDisgusted": blend(("angry", 0.60), ("sad", 0.25)),
        "DialogueDisgusted": blend(("angry", 0.75), ("sad", 0.30)),
        "MoodPuzzled": blend(("sad", 0.55), (("brow_sad", "brow_in"), 0.40)),
        "DialoguePuzzled": blend(("sad", 0.65), (("brow_sad", "brow_in"), 0.50)),
        # Brows
        "BrowUpLeft": brow_up * left_mask if brow_up is not None else zeros.copy(),
        "BrowUpRight": brow_up * right_mask if brow_up is not None else zeros.copy(),
        "BrowDownLeft": brow_down * left_mask if brow_down is not None else zeros.copy(),
        "BrowDownRight": brow_down * right_mask if brow_down is not None else zeros.copy(),
        "BrowInLeft": brow_in * left_mask if brow_in is not None else zeros.copy(),
        "BrowInRight": brow_in * right_mask if brow_in is not None else zeros.copy(),
        # Eye gaze
        "LookDown": blend(("lookDown", 1.0)),
    }
    return {name: morphs[name] for name in SKYRIM_EXPRESSION_MORPHS}


def load_facial_manifest(output):
    """Return facial-expressions.json dict if enabled, else None."""
    path = Path(output) / "facial-expressions.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf8"))
    return data if data.get("enabled") and data.get("parts") else None


def read_tri(path):
    """Read an FRTRI003 .tri file using PyNifly's standalone TriFile reader."""
    tri_dir = str(ROOT / "dependencies/io_scene_nifly/tri")
    if tri_dir not in sys.path:
        sys.path.insert(0, tri_dir)
    from trifile import TriFile  # noqa: E402
    with open(path, "rb") as handle:
        return TriFile.from_file(handle)


def facegeom_relative(settings) -> str:
    return f"meshes/actors/character/facegendata/facegeom/{settings.plugin_name}/00000800.nif"


def validate_facial_assets(output, settings):
    """Verify FaceGeom NIF, HDPT NIFs, and FRTRI003 .tri files match 1-to-1."""
    from custom_skeleton import NifFile

    manifest = load_facial_manifest(output)
    if not manifest:
        return None
    output = Path(output)
    mod = output / "mod"
    facegeom_path = mod / facegeom_relative(settings)
    if not facegeom_path.is_file():
        raise ValueError(f"Facial FaceGeom NIF is missing: {facegeom_path}")

    with NifFile(str(facegeom_path)) as fg:
        if fg.game != "SKYRIMSE":
            raise ValueError(f"Wrong FaceGeom NIF target: {fg.game}")
        if fg.root.blockname != "BSFadeNode":
            raise ValueError(f"FaceGeom root must be BSFadeNode, got {fg.root.blockname}")
        fg_shapes = {s.name: s for s in fg.shapes}
        expected_names = [part["edid"] for part in manifest["parts"]]
        if set(fg_shapes) != set(expected_names):
            raise ValueError(f"FaceGeom shapes {sorted(fg_shapes)} != expected HDPT EDIDs {sorted(expected_names)}")
        fg_data = {}
        for part in manifest["parts"]:
            shape = fg_shapes[part["edid"]]
            if shape.blockname != "BSDynamicTriShape":
                raise ValueError(f"FaceGeom shape {shape.name} must be BSDynamicTriShape, got {shape.blockname}")
            if not shape.parent or shape.parent.name != "BSFaceGenNiNodeSkinned":
                raise ValueError(f"FaceGeom shape {shape.name} must be parented to BSFaceGenNiNodeSkinned")
            fg_data[part["edid"]] = (np.asarray(shape.verts, dtype=np.float64),
                                     np.asarray(shape.tris, dtype=np.int32))

    verified_parts = []
    any_nonzero = False
    for part in manifest["parts"]:
        edid = part["edid"]
        part_nif_path = mod / part["nif"]
        part_tri_path = mod / part["tri"]
        if not part_nif_path.is_file() or not part_tri_path.is_file():
            raise ValueError(f"Missing facial part assets for {edid}: {part_nif_path}, {part_tri_path}")
        with NifFile(str(part_nif_path)) as pnif:
            if len(pnif.shapes) != 1:
                raise ValueError(f"HDPT NIF {part_nif_path.name} must contain exactly 1 shape, got {len(pnif.shapes)}")
            pshape = pnif.shapes[0]
            if pshape.blockname != "BSDynamicTriShape":
                raise ValueError(f"HDPT shape {pshape.name} must be BSDynamicTriShape, got {pshape.blockname}")
            p_verts = np.asarray(pshape.verts, dtype=np.float64)
            p_tris = np.asarray(pshape.tris, dtype=np.int32)
        fg_verts, fg_tris = fg_data[edid]
        if p_verts.shape != fg_verts.shape or p_tris.shape != fg_tris.shape:
            raise ValueError(f"HDPT NIF and FaceGeom topology mismatch for {edid}")
        if float(np.max(np.abs(p_verts - fg_verts))) > 1e-4:
            raise ValueError(f"HDPT NIF and FaceGeom vertices diverge for {edid}")

        tri = read_tri(part_tri_path)
        if tri.header.signature != "FRTRI003":
            raise ValueError(f"Invalid TRI signature in {part_tri_path.name}: {tri.header.signature}")
        if tri.header.vertexNum != len(fg_verts) or tri.header.faceNum != len(fg_tris):
            raise ValueError(
                f"TRI topology mismatch for {edid}: tri=({tri.header.vertexNum}v,{tri.header.faceNum}f) "
                f"vs nif=({len(fg_verts)}v,{len(fg_tris)}f)"
            )
        tri_verts = np.asarray(tri.vertices, dtype=np.float64)
        max_err = float(np.max(np.abs(tri_verts - fg_verts)))
        if max_err > 1e-4:
            raise ValueError(f"TRI base vertices differ from FaceGeom NIF for {edid}: {max_err}")

        nonzero_morphs = []
        for mname, mverts in tri.morphs.items():
            if mname == "Basis":
                continue
            delta = np.asarray(mverts, dtype=np.float64) - tri_verts
            if float(np.max(np.abs(delta))) > 1e-4:
                nonzero_morphs.append(mname)
        if nonzero_morphs:
            any_nonzero = True
        verified_parts.append({
            "edid": edid,
            "vertices": len(fg_verts),
            "triangles": len(fg_tris),
            "morph_count": len([k for k in tri.morphs if k != "Basis"]),
            "nonzero_morphs": sorted(nonzero_morphs),
        })

    if not any_nonzero:
        raise ValueError("Facial expression TRI files contain no non-zero morph deltas")
    logging.info("Validated %d facial BSDynamicTriShape parts + FaceGeom + FRTRI003 morphs", len(verified_parts))
    return verified_parts
