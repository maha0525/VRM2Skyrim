/* Automatic hair classification from materials, and the question before leaving STEP 01 without hair. */
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),fixture=path.join(root,'build/ui-roles');
const defaults=JSON.parse(fs.readFileSync(path.join(fixture,'defaults.json'),'utf8'));
const choices=JSON.parse(fs.readFileSync(path.join(fixture,'roles.json'),'utf8'));
const source={source_id:'hair',sha256:'a'.repeat(64),filename:'hair.vrm',mesh_count:4,triangles:40,suggested_name:'Test',parts:[
 {node:0,name:'Body',triangles:10,materials:['Material_lower_body'],suggested_role:'body'},
 {node:1,name:'Head',triangles:10,materials:['Material_head','Material_inner_hair'],suggested_role:'fixed'},
 {node:2,name:'Spring_01_bob',triangles:10,materials:['Material_hair'],suggested_role:'fixed'},
 {node:3,name:'Spring_02_ornament',triangles:10,materials:['Material_accessories'],suggested_role:'fixed'}]};
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  const page=await browser.newPage({locale:'ja-JP'});
  const errors=[],dialogs=[];let answer=false;
  page.on('pageerror',e=>errors.push(e.message));
  page.on('dialog',d=>{dialogs.push(d.message());return answer?d.accept():d.dismiss();});
  await page.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url());let data;
   if(url.pathname==='/api/environment')data={defaults,game:'Read-only fixture',blender:'Fixture Blender',version:'test'};
   else if(url.pathname==='/api/jobs')data={jobs:[]};
   else if(url.pathname==='/api/toon-shader-status')data={archive:'x.zip',available:true,release:'1.0.22',state:'original'};
   else if(url.pathname==='/api/source')data=source;
   else if(url.pathname==='/api/catalog')data={checks:{ready:true},choices:{...choices,armors:[],equipment_plugins:[]}};
   else if(url.pathname==='/api/validate')data={settings:request.postDataJSON().settings};
   if(data!==undefined)return route.fulfill({json:data});
   const name=url.pathname==='/'?'index.html':url.pathname.slice(1),file=path.join(root,'web',name);
   return route.fulfill({body:fs.readFileSync(file),contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html'});
  });
  const role=node=>page.locator(`.wardrobe-part[data-node="${node}"] select`).first();
  const onStep=step=>page.locator(`[data-step="${step}"]`).isVisible();
  async function start(armor=true){
   await page.goto('http://127.0.0.1:8899/');await page.waitForFunction(()=>document.querySelector('#game').value.length>0);
   await page.locator('#armor_support').selectOption(String(armor));
   const response=page.waitForResponse(r=>r.url().endsWith('/api/source'));
   await page.locator('#source').setInputFiles({name:'hair.vrm',mimeType:'application/octet-stream',buffer:Buffer.from('vrm')});await response;
   await page.waitForFunction(()=>!document.querySelector('#next').disabled);
  }
  // The material finds the hair without the word in the mesh name; a head with hair material stays the face.
  await start();
  assert.equal(await role(2).inputValue(),'hair');assert.equal(await role(1).inputValue(),'face');assert.equal(await role(3).inputValue(),'fixed');
  await page.locator('#next').click();await page.locator('[data-step="1"]').waitFor({state:'visible'});
  assert.deepEqual(dialogs,[],'a classified hair mesh asks nothing');
  // Without hair the user is asked, stays on STEP 01 when declining, and can still continue.
  await start();await role(2).selectOption('body');
  await page.locator('#next').click();await page.waitForFunction(()=>!document.querySelector('#next').disabled);
  assert.equal(dialogs.length,1);assert.match(dialogs[0],/「髪」に分類したメッシュがありません/);assert.equal(await onStep(0),true);
  answer=true;await page.locator('#next').click();await page.locator('[data-step="1"]').waitFor({state:'visible'});
  assert.equal(dialogs.length,2);
  // The same question in English; going back and fixing the role removes it.
  answer=false;await start();await page.locator('#language').selectOption('en');await role(2).selectOption('fixed');
  await page.locator('#next').click();await page.waitForFunction(()=>!document.querySelector('#next').disabled);
  assert.match(dialogs.at(-1),/No mesh is classified as Hair/);
  const count=dialogs.length;await role(2).selectOption('hair');
  await page.locator('#next').click();await page.locator('[data-step="1"]').waitFor({state:'visible'});
  assert.equal(dialogs.length,count);
  // Without clothing separation every mesh ships as one avatar; there is no hair role to ask about.
  await start(false);await page.locator('#next').click();await page.locator('[data-step="1"]').waitFor({state:'visible'});
  assert.equal(dialogs.length,count);
  assert.deepEqual(errors,[]);console.log('PASS hair classification from materials and the missing hair question');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
