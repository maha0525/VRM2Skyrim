/* Own headless browser only; input avatars/downloads remain local. */
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'..','build','ui-equipment-groups');fs.mkdirSync(root,{recursive:true});
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  const page=await browser.newPage({locale:'ja-JP',acceptDownloads:true,viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(process.env.VRM2SKYRIM_TEST_URL||'http://127.0.0.1:8773');
  await page.waitForFunction(()=>document.querySelector('#game').value.length>0);
  await page.locator('#source').setInputFiles(process.env.VRM2SKYRIM_TEST_VRM);
  await page.waitForFunction(()=>document.querySelector('#source-status').textContent.includes('三角形'));
  await page.locator('#armor_support').selectOption('true');
  await page.locator('#wardrobe-split').click();
  const item=page.locator('.wardrobe-item').first();await item.locator('summary').click();
  assert.equal(await item.locator('[data-field="slot"]').inputValue(),'auto');
  assert.equal(await item.locator('[data-field="slot"] option[value="32"]').count(),1);
  assert.equal(await item.locator('[data-field="slot"] option[value="42"]').count(),1);
  assert.match(await item.locator('[data-field="slot"] option[value="47"]').textContent(),/バッグ/);
  await item.locator('[data-field="item_kind"]').selectOption('legs');
  assert.match(await item.locator('[data-field="slot"] option[value="auto"]').textContent(),/32/);
  await item.locator('[data-field="slot"]').selectOption('59');
  assert.equal(await item.locator('[data-field="equipment_group"]').count(),0);
  await page.locator('#next').click();
  for(let step=1;step<4;step++)await page.locator('#next').click();
  const download=page.waitForEvent('download');await page.locator('#export-settings').click();
  const file=path.join(root,'settings.json');await(await download).saveAs(file);
  assert.equal(JSON.parse(fs.readFileSync(file,'utf8')).wardrobe_policy,'native_slots');
  assert.equal(JSON.parse(fs.readFileSync(file,'utf8')).appearance_parts.garments[0].item_kind,'legs');
  assert.equal(JSON.parse(fs.readFileSync(file,'utf8')).appearance_parts.garments[0].slot,59);
  for(let i=0;i<4;i++)await page.locator('#back').click();
  await page.locator('#import-settings').setInputFiles(file);
  await page.waitForFunction(()=>document.querySelector('#import-status').textContent.includes('読み込みました'));
  const imported=page.locator('.wardrobe-item').first();
  if(!await imported.evaluate(el=>el.open))await imported.locator('summary').click();
  assert.equal(await imported.locator('[data-field="equipment_group"]').count(),0);
  assert.equal(await imported.locator('[data-field="item_kind"]').inputValue(),'legs');
  assert.equal(await imported.locator('[data-field="slot"]').inputValue(),'59');
  assert.equal(errors.length,0,errors.join('\n'));
  await page.screenshot({path:path.join(root,'equipment-groups.png'),fullPage:true});
  console.log('Actual garment-group select -> settings download -> reimport PASS');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
