/* Exercise creation -> again -> saved-result reopening in an isolated browser. */
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const defaults=JSON.parse(fs.readFileSync(path.join(root,'build/ui-roles/defaults.json')));
const choice=id=>[{id,label:id,humanoid:true,used_by:[]}];
const choices={voices:choice(defaults.voice),classes:choice(defaults.combat_class),styles:choice(defaults.combat_style),weapons:choice(defaults.weapon),ammunition:[],perks:[],spells:[],armors:[],equipment_plugins:[],marriage_voices:[]};
const completed=id=>({id,npc_name:'New Follower',plugin_name:'SameFollower.esp',status:'complete',archive:id+'.zip',output:'fixture',previews:[],events:[],stage:'complete'});
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  for(const initiallyEmpty of [true,false]){
   const page=await browser.newPage({locale:'ja-JP'});const errors=[];page.on('pageerror',e=>errors.push(e.message));
   let jobs=initiallyEmpty?[]:[{...completed('old'),npc_name:'Old Follower'}],failList=false,listReads=0;
   await page.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());let data;
    if(url.pathname==='/api/environment')data={defaults,game:'Fixture Game',blender:'Fixture Blender',version:'test'};
    else if(url.pathname==='/api/jobs'&&request.method()==='POST'){
     const job=completed('new-'+jobs.length);jobs.push(job);data={job_id:job.id};
    }else if(url.pathname==='/api/jobs'){
     listReads++;if(failList)return route.fulfill({status:500,json:{error:'fixture list failure'}});
     data={jobs};
    }else if(url.pathname.startsWith('/api/jobs/'))data=jobs.find(job=>job.id===url.pathname.split('/')[3]);
    else if(url.pathname==='/api/source')data={source_id:'fixture',sha256:'fixture',filename:'fixture.vrm',mesh_count:1,triangles:1,suggested_name:'New Follower',parts:[]};
    else if(url.pathname==='/api/catalog')data={checks:{ready:true},choices};
    else if(url.pathname==='/api/validate')data={settings:request.postDataJSON().settings};
    if(data!==undefined)return route.fulfill({json:data});
    const name=url.pathname==='/'?'index.html':url.pathname.slice(1),file=path.join(root,'web',name);
    if(!fs.existsSync(file))return route.fulfill({status:404,body:'not found'});
    return route.fulfill({body:fs.readFileSync(file),contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html'});
   });
   await page.goto('http://127.0.0.1:8899/');
   await page.waitForFunction(()=>document.querySelector('#game').value.length>0);
   await page.waitForTimeout(100);
   assert.equal(await page.locator('#saved-results').isVisible(),!initiallyEmpty);
   for(let iteration=0;iteration<2;iteration++){
    await page.locator('#source').setInputFiles({name:'fixture.vrm',mimeType:'application/octet-stream',buffer:Buffer.from('fixture')});
    await page.waitForFunction(()=>document.querySelector('#source-status').textContent.includes('三角形'));
    for(let step=1;step<5;step++){
     await page.locator('#next').click();await page.locator(`[data-step="${step}"]`).waitFor({state:'visible'});
     assert.equal(await page.locator('#saved-results').isVisible(),false);
    }
    await page.locator('#create').click();await page.locator('#result').waitFor({state:'visible'});
    const id=jobs.at(-1).id,readsBefore=listReads;
    await page.locator('#again').click();await page.locator('[data-step="0"]').waitFor({state:'visible'});
    await page.waitForFunction(id=>document.querySelector('#saved-job').value===id,id);
    assert.equal(await page.locator('#saved-results').isVisible(),true);
    assert.equal(await page.locator('#saved-job option').count(),jobs.length);
    assert.equal(listReads,readsBefore+1);
    await page.locator('#open-saved').click();await page.locator('#result').waitFor({state:'visible'});
    assert.ok((await page.locator('#download').getAttribute('href')).includes('/'+id+'/'));
    await page.locator('#again').click();await page.locator('[data-step="0"]').waitFor({state:'visible'});
    await page.waitForFunction(id=>document.querySelector('#saved-job').value===id,id);
   }
   const selected=await page.locator('#saved-job').inputValue(),count=await page.locator('#saved-job option').count();
   await page.locator('#open-saved').click();await page.locator('#result').waitFor({state:'visible'});
   failList=true;await page.locator('#again').click();await page.locator('#error').waitFor({state:'visible'});
   assert.match(await page.locator('#error').textContent(),/一覧を更新できませんでした.*fixture list failure/);
   assert.equal(await page.locator('#saved-job').inputValue(),selected);
   assert.equal(await page.locator('#saved-job option').count(),count);
   assert.equal(await page.locator('[data-step="0"]').isVisible(),true);
   failList=false;jobs=[completed(selected)];
   await page.locator('#open-saved').click();await page.locator('#result').waitFor({state:'visible'});
   jobs=[];await page.locator('#again').click();await page.locator('#saved-results').waitFor({state:'hidden'});
   assert.equal(await page.locator('#saved-job option').count(),0);
   assert.deepEqual(errors,[]);await page.close();
  }
  console.log('PASS: new completions appear on again, latest job selected, same-plugin results retained, saved ZIP reopening, empty initial/history states and refresh failure recovery');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
