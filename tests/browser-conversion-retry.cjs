/* Real create button with a saved configuration that previously failed. */
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  const page=await browser.newPage({locale:'ja-JP',viewport:{width:1440,height:1100}});
  await page.goto(process.env.VRM2SKYRIM_TEST_URL||'http://127.0.0.1:8791');
  await page.waitForFunction(()=>document.querySelector('#game').value.length>0);
  await page.locator('#source').setInputFiles(process.env.VRM2SKYRIM_TEST_VRM);
  await page.waitForFunction(()=>document.querySelector('#source-status').textContent.includes('三角形'));
  await page.locator('#import-settings').setInputFiles(process.env.VRM2SKYRIM_TEST_SETTINGS);
  await page.waitForFunction(()=>document.querySelector('#import-status').textContent.includes('読み込みました'));
  for(let i=0;i<4;i++)await page.locator('#next').click();
  const response=page.waitForResponse(r=>r.url().endsWith('/api/jobs')&&r.request().method()==='POST');
  await page.locator('#create').click();const value=await(await response).json();
  assert.ok(value.job_id,JSON.stringify(value));console.log('Normal create button started',value.job_id);
  await page.waitForFunction(()=>!document.querySelector('#result').hidden||!document.querySelector('#failure').hidden,{},{timeout:1200000});
  if(await page.locator('#failure').isVisible())throw Error(await page.locator('#failure').textContent());
  const job=await(await page.request.get(new URL('/api/jobs/'+value.job_id,page.url()).href)).json();
  const dir=path.resolve(__dirname,'../build/ui-conversion-retry');fs.mkdirSync(dir,{recursive:true});
  fs.writeFileSync(path.join(dir,'job.json'),JSON.stringify(job,null,2));
  await page.screenshot({path:path.join(dir,'normal-generated-result.png'),fullPage:true});
  assert.match(job.archive,/0\.8\.0/);assert.ok(job.armor_patch);
  console.log('Saved VRM / wardrobe -> actual create button -> complete normal follower MOD PASS',job.output);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
