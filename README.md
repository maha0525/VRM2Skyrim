# VRM Skyrim Converter

[日本語 README](README.ja.md)

**VRM Skyrim Converter** is a local tool that turns a VRM avatar (`.vrm`) into a ready-to-install follower mod (ZIP archive) for **Skyrim Special Edition / Anniversary Edition**.

Guided by a 5-step browser wizard, you can convert your 3D model, set up removable outfits and body-fitted armor, generate Faster HDT-SMP hair and cloth physics, enable anime-style toon shading for Community Shaders, and configure combat classes, spells, perks, shouts, and custom GLB weapons—all packaged cleanly for Mod Organizer 2 or Vortex.

---

## Key Features

- **5-Step Browser Wizard**
  Configure your follower's name, voice, meeting location, combat role, starting gear, perks, spells, and shouts step by step. The wizard scans your Skyrim installation and active load order automatically, so you never have to look up raw FormIDs.
- **Removable Outfits & Fitted Skyrim Armor**
  Split your VRM meshes into body, underwear, and garments so your follower can unequip their default outfit or wear other armor in-game. You can also automatically fit base-game or mod armor meshes to your avatar's proportions.
- **Hair & Cloth Physics (Faster HDT-SMP)**
  Reads VRM Spring Bone chains and generates Faster HDT-SMP cloth XML and collision bodies automatically, with presets and sliders for stiffness, gravity, damping, and wind.
- **Anime-Style Toon Shading (Community Shaders)**
  Supports a custom Community Shaders 1.4.x addon that brings soft cel shading, rim lighting, and ink outlines to your follower.
- **Custom Weapons from GLB**
  Upload a `.glb` weapon model, adjust its scale and grip orientation with live previews, and bundle it as your follower's signature weapon.
- **Automatic Sitting Height Adjustment**
  Compensates for your avatar's leg length and proportions so they sit at a natural height on chairs and benches.

---

## Requirements

### PC Requirements (For Running the Converter)

| Component | Requirement |
| :--- | :--- |
| **OS** | Windows 10 / 11 (64-bit) |
| **Python** | Python 3.11 or newer |
| **Blender** | Blender 4.2 or newer |
| **Skyrim** | Skyrim Special Edition (or Anniversary Edition) installed locally |

### In-Game Mod Requirements (For Playing with the Generated Follower)

Basic follower features (recruiting, combat, removable outfits, and custom weapons) **do not require any additional prerequisite mods**. Depending on the optional features you enable, install the following in your Skyrim load order:

| Optional Feature | Required Skyrim Mods | Notes |
| :--- | :--- | :--- |
| **Basic Follower, Removable Outfits, Custom Weapon** | None | Runs on vanilla Skyrim SE/AE (plus any official DLC/Creations you select for gear or shouts). |
| **Sitting Height Adjustment** | **SKSE64** | Adjusts seat height via script when sitting (launch via `skse64_loader.exe`). |
| **Hair & Cloth Physics** | **SKSE64** + **Faster HDT-SMP** | Required to animate converted VRM Spring Bone chains in-game. |
| **Toon Shading** | **SKSE64** + **Community Shaders 1.4.x** + **VRM2Skyrim Toon Shader Addon** | Download the Toon Shader Addon ZIP from STEP 01 or the completion screen. |
| **Existing Armor Fitting** | **SKSE64** + **SkyPatcher** | Required when fitting official Skyrim armor/headgear to your follower's body. |

---

## Getting Started

### 1. First-Time Setup

After downloading the repository, double-click **`Setup.cmd`** once.
It creates a local Python virtual environment (`.venv`) and prepares the required Blender add-on and conversion tools.

### 2. Launching the Wizard

Double-click **`Launch.cmd`** whenever you want to create or edit a follower.
This starts the local server and opens the wizard in your default web browser.

> [!TIP]
> After updating this tool, close any running command window from an earlier session and launch `Launch.cmd` again so the latest server code is loaded.

---

## Creating a Follower (5 Steps)

### STEP 01: Avatar, Wardrobe & Rendering Setup

1. **Select Your VRM File**
   Upload your `.vrm` file to inspect its meshes, triangle count, and Spring Bone chains.
2. **Toon Shading (Optional)**
   Open **Toon shading (for Community Shaders)** and enable it if you want anime-style cel shading.
3. **Removable Outfits & Armor Fitting (Optional)**
   Switch **Clothing and armor separation** to **Enabled: separate body, underwear, and clothes** if you want your follower's clothing to be removable in-game.
   - Assign each VRM mesh to Body, Underwear, Clothing, Face, Hair, or Ears/Horns.
   - Use **Reset to suggested**, **One item per mesh**, or **Combine into one outfit** to organize garments quickly, and render a Blender preview to check how dressed, underwear, and nude states look.
   - Enable **Fit existing Skyrim armor to this body** to conform vanilla or replacer armor to your avatar's body shape.
4. **Physics Settings (Optional)**
   If your VRM includes Spring Bones, choose which meshes should sway and adjust their stiffness and damping.
5. **Environment Paths & Saved Sessions (Optional)**
   Reopen previously built follower ZIPs from the top of STEP 01, verify Skyrim/Blender paths, or load a saved `.json` settings file.

### STEP 02: Identity & Profile

- **Follower Name, Mod Name, and Plugin Name**: Set the in-game display name and the generated `.esp` filename.
- **Sex, Height, and Weight**: Choose the animation skeleton (Female / Male) and body scale.
- **Voice Type & Marriage Dialogue**: Pick from Skyrim's available voice types and marriage options.

### STEP 03: Combat Style, Starting Gear & Behavior

- **Combat Preset**: Pick a role preset (such as One-Handed Warrior, Ranger, or Destruction Mage) to automatically populate matching class, weapon, and stat defaults.
- **Starting Weapon & Custom GLB Weapon**:
  - Choose an existing weapon from your game, or select **Original weapon** to upload a `.glb` model and tune its length, grip position, and orientation with live previews.
- **Protection & Morality**: Set whether the follower is Essential, Protected, or Mortal, and how they react to crimes.
- **Stats, Skills & Sitting Height**: Let Skyrim auto-calculate skills by class, manually set all 18 skill values and base Health / Magicka / Stamina, or fine-tune chair/bench sitting height.

### STEP 04: Perks, Spells & Shouts

- Select starting **Perks**, **Spells**, and **Shouts** for your follower.
- Filter by skill school or search by name/FormID; selected items appear as removable tags at the top of each section.

### STEP 05: Review & Build

- Review your configuration summary and click **Build Follower Mod**.
- You can also click **Export Settings JSON** beforehand so you can reload and tweak the same setup later.

---

## Installing into Skyrim

1. **Install the Follower Mod ZIP**
   Once conversion finishes, download the generated **Follower Mod ZIP**, install and enable it in Mod Organizer 2 or Vortex, and meet your follower inside the **Temple of Kynareth in Whiterun**.
2. **If You Enabled Toon Shading**
   Click **Download the toon shader** in STEP 01 or on the completion screen, and install that ZIP alongside Community Shaders (only needed once).
3. **If You Enabled Existing Armor Fitting**
   Install SKSE64 and SkyPatcher, and make sure `iEnableArmorPatching` and `iEnableFormlistPatching` are set to `1` in `SkyPatcher.ini` (you can verify your setup directly from the completion screen using **Check after deploying**).
4. **Refining Meshes in Outfit Studio (Optional)**
   Use the **Finish equipment in Outfit Studio** section on the completion screen to download the editing kit ZIP, tweak any fitted `.nif` in Outfit Studio, and import it back to update the mod ZIP.

---

## Troubleshooting

### "Restart the wizard" appears on screen
If you updated the repository while an older `Launch.cmd` window was still running, press `Ctrl+C` in the old terminal (or close it), run `Launch.cmd` again, and use the newly opened browser tab.

### An existing save does not show updated follower gear or appearance
Skyrim caches NPC state and inventory in your save file once you have met them. When testing a rebuilt follower with the same plugin name, use a save made before meeting the follower, or travel to another cell and reset the actor via the console (`recycleactor`).

---

## Command-Line Usage (CLI)

You can also run conversions directly from the command line (or via `Convert-VRM.cmd`) without opening the browser wizard:

```powershell
# Launch the web wizard
.venv\Scripts\python.exe wizard.py

# Convert a VRM directly into a follower mod directory
.venv\Scripts\python.exe converter.py ^
  --input "path\to\avatar.vrm" ^
  --output "build\my-follower" ^
  --npc-name "Follower Name" ^
  --plugin-name "MyFollower.esp"
```

---

## Guides & Documentation

- **[Toon Shading Guide (docs/TOON.md)](docs/TOON.md)** — Setting up and tuning the Community Shaders toon addon
- **[Cloth & Hair Physics Guide (docs/FSMP.md)](docs/FSMP.md)** — Converting and tuning VRM Spring Bones for Faster HDT-SMP
- **[Sitting Height Guide (docs/SEATING.md)](docs/SEATING.md)** — How automatic and manual chair height compensation works
- **[Headwear & Hair Visibility Guide (docs/HEADWEAR.md)](docs/HEADWEAR.md)** — Preventing hair/ear clipping with helmets, hoods, and custom headwear
- **[Output Format Specification (docs/FORMAT.md)](docs/FORMAT.md)** — Technical reference for generated NIF, ESP, and texture records
- **[Development & Testing (docs/development.md)](docs/development.md)** — Running unit tests, linters, and browser checks

---

## License & Third-Party Notices

- Project source code is licensed under the [MIT License](LICENSE).
- See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for license details of bundled tools and shader adaptations.
