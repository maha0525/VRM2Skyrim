# Optional hair and cloth physics / 髪・布の物理演算

The development branch `codex/fsmp-physics` exports optional FSMP systems.
The stable `main` branch remains 0.8.1.

## Using the wizard

1. Select your VRM. Enable **髪・布を揺らす（FSMP・開発版）**.
2. Select the hair and cloth meshes that should move. Leave rigid accessories,
   shoes and the avatar's body out of this selection. With no explicit selection,
   assigned hair/clothing and actually weighted VRM spring meshes are candidates.
3. Choose **揺れの硬さ**: softer 0.3, calm (default) 1, firmer 3.
   All choices use geometry-scaled damping and restricted twist. The default
   adds no wind force; it lets long cloth fall without encouraging repeated sway.
4. Generate the follower ZIP and install it normally. Enable Faster HDT-SMP and
   the SKSE64 build matching your game, then launch through SKSE64.

Turning the option off generates the conventional fixed appearance. FSMP is
not installed or bundled by this tool. Rigged secondary bones are required;
the converter reports an error when the selected meshes have no movable chain.
It does not invent cloth weights for an entirely rigid mesh.

## Generated assets

- Secondary bones retain source geometry, weights and anatomical joint pivots.
  Simulation origins move to mass centres with compensated skin binds.
  Humanoid animation bones retain their existing locals.
- Hair scalp roots and garment attachment roots stay fixed to the animated
  body. Sleeve bones close to the arm extend that fixed prefix; hanging distal
  cloth retains its independent motion. Rigid single-bone accessories are excluded.
- Separate clothing components receive distinct copies of shared secondary
  chains. Removing one piece cannot stop another piece's simulation, and two
  systems do not drive the same dynamic bone.
- Original body vertices generate compact collision hulls. A hidden skinned
  `V2SCollision_Body` shape carries them inside each owning NIF. FSMP uses a
  per-triangle body surface and per-vertex hair/cloth surfaces for contacts.
  Bone collision shapes alone cannot provide these contacts: FSMP excludes
  rigid bone bodies from Bullet's normal collision broadphase.
- XMLs live under `SKSE/Plugins/hdtSkinnedMeshConfigs/vrm2skyrim/<mod-id>/`.
  The NIF root links them through `HDT Skinned Mesh Physics Object`.
  Collision tags are private to each component and MOD. `defaultBBPs.xml` is
  never changed.
- Head visibility variants retain only their available dynamic chains.
  Equipping/removing clothes continues to use native equipment slots.

VRM 0/1 spring metadata identifies candidate chains. The generated mass,
inertia, centre of mass, damping and spring settings are converter presets;
VRM parameters are not copied as if they were equivalent Bullet parameters.
Quon and Erys's inspected VRMs have dedicated weighted chains without spring
metadata, so presets also work for that case.

### Calm default (0.9.1-dev)

The first game test reported excessive hair and sleeve oscillation. The shared
generator now uses the following profile, including for imported settings:

- Angular stiffness scales with geometric sphere inertia, using a nominal
  0.65 Hz coefficient at the standard multiplier rather than constant torque.
  Explicit XML inertia is five times the geometric sphere inertia, without
  increasing restoring stiffness. This slows abrupt rotations without pulling
  gravity-draped sleeves back into a horizontal pose. See the 0.9.3 correction below.
- Constraint damping targets a damping ratio of 1.1 using the pivot's
  parallel-axis inertia and gravitational restoring torque. Long sleeves
  therefore receive more damping than short hair tips. Bullet timestep safety
  caps remain enabled for connected moving bodies.
- Bone velocity damping is 0.85 linear / 0.95 angular; wind factor is zero.
- Dynamic mass tapers from 0.1 by 0.6 per dynamic ancestor (floor 0.0025).
  Lighter tips reduce upstream loads in long chains. The geometric sphere covers
  both the influenced surface and pivot-to-centre-of-mass lever, without the
  former radius cap of eight game units.
- Constraint Z follows the influenced surface. X permits up to 1.7 radians of
  gravity-plane swing (so horizontal sleeves can fall), Y up to 1.1 radians of
  lateral swing, Z only 0.25 radians of twist. The middle Euler axis stays below
  its singularity. This replaces unrestricted 2.4-radian motion on every axis.
- `frameInB` has zero origin in **bone-local** coordinates. FSMP itself applies
  the inverse centre-of-mass transform when constructing the rigid-body joint.
  Subtracting the centre twice, as the initial generator did, moves the pivot.

The offline diagnostic uses FSMP's gravity conversion, `9.8 / 0.01425` game
units/s², rather than treating game units as metres. It uses 16 solver iterations
and one step per 60 Hz frame, translating anchors by 30 game units and turning
them through 35 degrees before measuring settling. These settings do not modify
the user's global FSMP configuration.

### Protected attachments (0.9.2-dev)

The game test revealed that lower sway alone could not preserve sleeve openings:
their attachment bones were still free movers. The shared XML stage now fixes
the first secondary garment root to its animated parent. For an arm-attached
chain, it extends the fixed prefix while 90% of strongly influenced vertices
(weight above 0.2) lie inside the avatar arm hulls expanded by 4% of body height.
Only the corresponding left/right upper arm, forearm and hand hulls are used;
nearby torso surfaces cannot accidentally pin a hanging sleeve tail.

The prefix stops at the first moving bone. A fixed node beneath a mover would
inherit the mover's displacement, so distal cloth is never frozen in isolation.
Hair keeps its existing policy. This rule uses source ancestry, weights and
geometry, without character-specific names. Protected bones have mass zero and
no spring constraint. Their original NIF hierarchy, rest transforms and weights
remain intact; the body animation supplies their movement. Each XML can also
retain a fully fixed selected component, replacing its previous linked physics
system instead of leaving a stale dynamic XML behind.

`physics.json` records `protected_bones` and the reason for each pin. Readback
verifies that they have no dynamic mass or spring constraint. The diagnostic's
`--articulate-arms` option bends shoulders and elbows while moving/turning the
actor, applying the same arm motion to the newly fixed sleeve nodes.

### Direct runtime inertia (0.9.3-dev)

The user confirmed the repaired sleeve openings and arm following, but long
cloth still trembled at rest. Tracing the released FSMP 4.1.1 XML reader through
its rigid-body constructor to Bullet 3.25 revealed a generator error: XML
`inertia` is a direct local inertia tensor, not a divisor of shape-derived
inertia. Previous builds wrote 0.2 on every axis while the offline diagnostic
treated that number as a divisor. The generated runtime and diagnostic therefore
used different rotational resistance.

The shared generator now writes `5 * (2/5) * mass * radius²` on each axis, in
mass times squared game units. Radius covers the influenced surface and the
pivot-to-centre-of-mass lever. Constraint damping uses that same explicit
inertia plus the parallel-axis term; the bone shape itself does not calculate
inertia in FSMP. Mass taper, spring torque, protected attachments, angular limits
and mesh collision settings remain as in 0.9.2, isolating this correction.

The diagnostic reconstructs a Bullet sphere with radius `sqrt(I / (0.4 * mass))`
from the delivered XML, and records the inertia round trip for each mover.
It rejects zero, negative, non-finite or anisotropic inertia rather than silently
simulating another tensor. `--stationary` checks undisturbed anchors from the
start; moving/turning and articulated-arm checks still test subsequent settling.
The final second is checked for peak linear and angular velocity, so the last
frame alone cannot hide periodic twitching.

`physics.json` records `calm_explicit_inertia_v3`, direct runtime units, and the
geometry multiplier. Component logs include the generated inertia range.
This is an XML-only physics update for existing 0.9.2 followers: replace the
follower package and restart Skyrim; retain the existing combined armor patch.

### Unified render/contact frames (0.9.4-dev)

The 0.9.3 game feedback reported continued lateral sleeve twitching and waist
cloth passing through the body. Read-only hashes confirmed the installed XMLs
matched the delivered 0.9.3 build. The FSMP 4.1.1 contact path computes
`inverse(COM) * rigWorld`, while its visible-bone write path computes
`rigWorld * inverse(COM)`. Nonzero COM offsets therefore displace collision
geometry differently from the rendered skin when the bone or actor rotates.
The Quon diagnostic reproduced up to 16.963 game units of frame displacement.

The shared conversion stage now places each dynamic private node at its mass
centre and emits identity `centerOfMassTransform`. Its original anatomical
pivot stays in `frameInB` as a negative centre offset. Skin-to-bone matrices are
compensated so `boneWorld * skinBind` retains its original value. Child world
frames, bone names/hierarchy, vertices, triangles, weights and textures remain
intact. Native NIF saving recalculates per-bone skin bounds from the adjusted
binds. Inertia, gravity and joint coefficients retain the 0.9.3 profile.

`skeleton.json` retains source rest frames; `physics-frames.json` records the
new simulation frames and original-local centre offsets. `physics.json`
identifies `unified_contact_frames_v4`. Validation checks identity COM and the
delivered skeleton frames. Native origin/bind edits are idempotent, using the
NIF's float32 hierarchy precision tolerance rather than repeatedly correcting
sub-millimetre roundoff.

Replace the **complete follower ZIP**, including NIFs and XMLs, then restart
Skyrim. ESP records, item identities and runtime scripts are unchanged; retain
the existing combined armor patch. This correction does not require a save
reset or changing the global FSMP configuration.

## Diagnostics and editing

`skeleton.json` records the source-to-private bone identities and full rest
transforms. `conversion.json` records each mesh's physics mapping.
`physics.json` lists NIF/XML pairs. Readback checks resolve links, bones,
constraint bodies, collision shapes, hidden flags, weights and collision bind
poses. Regenerating physics frames and XMLs is idempotent.

`physics_preview_blender.py -- --output <build>` runs an offline Bullet
joint/gravity simulation from the emitted XML. `render_blender.py` accepts
`--physics-frame <frame>` to render a sampled pose using delivered NIF meshes.
This diagnostic checks anchor following, pivots, falling and settling. FSMP's
custom skinned-mesh contact solver remains the runtime contact implementation;
the offline diagnostic deliberately disables rigid bone-body collisions.

The original-asset physics is independent of fitted Skyrim armor. Outfit Studio
edits of fitted equipment retain the original physics assets. After editing
original cloth meshes outside the tool, regenerate the affected NIF/XML pair
and keep bone names, skinning and the root XML link together.

## 日本語での要点

有効化すると元VRMの独立した骨とウェイトを残し、髪・布用の物理設定を
生成します。VRMに揺れ設定がなくても、独立した骨があれば対応できます。
身体・硬いアクセサリー・靴は選択から外し、髪や振袖などを選んでください。
未選択なら分類した髪・衣服を候補にします。

揺れの硬さは「穏やか（標準）」から始めてください。長さに合わせた減衰、
ねじれの制限、風なしの設定を全プリセットで使います。柔らかめ・硬めへ
変更しても減衰は自動調整します。横に伸びた布が垂れる方向は残しています。

衣服の付け根と腕に沿う袖の部分は、身体のアニメーションに追従させます。
その先の布を揺らすので、袖口そのものが重力でずれたり回ったりするのを
防ぎます。元VRMや各キャラクターの設定を手で書き換える必要はありません。

身体との接触には、元の身体から作る非表示の衝突メッシュを使います。
XML、骨、衝突タグはフォロワー・衣服ごとの専用です。脱いだ衣服は自身の
物理システムごと外れ、他の衣服や別フォロワーの骨を制御しません。

## References

- [Faster HDT-SMP](https://www.nexusmods.com/skyrimspecialedition/mods/57339)
- [FSMP source](https://github.com/DaymareOn/hdtSMP64/tree/dev)
- [FSMP author XML guide](https://github.com/DaymareOn/FSMP-Validator/wiki)
- [Spring and damping units](https://github.com/DaymareOn/FSMP-Validator/wiki/33-%E2%80%90-Springs-stiffness-and-damping)
- [Runtime frame conversion](https://github.com/DaymareOn/hdtSMP64/blob/dev/src/hdtSkinnedMesh/hdtGeneric6DofConstraint.cpp)
- [FSMP 4.1.1 inertia reader](https://github.com/DaymareOn/hdtSMP64/blob/v4.1.1/src/hdtSkyrimSystem.cpp#L462)
- [Bullet 3.25 direct inertia](https://github.com/bulletphysics/bullet3/blob/3.25/src/BulletDynamics/Dynamics/btRigidBody.cpp#L226)
- [FSMP 4.1.1 contact transforms](https://github.com/DaymareOn/hdtSMP64/blob/v4.1.1/src/hdtSkinnedMesh/hdtSkinnedMeshBone.cpp)
- [FSMP 4.1.1 visible transforms](https://github.com/DaymareOn/hdtSMP64/blob/v4.1.1/src/hdtSkyrimBone.cpp)
- [VRM spring-bone specification](https://vrm.dev/en/vrm1/springbone/)
