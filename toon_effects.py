"""Version 3 source atlas for shade, MatCap, rim mask and tangent normals."""
import hashlib
import json
import logging
from pathlib import Path
import struct
import subprocess

import numpy as np
from PIL import Image

from dds import validate_dds
from toon_shade import ROOT, WRAP_CODES, metadata_pixels, shade_image

MAP_NAMES = ('shade', 'matcap', 'rim_mask', 'normal')
FLOAT_FIELDS = ('rim_r', 'rim_g', 'rim_b', 'rim_power', 'rim_lift', 'rim_mix',
                'outline_r', 'outline_g', 'outline_b', 'outline_mix')
METADATA_BLOCKS = 102


def effects_for(material, outline=False):
    mtoon = material.get('extensions', {}).get('VRMC_materials_mtoon', {})
    values = [*mtoon.get('parametricRimColorFactor', [0, 0, 0]),
              mtoon.get('parametricRimFresnelPowerFactor', 5.), mtoon.get('parametricRimLiftFactor', 0.),
              mtoon.get('rimLightingMixFactor', 1.), *mtoon.get('outlineColorFactor', [0, 0, 0]),
              mtoon.get('outlineLightingMixFactor', 1.)]
    result = dict(zip(FLOAT_FIELDS, values))
    result['normal_scale'] = material.get('normalTexture', {}).get('scale', 1.)
    if len(values) != len(FLOAT_FIELDS) or not all(np.isfinite(v) for v in result.values()):
        raise ValueError('Invalid authored MToon effect controls')
    if any(result[k] < 0 for k in ['rim_r', 'rim_g', 'rim_b', 'rim_power', 'outline_r', 'outline_g', 'outline_b']):
        raise ValueError('Negative MToon effect colour/power')
    if any(not 0 <= result[k] <= 1 for k in ['rim_mix', 'outline_mix']):
        raise ValueError('Invalid MToon lighting mix')
    result['outline'] = bool(outline)
    return result


def images_for(document, binary, material):
    mtoon = material['extensions']['VRMC_materials_mtoon']
    images = [shade_image(document, binary, material)[0]]
    for key, factor in [('matcapTexture', mtoon.get('matcapFactor', [1, 1, 1])),
                        ('rimMultiplyTexture', [1, 1, 1]), ('normalTexture', [1, 1, 1])]:
        info = material.get(key) if key == 'normalTexture' else mtoon.get(key)
        if info is None or (key == 'matcapTexture' and not any(factor)):
            images.append(None)
            continue
        synthetic = {'extensions': {'VRMC_materials_mtoon': {
            'shadeMultiplyTexture': info, 'shadeColorFactor': factor}}}
        images.append(shade_image(document, binary, synthetic)[0])
    return images


def atlas_layout(images):
    boxes = [(i, (im.width+11)//4*4, (im.height+11)//4*4) for i, im in enumerate(images) if im is not None]
    minimum = max(METADATA_BLOCKS*4, max(w for _, w, _ in boxes))
    candidates = sorted({minimum, *[min(16384, minimum*n) for n in [2, 3, 4]]})
    layouts = []
    for width in candidates:
        x = y = row = 0
        rectangles = [None]*4
        for i, w, h in boxes:
            if x+w > width:
                y += row
                x = row = 0
            rectangles[i] = [x+4, y+4, images[i].width, images[i].height, *images[i].info['wrap']]
            x += w
            row = max(row, h)
        height = y+row+4
        if width <= 16384 and height <= 16384:
            layouts.append((width*height, width, height, rectangles))
    if not layouts:
        raise ValueError('MToon source atlas exceeds Direct3D texture limits')
    _, width, height, rectangles = min(layouts, key=lambda item: (item[0], item[1]))
    return (width, height), rectangles


def effect_metadata(parameters, rectangles, effects):
    shade = rectangles[0]
    result = metadata_pixels(parameters, shade[2:4], shade[4:])
    result[8] = (0, 0, 0, 64)
    result.append((0, 0, 0, 0))  # slot 15 reserved
    for rect in rectangles:
        values = [0]*10 if rect is None else [v for n in rect[:4] for v in [n & 255, n >> 8]]+[WRAP_CODES[n] for n in rect[4:]]
        result += [(0, 0, 0, v) for v in values]
    result.append((0, 0, 0, sum(1 << i for i, rect in enumerate(rectangles) if rect is not None)))
    for key in FLOAT_FIELDS:
        result += [(0, 0, 0, v) for v in struct.pack('<f', effects[key])]
    result.append((0, 0, 0, int(effects['outline'])))
    result += [(0, 0, 0, v) for v in struct.pack('<f', effects['normal_scale'])]
    assert len(result) == METADATA_BLOCKS
    return result


def pack_material(images, parameters, effects):
    size, rectangles = atlas_layout(images)
    atlas = Image.new('RGBA', size)
    modes = {10497: 'wrap', 33071: 'edge', 33648: 'symmetric'}
    for image, rect in zip(images, rectangles):
        if image is None:
            continue
        x, y, _, _, u, v = rect
        data = np.pad(np.asarray(image), ((0, 0), (4, 4), (0, 0)), mode=modes[u])
        data = np.pad(data, ((4, 4), (0, 0), (0, 0)), mode=modes[v])
        atlas.paste(Image.fromarray(data), (x-4, y-4))
    for i, rgba in enumerate(effect_metadata(parameters, rectangles, effects)):
        atlas.paste(rgba, (i*4, size[1]-4, i*4+4, size[1]))
    return atlas, rectangles


def validate_material(path, parameters, report):
    validate_dds(path, report['size'], report['format'])
    if hashlib.sha256(Path(path).read_bytes()).hexdigest() != report['sha256']:
        raise ValueError('Authored MToon atlas changed')
    if report['source_size'] != report['rectangles'][0][2:4]:
        raise ValueError('Authored MToon source domain changed')
    expected = np.asarray(effect_metadata(parameters, report['rectangles'], report['effects']))
    with Image.open(path) as image:
        actual = np.asarray(image.convert('RGBA').crop((0, image.height-4, METADATA_BLOCKS*4, image.height-3)))[0, ::4].astype(int)
    if np.max(np.abs(actual-expected)) > 1 or not np.array_equal(actual[8:], expected[8:]):
        raise ValueError('Authored MToon source domain/effect controls changed in DDS')


def build_material(output, document, binary, material, parameters, outline=False):
    effects = effects_for(material, outline)
    images = images_for(document, binary, material)
    atlas, rectangles = pack_material(images, parameters, effects)
    # Unaligned or tiny inputs keep exact pixels, even if atlas padding is BC-aligned.
    format_name = ('BC7_UNORM' if all(im is None or (im.width >= 64 and im.width % 4 == 0 and im.height % 4 == 0)
                                    for im in images) else 'R8G8B8A8_UNORM')
    key = hashlib.sha256(atlas.tobytes()+json.dumps([atlas.size, format_name]).encode()).hexdigest()[:16]
    folder = Path(output)/'toon-shade-cache'
    folder.mkdir(exist_ok=True)
    png, dds, complete = [folder/(key+suffix) for suffix in ['.png', '.dds', '.json']]
    report = {'profile': 'authored_material', 'metadata_version': 3, 'size': list(atlas.size),
              'format': format_name, 'source_size': list(images[0].size), 'rectangles': rectangles, 'effects': effects}
    if not (dds.exists() and complete.exists()):
        atlas.save(png)
        args = [str(ROOT/'dependencies/texconv.exe'), '-nologo', '-y', '-f', format_name, '-m', '1', '-o', str(folder)]
        if format_name != 'BC7_UNORM':
            args.append('-dx10')
        # Atlas includes linear normal data; no global sRGB processing is valid.
        run = subprocess.run([*args, str(png)], capture_output=True)
        if run.returncode:
            raise RuntimeError('MToon atlas encoding failed: '+(run.stdout+run.stderr).decode(errors='replace'))
        report['sha256'] = hashlib.sha256(dds.read_bytes()).hexdigest()
        validate_material(dds, parameters, report)
        complete.write_text(json.dumps({'sha256': report['sha256']}), encoding='utf8')
    report['sha256'] = json.loads(complete.read_text(encoding='utf8'))['sha256']
    validate_material(dds, parameters, report)
    logging.info('MToon effect atlas %s: %s, maps %s; outline=%s', dds.name, atlas.size,
                 [name for name, image in zip(MAP_NAMES, images) if image is not None], outline)
    return dds.read_bytes(), report
