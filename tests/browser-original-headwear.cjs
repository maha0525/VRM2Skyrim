/* Real wizard controls, isolated mocked APIs; does not launch a conversion. */
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),out=path.join(root,'build/ui-headwear');fs.mkdirSync(out,{recursive:true});
const defaults=JSON.parse(fs.readFileSync(path.join(root,'build/ui-roles/defaults.json')));
const choices=JSON.parse(fs.readFileSync(path.join(root,'build/ui-roles/roles.json')));
const actualSource=path.join(root,'build/headwear/Cecil_0.10.0/source.json');
const source=fs.existsSync(actualSource)?JSON.parse(fs.readFileSync(actualSource)):{sha256:'a'.repeat(64),total_triangles:8,parts:[
 {node:392,name:'Body',triangles:2,materials:['Skin'],suggested_role:'body'},
 {node:387,name:'Face',triangles:2,materials:['Face'],suggested_role:'fixed'},
 {node:396,name:'Hair',triangles:2,materials:['Hair'],suggested_role:'fixed'},
 {node:405,name:'Obj135',triangles:2,materials:['Hat'],suggested_role:'fixed'}]};
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome',downloadsPath:out});
 try {
  const page=await browser.newPage({acceptDownloads:true,viewport:{width:1440,height:1100}}),errors=[];let preview;
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url());let data;
   if(url.pathname==='/api/environment')data={defaults,game:'Fixture',blender:'Fixture',version:'test'};
   else if(url.pathname==='/api/jobs')data={jobs:[]};
   else if(url.pathname==='/api/source')data={...source,source_id:'fixture',filename:'Cecil.vrm',mesh_count:source.parts.length,triangles:source.total_triangles,suggested_name:'Cecil'};
   else if(url.pathname==='/api/catalog')data={checks:{ready:true},choices:{...choices,armors:[],equipment_plugins:[]}};
   else if(url.pathname==='/api/validate')data={settings:req.postDataJSON().settings};
   else if(url.pathname==='/api/appearance-preview'){preview=req.postDataJSON();data={job_id:'preview'};}
   else if(url.pathname==='/api/jobs/preview')data={status:'complete',previews:[]};
   if(data!==undefined)return route.fulfill({json:data});
   const name=url.pathname==='/'?'index.html':url.pathname.slice(1),file=path.join(root,'web',name);
   if(!fs.existsSync(file))return route.fulfill({status:404,body:'not found'});
   return route.fulfill({body:fs.readFileSync(file),contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html'});
  });
  await page.goto('http://127.0.0.1:8899/');
  await page.waitForFunction(()=>document.querySelector('#game').value.length>0);
  await page.locator('#source').setInputFiles({name:'Cecil.vrm',mimeType:'application/octet-stream',buffer:Buffer.from('fixture')});
  await page.waitForFunction(()=>document.querySelector('#source-status').textContent.includes('三角形'));
  await page.locator('#armor_support').selectOption('true');
  await page.locator('.wardrobe-part[data-node="392"] select').first().selectOption('body');
  await page.locator('.wardrobe-part[data-node="387"] select').first().selectOption('face');
  await page.locator('.wardrobe-part[data-node="396"] select').first().selectOption('hair');
  await page.locator('#wardrobe-add').click();
  await page.locator('.wardrobe-part[data-node="405"] select').first().selectOption('garment');
  const hat=page.locator('.wardrobe-item[data-garment="item_1"]');await hat.locator('summary').click();
  await hat.locator('[data-field="item_kind"]').selectOption('head');
  assert.match(await hat.locator('[data-field="slot"] option:checked').textContent(),/30/);
  assert.equal(await hat.locator('[data-field="slot"] option[value="31"]').count(),1);
  assert.equal(await hat.locator('[data-field="hide_face"]').isChecked(),false);
  assert.equal(await hat.locator('[data-field="hide_hair"]').isChecked(),false);
  await hat.locator('[data-field="hide_hair"]').check();
  await page.locator('#wardrobe-preview').click();
  await page.waitForFunction(()=>document.querySelector('#wardrobe-preview-status').textContent.includes('確認できます'));
  const garment=preview.settings.appearance_parts.garments[0];
  assert.equal(garment.item_kind,'head');assert.equal(garment.slot,30);assert.equal(garment.hide_hair,true);
  assert.deepEqual(garment.nodes,[405]);assert.ok(preview.settings.appearance_heads.hair.includes(396));
  await hat.screenshot({path:path.join(out,'headwear-settings.png')});
  for(let i=0;i<4;i++)await page.locator('#next').click();
  const downloading=page.waitForEvent('download');await page.locator('#export-settings').click();
  const file=path.join(out,'settings.json');await(await downloading).saveAs(file);
  const exported=JSON.parse(fs.readFileSync(file));assert.equal(exported.appearance_parts.garments[0].hide_hair,true);
  for(let i=0;i<4;i++)await page.locator('#back').click();
  await page.locator('#import-settings').setInputFiles(file);
  await page.waitForFunction(()=>document.querySelector('#import-status').textContent.includes('読み込みました'));
  const imported=page.locator('.wardrobe-item').first();
  if(!await imported.evaluate(el=>el.open))await imported.locator('summary').click();
  assert.equal(await imported.locator('[data-field="item_kind"]').inputValue(),'head');
  assert.equal(await imported.locator('[data-field="hide_hair"]').isChecked(),true);
  await imported.locator('[data-field="item_kind"]').selectOption('body');
  assert.equal(await imported.locator('[data-field="hide_hair"]').count(),0);
  await imported.locator('[data-field="item_kind"]').selectOption('head');
  assert.equal(await imported.locator('[data-field="hide_hair"]').isChecked(),false);
  assert.deepEqual(errors,[]);
  console.log('Obj135 -> headwear slot30 -> optional hair policy -> preview/export/import PASS');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
