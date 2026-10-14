# Original VRM hats and helmets

Create removable headwear from original VRM meshes, including the user's Cecil
Obj135. Add a headwear purpose with automatic equip slot 30, manual head/hair
slots 30/31, head clothing/helmet keywords, and native headwear NIF partitions
130/131/141/142/143. Native equip masks must replace headwear without scripted
unequips. Preserve original geometry, skin, skeleton and unrelated clothing.

Optional per-item hide_face/hide_hair defaults are false, preserving the original
hat/hairstyle. Reuse existing private skin variants and head visibility runtime,
including without any fitted Skyrim equipment. Include generated headwear ARMO
IDs in the visibility lists. Require the requested face/hair to be separately
classified; hiding only removes existing meshes and never creates missing hair.
Source and converted previews must show the same equipped-item visibility policy.

Verify actual wizard selection, export/import and preview request. Independently
read native slots, keywords, VMAD/lists and compiled PEX equip/unequip behavior.
Convert the supplied VRM and inspect hat-on/off output renders; keep both its
source and generated test MOD local. Do not resume seating or body physics work.
