"""Deform equipment into a target body; target skin vertices are read-only."""
import logging

import numpy as np
from scipy.spatial import cKDTree

from preserved_pose import align_rotation

LOG = logging.getLogger(__name__)
CENTRAL = ("NPC Pelvis [Pelv]", "NPC Spine [Spn0]", "NPC Spine1 [Spn1]",
           "NPC Spine2 [Spn2]", "NPC Neck [Neck]", "NPC Head [Head]")
SEGMENTS = dict(zip(CENTRAL[:-1], CENTRAL[1:]))
PRIMARY = set(CENTRAL)
for side in ("L", "R"):
    names = [f"NPC {side} {name} [{side}{code}]" for name, code in
             (("Clavicle", "Clv"), ("UpperArm", "Uar"), ("Forearm", "Lar"), ("Hand", "Hnd"))]
    legs = [f"NPC {side} {name} [{side}{code}]" for name, code in
            (("Thigh", "Thg"), ("Calf", "Clf"), ("Foot", "ft "), ("Toe0", "Toe"))]
    SEGMENTS.update(zip(names[:-1], names[1:]))
    SEGMENTS.update(zip(legs[:-1], legs[1:]))
    SEGMENTS[names[-1]] = f"NPC {side} Finger20 [{side}F20]"
    PRIMARY.update(names + legs)


def canonical_bone(name, parents):
    visited = set()
    while name not in PRIMARY:
        if name in visited or name not in parents or parents[name] is None:
            raise ValueError(f"Cannot map equipment bone to humanoid skeleton: {name}")
        visited.add(name)
        name = parents[name]
    return name


def canonical_weights(weights, parents):
    result = {}
    for name, pairs in weights.items():
        target = canonical_bone(name, parents)
        merged = result.setdefault(target, {})
        for index, weight in pairs:
            merged[index] = merged.get(index, 0) + weight
    return {name: list(values.items()) for name, values in result.items()}


def dense_weights(weights, count):
    result = {name: np.zeros(count) for name in weights}
    for name, pairs in weights.items():
        for index, value in pairs:
            result[name][index] += value
    return result


class BodyField:
    def __init__(self, source, source_weights, target, target_weights, source_joints, target_joints):
        self.source = np.asarray(source, dtype=float)
        self.target = np.asarray(target, dtype=float)
        self.transforms = {}
        source_dense = dense_weights(source_weights, len(source))
        target_dense = dense_weights(target_weights, len(target))
        self.source_joints, self.target_joints = source_joints, target_joints
        for bone in source_joints.keys() & target_joints.keys() & PRIMARY:
            origin, destination = source_joints[bone], target_joints[bone]
            child = SEGMENTS.get(bone)
            if child in source_joints and child in target_joints:
                along = source_joints[child] - origin
                target_along = target_joints[child] - destination
                length = np.linalg.norm(along)
                target_length = np.linalg.norm(target_along)
            else:
                along, target_along = np.array((0., 0., 1.)), np.array((0., 0., 1.))
                length = target_length = 1.
            if min(length, target_length) < 1e-5:
                raise ValueError(f"Degenerate armor reference joint: {bone}")
            axis = along / length
            across = np.array((1., 0., 0.))
            if abs(np.dot(across, axis)) > .8:
                across = np.array((0., 1., 0.))
            across -= axis * np.dot(across, axis)
            across /= np.linalg.norm(across)
            basis = np.column_stack((across, np.cross(axis, across), axis))
            rotation = align_rotation(along, target_along)
            target_basis = rotation @ basis
            if " Hand " in bone:
                side = "L" if "NPC L " in bone else "R"
                index, little = f"NPC {side} Finger10 [{side}F10]", f"NPC {side} Finger40 [{side}F40]"
                if all(n in source_joints and n in target_joints for n in (index, little)):
                    def palm_frame(joints, direction):
                        axis = direction / np.linalg.norm(direction)
                        across = joints[index] - joints[little]
                        across -= axis * np.dot(across, axis)
                        across /= np.linalg.norm(across)
                        return np.column_stack((across, np.cross(axis, across), axis))
                    basis = palm_frame(source_joints, along)
                    target_basis = palm_frame(target_joints, target_along)
            scales = np.array((1., 1., target_length / length))
            src = self.source[source_dense.get(bone, np.zeros(len(source))) > .15]
            dst = self.target[target_dense.get(bone, np.zeros(len(target))) > .15]
            radial_offset = np.zeros(3)
            if min(len(src), len(dst)) >= 8:
                a, b = (src - origin) @ basis, (dst - destination) @ target_basis
                lo_a, hi_a = np.quantile(a, [.03, .97], axis=0)
                lo_b, hi_b = np.quantile(b, [.03, .97], axis=0)
                spans_a, spans_b = hi_a - lo_a, hi_b - lo_b
                scales[:2] = np.clip(spans_b[:2] / np.maximum(spans_a[:2], .1), .25, 4.)
                radial_offset[:2] = (lo_b[:2] + hi_b[:2]) / 2 - (lo_a[:2] + hi_a[:2]) / 2 * scales[:2]
            linear = target_basis @ np.diag(scales) @ basis.T
            offset = destination - linear @ origin + target_basis @ radial_offset
            self.transforms[bone] = (linear, offset)
        coarse = self.coarse(self.source, source_weights)
        # Condition nearest-surface correspondences on the same anatomical bone.
        residuals = np.zeros_like(coarse)
        totals = np.zeros(len(coarse))
        for bone, values in source_dense.items():
            selected = np.flatnonzero(values > 1e-5)
            target_indices = np.flatnonzero(target_dense.get(bone, np.zeros(len(target))) > .05)
            if not len(target_indices):
                continue
            tree = cKDTree(self.target[target_indices])
            _, indices = tree.query(coarse[selected])
            residuals[selected] += (self.target[target_indices[indices]] - coarse[selected]) * values[selected, None]
            totals[selected] += values[selected]
        residuals /= np.maximum(totals, 1e-12)[:, None]
        # Average nearby reference corrections rather than forcing armor onto skin.
        self.coarse_source = coarse
        self.reference_tree = cKDTree(coarse)
        distances, indices = self.reference_tree.query(coarse, k=min(12, len(coarse)))
        factors = 1 / np.maximum(distances, .6) ** 2
        self.residuals = np.sum(residuals[indices] * factors[:, :, None], axis=1) / factors.sum(axis=1)[:, None]
        LOG.info("Armor field: %s reference vertices, %s target vertices, %s bone transforms",
                 len(source), len(target), len(self.transforms))

    def coarse(self, points, weights):
        points = np.asarray(points, dtype=float)
        result, total = np.zeros_like(points), np.zeros(len(points))
        for bone, pairs in weights.items():
            if bone not in self.transforms:
                raise ValueError(f"Armor bone has no fitted segment: {bone}")
            merged = {}
            for index, value in pairs:
                merged[index] = merged.get(index, 0) + value
            indices = np.array(list(merged), dtype=int)
            values = np.array(list(merged.values()))
            linear, offset = self.transforms[bone]
            result[indices] += (points[indices] @ linear.T + offset) * values[:, None]
            total[indices] += values
        if np.any(total < 1e-6):
            raise ValueError("Unweighted equipment vertices")
        return result / total[:, None]

    def deform(self, points, weights):
        coarse = self.coarse(points, weights)
        distances, indices = self.reference_tree.query(coarse, k=min(12, len(self.source)))
        factors = 1 / np.maximum(distances, .6) ** 2
        correction = np.sum(self.residuals[indices] * factors[:, :, None], axis=1) / factors.sum(axis=1)[:, None]
        return coarse + correction
