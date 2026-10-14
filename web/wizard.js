"use strict";
const $ = id => document.getElementById(id);
const state = {step:0, source:null, choices:null, defaults:null, job:null, imported:null, importPending:false, perks:new Map(), spells:new Set(), nameDirty:false, idDirty:false};
const skills = ["OneHanded","TwoHanded","Marksman","Block","Smithing","HeavyArmor","LightArmor","Pickpocket","Lockpicking","Sneak","Alchemy","Speechcraft","Alteration","Conjuration","Destruction","Illusion","Restoration","Enchanting"];
const skillLabels = ["片手武器","両手武器","弓術","防御","鍛冶","重装","軽装","スリ","開錠","隠密","錬金術","話術","変性","召喚","破壊","幻惑","回復","付呪"];
const integers = new Set(["level","min_level","max_level","health","magicka","stamina","confidence","aggression","morality"]);
const floats = new Set(["level_multiplier","height_scale","spawn_offset_x","spawn_offset_y","physics_stiffness","sitting_offset"]);
function error(message="") {$('error').hidden=!message; $('error').textContent=message;}
async function api(path, data) {
  if(path==='/api/catalog')data={...data,sex:$('sex').value};
  const response=await fetch(path, data===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
  const result=await response.json(); if(!response.ok)throw new Error(result.error||"通信に失敗しました"); return result;
}
function download(name, value) {const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:"application/json"})); const a=document.createElement('a'); a.href=url; a.download=name; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);}
function applySettings(settings) {
  if(settings.physics_stiffness!==undefined&&!Array.from($('physics_stiffness').options).some(o=>o.value===String(settings.physics_stiffness)))$('physics_stiffness').add(new Option('指定値 '+settings.physics_stiffness,String(settings.physics_stiffness)));
  for(const [key,value] of Object.entries(settings)) {const input=$(key); if(!input)continue; if(input.type==='checkbox') input.checked=value; else input.value=String(value);}
  state.perks=new Map((settings.perks||[]).map(item=>[item.editor_id,item.rank])); state.spells=new Set(settings.spells||[]);
  state.fitArmors=new Set(settings.fit_armors||[]); $('fit-enabled').checked=state.fitArmors.size>0||settings.fit_mode==='all_official';
  state.headOverrides=structuredClone(settings.head_overrides||{});
  $('head-hide-face').checked=settings.head_defaults?.hide_face??false; $('head-hide-hair').checked=settings.head_defaults?.hide_hair??true; setupFitting();
  for(const key of skills) $('skill-'+key).value=settings.skills?.[key]??20;
  if(state.source)wardrobeLoad(state.source,settings);
  state.physicsNodes=new Set(!state.source||settings.appearance_source_sha256===state.source.sha256?settings.physics_nodes||[]:[]); renderPhysics();
  if(state.choices)updateStyles(settings.combat_style);
  updateLevel(); updateMarriage(); renderChoices();
}
function collect() {
  const settings={};
  for(const [key,value] of Object.entries(state.defaults)) {
    const input=$(key); if(!input)continue;
    settings[key]=input.type==='checkbox'?input.checked:integers.has(key)?Number.parseInt(input.value,10):floats.has(key)?Number(input.value):typeof value==='boolean'?input.value==='true':input.value.trim();
  }
  settings.perks=[...state.perks].map(([editor_id,rank])=>({editor_id,rank})); settings.spells=[...state.spells];
  settings.skills=settings.auto_calculate?{}:Object.fromEntries(skills.map(key=>[key,Number($('skill-'+key).value)])); Object.assign(settings,wardrobeCollect());
  settings.fit_armors=settings.armor_support&&$('fit-enabled').checked?[...$('fit-armors').selectedOptions].map(o=>o.value):[];
  settings.fit_mode=settings.armor_support&&$('fit-enabled').checked?$('fit_mode').value:'selected';
  settings.head_defaults={hide_face:$('head-hide-face').checked,hide_hair:$('head-hide-hair').checked};
  settings.head_overrides=state.headOverrides||{};
  if(settings.fit_mode==='all_official')settings.fit_armors=[];
  settings.physics_nodes=[...(state.physicsNodes||[])];
  if(settings.armor_support&&$('fit-enabled').checked&&settings.fit_mode==='selected'&&!settings.fit_armors.length)throw new Error('体型合わせする装備を選んでください'); return settings;
}
async function updateId() {
  if(state.idDirty)return;
  const name=$('mod_name').value; let id=name.replaceAll(' ','_').replace(/[^A-Za-z0-9_]/g,'').slice(0,48);
  if(!id){const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(name)); id='Avatar_'+[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('').slice(0,12);}
  else if(!/^[A-Za-z]/.test(id))id='Avatar_'+id;
  $('mod_id').value=id;
}
async function upload(file) {
  if(!file)return; error(); $('next').disabled=true; $('source-status').textContent='VRMを読み込んでいます…';
  try {
    const response=await fetch('/api/source',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Filename':encodeURIComponent(file.name)},body:file});
    const result=await response.json(); if(!response.ok)throw new Error(result.error); state.source=result;
    wardrobeLoad(result,state.imported);
    state.physicsNodes=new Set(state.imported?.appearance_source_sha256===result.sha256?state.imported.physics_nodes||[]:[]); renderPhysics();
    $('source-status').textContent=`${result.filename} · ${result.mesh_count}メッシュ · ${result.triangles.toLocaleString()}三角形`;
    if(!state.nameDirty&&!state.imported){$('npc_name').value=result.suggested_name; $('mod_name').value=result.suggested_name+'Follower'; await updateId();}
  }catch(e){state.source=null; error(e.message); $('source-status').textContent='読み込めませんでした';}
  finally{$('next').disabled=false;}
}
function renderPhysics(){
  $('physics-panel').hidden=!$('physics_enabled').checked;
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
  const selected=$(id).value||String(state.defaults[id]??''); $(id).replaceChildren();
  if(allowNone)$(id).add(new Option('なし',''));
  for(const item of choices)$(id).add(new Option(item.label===item.id?item.id:`${item.label} (${item.id})`,item.id));
  $(id).value=selected;
}
function setupChoices(choices) {
  state.choices=choices;
  for(const [id,key] of [['voice','voices'],['combat_class','classes'],['combat_style','styles'],['weapon','weapons'],['ammunition','ammunition']])fillSelect(id,choices[key],['weapon','ammunition'].includes(id));
  if(state.imported&&state.importPending){applySettings(state.imported);state.importPending=false;}
  updateStyles();updateRoleDetails();
  updateMarriage();
  renderChoices();
  setupFitting();
}
function setupFitting() {
  const selected=state.fitArmors||new Set(); $('fit-armors').replaceChildren();
  for(const item of state.choices?.armors||[]){const option=new Option(`${item.label} (${item.editor_id}) · ${item.plugin}`,item.id);option.dataset.editorId=item.editor_id;option.selected=selected.has(item.id)||selected.has(item.editor_id);$('fit-armors').add(option);}
  $('fit-panel').hidden=!$('fit-enabled').checked;
  $('fit-selection').hidden=$('fit_mode').value==='all_official';
  $('fit-count').textContent=`${(state.choices?.armors||[]).length.toLocaleString()}品 · ${(state.choices?.equipment_plugins||[]).join(' / ')}`;
  if($('fit-enabled').checked&&!$('fit-armors').selectedOptions.length){for(const option of $('fit-armors').options)option.selected=['ArmorIronBandedCuirass','ArmorIronBoots'].includes(option.dataset.editorId);}
  renderHeadPolicies();
}
function headPreviewSignature(){return JSON.stringify([state.source?.source_id,wardrobeState.revision,$('sex').value,$('fit_source').value,$('height_scale').value]);}
function renderHeadPolicies(){
  const target=$('head-policies'),selector=$('head-model'),previous=selector.value;target.replaceChildren();
  const rows=new Map(),filter=$('head-search').value.toLowerCase();
  const selected=new Set([...$('fit-armors').selectedOptions].map(o=>o.value));
  for(const item of state.choices?.armors||[]){if($('fit_mode').value==='selected'&&!selected.has(item.id))continue;for(const addon of item.addons||[]){if(!(addon.mask&0x3803))continue;if(!rows.has(addon.key))rows.set(addon.key,{...addon,label:item.label,armor:item.id});}}
  const visible=[...rows.values()].filter(a=>!filter||`${a.label} ${a.name}`.toLowerCase().includes(filter));
  selector.replaceChildren(...visible.map(a=>new Option(`${a.label} (${a.name})`,a.key)));
  if(visible.some(a=>a.key===previous))selector.value=previous;
  $('head-count').textContent=`${visible.length}モデル。装備を一つ選んで表示設定と見た目を確認できます。`;
  if(selector.value!==previous){$('head-preview-images').replaceChildren();$('head-preview-status').textContent='';}
  const addon=rows.get(selector.value);if(!addon)return;
  const row=document.createElement('div');row.dataset.addon=addon.key;row.className='head-policy-card';
  const name=document.createElement('strong');name.textContent=addon.label;const id=document.createElement('small');id.textContent=addon.name;row.append(name,id);
  const controls=document.createElement('div');controls.className='head-controls';
  const policy=state.headOverrides?.[addon.key]||{hide_face:$('head-hide-face').checked,hide_hair:$('head-hide-hair').checked&&!!(addon.mask&2)};
  for(const [key,label]of [['hide_face','顔を隠す'],['hide_hair','髪を隠す']]){const box=document.createElement('label');box.className='checkbox';const input=document.createElement('input');input.type='checkbox';input.checked=policy[key];input.dataset.policy=key;input.onchange=()=>{state.headOverrides??={};state.headOverrides[addon.key]={...policy,[key]:input.checked};$('head-preview-images').replaceChildren();renderHeadPolicies();};box.append(input,document.createTextNode(label));controls.append(box);}row.append(controls);
  const reset=document.createElement('button');reset.type='button';reset.className='secondary';reset.textContent='リセット';reset.onclick=()=>{delete state.headOverrides[addon.key];$('head-preview-images').replaceChildren();renderHeadPolicies();};
  const preview=document.createElement('button');preview.type='button';preview.className='secondary';preview.id='head-preview';preview.textContent='この頭装備を着せてプレビュー';
  preview.onclick=async()=>{preview.disabled=true;error();$('head-preview-images').replaceChildren();$('head-preview-status').textContent='頭装備をアバターに合わせています…';const identity=addon.key+JSON.stringify(policy),signature=headPreviewSignature();try{const result=await api('/api/head-preview',{source_id:state.source.source_id,game:$('game').value,blender:$('blender').value,settings:collect(),armor:addon.armor,policy});for(;;){const job=await api('/api/jobs/'+result.job_id);$('head-preview-status').textContent=job.stage;if(job.status==='failed')throw new Error(job.error);if(job.status==='complete'){const current=state.headOverrides?.[addon.key]||{hide_face:$('head-hide-face').checked,hide_hair:$('head-hide-hair').checked&&!!(addon.mask&2)};if($('head-model').value+JSON.stringify(current)!==identity||headPreviewSignature()!==signature){$('head-preview-status').textContent='設定が変わりました。プレビューを更新してください。';break;}for(const path of job.previews){const img=document.createElement('img');img.src=fileURL(job.id,path);img.alt=addon.label+'を装着したアバター';$('head-preview-images').append(img);}break;}await new Promise(r=>setTimeout(r,1000));}}catch(e){error(e.message);$('head-preview-status').textContent='プレビューを作成できませんでした';}finally{preview.disabled=false;}};
  row.append(reset,preview);target.append(row);
}
async function checkDeployedPatch(){
  const target=$('deployed-patch-status');
  try{
    const value=await api('/api/patch-status?job='+encodeURIComponent(state.resultJob)+'&game='+encodeURIComponent($('game').value));
    target.textContent=value.status==='current'?`ゲーム内のパッチは、このフォロワーの${value.expected_items.toLocaleString()}品に対応しています。`:`ゲーム内のパッチ：${value.installed_items.toLocaleString()}品。このフォロワー用の装備登録が${value.missing_bindings.toLocaleString()}件不足しています。生成した防具互換パッチZIPを旧版と置き換え、Deployしてください。`;
    target.className=value.status==='current'?'hint':'note';
  }catch(e){target.textContent=e.message;}
}
async function showArmorPatch(job) {
  $('armor-patch-result').hidden=!job.armor_patch; if(!job.armor_patch)return;
  $('armor-patch-download').textContent='このフォロワーだけのパッチを保存';$('armor-patch-download').href=fileURL(job.id,job.armor_patch);$('armor-patch-download').download='VRM2SkyrimArmorPatch.zip';await checkDeployedPatch();
  const result=await api('/api/fitted-followers?game='+encodeURIComponent($('game').value));$('fitted-followers').replaceChildren();
  for(const profile of result.profiles){const label=document.createElement('label'),input=document.createElement('input');label.className='checkbox';input.type='checkbox';input.value=profile.id;input.checked=profile.plugin===job.plugin_name||profile.deployed;label.append(input,document.createTextNode(profile.plugin));$('fitted-followers').append(label);}
}
function selectedTags(kind) {
  const selected=kind==='perks'?state.perks.keys():state.spells; const target=$('selected-'+kind); target.replaceChildren();
  for(const id of selected){const item=state.choices?.[kind].find(item=>item.id===id);const button=document.createElement('button'); button.type='button';button.textContent=(item?.label||id)+' ×';button.onclick=()=>{if(kind==='perks')state.perks.delete(id);else state.spells.delete(id);renderChoices();};target.append(button);}
}
function renderChoiceList(kind, term) {
  if(!state.choices)return; const target=$(kind);target.replaceChildren(); const q=term.toLowerCase();
  const visible=state.choices[kind].filter(item=>(item.id+' '+item.label+' '+item.description).toLowerCase().includes(q)).slice(0,100);
  for(const item of visible) {
    if(kind==='perks'&&item.ranks===0)continue;
    const label=document.createElement('label');label.className='choice'; const check=document.createElement('input');check.type='checkbox';check.dataset.recordId=item.id;check.checked=kind==='perks'?state.perks.has(item.id):state.spells.has(item.id);
    const title=document.createElement('strong');title.textContent=item.label;label.append(check,title);
    const desc=document.createElement('small');desc.textContent=item.id+(item.description?' · '+item.description:'');label.append(desc);
    check.onchange=()=>{if(kind==='perks'){if(check.checked)state.perks.set(item.id,0);else state.perks.delete(item.id);}else{if(check.checked)state.spells.add(item.id);else state.spells.delete(item.id);}renderChoices();};
    if(kind==='perks'&&check.checked&&item.ranks>1){const rank=document.createElement('input');rank.type='number';rank.min='1';rank.max=String(item.ranks);rank.value=String(state.perks.get(item.id)+1);rank.setAttribute('aria-label',item.label+'のランク');rank.onchange=()=>state.perks.set(item.id,Number(rank.value)-1);label.append(rank);}
    target.append(label);
  }
}
function renderChoices(){renderChoiceList('perks',$('perk-search').value);renderChoiceList('spells',$('spell-search').value);$('perk-count').textContent=state.perks.size;$('spell-count').textContent=state.spells.size;selectedTags('perks');selectedTags('spells');}
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
    const skillText=entries.map(([key,weight])=>`${skillLabels[skills.indexOf(key)]} ${weight}`).join(' ／ ');
    for(const text of [`得意スキルの成長配分：${skillText||'配分なし'}`,`体力 ${growth.attributes.health}：マジカ ${growth.attributes.magicka}：スタミナ ${growth.attributes.stamina}`, '数字は成長配分の比率です。自動計算で使われ、個別スキルの手動指定ではスキル値をこの配分から計算しません。']){const p=document.createElement('p');p.textContent=text;target.append(p);}
  }else target.textContent='このクラスの成長配分を読み取れませんでした。';
  const style=state.choices?.styles.find(item=>item.id===$('combat_style').value);
  $('style-details').textContent=style?`${style.humanoid?'人型NPCでの使用例あり':'人型NPCでの使用例を確認できないスタイル'}。使用種族：${style.used_by?.join('、')||'確認できず'}。`:'';
}
function updateLevel() {
  const manual=$('auto_calculate').value==='false';
  $('fixed-level').hidden=$('level_mode').value!=='fixed';$('mult-level').hidden=$('level_mode').value!=='player';
  $('skill-inputs').hidden=!manual;$('use-manual-skills').hidden=manual;
  for(const key of skills)$('skill-'+key).disabled=!manual;
  $('skills-hint').textContent=manual?'18スキルを0〜100で指定します。レベル追従を選んでも、スキルはこの指定値を使います。':'自動計算では、クラスとNPCのレベルからゲームがスキル値を決めます。数値を指定したい場合は手動設定へ切り替えてください。';
  $('stat-hint').textContent=manual?'体力・マジカ・スタミナも指定値を使います。':'成長前の基礎値を指定します。クラスとNPCのレベルに応じた成長分が加わります。';
  for(const [key,label] of [['health','体力'],['magicka','マジカ'],['stamina','スタミナ']])$(key).parentElement.firstChild.textContent=(manual?'':'基礎')+label;
  updateRoleDetails();
}
function updateMarriage(){if(!state.choices)return;const supported=state.choices.marriage_voices.includes($('voice').value);$('marriage').disabled=!supported;if(!supported)$('marriage').checked=false;}
function showStep(step) {
  state.step=step;error(); document.querySelectorAll('[data-step]').forEach(section=>section.hidden=Number(section.dataset.step)!==step);
  [...$('steps').children].forEach((li,index)=>{li.classList.toggle('active',index===step);li.classList.toggle('done',index<step);});
  $('back').hidden=step===0;$('next').hidden=step===4;$('create').hidden=step!==4;window.scrollTo(0,0);
}
function summarize(settings) {
  const voice=state.choices.voices.find(item=>item.id===settings.voice);
  const rows=[['アバター',state.source.filename],['NPC名',settings.npc_name],['MOD',settings.mod_name+' / '+settings.mod_id+'.esp'],['ボイス',voice?.label||settings.voice],['戦闘',settings.combat_class+' / '+settings.combat_style],['レベル',settings.level_mode==='player'?`プレイヤー×${settings.level_multiplier}（${settings.min_level}〜${settings.max_level}）`:String(settings.level)],['生存',{'protected':'保護','essential':'不死','mortal':'通常'}[settings.protection]],['体力 / マジカ / スタミナ',`${settings.health} / ${settings.magicka} / ${settings.stamina}${settings.auto_calculate?'（自動成長の補正に使用）':''}`],['Perk / 魔法',`${settings.perks.length} / ${settings.spells.length}`],['初期配置','ホワイトラン · キナレス聖堂']];
  rows.push(['衣服',settings.armor_support?`${settings.appearance_parts.garments.length}品を着脱可能（初期装備${settings.appearance_parts.garments.filter(g=>g.equipped).length}品）`:'元の衣服を着脱しない']);
  rows.push(['髪・布の物理演算',settings.physics_enabled?`FSMPを使用 · 硬さ${settings.physics_stiffness} · ${settings.physics_nodes.length?settings.physics_nodes.length+'メッシュを選択':'髪・衣服を自動選択'}`:'固定']);
  rows.push(['既存装備の体型合わせ',settings.fit_armors.length?settings.fit_armors.join('、'):'なし']);
  const dl=document.createElement('dl');for(const [title,value]of rows){const dt=document.createElement('dt');dt.textContent=title;const dd=document.createElement('dd');dd.textContent=value;dl.append(dt,dd);}$('summary').replaceChildren(dl);
}
async function next() {
  error(); const current=document.querySelector(`[data-step="${state.step}"]`);
  for(const field of current.querySelectorAll('input,select'))if(!field.checkValidity()){field.reportValidity();return;}
  $('next').disabled=true;
  try {
    if(state.step===0){if(!state.source)throw new Error('VRMファイルを選択してください');const result=await api('/api/catalog',{game:$('game').value,blender:$('blender').value});$('checks').replaceChildren();for(const [key,value]of Object.entries(result.checks)){const badge=document.createElement('span');badge.textContent=key+(value?' ✓':' 未準備');badge.className=value?'':'missing';$('checks').append(badge);}if(Object.values(result.checks).some(value=>!value))throw new Error('環境が未準備です。パスを確認し、初回はSetup.cmdを実行してください。');setupChoices(result.choices);}
    const result=await api('/api/validate',{source_id:state.source.source_id,game:$('game').value,settings:collect()});if(state.step===3)summarize(result.settings);
    showStep(state.step+1);
  }catch(e){error(e.message);}finally{$('next').disabled=false;}
}
function fileURL(job,name){return `/api/jobs/${job}/file?name=${encodeURIComponent(name)}`;}
function showResult(job) {
  state.resultJob=job.id;$('equipment-edit').hidden=!job.edit_kit;
  if(job.edit_kit){$('edit-kit-download').href=fileURL(job.id,job.edit_kit);$('edit-mesh').replaceChildren(...job.edit_meshes.map(i=>new Option(i.name,i.key)));}
  showArmorPatch(job).catch(e=>error(e.message));
  $('progress').hidden=true;$('result').hidden=false;$('result-title').textContent=job.npc_name+'を、スカイリムへ。';$('download').href=fileURL(job.id,job.archive);$('download').download=job.archive;$('plugin-name').textContent=job.plugin_name;$('output-folder').textContent='出力フォルダ: '+job.output;
  const names=['original-01.png','rest-01.png','walk-08.png','attack-10.png','attack-hand-10.png']; const labels=['元VRM（姿勢合わせ）','出力NIF','標準歩行','標準の剣攻撃','手と剣の近接確認'];$('previews').replaceChildren();
  for(let i=0;i<names.length;i++){const path=job.previews.find(path=>path.endsWith('/'+names[i]));if(!path)continue;const figure=document.createElement('figure');const image=document.createElement('img');image.src=fileURL(job.id,path);image.alt=labels[i];const caption=document.createElement('figcaption');caption.textContent=labels[i];figure.append(image,caption);$('previews').append(figure);}
  if(job.armor_support){const extra=[['wardrobe-underwear-rest-01.png','服を外した状態'],['wardrobe-underwear-walk-08.png','下着状態で歩行'],['wardrobe-underwear-attack-10.png','下着状態で剣攻撃'],...(job.garments||[]).map(g=>['wardrobe-without-'+g.id+'-rest-01.png',g.name+'だけ外した状態'])];for(const [name,label]of extra){const path=job.previews.find(p=>p.endsWith('/'+name));if(!path)continue;const figure=document.createElement('figure'),img=document.createElement('img'),caption=document.createElement('figcaption');img.src=fileURL(job.id,path);img.alt=label;caption.textContent=label;figure.append(img,caption);$('previews').append(figure);}}
  if(job.fit_armors?.length){for(const [name,label] of [['wardrobe-armor-all-rest-01.png','体型を合わせた装備'],['wardrobe-armor-all-walk-08.png','装備して歩行'],['wardrobe-armor-all-attack-10.png','装備して剣攻撃']]){const path=job.previews.find(p=>p.endsWith('/'+name));if(!path)continue;const figure=document.createElement('figure'),img=document.createElement('img'),caption=document.createElement('figcaption');img.src=fileURL(job.id,path);img.alt=label;caption.textContent=label;figure.append(img,caption);$('previews').append(figure);}}
}
async function poll() {
  try {const job=await api('/api/jobs/'+state.job);$('stage').textContent=job.stage;$('events').replaceChildren(...job.events.map(text=>{const li=document.createElement('li');li.textContent=text;return li;}));
    if(job.status==='complete'){showResult(job);return;}
    if(job.status==='failed'){$('failure').hidden=false;$('failure').textContent=job.error;$('wizard').hidden=false;$('progress').querySelector('.progress-bar').hidden=true;return;}
    setTimeout(poll,1000);
  }catch(e){error(e.message);$('wizard').hidden=false;}
}
async function create() {
  error();$('create').disabled=true;
  try {const result=await api('/api/jobs',{source_id:state.source.source_id,game:$('game').value,blender:$('blender').value,settings:collect()});state.job=result.job_id;$('wizard').hidden=true;$('progress').hidden=false;$('failure').hidden=true;$('progress').querySelector('.progress-bar').hidden=false;poll();}
  catch(e){error(e.message);}finally{$('create').disabled=false;}
}
function preset() {
  const presets={warrior:{combat_class:'CombatWarrior1H',combat_style:'csHumanMeleeLvl1',weapon:'SteelSword',ammunition:'',spells:[]},twohand:{combat_class:'CombatWarrior2H',combat_style:'csHumanBoss2H',weapon:'SteelGreatsword',ammunition:'',spells:[]},archer:{combat_class:'CombatRanger',combat_style:'csHumanMissile',weapon:'HuntingBow',ammunition:'IronArrow',spells:[]},mage:{combat_class:'CombatMageDestruction',combat_style:'csHumanMagic',weapon:'',ammunition:'',spells:['Firebolt','FastHealing']},conjurer:{combat_class:'CombatMageConjurer',combat_style:'csHumanMagic',weapon:'',ammunition:'',spells:['ConjureFlameAtronach','FastHealing']}};
  const chosen=presets[$('preset').value];if(!chosen)return;for(const key of ['combat_class','combat_style','weapon','ammunition'])$(key).value=chosen[key];state.spells=new Set(chosen.spells.filter(id=>state.choices.spells.some(item=>item.id===id)));renderChoices();
  const caster=['mage','conjurer'].includes($('preset').value);$('health').value=caster?150:200;$('magicka').value=caster?200:100;$('stamina').value=caster?100:150;updateStyles(chosen.combat_style);updateRoleDetails();
}
async function refreshSavedResults(preferred=$('saved-job').value) {
  const saved=await api('/api/jobs');
  $('saved-job').replaceChildren(...saved.jobs.map(job=>new Option(job.npc_name+' · '+job.plugin_name,job.id)));
  if(saved.jobs.some(job=>job.id===preferred))$('saved-job').value=preferred;
  $('saved-results').hidden=saved.jobs.length===0;
}
async function init() {
  for(let i=0;i<skills.length;i++){const label=document.createElement('label');label.textContent=skillLabels[i];const input=document.createElement('input');input.id='skill-'+skills[i];input.type='number';input.min='0';input.max='100';input.value='20';label.append(input);$('skills').append(label);}
  const env=await api('/api/environment');state.defaults=env.defaults;$('version').textContent='VRM2Skyrim '+env.version;$('game').value=env.game;$('blender').value=env.blender;applySettings(env.defaults);
  initWardrobe();
  await refreshSavedResults();
  $('check-deployed-patch').onclick=checkDeployedPatch;
  $('open-saved').onclick=async()=>{try{const job=await api('/api/jobs/'+$('saved-job').value);$('wizard').hidden=true;showResult(job);}catch(e){error(e.message);}};
  $('fit-enabled').onchange=async()=>{if($('fit-enabled').checked&&!state.choices){$('next').disabled=true;try{const result=await api('/api/catalog',{game:$('game').value,blender:$('blender').value});setupChoices(result.choices);}catch(e){error(e.message);$('fit-enabled').checked=false;}finally{$('next').disabled=false;}}setupFitting();};
  $('fit-armors').onchange=()=>{state.fitArmors=new Set([...$('fit-armors').selectedOptions].map(o=>o.value));renderHeadPolicies();};
  $('head-model').onchange=()=>{$('head-preview-images').replaceChildren();renderHeadPolicies();};$('fit_mode').onchange=setupFitting;$('head-search').oninput=renderHeadPolicies;
  $('head-hide-face').onchange=$('head-hide-hair').onchange=()=>{$('head-preview-images').replaceChildren();$('head-preview-status').textContent='';renderHeadPolicies();};$('fit_source').onchange=()=>{$('head-preview-images').replaceChildren();$('head-preview-status').textContent='';};
  $('import-edit').onclick=async()=>{const file=$('edit-nif').files[0];if(!file){$('edit-status').textContent='編集したNIFを選んでください';return;}$('import-edit').disabled=true;try{const response=await fetch('/api/equipment-edit',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Job-Id':state.resultJob,'X-Mesh-Key':$('edit-mesh').value,'X-Blender':encodeURIComponent($('blender').value)},body:file});const result=await response.json();if(!response.ok)throw new Error(result.error);for(;;){const job=await api('/api/jobs/'+result.job_id);$('edit-status').textContent=job.stage;if(job.status==='failed')throw new Error(job.error);if(job.status==='complete'){showResult(job);$('edit-status').textContent='仕上げを反映しました。更新されたMOD ZIPを保存してください。';break;}await new Promise(r=>setTimeout(r,1000));}}catch(e){$('edit-status').textContent=e.message;}finally{$('import-edit').disabled=false;}};
  $('merge-armor-patch').onclick=async()=>{const button=$('merge-armor-patch');button.disabled=true;$('armor-patch-status').textContent='互換パッチを作成しています…';try{const result=await api('/api/armor-patch',{game:$('game').value,profiles:[...$('fitted-followers').querySelectorAll('input:checked')].map(input=>input.value)});$('armor-patch-download').textContent='統合パッチを保存';$('armor-patch-download').href=fileURL(result.job_id,result.archive);$('armor-patch-status').textContent='選択したフォロワー分のパッチを作成しました。このZIPに差し替えてください。';}catch(e){$('armor-patch-status').textContent=e.message;}finally{button.disabled=false;}};
  $('source').onchange=()=>upload($('source').files[0]);const zone=document.querySelector('.dropzone');zone.ondragover=e=>{e.preventDefault();zone.classList.add('drag');};zone.ondragleave=()=>zone.classList.remove('drag');zone.ondrop=e=>{e.preventDefault();zone.classList.remove('drag');upload(e.dataTransfer.files[0]);};
  $('next').onclick=next;$('back').onclick=()=>showStep(state.step-1);$('create').onclick=create;$('level_mode').onchange=updateLevel;$('auto_calculate').onchange=updateLevel;$('preset').onchange=preset;
  $('combat_class').onchange=updateRoleDetails;$('combat_style').onchange=updateRoleDetails;
  $('all-styles').onchange=()=>{const selected=$('combat_style').value;const item=state.choices.styles.find(item=>item.id===selected);updateStyles(!$('all-styles').checked&&!item?.humanoid?state.defaults.combat_style:selected);};
  $('use-manual-skills').onclick=()=>{$('auto_calculate').value='false';$('manual-skills').open=true;updateLevel();};
  $('mod_name').oninput=()=>{state.nameDirty=true;updateId();};$('npc_name').oninput=()=>state.nameDirty=true;$('mod_id').oninput=()=>state.idDirty=true;
  $('sex').onchange=async()=>{const sex=$('sex').value;$('voice').value=sex==='male'?'MaleNord':'FemaleEvenToned';updateMarriage();if(state.choices){try{state.fitArmors=new Set([...$('fit-armors').selectedOptions].map(o=>o.value));const result=await api('/api/catalog',{game:$('game').value,blender:$('blender').value});if($('sex').value===sex){state.choices.armors=result.choices.armors;setupFitting();}}catch(e){error(e.message);}}};$('voice').onchange=updateMarriage;
  $('perk-search').oninput=renderChoices;$('spell-search').oninput=renderChoices;
  $('export-settings').onclick=()=>download($('mod_id').value+'-settings.json',collect());
  $('import-settings').onchange=async()=>{try{state.imported=JSON.parse(await $('import-settings').files[0].text());state.importPending=!state.choices;applySettings(state.imported);state.nameDirty=true;state.idDirty=true;$('import-status').textContent='設定を読み込みました';}catch(e){error(e.message);}};
  $('again').onclick=async()=>{$('result').hidden=true;$('equipment-edit').hidden=true;$('wizard').hidden=false;state.source=null;state.imported=null;state.nameDirty=false;state.idDirty=false;$('source').value='';$('source-status').textContent='次のVRMを選択してください';wardrobeLoad(null);showStep(0);try{await refreshSavedResults(state.resultJob);}catch(e){error('前に作ったフォロワーの一覧を更新できませんでした：'+e.message);}};
}
init().catch(e=>error(e.message));
