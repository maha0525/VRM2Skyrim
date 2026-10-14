"""Secondary-rig ownership and FSMP joint-frame contracts."""
import unittest
from pathlib import Path
import tempfile

import numpy as np

from fsmp import (ARM_PROXY, GRAVITY, LINK, MASS, PROXY, add_arm_collision_proxy,
                  add_collision_proxy, arm_cloth_bones, attach, joint_profile,
                  local_points, protect_attachments, skin_samples, system_xml)
from custom_skeleton import NifFile, create_skeleton, matrix, rigid_buffer
from physics_rig import inertia_sphere_radius, plan_bones, selected_meshes, spring_nodes, rotation_step_angles
from settings import FollowerSettings
from physics_frames import shift_frames, translation


class PhysicsTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
