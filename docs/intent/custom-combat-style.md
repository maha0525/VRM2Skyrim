# Private follower combat style editor

Provide existing-style use and private editing in STEP 03. Explicitly copy an
existing style as a starting point; switching the candidate must not overwrite
edits until Copy is pressed. Confirm replacement of edited values. Show melee,
ranged and magic equipment scores and dual-wield permission first, then all CK
General/Melee/Close Range/Long Range fields, with Flight collapsed separately.
Use Japanese/English explanations plus CK names, range and numeric controls,
original values, and per-field/all-field reset.

Save mode, copy source and numeric/flag snapshots in JSON. Importing settings,
opening a saved follower, changing language or applying a role preset must not
silently recopy over custom values. Old settings remain on the existing-style
path. Clone the source CSTY into a reserved private FormID and unique EditorID,
preserve unknown fields/bits and omitted float tails, and point only this NPC's
ZNAM at the clone. No override of a vanilla CSTY; no runtime script or extra
dependency. Existing generated records and their IDs must remain unchanged.

Validate finite nonnegative representable floats and known field names, source
and flags before conversion. UI explains equipment scores are preferences,
not damage multipliers or fixed probabilities; dual wield also needs suitable
weapons. Log source/private identity and changed fields at generation. Verify
real game field readback, cloned ESP linkage/isolation, JSON round trips and
invalid inputs, then actual browser Copy/Edit/Reset/Import/Export and language
switching. Commit only; do not push. User will evaluate game AI behavior.

Schema reference: xEdit `Core/wbDefinitionsTES5.pas`, CSTY definition:
https://github.com/TES5Edit/TES5Edit/blob/dev-4.1.6/Core/wbDefinitionsTES5.pas#L4326-L4382
Validated all editable local Skyrim.esm style snapshots, including omitted
CSME/CSFL tails and the dual-wield styles mentioned by the user. Tests cover
unknown-data preservation, reserved-ID isolation and original-record immutability.
Browser evidence is in `build/ui-roles/combat-style-*.png` and test logs.
Run `python tests/browser-roles-fixture.py`, then
`node tests/browser-combat-style.cjs` with Playwright available.
