# Official equipment, head visibility and finishing edits

Approved goal: batch-fit playable humanoid equipment from Skyrim SE, its installed
DLC and official Creation plugins. Keep original item records, statistics and
other races' appearances; add private-race addons through one combined patch.

## Architecture

- Resolve disk FormIDs through each plugin's actual master list, including ESL
  files. Never confuse plugin-relative indices with runtime load order.
- Read official assets from their archives, pairing vanilla equipment with the
  vanilla reference body. An installed/mod reference profile uses the deployed
  body and skeleton instead. BodyField does not require equal mesh topology.
- Convert each unique addon geometry once; enchanted variants share the fitted
  addon. Support multiple humanoid addons and all humanoid biped categories.
  Include shared male models used by female actors, notably shields. Persist
  owner/local IDs rather than catalog indices so additional Creations do not
  invalidate existing follower profiles when combining patches.
- Keep the follower plugin's existing Skyrim-only master layout and saved IDs.
  DLC gear lists live in the combined patch, which remaps all native references.
- Face and hair are classified independently. Four permanent-layer NIF models
  each combine the visible face, hair and fixed accessories into one slot-60
  addon. Four private skin records select those models; an empty combination
  simply omits the addon. Models never compete with one another in that layer.
  An SKSE Actor script selects the skin from equipped headgear policies and
  refreshes the actor's scene. It never restores native FaceGen or alters outfits.
- Headgear settings have independent face/hair defaults and per-addon overrides;
  identical enchanted variants share policy. Fixed accessories can remain visible.
- Export an Outfit Studio edit kit with target reference body and skeleton.
  Import shape-only edits into the original NIF, preserving skin, materials,
  partitions and bind poses. Reject topology changes rather than corrupting them.
  Store edits by avatar and source geometry identity; regeneration reuses them.
  Failed imports restore prior meshes/overrides/archives. Completed wizard
  results persist locally and can be reopened after restarting the tool.

## Verification

Test master-reference round trips and preserved item data, multi-addon selection,
deduplication, all-category selection, settings round trips and head events using
compiled PEX. Read back the generated all-equipment patch and NIFs. Render source
and fitted category samples; exercise the wizard's selection and policy controls.
Private VRM, game assets, previews and generated MODs remain local.
