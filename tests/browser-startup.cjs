/* Real HTTP listeners: stale tab rejects input; the launcher's new URL is usable. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const [oldUrl,newUrl]=process.argv.slice(2);
 assert.notEqual(oldUrl,newUrl);
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  const page=await browser.newPage({locale:'ja-JP'});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(oldUrl);
  await page.waitForFunction(()=>document.querySelector('#error').textContent.includes('0.9.5-dev'));
  assert.equal(await page.locator('#source').isDisabled(),true);
  assert.match(await page.locator('#error').textContent(),/新しく開いたページ/);
  await page.goto(newUrl);
  await page.waitForFunction(()=>document.querySelector('#game').value.length>0);
  assert.equal(await page.locator('#error').isVisible(),false);
  assert.equal(await page.locator('#source').isEnabled(),true);
  const expected=await page.locator('meta[name="converter-version"]').getAttribute('content');
  assert.equal(await page.locator('#version').textContent(),'VRM2Skyrim '+expected);
  assert.deepEqual(errors,[]);
  console.log('PASS: stale listener remains alive, new port loads the current UI and enables input');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
