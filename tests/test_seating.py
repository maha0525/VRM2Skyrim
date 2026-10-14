"""Compiled seating PEX lifecycle and independent skeleton/pose readback."""
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np

from equipment_runtime import rename_pex
from plugin import Record
from seating import chair_record, animated_pelvis, binding, NODE, validate_root
from settings import FollowerSettings
from tests.pex_vm import Actor, PexVM
from environment import find_game

ROOT = Path(__file__).resolve().parents[1]


class Furniture:
    def __init__(self, form_id):
        self.form_id = form_id

    def call(self, name, values):
        assert name == 'getbaseobject'
        return self.form_id


class SeatedActor(Actor):
    def __init__(self):
        super().__init__({})
        self.loaded, self.node, self.position = True, True, 0.0
        self.sit, self.sleep, self.mounted = 0, 0, False
        self.furniture = Furniture(200)
        self.pending, self.writes = False, []
        self.animation_events, self.intervals = set(), []

    def call(self, name, values):
        results = {'is3dloaded': self.loaded, 'getsitstate': self.sit, 'getsleepstate': self.sleep,
                   'isonmount': self.mounted, 'getfurniturereference': self.furniture}
        if name in results:
            return results[name]
        if name == 'registerforsingleupdate':
            assert any(abs(values[0] - interval) < 1e-7 for interval in (.5, .1))
            self.intervals.append(round(values[0], 3))
            self.pending = True
            return
        if name == 'registerforanimationevent':
            assert values[0] is self
            self.animation_events.add(values[1])
            return True
        if name == 'unregisterforupdate':
            self.pending = False
            return
        return super().call(name, values)

    def global_call(self, target, name, values):
        assert target == 'netimmerse'
        assert values[:2] == [self, NODE]
        assert values[-1] == 0
        if name == 'hasnode':
            return self.node
        if name == 'getnodelocalpositionz':
            return self.position
        assert name == 'setnodelocalpositionz'
        self.position = values[2]
        self.writes.append(self.position)


class SeatingTests(unittest.TestCase):
    def fixture(self):
        actor = SeatedActor()
        data = rename_pex((ROOT / 'runtime/V2SSeating.pex').read_bytes(), 'V2S_TestSeating', 'V2SSeating')
        return actor, PexVM(data, actor, {'Seats': (200,), 'Offset': 14.0})

    def test_entry_corrects_before_onsit_without_double_add_and_cancellation_restores(self):
        actor, vm = self.fixture()
        vm.run('OnLoad')
        self.assertIn('IdleChairEnterStart', actor.animation_events)
        self.assertIn('IdleLeftChairEnterStart', actor.animation_events)
        self.assertIn('IdleRightChairEnterStart', actor.animation_events)
        self.assertIn('SoundPlay.NPCHumanSitChairDownLR', actor.animation_events)
        actor.position = 7.0
        actor.sit = 2  # Entry animation is running; OnSit has not happened yet.
        for event in sorted(actor.animation_events):
            vm.run('OnAnimationEvent', actor, event)
        self.assertEqual(actor.writes, [21.0])
        actor.sit = 3
        vm.run('OnSit', actor.furniture)
        self.assertEqual(actor.writes, [21.0])
        actor.sit = 4
        vm.run('OnGetUp', actor.furniture)
        self.assertEqual(actor.position, 7.0)
        actor.sit = 2
        vm.run('OnAnimationEvent', actor, 'IdleFurnitureStart')
        actor.sit = 0  # The entry was cancelled before sitting.
        vm.run('OnUpdate')
        self.assertEqual(actor.position, 7.0)

    def test_early_event_waits_for_real_sit_state_and_unknown_events_are_ignored(self):
        actor, vm = self.fixture()
        vm.run('OnAnimationEvent', None, 'IdleChairEnterStart')
        vm.run('OnAnimationEvent', actor, 'UnknownEvent')
        self.assertFalse(actor.pending)
        vm.run('OnAnimationEvent', actor, 'IdleChairEnterStart')
        self.assertEqual(actor.writes, [])
        self.assertEqual(actor.intervals, [.1])
        actor.sit = 2
        vm.run('OnUpdate')
        self.assertEqual(actor.position, 14)
        actor.sit = 0
        vm.run('OnUpdate')
        self.assertEqual(actor.position, 0)

    def test_entry_on_workbench_sleep_or_mount_never_shifts_root(self):
        for kind in ('workbench', 'sleep', 'mount', 'no_furniture', 'missing_node', 'unloaded'):
            with self.subTest(kind=kind):
                actor, vm = self.fixture()
                actor.sit = 2
                if kind == 'workbench':
                    actor.furniture = Furniture(999)
                elif kind == 'sleep':
                    actor.sleep = 2
                elif kind == 'mount':
                    actor.mounted = True
                elif kind == 'no_furniture':
                    actor.furniture = None
                elif kind == 'missing_node':
                    actor.node = False
                else:
                    actor.loaded = False
                vm.run('OnAnimationEvent', actor, 'IdleFurnitureStart')
                self.assertEqual(actor.writes, [])

    def test_entry_waits_across_delayed_engine_state_and_stops_after_timeout(self):
        actor, vm = self.fixture()
        vm.run('OnAnimationEvent', actor, 'IdleChairEnterStart')
        for _ in range(15):
            actor.pending = False
            vm.run('OnUpdate')
            self.assertTrue(actor.pending)
            self.assertEqual(actor.writes, [])
        actor.sit = 2
        vm.run('OnUpdate')
        self.assertEqual(actor.writes, [14.0])
        actor.sit = 3
        vm.run('OnSit', actor.furniture)
        self.assertEqual(actor.writes, [14.0])
        actor.sit = 0
        vm.run('OnUpdate')
        self.assertEqual(actor.position, 0.0)
        actor, vm = self.fixture()
        vm.run('OnAnimationEvent', actor, 'IdleChairEnterStart')
        for _ in range(41):
            actor.pending = False
            vm.run('OnUpdate')
        self.assertFalse(actor.pending)
        self.assertEqual(actor.writes, [])

    def test_nested_event_during_native_write_does_not_add_offset_twice(self):
        class ReentrantActor(SeatedActor):
            def global_call(self, target, name, values):
                result = super().global_call(target, name, values)
                if name == 'setnodelocalpositionz' and len(self.writes) == 1:
                    vm.run('OnUpdate')
                return result
        actor = ReentrantActor()
        data = rename_pex((ROOT / 'runtime/V2SSeating.pex').read_bytes(), 'V2S_TestSeating', 'V2SSeating')
        vm = PexVM(data, actor, {'Seats': (200,), 'Offset': 14.0})
        actor.sit = 2
        actor.position = 7.0
        vm.run('OnAnimationEvent', actor, 'IdleChairEnterStart')
        self.assertEqual(actor.writes, [21.0])
        actor.sit = 0
        vm.run('OnUpdate')
        self.assertEqual(actor.position, 7.0)

    def test_unload_stops_entry_retries_without_touching_unloaded_3d(self):
        actor, vm = self.fixture()
        vm.run('OnAnimationEvent', actor, 'IdleChairEnterStart')
        actor.loaded = False
        vm.run('OnUnload')
        self.assertFalse(actor.pending)
        self.assertEqual(vm.variables['entryretries'], 0)
        self.assertEqual(actor.writes, [])

    def test_seated_load_rebuild_and_delayed_exit_are_idempotent(self):
        actor, vm = self.fixture()
        vm.run('OnInit')
        self.assertEqual(actor.writes, [])
        actor.sit = 3
        vm.run('OnSit', actor.furniture)
        self.assertEqual(actor.position, 14)
        for _ in range(8):
            vm.run('OnUpdate')
            vm.run('OnNiNodeUpdate', actor)
        self.assertEqual(actor.writes, [14])
        actor.position = 0  # The engine reconstructed the skeleton from disk.
        vm.run('OnNiNodeUpdate', actor)
        self.assertEqual(actor.position, 14)
        vm.run('OnUnload')
        self.assertEqual(actor.position, 0)
        self.assertFalse(actor.pending)
        vm.run('OnLoad')  # Already seated when entering the cell/loading save.
        self.assertEqual(actor.position, 14)
        actor.sit = 4
        vm.run('OnGetUp', actor.furniture)
        self.assertEqual(actor.position, 0)
        actor.sit = 0
        actor.pending = False
        vm.run('OnUpdate')
        vm.run('OnSit', actor.furniture)  # Delayed old sit event after standing.
        self.assertEqual(actor.position, 0)
        self.assertFalse(actor.pending)
        self.assertEqual(actor.inventory, {})

    def test_workbench_sleep_mount_missing_furniture_and_unloaded_actor(self):
        for kind in ('workbench', 'sleep', 'mount', 'no_furniture', 'missing_node', 'unloaded'):
            with self.subTest(kind=kind):
                actor, vm = self.fixture()
                actor.sit = 3
                if kind == 'workbench':
                    actor.furniture = Furniture(999)
                elif kind == 'sleep':
                    actor.sleep = 3
                elif kind == 'mount':
                    actor.mounted = True
                elif kind == 'no_furniture':
                    actor.furniture = None
                elif kind == 'missing_node':
                    actor.node = False
                else:
                    actor.loaded = False
                vm.run('OnLoad')
                self.assertEqual(actor.writes, [])

    def test_standing_does_not_write_existing_root_adjustments(self):
        actor, vm = self.fixture()
        actor.position = 7.0  # Another component owns this standing adjustment.
        for event in ('OnInit', 'OnLoad', 'OnUpdate', 'OnGetUp'):
            vm.run(event, actor.furniture) if event == 'OnGetUp' else vm.run(event)
        self.assertEqual(actor.writes, [])
        actor.sit = 3
        vm.run('OnSit', actor.furniture)
        self.assertEqual(actor.position, 21)
        actor.sit = 0
        vm.run('OnGetUp', actor.furniture)
        self.assertEqual(actor.position, 7)
        actor.sit = 3
        vm.run('OnSit', actor.furniture)
        actor.position = 9.0  # A new transform replaces our correction.
        actor.sit = 0
        vm.run('OnGetUp', actor.furniture)
        self.assertEqual(actor.position, 9)

    def test_saved_tracking_with_rebuilt_or_existing_3d_does_not_accumulate(self):
        actor, vm = self.fixture()
        actor.sit = 3
        vm.run('OnSit', actor.furniture)
        vm.run('OnLoad')  # Same node is still at its previously corrected value.
        self.assertEqual(actor.position, 14)
        actor.position = 0  # Reload reconstructed the original skeleton.
        vm.run('OnLoad')
        self.assertEqual(actor.position, 14)
        actor.sit = 0
        actor.position = 0
        vm.run('OnLoad')
        self.assertEqual(actor.position, 0)

    def test_identity_wrapper_is_rejected_despite_equal_rest_transforms(self):
        root = type('Node', (), {'id': 0})()
        npc = type('Node', (), {'parent': root})()
        nif = type('Nif', (), {'rootNode': root, 'nodes': {'NPC': npc}})()
        validate_root(nif)
        wrapper = type('Node', (), {'id': 1, 'parent': root})()
        npc.parent = wrapper
        nif.nodes['VRM2SkyrimSeating'] = wrapper
        with self.assertRaisesRegex(ValueError, 'original scene root'):
            validate_root(nif)

    def test_actual_marker_classification(self):
        chair = Record(b'FURN', 200, 0, [(b'MODL', b'chair.nif\0'), (b'FNPR', struct.pack('<HH', 1, 15))])
        self.assertTrue(chair_record(chair))
        for changes in ({'flags': 0x800000}, {'flags': 0x80}, {'marker': 2}, {'marker': 4}, {'workbench': 2}):
            record = Record(chair.kind, chair.form_id, changes.get('flags', 0), list(chair.fields))
            record.replace(b'FNPR', struct.pack('<HH', changes.get('marker', 1), 15))
            if 'workbench' in changes:
                record.replace(b'WBDT', bytes((changes['workbench'], 0)))
            self.assertFalse(chair_record(record))

    def test_pose_is_evaluated_through_unanimated_offsets(self):
        pelvis = 'NPC Pelvis [Pelv]'
        local = {pelvis: np.eye(4), 'offset': np.eye(4), 'root': np.eye(4)}
        local['offset'][2, 3] = -14
        local['root'][2, 3] = 30
        track = type('Track', (), {'rotations': [[0, 0, 0, 1]], 'scales': [[1, 1, 1]],
                                  'translations': [[0, 0, 8]]})()
        z = animated_pelvis(local, {pelvis: 'offset', 'offset': 'root', 'root': None}, [pelvis], [track], 0)
        self.assertEqual(z, 24)

    def test_private_binding_and_settings_validation(self):
        for offset in (float('nan'), 101, -101):
            with self.assertRaises(ValueError):
                FollowerSettings(sitting_offset=offset)
        for key in ('sitting_enabled', 'sitting_auto'):
            with self.assertRaises(ValueError):
                FollowerSettings(**{key: 'true'})
        first = binding(FollowerSettings(mod_id='First'), 14)
        second = binding(FollowerSettings(mod_id='Second'), 14)
        self.assertIn(b'V2S_FirstSeating', first)
        self.assertIn(b'V2S_SecondSeating', second)
        self.assertEqual(struct.unpack('<f', first[-4:])[0], 14)


@unittest.skipUnless(find_game(), 'Local Skyrim assets required')
class SeatingNativeTests(unittest.TestCase):
    def test_original_chair_entry_annotations_are_at_animation_start(self):
        import sys
        from bsa import BSA
        sys.path.insert(0, str(ROOT / 'dependencies/io_scene_nifly/hkx'))
        from anim_skyrim import load_skyrim_animation
        archive = BSA(find_game() / 'Data/Skyrim - Animations.bsa')
        graph = archive.read('meshes/actors/character/behaviors/0_master.hkx')
        for event in ('IdleFurnitureStart', 'IdleChairEnterStart', 'IdleLeftChairEnterStart',
                      'IdleRightChairEnterStart'):
            self.assertIn(event.encode() + b'\0', graph)
        root = ROOT / 'build/test-tmp'
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            for sex in ('male', 'female'):
                for clip, event in (('chair_frontentervar1', 'SoundPlay.NPCHumanSitChairDown'),
                                    ('chair_leftenter', 'SoundPlay.NPCHumanSitChairDownLR'),
                                    ('chair_rightenter', 'SoundPlay.NPCHumanSitChairDownLR')):
                    with self.subTest(sex=sex, clip=clip):
                        path = archive.extract(f'meshes/actors/character/animations/{sex}/{clip}.hkx',
                                               Path(directory) / f'{sex}_{clip}.hkx')
                        animation = load_skyrim_animation(str(path))
                        self.assertTrue(any(a.text == event and a.time == 0 for a in animation.annotations))

    def test_reference_sized_skeleton_pose_offset_and_plugin_readback(self):
        import json
        from build_npc import build_npc, NPC_ID
        from converter import references
        from custom_skeleton import NifFile, matrix, create_skeleton, save_report
        from plugin import records
        from seating import prepare, validate_runtime, SEATS_ID
        root = ROOT / 'build/test-tmp'
        root.mkdir(parents=True, exist_ok=True)
        game = find_game()
        for sex, voice in (('female', 'FemaleEvenToned'), ('male', 'MaleNord')):
            with self.subTest(sex=sex), tempfile.TemporaryDirectory(dir=root) as directory:
                output = Path(directory)
                settings = FollowerSettings(sex=sex, voice=voice, sitting_offset=2.5)
                source = references(game / 'Data', sex)
                target = output / 'mod/meshes' / settings.asset_dir / 'skeleton.nif'
                report = create_skeleton(source, target, {})
                save_report(report, output)
                (output / 'references.json').write_text(json.dumps({'root': str(source.parents[4])}))
                result = prepare(output, game / 'Data', settings)
                self.assertAlmostEqual(result['automatic_offset'], 0, places=4)
                self.assertEqual(result['offset'], 2.5)
                with NifFile(str(source)) as nif:
                    original = {name: matrix(node.global_transform) for name, node in nif.nodes.items()}
                with NifFile(str(target)) as nif:
                    validate_root(nif)
                    for name, value in original.items():
                        np.testing.assert_allclose(matrix(nif.nodes[name].global_transform), value, atol=5e-5)
                plugin = build_npc(game / 'Data', output, settings)
                generated = list(records(plugin))
                by_id = {r.form_id: r for r in generated}
                validate_runtime(output, settings, by_id[NPC_ID], by_id)
                furniture = next(r for r in records(game / 'Data/Skyrim.esm', {b'FURN'})
                                 if r.editor_id == 'WRTempleBench01')
                self.assertIn(struct.pack('<I', furniture.form_id), by_id[SEATS_ID].values(b'LNAM'))
                self.assertFalse(any(r.kind == b'FURN' for r in generated))


if __name__ == '__main__':
    unittest.main()
