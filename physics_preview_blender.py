"""Offline Bullet joint/gravity preview driven by the emitted FSMP XML.

Blender's Bullet solver verifies joint frames, settling and anchor following.
FSMP's custom skinned-mesh contact solver is separate; this preview disables
bone-body collisions, just as FSMP does, rather than inventing rigid contacts.
"""
import argparse
import json
import math
from pathlib import Path
import sys

import bpy
import numpy as np
from mathutils import Matrix

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'dependencies'))
from custom_skeleton import NifFile, matrix  # noqa: E402
from settings import load_settings  # noqa: E402
from physics_rig import read_system  # noqa: E402


def vec(node, tag):
    child = node.find(tag)
    return np.array([float(child.attrib.get(a, 0)) for a in 'xyz']) if child is not None else np.zeros(3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    output = args.output.resolve()
    settings = load_settings(output)
    with NifFile(str(output/'mod/meshes'/settings.asset_dir/'skeleton.nif')) as file:
        globals_ = {n: matrix(node.global_transform) for n, node in file.nodes.items()}
    systems = json.loads((output/'physics.json').read_text(encoding='utf8'))['systems']
    # Appearance parts equip only one face/hair variant at a time.
    systems = [s for s in systems if Path(s['nif']).stem not in ('fixed_full', 'fixed_no_face')]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = 60
    scene.gravity = (0, 0, -9.81)
    bodies, offsets, definitions, constraints = {}, {}, {}, []
    for system in systems:
        root = read_system(output/'mod'/system['xml'])
        for definition in root.findall('bone'):
            name = definition.attrib['name']
            mass = float(definition.findtext('mass', '0'))
            if name in definitions and mass != float(definitions[name].findtext('mass', '0')):
                raise ValueError('Conflicting physics owners in simultaneously worn components')
            definitions[name] = definition
        constraints.extend(root.findall('generic-constraint'))
    for name, definition in definitions.items():
        mass = float(definition.findtext('mass', '0'))
        offset = np.eye(4)
        com = definition.find('centerOfMassTransform')
        if com is not None:
            offset[:3, 3] = vec(com, 'origin')
        offsets[name] = offset
        radius = float(definition.findtext('shape/radius', '.65'))
        bpy.ops.mesh.primitive_uv_sphere_add(segments=8, ring_count=4, radius=radius)
        obj = bpy.context.object
        obj.name = name
        obj.matrix_world = Matrix((globals_[name] @ offset).tolist())
        bpy.ops.rigidbody.object_add()
        rb = obj.rigid_body
        rb.type = 'ACTIVE'
        rb.kinematic = mass == 0
        rb.mass = mass or 1.
        rb.collision_shape = 'SPHERE'
        rb.collision_collections = [False]*20
        rb.linear_damping = float(definition.findtext('linearDamping', '.04'))
        rb.angular_damping = float(definition.findtext('angularDamping', '.1'))
        obj.hide_render = True
        bodies[name] = obj
        if not mass:
            original = obj.location.copy()
            for frame in range(1, 1801):
                # One smooth anchor excursion, then let the cloth settle.
                shift = 3*(1-math.cos(2*math.pi*(frame-120)/120)) if 120 <= frame <= 240 else 0
                obj.location = original.copy()
                obj.location.x += shift
                obj.keyframe_insert(data_path='location', frame=frame)
    scene.rigidbody_world.substeps_per_frame = 16
    scene.rigidbody_world.solver_iterations = 160
    scene.rigidbody_world.point_cache.frame_start = 1
    scene.rigidbody_world.point_cache.frame_end = 1800
    for definition in constraints:
        a, b = definition.attrib['bodyA'], definition.attrib['bodyB']
        frame = np.eye(4)
        frame[:3, 3] = vec(definition.find('frameInB'), 'origin')
        obj = bpy.data.objects.new('Joint_'+b, None)
        scene.collection.objects.link(obj)
        obj.matrix_world = Matrix((globals_[b] @ offsets[b] @ frame).tolist())
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.rigidbody.constraint_add()
        joint = obj.rigid_body_constraint
        joint.type = 'GENERIC_SPRING'
        joint.object1, joint.object2 = bodies[a], bodies[b]
        joint.disable_collisions = True
        for i, axis in enumerate('xyz'):
            setattr(joint, 'use_limit_lin_'+axis, True)
            setattr(joint, 'limit_lin_'+axis+'_lower', float(vec(definition, 'linearLowerLimit')[i]))
            setattr(joint, 'limit_lin_'+axis+'_upper', float(vec(definition, 'linearUpperLimit')[i]))
            setattr(joint, 'use_limit_ang_'+axis, True)
            setattr(joint, 'limit_ang_'+axis+'_lower', float(vec(definition, 'angularLowerLimit')[i]))
            setattr(joint, 'limit_ang_'+axis+'_upper', float(vec(definition, 'angularUpperLimit')[i]))
            setattr(joint, 'use_spring_ang_'+axis, True)
            setattr(joint, 'spring_stiffness_ang_'+axis, float(vec(definition, 'angularStiffness')[i]))
            setattr(joint, 'spring_damping_ang_'+axis, float(vec(definition, 'angularDamping')[i]))
        obj.select_set(False)
    frames, errors, positions = {}, [], []
    dynamic = [n for n, d in definitions.items() if float(d.findtext('mass', '0')) > 0]
    for frame in range(1, 1801):
        scene.frame_set(frame)
        graph = bpy.context.evaluated_depsgraph_get()
        values = {n: np.asarray(o.evaluated_get(graph).matrix_world) for n, o in bodies.items()}
        for constraint in constraints:
            a, b = constraint.attrib['bodyA'], constraint.attrib['bodyB']
            # Compare the shared rest-world pivot transformed with both bodies.
            pivot = globals_[b][:3, 3]
            rest_a = globals_[a] @ offsets[a]
            rest_b = globals_[b] @ offsets[b]
            pa = values[a] @ np.linalg.inv(rest_a) @ np.r_[pivot, 1]
            pb = values[b] @ np.linalg.inv(rest_b) @ np.r_[pivot, 1]
            errors.append(float(np.linalg.norm(pa[:3]-pb[:3])))
        positions.append(np.array([values[n][:3, 3] for n in dynamic]))
        if frame in (1, 120, 180, 240, 360, 600, 1800):
            frames[str(frame)] = {n: (values[n] @ np.linalg.inv(offsets[n]) @ np.linalg.inv(globals_[n])).tolist()
                                  for n in dynamic}
            print('Bullet frame', frame, 'max joint error', max(errors), flush=True)
    displacement = np.linalg.norm(positions[-1]-positions[0], axis=1)
    result = {'engine': 'Blender Bullet joint-only preview from delivered FSMP XML',
              'frames': frames, 'dynamic_bones': len(dynamic), 'max_joint_error': max(errors),
              'max_settle_speed': float(np.linalg.norm(positions[-1]-positions[-2], axis=1).max()*60),
              'max_displacement': float(displacement.max()),
              'mesh_contact_solver': 'FSMP runtime handles contacts; bone collisions disabled in this preview'}
    if (not np.isfinite(displacement).all() or max(errors) > .1 or displacement.max() < 1 or
            result['max_settle_speed'] > 1.):
        raise ValueError('Physics preview failed joint/gravity checks')
    (output/'physics-preview.json').write_text(json.dumps(result, indent=2), encoding='utf8')


if __name__ == '__main__':
    main()
