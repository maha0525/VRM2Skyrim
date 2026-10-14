# Wizard controls, standard clothing slots and headgear preview

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
