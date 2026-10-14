"""Catch DDSs that decode on the CPU but cannot become D3D11 textures."""
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest

from PIL import Image

from dds import texture_format, validate_dds
from settings import FollowerSettings
from textures import bake_base_color, convert_textures

ROOT = Path(__file__).resolve().parents[1]


def fixture(width, height, dxgi=98, mips=1, faces=1):
    header = bytearray(148)
    header[:4] = b'DDS '
    struct.pack_into('<7I', header, 4, 124, 0x2100F, height, width, 0, 0, mips)
    struct.pack_into('<II4s', header, 76, 32, 4, b'DX10')
    struct.pack_into('<I', header, 108, 0x401008)
    struct.pack_into('<5I', header, 128, dxgi, 3, 4 if faces == 6 else 0, 1, 0)
    payload = 0
    for _ in range(mips):
        payload += (((width + 3) // 4) * ((height + 3) // 4) * 16 if dxgi == 98
                    else width * height * 4) * faces
        width, height = max(1, width // 2), max(1, height // 2)
    return bytes(header) + bytes(payload)


class DDSContractTests(unittest.TestCase):
    def test_material_tint_uses_linear_rgb_and_preserves_alpha(self):
        source = Image.new('RGBA', (2, 1))
        source.putdata([(255, 128, 64, 72), (128, 255, 200, 0)])
        self.assertEqual(list(bake_base_color(source, [1, 1, 1]).getdata()), list(source.getdata()))
        self.assertEqual(list(bake_base_color(source, [0, 0, 0]).getdata()), [(0, 0, 0, 72), (0, 0, 0, 0)])
        # Half linear intensity is brighter than multiplying the encoded byte by .5.
        self.assertEqual(bake_base_color(source, [.5, .5, .5]).getpixel((0, 0)), (188, 92, 44, 72))
        self.assertEqual(source.getpixel((0, 0)), (255, 128, 64, 72))
        for invalid in ([1, 1], [1, 1, float('nan')], [1, -1, 1], [1, 2, 1]):
            with self.assertRaisesRegex(ValueError, 'factor'):
                bake_base_color(source, invalid)

    def test_small_and_unaligned_images_keep_their_dimensions_without_compression(self):
        for size in [(1, 1), (2, 2), (4, 2), (6, 5), (1025, 1024)]:
            self.assertEqual(texture_format(size), 'R8G8B8A8_UNORM')
        for size in [(4, 4), (8, 4), (1024, 1024), (16384, 4)]:
            self.assertEqual(texture_format(size), 'BC7_UNORM')
        for size in [(0, 4), (-1, 4), (16385, 4), (True, 4)]:
            with self.assertRaises(ValueError):
                texture_format(size)

    def test_regression_2x2_bc7_is_rejected_even_with_complete_mips(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tiny.dds'
            path.write_bytes(fixture(2, 2, mips=2))
            with self.assertRaisesRegex(ValueError, 'Direct3D rejects 2x2'):
                validate_dds(path)

    def test_only_the_top_level_must_be_block_aligned(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'valid.dds'
            path.write_bytes(fixture(4, 4, mips=3))
            result = validate_dds(path, (4, 4), 'BC7_UNORM')
            self.assertEqual(result['mip_levels'], 3)
            self.assertEqual(result['minimum_bytes'], 196)

    def test_rgba8_can_be_small_and_non_square(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'valid.dds'
            path.write_bytes(fixture(2, 3, dxgi=28, mips=2))
            result = validate_dds(path, (2, 3), 'R8G8B8A8_UNORM')
            self.assertFalse(result['compressed'])
            with self.assertRaisesRegex(ValueError, 'dimensions changed'):
                validate_dds(path, (4, 4))
            with self.assertRaisesRegex(ValueError, 'format differs'):
                validate_dds(path, expected_format='BC7_UNORM')

    def test_incomplete_headers_payloads_and_excess_mips_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'invalid.dds'
            for data in [b'not a DDS', fixture(4, 4)[:140], fixture(4, 4)[:-1],
                         fixture(4, 4, mips=4)]:
                path.write_bytes(data)
                with self.assertRaises(ValueError):
                    validate_dds(path)

    def test_cubemap_payload_counts_all_faces(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cube.dds'
            path.write_bytes(fixture(4, 4, mips=3, faces=6))
            self.assertEqual(validate_dds(path)['minimum_bytes'], 436)
            path.write_bytes(path.read_bytes()[:-1])
            with self.assertRaisesRegex(ValueError, 'Truncated DDS mip payload'):
                validate_dds(path)


@unittest.skipUnless(os.name == 'nt' and (ROOT / 'dependencies/texconv.exe').is_file(),
                     'Pinned Windows texconv required')
class NativeTextureTests(unittest.TestCase):
    def test_material_bakes_survive_dds_and_reconversion_without_changing_source_pngs(self):
        native_temp = ROOT / 'build/native-texture-tests'
        native_temp.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=native_temp) as directory:
            output = Path(directory)
            sources = output / 'texture-sources'
            sources.mkdir()
            settings = FollowerSettings(mod_id='TintContract')
            settings.save(output / 'settings.json')
            original = Image.new('RGBA', (2, 2))
            original.putdata([(255, 255, 255, 72), (128, 255, 64, 0),
                              (32, 200, 90, 255), (200, 0, 255, 128)])
            manifest, hashes = [], {}
            for index, factor in enumerate(([0, 0, 0], [.42578125, .2890625, .421875119], [1, 1, 1])):
                png = sources / f'shared_{index}.png'
                original.save(png)
                hashes[png] = hashlib.sha256(png.read_bytes()).hexdigest()
                manifest.append({'png': str(png), 'relative': f'textures/{settings.asset_dir}/{png.stem}.dds',
                                 'base_color_factor': factor})
            (output / 'textures.json').write_text(json.dumps(manifest), encoding='utf8')
            for _ in range(2):
                convert_textures(output)
                for entry in manifest:
                    with Image.open(output / 'mod' / entry['relative']) as decoded:
                        self.assertEqual(decoded.convert('RGBA').tobytes(),
                                         bake_base_color(original, entry['base_color_factor']).tobytes())
                for png, digest in hashes.items():
                    self.assertEqual(hashlib.sha256(png.read_bytes()).hexdigest(), digest)

    def test_actual_pipeline_preserves_tiny_pixels_alpha_and_source_files(self):
        native_temp = ROOT / 'build/native-texture-tests'
        native_temp.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=native_temp) as directory:
            output = Path(directory)
            sources = output / 'texture-sources'
            sources.mkdir()
            settings = FollowerSettings(mod_id='TextureContract')
            settings.save(output / 'settings.json')
            manifest, originals = [], {}
            sizes = [(1, 1), (2, 2), (3, 5), (6, 2), (4, 4), (8, 4)]
            for index, size in enumerate(sizes):
                image = Image.new('RGBA', size)
                image.putdata([(i * 19 % 256, i * 31 % 256, 205, i * 47 % 256)
                               for i in range(size[0] * size[1])])
                png = sources / f'fixture_{index}.png'
                image.save(png)
                originals[png] = hashlib.sha256(png.read_bytes()).hexdigest()
                manifest.append({'png': str(png), 'relative': f'textures/{settings.asset_dir}/fixture_{index}.dds'})
            (output / 'textures.json').write_text(json.dumps(manifest), encoding='utf8')
            convert_textures(output)
            # Re-running the shared pipeline must preserve the same choices.
            convert_textures(output)
            for index, item in enumerate(manifest):
                size = sizes[index]
                target = output / 'mod' / item['relative']
                info = validate_dds(target, size, texture_format(size))
                self.assertEqual(info['compressed'], index >= 4)
                if not info['compressed']:
                    with Image.open(item['png']) as source, Image.open(target) as decoded:
                        self.assertEqual(decoded.convert('RGBA').tobytes(), source.convert('RGBA').tobytes())
            for path, digest in originals.items():
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)


if __name__ == '__main__':
    unittest.main()
