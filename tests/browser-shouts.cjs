/* STEP 04 shouts with read-only catalog fixtures (tests/browser-roles-fixture.py); no game writes. */
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),fixture=path.join(root,'build/ui-roles');
const defaults=JSON.parse(fs.readFileSync(path.join(fixture,'defaults.json'),'utf8'));
const choices=JSON.parse(fs.readFileSync(path.join(fixture,'roles.json'),'utf8'));
const CYCLONE='Dragonborn.esm:0200C0',FORCE='Skyrim.esm:013E07';
(async()=>{
 assert.equal(choices.shouts?.length,27,'Regenerate the fixture: python tests/browser-roles-fixture.py');
 const cyclone=choices.shouts.find(item=>item.id===CYCLONE),force=choices.shouts.find(item=>item.id===FORCE);
 const zeroStyle=choices.styles.find(item=>item.config?.values?.shout_score===0)?.id;assert.ok(zeroStyle);
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  const page=await browser.newPage({locale:'ja-JP',acceptDownloads:true,viewport:{width:1440,height:1100}});
  const errors=[],validated=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url());let data;
   if(url.pathname==='/api/environment')data={defaults,game:'Read-only fixture',blender:'Fixture Blender',version:'test'};
   else if(url.pathname==='/api/jobs')data={jobs:[]};
   else if(url.pathname==='/api/source')data={source_id:'fixture',sha256:'fixture',filename:'fixture.vrm',mesh_count:1,triangles:1,suggested_name:'Test',parts:[]};
   else if(url.pathname==='/api/catalog')data={checks:{ready:true},choices:{...choices,armors:[],equipment_plugins:[]}};
   else if(url.pathname==='/api/validate'){const settings=request.postDataJSON().settings;validated.push(settings);data={settings};}
   if(data!==undefined)return route.fulfill({json:data});
   const name=url.pathname==='/'?'index.html':url.pathname.slice(1),file=path.join(root,'web',name);
   if(!fs.existsSync(file))return route.fulfill({status:404,body:'not found'});
   return route.fulfill({body:fs.readFileSync(file),contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html'});
  });
  async function to(step){
   for(let current=await page.evaluate(()=>state.step);current<step;current++){await page.locator('#next').click();await page.locator(`[data-step="${current+1}"]`).waitFor({state:'visible'});}
   for(let current=await page.evaluate(()=>state.step);current>step;current--){await page.locator('#back').click();await page.locator(`[data-step="${current-1}"]`).waitFor({state:'visible'});}
  }
  async function start(imported){
   await page.goto('http://127.0.0.1:8899/');
   await page.waitForFunction(()=>document.querySelector('#game').value.length>0);
   if(imported){await page.locator('#import-settings').setInputFiles({name:'shouts.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(imported))});await page.waitForFunction(()=>document.querySelector('#import-status').textContent.length>0);}
   await page.locator('#source').setInputFiles({name:'fixture.vrm',mimeType:'application/octet-stream',buffer:Buffer.from('fixture')});
   await page.waitForFunction(()=>document.querySelector('#source-status').textContent.includes('fixture.vrm'));
  }
  const row=id=>page.locator('#shouts label.choice').filter({has:page.locator(`input[data-record-id="${id}"]`)});
  const checked=async()=>page.$$eval('#shouts input:checked',inputs=>inputs.map(input=>input.dataset.recordId));
  await start();
  await to(2);await page.locator('#preset').selectOption('mage');
  await to(3);
  assert.equal(await page.locator('#shouts label.choice').count(),27);
  assert.equal(await row(CYCLONE).locator('strong').textContent(),cyclone.labels.ja);
  assert.equal(await row(CYCLONE).locator('.dlc').textContent(),'Dragonborn が必要');
  assert.match(await row(CYCLONE).locator('small').textContent(),new RegExp('DLC2CycloneShout · '+cyclone.descriptions.ja.slice(0,8)));
  assert.equal(await row(FORCE).locator('.dlc').count(),0);
  assert.equal(await page.locator('#shouts .dlc').count(),7);  // Dawnguard 3 + Dragonborn 4
  assert.match(await page.locator('[data-step="3"]').textContent(),/戦闘でそのシャウトを使うかどうかは、ゲームで確かめていません/);
  assert.equal(await page.locator('#shout-score').isHidden(),true);
  await row(CYCLONE).locator('input').check();await row(FORCE).locator('input').check();
  assert.equal(await page.locator('#shout-count').textContent(),'2');
  assert.deepEqual(await page.$$eval('#selected-shouts button',b=>b.map(x=>x.textContent)),[cyclone.labels.ja+' ×',force.labels.ja+' ×']);
  assert.equal(await page.locator('#shout-score').textContent(),'戦闘スタイル csHumanMagic のシャウトの優先度: 1');
  assert.equal(await page.locator('#shout-score-warning').isHidden(),true);
  // A preset replaces style and spells, never shouts.
  await to(2);await page.locator('#preset').selectOption('warrior');await to(3);
  assert.deepEqual(await checked(),[FORCE,CYCLONE].sort((a,b)=>choices.shouts.findIndex(i=>i.id===a)-choices.shouts.findIndex(i=>i.id===b)));
  assert.equal(await page.locator('#shout-score').textContent(),'戦闘スタイル csHumanMeleeLvl1 のシャウトの優先度: 1');
  // A style whose shout priority is 0 shows the warning.
  await to(2);await page.locator('#all-styles').check();await page.locator('#combat_style').selectOption(zeroStyle);await to(3);
  assert.equal(await page.locator('#shout-score').textContent(),`戦闘スタイル ${zeroStyle} のシャウトの優先度: 0`);
  assert.match(await page.locator('#shout-score-warning').textContent(),/シャウトの優先度が 0 なので、この戦闘スタイルではシャウトを使いません/);
  await page.screenshot({path:path.join(fixture,'shouts-warning-ja.png'),fullPage:true});
  // A private style shows its edited value, not the copied official one.
  await to(2);await page.locator('#combat_style_mode').selectOption('custom');
  await page.locator('#combat-style-editor').waitFor({state:'visible'});
  await page.locator('[data-combat-section="general"] summary').click();
  assert.equal(await page.locator('#combat-shout_score').inputValue(),'0');
  await page.locator('#combat-shout_score').fill('2.5');
  await to(3);
  assert.equal(await page.locator('#shout-score').textContent(),'専用の戦闘スタイルのシャウトの優先度: 2.5');
  assert.equal(await page.locator('#shout-score-warning').isHidden(),true);
  await page.locator('#language').selectOption('en');
  assert.equal(await row(CYCLONE).locator('strong').textContent(),cyclone.labels.en);
  assert.equal(await row(CYCLONE).locator('.dlc').textContent(),'Requires Dragonborn');
  assert.match(await row(CYCLONE).locator('small').textContent(),/whirling cyclone/);
  assert.equal(await page.locator('#shout-score').textContent(),'Private combat style, Equipment Score Mult - Shout: 2.5');
  assert.match(await page.locator('[data-step="3"]').textContent(),/Optionally add perks, spells and shouts\./);
  assert.match(await page.locator('[data-step="3"]').textContent(),/has not been checked in the game/);
  await page.screenshot({path:path.join(fixture,'shouts-en.png'),fullPage:true});
  await page.locator('#language').selectOption('ja');
  await row(FORCE).locator('input').uncheck();await row(FORCE).locator('input').check();  // selection order: Cyclone, Force
  await to(4);
  assert.match(await page.locator('#summary').textContent(),new RegExp(`シャウト${cyclone.labels.ja}、${force.labels.ja}`));
  assert.deepEqual(validated.at(-1).shouts,[CYCLONE,FORCE]);
  const pending=page.waitForEvent('download');await page.locator('#export-settings').click();
  const saved=JSON.parse(fs.readFileSync(await (await pending).path(),'utf8'));
  assert.deepEqual(saved.shouts,[CYCLONE,FORCE]);
  assert.equal(saved.combat_style_custom.values.shout_score,2.5);
  // Import before the catalog: the shouts come back checked, and a preset keeps them.
  await start(saved);await to(3);
  assert.deepEqual((await checked()).sort(),[CYCLONE,FORCE].sort());
  assert.equal(await page.locator('#shout-score').textContent(),'専用の戦闘スタイルのシャウトの優先度: 2.5');
  await to(2);await page.locator('#combat_style_mode').selectOption('existing');await page.locator('#preset').selectOption('archer');await to(3);
  assert.deepEqual((await checked()).sort(),[CYCLONE,FORCE].sort());
  assert.equal(await page.locator('#shout-score').textContent(),'戦闘スタイル csHumanMissile のシャウトの優先度: 1');
  // Old settings files have no shouts.
  const legacy={...defaults};delete legacy.shouts;
  await start(legacy);await to(3);
  assert.deepEqual(await checked(),[]);
  assert.deepEqual(validated.at(-1).shouts,[]);
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.deepEqual(errors,[]);
  console.log('PASS: 27 shouts, DLC labels, shout priority (official/private/zero warning), preset keeps shouts, JA/EN, review, export/import, legacy JSON, mobile');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
