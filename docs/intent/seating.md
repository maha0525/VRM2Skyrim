# Seated height compensation

Preserve small VRM proportions while aligning the seated pelvis with vanilla
chair/bench animations. Add automatic compensation and a manual offset to the
shared settings and wizard. Defaults: enabled, automatic, manual adjustment 0.
Require SKSE64 only; no RaceMenu dependency, furniture overrides or equip changes.

Calculate the offset by sampling the official sex-specific chair idle HKX on
both the delivered custom skeleton and vanilla skeleton. Preserve NPC directly
beneath the original scene root in both skeleton and meshes. Do not insert a
wrapper above NPC. Apply a temporary Z offset to the existing unanimated NPC
node, saving its previous value and restoring only the value this script owns.
Standing code must never force the node to zero. Apply the offset only
while seated on recognized chair furniture. Exclude sleeping, mounted actors,
workbenches and ground/ledge markers. Classify Skyrim.esm FURN records by actual
marker type and workbench data, never editor-ID name guesses; no global FURN edits.

OnLoad/OnInit/OnSit/OnGetUp/OnNiNodeUpdate refresh from current state, including
already-seated actors. Clear on exit/unload, and reconcile while seated so delayed
events or geometry rebuilds cannot accumulate an offset. Log transitions only.
Use private script names and records for multiple followers. Package the computed
report and explain SKSE requirements, manual units and disabling for another
furniture-height correction mod. Imported explicit settings remain unchanged.

Verify neutral skeleton globals/local animation transforms are preserved, sampled
seated pelvis residuals, actual compiled PEX lifecycle execution, VMAD/FLST readback,
browser controls/export/reimport, and a rebuilt Sumire ZIP using her existing assets.

0.9.6 regression: an identity wrapper above NPC changed the engine-facing root
hierarchy in the skeleton and all exported skins. Equal rest/FK matrices and
passing script tests did not establish that this hierarchy was safe; the user
observed a destroyed standing body. Reject that exact topology in validation.
For the fix, compare all node parents, locals/globals, skin binds, vertex weights,
geometry and texture contents against the known-good 0.9.5 output, and render the
delivered standing mesh. Structural contracts and output appearance are separate
requirements from mathematical pose checks. Use this invariant for every future
root/helper-node change, not only seated height correction.
