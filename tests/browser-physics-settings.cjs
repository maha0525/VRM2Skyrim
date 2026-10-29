/* Actual checkbox -> navigation -> JSON download -> new page/import roundtrip. */
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),fixture=path.join(root,'build/ui-roles');
const defaults=JSON.parse(fs.readFileSync(path.join(fixture,'defaults.json'),'utf8'));
const choices=JSON.parse(fs.readFileSync(path.join(fixture,'roles.json'),'utf8'));
const source={source_id:'physics',sha256:'a'.repeat(64),filename:'physics.vrm',mesh_count:3,triangles:30,suggested_name:'Test',parts:[
 {node:0,name:'Body',triangles:10,materials:['body'],suggested_role:'body'},
 {node:1,name:'Hair',triangles:10,materials:['hair'],suggested_role:'fixed'},
 {node:2,name:'Cape',triangles:10,materials:['cloth'],suggested_role:'garment'}]};
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  const page=await browser.newPage({locale:'ja-JP',acceptDownloads:true});
  const errors=[],submitted=[],shaderRequests=[];page.on('pageerror',e=>errors.push(e.message));
  const archive='VRM2Skyrim-Toon-Shader-0.13.0.zip';let toonShader={archive,available:true,release:'1.0.22',state:'original'},jobToon=true;
  await page.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url());let data;
   if(url.pathname==='/api/environment')data={defaults,game:'Read-only fixture',blender:'Fixture Blender',version:'test'};
   else if(url.pathname==='/api/jobs')data=request.method()==='POST'?{job_id:'completed'}:{jobs:[]};
   else if(url.pathname==='/api/jobs/completed')data={id:'completed',status:'complete',stage:'Complete',events:[],npc_name:'Test',plugin_name:'Test.esp',archive:'Test.zip',output:'Fixture',previews:[],toon_enabled:jobToon};
   else if(url.pathname==='/api/toon-shader-status'){shaderRequests.push(url.searchParams.get('game'));data=toonShader;}
   else if(url.pathname==='/api/toon-shader')return route.fulfill({body:Buffer.from('fixture zip'),contentType:'application/zip',headers:{'Content-Disposition':`attachment; filename="${archive}"`}});
   else if(url.pathname==='/api/source')data={...source,sha256:request.headers()['x-filename']==='other.vrm'?'b'.repeat(64):source.sha256};
   else if(url.pathname==='/api/catalog')data={checks:{ready:true},choices:{...choices,armors:[],equipment_plugins:[]}};
   else if(url.pathname==='/api/validate'){submitted.push(request.postDataJSON().settings);data={settings:submitted.at(-1)};}
   if(data!==undefined)return route.fulfill({json:data});
   const name=url.pathname==='/'?'index.html':url.pathname.slice(1),file=path.join(root,'web',name);
   return route.fulfill({body:fs.readFileSync(file),contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html'});
  });
  const mesh=node=>page.locator(`#physics-meshes input[data-node="${node}"]`);
  async function start(){await page.goto('http://127.0.0.1:8899/');await page.waitForFunction(()=>document.querySelector('#game').value.length>0);}
  // Wait on the resulting DOM, not on internal state.
  async function sourceFile(name='physics.vrm'){
   const response=page.waitForResponse(r=>r.url().endsWith('/api/source'));
   await page.locator('#source').setInputFiles({name,mimeType:'application/octet-stream',buffer:Buffer.from(name)});await response;
   await page.waitForFunction(()=>document.querySelectorAll('#physics-meshes input').length===3&&!document.querySelector('#next').disabled);
  }
  async function importJSON(settings){
   await page.locator('#import-settings').setInputFiles({name:'physics.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(settings))});
   await page.waitForFunction(()=>document.querySelector('#import-status').textContent.length>0);
  }
  async function review(){for(let step=1;step<=4;step++){await page.locator('#next').click();await page.locator(`[data-step="${step}"]`).waitFor({state:'visible'});}}
  async function save(){const pending=page.waitForEvent('download');await page.locator('#export-settings').click();return JSON.parse(fs.readFileSync(await (await pending).path(),'utf8'));}
  const legacy={...defaults,physics_enabled:true,physics_nodes:[],appearance_source_sha256:source.sha256};
  await start();await importJSON(legacy);await sourceFile();
  await mesh(1).check();await mesh(2).check();
  await review();
  assert.deepEqual(submitted[0].physics_nodes,[1,2],'Next must preserve edits made after JSON import');
  const saved=await save();assert.deepEqual(saved.physics_nodes,[1,2]);assert.equal(saved.physics_source_sha256,source.sha256);
  fs.writeFileSync(path.join(fixture,'physics-settings-export.json'),JSON.stringify(saved,null,2));
  // Both file input orders restore downloaded JSON in a fresh page.
  for(const jsonFirst of [true,false]){
   await start();if(jsonFirst)await importJSON(saved);await sourceFile();if(!jsonFirst)await importJSON(saved);
   assert.equal(await mesh(1).isChecked(),true);assert.equal(await mesh(2).isChecked(),true);
   await mesh(2).uncheck();await sourceFile();assert.equal(await mesh(1).isChecked(),true);assert.equal(await mesh(2).isChecked(),false,'same VRM cannot replay stale import');
   await page.locator('#language').selectOption('en');assert.equal(await mesh(1).isChecked(),true);
   await review();assert.deepEqual((await save()).physics_nodes,[1]);
   for(let step=3;step>=0;step--){await page.locator('#back').click();await page.locator(`[data-step="${step}"]`).waitFor({state:'visible'});}
   assert.equal(await mesh(1).isChecked(),true);assert.equal(await mesh(2).isChecked(),false);
  }
  // Legacy fingerprint remains supported; a physics-specific fingerprint wins
  // over stale optional wardrobe data. Different sources never reuse node IDs.
  await start();await importJSON({...legacy,physics_nodes:[1]});await sourceFile();assert.equal(await mesh(1).isChecked(),true);
  await sourceFile('other.vrm');assert.equal(await mesh(1).isChecked(),false);assert.equal(await page.locator('#physics-warning').isVisible(),true);
  await page.locator('#language').selectOption('en');assert.match(await page.locator('#physics-warning').textContent(),/different VRM/);
  // Settings saved on another VRM, in either file order: the warning shows on STEP 01 and
  // a selection made again here is sent with this VRM's fingerprint.
  for(const jsonFirst of [true,false]){
   await start();if(jsonFirst)await importJSON(saved);await sourceFile('other.vrm');if(!jsonFirst)await importJSON(saved);
   assert.equal(await page.locator('#physics-warning').isVisible(),true);assert.equal(await mesh(1).isChecked(),false);
   await mesh(1).check();await review();
   assert.deepEqual(submitted.at(-1).physics_nodes,[1]);assert.equal(submitted.at(-1).physics_source_sha256,'b'.repeat(64));
  }
  await start();await importJSON({...saved,appearance_source_sha256:'b'.repeat(64)});await sourceFile();assert.equal(await mesh(1).isChecked(),true);
  await start();await importJSON({...saved,physics_nodes:[1,999]});await sourceFile();assert.equal(await mesh(1).isChecked(),true);assert.equal(await page.locator('#physics-warning').isVisible(),true);
  await page.screenshot({path:path.join(fixture,'physics-settings-warning.png'),fullPage:true});
  // A fresh conversion without any imported JSON follows the same save path.
  await start();await sourceFile();await page.locator('#physics_enabled').check();await mesh(2).check();
  await page.locator('#physics_enabled').uncheck();await page.locator('#physics_enabled').check();assert.equal(await mesh(2).isChecked(),true);
  await review();assert.deepEqual((await save()).physics_nodes,[2]);
  await page.locator('#create').click();await page.locator('#result').waitFor({state:'visible'});
  await page.locator('#again').click();await page.locator('[data-step="0"]').waitFor({state:'visible'});
  assert.equal(await page.locator('#physics-meshes input').count(),0);
  await sourceFile();assert.equal(await mesh(2).isChecked(),false,'new follower cannot inherit old mesh selections');
  // The appearance control is visible in STEP 01, enabled by the shared
  // default, and an explicit OFF survives language/navigation/JSON roundtrips.
  await start();
  const toon=page.locator('#toon_enabled');
  assert.equal(await toon.isVisible(),true);assert.equal(await toon.isChecked(),true);
  assert.equal(await toon.evaluate(e=>e.closest('[data-step]').dataset.step),'0');
  assert.equal(await page.locator('[data-step="1"] #toon_enabled').count(),0);
  await sourceFile();await toon.uncheck();await page.locator('#language').selectOption('en');
  assert.equal(await toon.isChecked(),false);assert.match(await toon.locator('..').textContent(),/Toon shading/);
  await page.screenshot({path:path.join(fixture,'toon-step01-en.png'),fullPage:true});
  await review();const toonOff=await save();assert.equal(toonOff.toon_enabled,false);
  assert.equal(submitted.at(-1).toon_enabled,false);
  const toonSummary=()=>page.locator('#summary dt').filter({hasText:/^(Toon shading|トゥーン描画)$/}).locator('xpath=following-sibling::dd[1]');
  assert.equal(await toonSummary().textContent(),'Disabled');
  await page.locator('#language').selectOption('ja');assert.equal(await toonSummary().textContent(),'無効');
  await start();await importJSON(toonOff);await page.waitForFunction(()=>!document.querySelector('#toon_enabled').checked);
  assert.equal(await toon.isChecked(),false);
  // An older JSON without this key follows the default, even after importing OFF.
  const oldJSON={...toonOff};delete oldJSON.toon_enabled;await importJSON(oldJSON);
  await page.waitForFunction(()=>document.querySelector('#toon_enabled').checked);
  assert.match(await toon.locator('..').textContent(),/トゥーン描画/);
  await sourceFile();await review();assert.equal((await save()).toon_enabled,true);
  assert.equal(await toonSummary().textContent(),'有効');
  for(let step=3;step>=0;step--){await page.locator('#back').click();await page.locator(`[data-step="${step}"]`).waitFor({state:'visible'});}
  await page.screenshot({path:path.join(fixture,'toon-step01-ja.png'),fullPage:true});
  assert.equal(await toon.isChecked(),true);
  // The shipped shader ZIP downloads beside the STEP 01 checkbox and on the
  // result page. The game's Data/Shaders hashes select the message: the
  // supported originals and an installed ZIP inform; other or unreadable
  // shaders warn. Both languages; toon shading stays selectable.
  async function shaderState(name,available=true){
   toonShader={archive,available,release:'1.0.22',state:name};const game='Fixture game '+shaderRequests.length;
   await page.locator('#game').fill(game);await page.locator('#game').dispatchEvent('change');
   await page.waitForFunction(({game,name,available})=>document.querySelector('#game').value===game&&state.toonShader?.state===name&&state.toonShader?.available===available,{game,name,available});
   assert.equal(shaderRequests.at(-1),game);
  }
  const shaderLink=page.locator('#toon-shader-download'),shaderStatus=page.locator('#toon-shader-status');
  const kind=()=>shaderStatus.evaluate(e=>e.dataset.kind+':'+e.className);
  const originalText={ja:/Community ShadersはこのZIPの対象（Bottled Shaders 1\.0\.22）です。次に、トゥーン描画用シェーダーのZIPを保存してVortex \/ MO2で導入してください。/,
   en:/Community Shaders is the release this ZIP is for \(Bottled Shaders 1\.0\.22\)\. Next, save the toon shader ZIP and install it with Vortex \/ MO2\./};
  const installedText={ja:/トゥーン描画用シェーダー（VRM2Skyrim-Toon-Shader-0\.13\.0\.zip）は導入済みです。/,
   en:/The toon shader \(VRM2Skyrim-Toon-Shader-0\.13\.0\.zip\) is installed\./};
  const otherText={ja:/導入されているCommunity Shadersのシェーダーは、このZIPの対象と異なります。このZIPはBottled Shaders 1\.0\.22用のため、このCommunity Shadersでは描画が崩れる場合があります。/,
   en:/The installed Community Shaders shaders differ from the ones this ZIP is for\. This ZIP is for Bottled Shaders 1\.0\.22 and may break rendering with this Community Shaders\./};
  const uncheckedText={ja:/Community Shadersの版を確認できませんでした（MO2ではシェーダーがMO2のmodsフォルダに置かれます）。このZIPはBottled Shaders 1\.0\.22用です。/,
   en:/Could not check the Community Shaders release \(MO2 keeps the shaders in its own mods folder\)\. This ZIP is for Bottled Shaders 1\.0\.22\./};
  await start();await sourceFile();await page.waitForFunction(()=>state.toonShader?.state==='original');
  assert.equal(shaderRequests.at(-1),'Read-only fixture');
  assert.equal(await shaderLink.textContent(),'トゥーン描画用シェーダーをダウンロード');assert.equal(await shaderLink.isVisible(),true);
  assert.equal(await shaderLink.evaluate(e=>e.closest('[data-step]').dataset.step+':'+!!e.closest('#toon-settings')),'0:true');
  assert.equal(await shaderStatus.isVisible(),true,'the supported release shows the download as the next step');
  assert.match(await shaderStatus.textContent(),originalText.ja);assert.equal(await kind(),'information:hint','no warning for the supported release');
  const shaderDownload=page.waitForEvent('download');await shaderLink.click();assert.equal((await shaderDownload).suggestedFilename(),archive);
  for(const language of ['ja','en']){
   await page.locator('#language').selectOption(language);
   assert.equal(await shaderLink.textContent(),{ja:'トゥーン描画用シェーダーをダウンロード',en:'Download the toon shader'}[language]);
   await shaderState('other');assert.equal(await shaderStatus.isVisible(),true);assert.match(await shaderStatus.textContent(),otherText[language]);
   assert.equal(await kind(),'warning:note');
   await toon.uncheck();assert.equal(await shaderStatus.isVisible(),false,'warning only while toon shading is on');
   await toon.check();assert.equal(await shaderStatus.isVisible(),true);assert.equal(await toon.isEnabled(),true);
   await shaderState('unchecked');assert.match(await shaderStatus.textContent(),uncheckedText[language]);assert.equal(await kind(),'warning:note');
   await page.screenshot({path:path.join(fixture,`toon-shader-step01-${language}.png`),fullPage:true});
   await shaderState('original');assert.match(await shaderStatus.textContent(),originalText[language]);assert.equal(await kind(),'information:hint');
   await shaderState('installed');assert.match(await shaderStatus.textContent(),installedText[language]);assert.equal(await kind(),'information:hint');
   assert.equal(await shaderLink.isVisible(),true);
  }
  // A shown warning follows a language change without another check.
  await shaderState('other');const requests=shaderRequests.length;
  await page.locator('#language').selectOption('ja');assert.match(await shaderStatus.textContent(),otherText.ja);assert.equal(shaderRequests.length,requests);
  await shaderState('original',false);assert.equal(await shaderLink.isVisible(),false);
  assert.match(await shaderStatus.textContent(),/トゥーン描画用シェーダーのZIP（VRM2Skyrim-Toon-Shader-0\.13\.0\.zip）が見つかりません。/);
  assert.equal(await kind(),'warning:note');
  // The result page repeats the download and the warning for a toon follower.
  await shaderState('unchecked');await review();await page.locator('#create').click();await page.locator('#result').waitFor({state:'visible'});
  const resultLink=page.locator('#toon-shader-result-download'),resultStatus=page.locator('#toon-shader-result-status');
  await resultStatus.waitFor({state:'visible'});assert.equal(await resultLink.isVisible(),true);
  assert.equal(await resultLink.textContent(),'トゥーン描画用シェーダーをダウンロード');assert.match(await resultStatus.textContent(),uncheckedText.ja);
  const resultDownload=page.waitForEvent('download');await resultLink.click();assert.equal((await resultDownload).suggestedFilename(),archive);
  toonShader={archive,available:true,release:'1.0.22',state:'other'};await page.locator('#language').selectOption('en');
  assert.equal(await resultLink.textContent(),'Download the toon shader');assert.match(await resultStatus.textContent(),uncheckedText.en);
  await page.locator('#again').click();await page.locator('[data-step="0"]').waitFor({state:'visible'});
  jobToon=false;await sourceFile();await review();await page.locator('#create').click();await page.locator('#result').waitFor({state:'visible'});
  await page.waitForFunction(()=>state.toonShader?.state==='other');
  assert.equal(await page.locator('#toon-shader-result').isVisible(),false,'no shader download for a follower without toon shading');
  assert.deepEqual(errors,[]);console.log('PASS physics mesh persistence: navigation, downloaded JSON, both import orders, source guards and localization');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
