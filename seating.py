"""Chair-only height correction from actual delivered NIF and official HKX."""
import json
import logging
from pathlib import Path
import struct
import sys

import numpy as np
from scipy.spatial.transform import Rotation

from plugin import Record, records

ROOT = Path(__file__).resolve().parent
NODE = 'VRM2SkyrimSeating'
TEMPLATE = 'V2SSeating'
SEATS_ID = 0x01000870
PELVIS = 'NPC Pelvis [Pelv]'


def chair_record(record):
    # FURN FNPR marker type 1 is Sit, 2 Lay, 4 Lean (xEdit TES5 schema).
    # Workbench, perch and invisible idle markers must not receive chair offsets.
    if record.flags & (4 | 0x80 | 0x800000) or not record.values(b'MODL'):
        return False
    work = record.values(b'WBDT')
    if work and work[0] and work[0][0] != 0:
        return False
    markers = record.values(b'FNPR')
    return bool(markers) and all(len(v) == 4 and struct.unpack_from('<H', v)[0] == 1 for v in markers)


def animated_pelvis(local, parents, names, tracks, frame):
    animated = dict(local)
    for name, track in zip(names, tracks):
        if name not in local:
            continue
        value = np.eye(4)
        value[:3, :3] = Rotation.from_quat(track.rotations[frame]).as_matrix() @ np.diag(track.scales[frame])
        value[:3, 3] = track.translations[frame]
        animated[name] = value
    value = animated[PELVIS]
    parent = parents[PELVIS]
    while parent is not None:
        value = animated[parent] @ value
        parent = parents[parent]
    return float(value[2, 3])


def calculate(output, settings):
    from bsa import BSA
    from custom_skeleton import NifFile, matrix
    from settings import reference_root
    sys.path.insert(0, str(ROOT / 'dependencies/io_scene_nifly/hkx'))
    from anim_skyrim import load_skyrim_animation, load_skyrim_skeleton

    output = Path(output)
    report = json.loads((output / 'skeleton.json').read_text(encoding='utf8'))
    root = reference_root(output)
    base = root / 'meshes/actors/character'
    name = f'meshes/actors/character/animations/{settings.sex}/chair_idlebasevar1.hkx'
    animation_path = root / name
    if not animation_path.exists():
        BSA(Path(report['game_data']) / 'Skyrim - Animations.bsa').extract(name, animation_path)
    hkx = load_skyrim_skeleton(str(base / 'character assets/skeleton.hkx'))
    animation = load_skyrim_animation(str(animation_path))
    indices = animation.track_to_bone_indices or list(range(animation.num_tracks))
    names = [hkx.bones[index] for index in indices]
    samples = []
    for path in (Path(report['source']), output / 'mod/meshes' / settings.asset_dir / 'skeleton.nif'):
        with NifFile(str(path)) as nif:
            local = {name: matrix(node.transform) for name, node in nif.nodes.items()}
            parents = {name: node.parent.name if node.parent else None for name, node in nif.nodes.items()}
            if path != Path(report['source']) and (NODE not in local or not np.allclose(local[NODE], np.eye(4))):
                raise ValueError('Seating requires an identity private skeleton node')
        samples.append(np.array([animated_pelvis(local, parents, names, animation.tracks, i)
                                 for i in range(animation.num_frames)]))
    differences = samples[0] - samples[1]
    offset = float(np.median(differences))
    if not np.isfinite(offset) or abs(offset) > 100:
        raise ValueError('Calculated seated height correction is outside supported range')
    return {'animation': name, 'frames': animation.num_frames, 'automatic_offset': offset,
            'vanilla_pelvis_z': float(np.median(samples[0])), 'custom_pelvis_z': float(np.median(samples[1])),
            'max_pelvis_residual': float(np.max(np.abs(differences - offset)))}


def prepare(output, game_data, settings):
    if not settings.sitting_enabled:
        return
    output = Path(output)
    # The calculation extracts only required game assets into the private cache.
    path = output / 'skeleton.json'
    report = json.loads(path.read_text(encoding='utf8'))
    report['game_data'] = str(Path(game_data).resolve())
    path.write_text(json.dumps(report, indent=2), encoding='utf8')
    result = calculate(output, settings) if settings.sitting_auto else {'automatic_offset': 0.0}
    result.update(manual_offset=settings.sitting_offset, offset=result['automatic_offset'] + settings.sitting_offset,
                  node=NODE, requires='SKSE64', scope='Skyrim.esm chair/bench furniture')
    (output / 'seating.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    logging.info('Seated height: automatic %.4f + manual %.4f = %.4f',
                 result['automatic_offset'], settings.sitting_offset, result['offset'])
    return result


def binding(settings, offset):
    def string(value):
        raw = value.encode()
        return struct.pack('<H', len(raw)) + raw
    return (string(settings.prefix + 'Seating') + struct.pack('<BH', 0, 2)
            + string('Seats') + bytes((1, 1)) + struct.pack('<HhI', 0, -1, SEATS_ID)
            + string('Offset') + bytes((4, 1)) + struct.pack('<f', offset))


def append_binding(data, settings, offset):
    data = data or struct.pack('<HHH', 5, 2, 0)
    count = struct.unpack_from('<H', data, 4)[0]
    return data[:4] + struct.pack('<H', count + 1) + data[6:] + binding(settings, offset)


def runtime_records(game_data, settings):
    seats = [r for r in records(Path(game_data) / 'Skyrim.esm', {b'FURN'}) if chair_record(r)]
    if not seats:
        raise ValueError('No chair furniture found in Skyrim.esm')
    return [Record(b'FLST', SEATS_ID, 0, [(b'EDID', (settings.prefix + 'Seats\0').encode()),
                                       *[(b'LNAM', struct.pack('<I', r.form_id)) for r in seats]])]


def write_runtime(output, settings):
    from equipment_runtime import rename_pex
    output = Path(output)
    name = settings.prefix + 'Seating'
    target = output / 'mod/scripts'
    target.mkdir(parents=True, exist_ok=True)
    (target / (name + '.pex')).write_bytes(rename_pex((ROOT / 'runtime' / (TEMPLATE + '.pex')).read_bytes(),
                                                    name, TEMPLATE))
    target = output / 'mod/source/scripts'
    target.mkdir(parents=True, exist_ok=True)
    (target / (name + '.psc')).write_text((ROOT / 'runtime' / (TEMPLATE + '.psc')).read_text().replace(TEMPLATE, name),
                                         encoding='utf8')
    logging.info('Private seated height runtime: %s (SKSE64)', name)


def validate_runtime(output, settings, npc, by_id):
    from custom_skeleton import NifFile, matrix
    from equipment_runtime import pex_strings, vmad
    output = Path(output)
    report = json.loads((output / 'seating.json').read_text(encoding='utf8'))
    expected = append_binding(vmad(settings) if settings.armor_support else None, settings, report['offset'])
    if npc.values(b'VMAD') != [expected]:
        raise ValueError('Seating script binding differs from computed correction')
    base = json.loads((output / 'skeleton.json').read_text(encoding='utf8'))
    for record in runtime_records(base['game_data'], settings):
        if by_id[record.form_id].fields != record.fields:
            raise ValueError('Seating furniture list differs from game chair records')
    with NifFile(str(output / 'mod/meshes' / settings.asset_dir / 'skeleton.nif')) as nif:
        if NODE not in nif.nodes or not np.allclose(matrix(nif.nodes[NODE].transform), np.eye(4)):
            raise ValueError('Seated correction must be zero in delivered standing skeleton')
    data = (output / 'mod/scripts' / (settings.prefix + 'Seating.pex')).read_bytes()
    _, _, _, strings = pex_strings(data)
    if (settings.prefix + 'Seating').encode() not in strings:
        raise ValueError('Seating PEX private name mismatch')
    if {s.lower() for s in strings} & {b'setposition', b'translateto', b'setscale', b'equipitem', b'unequipitem'}:
        raise ValueError('Seating runtime contains prohibited reference/equipment mutations')
    logging.info('Read back seated offset %.4f, private PEX, chair list and identity skeleton node', report['offset'])
