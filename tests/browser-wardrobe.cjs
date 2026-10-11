/* Real wardrobe UI test; private test avatars and results stay under build/. */
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

(async()=>{
  const source=process.env.VRM2SKYRIM_TEST_VRM;
  if(!source)throw new Error('Set VRM2SKYRIM_TEST_VRM to a separable humanoid VRM');
  const fitting=process.env.VRM2SKYRIM_TEST_FIT==='true';
  const out=path.resolve(__dirname,'..','build',fitting?'ui-fitting':'ui-wardrobe');fs.mkdirSync(out,{recursive:true});
  const browser=await chromium.launch({headless:true,...(process.env.VRM2SKYRIM_TEST_BROWSER?{channel:process.env.VRM2SKYRIM_TEST_BROWSER}:{})});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1120},acceptDownloads:true});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto(process.env.VRM2SKYRIM_TEST_URL||'http://127.0.0.1:8768');
    await page.waitForFunction(()=>document.querySelector('#game').value.length>0);
    await page.locator('#source').setInputFiles(source);
    await page.waitForFunction(()=>document.querySelector('#source-status').textContent.includes('三角形'));
    await page.locator('#armor_support').selectOption('true');
    await page.locator('#wardrobe-editor').waitFor({state:'visible'});
    if(fitting){await page.locator('#fit-enabled').check();await page.waitForFunction(()=>document.querySelector('#fit-armors').options.length>2);await page.locator('#fit-armors').selectOption(['ArmorIronBandedCuirass','ArmorIronBoots']);}
    const partCount=await page.locator('.wardrobe-part').count();assert(partCount>3);
    const roles=await page.locator('.wardrobe-part select:first-of-type').evaluateAll(xs=>xs.map(x=>x.value));
    assert(roles.includes('body'));assert(roles.includes('underwear'));assert(roles.includes('garment'));
    const clothingCount=roles.filter(r=>r==='garment').length;assert(clothingCount>1);
    await page.locator('#wardrobe-split').click();
    assert.equal(await page.locator('.wardrobe-item').count(),clothingCount);
    await page.locator('#wardrobe-combine').click();assert.equal(await page.locator('.wardrobe-item').count(),1);
    await page.locator('#wardrobe-split').click();
    const first=page.locator('.wardrobe-item').first();await first.locator('summary').click();
    await first.locator('[data-field="value"]').fill('17');await first.locator('[data-field="weight"]').fill('1');await first.locator('[data-field="value"]').focus();
    await page.locator('#wardrobe-preview-state').selectOption('underwear');
    await page.locator('#wardrobe-preview').click();
    await page.waitForFunction(()=>document.querySelectorAll('#wardrobe-preview-images img').length===2||!document.querySelector('#error').hidden,{},{timeout:120000});
    if(await page.locator('#error').isVisible())throw new Error(await page.locator('#error').textContent());
    await page.waitForFunction(()=>[...document.querySelectorAll('#wardrobe-preview-images img')].every(i=>i.complete&&i.naturalWidth>0));
    await page.screenshot({path:path.join(out,'01-classification.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.screenshot({path:path.join(out,'02-mobile-classification.png'),fullPage:true});await page.setViewportSize({width:1440,height:1120});
    console.log('VRM upload, role suggestions, split/combine, item settings and real source preview passed');
    await page.locator('#next').click();await page.locator('[data-step="1"]').waitFor({state:'visible'});
    const npc=process.env.VRM2SKYRIM_TEST_NPC||'Wardrobe Avatar',mod=process.env.VRM2SKYRIM_TEST_MOD||'WardrobeFollower';
    await page.locator('#npc_name').fill(npc);await page.locator('#mod_name').fill(mod);await page.locator('#mod_id').fill(mod);
    await page.locator('#back').click();await page.locator('[data-step="0"]').waitFor({state:'visible'});
    assert.equal(await page.locator('.wardrobe-item').count(),clothingCount);
    assert.equal(await page.locator('.wardrobe-item').first().locator('[data-field="value"]').inputValue(),'17');
    await page.locator('#next').click();
    for(let step=1;step<4;step++){await page.locator(`[data-step="${step}"]`).waitFor({state:'visible'});await page.locator('#next').click();}
    await page.locator('[data-step="4"]').waitFor({state:'visible'});
    assert((await page.locator('#summary').textContent()).includes(clothingCount+'品を着脱可能'));
    const downloadEvent=page.waitForEvent('download');await page.locator('#export-settings').click();const settingsDownload=await downloadEvent;
    const settingsPath=path.join(out,'settings.json');await settingsDownload.saveAs(settingsPath);const saved=JSON.parse(fs.readFileSync(settingsPath,'utf8'));
    assert(saved.armor_support);assert.equal(saved.appearance_parts.garments.length,clothingCount);assert.equal(saved.appearance_parts.garments[0].value,17);
    if(fitting)assert.deepEqual(saved.fit_armors,['ArmorIronBandedCuirass','ArmorIronBoots']);
    // Import the downloaded settings through the actual file input, retaining classification.
    for(let i=0;i<4;i++)await page.locator('#back').click();await page.locator('#import-settings').setInputFiles(settingsPath);
    await page.waitForFunction(()=>document.querySelector('#import-status').textContent.includes('読み込みました'));
    for(let step=0;step<4;step++){await page.locator(`[data-step="${step}"]`).waitFor({state:'visible'});await page.locator('#next').click();}
    await page.locator('[data-step="4"]').waitFor({state:'visible'});await page.locator('#create').click();
    await page.locator('#progress').waitFor({state:'visible'});console.log('Saved/imported classification and actual conversion button passed');
    await page.waitForFunction(()=>!document.querySelector('#result').hidden||!document.querySelector('#failure').hidden,{},{timeout:600000});
    if(await page.locator('#failure').isVisible())throw new Error(await page.locator('#failure').textContent());
    await page.waitForFunction(()=>document.querySelectorAll('#previews img').length>5&&[...document.querySelectorAll('#previews img')].every(i=>i.complete&&i.naturalWidth>0));
    const zipEvent=page.waitForEvent('download');await page.locator('#download').click();const zip=await zipEvent;await zip.saveAs(path.join(out,zip.suggestedFilename()));
    if(fitting){await page.locator('#armor-patch-result').waitFor({state:'visible'});const patchEvent=page.waitForEvent('download');await page.locator('#armor-patch-download').click();await(await patchEvent).saveAs(path.join(out,'VRM2SkyrimArmorPatch.zip'));await page.locator('#fitted-followers input:checked').waitFor();await page.locator('#merge-armor-patch').click();await page.waitForFunction(()=>document.querySelector('#armor-patch-status').textContent.includes('パッチを作成しました'));const mergedEvent=page.waitForEvent('download');await page.locator('#armor-patch-download').click();await(await mergedEvent).saveAs(path.join(out,'merged-armor-patch.zip'));}
    await page.screenshot({path:path.join(out,'03-result.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:path.join(out,'04-mobile-result.png'),fullPage:true});
    assert.deepEqual(errors,[]);const job=await page.evaluate(async()=>await(await fetch('/api/jobs/'+state.job)).json());
    fs.writeFileSync(path.join(out,'report.json'),JSON.stringify({status:'passed',parts:partCount,clothing:clothingCount,job,page_errors:errors},null,2));
    console.log('Separated NIF output previews and real MOD ZIP download passed:',job.output);
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
