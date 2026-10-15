# Wizard controls, standard clothing slots and headgear preview

## Combat preset selection round trip

Save the selected wizard preset ID as `combat_preset` in settings JSON,
including conversion output and reopened saved followers. Restore its label
without invoking the preset handler: imported class, combat style, weapons,
spells and attributes may have been customized and must remain authoritative.
Keep the selected starting preset even after individual adjustments. Old JSON
without this field shows Custom; do not guess an original selection from a
class/style pair. New defaults retain Warrior. Verify actual JSON export/import
before and after catalog loading, language switching, and legacy JSON.

## 2026-10-15 skill browsing and version consistency

The running 0.9.5-dev server returned old protection/morality defaults and no
class growth fields while serving newly edited JavaScript. Require matching
frontend/backend versions; detect source changes after startup, refuse new
POST operations and explain restarting Launch.cmd. Preserve explicit imported
settings. Never restart the user's active server or discard their selections.

Categorize Perks from AVIF PNAM trees and PERK NNAM chains. Show chain stages
beside names. Only offer an effect-rank selector if PRKE actually has multiple
effect ranks; Stealth records declare Num Ranks=5 but each has only rank-0
effects. Reject effectless ranks rather than generating an ineffective NPC.
Categorize spells by their half-cost Perk tree; fall back to cost-bearing MGEF
schools, excluding zero-cost auxiliary effects. Include an other category.
Combine category and text filters without the old silent 100-row truncation.
Validate through real local HTTP APIs and actual headless browser controls.

User-requested corrections: choose a clothing purpose to assign its slot, or
override the slot explicitly; include standard wearable slots 32..42. Keep
reserved appearance layers out of automatic allocation. Standard body/hands/feet
items include the displaced original skin, without changing the avatar shape.

Move garment grouping controls into the generated-clothes area and present a
visible plus item for adding clothes. Explain that mesh reassignment reset
restores the name-based suggestions and discards those manual assignments.
Place this reset action after the mesh-assignment list so users encounter it
after editing the assignments, before the generated-clothes section.
Simplify overall-preview language, head-policy global defaults and reset labels.
Show one selected headgear model at a time with an avatar wearing it; reuse
geometry conversion when only visibility policy changes. Explain source-profile
selection in terms of armor replacers, not merely installed body mods.

Resolve class labels from their actual role, including Blade/Delphine. Filter
magic candidates by SPIT type/casting type and spell-tome BOOK DATA references,
so abilities, blessings, scripted effects, powers and diseases do not appear as
castable spells. Preserve imported settings.

Verify browser controls/export/reimport and a real headgear preview. Read back
standard-slot clothing geometry and plugin masks; run the existing regressions.

Show "前に作ったフォロワー" only inside STEP 01. Hide it automatically when
moving to STEP 02..05 or opening a conversion result; restore it when returning
to STEP 01. Retain the existing saved-result and equipment-edit opening action.

Refresh completed followers when returning with "もう一体作る", not only at
startup. Select the just-created result by its job ID, retain separate results
with the same plugin name, and make the first completed result visible even if
the initial history was empty. Verify completion -> again -> open saved result
through actual browser buttons, including repeated creations and fetch errors.
Run `node tests/browser-saved-results.cjs` after generating the browser role
fixtures below; its API fixture simulates completed conversions and never runs
Blender or writes installed game files.

Expose the 18 individual skill settings even in automatic mode, with a clear
switch to manual values. Explain that chosen Perks are granted explicitly;
skill levels and Perks are separate settings. Display CLAS skill and attribute
growth weights from actual DATA, without claiming predicted final skill values.
By default show combat styles with positive usage evidence from NPCs using the
character skeleton, resolving inherited race Traits. Other/unclassified styles
remain available via an all-styles switch. Preserve imported choices, including
styles outside the normal list. This is a recommendation filter, not a CSTY race
restriction. New followers default to essential and morality 0; imported explicit
protection and morality must not change. Verify actual UI navigation/import/export
and read back generated NPC skill values, flags and morality.

For isolated browser verification, run `python tests/browser-roles-fixture.py`
then `node tests/browser-roles.cjs` with Playwright available. This reads local
game records, serves the actual UI via mocked API responses, and exercises the
controls without starting a conversion or changing installed game data.

Preserve native headwear partitions 130/131/141/142/143 in the NIF. Their
corresponding 30/31/41/42/43 values are used only for equipment masks and
priority checks. Retain the native partition when splitting/exporting geometry,
and compare it with the original game mesh during final readback.


## 2026-10-16 STEP 01 order and equipment wording

Keep the requested reading order: equipment support and fitting controls,
body/clothing classification, generated-clothing settings, optional physics,
then the overall preview. Physics remains available with fixed outfits; the
classification and preview panels remain conditional on wardrobe support.
Keep existing element IDs, saved values and preview operations intact.

Describe fit_mode as which official items to support, and fit_source as which
appearance to fit. Explain vanilla versus deployed armor-replacer/BodySlide
models, fallback to vanilla, and that newly added third-party items are outside
the official item catalog. Both produce private equipment for the VRM body.
Update Japanese and English together and verify actual browser layout, support
and physics toggles, selection/export, and overall preview interaction.


## 2026-10-16 catalog feedback and reusable headgear previews

Immediately show the fitting panel and a localized live loading message when
fitting is enabled. Disable Next while the catalog is loading and reuse the
same in-flight request; reuse a loaded catalog for the same environment. Show
failure with a retry path. New UI sessions default to all official equipment;
explicit imported selected/all settings remain authoritative.

Headgear previews must not generate ESPs, scripts, validation animations, edit
kits or MOD ZIPs. Share avatar/skeleton/texture/body preparation across different
headgear. Cache fitted headgear separately from face/hair policy renders, reuse
completed caches across restarts, and invalidate for changed avatar geometry,
classification, sex/height, source profile, source assets or converter code.
Only publish a ready cache after success; incomplete/corrupt caches rebuild.
Show first-use preparation guidance (about a minute, depending on the model),
current phase. Keep cache reuse details in logs, not UI copy. Verify two different real headgear requests
plus a policy-only rerender, with one avatar preparation and no MOD packaging.


Verification: 124 Python tests and four browser flows pass. Slow catalog tests
hold the real fetch response while checking live feedback, disabled Next, input
reload/language changes, one-request reuse, failure/retry and imported settings.
The real Erys preview run took 62.37s initially, 14.49s for a different helmet,
12.10s for a policy-only render and 0.99s for the same image after app restart.
There were no ESP/ZIP files anywhere in the preview cache. The Falmer close-up
is pixel-identical to the previous full-conversion preview; Iron Helmet images
were visually inspected. A normal full MOD conversion and final validator also
pass after extracting shared appearance and DDS preview preparation.

## 2026-10-16 user-facing copy audit

Review fitting from its effective mode, not the length of fit_armors: all_official
intentionally saves an empty explicit list. Show all, selected count, or none and
the chosen appearance profile, preserving JSON values. Cover all/selected/off in
Japanese and English through actual STEP 05 navigation and JSON export.

Audit all five steps, result/edit screens, and generated helper/status messages in
Japanese and English. Keep text only when it helps a user choose, act, understand
a current state, or anticipate a meaningful limit/wait. Do not present internal
architecture, cache reuse, output implementation, QA requests, assurances about
completed requirements, or information already conveyed by a label. The preview
notice is one sentence: the first preview may take about a minute. Preserve
prerequisites, recovery instructions, native Skyrim terminology, stage selection
advice, saved settings, and all controls. Show shared clothing-slot guidance once
instead of repeating it for each garment. Logs and developer docs retain internal
details. Verify localized screens, loading/navigation and JSON round trips through
the existing browser flows; keep the first-preview warning separate from progress.
