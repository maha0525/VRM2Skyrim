# Wizard controls, standard clothing slots and headgear preview

User-requested corrections: choose a clothing purpose to assign its slot, or
override the slot explicitly; include standard wearable slots 32..42. Keep
reserved appearance layers out of automatic allocation. Standard body/hands/feet
items include the displaced original skin, without changing the avatar shape.

Move garment grouping controls into the generated-clothes area and present a
visible plus item for adding clothes. Explain that mesh reassignment reset
restores the name-based suggestions and discards those manual assignments.
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

Preserve native headwear partitions 130/131/141/142/143 in the NIF. Their
corresponding 30/31/41/42/43 values are used only for equipment masks and
priority checks. Retain the native partition when splitting/exporting geometry,
and compare it with the original game mesh during final readback.
