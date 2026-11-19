"""Supply either no native human geometry or VRM facial expression HeadParts."""
import logging
from pathlib import Path
import struct

from expressions import EXTRA_HDPT_BASE_ID, load_facial_manifest, validate_facial_assets
from plugin import Record

HEAD_COVER_ID = 0x0100080B  # Retired 0.5.1 item: keep its saved FormID inert.
EMPTY_HEAD_ID = 0x0100080C
HEAD_RACES_ID = 0x0100080D
FACEGEN_HEAD_FLAG = 0x2  # xEdit TES5 DATA flags / CommonLibSSE TESRace::kFaceGenHead.


def _mesh_relative(mod_relative: str) -> bytes:
    """Convert 'meshes/...' mod-relative path to Skyrim MODL/NAM1 path (without 'meshes\\')."""
    rel = mod_relative.replace('/', '\\')
    if rel.lower().startswith('meshes\\'):
        rel = rel[7:]
    return (rel + '\0').encode('utf8')


def facial_extra_ids(facial) -> list[int]:
    if not facial:
        return []
    return [EXTRA_HDPT_BASE_ID + i for i in range(max(0, len(facial['parts']) - 1))]


def head_records(settings, race_id, facial=None):
    flst = Record(b'FLST', HEAD_RACES_ID, 0, [
        (b'EDID', (settings.prefix + 'HeadRaces\0').encode('utf8')),
        (b'LNAM', struct.pack('<I', race_id)),
    ])
    if not facial:
        model = settings.asset_dir.replace('/', '\\') + '\\native_head_empty.nif'
        return [
            flst,
            Record(b'HDPT', EMPTY_HEAD_ID, 4, [
                (b'EDID', (settings.prefix + 'EmptyHead\0').encode('utf8')),
                (b'MODL', (model + '\0').encode('utf8')),
                (b'DATA', b'\x06'),
                (b'PNAM', struct.pack('<I', 1)),
                (b'RNAM', struct.pack('<I', HEAD_RACES_ID)),
            ]),
        ]
    parts = facial['parts']
    extra_ids = facial_extra_ids(facial)
    primary = parts[0]
    primary_fields = [
        (b'EDID', (primary['edid'] + '\0').encode('utf8')),
        (b'FULL', (settings.npc_name + ' Face\0').encode('utf8')),
        (b'MODL', _mesh_relative(primary['nif'])),
        (b'DATA', b'\x06'),  # Male | Female, non-playable
        (b'PNAM', struct.pack('<I', 1)),  # Face
        *[(b'HNAM', struct.pack('<I', fid)) for fid in extra_ids],
        (b'NAM0', struct.pack('<I', 1)),  # Expression / phoneme / blink TRI
        (b'NAM1', _mesh_relative(primary['tri'])),
        (b'RNAM', struct.pack('<I', HEAD_RACES_ID)),
    ]
    records = [flst, Record(b'HDPT', EMPTY_HEAD_ID, 4, primary_fields)]
    for extra_id, part in zip(extra_ids, parts[1:]):
        records.append(Record(b'HDPT', extra_id, 4, [
            (b'EDID', (part['edid'] + '\0').encode('utf8')),
            (b'MODL', _mesh_relative(part['nif'])),
            (b'DATA', b'\x0E'),  # Male | Female | IsExtraPart
            (b'PNAM', struct.pack('<I', 0)),  # Misc (vanilla extra parts)
            (b'NAM0', struct.pack('<I', 1)),  # Expression / phoneme / blink TRI
            (b'NAM1', _mesh_relative(part['tri'])),
            (b'RNAM', struct.pack('<I', HEAD_RACES_ID)),
        ]))
    return records


def configure_native_head(npc, race, facial=None):
    data = bytearray(race.values(b'DATA')[0])
    flags = struct.unpack_from('<I', data, 32)[0]
    new_flags = (flags | FACEGEN_HEAD_FLAG) if facial else (flags & ~FACEGEN_HEAD_FLAG)
    struct.pack_into('<I', data, 32, new_flags)
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
    facial = load_facial_manifest(output)
    if facial:
        validate_facial_assets(output, settings)
        logging.info('Facial HeadParts active: %d BSDynamicTriShape parts with .tri morphs in FaceGeom',
                     len(facial['parts']))
        return
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


def validate_head_visibility(generated, settings, output=None):
    by_name = {record.editor_id: record for record in generated}
    by_id = {record.form_id: record for record in generated}
    npc, race = (by_name[settings.prefix + name] for name in ('NPC', 'Race'))
    facial = load_facial_manifest(output) if output is not None else None
    has_facegen = bool(struct.unpack_from('<I', race.values(b'DATA')[0], 32)[0] & FACEGEN_HEAD_FLAG)
    if npc.values(b'PNAM') != [struct.pack('<I', EMPTY_HEAD_ID)]:
        raise ValueError('NPC still uses native human head parts')
    if race.values(b'HEAD') != [struct.pack('<I', EMPTY_HEAD_ID)] * 2:
        raise ValueError('Race still supplies native human head parts')
    if by_id[HEAD_RACES_ID].values(b'LNAM') != [struct.pack('<I', race.form_id)]:
        raise ValueError('Head race list must belong only to this private race')
    head = by_id.get(EMPTY_HEAD_ID)
    if head is None or head.kind != b'HDPT' or head.values(b'PNAM') != [struct.pack('<I', 1)]:
        raise ValueError('Private face head part is missing')
    if head.values(b'RNAM') != [struct.pack('<I', HEAD_RACES_ID)]:
        raise ValueError('Face head part must belong only to this private race')

    if not facial:
        if has_facegen:
            raise ValueError('Race still enables native FaceGen head generation')
        expected = (settings.asset_dir.replace('/', '\\') + '\\native_head_empty.nif\0').encode('utf8')
        if head.values(b'MODL') != [expected] or head.values(b'HNAM') or head.values(b'NAM1'):
            raise ValueError('Native head must have only the empty model, without extra parts/morphs')
        return {'native_head_geometry': 'empty', 'native_facegen_enabled': False,
                'depends_on_equipped_head_cover': False, 'game_verified': False}

    if not has_facegen:
        raise ValueError('Race must enable FaceGen head flag when VRM facial expressions are active')
    appearance_armo = by_name.get(settings.prefix + 'Appearance')
    if appearance_armo is not None and appearance_armo.kind == b'ARMO':
        bod2_mask = struct.unpack_from('<I', appearance_armo.values(b'BOD2')[0], 0)[0]
        if bod2_mask & 1:
            raise ValueError('Appearance ARMO occupies slot 30 (HEAD), which hides SBP_130_HEAD facial FaceGeom')
    parts = facial['parts']
    extra_ids = facial_extra_ids(facial)
    if head.editor_id != parts[0]['edid']:
        raise ValueError(f"Primary HDPT EDID mismatch: {head.editor_id} != {parts[0]['edid']}")
    if head.values(b'MODL') != [_mesh_relative(parts[0]['nif'])]:
        raise ValueError('Primary facial HDPT MODL path mismatch')
    if head.values(b'NAM0') != [struct.pack('<I', 1)] or head.values(b'NAM1') != [_mesh_relative(parts[0]['tri'])]:
        raise ValueError('Primary facial HDPT must bind expression TRI with NAM0=1')
    if head.values(b'HNAM') != [struct.pack('<I', fid) for fid in extra_ids]:
        raise ValueError('Primary facial HDPT HNAM extra-part list mismatch')
    for extra_id, part in zip(extra_ids, parts[1:]):
        extra = by_id.get(extra_id)
        if extra is None or extra.kind != b'HDPT' or extra.editor_id != part['edid']:
            raise ValueError(f"Extra facial HDPT missing or EDID mismatch: {part['edid']}")
        if extra.values(b'DATA') != [b'\x0E'] or extra.values(b'PNAM') != [struct.pack('<I', 0)]:
            raise ValueError(f"Extra facial HDPT flags/type mismatch: {part['edid']}")
        if extra.values(b'MODL') != [_mesh_relative(part['nif'])]:
            raise ValueError(f"Extra facial HDPT MODL mismatch: {part['edid']}")
        if extra.values(b'NAM0') != [struct.pack('<I', 1)] or extra.values(b'NAM1') != [_mesh_relative(part['tri'])]:
            raise ValueError(f"Extra facial HDPT must bind expression TRI with NAM0=1: {part['edid']}")
        if extra.values(b'RNAM') != [struct.pack('<I', HEAD_RACES_ID)]:
            raise ValueError(f"Extra facial HDPT race list mismatch: {part['edid']}")
    return {'native_head_geometry': 'vrm_facial_headpart', 'native_facegen_enabled': True,
            'facial_parts': len(parts), 'depends_on_equipped_head_cover': False, 'game_verified': False}
