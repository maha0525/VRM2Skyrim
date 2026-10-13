"""Secondary-rig ownership and FSMP joint-frame contracts."""
import unittest
from pathlib import Path
import tempfile

import numpy as np

from fsmp import (GRAVITY, INERTIA_DIVISOR, LINK, MASS, PROXY, add_collision_proxy,
                  attach, joint_profile, local_points, system_xml)
from custom_skeleton import NifFile, create_skeleton, matrix, rigid_buffer
from physics_rig import plan_bones, selected_meshes, spring_nodes
from settings import FollowerSettings


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

    def test_weighted_sleeve_root_can_pivot_on_animated_arm(self):
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
        inertia = .4 * MASS * 3**2 / INERTIA_DIVISOR + MASS * 20**2
        ratio = damping[0] / (2*np.sqrt(inertia*(spring[0] + MASS*GRAVITY*20)))
        self.assertGreaterEqual(ratio, 1.)
        short = joint_profile([2, 0, 0], 3., np.eye(4))[2]
        self.assertGreater(damping[0], short[0]*10)

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
