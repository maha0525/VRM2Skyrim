# Optional hair and cloth physics / 髪・布の物理演算

The development branch `codex/fsmp-physics` exports optional FSMP systems.
The stable `main` branch remains 0.8.1.

## Using the wizard

1. Select your VRM. Enable **髪・布を揺らす（FSMP・開発版）**.
2. Select the hair and cloth meshes that should move. Leave rigid accessories,
   shoes and the avatar's body out of this selection. With no explicit selection,
   assigned hair/clothing and actually weighted VRM spring meshes are candidates.
3. Choose **揺れの硬さ**: soft 0.3, normal 1, firm 3.
4. Generate the follower ZIP and install it normally. Enable Faster HDT-SMP and
   the SKSE64 build matching your game, then launch through SKSE64.

Turning the option off generates the conventional fixed appearance. FSMP is
not installed or bundled by this tool. Rigged secondary bones are required;
the converter reports an error when the selected meshes have no movable chain.
It does not invent cloth weights for an entirely rigid mesh.

## Generated assets

- Secondary bones retain their source rest transforms and vertex weights in
  the private skeleton. Humanoid animation bones retain their existing locals.
- Hair scalp roots stay fixed. Weighted cloth roots can pivot on an animated
  humanoid anchor. Rigid single-bone accessories are excluded.
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

## Diagnostics and editing

`skeleton.json` records the source-to-private bone identities and full rest
transforms. `conversion.json` records each mesh's physics mapping.
`physics.json` lists NIF/XML pairs. Readback checks resolve links, bones,
constraint bodies, collision shapes, hidden flags, weights and collision bind
poses. Rebuilding the XML stage is idempotent.

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

身体との接触には、元の身体から作る非表示の衝突メッシュを使います。
XML、骨、衝突タグはフォロワー・衣服ごとの専用です。脱いだ衣服は自身の
物理システムごと外れ、他の衣服や別フォロワーの骨を制御しません。

## References

- [Faster HDT-SMP](https://www.nexusmods.com/skyrimspecialedition/mods/57339)
- [FSMP source](https://github.com/DaymareOn/hdtSMP64/tree/dev)
- [FSMP author XML guide](https://github.com/DaymareOn/FSMP-Validator/wiki)
- [VRM spring-bone specification](https://vrm.dev/en/vrm1/springbone/)
