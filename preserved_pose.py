"""Pose alignment by joint rotation only; never fit body lengths to Skyrim."""
import numpy as np


def align_rotation(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if min(np.linalg.norm(a), np.linalg.norm(b)) < 1e-8:
        return np.eye(3)
    a /= np.linalg.norm(a)
    b /= np.linalg.norm(b)
    cross = np.cross(a, b)
    cosine = np.clip(np.dot(a, b), -1, 1)
    if cosine < -0.999999:
        axis = np.cross(a, (1, 0, 0) if abs(a[0]) < .9 else (0, 1, 0))
        axis /= np.linalg.norm(axis)
        return 2 * np.outer(axis, axis) - np.eye(3)
    skew = np.array([[0, -cross[2], cross[1]], [cross[2], 0, -cross[0]], [-cross[1], cross[0], 0]])
    return np.eye(3) + skew + skew @ skew / (1 + cosine)


def point(transform, position):
    return transform[:3, :3] @ np.asarray(position) + transform[:3, 3]


def palm_basis(positions, names, side):
    hand = np.asarray(positions[names[side + "Hand"]])
    along = np.asarray(positions[names[side + "MiddleProximal"]]) - hand
    if np.linalg.norm(along) < 1e-8:
        raise ValueError("Degenerate palm direction")
    along /= np.linalg.norm(along)
    across = (np.asarray(positions[names[side + "LittleProximal"]])
              - positions[names[side + "IndexProximal"]])
    across -= along * np.dot(across, along)
    if np.linalg.norm(across) < 1e-8:
        raise ValueError("Degenerate palm width")
    across /= np.linalg.norm(across)
    return np.column_stack((along, across, np.cross(along, across)))


def preserved_transforms(source_positions, bone_names, source_parents, target_positions, core):
    transforms = {}
    # Leave the torso, head and legs in their original shape. Only lower the arms
    # from the VRM's spread pose into the game's neutral arm pose.
    for key in ("hips", "spine", "chest", "upperChest", "neck", "head",
                "leftShoulder", "rightShoulder", "leftUpperLeg", "rightUpperLeg",
                "leftLowerLeg", "rightLowerLeg", "leftFoot", "rightFoot", "leftToes", "rightToes"):
        if key in bone_names:
            transforms[bone_names[key]] = np.eye(4)
    for side in ("left", "right"):
        previous = np.eye(4)
        for current, following in (("UpperArm", "LowerArm"), ("LowerArm", "Hand"),
                                   ("Hand", "MiddleProximal")):
            key, next_key = side + current, side + following
            name = bone_names[key]
            p = np.asarray(source_positions[name])
            q = point(previous, p)
            if next_key in bone_names:
                a = np.asarray(source_positions[bone_names[next_key]]) - p
                b = np.asarray(target_positions[core[next_key]]) - target_positions[core[key]]
                rotation = align_rotation(a, b)
                palm_keys = [side + key for key in ("Hand", "MiddleProximal", "LittleProximal", "IndexProximal")]
                if current == "Hand" and all(key in bone_names for key in palm_keys):
                    try:
                        rotation = (palm_basis(target_positions, core, side)
                                    @ palm_basis(source_positions, bone_names, side).T)
                    except ValueError:
                        pass  # Keep the rigid along-axis alignment for degenerate optional finger data.
            else:
                rotation = previous[:3, :3]
            value = np.eye(4)
            value[:3, :3] = rotation
            value[:3, 3] = q - rotation @ p
            transforms[name] = value
            previous = value
        # Match the bend axes as well as the palm's direction. A proxy preserves
        # positions but the vanilla animation still rotates around vanilla axes.
        hand_rotation = previous[:3, :3]
        for finger in ("Thumb", "Index", "Middle", "Ring", "Little"):
            parts = ("Metacarpal", "Proximal", "Distal") if finger == "Thumb" else ("Proximal", "Intermediate", "Distal")
            previous = transforms[bone_names[side + "Hand"]]
            for index, part in enumerate(parts):
                key = side + finger + part
                if key not in bone_names:
                    continue
                name = bone_names[key]
                p = np.asarray(source_positions[name])
                q = point(previous, p)
                rotation = previous[:3, :3]
                if index < 2 and side + finger + parts[index + 1] in bone_names:
                    next_key = side + finger + parts[index + 1]
                    a = np.asarray(source_positions[bone_names[next_key]]) - p
                    b = np.asarray(target_positions[core[next_key]]) - target_positions[core[key]]
                    rotation = align_rotation(hand_rotation @ a, b) @ hand_rotation
                value = np.eye(4)
                value[:3, :3] = rotation
                value[:3, 3] = q - rotation @ p
                transforms[name] = value
                previous = value

    def inherited(name):
        if name in transforms:
            return transforms[name]
        parent = source_parents[name]
        transforms[name] = inherited(parent).copy() if parent else np.eye(4)
        return transforms[name]

    for name in source_positions:
        inherited(name)
    positions = {core[key]: point(transforms[name], source_positions[name])
                 for key, name in bone_names.items()
                 if key in core and key not in ("leftEye", "rightEye", "jaw")}
    spine1 = "NPC Spine1 [Spn1]"
    if core["neck"] not in positions:
        positions[core["neck"]] = positions[core["spine"]] + .85 * (positions[core["head"]] - positions[core["spine"]])
    # VRM permits chest/upperChest to be omitted. Add the game-only joint along
    # the existing spine-to-neck segment without moving any source vertex.
    if core["chest"] not in positions:
        positions[core["chest"]] = .5 * (positions[core["spine"]] + positions[core["neck"]])
    if spine1 in target_positions:
        start, end = core["spine"], core["chest"]
        fraction = (np.linalg.norm(target_positions[spine1] - target_positions[start])
                    / np.linalg.norm(target_positions[end] - target_positions[start]))
        positions[spine1] = positions[start] + fraction * (positions[end] - positions[start])
    lengths = {}
    for side in ("left", "right"):
        for first, last in (("UpperArm", "LowerArm"), ("LowerArm", "Hand"),
                            ("UpperLeg", "LowerLeg"), ("LowerLeg", "Foot")):
            a, b = side + first, side + last
            before = np.linalg.norm(np.asarray(source_positions[bone_names[b]]) - source_positions[bone_names[a]])
            if before < 1e-8:
                raise ValueError(f"Required humanoid limb has zero length: {a}")
            after = np.linalg.norm(positions[core[b]] - positions[core[a]])
            lengths[a] = {"source": float(before), "custom": float(after), "ratio": float(after / before)}
            if abs(after / before - 1) > 1e-6:
                raise ValueError(f"Original limb length changed: {a}")
    for name, value in transforms.items():
        if not np.allclose(value[:3, :3].T @ value[:3, :3], np.eye(3), atol=1e-6):
            raise ValueError(f"Nonrigid pose change: {name}")
    return transforms, positions, lengths
