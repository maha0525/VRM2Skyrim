"use strict";
const wardrobeSlots=[30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,53,54,55,56,57,58,59];
const wardrobeSlotNames={30:'頭（帽子・兜）',31:'髪',32:'胴',33:'手袋',34:'前腕',35:'首飾り',36:'指輪',37:'靴',38:'すね',39:'盾',40:'尻尾',41:'長い髪',42:'サークレット',43:'耳',44:'顔周り',45:'首周り',46:'マント',47:'バッグ',48:'その他',49:'下半身',53:'脚の追加パーツ',54:'タイツなど',55:'追加パーツ',56:'胴の追加パーツ',57:'肩周り',58:'腕の追加パーツ',59:'腕の追加パーツ'};
function wardrobeOccupiedSlots(slot,kind){return slot===32&&kind==='full'?[32,33,37]:[slot];}
function allocateWardrobeSlots(){
  const used=new Set([...wardrobeState.garments.values()].filter(g=>g.slot_mode!=='auto'&&g.equipped).flatMap(g=>wardrobeOccupiedSlots(g.slot,wardrobeItemKind(g))));
  for(const g of wardrobeState.garments.values()){
    if(g.slot_mode!=='auto')continue;
    const kind=wardrobeItemKind(g),primary={head:30,body:32,legs:32,full:32,hands:33,feet:37,cloak:46,backpack:47,accessory:48}[kind];
    // A second torso item must not silently become a coexistence layer.
    g.slot=kind==='accessory'?[48,49,53,54,55,56,57,58,59,44,45].find(s=>!used.has(s))??48:primary;
    if(g.equipped)wardrobeOccupiedSlots(g.slot,kind).forEach(s=>used.add(s));
  }
}

const wardrobeKinds={head:'帽子・兜',body:'胴の衣装（上下まとめて）',legs:'下半身（胴装備と同じ32番）',full:'全身セット（胴・手袋・靴）',hands:'手袋',feet:'靴',cloak:'マント',backpack:'バッグ',accessory:'その他のアクセサリー'};
function wardrobeHeadwear(g){return wardrobeItemKind(g)==='head'||[30,31,41,42,43].includes(g.slot);}
function wardrobeSlotLabel(slot){return `${slot} · ${tr(wardrobeSlotNames[slot]||'追加の装備枠')}`;}
function wardrobeItemKind(g){if(g.item_kind)return g.item_kind;const n=g.name.toLowerCase();for(const [kind,pattern]of [['feet',/boot|shoe|loafer|sandal|靴|ブーツ|サンダル/],['head',/helmet|helm|hood|hat|(?:^|[_ .-])cap(?:$|[_ .-])|帽子|兜|フード/],['hands',/glove|gauntlet|手袋|籠手/],['backpack',/backpack|リュック|バックパック/],['cloak',/cloak|cape|マント|ケープ/],['legs',/tights|stocking|skirt|pants|trouser|タイツ|スカート|ズボン/],['accessory',/accessor|ring|necklace|bracelet|earring|眼鏡|指輪|首飾り|アクセ/]])if(pattern.test(n))return kind;return 'body';}
const wardrobeState={nodes:new Map(),garments:new Map(),hash:'',sequence:0,preview:null,revision:0};
const wardrobeRoles={body:'身体',underwear:'下着（無装備でも表示）',face:'顔（頭装備で切替）',hair:'髪（頭装備で切替）',fixed:'常時表示のアクセサリー',garment:'着脱する衣服'};
function wardrobeEquipmentGroup(g){if(g.equipment_group)return g.equipment_group;if(wardrobeHeadwear(g))return 'accessory';const n=g.name.toLowerCase();if(/boot|shoe|loafer|sandal|靴|ブーツ|サンダル/.test(n))return 'feet';if(/glove|gauntlet|手袋|籠手/.test(n))return 'hands';if(/accessor|ring|necklace|bracelet|earring|backpack|cloak|cape|眼鏡|指輪|首飾り|アクセ|リュック|マント|ケープ/.test(n))return 'accessory';return 'body';}
function garmentDefaults(id,name,slot=32){return {id,name,nodes:[],slot,slot_mode:'auto',armor_type:'clothing',armor_rating:0,weight:0,value:0,equipped:true,item_kind:wardrobeItemKind({name})};}
function wardrobeNativeGroups(){
  wardrobeState.garments.clear();const groups=new Map();
  for(const [node,p]of wardrobeState.nodes){
    if(p.role!=='garment')continue;
    const name=state.source.parts.find(part=>part.node===node).name,kind=wardrobeItemKind({name});
    const region=kind==='legs'?'body':kind,key=['body','hands','feet'].includes(region)?'outfit_'+region:'part_'+node;
    if(!groups.has(key)){const g=garmentDefaults(key,{body:tr("胴の衣装セット"),hands:tr("手袋"),feet:tr("靴")}[region]||name);g.item_kind=region;groups.set(key,g);wardrobeState.garments.set(key,g);}
    p.group=key;
  }
}
function migrateLegacyWardrobe(){
  const groups=new Map(),kept=new Map();
  let recordIndex=0;for(const [id,g]of wardrobeState.garments){
    g.record_index=recordIndex++;
    const category=wardrobeEquipmentGroup(g);delete g.equipment_group;
    if(category==='accessory'){g.slot_mode='manual';kept.set(id,g);continue;}
    g.slot={body:32,hands:33,feet:37}[category];g.slot_mode='manual';
    if(category==='hands'||category==='feet')g.item_kind=category;
    if(g.equipped&&groups.has(category)){const first=groups.get(category);first.name=(first.name+' / '+g.name).slice(0,128);first.weight+=g.weight;first.value+=g.value;first.armor_rating=Math.max(first.armor_rating,g.armor_rating);for(const p of wardrobeState.nodes.values())if(p.group===id)p.group=first.id;}
    else{kept.set(id,g);if(g.equipped)groups.set(category,g);}
  }
  wardrobeState.garments=kept;
}
function wardrobeLoad(source,settings=null){
  wardrobeState.nodes.clear();wardrobeState.garments.clear();wardrobeState.sequence=0;
  $('wardrobe-migration').hidden=true;
  wardrobeState.revision++;
  if(!source){renderWardrobe();return;}
  const imported=settings?.armor_support&&settings.appearance_parts?.garments;
  wardrobeState.hash=imported?settings.appearance_source_sha256:source.sha256;
  if(imported){
    for(const g of settings.appearance_parts.garments)wardrobeState.garments.set(g.id,{...g,nodes:[...g.nodes]});
    for(const role of ['body','underwear','fixed'])for(const node of settings.appearance_parts[role]||[])wardrobeState.nodes.set(node,{role,group:''});
    for(const role of ['face','hair'])for(const node of settings.appearance_heads?.[role]||[])wardrobeState.nodes.set(node,{role,group:''});
    for(const g of settings.appearance_parts.garments)for(const node of g.nodes)wardrobeState.nodes.set(node,{role:'garment',group:g.id});
    if(!settings.wardrobe_policy){migrateLegacyWardrobe();$('wardrobe-migration').hidden=false;}
  }else{
    wardrobeState.garments.set('outfit',garmentDefaults('outfit',tr("元の衣装")));
    for(const p of source.parts){const role=p.suggested_role==='fixed'?/hair/i.test(p.name)?'hair':/face|head|eye|mouth/i.test(p.name)||p.materials.some(m=>/face|eyelash|eyebrow/i.test(m))?'face':'fixed':p.suggested_role;wardrobeState.nodes.set(p.node,{role,group:role==='garment'?'outfit':''});}
    wardrobeNativeGroups();
  }
  $('wardrobe-preview-images').replaceChildren();$('wardrobe-preview-status').textContent='';renderWardrobe();
}
function wardrobeCollect(){
  const usedIds=new Set([...wardrobeState.garments.values()].filter(g=>g.record_index!==undefined).map(g=>g.record_index));
  for(const g of wardrobeState.garments.values())if(g.record_index===undefined){g.record_index=Array.from({length:16},(_,i)=>i).find(i=>!usedIds.has(i));usedIds.add(g.record_index);}
  allocateWardrobeSlots();const parts={body:[],underwear:[],fixed:[],garments:[]};
  const heads={face:[],hair:[]};
  for(const [node,p]of wardrobeState.nodes)if(p.role!=='garment'){if(p.role==='face'||p.role==='hair'){parts.fixed.push(node);heads[p.role].push(node);}else parts[p.role].push(node);}
  for(const [id,g]of wardrobeState.garments){const nodes=[...wardrobeState.nodes].filter(([,p])=>p.role==='garment'&&p.group===id).map(([node])=>node);if(nodes.length)parts.garments.push({...g,nodes});}
  return {wardrobe_policy:'native_slots',appearance_parts:parts,appearance_source_sha256:wardrobeState.hash,appearance_heads:heads.face.length||heads.hair.length?heads:{}};
}
function wardrobeClearPreview(){
  wardrobeState.revision++;
  $('head-preview-images').replaceChildren();$('head-preview-status').textContent='';
  $('wardrobe-preview-images').replaceChildren();$('wardrobe-preview-status').textContent=tr("身体や衣服の表示設定が変わりました。プレビューを更新してください。");
}
function renderWardrobe(){
  allocateWardrobeSlots();$('wardrobe-editor').hidden=$('armor_support').value!=='true'||!state.source;
  $('wardrobe-add').disabled=wardrobeState.garments.size>=16;
  const target=$('wardrobe-parts');target.replaceChildren();
  if(!state.source)return;
  $('wardrobe-warning').textContent=wardrobeState.hash!==state.source.sha256?tr("保存した分類は別VRM用です。「読み込み時の自動割り当てに戻す」でこのVRMの割り当てをやり直してください。"):'';
  for(const p of state.source.parts){
    const selection=wardrobeState.nodes.get(p.node)||{role:'fixed',group:''};const row=document.createElement('div');row.className='wardrobe-part';row.dataset.node=p.node;
    const label=document.createElement('div');const name=document.createElement('strong');name.textContent=p.name;const info=document.createElement('small');info.textContent=tr("{0}三角形 · {1}", p.triangles.toLocaleString(), p.materials.join(', '));label.append(name,info);
    const role=document.createElement('select');role.setAttribute('aria-label',p.name+tr("の分類"));for(const [key,value]of Object.entries(wardrobeRoles))role.add(new Option(tr(value),key));role.value=selection.role;
    const group=document.createElement('select');group.setAttribute('aria-label',p.name+tr("の装備グループ"));for(const [id,g]of wardrobeState.garments)group.add(new Option(g.name,id));group.value=selection.group;group.disabled=selection.role!=='garment';
    role.onchange=()=>{wardrobeState.nodes.set(p.node,{role:role.value,group:role.value==='garment'?(selection.group||wardrobeState.garments.keys().next().value):''});wardrobeClearPreview();renderWardrobe();};
    group.onchange=()=>{wardrobeState.nodes.set(p.node,{role:'garment',group:group.value});wardrobeClearPreview();renderWardrobe();};row.append(label,role,group);target.append(row);
  }
  const garments=$('wardrobe-garments'),openIds=new Set([...garments.querySelectorAll('details[open]')].map(d=>d.dataset.garment));garments.replaceChildren();
  for(const [id,g]of wardrobeState.garments){
    const box=document.createElement('details');box.className='wardrobe-item';box.dataset.garment=id;box.open=openIds.has(id);
    const count=[...wardrobeState.nodes.values()].filter(p=>p.role==='garment'&&p.group===id).length;
    const title=document.createElement('summary');title.textContent=tr("{0} · {1}メッシュ{2}", g.name, count, count?'':tr("（未使用）"));box.append(title);
    const grid=document.createElement('div');grid.className='grid three';
    const fields=[['name',tr("装備名")],['item_kind',tr("部位・用途")],['slot',tr("占有する装備枠")],['armor_type',tr("防具の分類")],['armor_rating',tr("防御力")],['weight',tr("重量")],['value',tr("価値")],['equipped',tr("初期装備")]];
    if(wardrobeHeadwear(g))fields.push(['hide_hair',tr("この頭装備を着けたら髪を隠す")],['hide_face',tr("この頭装備を着けたら顔を隠す")]);
    const checkboxFields=['equipped','hide_face','hide_hair'];
    for(const [key,caption]of fields){
      const label=document.createElement('label');label.textContent=caption;let input;
      if(['slot','armor_type','item_kind'].includes(key)){input=document.createElement('select');const entries=key==='slot'?[['auto',tr("用途から自動（{0}）", wardrobeSlotLabel(g.slot))],...wardrobeSlots.map(s=>[s,wardrobeSlotLabel(s)])]:key==='item_kind'?Object.entries(wardrobeKinds).map(([key,value])=>[key,tr(value)]):[['clothing',tr("衣服（防具ではない）")],['light',tr("軽装")],['heavy',tr("重装")]];for(const [v,text]of entries)input.add(new Option(text,v));input.value=key==='slot'?(g.slot_mode==='auto'?'auto':g.slot):key==='item_kind'?wardrobeItemKind(g):g[key];}
      else {input=document.createElement('input');input.type=key==='name'?'text':checkboxFields.includes(key)?'checkbox':'number';if(checkboxFields.includes(key)){input.checked=!!g[key];label.className='checkbox';}else{input.value=g[key];if(key==='name')input.maxLength=128;else{input.min=0;input.max=key==='value'?2147483647:key==='weight'?1000:10000;input.step=key==='value'?1:.1;}}}
      input.dataset.field=key;input.setAttribute('aria-label',g.name+' '+caption);
      input.onchange=()=>{if(key==='slot'){g.slot_mode=input.value==='auto'?'auto':'manual';if(g.slot_mode==='manual')g.slot=Number(input.value);}else g[key]=checkboxFields.includes(key)?input.checked:['name','armor_type','equipment_group','item_kind'].includes(key)?input.value:Number(input.value);allocateWardrobeSlots();if(!wardrobeHeadwear(g)){g.hide_face=false;g.hide_hair=false;}wardrobeClearPreview();if(['name','item_kind','slot','equipped'].includes(key))renderWardrobe();};label.append(input);grid.append(label);
    }box.append(grid);const help=document.createElement('p');help.className='hint';help.textContent=tr("同じ装備枠を使う品は、ゲームの標準処理で入れ替わります。頭＝30、胴＝32、手袋＝33、靴＝37。同時に着るシャツ・上着・スカート・タイツは胴の一品にまとめます。追加枠を選ぶと鎧と併用されます。52＝下着、60＝顔・髪は内部予約枠です。");box.append(help);if(wardrobeHeadwear(g)){const hint=document.createElement('p');hint.className='hint';hint.textContent=tr("標準では元の顔・髪を残します。隠す場合は上の一覧で顔・髪を別メッシュとして分類してください。着脱時の切替にはSKSE64が必要です。帽子を外した状態の髪を新しく作る機能ではありません。");box.append(hint);}garments.append(box);
  }
  const preview=$('wardrobe-preview-state'), previous=preview.value;preview.replaceChildren(new Option(tr("全ての服を着る"),'all'),new Option(tr("服を外す（身体と下着）"),'underwear'));
  for(const g of wardrobeCollect().appearance_parts.garments)preview.add(new Option(tr('{0}だけ外す',g.name),'without:'+g.id));preview.value=[...preview.options].some(o=>o.value===previous)?previous:'all';
}
async function wardrobePreview(){
  const revision=wardrobeState.revision;
  error();$('wardrobe-preview').disabled=true;$('wardrobe-preview-images').replaceChildren();$('wardrobe-preview-status').textContent=tr("アバターの見た目を描画しています…");
  try{
    const result=await api('/api/appearance-preview',{source_id:state.source.source_id,blender:$('blender').value,settings:collect(),wardrobe:$('wardrobe-preview-state').value});wardrobeState.preview=result.job_id;
    for(;;){const job=await api('/api/jobs/'+result.job_id);if(job.status==='failed')throw new Error(job.error);if(job.status==='complete'){if(revision!==wardrobeState.revision){$('wardrobe-preview-status').textContent=tr("描画中に表示設定を変更しました。プレビューを更新してください。");break;}for(const path of job.previews){const figure=document.createElement('figure'),img=document.createElement('img'),caption=document.createElement('figcaption');img.src=fileURL(job.id,path);img.alt=tr("アバターの見た目");caption.textContent=tr("アバターの見た目（変換前）");figure.append(img,caption);$('wardrobe-preview-images').append(figure);}$('wardrobe-preview-status').textContent=tr("服を着た状態・外した状態の見た目を確認できます。");break;}await new Promise(resolve=>setTimeout(resolve,1000));}
  }catch(e){error(e.message);$('wardrobe-preview-status').textContent=tr("プレビューを作成できませんでした");}finally{$('wardrobe-preview').disabled=false;}
}
function initWardrobe(){
  $('armor_support').onchange=renderWardrobe;
  $('wardrobe-reset').onclick=()=>wardrobeLoad(state.source);
  $('wardrobe-add').onclick=()=>{if(wardrobeState.garments.size>=16)return;let id;do{id='item_'+(++wardrobeState.sequence);}while(wardrobeState.garments.has(id));const slot=wardrobeSlots[wardrobeState.garments.size%wardrobeSlots.length];wardrobeState.garments.set(id,garmentDefaults(id,tr('衣服{0}',wardrobeState.sequence),slot));wardrobeClearPreview();renderWardrobe();};
  $('wardrobe-combine').onclick=()=>{wardrobeState.garments.clear();const g=garmentDefaults('outfit',tr("元の全身衣装"));g.item_kind='full';wardrobeState.garments.set('outfit',g);for(const p of wardrobeState.nodes.values())if(p.role==='garment')p.group='outfit';wardrobeClearPreview();renderWardrobe();};
  $('wardrobe-split').onclick=()=>{wardrobeNativeGroups();wardrobeClearPreview();renderWardrobe();};
  $('wardrobe-preview-state').onchange=wardrobeClearPreview;$('wardrobe-preview').onclick=wardrobePreview;
}
