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
from mathutils import Matrix, Quaternion

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'dependencies'))
from custom_skeleton import NifFile, matrix  # noqa: E402
from settings import load_settings  # noqa: E402
from physics_rig import read_system  # noqa: E402

GRAVITY = 9.8 / .01425


def vec(node, tag):
    child = node.find(tag)
    return np.array([float(child.attrib.get(a, 0)) for a in 'xyz']) if child is not None else np.zeros(3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frames', type=int, default=900)
    parser.add_argument('--fps', type=int, default=60, choices=(30, 60, 120))
    parser.add_argument('--result', default='physics-preview.json')
    parser.add_argument('--allow-failure', action='store_true')
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
    scene.render.fps = args.fps
    scene.gravity = (0, 0, -GRAVITY)
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
        inertia = definition.find('inertia')
        if mass and inertia is not None:
            divisors = vec(definition, 'inertia')
            if not np.allclose(divisors, divisors[0]) or divisors[0] <= 0:
                raise ValueError('Preview requires an isotropic positive inertia divisor')
            radius /= math.sqrt(divisors[0])
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
            original = obj.matrix_world.copy()
            for frame in range(1, args.frames+1):
                # Move and turn the whole animated anchor frame, then stop.
                # 30 game-unit translation and 35-degree turn exercise inertia.
                t = frame/args.fps
                pulse = (1-math.cos(math.pi*(t-2)))/2 if 2 <= t <= 4 else 0
                move = Matrix.Translation((30*pulse, 0, 3*math.sin(4*math.pi*pulse)))
                rotate = Matrix.Rotation(math.radians(35)*pulse, 4, 'Z')
                obj.matrix_world = move @ rotate @ original
                obj.keyframe_insert(data_path='location', frame=frame)
                obj.keyframe_insert(data_path='rotation_euler', frame=frame)
    substeps = max(1, 60//args.fps)
    scene.rigidbody_world.substeps_per_frame = substeps
    scene.rigidbody_world.solver_iterations = 16
    scene.rigidbody_world.point_cache.frame_start = 1
    scene.rigidbody_world.point_cache.frame_end = args.frames
    for definition in constraints:
        a, b = definition.attrib['bodyA'], definition.attrib['bodyB']
        frame = np.eye(4)
        frame[:3, 3] = vec(definition.find('frameInB'), 'origin')
        q = definition.find('frameInB/basis')
        if q is not None:
            frame[:3, :3] = np.asarray(Quaternion([float(q.attrib[a]) for a in 'wxyz']).to_matrix())
        obj = bpy.data.objects.new('Joint_'+b, None)
        scene.collection.objects.link(obj)
        obj.matrix_world = Matrix((globals_[b] @ frame).tolist())
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.rigidbody.constraint_add()
        joint = obj.rigid_body_constraint
        joint.type = 'GENERIC_SPRING'
        joint.spring_type = 'SPRING2'
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
            expected = float(vec(definition, 'angularDamping')[i])
            if abs(getattr(joint, 'spring_damping_ang_'+axis) - expected) > max(.001, expected*.00001):
                raise ValueError('Preview solver clamps spring damping: '+str(expected))
        obj.select_set(False)
    frames, errors, positions, angles = {}, [], [], []
    worst_joint = None
    worst_error = -1.
    previous_values = None
    solver_errors, settled_errors = [], []
    dynamic = [n for n, d in definitions.items() if float(d.findtext('mass', '0')) > 0]
    for frame in range(1, args.frames+1):
        scene.frame_set(frame)
        graph = bpy.context.evaluated_depsgraph_get()
        values = {n: np.asarray(o.evaluated_get(graph).matrix_world) for n, o in bodies.items()}
        for constraint in constraints:
            a, b = constraint.attrib['bodyA'], constraint.attrib['bodyB']
            # Compare the shared rest-world pivot transformed with both bodies.
            pivot = (globals_[b] @ np.r_[vec(constraint.find('frameInB'), 'origin'), 1])[:3]
            rest_a = globals_[a] @ offsets[a]
            rest_b = globals_[b] @ offsets[b]
            pa = values[a] @ np.linalg.inv(rest_a) @ np.r_[pivot, 1]
            pb = values[b] @ np.linalg.inv(rest_b) @ np.r_[pivot, 1]
            error = float(np.linalg.norm(pa[:3]-pb[:3]))
            # Blender reports an animated kinematic pose at the frame boundary,
            # while Bullet integrates the intervening step. Bound anchor lag
            # by that anchor pivot's measured travel during one solver frame;
            # never discount errors between two dynamic bodies or at rest.
            travel = 0.
            if previous_values is not None and not float(definitions[a].findtext('mass', '0')):
                old_pa = previous_values[a] @ np.linalg.inv(rest_a) @ np.r_[pivot, 1]
                travel = float(np.linalg.norm(pa[:3]-old_pa[:3]))
            solver_errors.append(max(0., error-travel))
            if frame > args.frames-args.fps:
                settled_errors.append(error)
            if error > worst_error:
                worst_joint = (b, frame)
                worst_error = error
            errors.append(error)
        previous_values = values
        positions.append(np.array([values[n][:3, 3] for n in dynamic]))
        angles.append(np.array([values[n][:3, :3] for n in dynamic]))
        if frame in (1, 120, 180, 240, 360, 600, args.frames):
            frames[str(frame)] = {n: (values[n] @ np.linalg.inv(offsets[n]) @ np.linalg.inv(globals_[n])).tolist()
                                  for n in dynamic}
            print('Bullet frame', frame, 'max joint error', max(errors), flush=True)
    displacement = np.linalg.norm(positions[-1]-positions[0], axis=1)
    result = {'engine': 'Blender Bullet joint-only preview from delivered FSMP XML',
              'frames': frames, 'dynamic_bones': len(dynamic), 'max_joint_error': max(errors),
              'max_settle_speed': float(np.linalg.norm(positions[-1]-positions[-2], axis=1).max()*args.fps),
              'max_displacement': float(displacement.max()),
              'max_solver_joint_error': max(solver_errors),
              'max_settled_joint_error': max(settled_errors),
              'worst_joint': worst_joint,
              'fastest_bone': dynamic[int(np.argmax(np.linalg.norm(positions[-1]-positions[-2], axis=1)))],
              'gravity_game_units': GRAVITY, 'fps': args.fps, 'solver_iterations': 16, 'substeps_per_frame': substeps,
              'settled_rms_speed': float(np.sqrt(np.square(np.diff(positions[-args.fps:], axis=0)*args.fps).sum(axis=2).mean())),
              'settled_rms_rotation_change': float(np.sqrt(np.square(np.diff(angles[-args.fps:], axis=0)*args.fps).mean())),
              'limits': {'solver_joint_gap': 1., 'settled_joint_gap': .4, 'settling_speed': 1.},
              'mesh_contact_solver': 'FSMP runtime handles contacts; bone collisions disabled in this preview'}
    result['passed'] = bool(np.isfinite(displacement).all() and max(solver_errors) < 1. and
                            max(settled_errors) < .4 and
                            displacement.max() > 1 and result['max_settle_speed'] < 1.)
    (output/args.result).write_text(json.dumps(result, indent=2), encoding='utf8')
    print({key: value for key, value in result.items() if key != 'frames'}, flush=True)
    if not result['passed'] and not args.allow_failure:
        raise ValueError('Physics preview failed joint/gravity checks')


if __name__ == '__main__':
    main()
