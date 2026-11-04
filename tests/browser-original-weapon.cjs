/* Original weapon cards with read-only catalog fixtures and a mocked wizard API; no game writes. */
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),fixture=path.join(root,'build/ui-roles');
const defaults=JSON.parse(fs.readFileSync(path.join(fixture,'defaults.json'),'utf8'));
const choices=JSON.parse(fs.readFileSync(path.join(fixture,'roles.json'),'utf8'));
const staff='a'.repeat(64),other='b'.repeat(64);
const glbs={'crescent-staff.glb':{weapon_id:'w-staff',sha256:staff,triangles:19999,vertices:25540},
  'other.glb':{weapon_id:'w-other',sha256:other,triangles:900,vertices:700}};
const dimensions={SteelSword:{length:82,grip:.144},StaffFlames:{length:134,grip:.519},SteelGreatsword:{length:114.1,grip:.185}};
// Fixed stats and enchantments so the cards do not depend on the fixture's catalog version.
const steelStats={damage:8,weight:10,value:45,speed:1,reach:1};
const enchantments=[{id:'EnchWeaponFireDamage02',label:'炎ダメージ',labels:{ja:'炎ダメージ',en:'Fire Damage'},charge:1000}];
const keep={stats:{},enchantment:'keep'};
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==','base64');
(async()=>{
 assert.ok(choices.original_weapons,'Regenerate fixtures: python tests/browser-roles-fixture.py');
 const staffBases=choices.original_weapons.find(k=>k.id==='staff').candidates.map(c=>c.id);
 const otherStaff=staffBases.find(id=>id!=='StaffFlames');
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  const page=await browser.newPage({locale:'ja-JP',acceptDownloads:true,viewport:{width:1440,height:1100}});
  const errors=[],requests={validate:[],jobs:[],preview:[],bases:[]};page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url());let data,status=200;
   const body=request.method()==='POST'&&request.headers()['content-type']==='application/json'?request.postDataJSON():null;
   if(url.pathname==='/api/environment')data={defaults,game:'Read-only fixture',blender:'Fixture Blender',version:'test'};
   else if(url.pathname==='/api/jobs'&&request.method()==='GET')data={jobs:[]};
   else if(url.pathname==='/api/source')data={source_id:'fixture',sha256:'fixture',filename:'fixture.vrm',mesh_count:1,triangles:1,suggested_name:'Test',parts:[]};
   else if(url.pathname==='/api/catalog'){
    const weapons=structuredClone(choices.original_weapons);
    for(const kind of weapons)for(const item of kind.candidates){item.stats=item.id==='SteelSword'?steelStats:item.stats;item.enchantment=item.enchantment??null;}
    data={checks:{ready:true},choices:{...choices,original_weapons:weapons,weapon_enchantments:enchantments,armors:[],equipment_plugins:[]}};
   }
   else if(url.pathname==='/api/weapon-glb'){const name=decodeURIComponent(request.headers()['x-filename']);data={...glbs[name],filename:name,materials:1,extensions:[]};}
   else if(url.pathname==='/api/weapon-base'){requests.bases.push(body.base);const d=dimensions[body.base]||{length:120.7,grip:.44};data={base:body.base,kind:'',model:'',...d};}
   else if(url.pathname==='/api/validate'){
    requests.validate.push(body);const s=body.settings;
    // The server refuses original-weapon settings without the matching uploaded GLB (STEP 03 onward).
    const missing=s.original_weapons.findIndex((w,i)=>Object.values(glbs).find(g=>g.weapon_id===(body.weapon_ids||[])[i])?.sha256!==w.sha256);
    if(body.check_weapon!==false&&s.weapon_mode==='original'&&missing>=0){status=400;data={error:`オリジナル武器 ${missing+1} のGLBを選んでください`};}
    else data={settings:s};
   }
   else if(url.pathname==='/api/weapon-preview'){requests.preview.push(body);status=202;data={job_id:'preview1'};}
   else if(url.pathname==='/api/jobs/preview1')data={id:'preview1',kind:'weapon_preview',status:'complete',stage:'武器のプレビューを更新しました',
    previews:['previews/weapon-x-drawn.png','previews/weapon-x-hand.png','previews/weapon-x-sheathed.png','previews/weapon-x-compare.png'],views:['drawn','hand','sheathed','compare']};
   else if(url.pathname.startsWith('/api/jobs/preview1/file'))return route.fulfill({body:png,contentType:'image/png'});
   else if(url.pathname==='/api/jobs'&&request.method()==='POST'){requests.jobs.push(body);status=400;data={error:'fixture stops before conversion'};}
   if(data!==undefined)return route.fulfill({status,json:data});
   const name=url.pathname==='/'?'index.html':url.pathname.slice(1),file=path.join(root,'web',name);
   if(!fs.existsSync(file))return route.fulfill({status:404,body:'not found'});
   return route.fulfill({body:fs.readFileSync(file),contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html'});
  });
  async function start(imported){
   await page.goto('http://127.0.0.1:8899/');
   await page.waitForFunction(()=>document.querySelector('#game').value.length>0);
   if(imported){await page.locator('#import-settings').setInputFiles({name:'weapon.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(imported))});await page.waitForFunction(()=>document.querySelector('#import-status').textContent.length>0);}
   await page.locator('#source').setInputFiles({name:'fixture.vrm',mimeType:'application/octet-stream',buffer:Buffer.from('fixture')});
   await page.waitForFunction(()=>document.querySelector('#source-status').textContent.includes('fixture.vrm'));
   for(let step=1;step<=2;step++){await page.locator('#next').click();await page.locator(`[data-step="${step}"]`).waitFor({state:'visible'});}
  }
  const value=id=>page.locator('#'+id).inputValue();
  // Card n (0-based) and its controls; weapon.js builds the cards, so they carry data-role, not IDs.
  const card=n=>page.locator('[data-weapon-card]').nth(n);
  const role=(name,n=0)=>card(n).locator(`[data-role="${name}"]`);
  const field=(name,n=0)=>role(name,n).inputValue();
  const text=(name,n=0)=>role(name,n).textContent();
  const waitText=(name,pattern,n=0)=>page.waitForFunction(([name,pattern,n])=>new RegExp(pattern).test(document.querySelectorAll('[data-weapon-card]')[n]?.querySelector(`[data-role="${name}"]`)?.textContent||''),[name,pattern,n]);
  const waitValue=(name,expected,n=0)=>page.waitForFunction(([name,expected,n])=>document.querySelectorAll('[data-weapon-card]')[n]?.querySelector(`[data-role="${name}"]`)?.value===expected,[name,expected,n]);
  async function uploadGlb(name,n=0){await role('glb',n).setInputFiles({name,mimeType:'model/gltf-binary',buffer:Buffer.from('glTF fixture')});}

  await start();
  assert.equal(await value('weapon_mode'),'official');
  assert.equal(await page.locator('#original-weapon-panel').isHidden(),true);
  await page.locator('#preset').selectOption('mage');
  assert.equal(await value('weapon'),'');
  await page.locator('#weapon_mode').selectOption('original');
  assert.equal(await page.locator('#original-weapon-panel').isVisible(),true);
  assert.equal(await page.locator('#official-weapon').isHidden(),true);
  assert.equal(await role('kind').locator('option').count(),8);
  assert.equal(await field('kind'),'sword');
  assert.equal(await field('base'),'SteelSword');
  await waitValue('length','82.0');
  assert.equal(await field('grip'),'14.4');
  // A missing GLB blocks STEP 03 with a message instead of a server round trip.
  await page.locator('#next').click();
  assert.match(await page.locator('#error').textContent(),/オリジナル武器のGLBを選んでください/);
  // Dropping the GLB on its zone uploads it, as dropping a VRM does.
  const dropped=await page.evaluateHandle(()=>{const d=new DataTransfer();d.items.add(new File(['glTF fixture'],'crescent-staff.glb',{type:'model/gltf-binary'}));return d;});
  await role('drop').dispatchEvent('drop',{dataTransfer:dropped});
  await waitText('glb-status','19,999');
  assert.match(await text('glb-status'),/頂点25,540.*約9\.7倍/);
  assert.equal(await field('name'),'crescent-staff');
  await role('kind').selectOption('staff');
  assert.equal(await field('base'),'StaffFlames');
  await waitValue('length','134.0');
  assert.equal(await field('grip'),'51.9');
  assert.match(await text('base-status'),/134.*51\.9%/);
  // Edited size survives another base; the reset button takes the base's size again.
  await role('length').fill('120');
  await role('base').selectOption(otherStaff);
  await waitValue('base',otherStaff);await waitText('base-status','.');
  assert.equal(await field('length'),'120');
  assert.equal(await field('grip'),'51.9');
  await role('base').selectOption('StaffFlames');
  await role('reset-size').click();
  assert.equal(await field('length'),'134.0');
  await role('length').fill('120.5');await role('grip').fill('44');
  await role('roll').fill('90');await role('flip').check();
  await role('name').fill('三日月の杖');
  // Role presets change only the official weapon select.
  await page.locator('#preset').selectOption('twohand');
  assert.equal(await value('weapon'),'SteelGreatsword');
  assert.equal(await value('weapon_mode'),'original');
  assert.equal(await field('kind'),'staff');
  assert.equal(await field('base'),'StaffFlames');
  assert.equal(await field('length'),'120.5');
  assert.equal(await field('grip'),'44');
  // Preview: request carries the uploaded GLB id, never a path; edits mark it stale.
  await role('preview').click();
  await role('preview-images').locator('figure').nth(3).waitFor();
  const preview=requests.preview.at(-1);
  assert.deepEqual(preview.weapon_ids,['w-staff']);
  assert.deepEqual(preview.settings.original_weapons,[{sha256:staff,filename:'crescent-staff.glb',kind:'staff',base:'StaffFlames',name:'三日月の杖',grip:.44,length:120.5,flip:true,roll:90,...keep}]);
  assert.deepEqual(await role('preview-images').locator('figcaption').allTextContents(),
   ['武器を抜いて構えた姿','手元の拡大','武器を収めた姿','元の武器と同じ縮尺で比較（赤い線が握る位置）']);
  await role('roll').fill('45');
  assert.match(await text('preview-status'),/もう一度描いてください/);
  await role('roll').fill('90');
  assert.match(await text('preview-status'),/Blenderでの確認用/);
  await page.locator('#original-weapon-panel').screenshot({path:path.join(fixture,'original-weapon-ja.png')});
  // English.
  await page.locator('#language').selectOption('en');
  assert.equal(await page.locator('#weapon_mode option:checked').textContent(),'Original weapon');
  assert.equal(await role('kind').locator('option:checked').textContent(),'Staff');
  assert.match(await text('glb-status'),/19,999 triangles · 25,540 vertices \(about 9\.7 times/);
  assert.match(await text('base-status'),/134 long and is held 51\.9% from the bottom end/);
  assert.equal(await role('preview-images').locator('figcaption').first().textContent(),'Weapon drawn');
  assert.match(await page.locator('#original-weapon-panel').textContent(),/Grip position \(% from the bottom end\)/);
  assert.equal(await field('name'),'三日月の杖');
  await page.locator('#original-weapon-panel').screenshot({path:path.join(fixture,'original-weapon-en.png')});
  await page.locator('#language').selectOption('ja');
  for(let step=3;step<=4;step++){await page.locator('#next').click();await page.locator(`[data-step="${step}"]`).waitFor({state:'visible'});}
  assert.deepEqual(requests.validate.at(-1).weapon_ids,['w-staff']);
  assert.match(await page.locator('#summary').textContent(),/オリジナル武器「三日月の杖」（杖、元: StaffFlames、crescent-staff\.glb）/);
  const pending=page.waitForEvent('download');await page.locator('#export-settings').click();
  const exported=JSON.parse(fs.readFileSync(await (await pending).path(),'utf8'));
  assert.equal(exported.weapon_mode,'original');
  assert.equal(exported.weapon,'SteelGreatsword');
  assert.deepEqual(exported.original_weapons,preview.settings.original_weapons);
  assert.ok(!JSON.stringify(exported).includes('inputs'),'settings must not contain the GLB location');
  await page.locator('#create').click();
  await page.waitForFunction(()=>!document.querySelector('#error').hidden);
  assert.deepEqual(requests.jobs.at(-1).weapon_ids,['w-staff']);
  assert.deepEqual(requests.jobs.at(-1).settings.original_weapons,exported.original_weapons);

  // Import in a fresh page: the GLB must be chosen again and a different file is refused.
  await start(exported);
  assert.equal(requests.validate.filter(r=>r.check_weapon===false).length>=2,true);
  assert.equal(await value('weapon_mode'),'original');
  assert.equal(await field('kind'),'staff');
  assert.equal(await field('base'),'StaffFlames');
  assert.equal(await field('length'),'120.5');
  assert.equal(await field('grip'),'44');
  assert.equal(await field('roll'),'90');
  assert.equal(await role('flip').isChecked(),true);
  assert.equal(await field('name'),'三日月の杖');
  assert.match(await text('glb-status'),/設定に保存したGLB「crescent-staff\.glb」を選び直してください/);
  await page.locator('#next').click();
  await page.waitForFunction(()=>!document.querySelector('#error').hidden);
  assert.match(await page.locator('#error').textContent(),/オリジナル武器のGLBを選んでください/);
  await uploadGlb('other.glb');
  await role('mismatch').waitFor({state:'visible'});
  assert.match(await text('mismatch-text'),/「other\.glb」は、設定に保存したオリジナル武器のGLB「crescent-staff\.glb」と別のファイル/);
  await page.locator('#language').selectOption('en');
  assert.match(await text('mismatch-text'),/other\.glb cannot be used because it is a different file/);
  await page.locator('#language').selectOption('ja');
  await uploadGlb('crescent-staff.glb');
  await waitText('glb-status','19,999');
  assert.equal(await role('mismatch').isHidden(),true);
  // Imported size values are kept; the base measurement does not overwrite them.
  assert.equal(await field('length'),'120.5');
  await page.locator('#next').click();await page.locator('[data-step="3"]').waitFor({state:'visible'});
  assert.deepEqual(requests.validate.at(-1).weapon_ids,['w-staff']);
  // Official mode keeps the imported original weapon for switching back.
  await page.locator('#back').click();await page.locator('#weapon_mode').selectOption('official');
  assert.equal(await page.locator('#official-weapon').isVisible(),true);
  await page.locator('#next').click();await page.locator('[data-step="3"]').waitFor({state:'visible'});
  assert.equal(requests.validate.at(-1).settings.weapon_mode,'official');
  assert.deepEqual(requests.validate.at(-1).settings.original_weapons,exported.original_weapons);
  await page.setViewportSize({width:390,height:844});
  await page.locator('#back').click();await page.locator('#weapon_mode').selectOption('original');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.locator('#original-weapon-panel').screenshot({path:path.join(fixture,'original-weapon-mobile.png')});
  await page.setViewportSize({width:1440,height:1100});
  // STEP 01/02 do not require the original weapon, which is completed in STEP 03.
  await start();
  await page.locator('#weapon_mode').selectOption('original');
  for(let step=1;step>=0;step--){await page.locator('#back').click();await page.locator(`[data-step="${step}"]`).waitFor({state:'visible'});}
  await page.locator('#next').click();await page.locator('[data-step="1"]').waitFor({state:'visible'});
  assert.equal(await page.locator('#error').isHidden(),true);
  assert.deepEqual([requests.validate.at(-1).settings.weapon_mode,requests.validate.at(-1).check_weapon],['official',false]);
  await page.locator('#next').click();await page.locator('[data-step="2"]').waitFor({state:'visible'});
  assert.equal(await value('weapon_mode'),'original');
  await page.locator('#next').click();
  assert.match(await page.locator('#error').textContent(),/オリジナル武器のGLBを選んでください/);
  // Imported values finer than a 0.1 step stay valid; forgetting the saved GLB clears the shown file.
  const fine={...exported,original_weapons:[{...exported.original_weapons[0],grip:.44123,length:120.55,roll:12.5}]};
  await start(fine);
  assert.deepEqual([await field('grip'),await field('length'),await field('roll')],['44.123','120.55','12.5']);
  await uploadGlb('crescent-staff.glb');
  await waitText('glb-status','19,999');
  await uploadGlb('other.glb');
  await role('mismatch').waitFor({state:'visible'});
  const chooser=page.waitForEvent('filechooser');
  await role('forget').click();await chooser;
  assert.equal(await text('glb-status'),'まだ選択されていません');
  assert.equal(await role('mismatch').isHidden(),true);
  assert.equal(await role('glb').evaluate(input=>input.files.length),0);
  for(let step=1;step>=0;step--){await page.locator('#back').click();await page.locator(`[data-step="${step}"]`).waitFor({state:'visible'});}
  for(let step=1;step<=2;step++){await page.locator('#next').click();await page.locator(`[data-step="${step}"]`).waitFor({state:'visible'});}
  assert.equal(await page.locator('#error').isHidden(),true);
  await uploadGlb('other.glb');
  await waitText('glb-status','other\\.glb');
  await page.locator('#next').click();await page.locator('[data-step="3"]').waitFor({state:'visible'});
  assert.deepEqual(requests.validate.at(-1).settings.original_weapons,[{...fine.original_weapons[0],sha256:other,filename:'other.glb'}]);
  // The drawn preview goes stale when an appearance input it was drawn with changes in STEP 02.
  await page.locator('#back').click();await page.locator('[data-step="2"]').waitFor({state:'visible'});
  await role('preview').click();
  await role('preview-images').locator('figure').nth(3).waitFor();
  assert.match(await text('preview-status'),/Blenderでの確認用/);
  await page.locator('#back').click();await page.locator('[data-step="1"]').waitFor({state:'visible'});
  await page.locator('#sex').selectOption('male');
  await page.locator('#next').click();await page.locator('[data-step="2"]').waitFor({state:'visible'});
  assert.match(await text('preview-status'),/もう一度描いてください/);
  // Several weapons: a staff and a sword with its own GLB, stats and enchantment.
  await start(exported);
  assert.equal(await page.locator('[data-weapon-card]').count(),1);
  assert.equal(await role('remove').isDisabled(),true);
  assert.equal(await role('enchantment-field').isHidden(),true);  // a staff keeps its base staff's spell
  assert.equal(await role('staff-note').isVisible(),true);
  await uploadGlb('crescent-staff.glb');await waitText('glb-status','19,999');
  await page.locator('#add-weapon').click();
  assert.equal(await page.locator('[data-weapon-card]').count(),2);
  assert.equal(await card(1).locator('h4').first().textContent(),'オリジナル武器 2');
  assert.deepEqual([await field('kind',1),await field('base',1)],['sword','SteelSword']);
  await waitValue('length','82.0',1);
  assert.equal(await role('stat-damage',1).getAttribute('placeholder'),'8');
  assert.equal(await role('stat-weight',1).getAttribute('placeholder'),'10');
  assert.equal(await role('enchantment-field',1).isVisible(),true);
  assert.deepEqual(await role('enchantment',1).locator('option').evaluateAll(o=>o.map(x=>x.value)),['keep','none','EnchWeaponFireDamage02']);
  // The first card keeps what was typed and uploaded there.
  assert.deepEqual([await field('name'),await field('length')],['三日月の杖','120.5']);
  await waitText('glb-status','19,999');
  await page.locator('#next').click();
  assert.match(await page.locator('#error').textContent(),/オリジナル武器 2: オリジナル武器のGLBを選んでください/);
  await uploadGlb('other.glb',1);await waitText('glb-status','900',1);
  assert.equal(await field('name',1),'other');
  await role('stat-damage',1).fill('8.5');
  await page.locator('#next').click();
  assert.match(await page.locator('#error').textContent(),/オリジナル武器 2: 攻撃力は0〜65535の整数で指定してください/);
  await role('stat-damage',1).fill('12');await role('stat-speed',1).fill('1.3');
  await role('enchantment',1).selectOption('EnchWeaponFireDamage02');
  await page.locator('#language').selectOption('en');
  assert.equal(await role('stat-damage',1).inputValue(),'12');
  assert.equal(await role('enchantment',1).locator('option:checked').textContent(),'Fire Damage (EnchWeaponFireDamage02)');
  assert.match(await card(1).textContent(),/Stats and enchantment/);
  await page.locator('#language').selectOption('ja');
  for(let step=3;step<=4;step++){await page.locator('#next').click();await page.locator(`[data-step="${step}"]`).waitFor({state:'visible'});}
  assert.deepEqual(requests.validate.at(-1).weapon_ids,['w-staff','w-other']);
  const two=requests.validate.at(-1).settings.original_weapons;
  assert.deepEqual(two[0],exported.original_weapons[0]);
  assert.deepEqual(two[1],{sha256:other,filename:'other.glb',kind:'sword',base:'SteelSword',name:'other',grip:.144,length:82,
   flip:false,roll:0,stats:{damage:12,speed:1.3},enchantment:'EnchWeaponFireDamage02'});
  assert.match(await page.locator('#summary').textContent(),/オリジナル武器「三日月の杖」.*、オリジナル武器「other」（片手剣、元: SteelSword、other\.glb）/);
  const twoPending=page.waitForEvent('download');await page.locator('#export-settings').click();
  const twoExported=JSON.parse(fs.readFileSync(await (await twoPending).path(),'utf8'));
  assert.deepEqual(twoExported.original_weapons,two);
  // A reimport restores both cards with their stats and enchantment.
  await start(twoExported);
  assert.equal(await page.locator('[data-weapon-card]').count(),2);
  assert.deepEqual([await field('stat-damage',1),await field('stat-speed',1),await field('stat-weight',1),await field('enchantment',1)],
   ['12','1.3','','EnchWeaponFireDamage02']);
  await role('reset-stats',1).click();
  assert.deepEqual([await field('stat-damage',1),await field('enchantment',1)],['','keep']);
  await role('remove',1).click();
  assert.equal(await page.locator('[data-weapon-card]').count(),1);
  for(let i=1;i<8;i++)await page.locator('#add-weapon').click();
  assert.equal(await page.locator('[data-weapon-card]').count(),8);
  assert.equal(await page.locator('#add-weapon').isDisabled(),true);
  // Settings saved with one original_weapon object load as the first card.
  const single={...exported,original_weapon:{...exported.original_weapons[0]}};delete single.original_weapons;delete single.original_weapon.stats;delete single.original_weapon.enchantment;
  await start(single);
  assert.equal(await page.locator('[data-weapon-card]').count(),1);
  assert.deepEqual([await field('name'),await field('length'),await field('kind')],['三日月の杖','120.5','staff']);
  // Older settings without weapon fields load as the official weapon.
  const legacy={...defaults};delete legacy.weapon_mode;delete legacy.original_weapons;
  await start(legacy);
  assert.equal(await value('weapon_mode'),'official');
  assert.equal(await page.locator('#original-weapon-panel').isHidden(),true);
  assert.deepEqual(errors,[]);
  console.log('PASS: mode switch, GLB counts, kind/base defaults, base size fill and edits, preset preservation, preview, JA/EN, review, export/import, GLB re-selection and mismatch refusal, mobile layout, STEP 01 without the weapon, fine imported values, forgetting the saved GLB, stale preview after an appearance change, two weapon cards with stats/enchantment/export/import, card limit, single-weapon settings');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
