/* Real HTTP APIs and actual controls; isolated outputs, no game launch/deployment. */
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),out=path.join(root,'build/ui-live-feedback');
const source=process.env.VRM2SKYRIM_TEST_VRM,settingsPath=process.env.VRM2SKYRIM_TEST_SETTINGS;
if(!source||!settingsPath)throw new Error('Set VRM2SKYRIM_TEST_VRM and VRM2SKYRIM_TEST_SETTINGS to private local test inputs');
const previous=JSON.parse(fs.readFileSync(settingsPath,'utf8'));
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  const page=await browser.newPage({acceptDownloads:true,viewport:{width:1440,height:1100}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  if(process.env.VRM2SKYRIM_STALE_TEST_URL){
   await page.goto(process.env.VRM2SKYRIM_STALE_TEST_URL);
   await page.waitForFunction(()=>document.querySelector('#error').textContent.includes('再起動が必要'));
   assert.equal(await page.locator('#next').isDisabled(),true);
   await page.screenshot({path:path.join(out,'stale-server.png'),fullPage:true});
  }
  await page.goto('http://127.0.0.1:8793/');
  await page.waitForFunction(()=>document.querySelector('#game').value.length>0);
  assert.equal(await page.locator('#protection').inputValue(),'essential');
  assert.equal(await page.locator('#morality').inputValue(),'0');
  await page.locator('#import-settings').setInputFiles({name:'aifi-settings.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(previous))});
  await page.waitForFunction(()=>document.querySelector('#import-status').textContent.includes('読み込みました'));
  await page.locator('#source').setInputFiles(source);
  await page.waitForFunction(()=>document.querySelector('#source-status').textContent.includes('三角形'),{timeout:120000});
  const physics=page.locator('#physics-meshes label').filter({hasText:'Spring'});
  assert.equal(await physics.count(),previous.physics_nodes.length);
  for(const row of await physics.all())assert.equal(await row.locator('input').isChecked(),true);
  await page.locator('#next').click();await page.locator('[data-step="1"]').waitFor({state:'visible'});
  await page.locator('#next').click();await page.locator('[data-step="2"]').waitFor({state:'visible'});
  const classes=await page.locator('#combat_class option').evaluateAll(rows=>rows.map(row=>row.value));
  for(const key of classes){await page.locator('#combat_class').selectOption(key);assert.match(await page.locator('#class-details').textContent(),/成長配分：/);}
  await page.locator('#combat_class').selectOption(previous.combat_class);
  await page.screenshot({path:path.join(out,'class-growth.png'),fullPage:true});
  await page.locator('#next').click();await page.locator('[data-step="3"]').waitFor({state:'visible'});
  await page.locator('#perk-category').selectOption('Sneak');
  await page.locator('#perk-search').fill('隠術');
  assert.equal(await page.locator('#perks .choice').count(),5);
  assert.equal(await page.locator('#perks input[type="number"],#perks select').count(),0);
  assert.match(await page.locator('#perks').textContent(),/段階 1\/5/);
  assert.match(await page.locator('#perks').textContent(),/段階 5\/5/);
  await page.locator('#spell-category').selectOption('Illusion');
  assert.equal(await page.locator('#spells input[data-record-id="Muffle"]').count(),1);
  assert.equal(await page.locator('#spells input[data-record-id="Firebolt"]').count(),0);
  await page.locator('#spell-search').fill('Muffle');
  assert.equal(await page.locator('#spells .choice').count(),1);
  await page.locator('#spell-search').fill('');
  await page.screenshot({path:path.join(out,'categories.png'),fullPage:true});
  await page.locator('#next').click();await page.locator('[data-step="4"]').waitFor({state:'visible'});
  await page.locator('#render_previews').uncheck();
  const saved=page.waitForEvent('download');await page.locator('#export-settings').click();
  const exported=JSON.parse(fs.readFileSync(await (await saved).path(),'utf8'));
  assert.deepEqual(exported.physics_nodes,previous.physics_nodes);
  assert.deepEqual(exported.perks,previous.perks);assert.deepEqual(exported.spells,previous.spells);
  if(process.argv.includes('--resume')){
   await page.goto('http://127.0.0.1:8793/');
   await page.locator('#open-saved').waitFor({state:'visible'});
   await page.locator('#open-saved').click();
  }else{
   await page.locator('#create').click();
   await page.waitForFunction(()=>!document.querySelector('#result').hidden||!document.querySelector('#failure').hidden,null,{timeout:600000});
  }
  await page.locator('#result').waitFor({state:'visible'});
  assert.equal(await page.locator('#failure').isVisible(),false,await page.locator('#failure').textContent());
  const href=await page.locator('#download').getAttribute('href');
  const job=await (await page.request.get(new URL(href.split('/file?')[0],page.url()).href)).json();
  assert.equal(job.status,'complete');fs.writeFileSync(path.join(out,'verified-job.json'),JSON.stringify(job,null,2));
  await page.screenshot({path:path.join(out,'complete.png'),fullPage:true});
  const downloadPromise=page.waitForEvent('download');await page.locator('#download').click();
  const download=await downloadPromise;await download.saveAs(path.join(out,job.archive));
  await page.locator('#again').click();
  await page.waitForFunction(name=>document.querySelector('#saved-job').selectedOptions[0]?.textContent.includes(name),previous.npc_name);
  assert.equal(await page.locator('#saved-results').isVisible(),true);
  assert.deepEqual(errors,[]);
  console.log('PASS: defaults, all '+classes.length+' class growths, categories, stages, unchanged selections, '+previous.physics_nodes.length+' Spring meshes, full conversion/download/saved-results');
  console.log(job.output);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
