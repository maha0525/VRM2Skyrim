/* User-facing language controls, real game labels and unchanged conversion settings. */
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),vm=require('node:vm');
const root=path.resolve(__dirname,'..'),fixture=path.join(root,'build/ui-roles');
const defaults=JSON.parse(fs.readFileSync(path.join(fixture,'defaults.json')));
const choices=JSON.parse(fs.readFileSync(path.join(fixture,'roles.json')));
const translations=vm.runInNewContext(fs.readFileSync(path.join(root,'web/translations.js'),'utf8')+';englishUI');
for(const file of ['wizard.js','wardrobe.js'])for(const match of fs.readFileSync(path.join(root,'web',file),'utf8').matchAll(/\btr\(("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')/g)){
 const key=vm.runInNewContext(match[1]);assert.ok(Object.hasOwn(translations,key),`Missing English UI message: ${key}`);
}
const source={source_id:'fixture',sha256:'a'.repeat(64),filename:'テスト.vrm',mesh_count:5,triangles:50,suggested_name:'スミレ',parts:[
 {node:0,name:'Body',triangles:10,materials:['body'],suggested_role:'body'},
 {node:1,name:'Face',triangles:10,materials:['face'],suggested_role:'fixed'},
 {node:2,name:'Hair',triangles:10,materials:['hair'],suggested_role:'fixed'},
 {node:3,name:'Shirt',triangles:10,materials:['shirt'],suggested_role:'garment'},
 {node:4,name:'Hat',triangles:10,materials:['hat'],suggested_role:'garment'}]};
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  const context=await browser.newContext({locale:'en-US',viewport:{width:1440,height:1100},acceptDownloads:true});
  let jobStatus='running',catalogMissing=false;const errors=[];
  await context.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url());let data;
   if(url.pathname==='/api/environment')data={defaults,game:'Read-only fixture',blender:'Fixture Blender',version:'test'};
   else if(url.pathname==='/api/jobs')data=request.method()==='POST'?{job_id:'new'}:{jobs:[]};
   else if(url.pathname==='/api/source')data=source;
   else if(url.pathname==='/api/catalog'){
    const subset=structuredClone(choices);if(catalogMissing)for(const kind of ['perks','spells','classes','weapons','armors'])for(const item of subset[kind]){item.labels.en=item.id;item.descriptions={ja:item.description||'',en:''};}
    data={checks:{ready:true},choices:subset};
   }
   else if(url.pathname==='/api/validate')data={settings:request.postDataJSON().settings};
   else if(url.pathname==='/api/jobs/new')data={id:'new',status:jobStatus,stage:'FSMPの髪・布物理設定',events:['入力と設定の検査','骨格・モデルの変換'],npc_name:'スミレ',plugin_name:'Sumire.esp',archive:'Sumire.zip',output:'C:/fixture/スミレ',previews:[],error:'先にVRMを選択してください'};
   if(data!==undefined)return route.fulfill({json:data});
   const name=url.pathname==='/'?'index.html':url.pathname.slice(1),file=path.join(root,'web',name);
   if(!fs.existsSync(file))return route.fulfill({status:404,body:'not found'});
   return route.fulfill({body:fs.readFileSync(file),contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html'});
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8899/');await page.waitForFunction(()=>document.querySelector('#game').value.length>0);
  assert.equal(await page.locator('html').getAttribute('lang'),'en');
  assert.equal(await page.locator('#next').textContent(),'Next →');
  const missing=await page.evaluate(({dict,html})=>{const copy=new DOMParser().parseFromString(html,'text/html'),nodes=[],walker=document.createTreeWalker(copy,NodeFilter.SHOW_TEXT);while(walker.nextNode()){const n=walker.currentNode,s=n.textContent.trim();if(/[\u3040-\u30ff\u3400-\u9fff]/.test(s)&&!n.parentElement.closest('script,style,[data-no-i18n]')&&!Object.hasOwn(dict,s))nodes.push(s);}for(const e of copy.querySelectorAll('[placeholder],[aria-label],[title]'))if(!e.closest('[data-no-i18n]'))for(const attr of ['placeholder','aria-label','title']){const s=e.getAttribute(attr);if(s&&/[\u3040-\u30ff\u3400-\u9fff]/.test(s)&&!Object.hasOwn(dict,s))nodes.push(s);}return nodes;},{dict:translations,html:fs.readFileSync(path.join(root,'web/index.html'),'utf8')});
  assert.deepEqual(missing,[]);
  await page.locator('#source').setInputFiles({name:'テスト.vrm',mimeType:'application/octet-stream',buffer:Buffer.from('fixture')});
  await page.waitForFunction(()=>document.querySelector('#source-status').textContent.includes('triangles'));
  await page.locator('#armor_support').selectOption('true');
  await page.locator('#wardrobe-garments details').first().locator('summary').click();
  const garment=page.locator('#wardrobe-garments [data-field="name"]').first();await garment.fill('旅の衣服');await garment.dispatchEvent('change');
  const helmet=choices.armors.find(item=>item.editor_id==='ArmorElvenHelmet');assert.ok(helmet);
  await page.locator('#fit-enabled').check();await page.waitForFunction(()=>document.querySelector('#fit-armors').options.length>0);
  await page.locator('#fit_mode').selectOption('selected');await page.locator('#fit-armors').selectOption(helmet.id);
  assert.match(await page.locator('#fit-armors option:checked').textContent(),/Elven Helmet/);
  await page.locator('#head-policies').waitFor({state:'attached'});
  assert.match(await page.locator('#head-model option:checked').textContent(),/Elven Helmet/);
  await page.locator('#language').selectOption('ja');
  assert.equal(await page.locator('#next').textContent(),'次へ →');
  assert.equal(await page.locator('#source').evaluate(e=>e.files.length),1);
  assert.equal(await page.locator('#wardrobe-garments [data-field="name"]').first().inputValue(),'旅の衣服');
  assert.equal(await page.locator('#fit-armors').inputValue(),helmet.id);
  assert.match(await page.locator('#fit-armors option:checked').textContent(),/エルフ/);
  await page.locator('#language').selectOption('en');
  assert.equal(await page.locator('#wardrobe-garments [data-field="name"]').first().inputValue(),'旅の衣服');
  assert.match(await page.locator('#wardrobe-parts select').first().locator('option[value="face"]').textContent(),/Face/);
  await page.locator('#next').click();await page.locator('[data-step="1"]').waitFor({state:'visible'});
  await page.locator('#npc_name').fill('隠密');await page.locator('#mod_name').fill('旅の仲間');await page.locator('#mod_id').fill('Sumire');
  assert.equal(await page.locator('#voice').inputValue(),defaults.voice);
  await page.locator('#next').click();await page.locator('[data-step="2"]').waitFor({state:'visible'});
  assert.match(await page.locator('#class-details').textContent(),/One-Handed/);
  assert.equal(await page.locator('#protection option:checked').textContent(),'Essential: cannot be killed');
  assert.equal(await page.locator('#morality option:checked').textContent(),'Any Crime');
  await page.locator('#manual-skills summary').click();await page.locator('#use-manual-skills').click();
  await page.locator('#skill-Sneak').fill('73');
  await page.locator('#language').selectOption('ja');assert.equal(await page.locator('#skill-Sneak').inputValue(),'73');
  await page.locator('#language').selectOption('en');
  assert.equal(await page.locator('#npc_name').inputValue(),'隠密');assert.equal(await page.locator('#skill-Sneak').inputValue(),'73');
  await page.screenshot({path:path.join(fixture,'localization-english-step03.png'),fullPage:true});
  await page.locator('#next').click();await page.locator('[data-step="3"]').waitFor({state:'visible'});
  await page.locator('#perk-category').selectOption('Sneak');await page.locator('#perk-search').fill('Stealth');
  const stealth=page.locator('#perks label').filter({has:page.locator('input[data-record-id="Stealth80"]')});
  assert.match(await stealth.locator('strong').textContent(),/^Stealth \(stage 5\/5\)$/);
  const native=choices.perks.find(item=>item.id==='Stealth80');assert.match(await stealth.locator('small').textContent(),new RegExp(native.descriptions.en.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));
  await stealth.locator('input').check();
  await page.locator('#spell-category').selectOption('Destruction');await page.locator('#spell-search').fill('Firebolt');
  await page.locator('#spells input[data-record-id="Firebolt"]').check();
  await page.locator('#language').selectOption('ja');
  assert.equal(await page.locator('#perk-category').inputValue(),'Sneak');
  // Search text is user input and remains unchanged; selected tags still show native Japanese.
  assert.match(await page.locator('#selected-perks').textContent(),/隠術/);
  await page.locator('#language').selectOption('en');assert.match(await page.locator('#selected-perks').textContent(),/Stealth/);
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.locator('#language').isVisible());
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
  await page.screenshot({path:path.join(fixture,'localization-english-mobile.png'),fullPage:true});
  await page.setViewportSize({width:1440,height:1100});
  await page.screenshot({path:path.join(fixture,'localization-english-step04.png'),fullPage:true});
  await page.locator('#next').click();await page.locator('[data-step="4"]').waitFor({state:'visible'});
  const downloadPromise=page.waitForEvent('download');await page.locator('#export-settings').click();
  const exported=JSON.parse(fs.readFileSync(await (await downloadPromise).path(),'utf8'));
  assert.equal(exported.npc_name,'隠密');assert.equal(exported.mod_id,'Sumire');assert.equal(exported.skills.Sneak,73);
  assert.deepEqual(exported.perks,[{editor_id:'Stealth80',rank:0}]);assert.deepEqual(exported.spells,['Firebolt']);
  assert.deepEqual(exported.fit_armors,[helmet.id]);
  assert.ok(exported.appearance_parts.garments.some(g=>g.name==='旅の衣服'));assert.ok(!Object.hasOwn(exported,'language'));
  await page.locator('#create').click();await page.waitForFunction(()=>document.querySelector('#stage').textContent.includes('Generating FSMP'));
  await page.locator('#language').selectOption('ja');assert.equal(await page.locator('#stage').textContent(),'FSMPの髪・布物理設定');
  await page.locator('#language').selectOption('en');jobStatus='failed';
  await page.locator('#failure').waitFor({state:'visible'});assert.equal(await page.locator('#failure').textContent(),'Select a VRM first');
  // Retry through the actual button, then complete a synthetic job.
  jobStatus='complete';await page.locator('#create').click();await page.locator('#result').waitFor({state:'visible'});
  assert.equal(await page.locator('#result-title').textContent(),'スミレ in Skyrim!');
  await page.locator('#language').selectOption('ja');assert.equal(await page.locator('#result-title').textContent(),'スミレを、スカイリムへ。');
  await page.locator('#language').selectOption('en');assert.match(await page.locator('#output-folder').textContent(),/C:\/fixture\/スミレ/);
  await page.reload();await page.waitForFunction(()=>document.querySelector('#game').value.length>0);assert.equal(await page.locator('html').getAttribute('lang'),'en');
  await page.locator('#language').selectOption('ja');await page.reload();await page.waitForFunction(()=>document.querySelector('#game').value.length>0);assert.equal(await page.locator('html').getAttribute('lang'),'ja');
  assert.deepEqual(errors,[]);
  catalogMissing=true;await page.locator('#language').selectOption('en');
  await page.locator('#source').setInputFiles({name:'fixture.vrm',mimeType:'application/octet-stream',buffer:Buffer.from('fixture')});
  await page.waitForFunction(()=>document.querySelector('#source-status').textContent.includes('triangles'));
  for(let i=0;i<3;i++)await page.locator('#next').click();
  await page.locator('#perk-search').fill('Stealth80');
  assert.match(await page.locator('#perks label').textContent(),/Stealth80/);
  assert.ok(!(await page.locator('#perks label').textContent()).includes('隠術'));
  await context.close();
  console.log('PASS: native EN/JA labels, five steps, wardrobe, state preservation, export, progress/failure/result and persistent language selection');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
