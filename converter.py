"""VRM2Skyrim: shared local follower pipeline for the CLI and wizard."""
import argparse
import hashlib
import importlib.util
import json
import logging
from pathlib import Path
import subprocess
import sys
import zipfile
from datetime import datetime

from bsa import BSA
from build_npc import build_npc
from environment import find_blender, find_game
from game_catalog import GameCatalog
from inspect_vrm import inspect
from settings import FollowerSettings, VERSION, load_settings
from textures import convert_textures

ROOT = Path(__file__).resolve().parent


def doctor(game, blender):
    data = Path(game) / "Data" if game else Path("__missing_game__")
    return {"blender": bool(blender and Path(blender).is_file()), "skyrim_master": (data / "Skyrim.esm").is_file(),
            "game_meshes": all((data / name).is_file() for name in ("Skyrim - Meshes0.bsa", "Skyrim - Meshes1.bsa")),
            "game_animations": (data / "Skyrim - Animations.bsa").is_file(),
            "pynifly": (ROOT / "dependencies/io_scene_nifly/NiflyDLL.dll").is_file(),
            "texconv": (ROOT / "dependencies/texconv.exe").is_file(),
            **{name: importlib.util.find_spec(name) is not None for name in ("numpy", "scipy", "PIL", "lz4")}}


def references(game_data, sex="female"):
    fingerprint = str(Path(game_data).resolve())
    for name in ("Skyrim - Meshes0.bsa", "Skyrim - Meshes1.bsa", "Skyrim - Animations.bsa"):
        stat = (game_data / name).stat()
        fingerprint += f"|{name}:{stat.st_size}:{stat.st_mtime_ns}"
    root = ROOT / "reference" / hashlib.sha256(fingerprint.encode()).hexdigest()[:16]
    skeleton_name = ("meshes/actors/character/character assets female/skeleton_female.nif" if sex == "female"
                     else "meshes/actors/character/character assets/skeleton.nif")
    mesh_names = (skeleton_name, "meshes/weapons/steel/steelsword.nif")
    for name in mesh_names:
        if (root / name).exists():
            continue
        for archive in ("Skyrim - Meshes0.bsa", "Skyrim - Meshes1.bsa"):
            bsa = BSA(game_data / archive)
            if name in bsa.entries:
                bsa.extract(name, root / name)
                break
        else:
            raise FileNotFoundError(f"Reference mesh not found: {name}")
    animations = ("meshes/actors/character/character assets/skeleton.hkx",
                  f"meshes/actors/character/animations/{sex}/mt_walkforward.hkx",
                  "meshes/actors/character/animations/1hm_attackright.hkx")
    if any(not (root / name).exists() for name in animations):
        archive = BSA(game_data / "Skyrim - Animations.bsa")
        for name in animations:
            if not (root / name).exists():
                archive.extract(name, root / name)
    return root / skeleton_name


def run_blender(blender, script, arguments, output, label):
    command = [str(blender), "--background", "--factory-startup", "--python-exit-code", "1",
               "--python", str(ROOT / script), "--", *map(str, arguments)]
    logging.info("%s ...", label)
    log_path = output / (label.replace(" ", "-").lower() + ".log")
    with log_path.open("w", encoding="utf8") as log:
        result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        tail = "\n".join(log_path.read_text(encoding="utf8", errors="replace").splitlines()[-24:])
        raise RuntimeError(f"{label} failed. Log: {log_path}\n{tail}")
    logging.info("%s finished", label)


def package(output, settings=None):
    output = Path(output)
    settings = settings or load_settings(output)
    mod = output / "mod"
    metadata = mod / settings.asset_dir
    metadata.mkdir(parents=True, exist_ok=True)
    appearance_description = "Fixed original appearance; clothing is not removable."
    wardrobe_help = ""
    if settings.armor_support:
        appearance_description = "Separate body, permanent underwear, fixed face/hair, and removable original garments."
        rows = []
        for index, garment in enumerate(settings.appearance_parts["garments"]):
            rows.append(f"  {garment['name']}: {settings.prefix}Garment_{garment['id']}; local FormID {0x811 + index * 2:06X}; slot {garment['slot']}")
        wardrobe_help = """Original garments:
""" + "\n".join(rows) + f"""

Initial outfit contains the garments marked equipped in the settings. Other
garments are added to the NPC inventory. Base body/underwear are the race's
non-playable skin and are never included as ordinary removable equipment.
Original clothing uses layers 44-49/53-59; underwear=52, fixed face/hair=60.
These slots are reserved within this follower MOD. Existing Skyrim armor has
not been fitted to this avatar and is not supported by this build.
Inventory/dropped-item previews use Skyrim's generic farm-clothing model;
the worn appearance uses the actual converted VRM garment meshes.

To verify clothing changes on a test save, select the placed NPC in the console:
  help "{settings.prefix}Garment_" 4
Find each ARMO's actual FormID (the leading load-order digits vary), then:
  unequipitem <FormID>
  equipitem <FormID>
Check one garment at a time, then all original garments removed. The avatar
should retain the base body, underwear, face and hair. Standard NPC outfit
management may re-equip the default outfit; inventory dialogue/dismissal and
save/reload behavior still need in-game confirmation. These commands test the
generated wardrobe; they do not claim a new follower equipment UI.
"""
    fitting_help = ""
    if settings.fit_armors:
        wardrobe_help = wardrobe_help.replace("Existing Skyrim armor has\nnot been fitted to this avatar and is not supported by this build.",
                                              "Selected Skyrim equipment is fitted; other equipment is not supported.")
        fitted = json.loads((output / "armor-fitting.json").read_text())
        rows = [f"  {item['editor_id']}: base game FormID {item['original_form_id']:08X}" for item in fitted["equipment"]]
        remove = "\n".join(f"  unequipitem <{settings.prefix}Garment_{g['id']} FormID>" for g in settings.appearance_parts["garments"])
        fitting_help = """Fitted original equipment:
""" + "\n".join(rows) + """

Install the separate armor-patch/VRM2SkyrimArmorPatch.zip too. Enable the follower
ESP, then VRM2SkyrimArmorPatch.esp. This keeps the original armor items/stats and
adds private-race appearances. Only one combined armor patch should be active.
The wizard can rebuild a combined patch for several installed/converted followers.
After changing that set, replace the combined patch and deploy again.

Remove the original VRM garments before wearing game armor. Original wardrobe
layers are not automatically managed by this fitting feature. On a test save,
select the NPC and use the garment FormIDs listed above:
""" + remove + """
Then use additem/equipitem with the original armor's base game FormID above, or
give those items through follower inventory. Never add or equip the private ARMA.
Check armor alone, boots alone, both together, walking/combat, then removal to
the original underwear body. Torso uses 32/34/38, hands=33 and feet=37; exposed
skin in fitted armor comes from the original VRM, with unchanged skin vertices.
Both engine weight variants use the same original target body.
Game equip/remove behavior needs in-game confirmation. Other mods overriding
the same armor items may need a compatibility patch/load-order adjustment.
"""
    readme = f"""{settings.mod_name} — {settings.npc_name}
Generated by VRM2Skyrim {VERSION}

Install this ZIP with Vortex or Mod Organizer 2. Enable {settings.plugin_name}.
Restart Skyrim. Meet {settings.npc_name} inside the Temple of Kynareth in Whiterun.
The standard 'Follow me. I need your help.' dialogue recruits this follower.
Standard wait, dismiss and inventory dialogue use Skyrim's follower system.
No additional prerequisite MOD is required by this file layout.

To locate the placed follower using the console:
  help "{settings.prefix}FollowerREF" 4
Use the ACHR FormID shown in that load order, then: player.moveto <FormID>
Do not use player.placeatme for normal recruitment; a persistent reference is
already placed in the temple. Use a test save when checking a newly built MOD.

The original VRM appearance uses a private race/skeleton.
{appearance_description}
{wardrobe_help}
{fitting_help}
Lip sync, blinking and hair physics are not included. Existing Skyrim armor is
supported only for equipment explicitly selected for fitting.
Ragdoll collision shapes/constraints still require fitting to the avatar.
Console preview and file checks do not replace Skyrim recruitment/gameplay checks.

Settings are included as {settings.asset_dir}/settings.json for reproducible conversion.
The original VRM is not included. Respect its author's permissions when sharing.
"""
    (metadata / "README.txt").write_text(readme, encoding="utf8")
    settings.save(metadata / "settings.json")
    # These two generated metadata files used shared paths before 0.4.1.
    # Remove them when repackaging an old build so they cannot still collide.
    for name in ("README.txt", "VRM2Skyrim-settings.json"):
        (mod / name).unlink(missing_ok=True)
    archive = output / f"{settings.mod_id}-VRM2Skyrim-{VERSION}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as target:
        for path in sorted(mod.rglob("*")):
            if path.is_file():
                target.write(path, path.relative_to(mod).as_posix())
    with zipfile.ZipFile(archive) as source:
        if source.testzip() is not None:
            raise RuntimeError("ZIP CRC validation failed")
        manifest = {name: hashlib.sha256(source.read(name)).hexdigest() for name in source.namelist()}
    (output / "package-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf8")
    logging.info("MOD ZIP ready: %s", archive)
    return archive


def convert(source, game, blender, output, settings, progress=None):
    def stage(name):
        logging.info("Stage: %s", name)
        if progress:
            progress(name)

    checks = doctor(game, blender)
    if not all(checks.values()):
        raise FileNotFoundError(f"Missing prerequisites: {[key for key, value in checks.items() if not value]}")
    output, source = Path(output).resolve(), Path(source).resolve()
    if not source.is_file() or source.suffix.lower() != ".vrm":
        raise ValueError("Select a local .vrm file")
    if source.is_relative_to(output):
        raise ValueError("Output cannot contain the original input VRM")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use an empty output folder; previous builds are retained")
    output.mkdir(parents=True, exist_ok=True)
    settings.save(output / "settings.json")
    run = {"version": VERSION, "state": "converting", "game_verified": False}
    try:
        stage("入力と設定の検査")
        report = inspect(source)
        from wardrobe import validate_source
        validate_source(settings, report)
        run["source_sha256"] = report["sha256"]
        (output / "source.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
        catalog = GameCatalog(Path(game) / "Data")
        catalog.validate_settings(settings)
        (output / "run.json").write_text(json.dumps(run, indent=2), encoding="utf8")
        stage("骨格・モデルの変換")
        skeleton = references(Path(game) / "Data", settings.sex)
        (output / "references.json").write_text(json.dumps({"root": str(skeleton.parents[4])}), encoding="utf8")
        run_blender(blender, "convert_blender.py", ["--source", source, "--output", output, "--skeleton", skeleton], output, "Convert model")
        stage("テクスチャの変換")
        convert_textures(output)
        if settings.fit_armors:
            stage("既存装備の体型合わせと身体部位の分離")
            from armor_fitting import fit
            fit(output, Path(game) / "Data", blender)
        stage("フォロワーと初期配置の作成")
        build_npc(Path(game) / "Data", output, settings, catalog)
        stage("出力の読み戻し検査")
        from validate import validate
        from verify_animation import verify_animation
        validation = validate(output)
        if validation["total_triangles"] != report["total_triangles"]:
            raise RuntimeError("Conversion did not preserve all source triangles")
        verify_animation(output)
        if settings.fit_armors:
            from armor_validation import validate_fitting
            validate_fitting(output)
            from armor_patch import build_patch
            stage("専用種族用の防具互換パッチ")
            build_patch(Path(game) / "Data", [output / "armor-fitting.json"], output / "armor-patch")
        if settings.render_previews:
            for animation in ("original", "rest", "walk", "attack"):
                stage("プレビュー: " + animation)
                run_blender(blender, "render_blender.py", ["--output", output, "--animation", animation], output, "Render " + animation)
            if settings.armor_support:
                for animation in ("rest", "walk", "attack"):
                    stage("下着状態のプレビュー: " + animation)
                    run_blender(blender, "render_blender.py", ["--output", output, "--animation", animation, "--wardrobe", "underwear"], output, "Render underwear " + animation)
                if len(settings.appearance_parts["garments"]) > 1:
                    for garment in settings.appearance_parts["garments"]:
                        stage("衣服の分離プレビュー: " + garment["name"])
                        run_blender(blender, "render_blender.py", ["--output", output, "--wardrobe", "without:" + garment["id"]], output, "Render without " + garment["id"])
            if settings.fit_armors:
                for animation in ("rest", "walk", "attack"):
                    stage("装備した姿のプレビュー: " + animation)
                    run_blender(blender, "render_blender.py", ["--output", output, "--animation", animation, "--wardrobe", "armor:all"], output, "Render armor " + animation)
        stage("MOD ZIPの作成")
        archive = package(output, settings)
        if hashlib.sha256(source.read_bytes()).hexdigest() != report["sha256"]:
            raise RuntimeError("Original VRM changed")
        run.update(state="offline_verified", zip=str(archive), zip_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
        stage("変換完了")
        return archive
    except Exception as error:
        run.update(state="failed", error=str(error))
        raise
    finally:
        (output / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf8")


def main():
    sys.stdout.reconfigure(encoding="utf8")
    sys.stderr.reconfigure(encoding="utf8")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Create a Skyrim SE follower MOD from a humanoid VRM")
    parser.add_argument("source", nargs="?", type=Path)
    parser.add_argument("--game", type=Path, default=find_game())
    parser.add_argument("--blender", type=Path, default=find_blender())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--settings", type=Path)
    parser.add_argument("--doctor", action="store_true")
    args = parser.parse_args()
    if args.doctor:
        checks = doctor(args.game, args.blender)
        print(json.dumps(checks, indent=2))
        return 0 if all(checks.values()) else 1
    if not args.source:
        parser.error("A VRM source is required. Launch wizard.py for guided conversion.")
    settings = FollowerSettings.load(args.settings) if args.settings else FollowerSettings(
        npc_name=args.source.stem, mod_name=args.source.stem + "Follower")
    output = args.output or ROOT / "build" / (settings.mod_id + "_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    archive = convert(args.source, args.game, args.blender, output, settings)
    print(f"ZIP: {archive}\nGame recruitment verification: pending")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        logging.exception("Conversion stopped")
        sys.exit(1)
