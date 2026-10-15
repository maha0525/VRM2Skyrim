# Per-follower armor registration instead of a shared patch ESP

Status: implemented for new 0.12.0 exports. Offline conversion and browser workflow
verified; in-game behavior remains a required user acceptance check.

## User requirement
Adding, removing or disabling one generated follower must not require rebuilding
a separate plugin that depends on every follower. Each exported MOD must contain
its own fitted meshes, private armor addons and registration configuration.
Installing several independently generated followers must compose their armor
appearances without one output replacing another follower's registration.

## Proposed implementation
Use SkyPatcher's armorAddonsToAdd to append each follower's private ARMA to the
original ARMO at game startup. Generate a uniquely named per-follower configuration
inside that follower's ZIP, guarded with hasPlugins for its own ESP (and each
required original item plugin where applicable). Use plugin name plus local FormID,
never the user's load-order index. Keep private race filtering on the ARMA so other
races retain their original appearance. Preserve original armor models and stats.

No generated configuration may refer to a different generated follower. Uninstalling
a follower removes its own configuration; disabling its ESP skips its guarded rules.
The shared dependency is SkyPatcher, installed once, with no follower masters. This
is startup registration, not per-frame scanning or repeated Papyrus polling.

Armor fitting itself remains a conversion-time task: new/changed armor meshes still
need fitting. This architecture removes cross-follower bookkeeping, not mesh work.

## Existing responsibilities and migration
The old build_patch also writes equipment/visibility FLST data and some ARMA footstep
sound overrides. Trace and preserve these responsibilities in follower-owned data
or guarded runtime registration; emitting only ARMO additions is not a complete
migration. Preserve compatibility with the generated wardrobe policy and its runtime.

Stop producing the shared VRM2SkyrimArmorPatch.esp and the per-follower ZIPs with that
same plugin name for the new mode. Remove the combined-patch management flow from
the normal user journey. Detect an installed legacy patch and explain once that it
must be disabled/removed when migrating, preventing stale hard-master dependencies
and duplicate registrations. Do not change the user's Vortex/MO2 state automatically.

Check the required SkyPatcher version and armor patching setting in the wizard;
show the dependency in generated installation instructions. Do not bundle or modify
the installed third-party DLL without an explicit distribution decision.

## Acceptance criteria
- Convert A and B independently; each ZIP has unique config paths and no dependency
  on the other follower or a generated shared ESP.
- With A alone, B alone and both enabled, fitted armor appears on the correct private
  race and ordinary NPC armor retains its original model and stats.
- Disable A's ESP while retaining its files; only A's guarded rules are skipped.
  Remove A's MOD and restart; B retains all required registrations without rebuilding.
- Cover DLC/official item ownership, duplicate bindings, invalid/stale forms, original
  addon preservation, head visibility lists, footstep sounds and wardrobe replacement.
- Verify with the actual supported SkyPatcher build, generated ZIPs and game behavior;
  text generation and mock tests alone do not establish runtime compatibility.

## Evidence and rationale
The current armor_patch.py collects all follower ESPs as MAST dependencies and writes
one shared plugin. A per-follower build and a combined build use the same output name.
This makes exported MOD installation depend on the user's changing whole loadout.
web/wizard.js further hides the management section for non-fitting conversion results;
adding a permanent manager would expose maintenance without eliminating that burden.

SkyPatcher author documentation:
https://www.nexusmods.com/skyrimspecialedition/articles/6088
Implementation (armorAddonsToAdd and hasPlugins):
https://github.com/Zzyxz/SkyPatcher/blob/main/armor.cpp
The user's installed SkyPatcher DLL reports 7.1.3.0; actual runtime compatibility is an
acceptance check, not inferred from the latest online source.

Footstep sound refs are retained directly in private ARMA records. If a sound
requires an official DLC master, the follower adds only those official masters;
canonical internal follower IDs are mapped at serialization and readback. No
other follower becomes a master. Visibility lists receive guarded per-follower
SkyPatcher formList rules, with exact ESP.ini filenames for plugin gating.

## Verification evidence
`tests.test_skypatcher` covers independent configurations, optional DLC master
serialization, private NPC/race/style/reference links, guard/exclusion behavior,
packaging, tampered configs and missing/disabled runtime settings. The game-backed
case builds two independent follower ESP/ZIPs, including Skaal boots with a
Dragonborn footstep reference, and checks that installed paths do not collide.
`tests/browser-skypatcher.cjs` uses the real isolated wizard HTTP server for
missing runtime/config detection, deployment recheck, old output guidance,
non-fitting output, migration notice, JA/EN switching and mobile layout.
The real Quon VRM was converted end-to-end with iron boots, an elven helmet,
Skaal boots, a custom combat style and seated correction. Final NIF, animation,
fitting and ZIP checks passed: `build/patch-recovery/full-conversion/run.json`.

Official headgear is not prefilled into the private visibility FLSTs. Those contain
only follower-owned original headwear; the generated SkyPatcher formList rules add
official items exactly once. The native formList appender does not deduplicate, so
validation rejects prefilled official entries. Do not split base and DLC registration
across independent writers.
