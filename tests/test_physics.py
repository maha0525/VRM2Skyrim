"""Secondary-rig ownership and FSMP joint-frame contracts."""
from collections import Counter
import hashlib
import json
import math
import unittest
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

import numpy as np

from fsmp import (ARM_PROXY, SECONDARY_PROXY, SPRING_PROXY, TRIANGLE_MARGIN, GRAVITY, LINK, MASS, PROXY,
                  add_arm_collision_proxy, add_rigid_collision_proxy, borrowed_colliders, contact_patches,
                  add_collision_proxy, arm_cloth_bones, attach, build_physics, capsule_mesh, collider_depth,
                  contact_classes, contact_collider_groups, collider_groups, is_contact_patch, joint_profile, read_system,
                  local_points, protect_attachments, rest_spring, skin_samples, spring_joint, spring_mesh, system_xml,
                  contact_surface_points, validate_physics)
from custom_skeleton import NifFile, create_skeleton, matrix, rigid_buffer
from physics_rig import (blender_point, inertia_sphere_radius, inherited_spring, node_local_matrix, posed_point,
                         spring_tails,
                         node_world_matrices, plan_bones, posed_colliders, selected_meshes, spring_colliders,
                         spring_nodes, spring_settings, rotation_step_angles, unswayable_nodes)
from settings import FollowerSettings
from physics_frames import shift_frames, translation


class PhysicsTests(unittest.TestCase):
    def test_contact_uses_strong_real_surface_outside_body_instead_of_wrapped_centre(self):
        bone = {'dynamic': True, 'matrix': np.eye(4).tolist(), 'node_centre': [0, 0, 0]}
        hull = [[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
        points = contact_surface_points({'cloth': bone, 'helper': bone},
                                        {'cloth': [[0, 0, 0], [2, 0, 0], [10, 0, 0]]},
                                        {'cloth': [1, 1, .01]}, {'body': hull}, {'body': np.eye(4)})
        self.assertEqual(points, {'cloth': [2, 0, 0]})
        bone['node_centre'] = [3, 0, 0]
        preserved = contact_surface_points({'cloth': bone}, {'cloth': [[2, 0, 0], [4, 0, 0]]},
                                           {'cloth': [1, 1]}, {'body': hull}, {'body': np.eye(4)}, {'cloth'})
        self.assertEqual(preserved, {'cloth': [3, 0, 0]})

    def test_conversion_accepts_a_selection_remade_on_a_new_vrm(self):
        # Settings imported from another VRM keep its wardrobe fingerprint even after
        # the physics meshes are chosen again on this VRM.
        from unittest.mock import patch
        import converter
        report = {'sha256': 'f' * 64, 'parts': [{'node': 1}]}
        remade = FollowerSettings(physics_enabled=True, physics_nodes=[1], physics_source_sha256='f' * 64,
                                  appearance_source_sha256='a' * 64)
        with tempfile.TemporaryDirectory() as temp, patch.object(converter, 'inspect', return_value=report):
            self.assertIs(converter.prepare_source('avatar.vrm', Path(temp), remade), report)
            for stale in ({'physics_source_sha256': 'a' * 64}, {'physics_source_sha256': ''}):
                with self.subTest(**stale), self.assertRaisesRegex(ValueError, '別のVRM用'):
                    settings = FollowerSettings(physics_enabled=True, physics_nodes=[1],
                                                appearance_source_sha256='a' * 64, **stale)
                    converter.prepare_source('avatar.vrm', Path(temp), settings)

    def test_body_meshes_cannot_sway_only_while_the_body_is_cut(self):
        garment = {'id': 'robe', 'name': 'Robe', 'nodes': [3], 'slot': 32, 'armor_type': 'clothing',
                   'armor_rating': 0, 'weight': .5, 'value': 7, 'equipped': True}
        parts = {'body': [1, 2], 'underwear': [], 'fixed': [], 'garments': [garment]}
        values = dict(armor_support=True, appearance_source_sha256='a'*64, appearance_parts=parts)
        self.assertEqual(unswayable_nodes(FollowerSettings(**values)), {1, 2})
        head = {**garment, 'slot': 44}
        kept = FollowerSettings(**{**values, 'appearance_parts': {**parts, 'garments': [head]}})
        self.assertEqual(unswayable_nodes(kept), set())
        self.assertEqual(unswayable_nodes(FollowerSettings()), set())

    def test_default_off_and_setting_validation(self):
        self.assertFalse(FollowerSettings().physics_enabled)
        for values in ({'physics_enabled': 1}, {'physics_nodes': [True]},
                       {'physics_nodes': [1, 1]}, {'physics_stiffness': float('nan')},
                       {'physics_stiffness': 0}):
            with self.assertRaises(ValueError):
                FollowerSettings(**values)

    def test_preserve_chain_keep_humanoid_and_root_kinematic(self):
        parents = {'arm': None, 'root': 'arm', 'middle': 'root', 'end': 'middle'}
        plan = plan_bones(parents, {'arm': 'NPC Arm'}, {'sleeve': {'middle', 'end'}}, 'One')
        self.assertNotIn('arm', plan)
        self.assertFalse(plan['root']['dynamic'])
        self.assertTrue(plan['middle']['dynamic'])
        self.assertEqual(plan['end']['parent'], plan['middle']['name'])

    def test_rigid_accessory_not_simulated(self):
        self.assertEqual(plan_bones({'arm': None, 'ring': 'arm'}, {'arm': 'NPC Arm'},
                                    {'ring': {'ring'}}, 'One'), {})

    def test_body_or_unselected_mesh_influence_stays_kinematic(self):
        parents = {'head': None, 'root': 'head', 'end': 'root'}
        self.assertEqual(plan_bones(parents, {'head': 'NPC Head'}, {'hair': {'end'}},
                                    'One', fixed_bones={'end'}), {})

    def test_weighted_sleeve_root_is_retained_before_attachment_classification(self):
        parents = {'arm': None, 'sleeve': 'arm', 'tip': 'sleeve'}
        plan = plan_bones(parents, {'arm': 'NPC Arm'}, {'cloth': {'sleeve', 'tip'}},
                          'One', root_components={'cloth'})
        self.assertTrue(plan['sleeve']['dynamic'])
        self.assertEqual(plan['sleeve']['parent'], 'NPC Arm')

    def test_shared_bone_does_not_gain_two_dynamic_owners(self):
        parents = {'head': None, 'root': 'head', 'shared': 'root', 'a': 'shared', 'b': 'shared'}
        plan = plan_bones(parents, {'head': 'NPC Head'}, {'one': {'a'}, 'two': {'b'}}, 'One')
        self.assertFalse(plan['shared']['dynamic'])
        self.assertTrue(plan['a']['dynamic'])
        other = plan_bones(parents, {'head': 'NPC Head'}, {'one': {'a'}}, 'Two')
        self.assertTrue(set(i['name'] for i in plan.values()).isdisjoint(i['name'] for i in other.values()))

    def test_equipment_forks_shared_source_chains(self):
        parents = {'arm': None, 'root': 'arm', 'tip': 'root'}
        plans = [plan_bones(parents, {'arm': 'NPC Arm'}, {component: {'root', 'tip'}},
                            'SameMod|'+component, root_components={component})
                 for component in ('sleeve', 'coat')]
        self.assertTrue(all(plan['tip']['dynamic'] for plan in plans))
        self.assertTrue(set(i['name'] for i in plans[0].values()).isdisjoint(i['name'] for i in plans[1].values()))

    def test_source_spring_formats_and_explicit_mesh_validation(self):
        vrm1 = {'extensions': {'VRMC_springBone': {'springs': [{'joints': [{'node': 2}]}]}}}
        self.assertEqual(spring_nodes(vrm1), {'VRMNode_00002'})
        vrm0 = {'nodes': [{}, {'children': [2]}, {}], 'extensions': {'VRM': {
            'secondaryAnimation': {'boneGroups': [{'bones': [1]}]}}}}
        self.assertEqual(spring_nodes(vrm0), {'VRMNode_00001', 'VRMNode_00002'})
        with self.assertRaises(ValueError):
            selected_meshes(FollowerSettings(physics_nodes=[5]), {}, [1])

    def test_fsmp_converts_bone_frame_to_rigid_frame_once(self):
        value = np.eye(4)
        value[:3, 3] = [4, 5, 6]
        bones = {'root': {'parent': 'NPC Head', 'dynamic': False, 'matrix': value.tolist()},
                 'tip': {'parent': 'root', 'dynamic': True, 'matrix': value.tolist()}}
        root = system_xml(bones, {'tip': [[7, 9, 11]]}, {})
        com = root.find("bone[@name='tip']/centerOfMassTransform/origin").attrib
        pivot = root.find('generic-constraint/frameInB/origin').attrib
        # Runtime: worldBone * CoM * inverse(CoM) * boneLocalFrame.
        offset = np.eye(4)
        offset[:3, 3] = [float(com[a]) for a in 'xyz']
        frame = np.eye(4)
        frame[:3, 3] = [float(pivot[a]) for a in 'xyz']
        np.testing.assert_allclose(value @ offset @ np.linalg.inv(offset) @ frame, value)
        self.assertEqual(root.find("bone[@name='NPC Head']/mass").text, '0')
        np.testing.assert_allclose(local_points([[7, 9, 11]], value), [[3, 4, 5]])

    def test_long_horizontal_cloth_can_fall_but_not_spin(self):
        for com in ([20, 0, 0], [0, 20, 0], [0, 0, -20], [0, 0, 0]):
            basis, spring, damping = joint_profile(com, 3., np.eye(4))
            np.testing.assert_allclose(basis.T @ basis, np.eye(3), atol=1e-7)
            self.assertAlmostEqual(np.linalg.det(basis), 1.)
            self.assertTrue(np.isfinite(damping).all())
            self.assertTrue((spring > 0).all())
            if np.linalg.norm(com):
                np.testing.assert_allclose(basis[:, 2], np.asarray(com)/np.linalg.norm(com))
        _, spring, damping = joint_profile([20, 0, 0], 3., np.eye(4))
        inertia = .4 * MASS * 3**2 * 5 + MASS * 20**2
        ratio = damping[0] / (2*np.sqrt(inertia*(spring[0] + MASS*GRAVITY*20)))
        self.assertGreaterEqual(ratio, 1.)
        short = joint_profile([2, 0, 0], 3., np.eye(4))[2]
        self.assertGreater(damping[0], short[0]*10)

    def test_delivered_inertia_matches_runtime_and_preview_not_a_divisor(self):
        bones = {'long': {'parent': 'NPC Arm', 'dynamic': True, 'matrix': np.eye(4).tolist()},
                 'short': {'parent': 'NPC Head', 'dynamic': True, 'matrix': np.eye(4).tolist()}}
        xml = system_xml(bones, {'long': [[20, 0, 0]], 'short': [[2, 0, 0]]}, {})
        values = {}
        for name in bones:
            bone = xml.find(f"bone[@name='{name}']")
            mass = float(bone.findtext('mass'))
            values[name] = [float(bone.find('inertia').attrib[a]) for a in 'xyz']
            radius = inertia_sphere_radius(mass, values[name])
            # Bullet sphere's I = 2/5 mr². A unit torque has acceleration 1/I,
            # and must agree in the preview and FSMP's direct XML consumer.
            np.testing.assert_allclose([.4*mass*radius**2]*3, values[name])
        np.testing.assert_allclose(values['long'], [80.]*3)
        np.testing.assert_allclose(values['short'], [.8]*3)
        self.assertAlmostEqual((1/values['short'][0])/(1/values['long'][0]), 100.)
        for invalid in ([0, 0, 0], [-1, -1, -1], [1, 2, 1], [float('nan')]*3):
            with self.assertRaises(ValueError):
                inertia_sphere_radius(.1, invalid)

    def test_stationary_rounded_rotation_is_not_high_fps_twitching(self):
        rounded = np.diag([1., .9999999, 1.]).astype(np.float32)
        # acos(trace) alone incorrectly measures movement even against itself.
        false_speed = np.arccos((np.trace(rounded.T@rounded)-1)/2)*120
        self.assertGreater(false_speed, .05)
        np.testing.assert_array_equal(rotation_step_angles([rounded, rounded]), [0.])
        from scipy.spatial.transform import Rotation
        rotations = Rotation.from_euler('z', [0., 10., 30.], degrees=True).as_matrix()
        np.testing.assert_allclose(rotation_step_angles(rotations), np.radians([10., 20.]))

    def test_recentered_native_skin_matches_fsmp_contacts_after_rotation(self):
        from scipy.spatial.transform import Rotation
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'cloth.nif'
            original = np.eye(4)
            original[:3, :3] = Rotation.from_euler('xyz', [25, 45, 72], degrees=True).as_matrix()
            original[:3, 3] = [4, 6, 8]
            child = original @ translation([0, 0, 5])
            centre = np.array([2., 3., 4.])
            target = original @ translation(centre)
            verts = [(1., 2., 3.), (2., 3., 4.), (3., 4., 5.)]
            with NifFile() as nif:
                nif.initialize('SKYRIMSE', str(path))
                anchor = nif.add_node('NPC Anchor', rigid_buffer(np.eye(4)), nif.rootNode)
                parent = nif.add_node('V2SP_a', rigid_buffer(original), anchor)
                nif.add_node('V2SP_b', rigid_buffer(np.linalg.inv(original)@child), parent)
                shape = nif.createShapeFromData('Cloth', verts, [(0, 1, 2)], [(0., 0.)]*3, [(0., 0., 1.)]*3)
                shape.skin()
                shape.add_bone('V2SP_a', rigid_buffer(original), 'NPC Anchor')
                shape.set_global_to_skin(rigid_buffer(np.eye(4)))
                shape.set_skin_to_bone_xform('V2SP_a', rigid_buffer(np.linalg.inv(original)))
                shape.setShapeWeights('V2SP_a', [(0, 1.), (1, 1.), (2, 1.)])
                nif.save()
            self.assertEqual(shift_frames(path, {'V2SP_a': target, 'V2SP_b': child}), 1)
            self.assertEqual(shift_frames(path, {'V2SP_a': target, 'V2SP_b': child}), 0)
            packed = path.read_bytes()
            rounded = target.copy()
            rounded[0, 3] += .00005
            self.assertEqual(shift_frames(path, {'V2SP_a': rounded, 'V2SP_b': child}), 0)
            self.assertEqual(path.read_bytes(), packed)
            with NifFile(str(path)) as nif:
                shape = nif.shapes[0]
                np.testing.assert_array_equal(shape.verts, verts)
                np.testing.assert_allclose(matrix(nif.nodes['V2SP_b'].global_transform), child, atol=1e-5)
                bind = matrix(shape.get_shape_skin_to_bone('V2SP_a'))
                np.testing.assert_allclose(target@bind, np.eye(4), atol=1e-5)
                info = {'parent': 'NPC Anchor', 'dynamic': True, 'matrix': original.tolist(),
                        'centred_node': True, 'node_centre': centre.tolist()}
                sample = (original@np.r_[centre, 1])[:3].tolist()
                xml = system_xml({'V2SP_a': info}, {'V2SP_a': [sample]}, {})
                origin = xml.find("bone[@name='V2SP_a']/centerOfMassTransform/origin")
                offset = translation([float(origin.attrib[a]) for a in 'xyz'])
                pivot = xml.find('generic-constraint/frameInB/origin')
                frame = translation([float(pivot.attrib[a]) for a in 'xyz'])
                np.testing.assert_allclose((target@frame)[:3, 3], original[:3, 3], atol=1e-6)
                for yaw in (0, 90, 180):
                    actor = np.eye(4)
                    actor[:3, :3] = Rotation.from_euler('z', yaw, degrees=True).as_matrix()
                    actor[:3, 3] = [100, 200, 300]
                    # Both released runtime paths compose identity COM offsets.
                    rig = actor@target@offset
                    render = rig@np.linalg.inv(offset)@bind
                    contact = np.linalg.inv(offset)@rig@bind
                    np.testing.assert_allclose(contact, render, atol=1e-6)
                    np.testing.assert_allclose(render, actor, atol=1e-5)
                # Original physical pivot survives despite the shifted node.
                np.testing.assert_allclose(target@translation(-centre), original, atol=1e-6)

    def test_recenter_preserves_rounded_bind_rotation_and_scale(self):
        from pyn.structs import TransformBuf
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'rounded.nif'
            origin = translation([3, 4, 5])
            bind = TransformBuf()
            bind.store([-3, -4, -5], np.diag([1.00003, 1.00002, 1.00003]).tolist(), (.9, .9, .9))
            with NifFile() as nif:
                nif.initialize('SKYRIMSE', str(path))
                anchor = nif.add_node('NPC Anchor', rigid_buffer(np.eye(4)), nif.rootNode)
                nif.add_node('V2SP_a', rigid_buffer(origin), anchor)
                shape = nif.createShapeFromData('Cloth', [(0., 0., 0.), (1., 0., 0.), (0., 1., 0.)],
                                                [(0, 1, 2)], [(0., 0.)]*3, [(0., 0., 1.)]*3)
                shape.skin()
                shape.add_bone('V2SP_a', rigid_buffer(origin), 'NPC Anchor')
                shape.set_global_to_skin(rigid_buffer(np.eye(4)))
                shape.set_skin_to_bone_xform('V2SP_a', bind)
                shape.setShapeWeights('V2SP_a', [(0, 1.), (1, 1.), (2, 1.)])
                nif.save()
            with NifFile(str(path)) as nif:
                before = nif.shapes[0].get_shape_skin_to_bone('V2SP_a')
                rotation, scale = np.array(before.rotation), before.scale
                product = matrix(nif.nodes['V2SP_a'].global_transform) @ matrix(before)
            target = origin @ translation([2, 1, 3])
            self.assertEqual(shift_frames(path, {'V2SP_a': target}), 1)
            with NifFile(str(path)) as nif:
                after = nif.shapes[0].get_shape_skin_to_bone('V2SP_a')
                np.testing.assert_array_equal(after.rotation, rotation)
                self.assertEqual(after.scale, scale)
                np.testing.assert_allclose(matrix(nif.nodes['V2SP_a'].global_transform) @ matrix(after), product, atol=1e-5)
            packed = path.read_bytes()
            self.assertEqual(shift_frames(path, {'V2SP_a': target}), 0)
            self.assertEqual(path.read_bytes(), packed)
            changed = target.copy()
            changed[0, 0] = 1.1
            with self.assertRaisesRegex(ValueError, 'rotation/scale'):
                shift_frames(path, {'V2SP_a': changed})
            self.assertEqual(path.read_bytes(), packed)

    def test_distal_chain_does_not_overload_its_root(self):
        bones = {'a': {'parent': 'NPC Arm', 'dynamic': True, 'matrix': np.eye(4).tolist()},
                 'b': {'parent': 'a', 'dynamic': True, 'matrix': np.eye(4).tolist()}}
        root = system_xml(bones, {'a': [[10, 0, 0]], 'b': [[0, 2, 0]]}, {})
        self.assertGreater(float(root.find("bone[@name='a']/mass").text),
                           float(root.find("bone[@name='b']/mass").text))
        radius = float(root.find("bone[@name='a']/shape/radius").text)
        self.assertGreaterEqual(radius, 10.)
        joint = root.find('generic-constraint')
        limits = joint.find('angularUpperLimit').attrib
        self.assertGreater(float(limits['x']), np.pi/2)  # horizontal sleeve may drop
        self.assertLess(float(limits['y']), np.pi/2)  # Euler middle-axis singularity
        self.assertLess(float(limits['z']), .3)  # avoid free axial spin

    def test_garment_cuff_follows_arm_while_free_tail_keeps_physics(self):
        from itertools import product
        anchor = 'NPC L Forearm [LLar]'
        box = list(product((-1., 1.), (-1., 1.), (0., 20.)))
        globals_ = {anchor: np.eye(4)}
        def bone(parent, component='sleeve'):
            return {'parent': parent, 'dynamic': True, 'components': [component], 'matrix': np.eye(4).tolist()}
        bones = {'root': bone(anchor), 'cuff': bone('root'), 'tail': bone('cuff'),
                 'bridge': {**bone('tail'), 'dynamic': False},
                 'tip': bone('bridge'), 'hair': bone('NPC Head', 'hair')}
        samples = {'cuff': [[1.2, 0, 10], [1.3, 0, 11]], 'tail': [[10, 0, 15]],
                   'tip': [[1.1, 0, 10]]}
        result, protected = protect_attachments(bones, samples, {anchor: box}, globals_, {'sleeve'})
        self.assertFalse(result['root']['dynamic'])
        self.assertFalse(result['cuff']['dynamic'])
        self.assertTrue(result['tail']['dynamic'])
        self.assertTrue(result['tip']['dynamic'])  # also cannot freeze through a fixed helper below a mover
        self.assertTrue(result['hair']['dynamic'])
        self.assertTrue(bones['root']['dynamic'])  # do not mutate source rig metadata
        xml = system_xml(result, samples, {})
        self.assertEqual(xml.find("bone[@name='cuff']/mass").text, '0')
        self.assertFalse(any(j.attrib['bodyB'] in protected for j in xml.findall('generic-constraint')))

    def test_small_root_and_tip_stay_distinct_even_without_body_hulls(self):
        bones = {'root': {'parent': 'NPC Spine', 'dynamic': True, 'components': ['cape'], 'matrix': np.eye(4).tolist()},
                 'tip': {'parent': 'root', 'dynamic': True, 'components': ['cape'], 'matrix': np.eye(4).tolist()}}
        result, _ = protect_attachments(bones, {}, {}, {}, {'cape'})
        self.assertFalse(result['root']['dynamic'])
        self.assertTrue(result['tip']['dynamic'])

    def test_vrm_collider_spring_keeps_its_root_moving_like_vrm(self):
        cloth = {'parent': 'NPC Pelvis [Pelv]', 'dynamic': True, 'components': ['cloth'], 'matrix': np.eye(4).tolist()}
        spring = {'stiffness': 8, 'gravity': .1, 'hit_radius': .025, 'groups': [3]}
        bones = {'skirt': {**cloth, 'spring': spring},
                 'loop': {**cloth, 'spring': {**spring, 'groups': []}},
                 'apron': cloth,
                 'fold': {**cloth, 'borrowed': {'hit_radius': .025, 'groups': [3]}},
                 'sleeve': {**cloth, 'parent': 'NPC L UpperArm [LUar]', 'spring': spring}}
        result, protected = protect_attachments(bones, {}, {}, {}, {'cloth'})
        self.assertTrue(result['skirt']['dynamic'])
        self.assertTrue(result['fold']['dynamic'])  # borrowed colliders keep a fold off the legs
        self.assertEqual(set(protected), {'loop', 'apron', 'sleeve'})

    def test_cloth_outside_every_spring_borrows_the_nearest_chains_colliders(self):
        def bone(x, component='cloth', spring=None):
            value = np.eye(4)
            value[0, 3] = x
            return {'components': [component], 'matrix': value.tolist(), **({'spring': spring} if spring else {})}
        def spring(*groups):
            return {'stiffness': 8, 'gravity': .1, 'hit_radius': .025, 'groups': list(groups)}
        bones = {'skirt': bone(0, spring=spring(3)), 'ribbon': bone(10, spring=spring(2)),
                 'loop': bone(11, spring=spring()), 'apron': bone(2), 'hip': bone(9),
                 'hair': bone(0, 'hair'), 'strand': bone(1, 'hair', spring(0))}
        movers = list(bones)
        self.assertEqual(borrowed_colliders(bones, movers, {'cloth'}),
                         {'apron': {'hit_radius': .025, 'groups': [3]}, 'hip': {'hit_radius': .025, 'groups': [2]}})
        self.assertEqual(borrowed_colliders(bones, ['apron', 'loop'], {'cloth'}), {})

    def test_sleeve_contact_selection_uses_ancestry_and_excludes_hair_waist_shared_body(self):
        def bone(parent, component='cloth', dynamic=True):
            return {'parent': parent, 'components': [component], 'dynamic': dynamic}
        bones = {'cuff': bone('NPC L Forearm [LLar]', dynamic=False),
                 'sleeve': bone('cuff'), 'tip': bone('sleeve'),
                 'hair': bone('NPC Head [Head]', 'hair'),
                 'waist': bone('NPC Pelvis [Pelv]'),
                 'body': bone('NPC R Hand [RHnd]', 'body')}
        self.assertEqual(arm_cloth_bones(bones, {'cloth'}), {'sleeve', 'tip'})
        self.assertEqual(arm_cloth_bones(bones, {'cloth'}, [{'sleeve', 'waist', 'hair'}]),
                         {'sleeve', 'tip', 'waist'})
        bones['sleeve']['components'].append('body')
        self.assertEqual(arm_cloth_bones(bones, {'cloth'}), {'tip'})

    def test_sleeve_weighted_centre_does_not_give_distant_tiny_influence_equal_mass(self):
        bone = {'parent': 'NPC Arm', 'dynamic': True, 'matrix': np.eye(4).tolist()}
        root = system_xml({'sleeve': bone}, {'sleeve': [[1, 0, 0], [100, 0, 0]]}, {},
                          sample_weights={'sleeve': [1, .01]}, arm_contacts={'sleeve'})
        centre = root.find("bone[@name='sleeve']/centerOfMassTransform/origin")
        self.assertAlmostEqual(float(centre.attrib['x']), (1+1)/1.01, places=6)

    def test_mixed_visual_mesh_cannot_send_contact_back_to_sleeve_but_waist_is_retained(self):
        bones = {n: {'parent': 'NPC Arm', 'dynamic': True, 'matrix': np.eye(4).tolist()}
                 for n in ('sleeve', 'waist')}
        root = system_xml(bones, {'sleeve': [[1, 0, 0]], 'waist': [[0, 1, 0]]}, {'NPC Arm': []},
                          mesh_names=['mixed'], arm_contacts={'sleeve'})
        self.assertEqual(root.findtext("per-vertex-shape[@name='mixed']/weight-threshold[@bone='sleeve']"), '1')
        self.assertIsNone(root.find("per-vertex-shape[@name='mixed']/weight-threshold[@bone='waist']"))
        proxy = root.find(f"per-vertex-shape[@name='{ARM_PROXY}']")
        self.assertEqual(proxy.findtext('can-collide-with-tag'), 'V2SBody')
        self.assertEqual(proxy.findtext('margin'), '0.4')

    def test_hair_and_waist_contacts_are_rigid_and_exclude_visual_feedback(self):
        bones = {n: {'parent': 'NPC Head', 'dynamic': True, 'matrix': np.eye(4).tolist()}
                 for n in ('hair', 'waist')}
        root = system_xml(bones, {n: [[1, 0, 0], [100, 0, 0]] for n in bones}, {'NPC Head': []},
                          mesh_names=['mixed'], sample_weights={n: [1, .01] for n in bones},
                          secondary_contacts=set(bones))
        for name in bones:
            centre = root.find(f"bone[@name='{name}']/centerOfMassTransform/origin")
            self.assertAlmostEqual(float(centre.attrib['x']), 2/1.01, places=6)
            self.assertEqual(root.findtext(f"per-vertex-shape[@name='mixed']/weight-threshold[@bone='{name}']"), '1')
        proxy = root.find(f"per-vertex-shape[@name='{SECONDARY_PROXY}']")
        self.assertEqual(proxy.findtext('can-collide-with-tag'), 'V2SBody')
        self.assertIsNone(root.find(f"per-vertex-shape[@name='{ARM_PROXY}']"))

    def test_unweighted_chain_helper_keeps_joint_without_colliding_at_pivot(self):
        bones = {n: {'parent': 'NPC Arm', 'dynamic': True, 'matrix': np.eye(4).tolist()}
                 for n in ('helper', 'surface')}
        root = system_xml(bones, {'surface': [[0, 0, 1]]}, {'NPC Arm': []},
                          arm_contacts={'helper'}, secondary_contacts={'surface'}, noncontact_helpers={'helper'})
        self.assertIsNotNone(root.find("generic-constraint[@bodyB='helper']"))
        self.assertGreater(float(root.findtext("bone[@name='helper']/mass")), 0)
        self.assertEqual(root.findtext(f"per-vertex-shape[@name='{ARM_PROXY}']/weight-threshold[@bone='helper']"), '1')
        self.assertIsNone(root.find(f"per-vertex-shape[@name='{SECONDARY_PROXY}']/weight-threshold"))

    def test_native_sleeve_patch_single_owner_hidden_at_mass_centre_and_excluded_from_sampling(self):
        with tempfile.TemporaryDirectory() as directory:
            skeleton_path, mesh_path = [Path(directory)/n for n in ('skeleton.nif', 'sleeve.nif')]
            value = np.eye(4)
            value[:3, 3] = [10, 20, 30]
            for file in (skeleton_path, mesh_path):
                with NifFile() as nif:
                    nif.initialize('SKYRIMSE', str(file))
                    nif.add_node('Private Sleeve', rigid_buffer(value), nif.rootNode)
                    other = value.copy()
                    other[:3, 3] += [4, 5, 6]
                    nif.add_node('Private Other Sleeve', rigid_buffer(other), nif.rootNode)
                    nif.save()
            with NifFile(str(skeleton_path)) as skeleton, NifFile(str(mesh_path)) as nif:
                add_arm_collision_proxy(nif, skeleton, {'Private Sleeve', 'Private Other Sleeve'})
                nif.save()
            with NifFile(str(mesh_path)) as nif:
                proxy = next(s for s in nif.shapes if s.name == ARM_PROXY)
                self.assertTrue(proxy.properties.flags & 1)
                self.assertEqual(len(proxy.verts), 6)
                for name, position in (('Private Sleeve', value), ('Private Other Sleeve', other)):
                    pairs = proxy.bone_weights[name]
                    self.assertEqual(len(pairs), 3)
                    self.assertTrue(all(w == 1. for _, w in pairs))
                    np.testing.assert_allclose(position @ matrix(proxy.get_shape_skin_to_bone(name)), np.eye(4))
                    self.assertLess(np.max(np.linalg.norm(np.array(proxy.verts)[[i for i, _ in pairs]]-position[:3, 3], axis=1)), .002)
                self.assertEqual(skin_samples(nif), ({}, {}))
                with NifFile(str(skeleton_path)) as skeleton:
                    add_arm_collision_proxy(nif, skeleton, {'Private Sleeve', 'Private Other Sleeve'})
                nif.save()
            with NifFile(str(mesh_path)) as nif:
                self.assertEqual(len(nif.shapes), 1)

    def test_many_contact_owners_split_into_shapes_the_skin_can_address(self):
        # One shape addresses at most 256 bones; a hair rig with 582 movers once wrote
        # bones 256+ onto earlier ones. Each patch must stay on its own bone and point.
        from nif_limits import SHAPE_BONE_LIMIT
        names = [f'Private Hair {i:03}' for i in range(SHAPE_BONE_LIMIT*2 + 30)]
        positions = {name: [i, 2*i, 3*i] for i, name in enumerate(names)}
        with tempfile.TemporaryDirectory() as directory:
            skeleton_path, mesh_path = [Path(directory)/n for n in ('skeleton.nif', 'hair.nif')]
            for file in (skeleton_path, mesh_path):
                with NifFile() as nif:
                    nif.initialize('SKYRIMSE', str(file))
                    for name in names:
                        nif.add_node(name, rigid_buffer(np.eye(4)), nif.rootNode)
                    nif.save()
            with NifFile(str(skeleton_path)) as skeleton, NifFile(str(mesh_path)) as nif:
                add_rigid_collision_proxy(nif, skeleton, set(names), SECONDARY_PROXY, positions)
                nif.save()
            expected = contact_patches(SECONDARY_PROXY, names)
            self.assertEqual([n for n, _ in expected], [SECONDARY_PROXY, SECONDARY_PROXY+'_001', SECONDARY_PROXY+'_002'])
            with NifFile(str(mesh_path)) as nif:
                shapes = {s.name: s for s in nif.shapes}
                self.assertEqual(set(shapes), {n for n, _ in expected})
                for patch, owners in expected:
                    shape = shapes[patch]
                    self.assertTrue(shape.properties.flags & 1)
                    self.assertEqual(set(shape.bone_names), set(owners))
                    for name in owners:
                        pairs = shape.bone_weights[name]
                        self.assertEqual(len(pairs), 3)
                        self.assertLess(np.max(np.linalg.norm(np.array(shape.verts)[[i for i, _ in pairs]]-positions[name], axis=1)), .002)
                with NifFile(str(skeleton_path)) as skeleton:
                    add_rigid_collision_proxy(nif, skeleton, set(names), SECONDARY_PROXY, positions)
                self.assertEqual(len(nif.shapes), len(expected))
        bones = {n: {'parent': 'NPC Head', 'dynamic': True, 'matrix': np.eye(4).tolist()} for n in names}
        root = system_xml(bones, {n: [[1, 0, 0]] for n in names[1:]}, {'NPC Head': []},
                          secondary_contacts=set(names), noncontact_helpers={names[0], names[-1]})
        declared = {s.attrib['name']: {e.attrib['bone'] for e in s.findall('weight-threshold')}
                    for s in root.findall('per-vertex-shape')}
        self.assertEqual(declared, {expected[0][0]: {names[0]}, expected[1][0]: set(), expected[2][0]: {names[-1]}})

    def test_bone_names_survive_every_joined_length_around_the_reader_buffer(self):
        # PyNifly's 300-byte buffer cut the last character off a list of exactly that length.
        for extra in range(0, 12):
            names = [f'Private Bone {i:02} ' + 'x'*(20 + (extra if i == 0 else 0)) for i in range(8)]
            names[-1] += ']'
            with tempfile.TemporaryDirectory() as directory:
                skeleton_path, mesh_path = [Path(directory)/n for n in ('skeleton.nif', 'mesh.nif')]
                for file in (skeleton_path, mesh_path):
                    with NifFile() as nif:
                        nif.initialize('SKYRIMSE', str(file))
                        for name in names:
                            nif.add_node(name, rigid_buffer(np.eye(4)), nif.rootNode)
                        nif.save()
                with NifFile(str(skeleton_path)) as skeleton, NifFile(str(mesh_path)) as nif:
                    add_rigid_collision_proxy(nif, skeleton, set(names), SECONDARY_PROXY)
                    nif.save()
                with NifFile(str(mesh_path)) as nif:
                    self.assertEqual(sorted(nif.shapes[0].bone_names), sorted(names))

    def test_native_proxy_and_link_survive_save_and_rebuild(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target, mesh = [Path(directory)/n for n in ('stock.nif', 'skeleton.nif', 'cloth.nif')]
            with NifFile() as file:
                file.initialize('SKYRIMSE', str(source))
                file.add_node('NPC Anchor', rigid_buffer(np.eye(4)), file.rootNode)
                file.save()
            pose = np.eye(4)
            pose[:3, 3] = [3, 4, 5]
            create_skeleton(source, target, {}, {'Private': {'parent': 'NPC Anchor', 'matrix': pose.tolist()}})
            with NifFile(str(target)) as skeleton, NifFile() as nif:
                nif.initialize('SKYRIMSE', str(mesh))
                hulls = {'NPC Anchor': [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]}
                add_collision_proxy(nif, skeleton, hulls)
                attach(nif, 'SKSE\\Plugins\\private.xml')
            with NifFile(str(mesh)) as nif:
                proxy = next(s for s in nif.shapes if s.name == PROXY)
                self.assertEqual(proxy.properties.flags & 1, 1)
                self.assertEqual(len(proxy.tris), 4)
                self.assertEqual(set(proxy.bone_names), {'NPC Anchor'})
                np.testing.assert_allclose(matrix(proxy.get_shape_skin_to_bone('NPC Anchor')), np.eye(4))
                with NifFile(str(target)) as skeleton:
                    add_collision_proxy(nif, skeleton, hulls)
                attach(nif, 'SKSE\\Plugins\\private.xml')
            with NifFile(str(mesh)) as nif:
                self.assertEqual(len([s for s in nif.shapes if s.name == PROXY]), 1)
                self.assertEqual(len(list(nif.rootNode.extra_data(name=LINK))), 1)


class SpringReaderTests(unittest.TestCase):
    def test_vrm1_joints_defaults_and_collider_shapes(self):
        document = {'extensions': {'VRMC_springBone': {
            'colliders': [{'node': 7, 'shape': {'sphere': {'offset': [0, .1, 0], 'radius': .09}}},
                          {'node': 8, 'shape': {'capsule': {'offset': [1, 2, 3], 'tail': [4, 5, 6], 'radius': .12}}},
                          {'node': 9, 'shape': {'sphere': {}}}],
            'colliderGroups': [{'colliders': [0]}, {'colliders': [1, 2]}],
            'springs': [{'colliderGroups': [1, 0], 'joints': [
                {'node': 2, 'stiffness': 8, 'gravityPower': .12, 'hitRadius': .025}, {'node': 3}]}]}}}
        self.assertEqual(spring_settings(document), {
            'VRMNode_00002': {'stiffness': 8., 'gravity': .12, 'hit_radius': .025, 'groups': [0, 1]},
            'VRMNode_00003': {'stiffness': 1., 'gravity': 0., 'hit_radius': 0., 'groups': [0, 1]}})
        self.assertEqual(spring_colliders(document), {
            0: [{'node': 7, 'head': [0., .1, 0.], 'tail': None, 'radius': .09}],
            1: [{'node': 8, 'head': [1., 2., 3.], 'tail': [4., 5., 6.], 'radius': .12},
                {'node': 9, 'head': [0., 0., 0.], 'tail': None, 'radius': 0.}]})

    def test_vrm0_groups_reach_descendants_and_keep_the_spec_spelling(self):
        document = {'nodes': [{}, {'children': [2]}, {'children': [3]}, {}, {}], 'extensions': {'VRM': {
            'secondaryAnimation': {
                'boneGroups': [{'bones': [1], 'stiffiness': .5, 'gravityPower': .2, 'hitRadius': .01,
                                'colliderGroups': [1]}, {'bones': [2, 4]}],
                'colliderGroups': [{'node': 5, 'colliders': []}, {'node': 6, 'colliders': [
                    {'offset': {'x': -.1, 'y': .2, 'z': .3}, 'radius': .4}, {}]}]}}}}
        settings = spring_settings(document)
        self.assertEqual(set(settings), spring_nodes(document))
        cloth = {'stiffness': .5, 'gravity': .2, 'hit_radius': .01, 'groups': [1]}
        for name in ('VRMNode_00001', 'VRMNode_00002', 'VRMNode_00003'):
            self.assertEqual(settings[name], cloth)
        self.assertEqual(settings['VRMNode_00004'], {'stiffness': 1., 'gravity': 0., 'hit_radius': 0., 'groups': []})
        # Measured on AnimalKawaii_01_Kuro.vrm: x unchanged, z negated; see spring_colliders.
        self.assertEqual(spring_colliders(document), {1: [
            {'node': 6, 'head': [-.1, .2, -.3], 'tail': None, 'radius': .4},
            {'node': 6, 'head': [0., 0., 0.], 'tail': None, 'radius': 0.}]})

    def test_model_without_springs_reads_empty(self):
        self.assertEqual(spring_settings({'nodes': [{}]}), {})
        self.assertEqual(spring_colliders({'nodes': [{}]}), {})
        self.assertEqual(spring_tails({'nodes': [{}]}, {0: np.eye(4)}), {})

    def test_vrm1_tail_is_the_next_listed_joint(self):
        document = {'nodes': [{'translation': [0, 1, 0], 'children': [1]}, {'translation': [0, -.2, 0], 'children': [2]},
                              {'translation': [0, -.3, 0], 'children': [3]}, {'translation': [0, -.1, 0]}],
                    'extensions': {'VRMC_springBone': {'springs': [{'joints': [{'node': 1}, {'node': 2}]},
                                                                  {'joints': [{'node': 2}, {'node': 3}]}]}}}
        worlds = node_world_matrices(document)
        tails = spring_tails(document, worlds)
        self.assertEqual(set(tails), {'VRMNode_00001', 'VRMNode_00002'})
        np.testing.assert_allclose(tails['VRMNode_00001'], worlds[2][:3, 3])
        np.testing.assert_allclose(tails['VRMNode_00002'], worlds[3][:3, 3])

    def test_vrm0_tail_is_the_first_child_or_seven_centimetres_past_a_leaf(self):
        document = {'nodes': [{'translation': [0, 1, 0], 'children': [1, 3]}, {'translation': [0, -.2, 0], 'children': [2]},
                              {'translation': [0, -.3, 0]}, {'translation': [.1, 0, 0]}],
                    'extensions': {'VRM': {'secondaryAnimation': {'boneGroups': [{'bones': [0]}]}}}}
        worlds = node_world_matrices(document)
        tails = spring_tails(document, worlds)
        np.testing.assert_allclose(tails['VRMNode_00000'], worlds[1][:3, 3])
        np.testing.assert_allclose(tails['VRMNode_00001'], worlds[2][:3, 3])
        np.testing.assert_allclose(tails['VRMNode_00002'], worlds[2][:3, 3]+[0, -.07, 0])
        np.testing.assert_allclose(tails['VRMNode_00003'], worlds[3][:3, 3]+[.07, 0, 0])

    def test_tail_is_posed_by_the_bone_that_carries_it(self):
        orient = np.diag([-70., -70., 70., 1.])
        moved = np.eye(4)
        moved[:3, 3] = [1, 2, 3]
        np.testing.assert_allclose(posed_point(moved, orient, [.1, .5, 0]), [-7+1, 0+2, 35+3])

    def test_spring_settings_inherit_from_the_nearest_ancestor(self):
        parents = {'tip': 'middle', 'middle': 'root', 'root': 'hips', 'hips': None, 'other': 'hips'}
        near, far = {'stiffness': 1}, {'stiffness': 2}
        settings = {'middle': near, 'root': far}
        self.assertIs(inherited_spring('tip', parents, settings), near)
        self.assertIs(inherited_spring('root', parents, settings), far)
        self.assertIsNone(inherited_spring('other', parents, settings))

    def test_node_matrices_follow_gltf_conventions(self):
        from scipy.spatial.transform import Rotation
        rotation = Rotation.from_euler('xyz', [10, 20, 30], degrees=True)
        node = {'translation': [1, 2, 3], 'rotation': rotation.as_quat().tolist(), 'scale': [2, 2, 2]}
        value = node_local_matrix(node)
        np.testing.assert_allclose(value[:3, :3], rotation.as_matrix()*2)
        np.testing.assert_allclose(node_local_matrix({'matrix': value.T.reshape(-1).tolist()}), value)
        worlds = node_world_matrices({'nodes': [{'translation': [0, 1, 0], 'children': [1]}, node]})
        np.testing.assert_allclose(worlds[1], worlds[0] @ value)
        np.testing.assert_allclose(worlds[0][:3, 3], [0, 1, 0])

    def test_colliders_reach_the_custom_pose_through_the_mesh_transform(self):
        # glTF Y-up: hips one metre up, so Blender (x, -z, y) puts them on +Z.
        np.testing.assert_allclose(blender_point([0, 1, 0]), [0, 0, 1])
        orient = np.diag([-70., -70., 70., 1.])
        document = {'nodes': [{'translation': [0, 1, 0], 'children': [1]},
                              {'translation': [.1, -.5, 0], 'children': [2]}, {'translation': [0, -.1, 0]}]}
        worlds = node_world_matrices(document)
        arm = np.eye(4)
        arm[:3, 3] = [1, 2, 3]
        transforms = {'VRMNode_00000': np.eye(4), 'VRMNode_00001': arm}
        placed = posed_colliders({2: [{'node': 2, 'head': [0, 0, .01], 'tail': None, 'radius': .1}],
                                  4: [{'node': 0, 'head': [0, 0, 0], 'tail': [0, .1, 0], 'radius': .2},
                                      {'node': 9, 'head': [0, 0, 0], 'tail': None, 'radius': .3}]},
                                 {**worlds, 9: worlds[0]}, {1: 0, 2: 1}, set(transforms), transforms, orient,
                                 {'VRMNode_00000': 'NPC Pelvis', 'VRMNode_00001': 'NPC Thigh'}, 'VRMNode_00000')
        # Node 2 is no skin bone: its nearest ancestor owns the pose and the NPC anchor.
        self.assertEqual([c['bone'] for c in placed], ['NPC Thigh', 'NPC Pelvis', 'NPC Pelvis'])
        np.testing.assert_allclose(placed[0]['head'], [-7+1, .7+2, 28+3])
        self.assertIsNone(placed[0]['tail'])
        self.assertAlmostEqual(placed[0]['radius'], 7.)
        np.testing.assert_allclose(placed[1]['head'], [0, 0, 70])
        np.testing.assert_allclose(placed[1]['tail'], [0, 0, 77])
        json.dumps(placed)


class SpringJointTests(unittest.TestCase):
    @staticmethod
    def joint(tilt, spring, stiffness=1., length=10.):
        """A mover whose com sits tilt radians from straight down."""
        com = [length*math.sin(tilt), 0, -length*math.cos(tilt)]
        bones = {'cloth': {'parent': 'NPC Pelvis', 'dynamic': True, 'matrix': np.eye(4).tolist(), 'spring': spring}}
        root = system_xml(bones, {'cloth': [com]}, {}, stiffness)
        k = float(root.find('generic-constraint/angularStiffness').attrib['x'])
        return root, k, float(root.findtext("bone[@name='cloth']/gravity-factor"))

    def test_static_droop_equals_vrm_for_every_tilt_and_preset(self):
        for stiffness, gravity in ((8, .12), (2.5, .08), (1, .1)):
            spring = {'stiffness': stiffness, 'gravity': gravity, 'hit_radius': 0, 'groups': []}
            for degrees in (20, 45, 90, 135):
                tilt = math.radians(degrees)
                vrm = math.atan2(gravity*math.sin(tilt), stiffness+gravity*math.cos(tilt))
                for preset in (.3, 1., 3.):
                    _, k, factor = self.joint(tilt, spring, preset)
                    self.assertLess(factor, 1)
                    self.assertGreater(factor, 0)
                    low, high = 0., tilt  # k*a = factor*m*G*L*sin(tilt-a)
                    for _ in range(60):
                        droop = (low+high)/2
                        if k*droop < factor*MASS*GRAVITY*10*math.sin(tilt-droop):
                            low = droop
                        else:
                            high = droop
                    self.assertAlmostEqual(droop, vrm, delta=max(.002, vrm*.01))

    def test_preset_changes_the_speed_but_not_the_droop(self):
        spring = {'stiffness': 8, 'gravity': .12, 'hit_radius': 0, 'groups': []}
        (_, soft, soft_factor), (_, firm, firm_factor) = [self.joint(1., spring, s) for s in (.3, 3.)]
        self.assertGreater(firm, soft)
        self.assertGreater(firm_factor, soft_factor)
        self.assertAlmostEqual((firm/firm_factor)/(soft/soft_factor), 1., places=5)

    def test_vrm_movers_restore_as_fast_as_movers_without_settings(self):
        # Their restoring torque is the preset spring plus full gravity, split by VRM's ratio.
        for stiffness, gravity in ((8, .12), (2.2, .01), (2, 0)):
            spring = {'stiffness': stiffness, 'gravity': gravity, 'hit_radius': 0, 'groups': []}
            for preset in (.3, 1., 3.):
                root, k, factor = self.joint(1., spring, preset)
                radius = float(root.findtext("bone[@name='cloth']/shape/radius"))
                plain = rest_spring(radius, preset, MASS) + MASS*GRAVITY*10
                self.assertAlmostEqual((k + factor*MASS*GRAVITY*10)/plain, 1., places=5)

    def test_damping_uses_the_scaled_gravity(self):
        spring = {'stiffness': 8, 'gravity': .12, 'hit_radius': 0, 'groups': []}
        root, _, factor = self.joint(1., spring)
        com = [10*math.sin(1.), 0, -10*math.cos(1.)]
        radius = float(root.findtext("bone[@name='cloth']/shape/radius"))
        joint = root.find('generic-constraint/angularDamping').attrib
        multiplier, _ = spring_joint(spring, 1., radius, MASS, 10.)
        expected = joint_profile(com, radius, np.eye(4), multiplier, MASS, factor)[2]
        np.testing.assert_allclose([float(joint[a]) for a in 'xyz'], expected, atol=1e-6)
        self.assertLess(expected[0], joint_profile(com, radius, np.eye(4), multiplier, MASS)[2][0])

    def test_factor_limits(self):
        def joint(stiffness, gravity, length=10.):
            return spring_joint({'stiffness': stiffness, 'gravity': gravity}, 1., 10., MASS, length)
        self.assertEqual(joint(0, .5), (0., 1.))  # no restoring term: VRM hangs straight down
        self.assertEqual(joint(8, 0)[1], 0)
        multiplier, factor = joint(.001, 100)  # gravity capped at 1, the spring keeps the droop
        self.assertEqual(factor, 1.)
        self.assertAlmostEqual(multiplier*rest_spring(10., 1., MASS), MASS*GRAVITY*10/1e5)
        self.assertEqual(joint(8, .1, 0.), (1., 1.))  # no lever, no gravity torque to scale

    def test_movers_without_spring_keep_the_exact_xml(self):
        # Hash of this input's XML from system_xml before VRM spring settings existed.
        value = np.eye(4)
        value[:3, 3] = [1, 2, 3]
        bones = {'root': {'parent': 'NPC Head', 'dynamic': False, 'matrix': value.tolist()},
                 'sleeve': {'parent': 'root', 'dynamic': True, 'matrix': value.tolist()},
                 'hair': {'parent': 'sleeve', 'dynamic': True, 'matrix': value.tolist()},
                 'helper': {'parent': 'hair', 'dynamic': True, 'matrix': value.tolist()}}
        root = system_xml(bones, {'sleeve': [[3, 2, 9], [4, 3, 8]], 'hair': [[1, 7, 3]]},
                          {'NPC Head': [[0, 0, 0]]}, 1.5, (), 'V2SBody_x', {'sleeve': [1, .5], 'hair': [1]},
                          {'sleeve'}, {'hair', 'helper'}, {'helper'})
        self.assertEqual(hashlib.sha256(ET.tostring(root)).hexdigest(),
                         '181892a93b1ae3a5b55f9af8ae4b9b5a8745183327e1c46f4ca8cb2de2b01b30')


class SpringContactTests(unittest.TestCase):
    def assert_closed_outward(self, vertices, triangles):
        vertices = np.asarray(vertices)
        directed = Counter((t[i], t[(i+1) % 3]) for t in triangles for i in range(3))
        self.assertEqual(set(directed.values()), {1})
        self.assertTrue(all((b, a) in directed for a, b in directed))  # closed, consistently wound
        self.assertEqual(len(vertices)-len(directed)//2+len(triangles), 2)
        centre = vertices.mean(axis=0)
        cells = vertices[np.asarray(triangles)]-centre
        return float(np.einsum('ij,ij->i', cells[:, 0], np.cross(cells[:, 1], cells[:, 2])).sum())/6

    def test_capsule_and_sphere_are_closed_and_outward(self):
        head, tail = np.array([1., 2., 3.]), np.array([4., 2., 9.])
        for start, end in ((head, tail), (tail, head), ([0, 0, 0], [0, 0, 5]), ([0, 0, 5], [5, 0, 0])):
            vertices, triangles = capsule_mesh(start, end, 2.)
            volume = self.assert_closed_outward(vertices, triangles)
            length = np.linalg.norm(np.subtract(end, start))
            self.assertAlmostEqual(volume, math.pi*4*length + 4/3*math.pi*8, delta=volume*.15)
        vertices, triangles = capsule_mesh(head, None, 2.)
        volume = self.assert_closed_outward(vertices, triangles)
        self.assertAlmostEqual(volume, 4/3*math.pi*8, delta=volume*.2)
        np.testing.assert_allclose(np.linalg.norm(vertices-head, axis=1), 2.)
        self.assert_closed_outward(*capsule_mesh(head, head, 2.))

    def test_collider_mesh_skin_is_rigid_and_keeps_the_triangle_margin(self):
        colliders = [{'bone': 'NPC L', 'head': [0, 0, 0], 'tail': [0, 0, 9], 'radius': 8.4},
                     {'bone': 'NPC R', 'head': [20, 0, 0], 'tail': None, 'radius': .2},
                     {'bone': 'NPC L', 'head': [0, 20, 0], 'tail': None, 'radius': 1.}]
        vertices, triangles, weights = spring_mesh(colliders)
        self.assertEqual(set(weights), {'NPC L', 'NPC R'})
        pairs = [pair for values in weights.values() for pair in values]
        self.assertEqual(sorted(index for index, _ in pairs), list(range(len(vertices))))
        self.assertTrue(all(weight == 1. for _, weight in pairs))
        self.assertEqual({v for t in triangles for v in t}, set(range(len(vertices))))
        points = np.asarray(vertices)
        rights = points[[i for i, _ in weights['NPC R']]]
        np.testing.assert_allclose(np.linalg.norm(rights-[20, 0, 0], axis=1), .1)  # floor
        self.assertAlmostEqual(float(points[:, 2].max()), 9+8.4-TRIANGLE_MARGIN)

    def test_patches_partition_by_margin_and_groups_then_by_bone_limit(self):
        from nif_limits import SHAPE_BONE_LIMIT
        def spring(hit, *groups):
            return {'stiffness': 1, 'gravity': 0, 'hit_radius': hit, 'groups': list(groups)}
        bones = {'plain': {}, 'thin': {'spring': spring(.001)}, 'helper': {'spring': spring(.1, 3)}}
        bones.update({f'skirt{i:03}': {'spring': spring(.025, 3)} for i in range(SHAPE_BONE_LIMIT+1)})
        bones['hair'] = {'spring': spring(.025, 0, 1)}
        bones['dropped'] = {'spring': spring(.025, 3)}
        groups = {'hair': (0, 1), 'dropped': (), 'helper': (3,), **{n: (3,) for n in bones if n.startswith('skirt')}}
        classes = contact_classes(SECONDARY_PROXY, bones, bones, groups, {'helper'})
        base = SECONDARY_PROXY
        self.assertEqual([c[:3] for c in classes], [(base, .4, ()), (base+'_S1', 1.75, ()), (base+'_S2', 1.75, (0, 1)),
                                                    (base+'_S3', 1.75, (3,))])
        self.assertEqual(classes[0][3], ['helper', 'plain', 'thin'])
        self.assertEqual(classes[1][3], ['dropped'])
        self.assertEqual(sorted(n for c in classes for n in c[3]), sorted(bones))
        skirt = contact_patches(classes[3][0], classes[3][3])
        self.assertEqual([n for n, _ in skirt], [base+'_S3', base+'_S3_001'])
        self.assertTrue(is_contact_patch(base+'_001', base))
        self.assertFalse(is_contact_patch(base+'_S3', base))  # each class owns its own chunks

    def test_rest_point_inside_a_collider_drops_only_that_group(self):
        bones = {'hem': {'spring': {'hit_radius': .025, 'groups': [1, 2, 9]}}, 'plain': {}}
        groups = collider_groups([
            {'group': 1, 'bone': 'NPC', 'head': [0, 0, 0], 'tail': [0, 0, 10], 'radius': 8.4},
            {'group': 2, 'bone': 'NPC', 'head': [0, 0, 0], 'tail': None, 'radius': 2.}])
        def result(point):
            return contact_collider_groups(bones, {'hem': point, 'plain': point}, groups)
        self.assertEqual(result([10.1, 0, 5]), ({'hem': [2]}, {'hem': [1]}))  # 8.4+1.75 reaches past the point
        self.assertEqual(result([10.2, 0, 5]), ({'hem': [1, 2]}, {}))
        self.assertEqual(result([0, 0, -10.2]), ({'hem': [1, 2]}, {}))  # beyond the capsule end
        self.assertEqual(result([0, 0, 0]), ({}, {'hem': [1, 2]}))

    def test_contact_clearance_covers_each_bones_margin(self):
        hull = [[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
        def bone(hit):
            spring = {'hit_radius': hit, 'groups': []} if hit else None
            return {'dynamic': True, 'matrix': np.eye(4).tolist(), 'node_centre': [0, 0, 0],
                    **({'spring': spring} if spring else {})}
        samples = {'cloth': [[1.9, 0, 0], [3.4, 0, 0]]}
        weights = {'cloth': [1, 1]}
        plain = contact_surface_points({'cloth': bone(0)}, samples, weights, {'body': hull}, {'body': np.eye(4)})
        wide = contact_surface_points({'cloth': bone(.025)}, samples, weights, {'body': hull}, {'body': np.eye(4)})
        self.assertEqual(plain, {'cloth': [1.9, 0, 0]})  # .9 clears .4+.35+.05
        self.assertEqual(wide, {'cloth': [3.4, 0, 0]})  # .9 does not clear 1.75+.35+.05

    def test_contact_sits_at_the_vrm_tail_unless_it_starts_inside_the_body(self):
        hull = [[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
        samples = {'cloth': [[3.4, 0, 0]]}
        weights = {'cloth': [1]}
        def point(tail, *groups):
            spring = {'hit_radius': .025, 'groups': list(groups)}
            bone = {'dynamic': True, 'matrix': np.eye(4).tolist(), 'node_centre': [0, 0, 0],
                    'spring': spring, 'spring_tail': tail}
            return contact_surface_points({'cloth': bone}, samples, weights, {'body': hull},
                                          {'body': np.eye(4)})['cloth']
        self.assertEqual(point([9., 0., 0.], 3), [9., 0., 0.])
        self.assertEqual(point([1.5, 0., 0.], 3), [3.4, 0, 0])  # inside the body's clearance
        self.assertEqual(point([9., 0., 0.]), [3.4, 0, 0])  # VRM tests nothing for this spring

    def test_collider_depth_stops_at_the_thinnest_surface_radius(self):
        def group(*radii):
            return [{'radius': r} for r in radii]
        self.assertEqual(collider_depth(group(6.3)), 5.95)
        self.assertEqual(collider_depth(group(8.4, 5.6)), 5.25)
        self.assertEqual(collider_depth(group(8.4, 6.65, 4.55)), 4.2)  # the foot's surface radius
        self.assertEqual(collider_depth(group(.2)), 1.)  # never thinner than FSMP's default

    def test_xml_tags_and_margins_for_collider_groups(self):
        spring = {'stiffness': 8, 'gravity': .1, 'hit_radius': .025, 'groups': [1, 3]}
        bones = {'plain': {'parent': 'NPC Pelvis', 'dynamic': True, 'matrix': np.eye(4).tolist()},
                 'hem': {'parent': 'NPC Pelvis', 'dynamic': True, 'matrix': np.eye(4).tolist(), 'spring': spring}}
        root = system_xml(bones, {n: [[5, 0, 0]] for n in bones}, {'NPC Pelvis': [[0, 0, 0]]},
                          collision_tag='T', secondary_contacts=set(bones), contact_groups={'hem': [1, 3]},
                          collider_bones={'NPC L Thigh'})
        self.assertEqual(root.findtext("bone[@name='NPC L Thigh']/mass"), '0')
        tags = {s.attrib['name']: (s.findtext('margin'), s.findtext('tag'),
                                   [e.text for e in s.findall('no-collide-with-tag')])
                for s in root.findall('per-triangle-shape')}
        generated = ['T', 'T_g1', 'T_g3']
        self.assertEqual(tags, {PROXY: ('0.35', 'T', generated), SPRING_PROXY+'1': ('0.35', 'T_g1', generated),
                                SPRING_PROXY+'3': ('0.35', 'T_g3', generated)})
        patches = {s.attrib['name']: (s.findtext('margin'), [e.text for e in s.findall('can-collide-with-tag')])
                   for s in root.findall('per-vertex-shape')}
        self.assertEqual(patches, {SECONDARY_PROXY: ('0.4', ['T']),
                                   SECONDARY_PROXY+'_S1': ('1.75', ['T', 'T_g1', 'T_g3'])})


class SpringBuildTests(unittest.TestCase):
    """build_physics and validate_physics on real NIF files, one cloth chain at x=20."""
    PELVIS, THIGH = 'NPC Pelvis [Pelv]', 'NPC L Thigh [LThg]'
    TEXTURE = 'textures/spring/flat_n.dds'

    def fixture(self, output, springs, colliders, body_role='body', tails=None):
        settings = FollowerSettings(physics_enabled=True, mod_id='SpringTest')
        settings.save(output/'settings.json')
        mesh_dir = output/'mod/meshes'/settings.asset_dir
        mesh_dir.mkdir(parents=True)
        (output/'mod'/self.TEXTURE).parent.mkdir(parents=True)
        (output/'mod'/self.TEXTURE).write_bytes(b'')
        chain = {'V2SP_root': (self.PELVIS, 60), 'V2SP_a': ('V2SP_root', 50), 'V2SP_b': ('V2SP_a', 40),
                 'V2SP_c': ('V2SP_b', 30)}
        poses = {self.PELVIS: np.eye(4), self.THIGH: translation([5, 0, 40]),
                 **{n: translation([20, 0, z]) for n, (_, z) in chain.items()}}
        parents = {self.THIGH: self.PELVIS, **{n: p for n, (p, _) in chain.items()}}
        for path in (mesh_dir/'skeleton.nif', mesh_dir/'avatar.nif'):
            with NifFile() as nif:
                nif.initialize('SKYRIMSE', str(path))
                nodes = {}
                for name, pose in poses.items():
                    parent = parents.get(name)
                    local = np.linalg.inv(poses[parent]) @ pose if parent else pose
                    nodes[name] = nif.add_node(name, rigid_buffer(local), nodes[parent] if parent else nif.rootNode)
                if path.name == 'avatar.nif':
                    body = [(float(x), float(y), float(z)) for x in (-6, 6) for y in (-6, 6) for z in (30, 60)]
                    self.skinned(nif, 'VRMNode_00001', body, [(0, 1, 2), (1, 3, 2), (4, 6, 5), (5, 6, 7),
                                                              (0, 4, 1), (1, 4, 5), (2, 3, 6), (3, 7, 6),
                                                              (0, 2, 4), (2, 6, 4), (1, 5, 3), (3, 5, 7)],
                                 {self.PELVIS: range(8)}, poses, parents)
                    cloth, weights = [], {}
                    for name, (_, z) in chain.items():
                        weights[name] = range(len(cloth), len(cloth)+3)
                        cloth += [(20., -1., z-5.), (20., 1., z-5.), (20., 0., z-4.)]
                    self.skinned(nif, 'VRMNode_00002', cloth, [(i, i+1, i+2) for i in range(0, len(cloth), 3)],
                                 weights, poses, parents)
                nif.save()
        report = {n: {'name': n, 'parent': p, 'dynamic': True, 'components': ['appearance_cloth'],
                      'matrix': poses[n].tolist(), **({'spring': springs[n]} if n in springs else {}),
                      **({'spring_tail': tails[n]} if tails and n in tails else {})}
                  for n, (p, _) in chain.items()}
        for name, value in (('skeleton.json', {'physics_bones': report}),
                            ('appearance.json', {'components': [{'id': 'appearance', 'role': 'body', 'file': 'avatar.nif'}]}),
                            ('source.json', {'parts': [{'node': 1, 'name': 'Body', 'suggested_role': body_role}]}),
                            ('spring-colliders.json', colliders)):
            (output/name).write_text(json.dumps(value), encoding='utf8')
        return mesh_dir, settings

    def skinned(self, nif, name, vertices, triangles, weights, poses, parents):
        shape = nif.createShapeFromData(name, vertices, triangles, [(0., 0.)]*len(vertices),
                                        [(0., 0., 1.)]*len(vertices))
        shape.set_texture('Diffuse', self.TEXTURE)
        shape.set_texture('Normal', self.TEXTURE)
        shape.skin()
        for bone in weights:
            shape.add_bone(bone, rigid_buffer(poses[bone]), parents.get(bone))
        shape.set_global_to_skin(rigid_buffer(np.eye(4)))
        for bone, indices in weights.items():
            shape.set_skin_to_bone_xform(bone, rigid_buffer(np.linalg.inv(poses[bone])))
            shape.setShapeWeights(bone, [(int(i), 1.) for i in indices])

    def springs(self):
        spring = {'stiffness': 8., 'gravity': .12, 'hit_radius': .025, 'groups': [3, 5]}
        return {n: spring for n in ('V2SP_root', 'V2SP_a', 'V2SP_b')}

    def colliders(self):
        return [{'group': 3, 'bone': self.THIGH, 'head': [20, 0, 28], 'tail': None, 'radius': 6.5},
                {'group': 5, 'bone': self.THIGH, 'head': [30, 0, 30], 'tail': [30, 0, 50], 'radius': 2.},
                {'group': 5, 'bone': self.PELVIS, 'head': [10, 0, 60], 'tail': None, 'radius': 1.}]

    def test_collider_shapes_build_validate_and_rebuild(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            mesh_dir, settings = self.fixture(output, self.springs(), self.colliders())
            build_physics(output)
            system = json.loads((output/'physics.json').read_text(encoding='utf8'))['systems'][0]
            # b's cloth lies at z=35..36, within 6.5+1.75 of the sphere at z=28; a's lies far above it.
            self.assertEqual(system['contact_groups'], {'V2SP_root': [3, 5], 'V2SP_a': [3, 5], 'V2SP_b': [5],
                                                       'V2SP_c': [5]})  # c has no spring and borrows
            self.assertEqual(system['protected_bones'], {})
            self.assertEqual(system['rest_inside_colliders'], {'V2SP_b': [3], 'V2SP_c': [3]})
            root = read_system(output/'mod'/system['xml'])
            self.assertEqual({s.attrib['name'] for s in root.findall('per-triangle-shape')},
                             {PROXY, SPRING_PROXY+'3', SPRING_PROXY+'5'})
            self.assertEqual({s.attrib['name'] for s in root.findall('per-vertex-shape')},
                             {SECONDARY_PROXY+'_S1', SECONDARY_PROXY+'_S2'})
            self.assertEqual(root.findtext(f"per-triangle-shape[@name='{SPRING_PROXY}3']/penetration"), '6.15')
            self.assertEqual(root.findtext(f"per-triangle-shape[@name='{SPRING_PROXY}5']/penetration"), '1.0')
            self.assertIsNone(root.find(f"per-triangle-shape[@name='{PROXY}']/penetration"))
            self.assertEqual(root.findtext("bone[@name='V2SP_c']/gravity-factor"), '1')
            self.assertLess(float(root.findtext("bone[@name='V2SP_a']/gravity-factor")), .1)
            self.assertEqual(root.findtext(f"bone[@name='{self.THIGH}']/mass"), '0')
            with NifFile(str(mesh_dir/'avatar.nif')) as nif:
                shapes = {s.name: s for s in nif.shapes}
                self.assertEqual(set(shapes[SPRING_PROXY+'5'].bone_names), {self.THIGH, self.PELVIS})
                self.assertTrue(shapes[SPRING_PROXY+'3'].properties.flags & 1)
                self.assertEqual(sum(n.startswith('V2SCollision_') for n in shapes), 5)
                self.assertEqual(set(skin_samples(nif)[0]), {self.PELVIS, 'V2SP_root', 'V2SP_a', 'V2SP_b', 'V2SP_c'})
            build_physics(output)  # idempotent on rebuild, and validated by build_physics itself
            with NifFile(str(mesh_dir/'avatar.nif')) as nif:
                self.assertEqual(sum(s.name.startswith('V2SCollision_') for s in nif.shapes), 5)

    def test_validation_refuses_changed_collider_contacts(self):
        def tampered(edit, message):
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                self.fixture(output, self.springs(), self.colliders())
                build_physics(output)
                edit(output)
                with self.assertRaisesRegex(ValueError, message):
                    validate_physics(output)

        def change_json(name, change):
            def edit(output):
                value = json.loads((output/name).read_text(encoding='utf8'))
                change(value)
                (output/name).write_text(json.dumps(value), encoding='utf8')
            return edit

        def change_xml(old, new):
            def edit(output):
                system = json.loads((output/'physics.json').read_text(encoding='utf8'))['systems'][0]
                path = output/'mod'/system['xml']
                text = path.read_text(encoding='utf8')
                self.assertIn(old, text)
                path.write_text(text.replace(old, new, 1), encoding='utf8')
            return edit

        tampered(change_json('physics.json', lambda r: r['systems'][0]['rest_inside_colliders'].clear()),
                 'do not match the rest contact points')
        tampered(change_json('physics.json', lambda r: r['systems'][0]['contact_groups'].pop('V2SP_b')),
                 'Secondary contact proxy must be hidden and match')
        tampered(change_json('spring-colliders.json', lambda c: c[0].update(radius=1.)),
                 'do not match the rest contact points')
        tampered(change_json('spring-colliders.json', lambda c: c[1].update(radius=3.)),
                 'differs from its colliders')
        tampered(change_xml('<margin>1.75</margin>', '<margin>.4</margin>'), 'margin or tags differ')
        tampered(change_xml('_g5</can-collide-with-tag>', '_g9</can-collide-with-tag>'), 'margin or tags differ')
        tampered(change_xml('_g5</no-collide-with-tag>', '_g9</no-collide-with-tag>'), 'must not collide with each other')
        tampered(change_xml('<gravity-factor>1</gravity-factor>', '<gravity-factor>2</gravity-factor>'),
                 'gravity-factor outside')
        tampered(change_xml('<penetration>6.15</penetration>', '<penetration>1</penetration>'), 'depth differs')

    def test_contacts_at_vrm_tails_and_borrowed_colliders_build_and_validate(self):
        spring = self.springs()['V2SP_root']
        springs = {'V2SP_root': spring, 'V2SP_a': spring}  # V2SP_b and V2SP_c are outside every spring
        tails = {'V2SP_root': [20., 0., 50.], 'V2SP_a': [20., 0., 40.]}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            mesh_dir, _ = self.fixture(output, springs, self.colliders(), tails=tails)
            build_physics(output)
            system = json.loads((output/'physics.json').read_text(encoding='utf8'))['systems'][0]
            self.assertEqual(system['tail_contacts'], ['V2SP_a', 'V2SP_root'])
            self.assertEqual({n: system['contact_points'][n] for n in tails}, tails)
            self.assertEqual(system['borrowed_colliders'], {n: {'hit_radius': .025, 'groups': [3, 5]}
                                                            for n in ('V2SP_b', 'V2SP_c')})
            root = read_system(output/'mod'/system['xml'])
            self.assertEqual(root.findtext("bone[@name='V2SP_b']/gravity-factor"), '1')  # joints stay on the preset
            with NifFile(str(mesh_dir/'avatar.nif')) as nif:
                shapes = [s for s in nif.shapes if s.name.startswith(SECONDARY_PROXY)]
                owners = {b: s for s in shapes for b in s.bone_names}
                for name, tail in tails.items():
                    np.testing.assert_allclose(owners[name].verts[owners[name].bone_weights[name][0][0]], tail, atol=.01)
            build_physics(output)  # idempotent on rebuild, and validated by build_physics itself

            def refused(edit, message):
                path = output/'physics.json'
                original = path.read_text(encoding='utf8')
                report = json.loads(original)
                edit(report['systems'][0])
                path.write_text(json.dumps(report), encoding='utf8')
                with self.assertRaisesRegex(ValueError, message):
                    validate_physics(output)
                path.write_text(original, encoding='utf8')

            refused(lambda s: s['contact_points'].update(V2SP_a=[20., 0., 41.]), 'displaced from its VRM spring tail')
            refused(lambda s: s['borrowed_colliders'].pop('V2SP_b'), 'Borrowed colliders do not match')

    def test_a_root_outside_every_spring_moves_when_it_borrows_colliders(self):
        spring = self.springs()['V2SP_a']
        for root_moves in (True, False):
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                self.fixture(output, {'V2SP_a': spring, 'V2SP_b': spring}, self.colliders())
                report = json.loads((output/'skeleton.json').read_text(encoding='utf8'))
                report['physics_bones']['V2SP_root']['dynamic'] = root_moves
                (output/'skeleton.json').write_text(json.dumps(report), encoding='utf8')
                build_physics(output)  # validated by build_physics itself
                system = json.loads((output/'physics.json').read_text(encoding='utf8'))['systems'][0]
                # A planned mover borrows and stays free; a root the plan keeps still is pinned and borrows nothing.
                self.assertEqual('V2SP_root' in system['dynamic_bones'], root_moves)
                self.assertEqual('V2SP_root' in system['borrowed_colliders'], root_moves)
                self.assertEqual('V2SP_root' in system['protected_bones'], not root_moves)

    def test_colliders_work_without_body_hulls(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            mesh_dir, _ = self.fixture(output, self.springs(), self.colliders(), body_role='fixed')
            build_physics(output)
            system = json.loads((output/'physics.json').read_text(encoding='utf8'))['systems'][0]
            self.assertEqual(system['body_hulls'], 0)
            self.assertEqual(system['contact_groups'], {'V2SP_root': [3, 5], 'V2SP_a': [3, 5], 'V2SP_b': [5],
                                                       'V2SP_c': [5]})  # c has no spring and borrows
            self.assertEqual(system['secondary_contact_bones'], ['V2SP_a', 'V2SP_b', 'V2SP_c', 'V2SP_root'])
            root = read_system(output/'mod'/system['xml'])
            self.assertEqual({s.attrib['name'] for s in root.findall('per-triangle-shape')},
                             {SPRING_PROXY+'3', SPRING_PROXY+'5'})
            patches = {s.attrib['name']: {e.text.rsplit('_', 1)[1] for e in s.findall('can-collide-with-tag')}
                       for s in root.findall('per-vertex-shape')}
            self.assertEqual(patches, {SECONDARY_PROXY+'_S1': {'g3', 'g5'}, SECONDARY_PROXY+'_S2': {'g5'}})
            with NifFile(str(mesh_dir/'avatar.nif')) as nif:
                self.assertEqual({s.name for s in nif.shapes if s.name.startswith('V2SCollision_')},
                                 {SPRING_PROXY+'3', SPRING_PROXY+'5', SECONDARY_PROXY+'_S1', SECONDARY_PROXY+'_S2'})
            build_physics(output)  # idempotent on rebuild, and validated by build_physics itself

            path = output/'mod'/system['xml']
            text = path.read_text(encoding='utf8')
            path.write_text(text.replace('_g5</can-collide-with-tag>', '_g9</can-collide-with-tag>', 1), encoding='utf8')
            with self.assertRaisesRegex(ValueError, 'margin or tags differ'):
                validate_physics(output)

    def test_no_body_hulls_and_no_contact_adds_no_collision_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            swallowing = {'group': 3, 'bone': self.THIGH, 'head': [20, 0, 45], 'tail': None, 'radius': 40.}
            mesh_dir, _ = self.fixture(output, self.springs(), [swallowing], body_role='fixed')
            build_physics(output)
            system = json.loads((output/'physics.json').read_text(encoding='utf8'))['systems'][0]
            self.assertEqual((system['contact_groups'], system['secondary_contact_bones']), ({}, []))
            self.assertEqual(set(system['rest_inside_colliders']), {'V2SP_root', 'V2SP_a', 'V2SP_b', 'V2SP_c'})
            root = read_system(output/'mod'/system['xml'])
            self.assertEqual(root.findall('per-triangle-shape')+root.findall('per-vertex-shape'), [])
            with NifFile(str(mesh_dir/'avatar.nif')) as nif:
                self.assertFalse(any(s.name.startswith('V2SCollision_') for s in nif.shapes))

    def test_spring_without_colliders_scales_the_joint_and_adds_no_shape(self):
        spring = {'stiffness': 8., 'gravity': .12, 'hit_radius': 0., 'groups': []}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.fixture(output, {n: spring for n in ('V2SP_root', 'V2SP_a', 'V2SP_b')}, [])
            build_physics(output)
            system = json.loads((output/'physics.json').read_text(encoding='utf8'))['systems'][0]
            root = read_system(output/'mod'/system['xml'])
            self.assertEqual({s.attrib['name'] for s in root.findall('per-triangle-shape')}, {PROXY})
            self.assertEqual({s.attrib['name'] for s in root.findall('per-vertex-shape')}, {SECONDARY_PROXY})
            self.assertLess(float(root.findtext("bone[@name='V2SP_a']/gravity-factor")), .1)
            self.assertEqual((system['contact_groups'], system['rest_inside_colliders']), ({}, {}))

    def test_model_without_springs_matches_the_old_shapes(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            mesh_dir, _ = self.fixture(output, {}, [])
            (output/'spring-colliders.json').unlink()  # also an output older than this file
            build_physics(output)
            system = json.loads((output/'physics.json').read_text(encoding='utf8'))['systems'][0]
            root = read_system(output/'mod'/system['xml'])
            self.assertEqual({s.attrib['name'] for s in root.findall('per-vertex-shape')}, {SECONDARY_PROXY})
            self.assertEqual({b.findtext('gravity-factor') for b in root.findall('bone') if b.find('inertia') is not None},
                             {'1'})
            with NifFile(str(mesh_dir/'avatar.nif')) as nif:
                self.assertEqual(sum(s.name.startswith('V2SCollision_') for s in nif.shapes), 2)


class BonePartitionTests(unittest.TestCase):
    def test_blender_export_splits_shapes_by_bone_count_and_drops_unused_bones(self):
        import json
        from converter import run_blender
        from environment import find_blender
        from nif_limits import SHAPE_BONE_LIMIT
        if not find_blender():
            self.skipTest('Blender is not installed')
        count = SHAPE_BONE_LIMIT*2 + 30
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory)/'parts.json'
            run_blender(find_blender(), 'tests/blender-bone-partition.py', [report, count], Path(directory), 'Bone partition')
            parts = json.loads(report.read_text(encoding='utf8'))
        self.assertGreater(len(parts), 2)
        self.assertEqual(sum(p['vertices'] for p in parts), 4*count)
        for part in parts:
            self.assertLessEqual(len(part['weighted']), SHAPE_BONE_LIMIT)
            self.assertEqual(part['groups'], sorted(part['weighted'] + ['SBP_130_HEAD']))
        self.assertEqual(set().union(*(p['weighted'] for p in parts)), {f'Hair {i:03}' for i in range(count)})


if __name__ == '__main__':
    unittest.main()
