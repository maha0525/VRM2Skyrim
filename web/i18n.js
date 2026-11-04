"use strict";
// Capture only authored HTML. Never walk generated user/game content to translate it.
const i18n = (() => {
  const supported=new Set(['ja','en']),storageKey='vrm2skyrim.language';
  let stored;
  try{stored=localStorage.getItem(storageKey);}catch{/* Private browsing may deny storage. */}
  let language=supported.has(stored)?stored:((navigator.language||'en').toLowerCase().startsWith('ja')?'ja':'en');
  const textNodes=[],attributes=[];
  const walker=document.createTreeWalker(document.documentElement,NodeFilter.SHOW_TEXT);
  while(walker.nextNode()){
    const node=walker.currentNode,key=node.textContent.trim();
    if(Object.hasOwn(englishUI,key)&&!node.parentElement.closest('script,style,[data-no-i18n]'))textNodes.push([node,key,node.textContent.match(/^\s*/)[0],node.textContent.match(/\s*$/)[0]]);
  }
  for(const element of document.querySelectorAll('[placeholder],[aria-label],[title]')){
    for(const attr of ['placeholder','aria-label','title']){const key=element.getAttribute(attr);if(Object.hasOwn(englishUI,key))attributes.push([element,attr,key]);}
  }
  const format=(value,args)=>value.replace(/\{(\d+)\}/g,(_,index)=>String(args[index]??''));
  function text(key,...args){return format(language==='en'?(englishUI[key]??key):key,args);}
  const escape=value=>value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  // Only known, authored message patterns. Captured arguments are opaque data.
  const patterns=Object.entries(englishUI).filter(([key])=>/\{\d+\}/.test(key)).map(([ja,en])=>{
    const compile=value=>{const indices=[];let last=0,source='^';for(const match of value.matchAll(/\{(\d+)\}/g)){source+=escape(value.slice(last,match.index))+'([\\s\\S]*?)';indices.push(Number(match[1]));last=match.index+match[0].length;}return {regex:new RegExp(source+escape(value.slice(last))+'$'),indices};};
    return {ja,en,match:{ja:compile(ja),en:compile(en)}};
  });
  function message(value,from='ja',to=language){
    if(!value||from===to)return value;
    for(const [ja,en]of Object.entries(englishUI)){if(value===(from==='ja'?ja:en))return to==='ja'?ja:en;}
    for(const p of patterns){const m=p.match[from].regex.exec(value);if(m){const args=[];p.match[from].indices.forEach((n,i)=>args[n]=m[i+1]);return format(p[to],args);}}
    // Backend diagnostic prefixes retain filenames, IDs and traceback details verbatim.
    for(const [ja,en]of Object.entries(englishUI)){const source=from==='ja'?ja:en;if(/[:：] $/.test(source)&&value.startsWith(source))return (to==='ja'?ja:en)+value.slice(source.length);}
    return value;
  }
  function staticText(){
    document.documentElement.lang=language;
    for(const [node,key,before,after]of textNodes)if(node.isConnected)node.textContent=before+text(key)+after;
    for(const [element,attr,key]of attributes)if(element.isConnected)element.setAttribute(attr,text(key));
    document.getElementById('language').value=language;
  }
  function setLanguage(next){
    if(!supported.has(next)||next===language)return;
    const previous=language;language=next;
    try{localStorage.setItem(storageKey,next);}catch{/* The current page still switches. */}
    staticText();
    for(const id of ['source-status','import-status','wardrobe-preview-status','head-preview-status','error','failure','stage','edit-status','deployed-patch-status']){
      const walker=document.createTreeWalker(document.getElementById(id),NodeFilter.SHOW_TEXT);
      while(walker.nextNode())walker.currentNode.textContent=message(walker.currentNode.textContent,previous,next);
    }
    for(const element of document.querySelectorAll('#events li,#wardrobe-preview-images figcaption'))element.textContent=message(element.textContent,previous,next);
    for(const element of document.querySelectorAll('#wardrobe-preview-images img'))element.alt=message(element.alt,previous,next);
    document.dispatchEvent(new CustomEvent('languagechange',{detail:{language:next,previous}}));
  }
  document.getElementById('language').addEventListener('change',event=>setLanguage(event.target.value));
  staticText();
  return {text,message,setLanguage,get language(){return language;}};
})();
const tr=(key,...args)=>i18n.text(key,...args);
const uiMessage=value=>i18n.message(value);
function recordLabel(item){return item?.labels?.[i18n.language]??(i18n.language==='en'&&/[\u3040-\u30ff\u3400-\u9fff]/.test(item?.label||'')?(item?.id||item?.editor_id||''):item?.label||item?.id||'');}
function recordDescription(item){return item.descriptions?.[i18n.language]??(i18n.language==='en'?'':item.description||'');}
