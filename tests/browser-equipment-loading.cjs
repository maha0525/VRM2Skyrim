/* Slow catalog loading must be visible and block premature navigation. */
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),fixture=path.join(root,'build/ui-roles');
const defaults=JSON.parse(fs.readFileSync(path.join(fixture,'defaults.json'),'utf8'));
const choices=JSON.parse(fs.readFileSync(path.join(fixture,'roles.json'),'utf8'));
const source={source_id:'fixture',sha256:'a'.repeat(64),filename:'fixture.vrm',mesh_count:3,triangles:30,suggested_name:'Test',parts:[
 {node:0,name:'Body',triangles:10,materials:['body'],suggested_role:'body'},
 {node:1,name:'Face',triangles:10,materials:['face'],suggested_role:'fixed'},
 {node:2,name:'Shirt',triangles:10,materials:['cloth'],suggested_role:'garment'}]};
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  const page=await browser.newPage({locale:'en-US',acceptDownloads:true,viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let release,calls=0,fail=false,headDone=false;
  let gate=new Promise(resolve=>release=resolve);
  await page.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url());let data;
   if(url.pathname==='/api/environment')data={defaults,game:'Fixture',blender:'Fixture',version:'test'};
   else if(url.pathname==='/api/jobs')data={jobs:[]};
   else if(url.pathname==='/api/source')data=source;
   else if(url.pathname==='/api/catalog'){
    calls++;await gate;if(fail)return route.fulfill({status:400,json:{error:'Catalog fixture failure'}});
    data={checks:{ready:true},choices};
   }
   else if(url.pathname==='/api/validate')data={settings:req.postDataJSON().settings};
   else if(url.pathname==='/api/head-preview')data={job_id:'head'};
   else if(url.pathname==='/api/jobs/head')data={id:'head',status:headDone?'complete':'running',stage:headDone?'頭装備のプレビューを更新しました':'アバターを初回準備しています（約1分かかる場合があります）',previews:[]};
   if(data!==undefined)return route.fulfill({json:data});
   const name=url.pathname==='/'?'index.html':url.pathname.slice(1),file=path.join(root,'web',name);
   return route.fulfill({body:fs.readFileSync(file),contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html'});
  });
  async function start(){
   await page.goto('http://127.0.0.1:8899/');await page.waitForFunction(()=>document.querySelector('#game').value.length>0);
   await page.locator('#source').setInputFiles({name:'fixture.vrm',mimeType:'application/octet-stream',buffer:Buffer.from('fixture')});
   await page.waitForFunction(()=>document.querySelector('#source-status').textContent.includes('fixture.vrm'));
   await page.locator('#armor_support').selectOption('true');
  }
  await start();assert.equal(await page.locator('#fit_mode').inputValue(),'all_official');
  await page.locator('#fit-enabled').check();
  await page.locator('#catalog-status').waitFor({state:'visible'});
  assert.match(await page.locator('#catalog-status').textContent(),/Loading the equipment list/);
  assert.equal(await page.locator('#next').isDisabled(),true);assert.equal(await page.locator('#next').textContent(),'Loading…');
  assert.equal(await page.locator('#fit-panel').getAttribute('aria-busy'),'true');assert.equal(calls,1);
  const uploaded=page.waitForResponse(r=>r.url().endsWith('/api/source'));
  await page.locator('#source').setInputFiles({name:'fixture.vrm',mimeType:'application/octet-stream',buffer:Buffer.from('reload')});await uploaded;
  await page.waitForFunction(()=>document.querySelector('#source-status').textContent.includes('fixture.vrm'));
  assert.equal(await page.locator('#next').isDisabled(),true,'Finishing a VRM upload cannot unlock a pending catalog request');
  await page.locator('#language').selectOption('ja');assert.match(await page.locator('#catalog-status').textContent(),/一覧を読み込んでいます/);
  assert.equal(await page.locator('#next').isDisabled(),true);
  await page.locator('#fit-enabled').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(fixture,'catalog-loading-ja.png')});
  release();gate=Promise.resolve();
  await page.waitForFunction(()=>!document.querySelector('#next').disabled);
  assert.equal(await page.locator('#fit-selection').isVisible(),false);
  await page.locator('#next').click();await page.locator('[data-step="1"]').waitFor({state:'visible'});assert.equal(calls,1,'Next reuses the loaded catalog');
  await page.locator('#back').click();
  const helmet=choices.armors.find(item=>item.editor_id==='ArmorElvenHelmet');assert.ok(helmet);
  await page.locator('#import-settings').setInputFiles({name:'selected.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({...defaults,armor_support:true,fit_mode:'selected',fit_armors:[helmet.id]}))});
  await page.waitForFunction(()=>document.querySelector('#import-status').textContent.length>0);
  assert.equal(await page.locator('#fit_mode').inputValue(),'selected');assert.equal(await page.locator('#fit-armors').inputValue(),helmet.id);
  await page.locator('#fit-panel details summary').click();
  assert.match(await page.locator('#fit-panel').textContent(),/初回プレビュー.*約1分/);
  await page.locator('#head-preview').click();await page.waitForFunction(()=>document.querySelector('#head-preview-status').textContent.includes('初回準備'));
  assert.equal(await page.locator('#head-preview').isDisabled(),true);
  await page.locator('#language').selectOption('en');assert.match(await page.locator('#head-preview-status').textContent(),/about a minute/);
  assert.equal(await page.locator('#head-preview').isDisabled(),true);headDone=true;
  await page.waitForFunction(()=>!document.querySelector('#head-preview').disabled);
  fail=true;await start();await page.locator('#fit-enabled').check();
  await page.waitForFunction(()=>document.querySelector('#catalog-status').textContent.includes('Could not load'));
  assert.equal(await page.locator('#next').isDisabled(),false);
  fail=false;await page.locator('#fit-enabled').check();await page.waitForFunction(()=>!document.querySelector('#next').disabled&&document.querySelector('#fit-enabled').checked);
  assert.equal(await page.locator('#error').isVisible(),false);assert.equal(calls,3);
  assert.deepEqual(errors,[]);console.log('PASS slow catalog feedback, blocked Next, default all, imported selection, request reuse/retry and head preview guidance');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
