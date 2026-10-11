"""Check custom limb lengths while HKX overwrites animated bone-local transforms."""
import json
import logging
from pathlib import Path
import sys

import numpy as np
from scipy.spatial.transform import Rotation

from custom_skeleton import NifFile, matrix
from settings import load_settings, reference_root

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "dependencies/io_scene_nifly/hkx"))
from anim_skyrim import load_skyrim_animation, load_skyrim_skeleton  # noqa: E402


def verify_animation(output):
    output = Path(output)
    settings = load_settings(output)
    base = reference_root(output) / "meshes/actors/character"
    hkx = load_skyrim_skeleton(str(base / "character assets/skeleton.hkx"))
    with NifFile(str(output / "mod/meshes" / settings.asset_dir / "skeleton.nif")) as file:
        local = {name: matrix(node.transform) for name, node in file.nodes.items()}
        parents = {name: node.parent.name if node.parent else None for name, node in file.nodes.items()}
        original = {name: matrix(node.global_transform)[:3, 3] for name, node in file.nodes.items()}
    segments = {}
    for side in ("L", "R"):
        for a, b, ca, cb in (("UpperArm", "Forearm", "Uar", "Lar"), ("Forearm", "Hand", "Lar", "Hnd"),
                             ("Thigh", "Calf", "Thg", "Clf"), ("Calf", "Foot", "Clf", "ft ")):
            start, end = f"NPC {side} {a} [{side}{ca}]", f"NPC {side} {b} [{side}{cb}]"
            segments[start] = (end, np.linalg.norm(original[end] - original[start]))
    reports = {}
    for kind, filename in (("walk", f"animations/{settings.sex}/mt_walkforward.hkx"),
                           ("attack", "animations/1hm_attackright.hkx")):
        animation = load_skyrim_animation(str(base / filename))
        indices = animation.track_to_bone_indices or list(range(animation.num_tracks))
        names = [hkx.bones[index] for index in indices]
        errors = []
        for frame in range(animation.num_frames):
            animated = dict(local)
            for name, track in zip(names, animation.tracks):
                if name not in local:
                    continue
                value = np.eye(4)
                value[:3, :3] = Rotation.from_quat(track.rotations[frame]).as_matrix() @ np.diag(track.scales[frame])
                value[:3, 3] = track.translations[frame]
                animated[name] = value
            globals_ = {}

            def global_transform(name):
                if name not in globals_:
                    parent = parents[name]
                    globals_[name] = (global_transform(parent) if parent else np.eye(4)) @ animated[name]
                return globals_[name]

            for start, (end, expected) in segments.items():
                actual = np.linalg.norm(global_transform(end)[:3, 3] - global_transform(start)[:3, 3])
                errors.append(abs(actual / expected - 1))
        error = float(max(errors))
        if error > 0.0001:
            raise ValueError(f"HKX changes custom limb proportions: {kind}: {error}")
        reports[kind] = {"frames": animation.num_frames, "limb_segments": len(segments),
                         "max_length_ratio_error": error}
    report = {"animations": reports, "evaluation": "HKX local transforms plus delivered NIF proxy hierarchy",
              "game_verified": False, "foot_ik_verified": False, "ragdoll_verified": False}
    (output / "animation-validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    logging.info("Custom skeleton retained limb lengths throughout all %s sampled HKX frames",
                 sum(item["frames"] for item in reports.values()))
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    verify_animation(sys.argv[1])
