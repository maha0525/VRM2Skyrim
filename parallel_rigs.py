"""Match secondary humanoid rigs using both semantic names and rest geometry."""
import logging
import re

import numpy as np


def normalized(name):
    # Exporter duplicate suffixes only produce candidates; geometry/ownership
    # and uniqueness decide whether a candidate can actually be used.
    base = re.sub(r"(?:_\d+|\.\d{3})$", "", name)
    return re.sub(r"[^a-z0-9]", "", base.lower())


def follower_links(positions, labels, owners, humanoid):
    primary_owner = owners[humanoid["hips"]]
    height = max(np.linalg.norm(positions[humanoid["head"]] - positions[humanoid["leftFoot"]]), 1e-5)
    tolerance = height * .08
    links, reports = {}, []
    for owner in sorted(set(owners.values()) - {primary_owner}):
        candidates = [name for name in positions if owners[name] == owner]
        matches, distances, ambiguous = {}, {}, []
        for role, primary in humanoid.items():
            aliases = {normalized(labels[primary]), normalized(role)}
            near = [name for name in candidates if normalized(labels[name]) in aliases
                    and np.linalg.norm(positions[name] - positions[primary]) <= tolerance]
            if len(near) > 1:
                ambiguous.append(role)
            elif near:
                matches[near[0]] = primary
                distances[role] = float(np.linalg.norm(positions[near[0]] - positions[primary]))
        if humanoid["hips"] not in matches.values() or len(matches) < 3:
            continue  # Unrelated accessory rigs are not duplicate humanoids.
        if ambiguous:
            raise ValueError("Ambiguous secondary humanoid bones: " + ", ".join(ambiguous))
        # Parent direction must remain broadly compatible, not merely nearby.
        for side in ("left", "right"):
            for start, end in (("UpperArm", "LowerArm"), ("LowerArm", "Hand"), ("UpperLeg", "LowerLeg")):
                a, b = humanoid.get(side + start), humanoid.get(side + end)
                reverse = {primary: secondary for secondary, primary in matches.items()}
                if a in reverse and b in reverse:
                    first = positions[b] - positions[a]
                    second = positions[reverse[b]] - positions[reverse[a]]
                    denominator = np.linalg.norm(first) * np.linalg.norm(second)
                    if denominator < 1e-10 or np.dot(first, second) / denominator < .8:
                        raise ValueError("Secondary rig limb direction is incompatible: " + side + start)
        links.update(matches)
        reports.append({"rig": owner, "matched_bones": len(matches), "rest_distances": distances,
                        "tolerance": float(tolerance)})
        logging.info("Secondary rig %s: %s validated humanoid links", owner, len(matches))
    return links, reports


def propagate_pose(transforms, parents, owners, links):
    """Apply primary model-space pose deltas, preserving secondary rest offsets."""
    followers = {owners[name] for name in links}
    resolved = {}

    def resolve(name):
        if name in resolved:
            return resolved[name]
        if name in links:
            value = transforms[links[name]].copy()
        else:
            parent = parents[name]
            value = resolve(parent).copy() if parent and owners[parent] == owners[name] else np.eye(4)
        resolved[name] = value
        return value

    for name in transforms:
        if owners[name] in followers:
            resolve(name)
    transforms.update(resolved)
