"""Persistent avatar, fitted-headgear and render caches; never create a MOD."""
from dataclasses import asdict
import hashlib
import json
import logging
from pathlib import Path
import shutil
import time
import uuid

from converter import ROOT, convert_appearance, doctor, prepare_source, run_blender
from game_assets import GameAssets
from official_catalog import OfficialCatalog
from settings import FollowerSettings
from textures import decode_dds

LOG = logging.getLogger(__name__)
SCHEMA = 'head-preview-assets-1'


def fit(*args, **kwargs):
    # Portable cache tests and startup do not require the native NIF library.
    from armor_fitting import fit as fit_native
    return fit_native(*args, **kwargs)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:24]


def file_identity(path):
    path = Path(path)
    if not path.is_file():
        return [str(path), None]
    stat = path.stat()
    return [str(path), stat.st_size, stat.st_mtime_ns]


def deployed_path(data, kind, name):
    name = name.lower().replace('\\', '/')
    return data/name if name.startswith(kind+'/') else data/kind/name


def source_assets(data, catalog, settings, armor=None):
    """Track official archives and deployed reference/replacer inputs."""
    paths = set(GameAssets(data, catalog.plugins, data).paths)
    paths.update(data.glob('*.bsa'))  # An additional archive can shadow a reusable texture.
    paths.update(data/name for name in catalog.plugins)
    if settings.fit_source == 'installed':
        prefix = 'female' if settings.sex == 'female' else 'male'
        names = [f'actors/character/character assets/{prefix}{part}_1.nif' for part in ('body', 'hands', 'feet')]
        names += [f'actors/character/character assets/{prefix}head.nif',
                  'actors/character/character assets female/skeleton_female.nif' if settings.sex == 'female'
                  else 'actors/character/character assets/skeleton.nif']
        if armor is not None:
            names += [a.values(catalog.model_tag(a, settings.sex))[0].rstrip(b'\0').decode('utf8')
                      for a in catalog.addon_records(armor, settings.sex)]
        for name in names:
            path = deployed_path(data, 'meshes', name)
            paths.add(path)
            if armor is not None and path.is_file():
                from custom_skeleton import NifFile
                with NifFile(str(path)) as nif:
                    for shape in nif.shapes:
                        paths.update(deployed_path(data, 'textures', t) for t in shape.textures.values() if t)
        if armor is not None:
            # Alternate texture sets can refer to files outside the NIF's own
            # material list. Include deployed official TXST inputs as well.
            for record in catalog.by_id.values():
                if record.kind == b'TXST':
                    for tag, blob in record.fields:
                        if tag in (b'TX00', b'TX01', b'TX02', b'TX03', b'TX04', b'TX05', b'TX06', b'TX07'):
                            paths.add(deployed_path(data, 'textures', blob.rstrip(b'\0').decode('utf8')))
    return [file_identity(p) for p in sorted(paths)]


def ready_output(root, key):
    for path in sorted(root.glob(key+'_*'), reverse=True):
        try:
            marker = json.loads((path/'preview-ready.json').read_text(encoding='utf8'))
            if marker['key'] == key and marker['schema'] == SCHEMA and all(
                    file_identity(path/name)[1:] == identity for name, identity in marker['files'].items()):
                return path
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return None


def publish(output, key):
    files = [output/'settings.json', output/'appearance.json', *list((output/'mod').rglob('*'))]
    files += [p for p in (output/'armor-fitting.json', output/'armor-source/body.nif',
                          output/'equipment-textures.json') if p.is_file()]
    files += list((output/'dds-preview').glob('*.png'))
    files += [p for p in (output/'preview-assets').rglob('*') if p.is_file()]
    marker = dict(key=key, schema=SCHEMA, files={p.relative_to(output).as_posix(): file_identity(p)[1:]
                                              for p in files if p.is_file()})
    path = output/'preview-ready.tmp'
    path.write_text(json.dumps(marker), encoding='utf8')
    path.replace(output/'preview-ready.json')


def new_output(root, key):
    path = root/(key+'_'+uuid.uuid4().hex[:8])
    path.mkdir(parents=True)
    return path


def preview(workspace, source, game, blender, settings, armor_id, policy, progress):
    started = time.perf_counter()
    source, game, blender = Path(source), Path(game), Path(blender)
    checks = doctor(game, blender)
    if not all(checks.values()):
        raise ValueError('Missing preview prerequisites: '+', '.join(k for k, v in checks.items() if not v))
    catalog = OfficialCatalog(game/'Data')
    armor = catalog.require(armor_id, b'ARMO')
    code = hashlib.sha256(b''.join(p.read_bytes() for p in sorted(ROOT.glob('*.py')))).hexdigest()
    base_key = digest(dict(schema=SCHEMA, code=code, source=hashlib.sha256(source.read_bytes()).hexdigest(),
                           parts=settings.appearance_parts, heads=settings.appearance_heads,
                           sex=settings.sex, height=settings.height_scale, profile=settings.fit_source,
                           assets=source_assets(game/'Data', catalog, settings), blender=file_identity(blender)))
    root = Path(workspace)/'head-preview-cache'
    base = ready_output(root/'avatars', base_key)
    avatar_reused = base is not None
    values = {**asdict(settings), 'mod_id': 'Preview_'+base_key, 'fit_mode': 'all_official', 'fit_armors': [],
              'physics_enabled': False, 'sitting_enabled': False, 'toon_enabled': False, 'render_previews': False}
    prepared = FollowerSettings.from_dict(values)
    if base is None:
        progress('プレビューを準備しています…')
        base = new_output(root/'avatars', base_key)
        prepare_source(source, base, prepared)
        convert_appearance(source, game, blender, base, prepared, progress)
        progress('身体と衣服を準備しています…')
        fit(base, game/'Data', blender, skin_only=True)
        if any(g['slot'] in (32, 33, 34, 37, 38) for g in prepared.appearance_parts['garments']):
            run_blender(blender, 'standard_clothing_blender.py', ['--output', base], base, 'Preview clothing')
        progress('テクスチャを準備しています…')
        for texture in (base/'mod/textures').rglob('*.dds'):
            decode_dds(texture, base/'dds-preview')
        publish(base, base_key)
    LOG.info('Head preview avatar: %s (%s)', base_key, 'reused' if avatar_reused else 'prepared')
    prepared = FollowerSettings.load(base/'settings.json')
    gear_key = digest(dict(avatar=base_key, armor=catalog.key(armor),
                           assets=source_assets(game/'Data', catalog, settings, armor)))
    output = ready_output(root/'equipment', gear_key)
    equipment_reused = output is not None
    if output is None:
        progress('頭装備を合わせています…')
        output = new_output(root/'equipment', gear_key)
        shutil.copytree(base, output, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('*.blend', '*.blend1', '*.log', '*.npz',
                                                     'preview-ready.*', 'texture-sources', 'texture-bakes'))
        prepared.fit_mode = 'selected'
        prepared.fit_armors = [catalog.key(armor)]
        prepared.save(output/'settings.json')
        fit(output, game/'Data', blender, reuse_body=True)
        publish(output, gear_key)
    LOG.info('Head preview equipment: %s (%s)', catalog.key(armor), 'reused' if equipment_reused else 'fitted')
    render_key = digest({**policy, 'toon': settings.toon_enabled})
    relative = f'previews/head-{render_key}.png'
    image = output/relative
    render_reused = image.is_file()
    if render_reused:
        from PIL import Image
        try:
            with Image.open(image) as saved:
                saved.verify()
        except (OSError, ValueError):
            render_reused = False
    if not render_reused:
        progress('プレビューを描画しています…')
        arguments = ['--output', output, '--wardrobe', 'armor:'+armor.editor_id, '--keep-clothes', '--head-closeup',
                     '--hide-face' if policy['hide_face'] else '--no-hide-face',
                     '--hide-hair' if policy['hide_hair'] else '--no-hide-hair',
                     '--toon' if settings.toon_enabled else '--no-toon']
        run_blender(blender, 'render_blender.py', arguments, output, 'Headgear preview')
        shutil.copyfile(output/f'previews/wardrobe-armor-{armor.editor_id}-rest-01.png', image)
    elapsed = time.perf_counter()-started
    LOG.info('Head preview ready in %.2fs: avatar_reused=%s equipment_reused=%s render_reused=%s',
             elapsed, avatar_reused, equipment_reused, render_reused)
    return dict(output=str(output), previews=[relative], avatar_reused=avatar_reused,
                equipment_reused=equipment_reused, render_reused=render_reused, elapsed_seconds=round(elapsed, 2))
