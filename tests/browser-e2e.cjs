/* Test the real wizard in a separate headless browser, never the user's browser. */
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
  const source = process.env.VRM2SKYRIM_TEST_VRM;
  if (!source) throw new Error('Set VRM2SKYRIM_TEST_VRM to a local test VRM');
  const root = path.resolve(__dirname, '..', 'build', 'ui-test');
  fs.mkdirSync(root, { recursive: true });
  const browser = await chromium.launch({headless:true,...(process.env.VRM2SKYRIM_TEST_BROWSER ? {channel:process.env.VRM2SKYRIM_TEST_BROWSER} : {})});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1120},acceptDownloads:true});
    const errors=[]; page.on('pageerror', error=>errors.push(error.message));
    await page.goto(process.env.VRM2SKYRIM_TEST_URL || 'http://127.0.0.1:8768');
    await page.locator('#game').waitFor();
    await page.waitForFunction(()=>document.querySelector('#game').value.length>0);
    await page.locator('#source').setInputFiles(source);
    await page.waitForFunction(()=>document.querySelector('#source-status').textContent.includes('三角形'));
    await page.screenshot({path:path.join(root,'01-source.png'),fullPage:true});
    console.log('Real VRM upload passed');
    await page.locator('#next').click();
    await page.locator('[data-step="1"]').waitFor({state:'visible'});
    await page.locator('#npc_name').fill('Sophie');
    await page.locator('#mod_name').fill('SophieFollower');
    await page.locator('#mod_id').fill('SophieFollower');
    await page.locator('#author').fill('maha0525');
    await page.locator('#voice').selectOption('FemaleEvenToned');
    assert.equal(await page.locator('#voice option').count(),17);
    await page.screenshot({path:path.join(root,'02-identity.png'),fullPage:true});
    await page.locator('#next').click();
    await page.locator('[data-step="2"]').waitFor({state:'visible'});
    await page.locator('#preset').selectOption('mage');
    assert.equal(await page.locator('#combat_class').inputValue(),'CombatMageDestruction');
    await page.locator('#preset').selectOption('warrior');
    assert.equal(await page.locator('#weapon').inputValue(),'SteelSword');
    const defaultsOnly=process.env.VRM2SKYRIM_TEST_DEFAULTS==='1';
    if(!defaultsOnly){await page.locator('#auto_calculate').selectOption('false');await page.locator('#health').fill('250');await page.locator('#manual-skills summary').click();await page.locator('#skill-OneHanded').fill('75');}
    await page.screenshot({path:path.join(root,'03-combat.png'),fullPage:true});
    await page.locator('#next').click();
    await page.locator('[data-step="3"]').waitFor({state:'visible'});
    await page.locator('#perk-search').fill('Armsman00');
    if(!defaultsOnly)await page.locator('[data-record-id="Armsman00"]').check();
    await page.locator('#spell-search').fill('FastHealing');
    if(!defaultsOnly)await page.locator('[data-record-id="FastHealing"]').check();
    assert.equal(await page.locator('#perk-count').textContent(),defaultsOnly?'0':'1');
    assert.equal(await page.locator('#spell-count').textContent(),defaultsOnly?'0':'1');
    await page.screenshot({path:path.join(root,'04-perks.png'),fullPage:true});
    await page.locator('#next').click();
    await page.locator('[data-step="4"]').waitFor({state:'visible'});
    await page.locator('#back').click();
    assert.equal(await page.locator('#perk-count').textContent(),defaultsOnly?'0':'1');
    await page.locator('#next').click();
    await page.locator('[data-step="4"]').waitFor({state:'visible'});
    await page.screenshot({path:path.join(root,'05-review.png'),fullPage:true});
    const settingsDownload = page.waitForEvent('download');
    await page.locator('#export-settings').click();
    const settings = await settingsDownload;
    await settings.saveAs(path.join(root,'settings.json'));
    const saved=JSON.parse(fs.readFileSync(path.join(root,'settings.json'),'utf8'));
    if(!defaultsOnly){assert.equal(saved.health,250);assert.equal(saved.skills.OneHanded,75);assert.equal(saved.perks[0].editor_id,'Armsman00');}
    else{assert.equal(saved.health,200);assert.equal(saved.auto_calculate,true);assert.equal(saved.perks.length,0);}
    console.log('Five wizard steps, back navigation, presets, Perk/spell selection and settings download passed');
    await page.locator('#create').click();
    await page.locator('#progress').waitFor({state:'visible'});
    console.log('Actual conversion started through the create button');
    await page.waitForFunction(()=>!document.querySelector('#result').hidden || !document.querySelector('#failure').hidden,{},{timeout:300000});
    if(await page.locator('#failure').isVisible())throw new Error(await page.locator('#failure').textContent());
    await page.waitForFunction(()=>[...document.querySelectorAll('#previews img')].every(img=>img.complete&&img.naturalWidth>0));
    const zipDownload=page.waitForEvent('download');await page.locator('#download').click();const zip=await zipDownload;
    await zip.saveAs(path.join(root,zip.suggestedFilename()));
    await page.screenshot({path:path.join(root,'06-result.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(root,'07-mobile-result.png'),fullPage:true});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
    assert.deepEqual(errors,[]);
    const job=await page.evaluate(async()=>await (await fetch('/api/jobs/'+state.job)).json());
    fs.writeFileSync(path.join(root,'report.json'),JSON.stringify({status:'passed',job,zip:zip.suggestedFilename(),page_errors:errors},null,2));
    console.log('Real conversion, output previews and ZIP download passed:',job.output);
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
