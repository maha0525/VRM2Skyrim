"""Authored MToon shade textures using the already-bound native glow slot.

RGB contains the source shade surface. A four-pixel metadata row, outside its
UV domain, uses constant four-pixel blocks. Never require a second engine binding.
"""
import hashlib
import io
import json
import logging
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image

from dds import validate_dds
from textures import bake_base_color

ROOT = Path(__file__).resolve().parent
WRAP_CODES = {10497: 0, 33071: 128, 33648: 255}


def shade_image(document, binary, material):
    mtoon = material.get('extensions', {}).get('VRMC_materials_mtoon', {})
    info = mtoon.get('shadeMultiplyTexture')
    wrap = [10497, 10497]
    if info is None:
        image, source = Image.new('RGBA', (64, 4), 'white'), b'white'
    else:
        transform = info.get('extensions', {}).get('KHR_texture_transform', {})
        if (info.get('texCoord', 0) != 0 or transform.get('texCoord', 0) != 0
                or transform.get('offset', [0, 0]) != [0, 0]
                or transform.get('scale', [1, 1]) != [1, 1]
                or transform.get('rotation', 0) != 0):
            raise ValueError('Authored MToon shade needs the source UV0 transform to be preserved')
        texture = document['textures'][info['index']]
        sampler = document['samplers'][texture['sampler']] if 'sampler' in texture else {}
        wrap = [sampler.get(key, 10497) for key in ['wrapS', 'wrapT']]
        if any(mode not in WRAP_CODES for mode in wrap):
            raise ValueError('Invalid source shade texture addressing')
        image = document['images'][texture['source']]
        view = document['bufferViews'][image['bufferView']]
        start = view.get('byteOffset', 0)
        source = binary[start:start+view['byteLength']]
        image = Image.open(io.BytesIO(source)).convert('RGBA')
    factor = mtoon.get('shadeColorFactor', [0, 0, 0])
    if len(factor) != 3 or not all(np.isfinite(v) and 0 <= v <= 1 for v in factor):
        raise ValueError('Authored MToon shade colour is outside supported [0, 1] range')
    image = bake_base_color(image, factor)
    # RGB is the shade term; texture alpha does not affect MToon shade colour.
    image.putalpha(255)
    if image.width+8 > 16384 or image.height+12 > 16384:
        raise ValueError(f'Authored MToon shade exceeds native texture limits: {image.size}')
    image.info['wrap'] = wrap
    source_key = hashlib.sha256(source+json.dumps([factor, wrap]).encode()).hexdigest()
    return image, source_key


def metadata_pixels(parameters, source_size=None, wrap=None):
    # Constant 4x4 blocks; version 1=255, version 2=128. Never filter metadata.
    # Match legacy slot indices 2..7, with authored version in slot 8.
    values = [1, 1, *parameters['shade'], parameters['toony'],
              (parameters['shift']+1)/2, parameters['gi_equalization'], 1]
    if any(not np.isfinite(v) or not 0 <= v <= 1 for v in values):
        raise ValueError('Invalid authored MToon control parameter')
    result = [(255, 0, 255, 255), (0, 255, 0, 255)]+[(0, 0, 0, round(v*255)) for v in values[2:]]
    if source_size is not None:
        result[8] = (0, 0, 0, 128)
        width, height = source_size
        extra = [width & 255, width >> 8, height & 255, height >> 8,
                 *[WRAP_CODES[mode] for mode in wrap]]
        result += [(0, 0, 0, v) for v in extra]
    return result


def pack_shade(image, parameters):
    """Keep source pixels and resolution; padding carries wrap borders/metadata."""
    wrap = image.info['wrap']
    size = (max(64, (image.width+11)//4*4), (image.height+15)//4*4)
    packed = Image.new('RGBA', size)
    pixels = np.asarray(image)
    modes = {10497: 'wrap', 33071: 'edge', 33648: 'symmetric'}
    pixels = np.pad(pixels, ((0, 0), (4, 4), (0, 0)), mode=modes[wrap[0]])
    pixels = np.pad(pixels, ((4, 4), (0, 0), (0, 0)), mode=modes[wrap[1]])
    packed.paste(Image.fromarray(pixels), (0, 0))
    for index, rgba in enumerate(metadata_pixels(parameters, image.size, wrap)):
        packed.paste(rgba, (index*4, size[1]-4, (index+1)*4, size[1]))
    return packed


def validate_shade(path, parameters, expected_size, expected_hash, source_size=None, wrap=None, format_name='BC7_UNORM'):
    validate_dds(path, expected_size, format_name)
    if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected_hash:
        raise ValueError('Authored MToon shade DDS changed')
    with Image.open(path) as image:
        expected = metadata_pixels(parameters, source_size, wrap)
        row = image.convert('RGBA').crop((0, image.height-4, len(expected)*4, image.height-3))
        actual = np.asarray(row)[0, ::4].astype(int)
    if np.max(np.abs(actual-np.asarray(expected))) > 1:
        raise ValueError('Authored MToon metadata did not survive DDS encoding')
    if source_size is not None and not np.array_equal(actual[8:], np.asarray(expected)[8:]):
        raise ValueError('Authored MToon source domain did not survive DDS encoding exactly')


def build_shade(output, document, binary, material, parameters):
    image, source_key = shade_image(document, binary, material)
    wrap = image.info['wrap']
    # Tiny/unaligned sources have high-contrast edges inside BC7 blocks. Retain
    # their exact source pixels rather than compressing away authored detail.
    format_name = ('BC7_UNORM' if image.width >= 64 and image.height >= 4
                   and image.width % 4 == 0 and image.height % 4 == 0 else 'R8G8B8A8_UNORM')
    key = hashlib.sha256(('source-domain-v2:'+format_name+source_key+json.dumps(parameters, sort_keys=True)).encode()).hexdigest()[:16]
    folder = Path(output)/'toon-shade-cache'
    folder.mkdir(exist_ok=True)
    png, dds, complete = folder/(key+'.png'), folder/(key+'.dds'), folder/(key+'.json')
    packed = pack_shade(image, parameters)
    # Content-addressed input: a prior completed result may be reused only after
    # its format, hash and decoded metadata have passed validation below.
    if not (dds.exists() and complete.exists()):
        packed.save(png)
        args = [str(ROOT/'dependencies/texconv.exe'), '-nologo', '-y', '-f', format_name,
                '-m', '1', '-srgb', '-o', str(folder)]
        if format_name != 'BC7_UNORM':
            args.append('-dx10')
        result = subprocess.run([*args, str(png)], capture_output=True)
        if result.returncode:
            raise RuntimeError('MToon shade compression failed: '+(result.stdout+result.stderr).decode(errors='replace'))
        sha = hashlib.sha256(dds.read_bytes()).hexdigest()
        validate_shade(dds, parameters, packed.size, sha, image.size, wrap, format_name)
        complete.write_text(json.dumps({'sha256': sha}), encoding='utf8')
    sha = json.loads(complete.read_text(encoding='utf8'))['sha256']
    validate_shade(dds, parameters, packed.size, sha, image.size, wrap, format_name)
    logging.info('Authored MToon shade: %s; source RGB %sx%s %s, wrap %s, metadata outside UV; zero native emission',
                 dds.name, image.width, image.height, format_name, wrap)
    return dds.read_bytes(), {'profile': 'authored_material', 'size': list(packed.size),
                              'metadata_version': 2, 'source_size': list(image.size), 'wrap': wrap, 'format': format_name,
                              'sha256': sha, 'source_sha256': source_key}
