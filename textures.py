import argparse
import json
import logging
import locale
import math
from pathlib import Path
import subprocess

from PIL import Image
from dds import texture_format, validate_dds
from settings import load_settings

ROOT = Path(__file__).resolve().parent


def bake_base_color(image, factor):
    """Bake linear glTF RGB multipliers into sRGB pixels, keeping texture alpha."""
    if len(factor) != 3 or any(type(n) not in (int, float) or not math.isfinite(n) or not 0 <= n <= 1
                               for n in factor):
        raise ValueError('Invalid base-color RGB factor')
    tables = []
    for multiplier in factor:
        for value in range(256):
            srgb = value / 255
            linear = srgb / 12.92 if srgb <= .04045 else ((srgb + .055) / 1.055) ** 2.4
            tinted = linear * multiplier
            encoded = tinted * 12.92 if tinted <= .0031308 else 1.055 * tinted ** (1 / 2.4) - .055
            tables.append(round(encoded * 255))
    return image.convert('RGBA').point(tables + list(range(256)))


def convert_textures(output):
    output = Path(output).resolve()
    sources = json.loads((output / "textures.json").read_text(encoding="utf-8"))
    settings = load_settings(output)
    flat = output / "texture-sources/flat_n.png"
    Image.new("RGBA", (16, 16), (128, 128, 255, 0)).save(flat)
    sources.append({"png": str(flat), "relative": f"textures/{settings.asset_dir}/flat_n.dds", "normal": True})
    for source in sources:
        dest = output / "mod" / source["relative"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        source_png = Path(source['png'])
        with Image.open(source_png) as image:
            size = image.size
            factor = source.get('base_color_factor', [1, 1, 1])
            if factor != [1, 1, 1]:
                if source.get('normal'):
                    raise ValueError('Diffuse color factor cannot tint a normal map')
                baked = output / 'texture-bakes' / source_png.name
                baked.parent.mkdir(parents=True, exist_ok=True)
                bake_base_color(image, factor).save(baked)
                source_png = baked
                logging.info('Baked diffuse RGB %s: linear factor %s; source alpha unchanged', dest.name, factor)
        format_name = texture_format(size)
        if format_name != 'BC7_UNORM':
            logging.info('DDS %s: %sx%s uses uncompressed RGBA8 to preserve original pixels',
                         dest.name, *size)
        command = [str(ROOT / "dependencies/texconv.exe"), "-nologo", "-y", "-m", "0",
                   "-f", format_name]
        if format_name != 'BC7_UNORM':
            command += ['-dx10']
        command += ['-o', str(dest.parent)]
        if not source.get("normal"):
            command += ["-srgb"]
        command.append(str(source_png))
        result = subprocess.run(command, text=True, capture_output=True, encoding=locale.getencoding(), errors='replace')
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        if not dest.exists():
            raise RuntimeError(f"Texture not produced: {dest}")
        validate_dds(dest, expected_size=size, expected_format=format_name)
        logging.info("DDS ready: %s (%sx%s %s, %s bytes)", dest.name, *size,
                     format_name, dest.stat().st_size)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    convert_textures(parser.parse_args().output)
