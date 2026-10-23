/* Dependency-free UI lifecycle contract; numerical fixtures are not inference. */
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

class Element {
  constructor(tag){this.tagName=tag;this.children=[];this.attrs={};this.dataset={};this.value='';this.checked=false;this.open=false;this.hidden=false;this.disabled=false;this.classList={toggle(){}};this.listeners={};}
  set innerHTML(html){this.children=[];for(const match of html.matchAll(/<([a-z][a-z0-9-]*)\b([^>]*)>/gi)){const node=new Element(match[1].toLowerCase());for(const attr of match[2].matchAll(/([a-z][a-z0-9-]*)(?:="([^"]*)")?/gi)){node.attrs[attr[1]]=attr[2]??'';if(attr[1]==='value')node.value=attr[2];if(attr[1]==='checked')node.checked=true;if(attr[1]==='hidden')node.hidden=true;}this.children.push(node);}}
  append(...nodes){this.children.push(...nodes);if(this.tagName==='select'&&!this.value&&nodes[0])this.value=nodes[0].value;}
  replaceChildren(...nodes){this.children=[];this.value='';this.append(...nodes);}
  addEventListener(name,callback){this.listeners[name]=callback;}
  showModal(){this.open=true;}
  close(){this.open=false;}
  remove(){this.open=false;this.removed=true;}
  matches(selector){if(selector==='input,select,button')return ['input','select','button'].includes(this.tagName);const match=selector.match(/^\[([^\]]+)\](:checked)?$/);if(!match)return false;const key=match[1];const data=key.startsWith('data-')?key.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase()):null;return (Object.hasOwn(this.attrs,key)||(data&&Object.hasOwn(this.dataset,data)))&&(!match[2]||this.checked);}
  querySelectorAll(selector){const nodes=[];for(const child of this.children){if(child.matches(selector))nodes.push(child);nodes.push(...child.querySelectorAll(selector));}return nodes;}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
}

function environment(options={}){
  const host=new Element('body');const window={};const project={id:'project',assets:Array.from({length:12},(_,i)=>({id:'photo_'+i,kind:'image',width:640,height:480,path:`media/photo_${i}.png`,name:'<untrusted photo '+i+'>'}))};
  const context={projectId:'project',revision:3};const requests=[];const completions=[];const applications=[];const id='a'.repeat(32);
  const base=`/api/projects/project/lens-calibration/outputs/${id}/`;
  const receipt={type:'cinematicum-lens-calibration',quality:{train_rms_pixels:.1,holdout_rms_pixels:.12,observability:{rank:8,condition:200}},lens_profile:{version:1,reference_image_size:{width:640,height:480},params:{model:'brown'}},proposal_error:null};
  const result={output_id:id,receipt,quality:receipt.quality,lens_profile:receipt.lens_profile,calibration:{views:Array(12).fill({})},artifact_urls:{'provenance.json':base+'provenance.json','calibration.json':base+'calibration.json','preview.png':base+'preview.png'}};
  if(options.badArtifact)result.artifact_urls['preview.png']='https://outside.example/foreign.png';
  let published=false,releaseSubmit=null;
  const bridge={getProject:()=>project,getContext:()=>({...context}),onComplete:async value=>{completions.push(value);},applyLensProfile:async(...args)=>{applications.push(args);},request:async(url,config={})=>{
    url=new URL(url,'http://127.0.0.1:18200/').pathname;requests.push({url,config});
    if(url==='/api/lens-calibration-capabilities')return {available:true,opencv:'ENGINE TEST interface',runtime_operations_verified:true};
    if(url==='/api/projects/project/studio-results')return {results:published?[{tool:'lens-calibration',output_id:id,modified_at:0,artifact_urls:result.artifact_urls}]:[]};
    if(url==='/api/projects/project/lens-calibration'){
      assert.equal(config.method,'POST');assert.equal(config.body.recipe.operation,'calibrate_checkerboard');assert.equal(config.body.recipe.settings.asset_ids.length,12);assert.equal(config.body.recipe.settings.same_optics_confirmed,true);
      if(options.delaySubmit)await new Promise(resolve=>{releaseSubmit=resolve;});
      return {id,project_id:'project',kind:'lens-calibration',state:'queued'};
    }
    if(url===`/api/jobs/${id}`){published=true;if(options.changeRevision)context.revision++;return {id,project_id:'project',kind:'lens-calibration',state:'completed',progress:1,result};}
    if(url===`/api/jobs/${id}/cancel`)return {cancel_requested:true};
    if(url===base+'provenance.json')return receipt;
    if(url===base+'calibration.json')return result.calibration;
    throw Error('Unexpected UI request '+url);
  }};
  const sandbox={window,document:{createElement:tag=>new Element(tag)},location:{href:'http://127.0.0.1:18200/',origin:'http://127.0.0.1:18200'},URL,Date,JSON,Number,Object,Array,Set,Promise,Error,setTimeout:callback=>{queueMicrotask(callback);return 1;}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'web/lens-calibration-ui.js'),'utf8'),sandbox,{filename:'lens-calibration-ui.js'});
  const editor=window.CinematicumLensCalibration.mount(host,bridge);const dialog=host.children[0];const $=selector=>{const node=dialog.querySelector(selector);assert.ok(node,'Real markup must contain '+selector);return node;};
  return {editor,dialog,$,requests,completions,applications,context,result,release:()=>releaseSubmit?.()};
}

async function select(env){await env.editor.open();env.$('[data-cal-all]').onclick();env.$('[data-cal-fixed]').checked=true;}

(async()=>{
  const happy=environment();await select(happy);assert.equal(happy.dialog.querySelectorAll('[data-cal-photo]:checked').length,12);
  await happy.$('[data-cal-run]').onclick();assert.equal(happy.completions.length,1);assert.match(happy.$('[data-cal-summary]').textContent,/Held-out RMS/);assert.equal(happy.$('[data-cal-preview]').src,'http://127.0.0.1:18200'+happy.result.artifact_urls['preview.png']);
  await happy.$('[data-cal-apply]').onclick();assert.equal(happy.applications.length,1);assert.equal(happy.applications[0][1].type,'cinematicum-lens-calibration');
  await happy.$('[data-cal-open-saved]').onclick();assert.ok(happy.requests.some(row=>row.url.endsWith('/calibration.json')));happy.editor.close();assert.equal(happy.dialog.open,false);
  const unsafe=environment({badArtifact:true});await select(unsafe);await unsafe.$('[data-cal-run]').onclick();assert.match(unsafe.$('[data-cal-status]').textContent,/escaped its owned project/);assert.ok(unsafe.requests.some(row=>row.url.endsWith('/cancel')));
  const changed=environment({changeRevision:true});await select(changed);await changed.$('[data-cal-run]').onclick();assert.match(changed.$('[data-cal-status]').textContent,/project changed/i);assert.equal(changed.completions.length,0);
  const closing=environment({delaySubmit:true});await select(closing);const pending=closing.$('[data-cal-run]').onclick();await Promise.resolve();closing.editor.destroy();closing.release();await pending;assert.ok(closing.requests.some(row=>row.url.endsWith('/cancel')));assert.equal(closing.completions.length,0);
  process.stdout.write('PASS lens calibration UI: owned jobs, review/apply, saved reopen, foreign URL rejection, revision guard and late-submit cancellation\n');
})().catch(error=>{process.stderr.write(error.stack+'\n');process.exitCode=1;});
