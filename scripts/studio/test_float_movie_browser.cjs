#!/usr/bin/env node
/* Actual shipped controls, OCIO pixels, owned jobs and Chromium download.
 * Synthetic sources are ENGINE TEST fixtures. This does not certify macOS.
 * --python ABS --browser ABS --evidence NEW_ABS
 */
'use strict';
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {spawn,spawnSync}=require('child_process');
const {chromium}=require('playwright');
const options={},args=process.argv.slice(2);
if(args.length!==6)throw Error('Use --python ABS --browser ABS --evidence NEW_ABS');
for(let i=0;i<args.length;i+=2){if(options[args[i]]||!['--python','--browser','--evidence'].includes(args[i])||!path.isAbsolute(args[i+1]))throw Error('Invalid option');options[args[i]]=args[i+1];}
for(const key of ['--python','--browser','--evidence'])if(!options[key])throw Error('Missing '+key);
const evidence=options['--evidence'];fs.mkdirSync(evidence);
const hash=data=>crypto.createHash('sha256').update(data).digest('hex');
const checks=[],errors=[],networkFailures=[],requests=[];
let browser,child,fixture,childLog='',childOutput='',timer;
const started=Date.now();
function check(name,condition,detail){checks.push({name,passed:Boolean(condition),detail});if(!condition)throw Error(name+': '+JSON.stringify(detail));}
const setup=String.raw`import copy,json,shutil,sys,threading
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import test_float_movie as fixtures
from server import Store,Server
media=fixtures.FloatMovieTests();media.setUp()
store=Store(Path(sys.argv[2])/'workspace');server=None;thread=None
try:
    project=store.new_project({'name':'ENGINE TEST float browser','fps':4,'width':32,'height':24})
    movie,_=media.movie();image=media.exr('negative-superwhite',(-.25,2,4),.375)
    a=store.admit(project['id'],media.root/movie['path'],'ENGINE_TEST_movie.mkv')
    staged=store.project_dir(project['id'])/'ENGINE_TEST_upload.exr';shutil.copyfile(media.root/image['path'],staged)
    b=store.admit(project['id'],staged,'ENGINE_TEST_float.exr')
    project=store.get(project['id'])
    project['clips']=[{'id':'ENGINE_TEST_picture','asset_id':a['id'],'start':0,'in':0,'duration':4,'track':0}]
    project=store.save(project['id'],project)
    server=Server(0,store);thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    print(json.dumps({'url':'http://127.0.0.1:'+str(server.server_port),'project_id':project['id'],'video':a,'exr':b}),flush=True)
    sys.stdin.readline()
finally:
    if server:server.shutdown();server.server_close();thread.join(2)
    store.shutdown();media.tearDown()
`;

async function run(){
  const env={...process.env,CINEMATICUM_IMAGING_PYTHON:options['--python'],PYTHONDONTWRITEBYTECODE:'1'};
  child=spawn(options['--python'],['-I','-B','-c',setup,__dirname,evidence],{env,stdio:['pipe','pipe','pipe']});
  child.stderr.on('data',data=>{childLog+=data.toString();});
  fixture=await new Promise((resolve,reject)=>{
    const timeout=setTimeout(()=>reject(Error('Owned fixture startup exceeded 20 seconds')),20000);
    child.stdout.on('data',data=>{childOutput+=data.toString();if(childOutput.includes('\n')){try{const value=JSON.parse(childOutput.split('\n')[0]);clearTimeout(timeout);resolve(value);}catch(error){clearTimeout(timeout);reject(error);}}});
    child.once('exit',code=>{clearTimeout(timeout);reject(Error('Fixture exited '+code+': '+childLog));});
  });
  const origin=new URL(fixture.url).origin;
  check('owned-loopback-fixture',/^http:\/\/127\.0\.0\.1:\d+$/.test(origin),origin);
  browser=await chromium.launch({executablePath:options['--browser'],headless:true});
  const context=await browser.newContext({viewport:{width:1440,height:1100},acceptDownloads:true});
  await context.route('**/*',route=>{
    const url=route.request().url();if(url.startsWith(origin+'/')||url.startsWith('data:')||url.startsWith('blob:'))return route.continue();
    networkFailures.push(url);return route.abort();
  });
  const page=await context.newPage();page.setDefaultTimeout(20000);
  page.on('pageerror',error=>errors.push(String(error)));
  page.on('response',response=>{if(response.url().startsWith(origin+'/api/'))requests.push({url:new URL(response.url()).pathname,status:response.status()});});
  const saved=async()=>{const response=await context.request.get(origin+'/api/projects/'+fixture.project_id);if(!response.ok())throw Error('Saved project unavailable');return response.json();};
  const open=async()=>{await page.locator('#export-button').click();await page.locator('#export-dialog').waitFor({state:'visible'});};
  const close=()=>page.locator('#close-export').click();
  await page.goto(origin);await page.locator('#project-select').waitFor();await page.locator('#project-select option[value="'+fixture.project_id+'"]:checked').waitFor({state:'attached'});
  await open();check('standard-mode-before-edit',await page.locator('#movie-precision').inputValue()==='standard8');
  await page.locator('#movie-precision').selectOption('float32');
  await page.locator('[data-float-setting=working_space]').waitFor();
  check('actual-ocio-catalog',await page.locator('[data-float-setting=default_input_space] option').count()>10);
  await page.locator('#movie-transparent').check();
  await page.locator('[data-float-setting=default_input_space]').selectOption('Linear Rec.709 (sRGB)');
  await page.locator('[data-float-setting=working_space]').selectOption('ACES2065-1');
  await close();await page.locator('#undo-button').click();await open();
  check('working-space-undo',await page.locator('[data-float-setting=working_space]').inputValue()==='ACEScg');
  await close();await page.locator('#redo-button').click();await open();
  check('working-space-redo',await page.locator('[data-float-setting=working_space]').inputValue()==='ACES2065-1');
  await page.locator('[data-float-setting=working_space]').selectOption('ACEScg');
  await page.locator('[data-float-setting=output_space]').selectOption('ACES2065-1');
  const view=await page.locator('[data-float-setting=view]').inputValue();check('explicit-sdr-display-view',/SDR/.test(view),view);
  await close();await page.locator('[data-add="'+fixture.exr.id+'"]').click();
  await page.locator('#inspector [data-field=duration]').fill('4');await page.locator('#inspector [data-field=duration]').press('Tab');
  await page.locator('#inspector [data-field=start]').fill('0');await page.locator('#inspector [data-field=start]').press('Tab');
  await page.locator('#add-video-track').click();await page.locator('#inspector [data-field=track]').selectOption('1');
  await open();const inputs=page.locator('[data-float-clip]');check('both-source-interpretations-editable',await inputs.count()===2);
  const exrControl=page.locator('[data-float-clip]').nth(1);check('exr-explicit-source-space',await exrControl.inputValue()==='ACEScg');
  await exrControl.selectOption('Linear Rec.709 (sRGB)');await close();
  await page.locator('#undo-button').click();await open();check('source-space-undo',await page.locator('[data-float-clip]').nth(1).inputValue()==='ACEScg');
  await close();await page.locator('#redo-button').click();await open();check('source-space-redo',await page.locator('[data-float-clip]').nth(1).inputValue()==='Linear Rec.709 (sRGB)');
  await page.locator('[data-float-clip]').nth(1).selectOption('ACEScg');await close();
  await page.locator('#save-project').click();await page.locator('#save-state').filter({hasText:'SAVED LOCALLY'}).waitFor();
  const first=await saved();fs.writeFileSync(path.join(evidence,'saved-before-reopen.json'),JSON.stringify(first,null,2)+'\n');
  check('saved-float-state',first.settings.image_precision==='float32'&&first.settings.transparent_background===true&&first.settings.float_color.output_space==='ACES2065-1'&&first.clips[1].float_input_space==='ACEScg',first.settings);
  check('real-multitrack-media',first.clips.length===2&&first.clips[1].track===1&&first.clips.every(c=>c.duration===4&&c.start===0),first.clips.map(c=>({id:c.id,track:c.track,start:c.start,duration:c.duration})));
  await page.reload();await page.locator('#project-select option[value="'+fixture.project_id+'"]:checked').waitFor({state:'attached'});
  await open();check('reopened-processing-and-color',await page.locator('#movie-precision').inputValue()==='float32'&&await page.locator('[data-float-setting=output_space]').inputValue()==='ACES2065-1');
  check('master-profile-gates',await page.locator('[data-export=master32]').isEnabled()&&await page.locator('[data-export=master16]').isDisabled());
  await close();await page.locator('#processed-frame').waitFor({state:'visible'});
  check('actual-processed-preview',/Rendered frame/.test(await page.locator('#frame-status').textContent())&&await page.locator('#processed-frame').evaluate(img=>img.naturalWidth===32&&img.naturalHeight===24));
  await page.screenshot({path:path.join(evidence,'float-paused-preview.png')});
  await open();await page.screenshot({path:path.join(evidence,'float-export-controls.png')});
  await page.locator('[data-export=master32]').click();await page.locator('#job-label').filter({hasText:'Float EXR master complete'}).waitFor();
  const downloadPromise=page.waitForEvent('download');await page.locator('#download-job').click();const download=await downloadPromise;
  const filename=download.suggestedFilename();check('owned-master-download-name',/^[a-f0-9]{32}\.zip$/.test(filename),filename);
  const downloaded=path.join(evidence,filename);await download.saveAs(downloaded);check('browser-download-completed',!(await download.failure()));
  const url=await page.locator('#download-job').getAttribute('href');const jobid=filename.slice(0,32);
  const response=await context.request.get(origin+'/api/jobs/'+jobid);const job=await response.json();
  fs.writeFileSync(path.join(evidence,'completed-job.json'),JSON.stringify(job,null,2)+'\n');
  check('download-exact-receipt-bytes',hash(fs.readFileSync(downloaded))===job.result.sha256&&fs.statSync(downloaded).size===job.result.size,{sha256:job.result.sha256,size:job.result.size,url});
  check('zip-is-not-a-video-preview',await page.locator('#rendered-preview').isDisabled());
  const snapshot=await saved();fs.writeFileSync(path.join(evidence,'saved-after-render.json'),JSON.stringify(snapshot,null,2)+'\n');
  const verify=String.raw`import json,sys,zipfile
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import numpy as np,OpenEXR
from float_movie import verify_master_package
snapshot=json.loads(Path(sys.argv[3]).read_text());receipt=json.loads(Path(sys.argv[5]).read_text())
# JavaScript JSON writes integral numbers without Python's '.0'. Bind the
# exact preserved server snapshot, then compare the browser-visible values.
manifest=verify_master_package(sys.argv[2],receipt['snapshot']);assert manifest['project']==snapshot
with zipfile.ZipFile(sys.argv[2]) as z:
    target=Path(sys.argv[4])/'downloaded-frame.exr';target.write_bytes(z.read('frames/frame-00000000.exr'))
with OpenEXR.File(str(target),separate_channels=True) as f:
    assert all(f.channels()[c].pixels.dtype==np.dtype('float32') for c in 'RGBA')
    rgba=np.stack([f.channels()[c].pixels for c in 'RGBA'],axis=-1)
    assert np.isfinite(rgba).all() and manifest['frames']==4 and manifest['audio']['samples']==48000
print(json.dumps({'passed':True,'frames':manifest['frames'],'sources':manifest['sources'],'audio':manifest['audio'],'output_space':manifest['color']['output_space'],'minimum':float(rgba[...,:3].min()),'maximum':float(rgba[...,:3].max()),'issuance_effect':manifest['issuance_effect']}))
`;
  const preserved=path.join(evidence,'workspace','projects',fixture.project_id,'exports',jobid+'.json');
  const validation=spawnSync(options['--python'],['-I','-B','-c',verify,__dirname,downloaded,path.join(evidence,'saved-after-render.json'),evidence,preserved],{env,encoding:'utf8',timeout:20000});
  check('independent-downloaded-media-verification',validation.status===0,validation.stderr||validation.stdout);
  fs.writeFileSync(path.join(evidence,'download-verification.json'),validation.stdout);
  check('no-browser-script-errors',errors.length===0,errors);check('no-external-requests',networkFailures.length===0,networkFailures);
  await page.screenshot({path:path.join(evidence,'float-master-download.png')});
}

(async()=>{
  let failure;
  try{await Promise.race([run(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Owned float browser acceptance exceeded 120 seconds')),120000);})]);}
  catch(error){failure=String(error.stack||error);}
  finally{
    clearTimeout(timer);if(browser)await browser.close().catch(()=>{});
    if(child&&child.exitCode===null){child.stdin.end('stop\n');await new Promise(resolve=>{const t=setTimeout(()=>{child.kill('SIGTERM');resolve();},5000);child.once('exit',()=>{clearTimeout(t);resolve();});});}
    fs.writeFileSync(path.join(evidence,'fixture.stderr'),childLog);fs.writeFileSync(path.join(evidence,'fixture.stdout'),childOutput);
    const result={schema:'cinematicum-float32-browser-acceptance-v1',passed:!failure&&checks.every(c=>c.passed),engine_test_only:true,native_certified:false,issuance_effect:'NONE',elapsed_ms:Date.now()-started,
      chromium_sha256:hash(fs.readFileSync(options['--browser'])),checks,error:failure||null,requests,page_errors:errors};
    fs.writeFileSync(path.join(evidence,'browser-report.json'),JSON.stringify(result,null,2)+'\n');
    process.stdout.write(JSON.stringify(result)+'\n');if(!result.passed)process.exitCode=1;
  }
})().catch(error=>{process.stderr.write(String(error.stack||error)+'\n');process.exitCode=1;});
