"""Download the pinned exporter into this project; never change Blender preferences."""
import hashlib
import json
import logging
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
TAG = "V29.1.0"
URL = f"https://github.com/BadDogSkyrim/PyNifly/releases/download/{TAG}/io_scene_nifly.zip"
PYNIFLY_HASH = "fa52960650fc81dc1e4ac41538c86ba838f9defc9b0fc73e864348a8b5a46dd6"
TEXCONV_HASH = "dcfdec10244e02cf5037fba089c55fb7e1326b1c8181742d77d15fa5cb5eef06"


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    deps = ROOT / "dependencies"
    deps.mkdir(exist_ok=True)
    archive = deps / f"pynifly-{TAG}.zip"
    if not archive.exists():
        logging.info("Downloading %s", URL)
        req = urllib.request.Request(URL, headers={"User-Agent": "VRM-Skyrim-Converter"})
        with urllib.request.urlopen(req, timeout=120) as response:
            archive.write_bytes(response.read())
    if hashlib.sha256(archive.read_bytes()).hexdigest() != PYNIFLY_HASH:
        raise ValueError("Pinned PyNifly archive hash mismatch")
    with zipfile.ZipFile(archive) as package:
        for entry in package.infolist():
            target = (deps / entry.filename).resolve()
            if not target.is_relative_to(deps.resolve()):
                raise ValueError("Unsafe archive entry")
        package.extractall(deps)
    texture_url = "https://github.com/microsoft/DirectXTex/releases/download/may2026/texconv.exe"
    texture_tool = deps / "texconv.exe"
    if not texture_tool.exists():
        logging.info("Downloading %s", texture_url)
        request = urllib.request.Request(texture_url, headers={"User-Agent": "VRM-Skyrim-Converter"})
        with urllib.request.urlopen(request, timeout=120) as response:
            texture_tool.write_bytes(response.read())
    if hashlib.sha256(texture_tool.read_bytes()).hexdigest() != TEXCONV_HASH:
        raise ValueError("Pinned texconv binary hash mismatch")
    (deps / "manifest.json").write_text(json.dumps({
        "pynifly_tag": TAG, "url": URL,
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "texconv_url": texture_url,
        "texconv_sha256": hashlib.sha256(texture_tool.read_bytes()).hexdigest(),
    }, indent=2), encoding="utf-8")
    logging.info("PyNifly ready: %s", deps)


if __name__ == "__main__":
    main()
