"""Wizard-time original weapon preview: cached avatar, weapon model and renders; never creates a MOD."""
from dataclasses import asdict
import hashlib
import json
import logging
from pathlib import Path
import shutil
import time

from bsa import BSA
from converter import ROOT, convert_appearance, doctor, prepare_source, run_blender
from head_preview import digest, file_identity, new_output, publish, ready_output
from settings import FollowerSettings
from textures import decode_dds

LOG = logging.getLogger(__name__)
SCHEMA = 'weapon-preview-1'
VIEWS = ('drawn', 'hand', 'sheathed', 'compare')
ARCHIVES = ('Skyrim - Meshes0.bsa', 'Skyrim - Meshes1.bsa', 'Skyrim - Animations.bsa')


def fit(*args, **kwargs):
    # Portable cache tests do not require the native NIF library.
    from armor_fitting import fit as fit_native
    return fit_native(*args, **kwargs)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def archives(data):
    return [file_identity(Path(data)/name) for name in ARCHIVES]


def texture_archives(data):
    """The archives weapon.shared_environment searches for ShinyDull_e.dds."""
    return [file_identity(Path(data)/f'Skyrim - Textures{i}.bsa') for i in range(9)]


def base_model(catalog, editor_id):
    """(kind, NIF path) of an original-weapon base; only the wizard's candidates are accepted."""
    record = catalog.require(editor_id, b'WEAP')
    kind = catalog.original_weapon_kind(record)
    if kind is None:
        raise ValueError(f'{editor_id} is not an original-weapon base')
    return kind, record.values(b'MODL')[0].rstrip(b'\0').decode('utf8')


def base_dimensions(workspace, data, catalog, editor_id):
    """Length and grip fraction of the base's vanilla NIF, as convert_weapon measures it."""
    from game_assets import GameAssets
    from weapon_nif import base_dimensions as measure
    kind, model = base_model(catalog, editor_id)
    root = Path(workspace)/'weapon-bases'/digest(archives(data))
    cache = root/'dimensions.json'
    known = json.loads(cache.read_text(encoding='utf8')) if cache.is_file() else {}
    if model.lower() not in known:
        known[model.lower()] = measure(GameAssets(data, [], root).extract(model))
        root.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(known, indent=2), encoding='utf8')
    return {'base': editor_id, 'kind': kind, 'model': model, **known[model.lower()]}


def drawn_animation(data, refs, kind):
    """Extract the vanilla combat idle used for the drawn-weapon pose into the reference cache."""
    from weapon_nif import DRAWN_IDLES
    name = 'meshes/actors/character/animations/' + DRAWN_IDLES[kind]
    if not (refs/name).is_file():
        BSA(Path(data)/'Skyrim - Animations.bsa').extract(name, refs/name)


def valid_image(path):
    from PIL import Image
    try:
        with Image.open(path) as image:
            image.verify()
        return True
    except (OSError, ValueError):
        return False


def prepare_avatar(source, game, blender, settings, root, key, progress):
    """The follower's converted appearance without NPC, weapon or MOD packaging."""
    values = {**asdict(settings), 'mod_id': 'Preview_'+key, 'fit_mode': 'selected', 'fit_armors': [],
              'physics_enabled': False, 'sitting_enabled': False, 'toon_enabled': False, 'render_previews': False,
              'weapon_mode': 'official', 'original_weapon': {}}
    prepared = FollowerSettings.from_dict(values)
    progress('プレビューを準備しています…')
    base = new_output(root/'avatars', key)
    prepare_source(source, base, prepared)
    convert_appearance(source, game, blender, base, prepared, progress)
    if prepared.head_switch_enabled:
        run_blender(blender, 'head_variants_blender.py', ['--output', base], base, 'Head variants')
    if prepared.skin_partition_enabled:
        progress('身体と衣服を準備しています…')
        fit(base, game/'Data', blender, skin_only=True)
        if any(g['slot'] in (32, 33, 34, 37, 38) for g in prepared.appearance_parts['garments']):
            run_blender(blender, 'standard_clothing_blender.py', ['--output', base], base, 'Preview clothing')
    progress('テクスチャを準備しています…')
    for texture in (base/'mod/textures').rglob('*.dds'):
        decode_dds(texture, base/'dds-preview')
    publish(base, key)
    return base


def publish_textures(output, root, key):
    """Publish a placement output's converted DDS and decoded PNGs as the texture cache entry."""
    cache = new_output(root/'weapon-textures', key)
    report = json.loads((output/'weapon-textures-report.json').read_text(encoding='utf8'))
    for name in ['settings.json', 'weapon-textures-report.json', *('mod/'+r for r in report['textures']),
                 *(p.relative_to(output).as_posix() for p in (output/'dds-preview').glob('*.png'))]:
        (cache/name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(output/name, cache/name)
    publish(cache, key)
    return cache


def prepare_weapon(glb, game, blender, settings, catalog, root, key, textures, progress):
    """weapon.nif built by the same convert_weapon as a conversion; textures: a texture cache
    entry for this GLB (its DDS are copied, its PNGs drawn), or None to convert and decode them."""
    from weapon import convert_weapon
    progress('武器のモデルを作っています…')
    output = new_output(root/'weapons', key)
    # One asset folder for every preview, so converted textures fit any placement.
    prepared = FollowerSettings.from_dict({**asdict(settings), 'mod_id': 'PreviewWeapon'})
    prepared.save(output/'settings.json')
    convert_weapon(glb, game/'Data', blender, output, prepared, catalog, textures=textures)
    if textures is None:
        for texture in (output/'mod/textures').rglob('*.dds'):
            decode_dds(texture, output/'dds-preview')
    pngs = (textures or output)/'dds-preview'
    progress('元の武器と並べています…')
    plan = json.loads((output/'weapon-plan.json').read_text(encoding='utf8'))
    run_blender(blender, 'weapon_compare_blender.py',
                ['--weapon-nif', output/'mod'/plan['nif'], '--weapon-textures', pngs,
                 '--base-nif', plan['base_nif'], '--output', output/'compare.png'], output, 'Weapon comparison')
    publish(output, key)
    return output, plan


def preview(workspace, source, glb, game, blender, settings, catalog, progress):
    started = time.perf_counter()
    source, glb, game, blender = Path(source), Path(glb), Path(game), Path(blender)
    checks = doctor(game, blender)
    if not all(checks.values()):
        raise ValueError('Missing preview prerequisites: '+', '.join(k for k, v in checks.items() if not v))
    weapon = settings.original_weapon
    if settings.weapon_mode != 'original' or not weapon:
        raise ValueError('オリジナル武器を選んでください')
    glb_hash = sha256(glb)
    if glb_hash != weapon['sha256']:
        raise ValueError('オリジナル武器の設定は別のGLB用です。設定したときと同じGLBを選び直してください')
    code = hashlib.sha256(b''.join(p.read_bytes() for p in sorted(ROOT.glob('*.py')))).hexdigest()
    root = Path(workspace)/'weapon-preview-cache'
    avatar_key = digest(dict(schema=SCHEMA, code=code, source=sha256(source), armor_support=settings.armor_support,
                             parts=settings.appearance_parts, heads=settings.appearance_heads, sex=settings.sex,
                             height=settings.height_scale, assets=archives(game/'Data'), blender=file_identity(blender)))
    base = ready_output(root/'avatars', avatar_key)
    avatar_reused = base is not None
    if base is None:
        base = prepare_avatar(source, game, blender, settings, root, avatar_key, progress)
    # Converted 4096² textures depend on the GLB alone (and the game's environment map);
    # placement changes rebuild only the NIF and the renders.
    texture_key = digest(dict(schema=SCHEMA, code=code, glb=glb_hash, assets=texture_archives(game/'Data')))
    textures = ready_output(root/'weapon-textures', texture_key)
    textures_reused = textures is not None
    weapon_key = digest(dict(schema=SCHEMA, code=code, glb=glb_hash, textures=texture_key, assets=archives(game/'Data'),
                             blender=file_identity(blender), master=file_identity(game/'Data/Skyrim.esm'),
                             update=file_identity(game/'Data/Update.esm'),
                             weapon={k: weapon[k] for k in ('kind', 'base', 'grip', 'length', 'flip', 'roll')}))
    built = ready_output(root/'weapons', weapon_key)
    if built is not None and (textures is None or not valid_image(built/'compare.png')):
        built = None
    weapon_reused = built is not None
    if built is None:
        built, plan = prepare_weapon(glb, game, blender, settings, catalog, root, weapon_key, textures, progress)
        if textures is None:
            textures = publish_textures(built, root, texture_key)
    else:
        plan = json.loads((built/'weapon-plan.json').read_text(encoding='utf8'))
    render_key = digest(dict(avatar=avatar_key, weapon=weapon_key))
    previews = [f'previews/weapon-{render_key}-{view}.png' for view in VIEWS]
    render_reused = all(valid_image(base/p) for p in previews)
    if not render_reused:
        progress('武器を持たせて描画しています…')
        refs = Path(json.loads((base/'references.json').read_text(encoding='utf8'))['root'])
        drawn_animation(game/'Data', refs, weapon['kind'])
        run_blender(blender, 'render_blender.py',
                    ['--output', base, '--weapon-preview', render_key, '--weapon-nif', built/'mod'/plan['nif'],
                     '--weapon-textures', textures/'dds-preview', '--weapon-kind', weapon['kind']], base, 'Weapon preview')
        shutil.copyfile(built/'compare.png', base/previews[3])
    report = json.loads((built/'weapon.json').read_text(encoding='utf8'))
    elapsed = time.perf_counter()-started
    LOG.info('Weapon preview ready in %.2fs: avatar_reused=%s textures_reused=%s weapon_reused=%s render_reused=%s',
             elapsed, avatar_reused, textures_reused, weapon_reused, render_reused)
    return dict(output=str(base), previews=previews, views=list(VIEWS), avatar_reused=avatar_reused,
                textures_reused=textures_reused, weapon_reused=weapon_reused, render_reused=render_reused,
                elapsed_seconds=round(elapsed, 2),
                weapon_triangles=report['source']['triangles'], base_dimensions=report['base_dimensions'],
                weapon_settings={k: weapon[k] for k in ('kind', 'base', 'grip', 'length', 'flip', 'roll')})
