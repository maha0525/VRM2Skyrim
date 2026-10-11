"""Supply no native human geometry, independently of worn items or outfits."""
import logging
from pathlib import Path
import struct

from plugin import Record

HEAD_COVER_ID = 0x0100080B  # Retired 0.5.1 item: keep its saved FormID inert.
EMPTY_HEAD_ID = 0x0100080C
HEAD_RACES_ID = 0x0100080D
FACEGEN_HEAD_FLAG = 0x2  # xEdit TES5 DATA flags / CommonLibSSE TESRace::kFaceGenHead.


def head_records(settings, race_id):
    model = settings.asset_dir.replace('/', '\\') + '\\native_head_empty.nif'
    return [
        Record(b'FLST', HEAD_RACES_ID, 0, [(b'EDID', (settings.prefix+'HeadRaces\0').encode()),
                                        (b'LNAM', struct.pack('<I', race_id))]),
        Record(b'HDPT', EMPTY_HEAD_ID, 4, [(b'EDID', (settings.prefix+'EmptyHead\0').encode()),
             (b'MODL', (model+'\0').encode()), (b'DATA', b'\x06'),
             (b'PNAM', struct.pack('<I', 1)), (b'RNAM', struct.pack('<I', HEAD_RACES_ID))]),
    ]


def configure_native_head(npc, race):
    data = bytearray(race.values(b'DATA')[0])
    flags = struct.unpack_from('<I', data, 32)[0]
    struct.pack_into('<I', data, 32, flags & ~FACEGEN_HEAD_FLAG)
    race.replace(b'DATA', bytes(data))
    npc.remove(b'PNAM', b'NAM9', b'NAMA', b'TINI', b'TINC', b'TINV', b'TIRS', b'FTST')
    npc.replace(b'PNAM', struct.pack('<I', EMPTY_HEAD_ID))
    # NAM0 starts the final, sex-specific Head Data section of a TES5 RACE.
    start = next(i for i, (tag, data) in enumerate(race.fields) if tag == b'NAM0' and not data)
    race.fields = race.fields[:start] + [
        (b'NAM0', b''), (b'MNAM', b''), (b'INDX', struct.pack('<I', 0)),
        (b'HEAD', struct.pack('<I', EMPTY_HEAD_ID)),
        (b'NAM0', b''), (b'FNAM', b''), (b'INDX', struct.pack('<I', 0)),
        (b'HEAD', struct.pack('<I', EMPTY_HEAD_ID)),
    ]


def write_head_assets(output, settings):
    from custom_skeleton import NifFile
    mod = Path(output) / 'mod'
    paths = (mod / 'meshes' / settings.asset_dir / 'native_head_empty.nif',
             mod / 'meshes/actors/character/facegendata/facegeom' / settings.plugin_name / '00000800.nif')
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NifFile() as nif:
            nif.initialize('SKYRIMSE', str(path), 'BSFadeNode', '00000800.NIF')
            nif.save()
        with NifFile(str(path)) as nif:
            if nif.root.blockname != 'BSFadeNode' or nif.shapes:
                raise ValueError('Empty native head asset must be a meshless BSFadeNode')
    logging.info('Native head has no geometry: private HDPT and FaceGen; no worn-item dependency')


def validate_head_visibility(generated, settings):
    by_name = {record.editor_id: record for record in generated}
    by_id = {record.form_id: record for record in generated}
    npc, race = (by_name[settings.prefix+name] for name in ('NPC', 'Race'))
    if struct.unpack_from('<I', race.values(b'DATA')[0], 32)[0] & FACEGEN_HEAD_FLAG:
        raise ValueError('Race still enables native FaceGen head generation')
    if npc.values(b'PNAM') != [struct.pack('<I', EMPTY_HEAD_ID)]:
        raise ValueError('NPC still uses native human head parts')
    if race.values(b'HEAD') != [struct.pack('<I', EMPTY_HEAD_ID)] * 2:
        raise ValueError('Race still supplies native human head parts')
    head = by_id.get(EMPTY_HEAD_ID)
    if head is None or head.kind != b'HDPT' or head.values(b'PNAM') != [struct.pack('<I', 1)]:
        raise ValueError('Private empty face head part is missing')
    expected = (settings.asset_dir.replace('/', '\\')+'\\native_head_empty.nif\0').encode()
    if head.values(b'MODL') != [expected] or head.values(b'HNAM') or head.values(b'NAM1'):
        raise ValueError('Native head must have only the empty model, without extra parts/morphs')
    if head.values(b'RNAM') != [struct.pack('<I', HEAD_RACES_ID)] or by_id[HEAD_RACES_ID].values(b'LNAM') != [struct.pack('<I', race.form_id)]:
        raise ValueError('Empty head must belong only to this private race')
    return {'native_head_geometry': 'empty', 'native_facegen_enabled': False, 'depends_on_equipped_head_cover': False,
            'game_verified': False}
