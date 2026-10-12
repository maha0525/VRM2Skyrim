"use strict";
const wardrobeSlots=[53,54,55,56,57,58,59,44,45,48,49,46,47];
const wardrobeKinds={body:'上半身・全身服',legs:'下半身（スカート・タイツなど）',hands:'手袋',feet:'靴',cloak:'マント',backpack:'バッグ',accessory:'その他のアクセサリー'};
function wardrobeSlotLabel(slot){return slot===46?'46 · マントとして表示される枠':slot===47?'47 · バッグとして表示される枠':`${slot} · 重ね着枠`;}
function wardrobeItemKind(g){if(g.item_kind)return g.item_kind;const n=g.name.toLowerCase();for(const [kind,pattern]of [['feet',/boot|shoe|loafer|sandal|靴|ブーツ|サンダル/],['hands',/glove|gauntlet|手袋|籠手/],['backpack',/backpack|リュック|バックパック/],['cloak',/cloak|cape|マント|ケープ/],['legs',/tights|stocking|skirt|pants|trouser|タイツ|スカート|ズボン/],['accessory',/accessor|ring|necklace|bracelet|earring|眼鏡|指輪|首飾り|アクセ/]])if(pattern.test(n))return kind;return 'body';}
const wardrobeState={nodes:new Map(),garments:new Map(),hash:'',sequence:0,preview:null,revision:0};
const wardrobeRoles={body:'身体',underwear:'下着（無装備でも表示）',fixed:'顔・髪など常時表示',garment:'着脱する衣服'};
function wardrobeEquipmentGroup(g){if(g.equipment_group)return g.equipment_group;const n=g.name.toLowerCase();if(/boot|shoe|loafer|sandal|靴|ブーツ|サンダル/.test(n))return 'feet';if(/glove|gauntlet|手袋|籠手/.test(n))return 'hands';if(/accessor|ring|necklace|bracelet|earring|backpack|cloak|cape|眼鏡|指輪|首飾り|アクセ|リュック|マント|ケープ/.test(n))return 'accessory';return 'body';}
function garmentDefaults(id,name,slot=53){return {id,name,nodes:[],slot,armor_type:'clothing',armor_rating:0,weight:0,value:0,equipped:true,equipment_group:wardrobeEquipmentGroup({name}),item_kind:wardrobeItemKind({name})};}
function wardrobeLoad(source,settings=null){
  wardrobeState.nodes.clear();wardrobeState.garments.clear();wardrobeState.sequence=0;
  wardrobeState.revision++;
  if(!source){renderWardrobe();return;}
  const imported=settings?.armor_support&&settings.appearance_parts?.garments;
  wardrobeState.hash=imported?settings.appearance_source_sha256:source.sha256;
  if(imported){
    for(const g of settings.appearance_parts.garments)wardrobeState.garments.set(g.id,{...g,nodes:[...g.nodes]});
    for(const role of ['body','underwear','fixed'])for(const node of settings.appearance_parts[role]||[])wardrobeState.nodes.set(node,{role,group:''});
    for(const g of settings.appearance_parts.garments)for(const node of g.nodes)wardrobeState.nodes.set(node,{role:'garment',group:g.id});
  }else{
    wardrobeState.garments.set('outfit',garmentDefaults('outfit','元の衣装'));
    for(const p of source.parts)wardrobeState.nodes.set(p.node,{role:p.suggested_role,group:p.suggested_role==='garment'?'outfit':''});
  }
  $('wardrobe-preview-images').replaceChildren();$('wardrobe-preview-status').textContent='';renderWardrobe();
}
function wardrobeCollect(){
  const parts={body:[],underwear:[],fixed:[],garments:[]};
  for(const [node,p]of wardrobeState.nodes)if(p.role!=='garment')parts[p.role].push(node);
  for(const [id,g]of wardrobeState.garments){const nodes=[...wardrobeState.nodes].filter(([,p])=>p.role==='garment'&&p.group===id).map(([node])=>node);if(nodes.length)parts.garments.push({...g,nodes});}
  return {appearance_parts:parts,appearance_source_sha256:wardrobeState.hash};
}
function wardrobeClearPreview(){
  wardrobeState.revision++;
  $('wardrobe-preview-images').replaceChildren();$('wardrobe-preview-status').textContent='分類を変更しました。確認画像を更新してください。';
}
function renderWardrobe(){
  $('wardrobe-editor').hidden=$('armor_support').value!=='true'||!state.source;
  const target=$('wardrobe-parts');target.replaceChildren();
  if(!state.source)return;
  $('wardrobe-warning').textContent=wardrobeState.hash!==state.source.sha256?'保存した分類は別VRM用です。「分類候補へ戻す」でこのモデルを分類してください。':'';
  for(const p of state.source.parts){
    const selection=wardrobeState.nodes.get(p.node)||{role:'fixed',group:''};const row=document.createElement('div');row.className='wardrobe-part';row.dataset.node=p.node;
    const label=document.createElement('div');const name=document.createElement('strong');name.textContent=p.name;const info=document.createElement('small');info.textContent=`${p.triangles.toLocaleString()}三角形 · ${p.materials.join(', ')}`;label.append(name,info);
    const role=document.createElement('select');role.setAttribute('aria-label',p.name+'の分類');for(const [key,value]of Object.entries(wardrobeRoles))role.add(new Option(value,key));role.value=selection.role;
    const group=document.createElement('select');group.setAttribute('aria-label',p.name+'の装備グループ');for(const [id,g]of wardrobeState.garments)group.add(new Option(g.name,id));group.value=selection.group;group.disabled=selection.role!=='garment';
    role.onchange=()=>{wardrobeState.nodes.set(p.node,{role:role.value,group:role.value==='garment'?(selection.group||wardrobeState.garments.keys().next().value):''});wardrobeClearPreview();renderWardrobe();};
    group.onchange=()=>{wardrobeState.nodes.set(p.node,{role:'garment',group:group.value});wardrobeClearPreview();renderWardrobe();};row.append(label,role,group);target.append(row);
  }
  const garments=$('wardrobe-garments'),openIds=new Set([...garments.querySelectorAll('details[open]')].map(d=>d.dataset.garment));garments.replaceChildren();
  for(const [id,g]of wardrobeState.garments){
    const box=document.createElement('details');box.className='wardrobe-item';box.dataset.garment=id;box.open=openIds.has(id);
    const count=[...wardrobeState.nodes.values()].filter(p=>p.role==='garment'&&p.group===id).length;
    const title=document.createElement('summary');title.textContent=`${g.name} · ${count}メッシュ${count?'':'（未使用）'}`;box.append(title);
    const grid=document.createElement('div');grid.className='grid three';
    for(const [key,caption]of [['name','装備名'],['item_kind','部位・用途'],['slot','占有する装備枠'],['equipment_group','鎧との切替'],['armor_type','防具の分類'],['armor_rating','防御力'],['weight','重量'],['value','価値'],['equipped','初期装備']]){
      const label=document.createElement('label');label.textContent=caption;let input;
      if(['slot','armor_type','equipment_group','item_kind'].includes(key)){input=document.createElement('select');const entries=key==='slot'?wardrobeSlots.map(s=>[s,wardrobeSlotLabel(s)]):key==='item_kind'?Object.entries(wardrobeKinds):key==='equipment_group'?[['body','胴の鎧を優先して外す'],['hands','手袋を優先して外す'],['feet','靴を優先して外す'],['accessory','防具と併用']]:[['clothing','衣服（防具ではない）'],['light','軽装'],['heavy','重装']];for(const [v,text]of entries)input.add(new Option(text,v));input.value=key==='equipment_group'?wardrobeEquipmentGroup(g):key==='item_kind'?wardrobeItemKind(g):g[key];}
      else {input=document.createElement('input');input.type=key==='name'?'text':key==='equipped'?'checkbox':'number';if(key==='equipped'){input.checked=g[key];label.className='checkbox';}else{input.value=g[key];if(key==='name')input.maxLength=128;else{input.min=0;input.max=key==='value'?2147483647:key==='weight'?1000:10000;input.step=key==='value'?1:.1;}}}
      input.dataset.field=key;input.setAttribute('aria-label',g.name+' '+caption);
      input.onchange=()=>{g[key]=key==='equipped'?input.checked:['name','armor_type','equipment_group','item_kind'].includes(key)?input.value:Number(input.value);wardrobeClearPreview();if(key==='name')renderWardrobe();};label.append(input);grid.append(label);
    }box.append(grid);const help=document.createElement('p');help.className='hint';help.textContent='部位・用途はゲーム内の衣服判定に使います。SkyUIのアイコン・種類名は主に装備枠で決まり、UI MODによって表示が異なります。46・47はマント／バッグ向け。普通の服は他の重ね着枠を選んでください。防具と併用を選ぶと重ね着できますが、形によっては重なります。元衣装に戻すときは対応する鎧・手袋・靴を先に外してください。';box.append(help);garments.append(box);
  }
  const preview=$('wardrobe-preview-state'), previous=preview.value;preview.replaceChildren(new Option('全ての服を着る','all'),new Option('服を外す（身体と下着）','underwear'));
  for(const g of wardrobeCollect().appearance_parts.garments)preview.add(new Option(g.name+'だけ外す','without:'+g.id));preview.value=[...preview.options].some(o=>o.value===previous)?previous:'all';
}
async function wardrobePreview(){
  const revision=wardrobeState.revision;
  error();$('wardrobe-preview').disabled=true;$('wardrobe-preview-images').replaceChildren();$('wardrobe-preview-status').textContent='原VRMの分類結果を描画しています…';
  try{
    const result=await api('/api/appearance-preview',{source_id:state.source.source_id,blender:$('blender').value,settings:collect(),wardrobe:$('wardrobe-preview-state').value});wardrobeState.preview=result.job_id;
    for(;;){const job=await api('/api/jobs/'+result.job_id);if(job.status==='failed')throw new Error(job.error);if(job.status==='complete'){if(revision!==wardrobeState.revision){$('wardrobe-preview-status').textContent='描画中に分類を変更しました。プレビューを更新してください。';break;}for(const path of job.previews){const figure=document.createElement('figure'),img=document.createElement('img'),caption=document.createElement('figcaption');img.src=fileURL(job.id,path);img.alt='原VRMの分類プレビュー';caption.textContent='原VRMの分類確認（変換前）';figure.append(img,caption);$('wardrobe-preview-images').append(figure);}$('wardrobe-preview-status').textContent='身体・下着・服の分類を確認してください。出力NIFの検査画像は変換完了後に表示します。';break;}await new Promise(resolve=>setTimeout(resolve,1000));}
  }catch(e){error(e.message);$('wardrobe-preview-status').textContent='プレビューを作成できませんでした';}finally{$('wardrobe-preview').disabled=false;}
}
function initWardrobe(){
  $('armor_support').onchange=renderWardrobe;
  $('wardrobe-reset').onclick=()=>wardrobeLoad(state.source);
  $('wardrobe-add').onclick=()=>{let id;do{id='item_'+(++wardrobeState.sequence);}while(wardrobeState.garments.has(id));const slot=wardrobeSlots[wardrobeState.garments.size%wardrobeSlots.length];wardrobeState.garments.set(id,garmentDefaults(id,'衣服'+wardrobeState.sequence,slot));renderWardrobe();};
  $('wardrobe-combine').onclick=()=>{wardrobeState.garments.clear();wardrobeState.garments.set('outfit',garmentDefaults('outfit','元の衣装'));for(const p of wardrobeState.nodes.values())if(p.role==='garment')p.group='outfit';wardrobeClearPreview();renderWardrobe();};
  $('wardrobe-split').onclick=()=>{const cloth=[...wardrobeState.nodes].filter(([,p])=>p.role==='garment');if(cloth.length>wardrobeSlots.length){error(`${wardrobeSlots.length}品以内になるよう衣服をまとめてください`);return;}wardrobeState.garments.clear();cloth.forEach(([node,p],i)=>{const id='part_'+node;p.group=id;wardrobeState.garments.set(id,garmentDefaults(id,state.source.parts.find(p=>p.node===node).name,wardrobeSlots[i]));});wardrobeClearPreview();renderWardrobe();};
  $('wardrobe-preview-state').onchange=wardrobeClearPreview;$('wardrobe-preview').onclick=wardrobePreview;
}
