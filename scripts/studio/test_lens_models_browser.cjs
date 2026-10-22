#!/usr/bin/env node
/* Actual shipped controls and real profile-file admission. No native claim. */
'use strict';
const fs=require('fs'),path=require('path'),assert=require('assert'),crypto=require('crypto');
const {chromium}=require('playwright');
const config=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const origin=new URL(config.url).origin;
assert(/^http:\/\/127\.0\.0\.1:\d+$/.test(origin),'Owned loopback fixture required');
for(const key of ['browser','profile_file','report','screenshot'])assert(path.isAbsolute(config[key]),key+' must be absolute');
assert.strictEqual(crypto.createHash('sha256').update(fs.readFileSync(config.profile_file)).digest('hex'),config.profile_sha256);
const result={passed:false,native_certified:false,transport:'Chromium',checks:{},frames:{},page_errors:[]};
const began=Date.now();let browser,page,deadline;
const record=(name,value)=>{result.checks[name]=!!value;assert(value,name);};
async function until(predicate,arg,options={}){
  const end=Date.now()+(options.timeout||5000);
  while(Date.now()<end){if(await page.evaluate(predicate,arg))return;await new Promise(resolve=>setTimeout(resolve,25));}
  throw Error('Timed out waiting for actual editor state: '+String(predicate));
}
async function exactFrame(previous){
  await until(previous=>{
    const img=document.querySelector('#processed-frame');
    return img&&!img.hidden&&img.complete&&img.naturalWidth===160&&document.querySelector('#frame-status')?.textContent==='Rendered frame 0 · export graph'&&(!previous||new URL(img.currentSrc||img.src,location.href).pathname!==previous);
  },previous,{timeout:5000});
  return page.evaluate(()=>{
    const img=document.querySelector('#processed-frame'),url=new URL(img.currentSrc||img.src,location.href);
    const canvas=document.createElement('canvas');canvas.width=160;canvas.height=90;
    const ctx=canvas.getContext('2d');ctx.drawImage(img,0,0);const pixels=ctx.getImageData(0,0,160,90).data;
    let hash=2166136261;for(const value of pixels)hash=Math.imul(hash^value,16777619);
    return {url:url.pathname,pixel_hash:(hash>>>0).toString(16)};
  });
}
async function selectLens(){await page.locator('[data-node="'+result.lens_id+'"]').click({position:{x:40,y:15}});}
async function main(){
  try{
    browser=await chromium.launch({executablePath:config.browser,headless:true,args:['--autoplay-policy=no-user-gesture-required']});
    deadline=setTimeout(()=>browser.close().catch(()=>{}),27000);
    const context=await browser.newContext({viewport:{width:1440,height:1100}});
    await context.route('**/*',route=>{const url=route.request().url();return url.startsWith(origin+'/')||url.startsWith('data:')||url.startsWith('blob:')?route.continue():route.abort();});
    page=await context.newPage();page.setDefaultTimeout(5000);
    page.on('pageerror',error=>result.page_errors.push(String(error)));
    await page.goto(config.url);
    await until(()=>document.querySelector('#viewer-project')?.textContent.includes('ENGINE TEST'));
    await page.locator('[data-add="'+config.asset_id+'"]').click();
    await page.locator('[data-mode="composite"]').click();await page.locator('#jump-start').click();
    await page.locator('[data-graph-add-type]').selectOption('lens_distortion');await page.locator('[data-graph-action="add"]').click();
    result.lens_id=await page.locator('.compositor-node.selected').getAttribute('data-node');
    record('connected_lens_node',await page.locator('[data-graph-output]').inputValue()===result.lens_id);
    for(const [name,value] of [['fx','.55'],['fy','.72']]){const field=page.locator('[data-node-param="'+name+'"]');await field.fill(value);await field.press('Tab');}
    let previous=null;
    for(const projection of ['equidistant','equisolid','stereographic','orthographic']){
      await page.locator('[data-lens-model]').selectOption(projection);
      const frame=await exactFrame(previous);result.frames[projection]=frame;previous=frame.url;
    }
    record('four_real_distinct_projection_pictures',new Set(Object.values(result.frames).map(row=>row.pixel_hash)).size===4);
    await page.locator('[data-lensfun-file]').setInputFiles(config.profile_file);
    await until(()=>document.querySelectorAll('[data-lensfun-choice] option').length===106);
    record('exact_upstream_profile_options',await page.locator('[data-lensfun-choice] option').count()===106);
    await page.locator('[data-lensfun-choice]').selectOption(config.profile_id);
    record('exact_measured_sample_label',(await page.locator('[data-lensfun-choice] option:checked').textContent()).includes('7 mm · crop 2 · ptlens'));
    await page.locator('[data-node-action="lensfun-apply"]').click();
    record('profile_applied',await page.locator('[data-lens-model]').inputValue()==='lensfun');
    result.frames.lensfun=await exactFrame(previous);
    await page.locator('#undo-button').click();await selectLens();
    record('profile_undo_restores_fisheye',await page.locator('[data-lens-model]').inputValue()==='orthographic');
    await page.locator('#redo-button').click();await selectLens();
    record('profile_redo_restores_calibration',await page.locator('[data-lens-model]').inputValue()==='lensfun'&&await page.locator('[data-lens-crop]').inputValue()==='2');
    await page.locator('#save-project').click();
    await until(()=>document.querySelector('#save-state')?.textContent==='SAVED LOCALLY'&&!document.querySelector('#save-project').disabled);
    await page.reload();
    await until(()=>document.querySelectorAll('.timeline-clip[data-clip]').length===1);
    await page.locator('[data-mode="composite"]').click();
    await page.locator('.timeline-clip[data-clip]').focus();await page.keyboard.press('Enter');await selectLens();
    record('saved_profile_reopens_in_editor',await page.locator('[data-lens-model]').inputValue()==='lensfun'&&await page.locator('[data-lens-crop]').inputValue()==='2');
    record('applied_metadata_visible',(await page.locator('.node-lens-editor').textContent()).includes('Olympus Zuiko Digital ED 7-14mm f/4.0'));
    result.frames.reopened=await exactFrame();
    // preview_identity intentionally includes the save revision/timestamp.
    // Python verifies both full render snapshots and exact decoded equality.
    record('reopened_picture_same_pixels',result.frames.reopened.pixel_hash===result.frames.lensfun.pixel_hash);
    await page.locator('#export-button').click();await page.locator('[data-export="h264"]').click();
    await until(()=>['Render complete','Job failed'].includes(document.querySelector('#job-label')?.textContent),null,{timeout:6000});
    record('movie_export_completed',await page.locator('#job-label').textContent()==='Render complete');
    await until(()=>!document.querySelector('#render-video').hidden&&document.querySelector('#render-video').readyState>=2);
    await page.locator('#play-button').click();await until(()=>document.querySelector('#render-video').currentTime>.06);
    result.playback=await page.locator('#render-video').evaluate(video=>({url:video.getAttribute('src'),time:video.currentTime}));
    await page.locator('#play-button').click();record('movie_decodes_and_plays',result.playback.time>.06);
    await page.screenshot({path:config.screenshot});
    result.browser_version=await browser.version();record('no_page_errors',result.page_errors.length===0);result.passed=true;
  }catch(error){result.error=String(error.stack||error);if(page){result.ui=await page.evaluate(()=>({toast:document.querySelector('#toast')?.textContent,frame:document.querySelector('#frame-status')?.textContent,job:document.querySelector('#job-detail')?.textContent})).catch(()=>null);await page.screenshot({path:config.screenshot,timeout:500}).catch(()=>{});}}
  finally{clearTimeout(deadline);if(browser)await browser.close();result.elapsed_ms=Date.now()-began;fs.writeFileSync(config.report,JSON.stringify(result,null,2)+'\n');process.stdout.write(JSON.stringify(result)+'\n');if(!result.passed)process.exitCode=1;}
}
main().catch(error=>{process.stderr.write(String(error.stack||error)+'\n');process.exitCode=1;});
