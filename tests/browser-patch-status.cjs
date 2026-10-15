/* Actual result controls detect the deployed old patch and download the new one. */
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
(async()=>{
 const out=path.resolve(__dirname,'../build/ui-patch-status');fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  const page=await browser.newPage({locale:'ja-JP',acceptDownloads:true,viewport:{width:1440,height:1100}});
  await page.goto(process.env.VRM2SKYRIM_TEST_URL||'http://127.0.0.1:8791');
  await page.waitForFunction(()=>[...document.querySelectorAll('#saved-job option')].some(o=>o.textContent.includes('ErysWardrobe.esp')));
  const erys=await page.locator('#saved-job option').evaluateAll(xs=>xs.find(x=>x.textContent.includes('ErysWardrobe.esp')).value);
  await page.locator('#saved-job').selectOption(erys);
  await page.locator('#open-saved').click();
  await page.waitForFunction(()=>document.querySelector('#deployed-patch-status').textContent.includes('ゲーム内'));
  const response=page.waitForResponse(r=>r.url().includes('/api/patch-status'));
  await page.locator('#check-deployed-patch').click();
  const live=await(await response).json();
  assert.equal(live.expected_items,2986);
  assert.ok(['current','needs_update','missing'].includes(live.status));
  const event=page.waitForEvent('download');await page.locator('#armor-patch-download').click();
  await(await event).saveAs(path.join(out,'VRM2SkyrimArmorPatch.zip'));
  assert.ok(fs.statSync(path.join(out,'VRM2SkyrimArmorPatch.zip')).size>10000);
  await page.locator('#armor-patch-result').screenshot({path:path.join(out,'deployed-patch.png')});
  const erysProfile=page.locator('#fitted-followers label').filter({hasText:'ErysWardrobe.esp'});
  const quonProfile=page.locator('#fitted-followers label').filter({hasText:'Quon_Tsuruhane_Follower.esp'});
  assert.ok(await erysProfile.locator('input').isChecked());
  assert.ok(!await quonProfile.locator('input').isChecked());
  await quonProfile.locator('input').check();
  await page.locator('#merge-armor-patch').click();
  await page.waitForFunction(()=>document.querySelector('#armor-patch-status').textContent.includes('パッチを作成しました'));
  assert.equal(await page.locator('#armor-patch-download').textContent(),'統合パッチを保存');
  const merged=page.waitForEvent('download');await page.locator('#armor-patch-download').click();
  await(await merged).saveAs(path.join(out,'two-followers.zip'));
  console.log('Actual deployed patch -> refreshed status -> current patch ZIP -> two-follower combined patch download PASS');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
