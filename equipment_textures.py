"""Reuse existing game texture paths without adding missing-mod dependencies."""
import hashlib
import json
import logging
from pathlib import Path
import struct

from bsa import BSA
from game_assets import GameAssets, asset_name
from settings import load_settings

LOG = logging.getLogger(__name__)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class RuntimeTextures:
    def __init__(self, data, official):
        self.data = Path(data)
        official = {p.resolve() for p in official}
        self.others = [p for p in self.data.glob('*.bsa') if p.resolve() not in official]
        self.archives = {}

    def matches(self, name, digest, archive_digest):
        loose = self.data/name
        if loose.is_file():
            return sha(loose.read_bytes()) == digest
        for path in self.others:
            if path not in self.archives:
                try:
                    self.archives[path] = BSA(path)
                except (OSError, ValueError, UnicodeError, struct.error):
                    LOG.warning('Cannot rule out texture overrides in %s; retaining private textures', path.name)
                    self.archives[path] = None
            if self.archives[path] is None or name in self.archives[path].entries:
                return False
        return digest == archive_digest


def shared_candidates(output, game_data, plan):
    """Require an official fallback path and identical currently resolved bytes."""
    output, game_data = Path(output).resolve(), Path(game_data).resolve()
    settings = load_settings(output)
    assets = GameAssets(game_data, plan['plugins'], output/'shared-textures')
    runtime = RuntimeTextures(game_data, assets.paths)
    result = {}
    private_root = (output/'mod/textures'/settings.asset_dir/'equipment').resolve()
    for original, relative in plan['textures'].items():
        if not relative:
            continue
        file = (output/'mod'/relative).resolve()
        if not file.is_relative_to(private_root) or not file.is_file():
            continue
        name = asset_name(original, 'textures')
        try:
            archive_path, archive = assets.archive_source(name, 'textures')
        except FileNotFoundError:
            continue  # A replacer's additional files remain self-contained.
        digest = sha(file.read_bytes())
        archive_digest = sha(archive.read(name))
        if plan.get('source_profile', settings.fit_source) != 'installed' and archive_digest != digest:
            continue
        if not runtime.matches(name, digest, archive_digest):
            continue
        result[relative.lower().replace('\\', '/')] = {
            'path': name, 'archive': archive_path.name, 'sha256': digest,
            'archive_sha256': archive_digest,
            'private_path': relative.lower().replace('\\', '/'),
            'preview': file.stem+'.png', 'bytes': file.stat().st_size}
    return result


def compact(output, game_data):
    """Rewrite fitted NIF texture references and retire only proven duplicates."""
    from custom_skeleton import NifFile
    output = Path(output).resolve()
    settings = load_settings(output)
    plan_path = output/'armor-fit-plan.json'
    plan = json.loads(plan_path.read_text(encoding='utf8'))
    entries = shared_candidates(output, game_data, plan)
    previous = output/'equipment-textures.json'
    prior = json.loads(previous.read_text(encoding='utf8'))['textures'] if previous.is_file() else []
    if prior:
        validate_shared(output)
        entries.update((e['private_path'], e) for e in prior)
    shared = {e['path']: e for e in prior}
    shared.update((e['path'], e) for e in entries.values())
    report = {'schema': 1, 'game_data': str(Path(game_data).resolve()), 'plugins': plan['plugins'],
              'source_profile': plan.get('source_profile', settings.fit_source),
              'textures': list(shared.values())}
    mesh_dir = output/'mod/meshes'/settings.asset_dir
    profile = json.loads((output/'armor-fitting.json').read_text(encoding='utf8'))
    for name in sorted({e['file'] for e in profile['equipment']}):
        path = mesh_dir/name
        changed = False
        with NifFile(str(path)) as nif:
            for shape in nif.shapes:
                shape_changed = False
                for slot, texture in shape.textures.items():
                    entry = entries.get(texture.lower().replace('\\', '/'))
                    if entry:
                        shape.set_texture(slot, entry['path'].replace('/', '\\'))
                        changed = True
                        shape_changed = True
                if shape_changed and shape.shader.blockname == 'BSEffectShaderProperty':
                    shape.save_shader_attributes()
                    shape.write_properties()
            if changed:
                nif.save()
        if changed:
            path.with_name(path.name.replace('_1.nif', '_0.nif')).write_bytes(path.read_bytes())
        with NifFile(str(path)) as nif:
            if any(t.lower().replace('\\', '/') in entries for s in nif.shapes for t in s.textures.values()):
                raise ValueError('Shared texture reference did not survive export: '+name)
    plan['textures'] = {k: entries.get(v.lower().replace('\\', '/'), {}).get('path', v)
                        for k, v in plan['textures'].items()}
    plan_path.write_text(json.dumps(plan, indent=2), encoding='utf8')
    previous.write_text(json.dumps(report, indent=2), encoding='utf8')
    validate_shared(output)
    # Keep source DDS files in the work area so Blender can build its materials
    # without depending on the application's LZ4 runtime or the installed game.
    preview_root = (output/'preview-assets').resolve()
    preview_assets = GameAssets(game_data,plan['plugins'],preview_root,installed=True)
    for relative, entry in entries.items():
        file = (output/'mod'/relative).resolve()
        target = (preview_root/entry['path']).resolve()
        if not target.is_relative_to(preview_root):
            raise ValueError('Unsafe preview texture destination')
        if file.is_file():
            if not file.is_relative_to((output/'mod/textures'/settings.asset_dir/'equipment').resolve()):
                raise ValueError('Unsafe private texture source')
            target.parent.mkdir(parents=True,exist_ok=True)
            file.replace(target)
        elif not target.is_file():
            preview_assets.extract(entry['path'],'textures')
        if sha(target.read_bytes()) != entry['sha256']:
            raise ValueError('Preview texture differs from selected equipment: '+entry['path'])
    LOG.info('Official equipment texture reuse: %d images, %.1f MiB of duplicate DDS omitted',
             len(entries), sum(e['bytes'] for e in entries.values())/2**20)
    return report


def shared_report(output):
    path = Path(output)/'equipment-textures.json'
    if not path.is_file():
        return None
    report = json.loads(path.read_text(encoding='utf8'))
    if report.get('schema') != 1 or not isinstance(report.get('textures'), list):
        raise ValueError('Invalid shared equipment texture manifest')
    for entry in report['textures']:
        if (not isinstance(entry.get('path'), str) or entry['path'] != asset_name(entry['path'], 'textures')
                or not isinstance(entry.get('private_path'), str)
                or entry['private_path'] != asset_name(entry['private_path'], 'textures')
                or any(not isinstance(entry.get(k), str) or '/' in entry[k] or '\\' in entry[k]
                       or ':' in entry[k] or entry[k] in ('', '.', '..') for k in ('archive', 'preview'))
                or not entry['preview'].endswith('.png')
                or not isinstance(entry.get('sha256'), str) or len(entry['sha256']) != 64
                or any(c not in '0123456789abcdef' for c in entry['sha256'])
                or not isinstance(entry.get('archive_sha256'), str) or len(entry['archive_sha256']) != 64
                or any(c not in '0123456789abcdef' for c in entry['archive_sha256'])):
            raise ValueError('Invalid shared equipment texture entry')
    return report


def validate_shared(output):
    """Verify declared official dependencies instead of allowing arbitrary files."""
    report = shared_report(output)
    if report is None:
        return {}
    assets = GameAssets(report['game_data'], report['plugins'], Path(output)/'shared-textures')
    runtime = RuntimeTextures(report['game_data'], assets.paths)
    result = {}
    settings = load_settings(output)
    if report.get('source_profile', 'official') != settings.fit_source:
        raise ValueError('Shared texture profile differs from follower settings')
    private_prefix = 'textures/'+settings.asset_dir+'/equipment/'
    for e in report['textures']:
        name = asset_name(e['path'], 'textures')
        if name != e['path'] or name in result or not e['private_path'].startswith(private_prefix):
            raise ValueError('Invalid or duplicate shared texture path')
        archive_path, archive = assets.archive_source(name, 'textures')
        if archive_path.name != e['archive'] or sha(archive.read(name)) != e['archive_sha256']:
            raise ValueError('Shared official texture differs from fitted source: '+name)
        if report.get('source_profile', 'official') != 'installed' and e['sha256'] != e['archive_sha256']:
            raise ValueError('Official texture profile must retain the original image: '+name)
        if not runtime.matches(name, e['sha256'], e['archive_sha256']):
            raise ValueError('Shared official texture is overridden; regenerate equipment: '+name)
        result[name] = e
    return result


def preview_image(output, texture):
    """Preserve unique decoded images even when runtime paths share basenames."""
    output = Path(output)
    name = texture.lower().replace('\\', '/')
    report = shared_report(output)
    if report:
        matches = [e for e in report['textures'] if name == e['path'] or name.endswith('/'+e['path'])]
        if not matches:
            basename = name.rsplit('/', 1)[-1]
            matches = [e for e in report['textures'] if e['path'].rsplit('/', 1)[-1] == basename]
        if len(matches) > 1:
            raise ValueError('Ambiguous shared texture in preview: '+texture)
        if matches:
            return output/'dds-preview'/matches[0]['preview']
    return output/'dds-preview'/(name.rsplit('/', 1)[-1].rsplit('.', 1)[0]+'.png')


def prepare_preview_assets(output, paths):
    """Make selected archive images discoverable before Blender builds materials."""
    from custom_skeleton import NifFile
    output = Path(output)
    report = shared_report(output)
    if not report:
        return None
    shared = {e['path']:e for e in report['textures']}
    needed = set()
    for path in paths:
        with NifFile(str(Path(path).resolve())) as nif:
            needed.update(t.lower().replace('\\','/') for s in nif.shapes for t in s.textures.values()
                          if t.lower().replace('\\','/') in shared)
    root = output/'preview-assets'
    for name in needed:
        file = root/name
        if not file.is_file() or sha(file.read_bytes()) != shared[name]['sha256']:
            raise ValueError('Preview texture differs from selected equipment: '+name)
    LOG.info('Prepared %d shared equipment textures in preview workspace',len(needed))
    return root
