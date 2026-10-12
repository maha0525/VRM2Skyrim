# Native equipment slots

The user observed original clothing and new armor worn together inside the
follower trade menu, resolved only after closing it, and a crash at that moment.
The old converter assigned clothing independent extended slots and asynchronously
removed it in OnObjectEquipped. That permitted the unwanted intermediate state.
Remove this replacement policy rather than shortening its delay.

Use ARMO equip masks for exclusive equipment: torso outfits=32, gloves=33,
shoes=37. Combine simultaneously worn torso meshes into one ordinary outfit
item. Alternatives may share a slot, but cannot be initially equipped together.
Extended slots are intentional coexistence layers, never promise to remove them
when a cuirass is equipped. Keep manual slots available. Do not change vanilla
armor masks or add global clothing-slot conflicts to the combined fitting patch.

ARMO occupancy and ARMA geometry coverage are different: torso ARMO uses 32;
its ARMA covers 32/34/38 and retains displaced original skin. A full outfit that
contains shoes/gloves occupies 32/33/37 and includes the corresponding skin.
Wizard defaults/splitting group meshes by native region; no fallback moves a
second torso item to an extended slot. Imported legacy replacement groups are
migrated to native outfit sets with an explicit wizard notice.

Keep ordinary CNTO inventory and empty OTFT for removable trade-menu items.
The initial equip script runs once only. Its old replacement properties/event
names remain inert for save compatibility; no trade/equip/load handler removes
clothes, restores an outfit, or mutates inventory. Inspect shipped PEX bytecode
and simulate deferred menu events with real generated ARMO masks to verify that
mutual exclusion occurs before any script event executes.

Read back standard garment NIFs and original retained skin, validate a full
ordinary follower build, test actual wizard controls/export/reimport, and push
source without avatar/game assets. The available logs contain no crash stack;
the observed CTD is not proof of a particular crashing function.
