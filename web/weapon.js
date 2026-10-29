"use strict";
// Original weapon (STEP 03). The GLB stays on the server under weapon_id; settings keep only its SHA256.
const weaponKindLabels={sword:'片手剣',dagger:'短剣',waraxe:'片手斧',mace:'メイス',greatsword:'両手剣',battleaxe:'両手斧',warhammer:'戦槌',staff:'杖'};
const officialWeaponTriangles=2066;  // most triangles among official weapons (intent: 366–2,066)
function weaponKinds(){return state.choices?.original_weapons||[];}
function loadWeapon(settings){
  const saved=settings.original_weapon||{};
  state.weaponPending=Object.keys(saved).length?structuredClone(saved):null;
  state.weaponExpected=saved.sha256?{sha256:saved.sha256,filename:saved.filename}:null;
  if(state.weaponGlb&&state.weaponExpected&&state.weaponGlb.sha256!==state.weaponExpected.sha256)state.weaponGlb=null;
  state.weaponMismatch='';state.weaponSizeDirty=!!state.weaponPending;
  $('weapon_mode').value=settings.weapon_mode||'official';
  $('weapon-name').value=saved.name||'';
  $('weapon-grip').value=saved.grip!==undefined?String(Math.round(saved.grip*1e5)/1e3):'';
  $('weapon-length').value=saved.length!==undefined?String(saved.length):'';
  $('weapon-flip').checked=!!saved.flip;$('weapon-roll').value=String(saved.roll??0);
  clearWeaponPreview();setupWeapon();
}
function setupWeapon(){
  const original=$('weapon_mode').value==='original';
  $('original-weapon-panel').hidden=!original;$('official-weapon').hidden=original;
  const kinds=weaponKinds();
  if(kinds.length){
    const pending=state.weaponPending,kind=pending?.kind||$('weapon-kind').value||'sword';
    $('weapon-kind').replaceChildren(...kinds.map(item=>new Option(tr(weaponKindLabels[item.id]),item.id)));
    $('weapon-kind').value=kinds.some(item=>item.id===kind)?kind:kinds[0].id;
    fillWeaponBases(pending?.base??$('weapon-base').value);
    state.weaponBaseMissing=pending?.base&&$('weapon-base').value!==pending.base?pending.base:'';
    state.weaponPending=null;
  }
  renderWeaponGlb();renderWeaponBaseStatus();
  if(original)updateWeaponBase();
}
function fillWeaponBases(preferred){
  const kind=weaponKinds().find(item=>item.id===$('weapon-kind').value);if(!kind)return;
  $('weapon-base').replaceChildren(...kind.candidates.map(item=>new Option(recordLabel(item)===item.id?item.id:`${recordLabel(item)} (${item.id})`,item.id)));
  $('weapon-base').value=kind.candidates.some(item=>item.id===preferred)?preferred:kind.default;
}
function originalWeaponSettings(strict){
  const glb=state.weaponGlb||state.weaponExpected,pending=state.weaponPending||{};
  const value={sha256:glb?.sha256||'',filename:glb?.filename||'',kind:$('weapon-kind').value||pending.kind||'',base:$('weapon-base').value||pending.base||'',
    name:$('weapon-name').value.trim(),grip:Math.round(Number($('weapon-grip').value)*1e3)/1e5,length:Number($('weapon-length').value),
    flip:$('weapon-flip').checked,roll:Number($('weapon-roll').value)};
  const problem=!glb?'オリジナル武器のGLBを選んでください':!value.kind||!value.base?'元にする公式の武器を選んでください':!value.name?'武器の表示名を入力してください':
    !($('weapon-grip').value!==''&&value.grip>0&&value.grip<1)?'握る位置は0より大きく100未満の割合（%）で指定してください':
    !($('weapon-length').value!==''&&value.length>0&&value.length<1000)?'全長は0より大きく1000未満で指定してください':
    !($('weapon-roll').value!==''&&value.roll>=0&&value.roll<360)?'回転は0以上360未満の角度で指定してください':'';
  if(problem){if(strict)throw new Error(tr(problem));return {};}
  return value;
}
function renderWeaponGlb(){
  const glb=state.weaponGlb,expected=state.weaponExpected,language=i18n.language;
  let text=tr('まだ選択されていません');
  if(glb){
    text=tr('{0} · 三角形ポリゴン{1} · 頂点{2}',glb.filename,glb.triangles.toLocaleString(language),glb.vertices.toLocaleString(language));
    if(glb.triangles>officialWeaponTriangles)text+=tr('（公式の武器で最も多いものの約{0}倍）',(Math.round(glb.triangles/officialWeaponTriangles*10)/10).toLocaleString(language));
  }else if(expected)text=tr('設定に保存したGLB「{0}」を選び直してください',expected.filename);
  $('weapon-glb-status').textContent=text;
  $('weapon-glb-mismatch').hidden=!state.weaponMismatch;
  $('weapon-glb-mismatch-text').textContent=state.weaponMismatch?tr('「{0}」は、設定に保存したオリジナル武器のGLB「{1}」と別のファイルのため使えません。設定したときと同じGLBを選んでください。',state.weaponMismatch,expected?.filename||''):'';
}
async function uploadWeapon(file){
  if(!file)return;error();state.weaponMismatch='';$('weapon-glb-status').textContent=tr('GLBを読み込んでいます…');
  try{
    const response=await fetch('/api/weapon-glb',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Filename':encodeURIComponent(file.name)},body:file});
    const result=await response.json();if(!response.ok)throw new Error(result.error||tr('通信に失敗しました'));
    $('weapon-glb').value='';
    if(state.weaponExpected&&result.sha256!==state.weaponExpected.sha256){state.weaponMismatch=result.filename;renderWeaponGlb();return;}
    state.weaponGlb=result;
    if(!$('weapon-name').value.trim())$('weapon-name').value=result.filename.replace(/\.glb$/i,'');
    markWeaponPreviewStale();renderWeaponGlb();
  }catch(e){error(e.message);renderWeaponGlb();}
}
function setWeaponSize(dimensions){
  $('weapon-grip').value=(Math.round(dimensions.grip*1000)/10).toFixed(1);
  $('weapon-length').value=(Math.round(dimensions.length*10)/10).toFixed(1);
}
async function updateWeaponBase(){
  const base=$('weapon-base').value;if(!base||!$('game').value)return;
  let dimensions=state.weaponDimensions?.[base];
  if(!dimensions){
    state.weaponBaseLoading=true;renderWeaponBaseStatus();
    try{dimensions=await api('/api/weapon-base',{game:$('game').value,base});(state.weaponDimensions??={})[base]=dimensions;}
    catch(e){state.weaponBaseError=e.message;return;}
    finally{state.weaponBaseLoading=false;renderWeaponBaseStatus();}
  }
  if($('weapon-base').value!==base)return;
  state.weaponBaseError='';
  if(!state.weaponSizeDirty||$('weapon-grip').value===''||$('weapon-length').value===''){setWeaponSize(dimensions);state.weaponSizeDirty=false;}
  renderWeaponBaseStatus();
}
function renderWeaponBaseStatus(){
  const dimensions=state.weaponDimensions?.[$('weapon-base').value],language=i18n.language,parts=[];
  if(state.weaponBaseMissing)parts.push(tr('設定の元の武器 {0} が見つからないため、{1} を選びました。',state.weaponBaseMissing,$('weapon-base').value));
  if(state.weaponBaseLoading)parts.push(tr('元の武器の大きさを測っています…'));
  else if(dimensions)parts.push(tr('元の武器の全長は{0}、握る位置は下端から{1}%です。',(Math.round(dimensions.length*10)/10).toLocaleString(language),(Math.round(dimensions.grip*1000)/10).toLocaleString(language)));
  else if(state.weaponBaseError)parts.push(tr('元の武器の大きさを測れませんでした: ')+state.weaponBaseError);
  $('weapon-base-status').textContent=parts.join(' ');
}
const weaponViews={drawn:'武器を抜いて構えた姿',hand:'手元の拡大',sheathed:'武器を収めた姿',compare:'元の武器と同じ縮尺で比較（赤い線が握る位置）'};
function clearWeaponPreview(){state.weaponPreview=null;$('weapon-preview-images').replaceChildren();$('weapon-preview-status').textContent='';}
// Everything the server's avatar and weapon cache keys depend on (weapon_preview.preview).
function weaponPreviewSignature(settings){
  try{settings??=collect();}catch{return '';}
  return JSON.stringify([state.source?.source_id,$('game').value,$('blender').value,settings.original_weapon,settings.armor_support,
    settings.appearance_parts,settings.appearance_heads,settings.sex,settings.height_scale]);
}
function markWeaponPreviewStale(){if(state.weaponPreview){state.weaponPreview.stale=weaponPreviewSignature()!==state.weaponPreview.signature;renderWeaponPreview();}}
function renderWeaponPreview(){
  const job=state.weaponPreview;$('weapon-preview-images').replaceChildren();if(!job)return;
  job.previews.forEach((path,index)=>{
    const figure=document.createElement('figure'),image=document.createElement('img'),caption=document.createElement('figcaption');
    image.src=fileURL(job.id,path);image.alt=tr(weaponViews[job.views[index]]);caption.textContent=image.alt;figure.dataset.weaponView=job.views[index];
    figure.append(image,caption);$('weapon-preview-images').append(figure);
  });
  $('weapon-preview-status').textContent=job.stale?tr('プレビューの後で値を変えました。もう一度描いてください。'):tr('このプレビューはBlenderでの確認用です（握る位置や大きさの目安として確認できます）。');
}
async function weaponPreview(){
  if(state.weaponPreviewLoading)return;
  error();
  let settings;try{settings=collect();if(settings.weapon_mode!=='original')return;}catch(e){error(e.message);return;}
  state.weaponPreviewLoading=true;$('weapon-preview').disabled=true;$('weapon-preview-status').textContent=tr('武器のプレビューを準備しています…');
  const signature=weaponPreviewSignature(settings);
  try{
    const started=await api('/api/weapon-preview',{source_id:state.source.source_id,weapon_id:state.weaponGlb?.weapon_id,game:$('game').value,blender:$('blender').value,settings});
    for(;;){
      const job=await api('/api/jobs/'+started.job_id);$('weapon-preview-status').textContent=uiMessage(job.stage);
      if(job.status==='failed')throw new Error(job.error);
      if(job.status==='complete'){
        state.weaponPreview={...job,signature,stale:weaponPreviewSignature()!==signature};renderWeaponPreview();break;
      }
      await new Promise(resolve=>setTimeout(resolve,1000));
    }
  }catch(e){error(e.message);$('weapon-preview-status').textContent=tr('プレビューを作成できませんでした');}
  finally{state.weaponPreviewLoading=false;$('weapon-preview').disabled=false;}
}
function weaponSummary(settings){
  if(settings.weapon_mode==='original'){const w=settings.original_weapon;return tr('オリジナル武器「{0}」（{1}、元: {2}、{3}）',w.name,tr(weaponKindLabels[w.kind]),w.base,w.filename);}
  const item=state.choices?.weapons.find(item=>item.id===settings.weapon);
  return settings.weapon?recordLabel(item)||settings.weapon:tr('なし');
}
function initWeapon(){
  $('weapon_mode').addEventListener('change',()=>{error();setupWeapon();});
  // The native input is hidden: it is cleared after each upload, so its own label would say nothing is chosen.
  $('weapon-glb-choose').onclick=()=>$('weapon-glb').click();
  $('weapon-glb').addEventListener('change',()=>uploadWeapon($('weapon-glb').files[0]));
  $('weapon-glb-forget').onclick=()=>{state.weaponExpected=null;state.weaponGlb=null;state.weaponMismatch='';$('weapon-glb').value='';markWeaponPreviewStale();renderWeaponGlb();$('weapon-glb').click();};
  $('weapon-kind').addEventListener('change',()=>{state.weaponBaseMissing='';fillWeaponBases('');markWeaponPreviewStale();updateWeaponBase();});
  $('weapon-base').addEventListener('change',()=>{state.weaponBaseMissing='';markWeaponPreviewStale();updateWeaponBase();});
  for(const id of ['weapon-grip','weapon-length'])$(id).addEventListener('input',()=>{state.weaponSizeDirty=true;markWeaponPreviewStale();});
  for(const id of ['weapon-name','weapon-roll','weapon-flip'])$(id).addEventListener('input',markWeaponPreviewStale);
  $('weapon-flip').addEventListener('change',markWeaponPreviewStale);
  $('weapon-reset-size').onclick=()=>{const dimensions=state.weaponDimensions?.[$('weapon-base').value];if(dimensions){setWeaponSize(dimensions);state.weaponSizeDirty=false;markWeaponPreviewStale();}else updateWeaponBase();};
  $('weapon-preview').onclick=weaponPreview;
}
