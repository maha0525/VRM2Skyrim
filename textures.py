import argparse
import json
import logging
import locale
from pathlib import Path
import subprocess

from PIL import Image
from settings import load_settings

ROOT = Path(__file__).resolve().parent


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
        command = [str(ROOT / "dependencies/texconv.exe"), "-nologo", "-y", "-m", "0",
                   "-f", "BC7_UNORM", "-o", str(dest.parent)]
        if not source.get("normal"):
            command += ["-srgb"]
        command.append(source["png"])
        result = subprocess.run(command, text=True, capture_output=True, encoding=locale.getencoding(), errors='replace')
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        if not dest.exists():
            raise RuntimeError(f"Texture not produced: {dest}")
        logging.info("DDS ready: %s (%s bytes)", dest.name, dest.stat().st_size)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    convert_textures(parser.parse_args().output)
