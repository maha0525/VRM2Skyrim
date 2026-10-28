"use strict";
const $ = id => document.getElementById(id);
const state = {step:0, source:null, choices:null, defaults:null, job:null, imported:null, pendingSelects:null, perks:new Map(), spells:new Set(), shouts:new Set(), nameDirty:false, idDirty:false};
const catalogSelects=['voice','combat_class','combat_style','weapon','ammunition'];
const skills = ["OneHanded","TwoHanded","Marksman","Block","Smithing","HeavyArmor","LightArmor","Pickpocket","Lockpicking","Sneak","Alchemy","Speechcraft","Alteration","Conjuration","Destruction","Illusion","Restoration","Enchanting"];
const skillLabels = ["片手武器","両手武器","弓術","防御","鍛冶","重装","軽装","スリ","開錠","隠密","錬金術","話術","変性","召喚","破壊","幻惑","回復","付呪"];
const integers = new Set(["level","min_level","max_level","health","magicka","stamina","confidence","aggression","morality"]);
const floats = new Set(["level_multiplier","height_scale","spawn_offset_x","spawn_offset_y","physics_stiffness","sitting_offset"]);
function error(message="") {$('error').hidden=!message; $('error').textContent=uiMessage(message);}
async function api(path, data) {
  if(path==='/api/catalog')data={...data,sex:$('sex').value};
  const response=await fetch(path, data===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
  const result=await response.json(); if(!response.ok)throw new Error(result.error||tr("通信に失敗しました")); return result;
}
function download(name, value) {const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:"application/json"})); const a=document.createElement('a'); a.href=url; a.download=name; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);}
function applySettings(settings) {
  // Only option-dependent values need to wait for the catalog. Reapplying the
  // full imported snapshot later would overwrite edits already made in STEP 01.
  state.pendingSelects=state.choices?null:Object.fromEntries(catalogSelects.map(key=>[key,settings[key]??state.defaults[key]??'']));
  $('preset').value=settings.combat_preset??'custom';
  $('toon_enabled').checked=settings.toon_enabled??state.defaults.toon_enabled;
  if(settings.physics_stiffness!==undefined&&!Array.from($('physics_stiffness').options).some(o=>o.value===String(settings.physics_stiffness)))$('physics_stiffness').add(new Option(tr("指定値 ")+settings.physics_stiffness,String(settings.physics_stiffness)));
  for(const [key,value] of Object.entries(settings)) {const input=$(key); if(!input)continue; if(input.type==='checkbox') input.checked=value; else input.value=String(value);}
  state.styleDirty=false;loadCombatStyle(settings);
  state.perks=new Map((settings.perks||[]).map(item=>[item.editor_id,item.rank])); state.spells=new Set(settings.spells||[]); state.shouts=new Set(settings.shouts||[]); normalizeShouts();
  state.fitArmors=new Set(settings.fit_armors||[]); $('fit-enabled').checked=state.fitArmors.size>0||settings.fit_mode==='all_official';
  state.headOverrides=structuredClone(settings.head_overrides||{});
  $('head-hide-face').checked=settings.head_defaults?.hide_face??false; $('head-hide-hair').checked=settings.head_defaults?.hide_hair??true; setupFitting();
  for(const key of skills) $('skill-'+key).value=settings.skills?.[key]??20;
  if(state.source)wardrobeLoad(state.source,settings);
  loadPhysics(settings);
  if(state.choices)updateStyles(settings.combat_style);
  loadWeapon(settings);
  updateLevel(); updateMarriage(); renderChoices();
}
function collect() {
  const settings={};
  for(const [key,value] of Object.entries(state.defaults)) {
    const input=$(key); if(!input)continue;
    settings[key]=input.type==='checkbox'?input.checked:integers.has(key)?Number.parseInt(input.value,10):floats.has(key)?Number(input.value):typeof value==='boolean'?input.value==='true':input.value.trim();
  }
  settings.perks=[...state.perks].map(([editor_id,rank])=>({editor_id,rank})); settings.spells=[...state.spells]; settings.shouts=[...state.shouts];
  settings.combat_preset=$('preset').value;
  settings.combat_style_custom=structuredClone(state.styleCustom||{});
  settings.skills=settings.auto_calculate?{}:Object.fromEntries(skills.map(key=>[key,Number($('skill-'+key).value)])); Object.assign(settings,wardrobeCollect());
  settings.fit_armors=settings.armor_support&&$('fit-enabled').checked?[...$('fit-armors').selectedOptions].map(o=>o.value):[];
  settings.fit_mode=settings.armor_support&&$('fit-enabled').checked?$('fit_mode').value:'selected';
  settings.head_defaults={hide_face:$('head-hide-face').checked,hide_hair:$('head-hide-hair').checked};
  settings.head_overrides=state.headOverrides||{};
  if(settings.fit_mode==='all_official')settings.fit_armors=[];
  settings.physics_nodes=[...(state.physicsNodes||[])];
  settings.physics_source_sha256=state.physicsHash||'';
  // The original weapon is chosen in STEP 03; earlier steps send it only when complete (as check_weapon).
  settings.original_weapon=originalWeaponSettings(settings.weapon_mode==='original'&&state.step>=2);
  if(settings.weapon_mode==='original'&&!Object.keys(settings.original_weapon).length)settings.weapon_mode='official';
  if(settings.armor_support&&$('fit-enabled').checked&&settings.fit_mode==='selected'&&!settings.fit_armors.length)throw new Error(tr("体型合わせする装備を選んでください")); return settings;
}
async function updateId() {
  if(state.idDirty)return;
  const name=$('mod_name').value; let id=name.replaceAll(' ','_').replace(/[^A-Za-z0-9_]/g,'').slice(0,48);
  if(!id){const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(name)); id='Avatar_'+[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('').slice(0,12);}
  else if(!/^[A-Za-z]/.test(id))id='Avatar_'+id;
  $('mod_id').value=id;
}
async function upload(file) {
  if(!file)return; error(); state.sourceLoading=true;$('next').disabled=true; $('source-status').textContent=tr("VRMを読み込んでいます…");
  try {
    const response=await fetch('/api/source',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Filename':encodeURIComponent(file.name)},body:file});
    const result=await response.json(); if(!response.ok)throw new Error(result.error);
    const previous=state.source?{armor_support:$('armor_support').value==='true',...wardrobeCollect(),physics_nodes:[...(state.physicsNodes||[])],physics_source_sha256:state.physicsHash}:state.imported;
    state.source=result;
    wardrobeLoad(result,previous);
    loadPhysics(previous||{});
    $('source-status').textContent=tr("{0} · {1}メッシュ · {2}三角形", result.filename, result.mesh_count, result.triangles.toLocaleString());
    if(!state.nameDirty&&!state.imported){$('npc_name').value=result.suggested_name; $('mod_name').value=result.suggested_name+'Follower'; await updateId();}
  }catch(e){state.source=null; error(e.message); $('source-status').textContent=tr("読み込めませんでした");}
  finally{state.sourceLoading=false;renderCatalogStatus();}
}
function loadPhysics(settings){
  const selected=settings.physics_nodes||[];
  const hash=settings.physics_source_sha256||settings.appearance_source_sha256||'';
  const mismatch=state.source&&selected.length&&hash!==state.source.sha256;
  const nodes=new Set(state.source?.parts.map(part=>part.node)||selected);
  state.physicsNodes=new Set(mismatch?[]:selected.filter(node=>nodes.has(node)));
  state.physicsHash=state.source?.sha256||hash;
  state.physicsWarning=mismatch?'保存した揺れの選択は別VRM用のため適用していません。このVRMで揺らすメッシュを選び直してください。':selected.some(node=>!nodes.has(node))?'保存した揺れの選択に、このVRMに存在しないメッシュがあります。選択を確認してください。':'';
  if(state.physicsWarning)console.warn('Physics selection restore:',{savedSource:hash,loadedSource:state.source?.sha256,selected,restored:[...state.physicsNodes]});
  renderPhysics();
}
function renderPhysics(){
  $('physics-panel').hidden=!$('physics_enabled').checked;
  $('physics-warning').hidden=!state.physicsWarning;
  $('physics-warning').textContent=state.physicsWarning?tr(state.physicsWarning):'';
  const target=$('physics-meshes');target.replaceChildren();
  for(const part of state.source?.parts||[]){
    const row=document.createElement('label');row.className='checkbox';
    const input=document.createElement('input');input.type='checkbox';input.dataset.node=part.node;
    input.checked=state.physicsNodes?.has(part.node)||false;
    input.addEventListener('change',()=>{state.physicsNodes??=new Set();if(input.checked)state.physicsNodes.add(part.node);else state.physicsNodes.delete(part.node);});
    row.append(input,document.createTextNode(part.name));target.append(row);
  }
}
$('physics_enabled').addEventListener('change',renderPhysics);
function fillSelect(id, choices, allowNone=false) {
  const selected=$(id).options.length?$(id).value:String(state.defaults[id]??''); $(id).replaceChildren();
  if(allowNone)$(id).add(new Option(tr("なし"),''));
  for(const item of choices)$(id).add(new Option(recordLabel(item)===item.id?item.id:`${recordLabel(item)} (${item.id})`,item.id));
  $(id).value=selected;
}
function setupChoices(choices, localizing=false) {
  state.choices=choices;normalizeShouts();
  for(const kind of ['perk','spell']){
    const selector=$(kind+'-category'),previous=selector.value;
    const available=new Set(choices[kind==='perk'?'perks':'spells'].flatMap(item=>item.categories||['other']));
    selector.replaceChildren(new Option(tr("すべて"),'all'),...(choices.categories||[]).filter(item=>available.has(item.id)).map(item=>new Option(recordLabel(item),item.id)));
    selector.value=[...selector.options].some(item=>item.value===previous)?previous:'all';
  }
  for(const [id,key] of [['voice','voices'],['combat_class','classes'],['combat_style','styles'],['weapon','weapons'],['ammunition','ammunition']])fillSelect(id,choices[key],['weapon','ammunition'].includes(id));
  if(state.pendingSelects){for(const [id,value] of Object.entries(state.pendingSelects))$(id).value=value;state.pendingSelects=null;}
  updateStyles();updateRoleDetails();
  updateMarriage();
  renderChoices();
  setupFitting(!localizing);
  renderCombatStyle();
  setupWeapon();
}
function catalogIdentity(){return JSON.stringify([$('game').value,$('blender').value,$('sex').value]);}
function renderCatalogStatus(){
  const busy=!!state.catalogLoading;
  $('catalog-status').hidden=!busy&&!state.catalogError;
  $('catalog-status').textContent=busy?tr('装備の一覧を読み込んでいます…'):state.catalogError?tr(state.catalogError):'';
  $('fit-panel').setAttribute('aria-busy',String(busy));
  $('fit-enabled').disabled=busy;
  $('fit-count').hidden=busy;
  $('next').disabled=busy||!!state.sourceLoading||!!state.navigationLoading;
  $('next').textContent=busy||state.sourceLoading?tr('読み込み中…'):tr('次へ →');
}
async function loadCatalog(){
  const identity=catalogIdentity();
  if(state.catalogPromise){await state.catalogPromise;return loadCatalog();}
  if(state.choices&&state.catalogIdentity===identity)return {choices:state.choices,checks:state.catalogChecks};
  state.catalogLoading=true;state.catalogError='';renderCatalogStatus();
  state.catalogPromise=api('/api/catalog',{game:$('game').value,blender:$('blender').value});
  try{
    const result=await state.catalogPromise;
    if(catalogIdentity()!==identity){state.catalogPromise=null;return await loadCatalog();}
    setupChoices(result.choices);state.catalogIdentity=identity;state.catalogChecks=result.checks;return result;
  }catch(e){state.catalogError='装備の一覧を読み込めませんでした。もう一度チェックを付けるか「次へ」で再試行してください。';throw e;}
  finally{state.catalogPromise=null;state.catalogLoading=false;renderCatalogStatus();}
}
function setupFitting(autoDefaults=true) {
  const selected=state.fitArmors||new Set(); $('fit-armors').replaceChildren();
  for(const item of state.choices?.armors||[]){const option=new Option(`${recordLabel(item)} (${item.editor_id}) · ${item.plugin}`,item.id);option.dataset.editorId=item.editor_id;option.selected=selected.has(item.id)||selected.has(item.editor_id);$('fit-armors').add(option);}
  $('fit-panel').hidden=!$('fit-enabled').checked;
  $('fit-selection').hidden=$('fit_mode').value==='all_official';
  $('fit-count').textContent=tr("{0}品", (state.choices?.armors||[]).length.toLocaleString());
  if(autoDefaults&&$('fit-enabled').checked&&!$('fit-armors').selectedOptions.length){for(const option of $('fit-armors').options)option.selected=['ArmorIronBandedCuirass','ArmorIronBoots'].includes(option.dataset.editorId);}
  renderHeadPolicies();
}
function headPreviewSignature(){return JSON.stringify([state.source?.source_id,wardrobeState.revision,$('sex').value,$('fit_source').value,$('height_scale').value]);}
function renderHeadPolicies(){
  const target=$('head-policies'),selector=$('head-model'),previous=selector.value;target.replaceChildren();
  const rows=new Map(),filter=$('head-search').value.toLowerCase();
  const selected=new Set([...$('fit-armors').selectedOptions].map(o=>o.value));
  for(const item of state.choices?.armors||[]){if($('fit_mode').value==='selected'&&!selected.has(item.id))continue;for(const addon of item.addons||[]){if(!(addon.mask&0x3803))continue;if(!rows.has(addon.key))rows.set(addon.key,{...addon,label:recordLabel(item),armor:item.id});}}
  const visible=[...rows.values()].filter(a=>!filter||`${a.label} ${a.name}`.toLowerCase().includes(filter));
  selector.replaceChildren(...visible.map(a=>new Option(`${a.label} (${a.name})`,a.key)));
  if(visible.some(a=>a.key===previous))selector.value=previous;
  $('head-count').textContent=tr("{0}モデル", visible.length);
  if(selector.value!==previous){$('head-preview-images').replaceChildren();$('head-preview-status').textContent='';}
  const addon=rows.get(selector.value);if(!addon)return;
  const row=document.createElement('div');row.dataset.addon=addon.key;row.className='head-policy-card';
  const name=document.createElement('strong');name.textContent=addon.label;const id=document.createElement('small');id.textContent=addon.name;row.append(name,id);
  const controls=document.createElement('div');controls.className='head-controls';
  const policy=state.headOverrides?.[addon.key]||{hide_face:$('head-hide-face').checked,hide_hair:$('head-hide-hair').checked&&!!(addon.mask&2)};
  for(const [key,label]of [['hide_face',tr("顔を隠す")],['hide_hair',tr("髪を隠す")]]){const box=document.createElement('label');box.className='checkbox';const input=document.createElement('input');input.type='checkbox';input.checked=policy[key];input.dataset.policy=key;input.onchange=()=>{state.headOverrides??={};state.headOverrides[addon.key]={...policy,[key]:input.checked};$('head-preview-images').replaceChildren();renderHeadPolicies();};box.append(input,document.createTextNode(label));controls.append(box);}row.append(controls);
  const reset=document.createElement('button');reset.type='button';reset.className='secondary';reset.textContent=tr("リセット");reset.onclick=()=>{delete state.headOverrides[addon.key];$('head-preview-images').replaceChildren();renderHeadPolicies();};
  const preview=document.createElement('button');preview.type='button';preview.className='secondary';preview.id='head-preview';preview.disabled=!!state.headPreviewLoading;preview.textContent=tr("この頭装備を着せてプレビュー");
  preview.onclick=async()=>{state.headPreviewLoading=true;preview.disabled=true;error();$('head-preview-images').replaceChildren();$('head-preview-status').textContent=tr("頭装備をアバターに合わせています…");const identity=addon.key+JSON.stringify(policy),signature=headPreviewSignature();try{const result=await api('/api/head-preview',{source_id:state.source.source_id,game:$('game').value,blender:$('blender').value,settings:collect(),armor:addon.armor,policy});for(;;){const job=await api('/api/jobs/'+result.job_id);$('head-preview-status').textContent=uiMessage(job.stage);if(job.status==='failed')throw new Error(job.error);if(job.status==='complete'){const current=state.headOverrides?.[addon.key]||{hide_face:$('head-hide-face').checked,hide_hair:$('head-hide-hair').checked&&!!(addon.mask&2)};if($('head-model').value+JSON.stringify(current)!==identity||headPreviewSignature()!==signature){$('head-preview-status').textContent=tr("設定が変わりました。プレビューを更新してください。");break;}for(const path of job.previews){const img=document.createElement('img');img.src=fileURL(job.id,path);img.alt=addon.label+tr("を装着したアバター");$('head-preview-images').append(img);}break;}await new Promise(r=>setTimeout(r,1000));}}catch(e){error(e.message);$('head-preview-status').textContent=tr("プレビューを作成できませんでした");}finally{state.headPreviewLoading=false;preview.disabled=false;const current=$('head-preview');if(current)current.disabled=false;}};
  row.append(reset,preview);target.append(row);
}
async function checkDeployedPatch(){
  const target=$('deployed-patch-status');
  try{
    const value=await api('/api/patch-status?job='+encodeURIComponent(state.resultJob)+'&game='+encodeURIComponent($('game').value));
    const messages={missing_follower:tr("このフォロワーのESPが未配備です。MOD ZIPを導入してDeployしてください。"),outdated_config:tr("登録設定が古い出力のものです。最新のMOD ZIPへ置き換えてDeployしてください。"),missing_runtime:tr("SkyPatcherが未導入です。対応するSKSE64とSkyPatcherを導入してください。"),unsupported_runtime:tr("このSkyPatcherには必要な機能がありません。SkyPatcherを更新してください。"),missing_config:tr("このフォロワーの登録設定が未配備です。MOD ZIPを導入してDeployしてください。"),iEnableArmorPatching:tr("SkyPatcher.iniのiEnableArmorPatchingを1にしてください。"),iEnableFormlistPatching:tr("SkyPatcher.iniのiEnableFormlistPatchingを1にしてください。"),invalid_config:tr("SkyPatcher.iniを読み取れませんでした。設定ファイルを確認してください。")};
    target.textContent=value.ready?tr("SkyPatcherと、このフォロワーの登録設定を確認しました。ゲームを再起動して反映してください。"):value.problems.map(p=>messages[p]||p).join(' ');
    target.className=value.ready?'hint':'note';
  }catch(e){target.textContent=e.message;}
}
async function showArmorPatch(job) {
  $('armor-patch-result').hidden=!job.armor_registration&&!job.armor_patch;
  $('skypatcher-install-help').hidden=job.armor_registration!=='skypatcher';
  $('check-deployed-patch').hidden=job.armor_registration!=='skypatcher';
  if(job.armor_registration==='skypatcher')await checkDeployedPatch();
  else if(job.armor_patch)$('deployed-patch-status').textContent=tr("これは旧式パッチを使う変換結果です。SkyPatcher方式へ移行するには、このフォロワーを再出力してください。");
}
function selectedTags(kind) {
  const selected=kind==='perks'?state.perks.keys():state.spells; const target=$('selected-'+kind); target.replaceChildren();
  for(const id of selected){const item=state.choices?.[kind].find(item=>item.id===id);const button=document.createElement('button'); button.type='button';button.textContent=(recordLabel(item)||id)+(item?.stage?`（${item.stage.index}/${item.stage.total}）`:'')+' ×';button.onclick=()=>{if(kind==='perks')state.perks.delete(id);else state.spells.delete(id);renderChoices();};target.append(button);}
}
function renderChoiceList(kind, term) {
  if(!state.choices)return; const target=$(kind);target.replaceChildren(); const q=term.toLowerCase();
  const prefix=kind==='perks'?'perk':'spell',category=$(prefix+'-category').value;
  const visible=state.choices[kind].filter(item=>(category==='all'||(item.categories||['other']).includes(category))&&(item.id+' '+recordLabel(item)+' '+recordDescription(item)).toLowerCase().includes(q)&&!(kind==='perks'&&item.ranks===0));
  $(prefix+'-visible').textContent=(visible.length===1?tr('1件'):visible.length+tr("件"))+(visible.length?'':tr("。カテゴリや検索条件を変更してください。"));
  for(const item of visible) {
    if(kind==='perks'&&item.ranks===0)continue;
    const label=document.createElement('label');label.className='choice'; const check=document.createElement('input');check.type='checkbox';check.dataset.recordId=item.id;check.checked=kind==='perks'?state.perks.has(item.id):state.spells.has(item.id);
    const title=document.createElement('strong');title.textContent=recordLabel(item)+(item.stage?tr("（段階 {0}/{1}）", item.stage.index, item.stage.total):'');label.append(check,title);
    const desc=document.createElement('small');desc.textContent=item.id+(recordDescription(item)?' · '+recordDescription(item):'');label.append(desc);
    check.onchange=()=>{if(kind==='perks'){if(check.checked)state.perks.set(item.id,0);else state.perks.delete(item.id);}else{if(check.checked)state.spells.add(item.id);else state.spells.delete(item.id);}renderChoices();};
    if(kind==='perks'&&check.checked&&(item.effect_ranks||[0]).length>1){const caption=document.createElement('span');caption.textContent=tr("効果ランク");const rank=document.createElement('select');for(const value of item.effect_ranks)rank.add(new Option(String(value+1),String(value)));rank.value=String(state.perks.get(item.id));rank.setAttribute('aria-label',recordLabel(item)+tr("の効果ランク"));rank.onchange=()=>state.perks.set(item.id,Number(rank.value));label.append(caption,rank);}
    target.append(label);
  }
}
function renderChoices(){renderChoiceList('perks',$('perk-search').value);renderChoiceList('spells',$('spell-search').value);$('perk-count').textContent=state.perks.size;$('spell-count').textContent=state.spells.size;selectedTags('perks');selectedTags('spells');renderShouts();}
function shoutKey(id){
  // settings.py and the server compare shout keys case-insensitively; the wizard keeps the catalog's spelling.
  const known=[...(state.choices?.shouts||[]),...(state.choices?.unavailable_shouts||[])],folded=String(id).toLowerCase();
  return known.find(item=>item.id.toLowerCase()===folded)?.id??id;
}
function normalizeShouts(){state.shouts=new Set([...state.shouts].map(shoutKey));}
function shoutName(id){
  const item=state.choices?.shouts?.find(item=>item.id===id);
  return item?recordLabel(item):state.choices?.unavailable_shouts?.find(item=>item.id===id)?.editor_id??id;
}
function shoutScore(){
  // The custom style's edited value wins; otherwise the selected official style's value.
  // Missing, empty or non-numeric values read as null (shown as "no value").
  const number=value=>{const result=typeof value==='number'?value:typeof value==='string'&&value.trim()?Number(value):NaN;return Number.isFinite(result)?result:null;};
  if($('combat_style_mode').value==='custom')return {custom:true,value:number(state.styleCustom?.values?.shout_score)};
  const id=$('combat_style').value,styles=state.choices?.styles||[];
  const style=styles.find(item=>item.id===id)||styles.find(item=>String(item.id).toLowerCase()===id.toLowerCase());
  return {custom:false,id:style?.id??id,value:number(style?.config?.values?.shout_score)};
}
function renderShouts(){
  const list=$('shouts');list.replaceChildren();
  // Selected shouts the catalog cannot offer (DLC not installed, or an unknown key from a settings file)
  // stay visible here so they can be removed; conversion refuses them.
  const offered=new Set((state.choices?.shouts||[]).map(item=>item.id));
  if(state.choices)for(const id of state.shouts){
    if(offered.has(id))continue;
    const missing=(state.choices.unavailable_shouts||[]).find(item=>item.id===id);
    const row=document.createElement('div');row.className='choice unavailable';row.dataset.shoutKey=id;
    const title=document.createElement('strong');title.textContent=missing?missing.editor_id:id;row.append(title);
    if(missing?.dlc){const dlc=document.createElement('span');dlc.className='dlc';dlc.dataset.dlc=missing.dlc;dlc.textContent=tr('{0} が必要',missing.dlc);row.append(dlc);}
    const desc=document.createElement('small');
    desc.textContent=missing?id+' · '+tr('{0} がインストールされていないので、このシャウトは使えません。外してください。',missing.requires):tr('このシャウトは選べません: {0}',id)+' '+tr('外してください。');
    const remove=document.createElement('button');remove.type='button';remove.textContent=tr('外す');remove.onclick=()=>{state.shouts.delete(id);renderShouts();};
    row.append(desc,remove);list.append(row);
  }
  for(const item of state.choices?.shouts||[]){
    const label=document.createElement('label');label.className='choice';
    const check=document.createElement('input');check.type='checkbox';check.dataset.recordId=item.id;check.checked=state.shouts.has(item.id);
    const title=document.createElement('strong');title.textContent=recordLabel(item);label.append(check,title);
    if(item.dlc){const dlc=document.createElement('span');dlc.className='dlc';dlc.dataset.dlc=item.dlc;dlc.textContent=tr('{0} が必要',item.dlc);label.append(dlc);}
    const desc=document.createElement('small');desc.textContent=item.editor_id+(recordDescription(item)?' · '+recordDescription(item):'');label.append(desc);
    check.onchange=()=>{if(check.checked)state.shouts.add(item.id);else state.shouts.delete(item.id);renderShouts();};
    list.append(label);
  }
  $('shout-count').textContent=state.shouts.size;
  const tags=$('selected-shouts');tags.replaceChildren();
  for(const id of state.shouts){const button=document.createElement('button');button.type='button';button.textContent=shoutName(id)+' ×';button.onclick=()=>{state.shouts.delete(id);renderShouts();};tags.append(button);}
  const score=shoutScore(),known=score.value!==null,shown=state.shouts.size>0;
  $('shout-score').hidden=!shown;$('shout-score-warning').hidden=!shown||score.value!==0;
  const value=known?String(Number(score.value.toFixed(4))):'';
  $('shout-score').textContent=!known?tr('戦闘スタイルにシャウトの優先度の値がありません。ゲーム既定の値を使います。'):score.custom?tr('専用の戦闘スタイルのシャウトの優先度: {0}',value):tr('戦闘スタイル {0} のシャウトの優先度: {1}',score.id,value);
  $('shout-score-warning').textContent=tr('シャウトの優先度が 0 なので、この戦闘スタイルではシャウトを使いません。STEP 03 で別の戦闘スタイルを選ぶか、専用の戦闘スタイルで「シャウトの優先度」を上げてください。');
}
function updateStyles(selected=$('combat_style').value) {
  if(!state.choices)return;
  const items=state.choices.styles;
  if(items.some(item=>item.id===selected&&!item.humanoid))$('all-styles').checked=true;
  fillSelect('combat_style',items.filter(item=>$('all-styles').checked||item.humanoid));
  if([...$('combat_style').options].some(option=>option.value===selected))$('combat_style').value=selected;
  if(!$('combat_style').value)$('combat_style').value=state.defaults.combat_style;
  updateRoleDetails();
}
function updateRoleDetails() {
  const growth=state.choices?.classes.find(item=>item.id===$('combat_class').value)?.growth;
  const target=$('class-details');target.replaceChildren();
  if(growth){
    const entries=Object.entries(growth.skills).filter(([,weight])=>weight>0).sort((a,b)=>b[1]-a[1]);
    const skillText=entries.map(([key,weight])=>`${tr(skillLabels[skills.indexOf(key)])} ${weight}`).join(' ／ ');
    for(const text of [tr("得意スキルの成長配分：{0}", skillText||tr("配分なし")),tr("体力 {0}：マジカ {1}：スタミナ {2}", growth.attributes.health, growth.attributes.magicka, growth.attributes.stamina), tr("数字は自動成長の配分比率です。")]){const p=document.createElement('p');p.textContent=text;target.append(p);}
  }else target.textContent=tr("このクラスの成長配分を読み取れませんでした。");
  const style=state.choices?.styles.find(item=>item.id===$('combat_style').value);
  $('style-details').textContent=style?tr("{0}。使用種族：{1}。", style.humanoid?tr("人型NPCでの使用例あり"):tr("人型NPCでの使用例を確認できないスタイル"), (style.used_by_localized?.[i18n.language]||style.used_by)?.join(i18n.language==='en'?', ':'、')||tr("確認できず")):'';
}
function updateLevel() {
  const manual=$('auto_calculate').value==='false';
  $('fixed-level').hidden=$('level_mode').value!=='fixed';$('mult-level').hidden=$('level_mode').value!=='player';
  $('skill-inputs').hidden=!manual;$('use-manual-skills').hidden=manual;
  for(const key of skills)$('skill-'+key).disabled=!manual;
  $('skills-hint').textContent=manual?tr("18スキルを0〜100で指定します。レベル追従を選んでも、スキルはこの指定値を使います。"):tr("自動計算では、クラスとNPCのレベルからゲームがスキル値を決めます。数値を指定したい場合は手動設定へ切り替えてください。");
  $('stat-hint').textContent=manual?tr("体力・マジカ・スタミナも指定値を使います。"):tr("成長前の基礎値を指定します。クラスとNPCのレベルに応じた成長分が加わります。");
  for(const [key,label] of [['health',tr("体力")],['magicka',tr("マジカ")],['stamina',tr("スタミナ")]])$(key).parentElement.firstChild.textContent=(manual?'':tr("基礎"))+label;
  updateRoleDetails();
}
function updateMarriage(){if(!state.choices)return;const supported=state.choices.marriage_voices.includes($('voice').value);$('marriage').disabled=!supported;if(!supported)$('marriage').checked=false;}
function showStep(step) {
  state.step=step;error(); document.querySelectorAll('[data-step]').forEach(section=>section.hidden=Number(section.dataset.step)!==step);
  [...$('steps').children].forEach((li,index)=>{li.classList.toggle('active',index===step);li.classList.toggle('done',index<step);});
  $('back').hidden=step===0;$('next').hidden=step===4;$('create').hidden=step!==4;window.scrollTo(0,0);
  if(step===2)markWeaponPreviewStale();  // appearance inputs of STEP 01/02 are part of the preview
  if(step===3)renderShouts();  // the shout priority follows the STEP 03 combat style
}
function summarize(settings) {
  state.reviewSettings=settings;
  const voice=state.choices.voices.find(item=>item.id===settings.voice);
  const rows=[[tr("アバター"),state.source.filename],[tr("NPC名"),settings.npc_name],['MOD',settings.mod_name+' / '+settings.mod_id+'.esp'],[tr("ボイス"),recordLabel(voice)||settings.voice],[tr("戦闘"),settings.combat_class+' / '+settings.combat_style],[tr("レベル"),settings.level_mode==='player'?tr("プレイヤー×{0}（{1}〜{2}）", settings.level_multiplier, settings.min_level, settings.max_level):String(settings.level)],[tr("生存"),{'protected':tr("保護"),'essential':tr("不死"),'mortal':tr("通常")}[settings.protection]],[tr("体力 / マジカ / スタミナ"),`${settings.health} / ${settings.magicka} / ${settings.stamina}${settings.auto_calculate?tr("（自動成長の補正に使用）"):''}`],[tr("Perk / 魔法"),`${settings.perks.length} / ${settings.spells.length}`],[tr("初期配置"),tr("ホワイトラン · キナレス聖堂")]];
  rows.push([tr("衣服"),settings.armor_support?tr("{0}品を着脱可能（初期装備{1}品）", settings.appearance_parts.garments.length, settings.appearance_parts.garments.filter(g=>g.equipped).length):tr("元の衣服を着脱しない")]);
  rows.push([tr("シャウト"),settings.shouts.length?settings.shouts.map(shoutName).join(i18n.language==='en'?', ':'、'):tr("なし")]);
  rows.push([tr("トゥーン描画"),settings.toon_enabled?tr("有効"):tr("無効")]);
  rows.push([tr("開始武器"),weaponSummary(settings)]);
  if(settings.combat_style_mode==='custom')rows.push([tr('専用戦闘スタイル'),tr('コピー元: {0}',settings.combat_style_custom.source)]);
  rows.push([tr("髪・布の物理演算"),settings.physics_enabled?tr("FSMPを使用 · 硬さ{0} · {1}", settings.physics_stiffness, settings.physics_nodes.length?settings.physics_nodes.length+tr("メッシュを選択"):tr("髪・衣服を自動選択")):tr("固定")]);
  const fitting=settings.armor_support&&(settings.fit_mode==='all_official'||settings.fit_armors.length>0);
  rows.push([tr("既存装備の体型合わせ"),!fitting?tr("なし"):settings.fit_mode==='all_official'?tr("公式装備すべて"):tr("選択した公式装備（{0}品）",settings.fit_armors.length)]);
  if(fitting)rows.push([tr("元にする装備の見た目"),settings.fit_source==='installed'?tr("置き換えた見た目"):tr("標準の見た目")]);
  const dl=document.createElement('dl');for(const [title,value]of rows){const dt=document.createElement('dt');dt.textContent=title;const dd=document.createElement('dd');dd.textContent=value;dl.append(dt,dd);}$('summary').replaceChildren(dl);
}
async function next() {
  error(); const current=document.querySelector(`[data-step="${state.step}"]`);
  for(const field of current.querySelectorAll('input,select'))if(!field.closest('[hidden]')&&!field.checkValidity()){field.reportValidity();return;}
  state.navigationLoading=true;$('next').disabled=true;
  try {
    if(state.step===0){if(!state.source)throw new Error(tr("VRMファイルを選択してください"));const result=await loadCatalog();$('checks').replaceChildren();for(const [key,value]of Object.entries(result.checks)){const badge=document.createElement('span');badge.textContent=key+(value?' ✓':tr(" 未準備"));badge.className=value?'':'missing';$('checks').append(badge);}if(Object.values(result.checks).some(value=>!value))throw new Error(tr("環境が未準備です。パスを確認し、初回はSetup.cmdを実行してください。"));}
    const result=await api('/api/validate',{source_id:state.source.source_id,game:$('game').value,settings:collect(),weapon_id:state.weaponGlb?.weapon_id,check_weapon:state.step>=2,check_shouts:state.step>=3});if(state.step===3)summarize(result.settings);
    showStep(state.step+1);
  }catch(e){error(e.message);}finally{state.navigationLoading=false;renderCatalogStatus();}
}
function fileURL(job,name){return `/api/jobs/${job}/file?name=${encodeURIComponent(name)}`;}
function showResult(job) {
  state.completedJob=job;
  state.resultJob=job.id;$('equipment-edit').hidden=!job.edit_kit||!!job.armor_patch;
  if(job.edit_kit){$('edit-kit-download').href=fileURL(job.id,job.edit_kit);$('edit-mesh').replaceChildren(...job.edit_meshes.map(i=>new Option(i.name,i.key)));}
  showArmorPatch(job).catch(e=>error(e.message));
  renderResultAppearance(job);
}
function renderResultAppearance(job) {
  $('progress').hidden=true;$('result').hidden=false;$('result-title').textContent=tr('{0}を、スカイリムへ。',job.npc_name);$('download').href=fileURL(job.id,job.archive);$('download').download=job.archive;$('plugin-name').textContent=job.plugin_name;$('output-folder').textContent=tr("出力フォルダ: ")+job.output;
  const original=job.weapon_mode==='original';
  const names=['original-01.png','rest-01.png','walk-08.png','attack-10.png','attack-hand-10.png','sheathed-01.png']; const labels=[tr("元VRM（姿勢合わせ）"),tr("出力NIF"),tr("標準歩行"),original?tr("オリジナル武器で攻撃"):tr("標準の剣攻撃"),original?tr("手とオリジナル武器の近接確認"):tr("手と剣の近接確認"),tr("武器を収めた姿")];$('previews').replaceChildren();
  for(let i=0;i<names.length;i++){const path=job.previews.find(path=>path.endsWith('/'+names[i]));if(!path)continue;const figure=document.createElement('figure');const image=document.createElement('img');image.src=fileURL(job.id,path);image.alt=labels[i];const caption=document.createElement('figcaption');caption.textContent=labels[i];figure.append(image,caption);$('previews').append(figure);}
  if(job.armor_support){const extra=[['wardrobe-underwear-rest-01.png',tr("服を外した状態")],['wardrobe-underwear-walk-08.png',tr("下着状態で歩行")],['wardrobe-underwear-attack-10.png',tr("下着状態で剣攻撃")],...(job.garments||[]).map(g=>['wardrobe-without-'+g.id+'-rest-01.png',tr('{0}だけ外した状態',g.name)])];for(const [name,label]of extra){const path=job.previews.find(p=>p.endsWith('/'+name));if(!path)continue;const figure=document.createElement('figure'),img=document.createElement('img'),caption=document.createElement('figcaption');img.src=fileURL(job.id,path);img.alt=label;caption.textContent=label;figure.append(img,caption);$('previews').append(figure);}}
  if(job.fit_armors?.length){for(const [name,label] of [['wardrobe-armor-all-rest-01.png',tr("体型を合わせた装備")],['wardrobe-armor-all-walk-08.png',tr("装備して歩行")],['wardrobe-armor-all-attack-10.png',tr("装備して剣攻撃")]]){const path=job.previews.find(p=>p.endsWith('/'+name));if(!path)continue;const figure=document.createElement('figure'),img=document.createElement('img'),caption=document.createElement('figcaption');img.src=fileURL(job.id,path);img.alt=label;caption.textContent=label;figure.append(img,caption);$('previews').append(figure);}}
}
async function poll() {
  try {const job=await api('/api/jobs/'+state.job);$('stage').textContent=uiMessage(job.stage);$('events').replaceChildren(...job.events.map(text=>{const li=document.createElement('li');li.textContent=uiMessage(text);return li;}));
    if(job.status==='complete'){showResult(job);return;}
    if(job.status==='failed'){$('failure').hidden=false;$('failure').textContent=uiMessage(job.error);$('wizard').hidden=false;$('progress').querySelector('.progress-bar').hidden=true;return;}
    setTimeout(poll,1000);
  }catch(e){error(e.message);$('wizard').hidden=false;}
}
async function create() {
  error();$('create').disabled=true;
  try {const result=await api('/api/jobs',{source_id:state.source.source_id,game:$('game').value,blender:$('blender').value,settings:collect(),weapon_id:state.weaponGlb?.weapon_id});state.job=result.job_id;$('wizard').hidden=true;$('progress').hidden=false;$('failure').hidden=true;$('progress').querySelector('.progress-bar').hidden=false;poll();}
  catch(e){error(e.message);}finally{$('create').disabled=false;}
}
function preset() {
  const presets={warrior:{combat_class:'CombatWarrior1H',combat_style:'csHumanMeleeLvl1',weapon:'SteelSword',ammunition:'',spells:[]},twohand:{combat_class:'CombatWarrior2H',combat_style:'csHumanBoss2H',weapon:'SteelGreatsword',ammunition:'',spells:[]},archer:{combat_class:'CombatRanger',combat_style:'csHumanMissile',weapon:'HuntingBow',ammunition:'IronArrow',spells:[]},mage:{combat_class:'CombatMageDestruction',combat_style:'csHumanMagic',weapon:'',ammunition:'',spells:['Firebolt','FastHealing']},conjurer:{combat_class:'CombatMageConjurer',combat_style:'csHumanMagic',weapon:'',ammunition:'',spells:['ConjureFlameAtronach','FastHealing']}};
  const chosen=presets[$('preset').value];if(!chosen)return;for(const key of ['combat_class','combat_style','weapon','ammunition'])$(key).value=chosen[key];state.spells=new Set(chosen.spells.filter(id=>state.choices.spells.some(item=>item.id===id)));renderChoices();
  const caster=['mage','conjurer'].includes($('preset').value);$('health').value=caster?150:200;$('magicka').value=caster?200:100;$('stamina').value=caster?100:150;updateStyles(chosen.combat_style);updateRoleDetails();
}
async function refreshSavedResults(preferred=$('saved-job').value) {
  $('saved-job').disabled=true;$('open-saved').disabled=true;
  let saved;try{saved=await api('/api/jobs');}finally{$('saved-job').disabled=false;$('open-saved').disabled=false;}
  $('saved-job').replaceChildren(...saved.jobs.map(job=>new Option(job.npc_name+' · '+job.plugin_name,job.id)));
  if(saved.jobs.some(job=>job.id===preferred))$('saved-job').value=preferred;
  $('saved-results').hidden=saved.jobs.length===0;
}
async function init() {
  initCombatStyle();initWeapon();
  for(let i=0;i<skills.length;i++){const label=document.createElement('label');label.textContent=tr(skillLabels[i]);const input=document.createElement('input');input.id='skill-'+skills[i];input.type='number';input.min='0';input.max='100';input.value='20';label.append(input);$('skills').append(label);}
  const env=await api('/api/environment');
  const expected=document.querySelector('meta[name="converter-version"]').content;
  if(env.restart_required||(/^\d+\.\d+\./.test(env.version)&&env.version!==expected)){
    $('next').disabled=true;$('create').disabled=true;$('source').disabled=true;
    throw new Error(tr("ウィザードの再起動が必要です（起動中 {0}／画面 {1}）。古いウィザードのターミナルで Ctrl+C を押し、Launch.cmd を開き直してください。新しく開いたページを使ってください（ポート番号が変わることがあります）。設定JSONを保存済みなら再起動後に読み込めます。", env.version, expected));
  }
  state.defaults={...env.defaults,fit_mode:'all_official'};$('version').textContent='VRM2Skyrim '+env.version;$('game').value=env.game;$('blender').value=env.blender;applySettings(env.defaults);$('fit_mode').value='all_official';
  $('legacy-armor-notice').hidden=!env.armor_registration?.legacy_patch;
  initWardrobe();
  await refreshSavedResults();
  $('check-deployed-patch').onclick=checkDeployedPatch;
  $('open-saved').onclick=async()=>{try{const job=await api('/api/jobs/'+$('saved-job').value);$('wizard').hidden=true;showResult(job);}catch(e){error(e.message);}};
  $('fit-enabled').onchange=async()=>{error();setupFitting();if($('fit-enabled').checked){try{await loadCatalog();}catch(e){error(e.message);$('fit-enabled').checked=false;setupFitting();}}};
  $('fit-armors').onchange=()=>{state.fitArmors=new Set([...$('fit-armors').selectedOptions].map(o=>o.value));renderHeadPolicies();};
  $('head-model').onchange=()=>{$('head-preview-images').replaceChildren();renderHeadPolicies();};$('fit_mode').onchange=setupFitting;$('head-search').oninput=renderHeadPolicies;
  $('head-hide-face').onchange=$('head-hide-hair').onchange=()=>{$('head-preview-images').replaceChildren();$('head-preview-status').textContent='';renderHeadPolicies();};$('fit_source').onchange=()=>{$('head-preview-images').replaceChildren();$('head-preview-status').textContent='';};
  $('import-edit').onclick=async()=>{const file=$('edit-nif').files[0];if(!file){$('edit-status').textContent=tr("編集したNIFを選んでください");return;}$('import-edit').disabled=true;try{const response=await fetch('/api/equipment-edit',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Job-Id':state.resultJob,'X-Mesh-Key':$('edit-mesh').value,'X-Blender':encodeURIComponent($('blender').value)},body:file});const result=await response.json();if(!response.ok)throw new Error(result.error);for(;;){const job=await api('/api/jobs/'+result.job_id);$('edit-status').textContent=uiMessage(job.stage);if(job.status==='failed')throw new Error(job.error);if(job.status==='complete'){showResult(job);$('edit-status').textContent=tr("仕上げを反映しました。更新されたMOD ZIPを保存してください。");break;}await new Promise(r=>setTimeout(r,1000));}}catch(e){$('edit-status').textContent=e.message;}finally{$('import-edit').disabled=false;}};
  $('source').onchange=()=>upload($('source').files[0]);const zone=document.querySelector('.dropzone');zone.ondragover=e=>{e.preventDefault();zone.classList.add('drag');};zone.ondragleave=()=>zone.classList.remove('drag');zone.ondrop=e=>{e.preventDefault();zone.classList.remove('drag');upload(e.dataTransfer.files[0]);};
  $('next').onclick=next;$('back').onclick=()=>showStep(state.step-1);$('create').onclick=create;$('level_mode').onchange=updateLevel;$('auto_calculate').onchange=updateLevel;$('preset').onchange=preset;
  $('combat_class').onchange=updateRoleDetails;$('combat_style').onchange=updateRoleDetails;
  $('all-styles').onchange=()=>{const selected=$('combat_style').value;const item=state.choices.styles.find(item=>item.id===selected);updateStyles(!$('all-styles').checked&&!item?.humanoid?state.defaults.combat_style:selected);};
  $('use-manual-skills').onclick=()=>{$('auto_calculate').value='false';$('manual-skills').open=true;updateLevel();};
  $('mod_name').oninput=()=>{state.nameDirty=true;updateId();};$('npc_name').oninput=()=>state.nameDirty=true;$('mod_id').oninput=()=>state.idDirty=true;
  $('sex').onchange=async()=>{const sex=$('sex').value;$('voice').value=sex==='male'?'MaleNord':'FemaleEvenToned';updateMarriage();if(state.choices){try{state.fitArmors=new Set([...$('fit-armors').selectedOptions].map(o=>o.value));await loadCatalog();}catch(e){error(e.message);}}};$('voice').onchange=updateMarriage;
  $('perk-search').oninput=renderChoices;$('spell-search').oninput=renderChoices;
  $('perk-category').onchange=renderChoices;$('spell-category').onchange=renderChoices;
  $('export-settings').onclick=()=>download($('mod_id').value+'-settings.json',collect());
  $('import-settings').onchange=async()=>{try{state.imported=JSON.parse(await $('import-settings').files[0].text());applySettings(state.imported);state.nameDirty=true;state.idDirty=true;$('import-status').textContent=tr("設定を読み込みました");}catch(e){error(e.message);}};
  $('again').onclick=async()=>{state.completedJob=null;$('result').hidden=true;$('equipment-edit').hidden=true;$('wizard').hidden=false;state.source=null;state.imported=null;state.pendingSelects=null;loadPhysics({});state.nameDirty=false;state.idDirty=false;$('source').value='';$('source-status').textContent=tr("次のVRMを選択してください");wardrobeLoad(null);showStep(0);try{await refreshSavedResults(state.resultJob);}catch(e){error(tr("前に作ったフォロワーの一覧を更新できませんでした：")+e.message);}};
}
document.addEventListener('languagechange',()=>{
  for(const option of $('physics_stiffness').options)if(!['0.3','1','3'].includes(option.value))option.textContent=tr('指定値 ')+option.value;
  for(let i=0;i<skills.length;i++)$('skill-'+skills[i]).parentElement.firstChild.textContent=tr(skillLabels[i]);
  if(!state.defaults)return;
  if(state.choices){
    state.fitArmors=new Set([...$('fit-armors').selectedOptions].map(option=>option.value));
    setupChoices(state.choices,true);
  }
  renderWardrobe();renderPhysics();updateLevel();renderCatalogStatus();
  renderWeaponGlb();renderWeaponBaseStatus();if(state.weaponPreview&&!state.weaponPreviewLoading)renderWeaponPreview();
  if(state.source)$('source-status').textContent=tr('{0} · {1}メッシュ · {2}三角形',state.source.filename,state.source.mesh_count,state.source.triangles.toLocaleString(i18n.language));
  if(state.step===4&&state.reviewSettings)summarize(state.reviewSettings);
  if(state.completedJob&&!$('result').hidden)renderResultAppearance(state.completedJob);
});
init().catch(e=>error(e.message));
