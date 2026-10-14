# Original VRM hats and helmets / 元VRMの帽子・兜

Since 0.10.0-dev, original VRM meshes can become removable headwear.
Enable clothing/armor separation, add an item under generated clothes, and assign
the hat mesh to it. Choose **帽子・兜** as its purpose. The automatic equip slot is
30 (head); manual slots 30 and 31 are also available. Another item occupying the
same slot replaces it through Skyrim's native equip handling.

Each head item can optionally hide the classified face or hair while equipped.
Both options are off by default, preserving the avatar's original hat/hairstyle.
Visibility switching requires matching SKSE64 and separately classified existing
face/hair meshes. Removing the item restores those original meshes. No VRM-side
hat-removal gimmick is required, and no fitted Skyrim armor is required.

This does not create hair under a hat or cut a combined hat/hair mesh apart.
If the original VRM lacks the uncovered hairstyle, that geometry must be authored
in the model. Ordinary hat removal with visibility options off uses native equip
slots and does not itself require SKSE64; enabled seating/physics may still do so.

## 日本語

0.10.0-devから、元VRMの帽子・兜を着脱する頭装備にできます。

1. 「衣服・防具の扱い」を対応ありにします。
2. 「生成する衣服」で一品追加し、帽子のメッシュを「着脱する衣服」としてその品へ割り当てます。
3. 「部位・用途」を「帽子・兜」にします。装備枠は自動で30（頭）になります。
4. 顔や髪を隠したい場合だけ、その頭装備のチェックを入れます。標準では両方を残します。

顔・髪の切替には、上の一覧で対応する元メッシュを顔・髪として分類し、SKSE64を導入してください。
帽子を外すと元のメッシュへ戻ります。VRM側に着脱ギミックを用意する必要はありません。
Skyrimの既存装備を変換しなくても利用できます。

帽子の下の髪を新しく作る機能ではありません。帽子と髪が一体の場合は事前のメッシュ分離が必要で、
元モデルに帽子を外した髪型が存在しない場合は制作側で用意します。
