"""Native avatar/full-CS GPU comparison and controlled illumination sweep.

Only writes the supplied workspace output. Never changes deployed shaders,
game settings, follower NIFs or the game's compiled shader cache.
"""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from toon import control_bytes  # noqa: E402
from toon_gpu_fixture import build, scene  # noqa: E402


def unmark(source, destination):
    """Remove only marker bindings in the isolated fixture scene."""
    blob = source.read_bytes()
    count = struct.unpack_from('<I', blob, 4)[0]
    result, offset = bytearray(blob[:8]), 8
    for _ in range(count):
        header = bytearray(blob[offset:offset+24])
        nv, ni = struct.unpack_from('<II', header)
        struct.pack_into('<I', header, 8, 0)
        result += header
        offset += 24
        for index in range(3):
            length = struct.unpack_from('<I', blob, offset)[0]
            offset += 4
            value = blob[offset:offset+length] if index != 2 else b''
            result += struct.pack('<I', len(value))+value
            offset += length
        length = nv*32+ni*4
        result += blob[offset:offset+length]
        offset += length
    if offset != len(blob):
        raise ValueError('Fixture scene size mismatch')
    destination.write_bytes(result)


def sphere(output):
    """Uniform curved surface isolates lighting from baked texture detail."""
    vertices, indices = [], []
    for row in range(49):
        theta = np.pi*row/48
        for column in range(97):
            phi = 2*np.pi*column/96
            normal = [np.sin(theta)*np.cos(phi), np.sin(theta)*np.sin(phi), np.cos(theta)]
            vertices.append([*normal, *normal, column/96, row/48])
    for row in range(48):
        for column in range(96):
            a = row*97+column
            indices += [a, a+97, a+1, a+1, a+97, a+98]
    params = {'shade': [.85]*3, 'toony': .95, 'shift': 0, 'gi_equalization': 1}
    control = output/'probe-control.dds'
    control.write_bytes(control_bytes(params))
    paths = []
    for name, rgba in [('probe-color', [180, 180, 180, 255]), ('probe-normal', [128, 128, 255, 255])]:
        # Same valid uncompressed DX10 container, with constant RGBA pixels.
        blob = bytearray(control_bytes(params))
        blob[148:] = bytes(rgba)*32
        path = output/(name+'.dds')
        path.write_bytes(blob)
        paths.append(path)
    paths.append(control)
    data = bytearray(struct.pack('<II5If', 0x32535456, 1, len(vertices), len(indices), 2, 1 << 20, 0, 1.))
    for path in paths:
        encoded = str(path.resolve()).encode('utf8')
        data += struct.pack('<I', len(encoded))+encoded
    data += np.asarray(vertices, dtype='<f4').tobytes()+np.asarray(indices, dtype='<u4').tobytes()
    path = output/'sphere.scene'
    path.write_bytes(data)
    return path


def measure(folder):
    samples = {}
    for mode in ['legacy', 'linear']:
        for power in [5, 100, 400, 1600]:
            for kind in ['old', 'new']:
                key = f'{kind}-{mode}-{power}'
                pixels = np.asarray(Image.open(folder/f'sphere-{key}.ppm'))
                mask = np.any(pixels != [31, 36, 46], axis=2)
                values = pixels[mask]
                red = values[:, 0]
                frequencies = np.bincount(red, minlength=256)
                samples[key] = {'clipped_fraction': float(np.mean(np.max(values, axis=1) >= 254)),
                                'mean': float(values.mean()),
                                'red_p10': float(np.percentile(red, 10)),
                                'red_p90': float(np.percentile(red, 90)),
                                'two_band_fraction': float(np.sort(frequencies)[-2:].sum()/len(values))}
    (folder/'quality-metrics.json').write_text(json.dumps(samples, indent=2), encoding='utf8')
    for mode in ['legacy', 'linear']:
        normal = samples[f'new-{mode}-100']
        if normal['red_p90']-normal['red_p10'] < 30 or normal['two_band_fraction'] < .85:
            raise ValueError('Toon bands not visible: '+mode)
        if samples[f'new-{mode}-5']['mean'] >= normal['mean']*.8:
            raise ValueError('Dim light did not darken marked surface: '+mode)
        for power in [400, 1600]:
            if samples[f'old-{mode}-{power}']['clipped_fraction'] < .9:
                raise ValueError('Bright-light fixture did not reproduce clipping: '+mode)
            if samples[f'new-{mode}-{power}']['clipped_fraction'] > .01:
                raise ValueError('Marked bright-light clipping: '+mode)
    return samples


def comparison(folder):
    items = [('Original CS', 'original.ppm'), ('Prototype 1', 'old.ppm'), ('Prototype 2', 'toon.ppm'),
             ('Activation check', 'diagnostic.ppm')]
    canvas = Image.new('RGB', (4*480, 630), (28, 30, 34))
    draw = ImageDraw.Draw(canvas)
    for i, (label, filename) in enumerate(items):
        image = Image.open(folder/filename)
        image.thumbnail((480, 600))
        canvas.paste(image, (i*480, 30))
        draw.text((i*480+15, 8), label, fill='white')
    canvas.save(folder/'comparison.png')
    canvas = Image.new('RGB', (2*720, 930), (28, 30, 34))
    draw = ImageDraw.Draw(canvas)
    for i, (label, filename) in enumerate([('Prototype 1: strong light', 'old-bright.ppm'),
                                         ('Prototype 2: same light', 'toon-bright.ppm')]):
        canvas.paste(Image.open(folder/filename), (i*720, 30))
        draw.text((i*720+15, 8), label, fill='white')
    canvas.save(folder/'comparison-bright.png')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--marked', type=Path, required=True)
    parser.add_argument('--shaders', type=Path, required=True)
    parser.add_argument('--old-shaders', type=Path, required=True)
    parser.add_argument('--diagnostic-shaders', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    scene(args.marked, output/'marked.scene')
    unmark(output/'marked.scene', output/'base.scene')
    curved = sphere(output)
    build(output)
    subprocess.run([str(output/'toon_gpu.exe'), str(output/'base.scene'), str(output/'marked.scene'),
                    str((args.shaders/'original-cutout.cso').resolve()),
                    str((args.shaders/'toon-cutout.cso').resolve()), str(output/'renders'),
                    str((args.old_shaders/'toon-cutout.cso').resolve()),
                    str((args.diagnostic_shaders/'toon-cutout.cso').resolve()),
                    str((args.shaders/'toon-reflection-deferred.cso').resolve()), str(curved)], check=True)
    samples = measure(output/'renders')
    comparison(output/'renders')
    print(json.dumps(samples, indent=2))


if __name__ == '__main__':
    main()
