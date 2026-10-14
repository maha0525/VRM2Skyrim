# VRM2Skyrim

**English** | [日本語](README.ja.md)

**Turn your VRM avatar into a companion for your Skyrim adventures.**

VRM2Skyrim is a local tool that creates Skyrim Special Edition follower MODs from humanoid VRM 0/1 models. It generates a dedicated race and skeleton to preserve the avatar's proportions, face, hair, and original outfit. Configure the follower in a five-step wizard and export a ZIP for Vortex or Mod Organizer 2.

Materials retain the original VRM's single/double-sided rendering and transparency settings. Version 0.6.2 corrected the earlier behavior that forced all materials to render double-sided, resolving eyelashes appearing over the whites of the eyes. You do not need to delete eyelashes or expression parts from the VRM.

Followers start **inside the Temple of Kynareth in Whiterun**. The tool sets up the vanilla follower factions, a friendly relationship with the player, a recruitment-compatible voice, and a persistent placed reference, so the NPC can be recruited through dialogue.

The stable version on `main` is **0.8.1**. It can fit humanoid equipment from the base game, installed DLC, and official additional content in one batch, including helmets, shields, rings, and necklaces. You can configure face/hair visibility and import finishing edits made in Outfit Studio.

The `codex/fsmp-physics` branch is **0.9.8-dev** and adds optional hair/cloth physics. Enable **髪・布を揺らす** in the wizard, select the meshes, and start with the calm default. Garment roots and arm-adjacent sleeve attachments follow the body animation, while distal cloth moves independently. Rotational inertia and damping adjust to hair/cloth geometry and mass, with restricted twist and no wind force. Private bone origins and compensated skin binds keep FSMP render/contact frames aligned. Version 0.9.5 generates small hidden rigid contact patches for sleeves and connected cloth, reducing collision feedback that can coil long sleeves while the actor stands still. Original visible geometry and weights are preserved. Update the complete follower ZIP, including NIFs and XMLs. Generated followers require [Faster HDT-SMP](https://www.nexusmods.com/skyrimspecialedition/mods/57339) and matching SKSE64 when physics is enabled. See [physics setup and implementation](docs/FSMP.md).

Version 0.8.1 fixes Engine Fixes texture-load warnings caused by compressing small or unaligned images as BC7. These images now use uncompressed RGBA8 DDS, keeping their original dimensions and pixels. DDS format, dimensions, and mip storage are checked during conversion and output validation. This is a texture-only correction; existing followers do not need a save reset for this update.

The wizard interface is currently Japanese. English descriptions of its controls below are translations; some original Japanese labels are included to help locate them.

## Getting started

Requirements:

- Windows and Python **3.11 or 3.12**.
- Skyrim Special Edition, including `Skyrim.esm` and the base-game BSAs.
- **Blender 4.5 LTS**. Validation used version 4.5.12.
- A humanoid VRM model to convert.

1. Clone this repository, or use Code → Download ZIP and extract it.
2. Run **`Setup.cmd`** once. It installs Python dependencies into a dedicated `.venv` and downloads pinned versions of PyNifly and texconv into `dependencies/`.
3. Run **`Launch.cmd`** to open the wizard in your browser.
4. Select the VRM and check the Skyrim folder and Blender executable. Detected locations are filled in automatically.
5. Configure the follower and select **Create follower MOD** (`フォロワーMODを作る`). Download the ZIP and previews from the result page.

Processing runs on your PC. Models are not uploaded to external services. The tool does not modify the input VRM, game Data folder, or saves, and it does not change your Blender user preferences. To stop the wizard, press Ctrl+C in the terminal that launched it.

Install Blender separately from its [official website](https://www.blender.org/download/lts/). Generated MODs with headgear face/hair switching or seated height correction require [SKSE64](https://skse.silverlock.org/). With both options and physics disabled, fixed appearance and original-outfit separation do not require SKSE64. Creation Kit, RaceMenu, and XPMSSE are not mandatory.

Version 0.9.6 adds **seated height correction** in STEP 03. Automatic calculation uses the official sitting pose and the original avatar proportions, with an optional manual adjustment. It preserves standing proportions and corrects sinking into base-game chairs and benches. Generated MODs with this option enabled require SKSE64. See [settings and supported furniture](docs/SEATING.md).

0.9.7 removes the root wrapper introduced in 0.9.6 that broke standing avatars. It preserves the original skeleton/mesh root hierarchy and shifts the existing NPC node only while seated. Replace the complete follower ZIP and restart Skyrim.

0.9.8 starts chair-height correction during the entry animation. It listens for chair-entry events, verifies the furniture and restores the previous height if entry is cancelled.

## Wizard settings

| Area | Settings |
| --- | --- |
| VRM and environment | VRM file, Skyrim/Blender locations, loading saved settings |
| Clothing separation | Enable/disable support; assign meshes to body, underwear, always-visible parts, or garments; preview the original VRM assignments |
| Original outfit equipment | Combine into one item or split into items; names, occupied slots, clothing/light/heavy armor, armor rating, weight, value, and initial equipment |
| Name and voice | NPC name, MOD name, unique MOD ID, author, sex, and 17 voice types with vanilla follower dialogue |
| Combat and abilities | Warrior/two-handed/archer/destruction/conjuration presets, class, combat style, starting weapon, and ammunition |
| Growth and personality | Fixed/player-scaled level, multiplier and limits, automatic/manual stats, health/magicka/stamina, 18 skills, essential/protected/normal status, confidence, aggression, and crime behavior |
| Details | Uniform overall size multiplier, marriage eligibility with supported voices, and placement offset inside the temple |
| Perks and spells | Perks with ranks and spells, searchable by game name, ID, and description |
| Review and export | Save settings JSON, generate previews, and save the MOD ZIP |

Perk and spell candidates are read from the selected game's `Skyrim.esm`. Spells are restricted to ordinary spells taught by spell tomes; blessings, passive abilities, and trap effects are excluded. This version does not list DLC/MOD perks and spells or independently recorded custom voices. With automatic calculation, health, magicka, and stamina are base values before class/level growth. With manual calculation, the specified attributes and 18 skill values are used directly, including when the NPC's level follows the player. The individual-skills panel includes a button to switch to manual calculation. Selected Perks are granted explicitly; increasing a skill does not automatically add Perks.

The wizard displays each class's skill and health/magicka/stamina growth weights from the game records. Combat styles normally show candidates used by NPCs with the human character skeleton. Enable the all-styles option to include creature styles and styles without confirmed human usage; the selected style lists its example races. This filter is guidance, not a race restriction in the combat-style record. New followers default to **essential** and **no crime restrictions (morality 0)**. Explicit values in imported settings are preserved.

The MOD ID determines the ESP name, Editor IDs, and private mesh/texture paths. Use **different MOD IDs** when installing multiple avatars together. NPC names and display names can also use Japanese text.

## Separating body, underwear, and clothing

Since version 0.6.0, clothing is added as ordinary NPC inventory, with the default-outfit field left empty. A private NPC script equips the selected initial clothing once. It does not replenish items after removal or rewrite AFT outfit sets.

Clothing replacement uses Skyrim's native equipment-slot exclusion: torso outfits use 32, gloves 33, and shoes 37. To wear a shirt, jacket, skirt, and tights together, combine them into one torso outfit item. Equipping armor or boots replaces clothing in the same slots. There is no equipment-event script that removes clothing afterward. Slot exclusion also applies to equipment outside the conversion catalog when it occupies the same slot.

Use **Split into torso, gloves, and shoes** (`胴・手袋・靴に分ける`) to group meshes by region, or **Combine clothing into one item** (`衣服を一品にまとめる`) for a full-body set occupying torso/glove/shoe slots. Selecting a body region/purpose automatically chooses the slot; select a number directly only when needed, from 32–49 or 53–59. If several initial items occupy the same slot, the wizard asks you to combine them instead of silently moving them to extra slots. Cloaks and accessories assigned to extra slots coexist with armor.

ARMO equipment occupancy and ARMA body coverage are handled separately. A torso item occupies slot 32, while its displayed model retains the avatar's original skin for regions 32, 34, and 38. A full-body outfit also retains hand and foot skin. Slots 52 (underwear) and 60 (face/hair) are reserved internally. SkyUI item types and icons mainly depend on equipment slots. Legacy settings for scripted clothing replacement are migrated to regional outfit sets when loaded, with a notice in the wizard.

The hidden internal head item used in version 0.5.1 was removed because AFT could remove the default outfit and expose a human face. FaceGen head generation is disabled for the dedicated race, and the NPC and race point to an empty head model. The VRM face and hair are part of the skin in slot 60, with separate variants containing or hiding each according to headgear settings. The dedicated race's empty-head configuration is shared by every visibility state.

For a normal update, replace and deploy the new ZIP using the same ESP name, then quit and restart Skyrim. If only the old 3D appearance remains, select the NPC in the console, run `disable`, and run `enable` without changing the selection. If clothing-structure changes or other updates cause inventory/equipment problems, use the [reset procedure](#follower-update-reset) below.

Choose wardrobe support in the first screen to see suggested assignments for the VRM meshes. Suggestions are inferred from names and materials, so **check the body, underwear, always-visible parts such as face/hair, and removable garments yourself**. This version does not cut apart or reconstruct meshes where body and clothing are fused together.

You can combine garments into a single item or split them into separate equipment. Use **+ Add clothing** (`＋ 衣服を追加`) in the **Generated clothing** (`生成する衣服`) list to add groups, then assign each mesh to an equipment group to combine several meshes into one garment. Expand equipment details to adjust names, slots, stats, and initial equipment. Use **Remove clothing** or **Remove one item**, then **Preview overall appearance** (`全体の見た目をプレビュー`) to check that the body and underwear remain before conversion. This preview shows the original VRM; output NIF images are generated after conversion.

The body, underwear, always-visible parts, and each garment are exported as separate NIFs using the same dedicated skeleton. Underwear remains when no equipment is worn. Clothing can use standard slots 32–43 and layering slots 44–49 or 53–59. Garments occupying body slots also retain the original VRM body needed for exposed areas. Slots 52 and 60 are reserved for underwear and always-visible parts. Initially equipping conflicting items is rejected. All items are added to the NPC's inventory, and initial-equipment settings apply to the first equip only. Inventory/dropped-item views use a generic base-game clothing model; the equipped model uses the converted original VRM geometry.

Mesh assignments are associated with the input VRM's SHA256. If you load settings into a different VRM, open **Redo mesh assignments** (`メッシュの割り当てをやり直す`) in the first screen and choose **Restore automatic assignments from import** (`読み込み時の自動割り当てに戻す`). This clears manual assignments and clothing groups, restoring the initial suggestions based on names and materials. Every enabled mesh must be assigned exactly once; omissions and duplicates are rejected.

The generated README includes clothing IDs and equipment-trading instructions. Original clothing can be given or taken through ordinary follower inventory dialogue.

Search for and select headgear one item at a time to configure face/hair visibility and check an equipped preview. **Global defaults** (`全体デフォルト設定`) apply to items without an individual override. **Reset** (`リセット`) removes that item's override. **Preview with this headgear** (`この頭装備を着せてプレビュー`) fits the selected helmet to the VRM body and renders it. Changing only visibility settings reuses the fitted geometry.

Choose the source-data mode based on the **equipment you want to convert**. For standard base-game/DLC equipment, choose **Convert standard base-game/DLC equipment** (`本体・DLCの標準装備を変換`). For UNP/CBBE equipment replacers or BodySlide-generated equipment, choose **Convert currently installed equipment** (`現在導入している装備を変換`) after building and deploying both the body and equipment with the same body preset. Installing a body MOD alone does not require the latter option. The destination body is always the original VRM in either mode.

Version 0.7.1 also fixed export-name collisions when splitting large meshes with several materials. You do not need to consolidate materials or meshes in the VRM.

Headgear preserves source model partition identifiers such as 130 (full-face helmet) and 131 (hood). These are separate from ESP equipment slots 30 and 31; model partition 131 is not rewritten as ordinary hair slot 31. Generated data is checked against the original equipment.

## Installing in Skyrim

1. Install and enable the generated ZIP with Vortex or MO2. In Vortex, also run Deploy.
2. Enable the generated `<MOD ID>.esp` in the plugin list.
3. Quit and restart Skyrim, then visit **Whiterun's Temple of Kynareth** using a test save.
4. Talk to the NPC and choose the standard recruitment dialogue. Check recruitment, following, waiting, dismissal, and re-recruitment.

The NPC uses the vanilla follower slot. Dismiss another follower first if that slot is occupied. A follower is already placed inside the temple, so `player.placeatme` is normally unnecessary. The console command for moving to the temple during testing is `coc WhiterunTempleofKynareth`.

The generated README includes a command to find the placed reference and instructions for using its FormID with your actual load order. If you used the 0.1/0.2 Sophie prototype, it is a different plugin from SophieFollower; disable the old prototype in a test save when checking the new follower.

<a id="follower-update-reset"></a>

## Resetting a follower after a problematic update

If an update prevents opening inventory or causes incorrect equipment behavior, use these steps to reinstall the follower. This recovery procedure can be used for updates that merge or split clothing items. It resets the follower rather than retaining its inventory and follower-manager configuration.

1. **Restore the previous follower MOD and armor patch, then load a save from before the update.** Keep that save and the old ZIPs as backups.
2. **Recover entrusted items.** Take back weapons, armor, and other items except the original clothing added by this follower MOD. Also check equipment and cargo stored separately by AFT or another manager. If you moved the follower's original clothing to the player or a storage container, return it to that follower.
3. **Dismiss the follower and unregister it from your follower manager, if used.** Complete the AFT preparation below where applicable. Then move to another location without the follower, save manually into a new slot, and quit the game.
4. **Disable the follower MOD and armor patches that reference it, then load the save from step 3.** In Vortex, also deploy. For a shared multi-follower patch, rebuild it without this follower to preserve fitting for the others. Do not leave an enabled patch that depends on the disabled follower ESP.
5. **Save manually into another slot and quit.** Do not overwrite the original backup or the save from step 3.
6. **Install and enable the updated follower MOD and a matching armor patch, then load the save from step 5.** Deploy again in Vortex.
7. **Recruit the follower again at Whiterun's Temple of Kynareth.** Return the recovered equipment and redo the follower-manager settings you use.

**AFT preparation:** Dismissal alone leaves the management registration in place, so use the individual **Reset NPC** in step 3. The AFT author's sequence is: recover gear and turn off outfit management → dismiss this follower and all other active followers → wait 24 in-game hours → fast travel elsewhere and enter an interior → save, quit, restart, and reload that save → talk to the target NPC and choose **Settings → Reset NPC** → save and quit. This is different from resetting all of AFT. Translations may use different menu names. [AFT author's instructions](https://www.nexusmods.com/skyrimspecialedition/mods/80675?tab=posts)

If step 4 asks whether to reactivate inactive content (**Activate now?**), select **No**: this question would enable the MOD you deliberately disabled. For the subsequent warning that some objects may no longer be available (**Continue loading?**), select **Yes** to continue.

This is a recovery procedure for reinstalling a follower, not a guarantee that every reference in saves or external MOD data is removed. If recovery fails, restore the backup save and the old follower MOD/armor patch from step 1.

## Conversion scope

- Humanoid VRM 0/1 skeletons, arbitrary node/mesh names, and splitting large geometry where needed.
- Unit conversion and joint rotations preserving the original proportions, without stretching individual regions to the standard Skyrim body.
- Dedicated race and skeleton, fixed appearance or removable original-outfit equipment, vanilla follower settings, and initial placement.
- Secondary-rig mapping checked against position and orientation; clothing and hair made with separate rigs are integrated into the same output skeleton.
- OPAQUE/MASK/BLEND materials and DDS alpha. Initial expression-morph values are baked into the fixed appearance.
- NIF/DDS read-back checks, vertex comparison against the original VRM in the same pose, and standard walking/one-handed-sword animation checks and images.

With wardrobe support enabled, the assigned original garments can be equipped and removed. **Fit existing equipment to this body** (`既存装備をこの身体に合わせる`) converts either **all official equipment** or **selected equipment**. It reads the base game, installed Dawnguard/HearthFires/Dragonborn, and installed `cc*.esm`/`cc*.esl` files, using equipment Addons intended for humanoids. Human and beast-race models are selected separately. Enchanted variants using the same Addon share a single fitted model.

Besides torso, hand, and foot equipment, fitting covers headgear, circlets, shields, rings, and necklaces. The armor is deformed while the original skin vertices and faces are preserved, and exposed regions include the original skin. Texture Set variations, equipment slots, and original item stats are retained.

**Hide face** and **Hide hair** are independent headgear options. By default, the face remains visible and headgear occupying hair slots hides the hair. Circlets retain hair. An item override also applies to enchanted variants sharing the same Addon. In the mesh-assignment screen, identify the face, hair, and always-visible accessories.

Source body/equipment data can come from the original official archives or currently installed files. **For UNP/CBBE equipment replacements, build both the body and equipment using the same BodySlide preset before choosing installed data.** Source and destination vertex counts may differ. Additional physics bones are consolidated into body-following weights.

The result page's **Outfit Studio editing kit** contains a reference NIF preserving the original VRM body, the dedicated skeleton, fitted equipment, and textures. Refine shapes with brushes, export a NIF without including the reference body, and load it through **Import finished equipment** (`仕上げた装備を戻す`) to update the MOD ZIP. It imports vertices and normals while preserving weights, UVs, materials, and equipment slots. Added/deleted vertices or faces, renamed shapes, and edits to the reference body are rejected. Saved finishing edits are reused when reconverting the same VRM and equipment.

After restarting the wizard, open **Previously created followers** (`前に作ったフォロワー`) to access results and equipment editing. If importing an edit fails, the pre-edit meshes, saved edits, and ZIP are restored. You can also update the current ZIP from the CLI:

```powershell
python outfit_edits.py --output <conversion-folder> --mesh-key <editing-kit-source_key> --edited <edited-NIF> --blender <Blender.exe>
```

Installed-data mode reads the body, equipment, and skeleton from the game's Data folder. With MO2, run the tool in an environment that can see MO2's virtual Data folder. The official-equipment catalog does not list equipment records added by third-party MODs.

Without `--blender`, the CLI imports and saves a finishing edit for the next conversion:

```powershell
python outfit_edits.py --output <conversion-folder> --mesh-key <manifest-source_key> --edited <edited-NIF>
```

In addition to the follower ZIP, install the **armor compatibility patch ZIP** from the result page. Enable `VRM2SkyrimArmorPatch.esp` after the follower ESP, deploy in Vortex, and restart the game. Equipping fitted official equipment replaces original clothing occupying the same slots; clothing deliberately assigned to extra slots remains. Test FormIDs and commands are included in the generated README.

For several fitted followers, select them on the result page and combine them into one armor patch. Installed followers and followers converted with this wizard appear as candidates. Keep only one compatibility patch enabled, and rebuild it when adding or removing followers. It preserves original item stats, display names, and original-race Addons, but MODs overriding the same equipment may need load-order adjustments or further compatibility patches.

Lip sync, blinking, and hair/clothing physics are not supported. MToon shading and outlines are not reproduced. Fingers without finger bones are fixed to the hands. Ragdoll dimensions and constraints for falls/death are derived from the standard skeleton; avatar-specific adjustment and validation remain necessary.

The temple CELL record is included as a copy preserving the base-game contents so the follower can be placed there. MODs changing lighting or other properties of the same CELL may require normal load-order or compatibility-patch adjustments.

Follower ZIPs do not contain the input VRM, working reference meshes, or dependency tools. They do contain converted skeletons, appearance/equipment meshes, and the textures those meshes use. Follow the model author's terms when using a model or distributing a generated MOD; see [License](#license) and [third-party notices](THIRD_PARTY_NOTICES.md).

## CLI and reconversion

```powershell
python converter.py --doctor
python converter.py avatar.vrm --settings my-follower.json
python converter.py avatar.vrm --settings my-follower.json --game 'E:\SteamLibrary\steamapps\common\Skyrim Special Edition' --blender 'C:\path\blender.exe' --output build/my-new-build
python wizard.py --no-browser --port 8768
```

If you used `.venv` during setup, run `.venv\Scripts\python.exe`. You can also drag a VRM onto `Convert-VRM.cmd`. Outputs are written under `build/`, and previous conversions are not overwritten. An explicitly specified `--output` must be an empty folder.

Load `vrm2skyrim/<lowercase MOD ID>/settings.json` from a generated ZIP into the wizard to reconvert with the same settings. Its instructions are in `README.txt` in that same folder. Change the name and MOD ID when switching to a different avatar. The root-level `VRM2Skyrim-settings.json` from versions 0.3/0.4 can still be loaded. Since 0.4.1, all files, including instructions and settings, use MOD-specific paths to avoid conflicts between different MOD IDs.

## Development and validation

```powershell
python -m unittest test_converter tests.test_follower tests.test_wardrobe tests.test_package tests.test_armor tests.test_textures
python -m ruff check --exclude dependencies,build,reference .
```

Follower integration tests require a local `Skyrim.esm`; only those tests are skipped when the game is unavailable.

Browser E2E tests use a dedicated headless browser rather than your existing browser profile.

```powershell
npm install
npx playwright install chromium
# In another terminal, start: python wizard.py --no-browser
$env:VRM2SKYRIM_TEST_VRM='C:\path\test-avatar.vrm'
npm run test:ui
# For a test VRM with separate body, underwear, and several garments:
npm run test:wardrobe
# To include equipment selection and armor-patch generation:
$env:VRM2SKYRIM_TEST_FIT='true'
npm run test:fitting
```

To use an existing Chrome installation in a separate headless process, set `VRM2SKYRIM_TEST_BROWSER=chrome`. Set `VRM2SKYRIM_TEST_URL` to specify the server URL.

See [FORMAT.md](docs/FORMAT.md) for file structures and implementation references, [follower-wizard.md](docs/intent/follower-wizard.md) for the wizard design, [armor support](docs/intent/armor-support.md) for wardrobe design, and [armor fitting](docs/intent/armor-fitting.md) for fitting. The tool uses external PyNifly V29.1.0 and DirectXTex may2026 dependencies, checking pinned SHA256 values when downloading them. Their licenses are GPL-3.0 and MIT respectively. Input VRMs and game assets are not included in this repository.

## License

Original VRM2Skyrim code and documentation are licensed under the [MIT License](LICENSE). Modification, redistribution, and commercial use are permitted with the copyright and permission notice retained.

Dependencies keep their own licenses. In particular, PyNifly is GPL-3.0 and is imported directly by this tool. The original code can remain under MIT, but distributing the assembled converter with PyNifly requires GPL compliance for the combined work, including license notices and corresponding source. The combined distribution cannot be provided under MIT-only terms.

Input VRMs, Skyrim-derived assets, and resources from other equipment MODs are not covered by this MIT grant. Follow their respective authors' and rights holders' terms when distributing generated follower MODs or Outfit Studio editing kits. Include the MIT notice when redistributing original VRM2Skyrim runtime scripts. [Third-party notices and generated-asset terms](THIRD_PARTY_NOTICES.md) document dependency versions, primary sources, and redistribution requirements.
