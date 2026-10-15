/* Real wizard HTTP routes and actual user buttons; fake game only. */
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{spawn}=require('node:child_process');
const root=path.resolve(__dirname,'..'),out=path.join(root,'build/patch-recovery/browser-'+Date.now());
fs.mkdirSync(out,{recursive:true});
const py=spawn(process.env.TEST_PYTHON||'python',[path.join(__dirname,'browser-skypatcher-server.py'),out],{cwd:root,windowsHide:true});
(async()=>{
 let browser;
 try {
  const ready=await new Promise((resolve,reject)=>{let text='';py.stdout.on('data',b=>{text+=b;for(const l of text.split('\n')){try{const v=JSON.parse(l);if(v.port)resolve(v);}catch{}}});py.on('exit',code=>reject(Error('server exited '+code)));py.stderr.on('data',b=>fs.appendFileSync(path.join(out,'server.log'),b));});
  browser=await chromium.launch({headless:true,channel:'chrome'});
  const page=await browser.newPage({locale:'ja-JP',viewport:{width:1360,height:1050}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:'+ready.port);
  await page.locator('#legacy-armor-notice').waitFor({state:'visible'});
  assert.match(await page.locator('#legacy-armor-notice').textContent(),/全フォロワー/);
  await page.locator('#saved-job').selectOption({label:'Fitted · Fitted.esp'});
  await page.locator('#open-saved').click();
  await page.waitForFunction(()=>document.querySelector('#deployed-patch-status').textContent.includes('未導入'));
  assert.equal(await page.locator('#merge-armor-patch').count(),0);
  assert.equal(await page.locator('#armor-patch-download').count(),0);
  const plugins=path.join(ready.game,'Data/SKSE/Plugins');fs.mkdirSync(plugins,{recursive:true});
  fs.writeFileSync(path.join(plugins,'SkyPatcher.dll'),'armorAddonsToAdd filterByArmorAddonsExcluded hasPlugins formsToAdd');
  fs.writeFileSync(path.join(plugins,'SkyPatcher.ini'),'[Patcher]\niEnableArmorPatching=1\niEnableFormlistPatching=1\n');
  await page.locator('#check-deployed-patch').click();
  await page.waitForFunction(()=>document.querySelector('#deployed-patch-status').textContent.includes('未配備'));
  for(const kind of ['armor','formList']){const dir=path.join(plugins,'SkyPatcher',kind,'VRM2Skyrim');fs.mkdirSync(dir,{recursive:true});fs.writeFileSync(path.join(dir,'Fitted.esp.ini'),'; generated config');}
  await page.locator('#check-deployed-patch').click();
  await page.waitForFunction(()=>document.querySelector('#deployed-patch-status').textContent.includes('確認しました'));
  const deployedConfig=path.join(plugins,'SkyPatcher/armor/VRM2Skyrim/Fitted.esp.ini');
  fs.writeFileSync(deployedConfig,'; stale config');await page.locator('#check-deployed-patch').click();
  await page.waitForFunction(()=>document.querySelector('#deployed-patch-status').textContent.includes('古い出力'));
  fs.writeFileSync(deployedConfig,'; generated config');await page.locator('#check-deployed-patch').click();
  await page.waitForFunction(()=>document.querySelector('#deployed-patch-status').textContent.includes('確認しました'));
  await page.locator('#language').selectOption('en');
  assert.match(await page.locator('#armor-patch-result').textContent(),/Registration is included/);
  assert.match(await page.locator('#deployed-patch-status').textContent(),/configuration files are present/);
  await page.screenshot({path:path.join(out,'skypatcher-result-en.png'),fullPage:true});
  await page.locator('#language').selectOption('ja');
  await page.locator('#again').click();
  await page.locator('#saved-job').selectOption({label:'Plain · Plain.esp'});
  await page.locator('#open-saved').click();
  assert.equal(await page.locator('#armor-patch-result').isVisible(),false);
  assert.equal(await page.locator('#legacy-armor-notice').isVisible(),true);
  await page.locator('#again').click();
  await page.locator('#saved-job').selectOption({label:'Legacy · Legacy.esp'});
  await page.locator('#open-saved').click();
  await page.waitForFunction(()=>document.querySelector('#deployed-patch-status').textContent.includes('旧式'));
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:path.join(out,'skypatcher-legacy-mobile.png'),fullPage:true});
  assert.deepEqual(errors,[]);console.log('PASS: real wizard SkyPatcher install/check/migration/language workflow '+out);
 } finally {if(browser)await browser.close();py.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
