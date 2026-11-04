"use strict";
// Original weapons (STEP 03), one card per weapon in settings.original_weapons order.
// Each GLB stays on the server under its weapon_id; settings keep only its SHA256.
const weaponKindLabels={sword:'片手剣',dagger:'短剣',waraxe:'片手斧',mace:'メイス',greatsword:'両手剣',battleaxe:'両手斧',warhammer:'戦槌',staff:'杖'};
const officialWeaponTriangles=2066;  // most triangles among official weapons (intent: 366–2,066)
const maxOriginalWeapons=8;  // settings.MAX_ORIGINAL_WEAPONS
// Optional overrides of the base weapon's stats (settings.WEAPON_STATS); blank keeps the base value.
const weaponStats=[
  {id:'damage',label:'攻撃力',integer:true,max:65535,problem:'攻撃力は0〜65535の整数で指定してください'},
  {id:'weight',label:'重さ',problem:'重さは0以上の数で指定してください'},
  {id:'value',label:'価値（ゴールド）',integer:true,max:4294967295,problem:'価値は0〜4294967295の整数で指定してください'},
  {id:'speed',label:'速さ',positive:true,problem:'速さは0より大きい数で指定してください'},
  {id:'reach',label:'届く距離',positive:true,problem:'届く距離は0より大きい数で指定してください'}];
const weaponViews={drawn:'武器を抜いて構えた姿',hand:'手元の拡大',sheathed:'武器を収めた姿',compare:'元の武器と同じ縮尺で比較（赤い線が握る位置）'};
let weaponCardSerial=0;
function weaponKinds(){return state.choices?.original_weapons||[];}
function weaponCandidate(card){return weaponKinds().find(item=>item.id===card.kind)?.candidates.find(item=>item.id===card.base);}
function newWeaponCard(saved={}){
  return {key:++weaponCardSerial,glb:null,expected:saved.sha256?{sha256:saved.sha256,filename:saved.filename}:null,mismatch:'',
    kind:saved.kind||'',base:saved.base||'',pendingBase:saved.base||'',baseMissing:'',name:saved.name||'',
    grip:saved.grip!==undefined?String(Math.round(saved.grip*1e5)/1e3):'',length:saved.length!==undefined?String(saved.length):'',
    flip:!!saved.flip,roll:String(saved.roll??0),sizeDirty:!!saved.sha256,
    stats:Object.fromEntries(weaponStats.map(stat=>[stat.id,saved.stats?.[stat.id]!==undefined?String(saved.stats[stat.id]):''])),
    enchantment:saved.enchantment||'keep',preview:null,previewLoading:false};
}
function loadWeapon(settings){
  // Settings written before several weapons hold one original_weapon object.
  const saved=settings.original_weapons??(settings.original_weapon&&Object.keys(settings.original_weapon).length?[settings.original_weapon]:[]);
  const previous=state.weaponCards||[];
  state.weaponCards=saved.map(item=>{
    const card=newWeaponCard(item),uploaded=previous.find(old=>old.glb&&old.glb.sha256===card.expected?.sha256)?.glb;
    if(uploaded)card.glb=uploaded;  // the same GLB stays chosen across a settings import
    return card;
  });
  $('weapon_mode').value=settings.weapon_mode||'official';
  setupWeapon();
}
function setupWeapon(){
  const original=$('weapon_mode').value==='original';
  $('original-weapon-panel').hidden=!original;$('official-weapon').hidden=original;
  if(original&&!state.weaponCards?.length)state.weaponCards=[newWeaponCard()];
  state.weaponCards??=[];
  const kinds=weaponKinds();
  if(kinds.length)for(const card of state.weaponCards){
    if(!kinds.some(item=>item.id===card.kind))card.kind=kinds.some(item=>item.id==='sword')?'sword':kinds[0].id;
    const kind=kinds.find(item=>item.id===card.kind);
    const wanted=card.pendingBase||card.base;
    card.base=kind.candidates.some(item=>item.id===wanted)?wanted:kind.default;
    if(card.pendingBase&&card.base!==card.pendingBase)card.baseMissing=card.pendingBase;
    card.pendingBase='';
    if(card.kind==='staff')card.enchantment='keep';
  }
  renderWeaponCards();
  if(original)for(const card of state.weaponCards)updateWeaponBase(card);
}
function weaponIds(){return (state.weaponCards||[]).map(card=>card.glb?.weapon_id||null);}
function cardSettings(card,number,strict){
  const glb=card.glb||card.expected;
  const value={sha256:glb?.sha256||'',filename:glb?.filename||'',kind:card.kind,base:card.base,name:card.name.trim(),
    grip:Math.round(Number(card.grip)*1e3)/1e5,length:Number(card.length),flip:card.flip,roll:Number(card.roll),stats:{},
    enchantment:card.kind==='staff'?'keep':card.enchantment};
  let problem=!glb?'オリジナル武器のGLBを選んでください':!value.kind||!value.base?'元にする公式の武器を選んでください':!value.name?'武器の表示名を入力してください':
    !(card.grip!==''&&value.grip>0&&value.grip<1)?'握る位置は0より大きく100未満の割合（%）で指定してください':
    !(card.length!==''&&value.length>0&&value.length<1000)?'全長は0より大きく1000未満で指定してください':
    !(card.roll!==''&&value.roll>=0&&value.roll<360)?'回転は0以上360未満の角度で指定してください':'';
  for(const stat of weaponStats){
    const text=card.stats[stat.id].trim();if(problem||text==='')continue;
    const number=Number(text);
    const valid=Number.isFinite(number)&&(stat.integer?Number.isInteger(number)&&number>=0&&number<=stat.max:stat.positive?number>0:number>=0);
    if(valid)value.stats[stat.id]=number;else problem=stat.problem;
  }
  if(problem){if(strict)throw new Error(tr('オリジナル武器 {0}: {1}',number,tr(problem)));return null;}
  return value;
}
// strict (STEP 03 and later): every card must be complete. Otherwise incomplete cards send none.
function originalWeaponSettings(strict,cards=state.weaponCards||[]){
  const values=cards.map(card=>cardSettings(card,state.weaponCards.indexOf(card)+1,strict));
  return values.includes(null)?[]:values;
}
function weaponCardElement(card){return document.querySelector(`[data-weapon-card="${card.key}"]`);}
function field(card,role){return weaponCardElement(card)?.querySelector(`[data-role="${role}"]`);}
function labelled(text,control,note){
  const label=document.createElement('label');label.append(tr(text),control);
  if(note){const small=document.createElement('small');small.textContent=tr(note);label.append(small);}
  return label;
}
function input(role,type,attributes={}){
  const element=document.createElement('input');element.type=type;element.dataset.role=role;
  for(const [key,value] of Object.entries(attributes))element.setAttribute(key,value);
  return element;
}
function button(role,text,secondary=true){
  const element=document.createElement('button');element.type='button';element.dataset.role=role;element.textContent=tr(text);
  if(secondary)element.className='secondary';return element;
}
function buildWeaponCard(card,number){
  const section=document.createElement('section');section.className='weapon-card';section.dataset.weaponCard=card.key;
  const heading=document.createElement('div');heading.className='weapon-card-heading';
  const title=document.createElement('h4');title.textContent=tr('オリジナル武器 {0}',number);
  const remove=button('remove','この武器を外す');remove.disabled=state.weaponCards.length<=1;
  heading.append(title,remove);
  // The native input is hidden: it is cleared after each upload, so its own label would say nothing is chosen.
  // The drop zone is its label, so a click opens the file dialog and a dropped file uploads like the VRM's.
  const file=input('glb','file',{accept:'.glb',hidden:'',id:`weapon-glb-${card.key}`});
  const zone=document.createElement('label');zone.className='dropzone compact';zone.htmlFor=file.id;zone.tabIndex=0;
  zone.setAttribute('role','button');zone.dataset.role='drop';
  const strong=document.createElement('strong');strong.textContent=tr('武器のGLBファイルを選ぶ');
  const span=document.createElement('span');span.textContent=tr('クリック、またはここへドラッグ');zone.append(strong,span);
  const status=document.createElement('p');status.className='source-status';status.dataset.role='glb-status';status.setAttribute('aria-live','polite');
  const mismatch=document.createElement('div');mismatch.className='note weapon-glb-mismatch';mismatch.dataset.role='mismatch';mismatch.setAttribute('role','alert');
  const mismatchText=document.createElement('span');mismatchText.dataset.role='mismatch-text';
  mismatch.append(mismatchText,button('forget','設定のGLBを使わず、別のGLBにする'));
  const grid=document.createElement('div');grid.className='grid';
  const kind=document.createElement('select');kind.dataset.role='kind';
  kind.replaceChildren(...weaponKinds().map(item=>new Option(tr(weaponKindLabels[item.id]),item.id)));kind.value=card.kind;
  const base=document.createElement('select');base.dataset.role='base';
  const name=input('name','text',{maxlength:'128'});name.value=card.name;
  const grip=input('grip','number',{min:'0',max:'100',step:'any'});grip.value=card.grip;
  const length=input('length','number',{min:'0',max:'1000',step:'any'});length.value=card.length;
  const roll=input('roll','number',{min:'0',max:'360',step:'any'});roll.value=card.roll;
  const flip=input('flip','checkbox');flip.checked=card.flip;
  const flipLabel=document.createElement('label');flipLabel.className='checkbox';flipLabel.append(flip,tr('上下を反転する'));
  grid.append(labelled('武器の種類',kind),labelled('元にする公式の武器',base,'この武器の性能を受け継ぎます。'),labelled('ゲームでの表示名',name),
    labelled('握る位置（下端からの割合、%）',grip),labelled('全長',length,'Skyrimの長さの単位。1単位は約1.43cmです。'),
    labelled('回転（度）',roll,'長い向きを軸に回します。刃の向きを変えるときに使います。'),flipLabel);
  const baseStatus=document.createElement('p');baseStatus.className='hint';baseStatus.dataset.role='base-status';baseStatus.setAttribute('role','status');
  const statsTitle=document.createElement('h4');statsTitle.textContent=tr('性能と付呪');
  const statsHint=document.createElement('p');statsHint.className='hint';statsHint.textContent=tr('空欄の項目は、元にする公式の武器の値をそのまま使います。');
  const stats=document.createElement('div');stats.className='grid three';
  for(const stat of weaponStats){
    const element=input('stat-'+stat.id,'number',{min:'0',step:stat.integer?'1':'any',...(stat.max?{max:String(stat.max)}:{})});
    element.value=card.stats[stat.id];stats.append(labelled(stat.label,element));
  }
  const enchantment=document.createElement('select');enchantment.dataset.role='enchantment';
  const enchantmentLabel=labelled('武器の付呪',enchantment);enchantmentLabel.dataset.role='enchantment-field';
  const staffNote=document.createElement('p');staffNote.className='hint';staffNote.dataset.role='staff-note';
  staffNote.textContent=tr('杖の魔法（付呪）は、元にする杖のものをそのまま使います。');
  const previewTitle=document.createElement('h4');previewTitle.textContent=tr('プレビュー');
  const previewHint=document.createElement('p');previewHint.className='hint';previewHint.textContent=tr('値を変えたら、プレビューを描き直してください。初回はアバターの準備に数分かかる場合があります。');
  const previewStatus=document.createElement('p');previewStatus.className='hint';previewStatus.dataset.role='preview-status';
  previewStatus.setAttribute('role','status');previewStatus.setAttribute('aria-live','polite');
  const images=document.createElement('div');images.className='preview-grid weapon-preview-images';images.dataset.role='preview-images';
  section.append(heading,zone,file,status,mismatch,grid,baseStatus,button('reset-size','握る位置と全長を元の武器に合わせる'),
    statsTitle,statsHint,stats,enchantmentLabel,staffNote,button('reset-stats','性能と付呪を元の武器に戻す'),
    previewTitle,previewHint,button('preview','武器を持たせてプレビュー'),previewStatus,images);
  bindWeaponCard(card,section);
  return section;
}
function bindWeaponCard(card,section){
  const role=name=>section.querySelector(`[data-role="${name}"]`);
  const changed=()=>markWeaponPreviewStale();
  role('remove').onclick=()=>{state.weaponCards=state.weaponCards.filter(item=>item!==card);renderWeaponCards();};
  role('glb').addEventListener('change',()=>uploadWeapon(card,role('glb').files[0]));
  const zone=role('drop');
  zone.ondragover=e=>{e.preventDefault();zone.classList.add('drag');};
  zone.ondragleave=()=>zone.classList.remove('drag');
  zone.ondrop=e=>{e.preventDefault();zone.classList.remove('drag');uploadWeapon(card,e.dataTransfer.files[0]);};
  // The input is hidden, so the zone itself takes the keyboard, as the button it replaced did.
  zone.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();role('glb').click();}};
  role('forget').onclick=()=>{card.expected=null;card.glb=null;card.mismatch='';role('glb').value='';changed();renderWeaponGlb(card);role('glb').click();};
  role('kind').onchange=()=>{card.kind=role('kind').value;card.base='';card.baseMissing='';if(card.kind==='staff')card.enchantment='keep';
    fillWeaponBases(card);changed();updateWeaponBase(card);};
  role('base').onchange=()=>{card.base=role('base').value;card.baseMissing='';fillWeaponBases(card);changed();updateWeaponBase(card);};
  role('name').oninput=()=>{card.name=role('name').value;changed();};
  for(const key of ['grip','length'])role(key).oninput=()=>{card[key]=role(key).value;card.sizeDirty=true;changed();};
  role('roll').oninput=()=>{card.roll=role('roll').value;changed();};
  role('flip').onchange=()=>{card.flip=role('flip').checked;changed();};
  for(const stat of weaponStats)role('stat-'+stat.id).oninput=()=>{card.stats[stat.id]=role('stat-'+stat.id).value;};
  role('enchantment').onchange=()=>{card.enchantment=role('enchantment').value;};
  role('reset-size').onclick=()=>{const dimensions=state.weaponDimensions?.[card.base];
    if(dimensions){setWeaponSize(card,dimensions);card.sizeDirty=false;changed();}else updateWeaponBase(card);};
  role('reset-stats').onclick=()=>{for(const stat of weaponStats)card.stats[stat.id]='';card.enchantment='keep';fillWeaponStats(card);};
  role('preview').onclick=()=>weaponPreview(card);
}
function renderWeaponCards(){
  const container=$('weapon-cards');if(!container)return;
  state.weaponCards??=[];
  container.replaceChildren(...state.weaponCards.map((card,index)=>buildWeaponCard(card,index+1)));
  for(const card of state.weaponCards){fillWeaponBases(card);renderWeaponGlb(card);renderWeaponBaseStatus(card);renderWeaponPreview(card);}
  $('add-weapon').disabled=state.weaponCards.length>=maxOriginalWeapons;
}
function fillWeaponBases(card){
  const kind=weaponKinds().find(item=>item.id===card.kind),select=field(card,'base');if(!kind||!select)return;
  select.replaceChildren(...kind.candidates.map(item=>new Option(recordLabel(item)===item.id?item.id:`${recordLabel(item)} (${item.id})`,item.id)));
  if(!kind.candidates.some(item=>item.id===card.base))card.base=kind.default;
  select.value=card.base;
  fillWeaponStats(card);
}
function fillWeaponStats(card){
  const candidate=weaponCandidate(card),element=weaponCardElement(card);if(!element)return;
  for(const stat of weaponStats){
    const control=field(card,'stat-'+stat.id),base=candidate?.stats?.[stat.id];
    control.value=card.stats[stat.id];
    control.placeholder=base===undefined?'':String(stat.integer?base:Math.round(base*1000)/1000);
  }
  const staff=card.kind==='staff',select=field(card,'enchantment'),own=candidate?.enchantment;
  field(card,'enchantment-field').hidden=staff;field(card,'staff-note').hidden=!staff;
  select.replaceChildren(new Option(own?tr('元の武器のまま（{0}）',recordLabel(own)):tr('元の武器のまま（付呪なし）'),'keep'),
    new Option(tr('付呪なし'),'none'),
    ...(state.choices?.weapon_enchantments||[]).map(item=>new Option(recordLabel(item)===item.id?item.id:`${recordLabel(item)} (${item.id})`,item.id)));
  if(![...select.options].some(option=>option.value===card.enchantment))card.enchantment='keep';
  select.value=card.enchantment;
}
function renderWeaponGlb(card){
  const glb=card.glb,expected=card.expected,language=i18n.language,element=weaponCardElement(card);if(!element)return;
  let text=tr('まだ選択されていません');
  if(glb){
    text=tr('{0} · 三角形ポリゴン{1} · 頂点{2}',glb.filename,glb.triangles.toLocaleString(language),glb.vertices.toLocaleString(language));
    if(glb.triangles>officialWeaponTriangles)text+=tr('（公式の武器で最も多いものの約{0}倍）',(Math.round(glb.triangles/officialWeaponTriangles*10)/10).toLocaleString(language));
  }else if(expected)text=tr('設定に保存したGLB「{0}」を選び直してください',expected.filename);
  field(card,'glb-status').textContent=text;
  field(card,'mismatch').hidden=!card.mismatch;
  field(card,'mismatch-text').textContent=card.mismatch?tr('「{0}」は、設定に保存したオリジナル武器のGLB「{1}」と別のファイルのため使えません。設定したときと同じGLBを選んでください。',card.mismatch,expected?.filename||''):'';
}
async function uploadWeapon(card,file){
  if(!file)return;error();card.mismatch='';field(card,'glb-status').textContent=tr('GLBを読み込んでいます…');
  try{
    const response=await fetch('/api/weapon-glb',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Filename':encodeURIComponent(file.name)},body:file});
    const result=await response.json();if(!response.ok)throw new Error(result.error||tr('通信に失敗しました'));
    if(field(card,'glb'))field(card,'glb').value='';
    if(card.expected&&result.sha256!==card.expected.sha256){card.mismatch=result.filename;renderWeaponGlb(card);return;}
    card.glb=result;
    if(!card.name.trim()){card.name=result.filename.replace(/\.glb$/i,'');if(field(card,'name'))field(card,'name').value=card.name;}
    markWeaponPreviewStale();renderWeaponGlb(card);
  }catch(e){error(e.message);renderWeaponGlb(card);}
}
function setWeaponSize(card,dimensions){
  card.grip=(Math.round(dimensions.grip*1000)/10).toFixed(1);card.length=(Math.round(dimensions.length*10)/10).toFixed(1);
  if(field(card,'grip')){field(card,'grip').value=card.grip;field(card,'length').value=card.length;}
}
async function updateWeaponBase(card){
  const base=card.base;if(!base||!$('game').value)return;
  let dimensions=state.weaponDimensions?.[base];
  if(!dimensions){
    card.baseLoading=true;renderWeaponBaseStatus(card);
    try{dimensions=await api('/api/weapon-base',{game:$('game').value,base});(state.weaponDimensions??={})[base]=dimensions;}
    catch(e){card.baseError=e.message;return;}
    finally{card.baseLoading=false;renderWeaponBaseStatus(card);}
  }
  if(card.base!==base)return;
  card.baseError='';
  if(!card.sizeDirty||card.grip===''||card.length===''){setWeaponSize(card,dimensions);card.sizeDirty=false;}
  renderWeaponBaseStatus(card);
}
function renderWeaponBaseStatus(card){
  const dimensions=state.weaponDimensions?.[card.base],language=i18n.language,parts=[],element=field(card,'base-status');if(!element)return;
  if(card.baseMissing)parts.push(tr('設定の元の武器 {0} が見つからないため、{1} を選びました。',card.baseMissing,card.base));
  if(card.baseLoading)parts.push(tr('元の武器の大きさを測っています…'));
  else if(dimensions)parts.push(tr('元の武器の全長は{0}、握る位置は下端から{1}%です。',(Math.round(dimensions.length*10)/10).toLocaleString(language),(Math.round(dimensions.grip*1000)/10).toLocaleString(language)));
  else if(card.baseError)parts.push(tr('元の武器の大きさを測れませんでした: ')+card.baseError);
  element.textContent=parts.join(' ');
}
// Everything the server's avatar and weapon cache keys depend on (weapon_preview.preview).
function weaponPreviewSignature(card,settings){
  let weapon;
  try{settings??=collect({weaponCard:card});weapon=settings.original_weapons[0];}catch{return '';}
  return JSON.stringify([state.source?.source_id,$('game').value,$('blender').value,weapon&&['sha256','kind','base','grip','length','flip','roll'].map(key=>weapon[key]),
    settings.armor_support,settings.appearance_parts,settings.appearance_heads,settings.sex,settings.height_scale]);
}
function markWeaponPreviewStale(){
  for(const card of state.weaponCards||[])if(card.preview){card.preview.stale=weaponPreviewSignature(card)!==card.preview.signature;renderWeaponPreview(card);}
}
function renderWeaponPreview(card){
  const job=card.preview,images=field(card,'preview-images'),status=field(card,'preview-status');if(!images)return;
  images.replaceChildren();field(card,'preview').disabled=!!card.previewLoading;
  if(card.previewLoading){status.textContent=uiMessage(card.previewStage||'武器のプレビューを準備しています…');return;}
  if(card.previewFailed){status.textContent=tr('プレビューを作成できませんでした');return;}
  if(!job){status.textContent='';return;}
  job.previews.forEach((path,index)=>{
    const figure=document.createElement('figure'),image=document.createElement('img'),caption=document.createElement('figcaption');
    image.src=fileURL(job.id,path);image.alt=tr(weaponViews[job.views[index]]);caption.textContent=image.alt;figure.dataset.weaponView=job.views[index];
    figure.append(image,caption);images.append(figure);
  });
  status.textContent=job.stale?tr('プレビューの後で値を変えました。もう一度描いてください。'):tr('このプレビューはBlenderでの確認用です（握る位置や大きさの目安として確認できます）。');
}
async function weaponPreview(card){
  if(card.previewLoading)return;
  error();
  let settings;try{settings=collect({weaponCard:card});if(settings.weapon_mode!=='original')return;}catch(e){error(e.message);return;}
  card.previewLoading=true;card.previewFailed=false;card.previewStage='';renderWeaponPreview(card);
  const signature=weaponPreviewSignature(card,settings);
  try{
    // One card per preview: its settings alone, as the server builds it.
    const started=await api('/api/weapon-preview',{source_id:state.source.source_id,weapon_ids:[card.glb?.weapon_id],game:$('game').value,blender:$('blender').value,settings});
    for(;;){
      const job=await api('/api/jobs/'+started.job_id);card.previewStage=job.stage;renderWeaponPreview(card);
      if(job.status==='failed')throw new Error(job.error);
      if(job.status==='complete'){card.preview={...job,signature};card.previewLoading=false;card.preview.stale=weaponPreviewSignature(card)!==signature;break;}
      await new Promise(resolve=>setTimeout(resolve,1000));
    }
  }catch(e){error(e.message);card.previewFailed=true;}
  finally{card.previewLoading=false;renderWeaponPreview(card);}
}
function weaponSummary(settings){
  if(settings.weapon_mode==='original')return settings.original_weapons.map(w=>tr('オリジナル武器「{0}」（{1}、元: {2}、{3}）',w.name,tr(weaponKindLabels[w.kind]),w.base,w.filename)).join(i18n.language==='en'?', ':'、');
  const item=state.choices?.weapons.find(item=>item.id===settings.weapon);
  return settings.weapon?recordLabel(item)||settings.weapon:tr('なし');
}
function initWeapon(){
  $('weapon_mode').addEventListener('change',()=>{error();setupWeapon();});
  $('add-weapon').onclick=()=>{
    if(state.weaponCards.length>=maxOriginalWeapons)return;
    state.weaponCards.push(newWeaponCard());setupWeapon();
  };
}
