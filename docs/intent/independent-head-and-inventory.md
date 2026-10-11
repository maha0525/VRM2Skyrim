# Independent head and ordinary equipment

The user observed three 0.5.1 failures: original garments are hidden from normal
follower inventory, fitted armor overlaps them, and AFT outfit management removes
the native-head cover and exposes an unwanted dark human face. The deployed AFT
source removes/transfers inventory and assigns an empty default outfit. The
deployed fitting plugin/patch are correct for banded iron armor and iron boots;
the user confirmed the cuirass renders. Elven boots/hood were not converted.

Replace the worn-mask head workaround with a private empty head part and empty
FaceGen asset, used by both NPC and race, while keeping the VRM face in Skin.
Retain the old cover's ID as inert compatibility data, never worn or required.
Put every garment in CNTO with an empty OTFT. An actor script equips configured
initial garments once, then releases ownership. Never reset inventory/outfits
on load or periodically override AFT. Clothes and selected fitted armor exclude
one another by user-configurable body/hands/feet groups; accessories stay alone.
Switch events only unequip conflicting items, never delete or transfer them.

Validate actual head assets/records without relying on any equipped item, PEX
and VMAD property bindings, fresh initial inventory, and equip/unequip transitions
after removing all items and changing outfits. Preserve original mesh/texture
bytes. Real game rendering and AFT behavior require game confirmation; generated
binary/event-model tests cannot prove them. No computer UI operation is authorized.
