"""Insert rigid offsets without changing the animation-controlled local transforms."""
from ctypes import c_int
import json
import logging
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "dependencies/io_scene_nifly"))
from pyn.pynifly import NifFile  # noqa: E402
from pyn.niflydll import nifly  # noqa: E402
from pyn.structs import TransformBuf  # noqa: E402


def matrix(transform):
    result = np.eye(4)
    result[:3, :3] = np.array(transform.rotation) * transform.scale
    result[:3, 3] = transform.translation
    return result


def rigid_buffer(value):
    value = np.asarray(value)
    if not np.allclose(value[:3, :3].T @ value[:3, :3], np.eye(3), atol=2e-5):
        raise ValueError("Body-proportion preservation forbids nonrigid bone offsets")
    buf = TransformBuf()
    buf.store(value[:3, 3], value[:3, :3].tolist(), (1, 1, 1))
    return buf


def children(file, node):
    buf = (c_int * (len(file.nodes) + 100))()
    count = nifly.getNodeChildren(file._handle, node.id, len(buf), buf)
    if count < 0 or count > len(buf):
        raise ValueError("Invalid skeleton child count")
    return list(buf)[:count]


def set_children(file, node, ids):
    buf = (c_int * len(ids))(*ids)
    nifly.setNodeChildren(file._handle, node.id, buf, len(ids))


def create_skeleton(source, destination, positions):
    """positions is a dict of original bone names to desired global joint positions.

    The unanimated proxy transform P satisfies P @ V = C, where V is the
    unchanged vanilla local transform and C is the desired custom local pose.
    Native file editing retains the skeleton's collision and extra-data blocks.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with NifFile(str(source)) as file:
        original = dict(file.nodes)
        parents = {name: node.parent.name if node.parent else None for name, node in original.items()}
        local = {name: matrix(node.transform) for name, node in original.items()}
        original_children = {name: children(file, node) for name, node in original.items()}
        desired = {}

        def compute(name):
            if name in desired:
                return desired[name]
            parent = parents[name]
            value = (compute(parent) if parent else np.eye(4)) @ local[name]
            if name in positions:
                value[:3, 3] = positions[name]
            desired[name] = value
            return value

        for name in original:
            compute(name)
        offsets = {}
        replacement = {}
        for name, node in original.items():
            parent = parents[name]
            if parent is None:
                continue
            custom_local = np.linalg.inv(desired[parent]) @ desired[name]
            offset = custom_local @ np.linalg.inv(local[name])
            if np.allclose(offset, np.eye(4), atol=1e-5):
                continue
            proxy_name = "VRM2SkyrimOffset_" + name
            proxy = file.add_node(proxy_name, rigid_buffer(offset), original[parent])
            set_children(file, proxy, [node.id])
            replacement[node.id] = proxy.id
            offsets[name] = {"proxy": proxy_name, "parent": parent, "offset": offset.tolist()}
        # Remove original links and the temporary links added by add_node.
        for name, node in original.items():
            set_children(file, node, [replacement.get(index, index) for index in original_children[name]])
        file.filepath = str(destination)
        file.save()
    errors = {}
    with NifFile(str(destination)) as file:
        for name, expected in desired.items():
            observed = matrix(file.nodes[name].global_transform)
            error = float(np.max(np.abs(observed - expected)))
            if error > 5e-4:
                errors[name] = error
            # Animation must still find its own original bone-local transform.
            if not np.allclose(matrix(file.nodes[name].transform), local[name], atol=1e-5):
                raise ValueError(f"Animation-controlled transform changed: {name}")
        node_count = len(file.nodes)
    if errors:
        raise ValueError(f"Custom skeleton hierarchy mismatch: {errors}")
    report = {"source": str(source), "skeleton": str(destination), "nodes": node_count,
              "proxy_offsets": offsets, "joint_positions": {key: list(value) for key, value in positions.items()},
              "animation_local_transforms_unchanged": True, "bone_scale": 1.0,
              "game_verified": False, "ragdoll_fit_verified": False}
    logging.info("Custom skeleton: %s nodes, %s rigid offsets", node_count, len(offsets))
    return report


def save_report(report, output):
    (Path(output) / "skeleton.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
