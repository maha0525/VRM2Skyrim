# Chair and bench height correction

[日本語](#日本語)

Since 0.9.6-dev, STEP 03 includes chair/bench height correction, enabled by
default. This requires matching [SKSE64](https://skse.silverlock.org/); launch
the game through `skse64_loader.exe`. RaceMenu is not required.

Automatic mode samples the official male/female chair idle animation on both
the original game skeleton and the generated avatar skeleton. The median seated
pelvis-height difference is the offset. This detects short bones even when the
NPC and skeleton scale values are both 1.0. It does not enlarge the avatar.

The manual field adds an offset in Skyrim units: positive moves up, negative
moves down. With automatic calculation off, this is the entire correction.
Turn the correction off when using another furniture-height correction MOD.

A private unanimated node applies the correction while the follower is seated.
The shipped node's transform is identity: standing height and proportions stay
unchanged. The script reconciles state on load, sitting/getting up, skeleton
rebuilds and updates during furniture use; repeated events do not add offsets.
It never moves the placed reference or changes equipment.

The generated list includes Skyrim.esm chair/bench records whose FNPR markers
are all Sit (type 1), excluding workbenches, perches and invisible markers. Beds,
horses, floor/ledge idles and DLC/MOD-only furniture are outside this list. Vanilla
furniture appearance replacers keep working because the original form is used.
Unusual/custom sitting animations may need manual adjustment. The calculation
uses the pelvis as its reference; cushion contact also depends on the mesh shape.

The computed offset, sampled animation, frame count and residual are saved in
`seating.json` and included under the follower's private metadata directory.
Papyrus logs transitions as `VRM2Skyrim: seated height=...`.

Implementation sources: [SKSE NetImmerse functions](https://github.com/ianpatt/skse64/blob/master/scripts/modified/NetImmerse.psc),
[SKSE furniture-reference function](https://github.com/ianpatt/skse64/blob/master/scripts/modified/Actor.psc),
and [xEdit's FURN schema](https://github.com/TES5Edit/TES5Edit/blob/dev-4.1.6/Core/wbDefinitionsTES5.pas).
The runtime is original MIT-licensed code, not a copy of another height-fix MOD.

## 日本語

STEP 03の「椅子に座ったときの高さ補正」で設定します。初期値は補正有効・
自動計算オン・微調整0です。生成したMODにはゲームに対応するSKSE64が必要です。
`skse64_loader.exe`から起動してください。RaceMenuは不要です。

自動計算は公式の着座アニメーションを使い、標準骨格とアバターの腰の高さを
比較します。倍率が1.0でも、元VRMの脚や腰が短いことを検出できます。
微調整はSkyrim単位で、＋なら上へ、−なら下へ動きます。自動計算をオフにすると
微調整の数値だけを使います。他の家具高さ補正MODを使うときは本機能をオフにします。

本体ゲームの椅子・ベンチが対象です。ベッド・馬・作業台・地面に座る動作と、
DLCや追加MOD独自の家具は対象リストに含みません。元の家具を使う見た目の置換MODは
対象を維持します。独自の着座アニメーションや座面への接触具合は微調整で合わせられます。

立っているときの身長・体型は変えません。立ち上がり・再ロード・装備による骨格の
再生成にも対応し、補正を重ねて加算しません。衣服の装備やNPC参照の座標は操作しません。
計算結果は各フォロワーの`seating.json`に保存します。
