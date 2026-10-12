/* Exercise actual wizard controls and settings export/reimport in own Chrome. */
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'..','build','ui-all-equipment');fs.mkdirSync(root,{recursive:true});
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  const page=await browser.newPage({acceptDownloads:true,viewport:{width:1440,height:1100}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(process.env.VRM2SKYRIM_TEST_URL||'http://127.0.0.1:8784');
  await page.waitForFunction(()=>document.querySelector('#game').value.length>0);
  if(await page.locator('#saved-results').isVisible()){
   await page.locator('#open-saved').click();
   await page.waitForFunction(()=>!document.querySelector('#result').hidden);
   assert.ok(await page.locator('#equipment-edit').isVisible());
   assert.ok(await page.locator('#edit-mesh option').count()>400);
   assert.match(await page.locator('#edit-kit-download').getAttribute('href'),/OutfitStudio-EditKit/);
   await page.locator('#again').click();
  }
  await page.locator('#source').setInputFiles(process.env.VRM2SKYRIM_TEST_VRM);
  await page.waitForFunction(()=>document.querySelector('#source-status').textContent.includes('三角形'));
  await page.locator('#armor_support').selectOption('true');
  assert.equal(await page.locator('[data-node="493"] select').first().inputValue(),'face');
  await page.locator('#wardrobe-split').click();
  await page.locator('#fit-enabled').check();
  await page.waitForFunction(()=>document.querySelector('#fit-armors').options.length>2000);
  await page.locator('#fit_mode').selectOption('all_official');
  await page.locator('#fit_source').selectOption('installed');
  await page.locator('#fit-panel details summary').click();
  await page.locator('#head-search').fill('IronHelmet');
  const row=page.locator('#head-policies [data-addon]').first();
  assert.ok(await row.locator('[data-policy="hide_hair"]').isChecked());
  await row.locator('[data-policy="hide_face"]').check();
  await row.locator('[data-policy="hide_hair"]').uncheck();
  await page.locator('#next').click();
  for(const sex of ['male','female']){
   const response=page.waitForResponse(r=>r.url().endsWith('/api/catalog')&&r.request().postDataJSON()?.sex===sex);
   await page.locator('#sex').selectOption(sex);
   const catalog=await(await response).json();
   assert.ok(catalog.choices.armors.some(i=>i.editor_id==='ArmorIronShield'));
  }
  for(let i=1;i<4;i++)await page.locator('#next').click();
  const ready=page.waitForEvent('download');await page.locator('#export-settings').click();
  const file=path.join(root,'settings.json');await(await ready).saveAs(file);
  const settings=JSON.parse(fs.readFileSync(file,'utf8'));
  assert.equal(settings.fit_mode,'all_official');assert.equal(settings.fit_source,'installed');
  assert.deepEqual(settings.fit_armors,[]);assert.deepEqual(settings.appearance_heads.face,[493]);
  assert.ok(Object.values(settings.head_overrides).some(p=>p.hide_face&&!p.hide_hair));
  for(let i=0;i<4;i++)await page.locator('#back').click();
  await page.locator('#import-settings').setInputFiles(file);
  await page.waitForFunction(()=>document.querySelector('#import-status').textContent.includes('読み込みました'));
  assert.equal(await page.locator('#fit_mode').inputValue(),'all_official');
  assert.equal(await page.locator('#fit_source').inputValue(),'installed');
  assert.ok(await page.locator('#fit-enabled').isChecked());
  assert.equal(errors.length,0,errors.join('\n'));
  await page.screenshot({path:path.join(root,'all-equipment.png'),fullPage:true});
  console.log('Official batch / deployed reference / independent head policy -> export -> reimport PASS');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
