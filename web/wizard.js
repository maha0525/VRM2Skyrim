"use strict";
const $ = id => document.getElementById(id);
const state = {step:0, source:null, choices:null, defaults:null, job:null, imported:null, perks:new Map(), spells:new Set(), nameDirty:false, idDirty:false};
const skills = ["OneHanded","TwoHanded","Marksman","Block","Smithing","HeavyArmor","LightArmor","Pickpocket","Lockpicking","Sneak","Alchemy","Speechcraft","Alteration","Conjuration","Destruction","Illusion","Restoration","Enchanting"];
const skillLabels = ["片手武器","両手武器","弓術","防御","鍛冶","重装","軽装","スリ","開錠","隠密","錬金術","話術","変性","召喚","破壊","幻惑","回復","付呪"];
const integers = new Set(["level","min_level","max_level","health","magicka","stamina","confidence","aggression","morality"]);
const floats = new Set(["level_multiplier","height_scale","spawn_offset_x","spawn_offset_y"]);
function error(message="") {$('error').hidden=!message; $('error').textContent=message;}
async function api(path, data) {
  const response=await fetch(path, data===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
  const result=await response.json(); if(!response.ok)throw new Error(result.error||"通信に失敗しました"); return result;
}
function download(name, value) {const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:"application/json"})); const a=document.createElement('a'); a.href=url; a.download=name; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);}
function applySettings(settings) {
  for(const [key,value] of Object.entries(settings)) {const input=$(key); if(!input)continue; if(input.type==='checkbox') input.checked=value; else input.value=String(value);}
  state.perks=new Map((settings.perks||[]).map(item=>[item.editor_id,item.rank])); state.spells=new Set(settings.spells||[]);
  for(const key of skills) $('skill-'+key).value=settings.skills?.[key]??20;
  updateLevel(); updateMarriage(); renderChoices();
}
function collect() {
  const settings={};
  for(const [key,value] of Object.entries(state.defaults)) {
    const input=$(key); if(!input)continue;
    settings[key]=input.type==='checkbox'?input.checked:integers.has(key)?Number.parseInt(input.value,10):floats.has(key)?Number(input.value):typeof value==='boolean'?input.value==='true':input.value.trim();
  }
  settings.perks=[...state.perks].map(([editor_id,rank])=>({editor_id,rank})); settings.spells=[...state.spells];
  settings.skills=settings.auto_calculate?{}:Object.fromEntries(skills.map(key=>[key,Number($('skill-'+key).value)])); return settings;
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
    $('source-status').textContent=`${result.filename} · ${result.mesh_count}メッシュ · ${result.triangles.toLocaleString()}三角形`;
    if(!state.nameDirty&&!state.imported){$('npc_name').value=result.suggested_name; $('mod_name').value=result.suggested_name+'Follower'; await updateId();}
  }catch(e){state.source=null; error(e.message); $('source-status').textContent='読み込めませんでした';}
  finally{$('next').disabled=false;}
}
function fillSelect(id, choices, allowNone=false) {
  const selected=$(id).value||String(state.defaults[id]??''); $(id).replaceChildren();
  if(allowNone)$(id).add(new Option('なし',''));
  for(const item of choices)$(id).add(new Option(item.label===item.id?item.id:`${item.label} (${item.id})`,item.id));
  $(id).value=selected;
}
function setupChoices(choices) {
  state.choices=choices;
  for(const [id,key] of [['voice','voices'],['combat_class','classes'],['combat_style','styles'],['weapon','weapons'],['ammunition','ammunition']])fillSelect(id,choices[key],['weapon','ammunition'].includes(id));
  if(state.imported)applySettings(state.imported);
  updateMarriage();
  renderChoices();
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
function updateLevel() {$('fixed-level').hidden=$('level_mode').value!=='fixed';$('mult-level').hidden=$('level_mode').value!=='player';$('manual-skills').hidden=$('auto_calculate').value!=='false';}
function updateMarriage(){if(!state.choices)return;const supported=state.choices.marriage_voices.includes($('voice').value);$('marriage').disabled=!supported;if(!supported)$('marriage').checked=false;}
function showStep(step) {
  state.step=step;error(); document.querySelectorAll('[data-step]').forEach(section=>section.hidden=Number(section.dataset.step)!==step);
  [...$('steps').children].forEach((li,index)=>{li.classList.toggle('active',index===step);li.classList.toggle('done',index<step);});
  $('back').hidden=step===0;$('next').hidden=step===4;$('create').hidden=step!==4;window.scrollTo(0,0);
}
function summarize(settings) {
  const voice=state.choices.voices.find(item=>item.id===settings.voice);
  const rows=[['アバター',state.source.filename],['NPC名',settings.npc_name],['MOD',settings.mod_name+' / '+settings.mod_id+'.esp'],['ボイス',voice?.label||settings.voice],['戦闘',settings.combat_class+' / '+settings.combat_style],['レベル',settings.level_mode==='player'?`プレイヤー×${settings.level_multiplier}（${settings.min_level}〜${settings.max_level}）`:String(settings.level)],['生存',{'protected':'保護','essential':'不死','mortal':'通常'}[settings.protection]],['体力 / マジカ / スタミナ',`${settings.health} / ${settings.magicka} / ${settings.stamina}${settings.auto_calculate?'（自動成長の補正に使用）':''}`],['Perk / 魔法',`${settings.perks.length} / ${settings.spells.length}`],['初期配置','ホワイトラン · キナレス聖堂']];
  const dl=document.createElement('dl');for(const [title,value]of rows){const dt=document.createElement('dt');dt.textContent=title;const dd=document.createElement('dd');dd.textContent=value;dl.append(dt,dd);}$('summary').replaceChildren(dl);
}
async function next() {
  error(); const current=document.querySelector(`[data-step="${state.step}"]`);
  for(const field of current.querySelectorAll('input,select'))if(!field.checkValidity()){field.reportValidity();return;}
  $('next').disabled=true;
  try {
    if(state.step===0){if(!state.source)throw new Error('VRMファイルを選択してください');const result=await api('/api/catalog',{game:$('game').value,blender:$('blender').value});$('checks').replaceChildren();for(const [key,value]of Object.entries(result.checks)){const badge=document.createElement('span');badge.textContent=key+(value?' ✓':' 未準備');badge.className=value?'':'missing';$('checks').append(badge);}if(Object.values(result.checks).some(value=>!value))throw new Error('環境が未準備です。パスを確認し、初回はSetup.cmdを実行してください。');setupChoices(result.choices);}
    if(state.step>=1){const result=await api('/api/validate',{game:$('game').value,settings:collect()});if(state.step===3)summarize(result.settings);}
    showStep(state.step+1);
  }catch(e){error(e.message);}finally{$('next').disabled=false;}
}
function fileURL(job,name){return `/api/jobs/${job}/file?name=${encodeURIComponent(name)}`;}
function showResult(job) {
  $('progress').hidden=true;$('result').hidden=false;$('result-title').textContent=job.npc_name+'を、スカイリムへ。';$('download').href=fileURL(job.id,job.archive);$('download').download=job.archive;$('plugin-name').textContent=job.plugin_name;$('output-folder').textContent='出力フォルダ: '+job.output;
  const names=['original-01.png','rest-01.png','walk-08.png','attack-10.png','attack-hand-10.png']; const labels=['元VRM（姿勢合わせ）','出力NIF','標準歩行','標準の剣攻撃','手と剣の近接確認'];$('previews').replaceChildren();
  for(let i=0;i<names.length;i++){const path=job.previews.find(path=>path.endsWith('/'+names[i]));if(!path)continue;const figure=document.createElement('figure');const image=document.createElement('img');image.src=fileURL(job.id,path);image.alt=labels[i];const caption=document.createElement('figcaption');caption.textContent=labels[i];figure.append(image,caption);$('previews').append(figure);}
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
  const caster=['mage','conjurer'].includes($('preset').value);$('health').value=caster?150:200;$('magicka').value=caster?200:100;$('stamina').value=caster?100:150;
}
async function init() {
  for(let i=0;i<skills.length;i++){const label=document.createElement('label');label.textContent=skillLabels[i];const input=document.createElement('input');input.id='skill-'+skills[i];input.type='number';input.min='0';input.max='100';input.value='20';label.append(input);$('skills').append(label);}
  const env=await api('/api/environment');state.defaults=env.defaults;$('version').textContent='VRM2Skyrim '+env.version;$('game').value=env.game;$('blender').value=env.blender;applySettings(env.defaults);
  $('source').onchange=()=>upload($('source').files[0]);const zone=document.querySelector('.dropzone');zone.ondragover=e=>{e.preventDefault();zone.classList.add('drag');};zone.ondragleave=()=>zone.classList.remove('drag');zone.ondrop=e=>{e.preventDefault();zone.classList.remove('drag');upload(e.dataTransfer.files[0]);};
  $('next').onclick=next;$('back').onclick=()=>showStep(state.step-1);$('create').onclick=create;$('level_mode').onchange=updateLevel;$('auto_calculate').onchange=updateLevel;$('preset').onchange=preset;
  $('mod_name').oninput=()=>{state.nameDirty=true;updateId();};$('npc_name').oninput=()=>state.nameDirty=true;$('mod_id').oninput=()=>state.idDirty=true;
  $('sex').onchange=()=>{$('voice').value=$('sex').value==='male'?'MaleNord':'FemaleEvenToned';updateMarriage();};$('voice').onchange=updateMarriage;
  $('perk-search').oninput=renderChoices;$('spell-search').oninput=renderChoices;
  $('export-settings').onclick=()=>download($('mod_id').value+'-settings.json',collect());
  $('import-settings').onchange=async()=>{try{state.imported=JSON.parse(await $('import-settings').files[0].text());applySettings(state.imported);state.nameDirty=true;state.idDirty=true;$('import-status').textContent='設定を読み込みました';}catch(e){error(e.message);}};
  $('again').onclick=()=>{$('result').hidden=true;$('wizard').hidden=false;state.source=null;state.imported=null;state.nameDirty=false;state.idDirty=false;$('source').value='';$('source-status').textContent='次のVRMを選択してください';showStep(0);};
}
init().catch(e=>error(e.message));
