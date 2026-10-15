/* Actual style editor controls with read-only catalog fixtures; no game writes. */
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),fixture=path.join(root,'build/ui-roles');
const defaults=JSON.parse(fs.readFileSync(path.join(fixture,'defaults.json'),'utf8'));
const choices=JSON.parse(fs.readFileSync(path.join(fixture,'roles.json'),'utf8'));
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  const page=await browser.newPage({locale:'ja-JP',acceptDownloads:true,viewport:{width:1440,height:1100}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url());let data;
   if(url.pathname==='/api/environment')data={defaults,game:'Read-only fixture',blender:'Fixture Blender',version:'test'};
   else if(url.pathname==='/api/jobs')data={jobs:[]};
   else if(url.pathname==='/api/source')data={source_id:'fixture',sha256:'fixture',filename:'fixture.vrm',mesh_count:1,triangles:1,suggested_name:'Test',parts:[]};
   else if(url.pathname==='/api/catalog')data={checks:{ready:true},choices:{...choices,armors:[],equipment_plugins:[]}};
   else if(url.pathname==='/api/validate')data={settings:request.postDataJSON().settings};
   if(data!==undefined)return route.fulfill({json:data});
   const name=url.pathname==='/'?'index.html':url.pathname.slice(1),file=path.join(root,'web',name);
   if(!fs.existsSync(file))return route.fulfill({status:404,body:'not found'});
   return route.fulfill({body:fs.readFileSync(file),contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html'});
  });
  async function start(imported){
   await page.goto('http://127.0.0.1:8899/');
   await page.waitForFunction(()=>document.querySelector('#game').value.length>0);
   if(imported){await page.locator('#import-settings').setInputFiles({name:'style.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(imported))});await page.waitForFunction(()=>document.querySelector('#import-status').textContent.length>0);}
   await page.locator('#source').setInputFiles({name:'fixture.vrm',mimeType:'application/octet-stream',buffer:Buffer.from('fixture')});
   await page.waitForFunction(()=>document.querySelector('#source-status').textContent.includes('fixture.vrm'));
   for(let step=1;step<=2;step++){await page.locator('#next').click();await page.locator(`[data-step="${step}"]`).waitFor({state:'visible'});}
  }
  await start();
  assert.equal(await page.locator('#combat_style_mode').inputValue(),'existing');
  await page.locator('#preset').selectOption('mage');
  await page.locator('#combat_style_mode').selectOption('custom');
  await page.locator('#combat-style-editor').waitFor({state:'visible'});
  assert.equal(await page.locator('[data-combat-field]').count(),31);
  assert.equal(await page.locator('#combat-dual-wield').isChecked(),false);
  assert.equal(await page.locator('#combat-special_attack').inputValue(),'');
  await page.locator('#combat-magic_score').fill('6.25');
  await page.locator('#combat-dual-wield').check();
  await page.locator('[data-combat-section="close"] summary').click();
  await page.locator('#combat-close-strategy').selectOption('2');
  await page.locator('[data-combat-section="melee"] summary').click();
  await page.locator('#combat-special_attack').fill('0.35');
  await page.locator('[data-combat-field="special_attack"] button').click();
  assert.equal(await page.locator('#combat-special_attack').inputValue(),'');
  await page.locator('#language').selectOption('en');
  assert.equal(await page.locator('#weapon').inputValue(),'');
  assert.equal(await page.locator('#combat-magic_score').inputValue(),'6.25');
  assert.equal(await page.locator('#combat-dual-wield').isChecked(),true);
  assert.match(await page.locator('[data-combat-field="magic_score"] label').textContent(),/Equipment Score Mult - Magic/);
  assert.match(await page.locator('#copy-combat-style').textContent(),/Copy selected/);
  await page.locator('#language').selectOption('ja');
  // Selecting a different template cannot destroy edits; explicit Copy confirms.
  await page.locator('#combat_style').selectOption('csHumanMeleeLvl1');
  assert.equal(await page.locator('#combat-magic_score').inputValue(),'6.25');
  page.once('dialog',dialog=>dialog.dismiss());await page.locator('#copy-combat-style').click();
  assert.equal(await page.locator('#combat-magic_score').inputValue(),'6.25');
  await page.screenshot({path:path.join(fixture,'combat-style-desktop.png'),fullPage:true});
  await page.locator('.combat-style-panel').screenshot({path:path.join(fixture,'combat-style-editor.png')});
  for(let step=3;step<=4;step++){await page.locator('#next').click();await page.locator(`[data-step="${step}"]`).waitFor({state:'visible'});}
  assert.match(await page.locator('#summary').textContent(),/csHumanMagic/);
  const pending=page.waitForEvent('download');await page.locator('#export-settings').click();
  const downloaded=await pending,saved=JSON.parse(fs.readFileSync(await downloaded.path(),'utf8'));
  assert.equal(saved.combat_style_mode,'custom');
  assert.equal(saved.combat_style,'csHumanMeleeLvl1');
  assert.equal(saved.combat_style_custom.source,'csHumanMagic');
  assert.equal(saved.combat_style_custom.values.magic_score,6.25);
  assert.equal(saved.combat_style_custom.flags,6);
  assert.equal(Object.hasOwn(saved.combat_style_custom.values,'special_attack'),false);
  await start(saved); // JSON loaded before catalog; no implicit source copy.
  assert.equal(await page.locator('#combat-magic_score').inputValue(),'6.25');
  assert.equal(await page.locator('#combat-dual-wield').isChecked(),true);
  await page.locator('#combat_style').selectOption('csAlikrBerserker');
  page.once('dialog',dialog=>dialog.accept());await page.locator('#copy-combat-style').click();
  assert.match(await page.locator('#combat-style-source').textContent(),/csAlikrBerserker/);
  await page.locator('#combat-magic_score').fill('2');
  await page.locator('[data-combat-field="magic_score"] button').click();
  assert.equal(await page.locator('#combat-magic_score').inputValue(),'1');
  await page.locator('#combat-magic_score').fill('3');
  page.once('dialog',dialog=>dialog.accept());await page.locator('#reset-combat-style').click();
  assert.equal(await page.locator('#combat-magic_score').inputValue(),'1');
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(fixture,'combat-style-mobile.png'),fullPage:true});
  const legacy={...defaults};delete legacy.combat_style_mode;delete legacy.combat_style_custom;
  await start(legacy);
  assert.equal(await page.locator('#combat_style_mode').inputValue(),'existing');
  assert.deepEqual(errors,[]);
  console.log('PASS: 31 controls, explicit copy/cancel, edits, omitted fields, resets, JA/EN, JSON before catalog, private source snapshot, review and mobile layout');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
