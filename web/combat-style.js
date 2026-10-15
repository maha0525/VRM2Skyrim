"use strict";
function loadCombatStyle(settings){
  state.styleCustom=structuredClone(settings.combat_style_custom||{});
  $('combat_style_mode').value=settings.combat_style_mode||'existing';
  renderCombatStyle();
}
function copyCombatStyle(confirmChanges=true){
  const source=state.choices?.styles.find(item=>item.id===$('combat_style').value)?.config;
  if(!source){error(tr('このスタイルには編集できる設定がありません。別のスタイルを選んでください。'));return false;}
  if(confirmChanges&&state.styleDirty&&!window.confirm(tr('現在の調整を、選択したスタイルの値で置き換えますか？')))return false;
  state.styleCustom=structuredClone(source);state.styleDirty=false;
  $('combat_style_mode').value='custom';error();renderCombatStyle();return true;
}
function renderCombatStyle(){
  const custom=$('combat_style_mode').value==='custom';
  $('combat-style-editor').hidden=!custom;
  $('copy-combat-style').disabled=!state.choices;
  if(!custom)return;
  const config=state.styleCustom,original=state.choices?.styles.find(item=>item.id===config?.source)?.config;
  if(original)config.values={...original.values,...config.values};
  if(original&&(config.flags!==original.flags||Object.keys({...original.values,...config.values}).some(key=>config.values[key]!==original.values[key])))state.styleDirty=true;
  $('combat-style-source').textContent=tr('コピー元: {0}',config?.source||tr('未選択'));
  const basic=$('combat-style-basic'),advanced=$('combat-style-advanced');basic.replaceChildren();advanced.replaceChildren();
  if(!config?.values||!state.choices)return;
  const flags=document.createElement('div');flags.className='combat-style-flags';
  const dual=document.createElement('label');dual.className='checkbox';
  const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.id='combat-dual-wield';checkbox.checked=Boolean(config.flags&4);
  checkbox.onchange=()=>{config.flags=(config.flags&~4)|(checkbox.checked?4:0);state.styleDirty=true;};
  dual.append(checkbox,document.createTextNode(tr('二刀流を許可する (Allow Dual Wielding)')));flags.append(dual);
  const hint=document.createElement('p');hint.className='hint';hint.textContent=tr('二刀流には使用できる片手武器が2本必要です。Perk・武器・魔法の設定は別途行います。');flags.append(hint);
  const resetFlags=document.createElement('button');resetFlags.type='button';resetFlags.className='secondary';resetFlags.textContent=tr('許可・接近戦の方針を元に戻す');resetFlags.onclick=()=>{config.flags=original?.flags??config.flags;state.styleDirty=true;renderCombatStyle();};flags.append(resetFlags);basic.append(flags);
  const groups={};
  for(const [key,label] of [['general',tr('全般')],['melee',tr('近接攻撃・バッシュ')],['close',tr('接近戦の移動')],['long',tr('遠距離戦の移動')],['flight',tr('飛行用（通常は変更不要）')]]){
    const details=document.createElement('details');details.dataset.combatSection=key;
    const summary=document.createElement('summary');summary.textContent=label;details.append(summary);
    const grid=document.createElement('div');grid.className='combat-style-grid';details.append(grid);advanced.append(details);groups[key]=grid;
  }
  const strategy=document.createElement('label');strategy.textContent=tr('接近戦の方針');
  const select=document.createElement('select');select.id='combat-close-strategy';
  for(const [value,label] of [[0,tr('指定なし')],[1,tr('正面で戦う (Dueling)')],[2,tr('側面へ回り込む (Flanking)')]])select.add(new Option(label,String(value)));
  if((config.flags&3)===3)select.add(new Option(tr('元データの組合せ'),'3'));
  select.value=String(config.flags&3);select.onchange=()=>{config.flags=(config.flags&~3)|Number(select.value);state.styleDirty=true;};strategy.append(select);groups.close.append(strategy);
  for(const field of state.choices.combat_style_fields||[]){
    const key=field.key,baseline=original?.values[key],row=document.createElement('div');row.className='combat-style-field';row.dataset.combatField=key;
    const label=document.createElement('label');label.htmlFor='combat-'+key;label.textContent=field.labels[i18n.language];
    if(i18n.language!=='en'){const ck=document.createElement('small');ck.textContent=field.labels.en;label.append(ck);}
    const controls=document.createElement('div');controls.className='combat-style-controls';
    const range=document.createElement('input');range.type='range';range.min='0';range.max=String(field.slider_max);range.step='0.01';range.setAttribute('aria-label',field.labels[i18n.language]);
    const number=document.createElement('input');number.type='number';number.id='combat-'+key;number.min='0';number.max=String(field.slider_max);number.step='any';number.placeholder=tr('ゲーム既定');
    function refresh(){const value=config.values[key];number.value=value===undefined?'':String(value===baseline?Number(value.toFixed(4)):value);number.required=value!==undefined;range.value=String(value??0);row.classList.toggle('changed',value!==baseline);}
    range.oninput=()=>{config.values[key]=Number(range.value);state.styleDirty=true;refresh();};
    number.oninput=()=>{config.values[key]=number.value===''?NaN:Number(number.value);state.styleDirty=true;range.value=number.value;row.classList.toggle('changed',config.values[key]!==baseline);};
    const reset=document.createElement('button');reset.type='button';reset.className='secondary';reset.textContent=tr('元に戻す');reset.onclick=()=>{if(baseline===undefined)delete config.values[key];else config.values[key]=baseline;state.styleDirty=true;refresh();};
    const originalText=document.createElement('small');originalText.textContent=tr('コピー元: {0}',baseline===undefined?tr('ゲーム既定'):String(Number(baseline.toFixed(4))));
    controls.append(range,number,reset);row.append(label,controls,originalText);(field.basic?basic:groups[field.section]).append(row);refresh();
  }
}
function initCombatStyle(){
  $('combat_style_mode').onchange=()=>{
    if($('combat_style_mode').value==='custom'&&!state.styleCustom?.values&&!copyCombatStyle(false))$('combat_style_mode').value='existing';
    renderCombatStyle();
  };
  $('copy-combat-style').onclick=()=>copyCombatStyle();
  $('reset-combat-style').onclick=()=>{
    if(!window.confirm(tr('すべての調整をコピー元の値に戻しますか？')))return;
    const source=state.choices.styles.find(item=>item.id===state.styleCustom?.source)?.config;
    if(source){state.styleCustom=structuredClone(source);state.styleDirty=false;renderCombatStyle();}
  };
}
