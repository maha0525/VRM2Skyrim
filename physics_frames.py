"""Unify FSMP render/contact frames while preserving the original skin.

FSMP 4.1.1 uses inverse(COM)*rig for contacts and rig*inverse(COM) for
rendering. Identity COM eliminates this mismatch; shifted native origins,
compensated binds and explicit joint frames preserve the intended physics.
"""
import logging

import numpy as np

from custom_skeleton import NifFile, matrix, rigid_buffer

FRAME_TOLERANCE = .0005  # NIF float32 hierarchy precision; native readback allows .001


def translation(value):
    result = np.eye(4)
    result[:3, 3] = value
    return result


def shift_frames(path, targets):
    """Move secondary nodes to mass centres and compensate G*bind products.

    Child world frames are retained unless explicitly targeted. Bone names,
    hierarchy, vertices, weights and humanoid globals remain intact. Native
    saving rebuilds skin bounds from the adjusted skin-to-bone matrices.
    """
    with NifFile(str(path)) as nif:
        old = {n: matrix(node.global_transform) for n, node in nif.nodes.items()}
        desired = {n: np.asarray(targets[n]) if n in targets else value for n, value in old.items()}
        changed = {n for n in old if not np.allclose(old[n], desired[n], atol=FRAME_TOLERANCE, rtol=0)}
        if not changed:
            return 0
        if any(not n.startswith('V2SP_') for n in changed):
            raise ValueError('Only private secondary bone origins may change')
        products = []
        for shape in nif.shapes:
            for name in set(shape.bone_names) & changed:
                bind = shape.get_shape_skin_to_bone(name)
                if bind is None:
                    raise ValueError('Physics bone lacks a skin bind: '+name)
                invariant = old[name] @ matrix(bind)
                shape.set_skin_to_bone_xform(name, rigid_buffer(np.linalg.inv(desired[name]) @ invariant))
                products.append((shape.name, name, invariant))
        for name, node in nif.nodes.items():
            parent = node.parent.name if node.parent else None
            if name not in changed and parent not in changed:
                continue
            local = np.linalg.inv(desired[parent]) @ desired[name] if parent else desired[name]
            node.transform = rigid_buffer(local)
            node.write_properties()
        nif.save()
    with NifFile(str(path)) as nif:
        for name, value in desired.items():
            if not np.allclose(matrix(nif.nodes[name].global_transform), value, atol=.001, rtol=0):
                raise ValueError('Physics origin/child world-frame mismatch: '+name)
        shapes = {s.name: s for s in nif.shapes}
        for shape, name, invariant in products:
            observed = matrix(nif.nodes[name].global_transform) @ matrix(shapes[shape].get_shape_skin_to_bone(name))
            if not np.allclose(observed, invariant, atol=.001, rtol=0):
                raise ValueError('Recentring changed the rendered skin: '+name)
    logging.info('FSMP unified contact frames: %s, %s origins, %s compensated binds',
                 path.name, len(changed), len(products))
    return len(changed)
