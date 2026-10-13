/* Exercise the actual optional controls and exported settings in isolation. */
const {chromium}=require('playwright');
const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'../build/physics/ui');fs.mkdirSync(root,{recursive:true});
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  const page=await browser.newPage({acceptDownloads:true,viewport:{width:1400,height:1100}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(process.env.VRM2SKYRIM_TEST_URL||'http://127.0.0.1:8795');
  await page.waitForFunction(()=>document.querySelector('#game').value.length>0);
  assert.equal(await page.locator('#physics_enabled').isChecked(),false);
  await page.locator('#source').setInputFiles(process.env.VRM2SKYRIM_TEST_VRM);
  await page.waitForFunction(()=>document.querySelector('#source-status').textContent.includes('三角形'));
  await page.locator('#physics_enabled').check();
  assert.ok(await page.locator('#physics-panel').isVisible());
  assert.match(await page.locator('#physics-panel').textContent(),/SKSE64/);
  assert.equal(await page.locator('#physics_stiffness').inputValue(),'1');
  assert.match(await page.locator('#physics_stiffness option:checked').textContent(),/穏やか/);
  assert.match(await page.locator('#physics-panel').textContent(),/減衰を自動調整/);
  await page.locator('#physics_stiffness').selectOption('0.3');
  await page.locator('#physics-meshes input[data-node="639"]').check();
  await page.screenshot({path:path.join(root,'physics-controls.png'),fullPage:true});
  for(let i=0;i<4;i++)await page.locator('#next').click();
  const download=page.waitForEvent('download');await page.locator('#export-settings').click();
  const file=path.join(root,'settings.json');await(await download).saveAs(file);
  const settings=JSON.parse(fs.readFileSync(file,'utf8'));
  assert.equal(settings.physics_enabled,true);assert.equal(settings.physics_stiffness,.3);
  assert.deepEqual(settings.physics_nodes,[639]);assert.equal(errors.length,0,errors.join('\n'));
  console.log('FSMP toggle, prerequisite hint, mesh selection, stiffness and real settings download PASS');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
