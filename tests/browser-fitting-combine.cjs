/* A second real conversion and the combined-patch button, in a private browser. */
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
(async()=>{
  const source=process.env.VRM2SKYRIM_TEST_VRM;
  if(!source)throw new Error('Set a local separable humanoid test VRM');
  const current=(process.env.VRM2SKYRIM_TEST_MOD||'WardrobeFollower')+'.esp';
  const out=path.resolve(__dirname,'..','build','ui-fitting');fs.mkdirSync(out,{recursive:true});
  const browser=await chromium.launch({headless:true,channel:process.env.VRM2SKYRIM_TEST_BROWSER||'chrome'});
  try{
    const page=await browser.newPage({locale:'ja-JP',acceptDownloads:true,viewport:{width:1440,height:1120}});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto(process.env.VRM2SKYRIM_TEST_URL||'http://127.0.0.1:8768');
    await page.waitForFunction(()=>document.querySelector('#game').value.length>0);
    await page.locator('#source').setInputFiles(source);
    await page.waitForFunction(()=>document.querySelector('#source-status').textContent.includes('三角形'));
    await page.locator('#armor_support').selectOption('true');
    await page.locator('#fit-enabled').check();
    await page.waitForFunction(()=>document.querySelector('#fit-armors').options.length>2);
    await page.locator('#fit-armors').selectOption(['ArmorIronBandedCuirass','ArmorIronBoots']);
    await page.locator('#next').click();await page.locator('[data-step="1"]').waitFor({state:'visible'});
    await page.locator('#npc_name').fill('Patch comparison');await page.locator('#mod_name').fill('ArmorPatchComparison');await page.locator('#mod_id').fill('ArmorPatchComparison');
    for(let step=1;step<3;step++){await page.locator('#next').click();await page.locator(`[data-step="${step+1}"]`).waitFor({state:'visible'});}
    await page.locator('#next').click();await page.locator('[data-step="4"]').waitFor({state:'visible'});await page.locator('#render_previews').uncheck();
    await page.locator('#create').click();
    await page.waitForFunction(()=>!document.querySelector('#result').hidden||!document.querySelector('#failure').hidden,{},{timeout:600000});
    if(await page.locator('#failure').isVisible())throw new Error(await page.locator('#failure').textContent());
    await page.waitForFunction(()=>document.querySelectorAll('#fitted-followers input').length>=2);
    const wanted=new Set([current,'ArmorPatchComparison.esp']);
    for(const label of await page.locator('#fitted-followers label').all()){
      const plugin=(await label.textContent()).trim();await label.locator('input').setChecked(wanted.has(plugin));
    }
    assert.equal(await page.locator('#fitted-followers input:checked').count(),2);
    await page.locator('#merge-armor-patch').click();
    await page.waitForFunction(()=>document.querySelector('#armor-patch-status').textContent.includes('パッチを作成しました'));
    const event=page.waitForEvent('download');await page.locator('#armor-patch-download').click();await(await event).saveAs(path.join(out,'two-followers-armor-patch.zip'));
    await page.screenshot({path:path.join(out,'05-combined-patch.png'),fullPage:true});
    const job=await page.evaluate(async()=>await(await fetch('/api/jobs/'+state.job)).json());
    fs.writeFileSync(path.join(out,'combined-report.json'),JSON.stringify({status:'passed',job,plugins:[...wanted],page_errors:errors},null,2));
    assert.deepEqual(errors,[]);console.log('Two real follower outputs and combined-patch button passed:',job.output);
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
