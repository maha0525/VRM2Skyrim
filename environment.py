"""Find local tools and game installations without developer-specific defaults."""
import os
from pathlib import Path
import re
import shutil


def find_game():
    candidates = [os.environ.get("SKYRIM_PATH", "")]
    steam = [Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Steam"]
    if os.name == "nt":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                steam.append(Path(winreg.QueryValueEx(key, "SteamPath")[0]))
        except OSError:
            pass
    for root in list(steam):
        libraries = root / "steamapps/libraryfolders.vdf"
        if libraries.exists():
            steam += [Path(value.replace("\\\\", "\\")) for value in
                      re.findall(r'"path"\s+"([^\"]+)"', libraries.read_text(encoding="utf8"))]
    candidates += [root / "steamapps/common/Skyrim Special Edition" for root in steam]
    for candidate in candidates:
        if candidate and (Path(candidate) / "Data/Skyrim.esm").is_file():
            return Path(candidate).resolve()
    return None


def find_blender():
    candidates = [os.environ.get("BLENDER_PATH", ""), shutil.which("blender")]
    roots = [Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Blender Foundation",
             Path(__file__).resolve().parent / "dependencies/blender",
             Path.home() / "AppData/Local/SAIVerse/Tools/Blender"]
    for root in roots:
        if root.exists():
            candidates += sorted(root.glob("**/blender.exe"), reverse=True)
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    return None
