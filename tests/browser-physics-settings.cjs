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
  const errors=[],submitted=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url());let data;
   if(url.pathname==='/api/environment')data={defaults,game:'Read-only fixture',blender:'Fixture Blender',version:'test'};
   else if(url.pathname==='/api/jobs')data=request.method()==='POST'?{job_id:'completed'}:{jobs:[]};
   else if(url.pathname==='/api/jobs/completed')data={id:'completed',status:'complete',stage:'Complete',events:[],npc_name:'Test',plugin_name:'Test.esp',archive:'Test.zip',output:'Fixture',previews:[]};
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
  assert.deepEqual(errors,[]);console.log('PASS physics mesh persistence: navigation, downloaded JSON, both import orders, source guards and localization');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
