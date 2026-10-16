"""Authored face shade textures using the already-bound native glow slot.

RGB contains the source shade surface. A four-pixel metadata row, outside its
UV domain, uses constant BC7 blocks. Never require a second engine binding.
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


def shade_image(document, binary, material):
    mtoon = material.get('extensions', {}).get('VRMC_materials_mtoon', {})
    info = mtoon.get('shadeMultiplyTexture')
    if info is None:
        image, source = Image.new('RGBA', (64, 4), 'white'), b'white'
    else:
        transform = info.get('extensions', {}).get('KHR_texture_transform', {})
        if (info.get('texCoord', 0) != 0 or transform.get('texCoord', 0) != 0
                or transform.get('offset', [0, 0]) != [0, 0]
                or transform.get('scale', [1, 1]) != [1, 1]
                or transform.get('rotation', 0) != 0):
            raise ValueError('Authored face shade needs the source UV0 transform to be preserved')
        texture = document['textures'][info['index']]
        sampler = document['samplers'][texture['sampler']] if 'sampler' in texture else {}
        if any(sampler.get(key, 10497) != 10497 for key in ['wrapS', 'wrapT']):
            raise ValueError('Authored face shade currently requires repeat texture addressing')
        image = document['images'][texture['source']]
        view = document['bufferViews'][image['bufferView']]
        start = view.get('byteOffset', 0)
        source = binary[start:start+view['byteLength']]
        image = Image.open(io.BytesIO(source)).convert('RGBA')
    factor = mtoon.get('shadeColorFactor', [0, 0, 0])
    if len(factor) != 3 or not all(np.isfinite(v) and 0 <= v <= 1 for v in factor):
        raise ValueError('Authored face shade colour is outside supported [0, 1] range')
    image = bake_base_color(image, factor)
    # RGB is the shade term; texture alpha does not affect MToon shade colour.
    image.putalpha(255)
    width, height = image.size
    if width < 64 or width % 4 or height % 4 or height+12 > 16384:
        raise ValueError(f'Authored face shade dimensions cannot carry BC7 metadata: {image.size}')
    source_key = hashlib.sha256(source+json.dumps(factor).encode()).hexdigest()
    return image, source_key


def metadata_pixels(parameters):
    # Nine 4x4 constant blocks, including version=1; never filter the metadata.
    # Match legacy slot indices 2..7, with authored version in slot 8.
    values = [1, 1, *parameters['shade'], parameters['toony'],
              (parameters['shift']+1)/2, parameters['gi_equalization'], 1]
    if any(not np.isfinite(v) or not 0 <= v <= 1 for v in values):
        raise ValueError('Invalid authored face control parameter')
    return [(255, 0, 255, 255), (0, 255, 0, 255)]+[(0, 0, 0, round(v*255)) for v in values[2:]]


def validate_shade(path, parameters, expected_size, expected_hash):
    validate_dds(path, expected_size, 'BC7_UNORM')
    if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected_hash:
        raise ValueError('Authored face shade DDS changed')
    with Image.open(path) as image:
        row = image.convert('RGBA').crop((0, image.height-4, 36, image.height-3))
        actual = np.asarray(row)[0, ::4].astype(int)
    if np.max(np.abs(actual-np.asarray(metadata_pixels(parameters)))) > 1:
        raise ValueError('Authored face metadata did not survive BC7 encoding')


def build_shade(output, document, binary, material, parameters):
    image, source_key = shade_image(document, binary, material)
    key = hashlib.sha256(('repeat-gutters-v1:'+source_key+json.dumps(parameters, sort_keys=True)).encode()).hexdigest()[:16]
    folder = Path(output)/'toon-shade-cache'
    folder.mkdir(exist_ok=True)
    png, dds, complete = folder/(key+'.png'), folder/(key+'.dds'), folder/(key+'.json')
    packed = Image.new('RGBA', (image.width, image.height+12))
    packed.paste(image.crop((0, image.height-4, image.width, image.height)), (0, 0))
    packed.paste(image, (0, 4))
    packed.paste(image.crop((0, 0, image.width, 4)), (0, image.height+4))
    for index, rgba in enumerate(metadata_pixels(parameters)):
        packed.paste(rgba, (index*4, image.height+8, (index+1)*4, image.height+12))
    # Content-addressed input: a prior completed result may be reused only after
    # its format, hash and decoded metadata have passed validation below.
    if not (dds.exists() and complete.exists()):
        packed.save(png)
        result = subprocess.run([str(ROOT/'dependencies/texconv.exe'), '-nologo', '-y',
                                 '-f', 'BC7_UNORM', '-m', '1', '-srgb', '-o', str(folder), str(png)],
                                capture_output=True)
        if result.returncode:
            raise RuntimeError('Face shade compression failed: '+(result.stdout+result.stderr).decode(errors='replace'))
        sha = hashlib.sha256(dds.read_bytes()).hexdigest()
        validate_shade(dds, parameters, packed.size, sha)
        complete.write_text(json.dumps({'sha256': sha}), encoding='utf8')
    sha = json.loads(complete.read_text(encoding='utf8'))['sha256']
    validate_shade(dds, parameters, packed.size, sha)
    logging.info('Authored face shade: %s; source RGB %sx%s, metadata outside UV; zero native emission',
                 dds.name, image.width, image.height)
    return dds.read_bytes(), {'profile': 'authored_face', 'size': list(packed.size),
                              'sha256': sha, 'source_sha256': source_key}
