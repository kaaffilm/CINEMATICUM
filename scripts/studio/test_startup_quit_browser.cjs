#!/usr/bin/env node
/* Real page/server startup barriers, persistence, authentication and FFmpeg.
 * Chromium evidence is deliberately not reported as native AppKit acceptance.
 * --baseline is optional: omit it for current-source CI without legacy replay.
 */
'use strict';
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {spawn}=require('child_process');
const {chromium}=require('playwright');
const options={},args=process.argv.slice(2);
for(let i=0;i<args.length;i+=2){
  if(!['--python','--browser','--evidence','--baseline'].includes(args[i])||options[args[i]]||!path.isAbsolute(args[i+1]||''))throw Error('Use absolute --python, --browser, --evidence paths and optional --baseline path');
  options[args[i]]=args[i+1];
}
for(const key of ['--python','--browser','--evidence'])if(!options[key])throw Error('Missing '+key);
const output=options['--evidence'];fs.mkdirSync(output);
const sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const checks=[],cases=[],pageErrors=[],contentSecurityPolicies=[];let browser,current,browserVersion;
const legacyRequested=Boolean(options['--baseline']);
const began=Date.now();
const legacy="if (typeof state !== 'undefined' && state.dirty && typeof saveProject === 'function') { await saveProject(false); } return await api('/api/prepare-quit', {method:'POST', body:{cancel_active:false}});";
function check(name,ok,detail){checks.push({name,passed:Boolean(ok),detail});if(!ok)throw Error(name+': '+JSON.stringify(detail));}
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};}
function bound(promise,message,ms=16000){let timer;return Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error(message)),ms);})]).finally(()=>clearTimeout(timer));}

async function fixture(name,phase,{baseline=false}={}){
  const directory=path.join(output,name);fs.mkdirSync(directory);
  const root=baseline?path.join(options['--baseline'],'scripts/studio'):__dirname;
  const command="import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_path(sys.argv.pop(1),run_name='__main__')";
  const child=spawn(options['--python'],['-I','-B','-c',command,root,path.join(__dirname,'startup_quit_fixture.py'),
    '--workspace',path.join(directory,'workspace'),'--evidence',directory,'--phase',phase],
    {env:{...process.env,CINEMATICUM_IMAGING_PYTHON:options['--python'],PYTHONDONTWRITEBYTECODE:'1'},stdio:['pipe','pipe','pipe']});
  const ready=deferred(),gate=deferred(),closed=deferred();let stdout='',stderr='',tail='';
  child.stdout.on('data',data=>{stdout+=data;tail+=data;let end;while((end=tail.indexOf('\n'))>=0){const line=tail.slice(0,end);tail=tail.slice(end+1);
    if(line.startsWith('ENGINE_TEST_FIXTURE: '))ready.resolve(JSON.parse(line.slice(21)));
    if(line.startsWith('ENGINE_TEST_GATE: '))gate.resolve(line.slice(18));}});
  child.stderr.on('data',data=>{stderr+=data;});
  child.on('error',error=>{ready.reject(error);closed.reject(error);});
  child.on('exit',code=>{closed.resolve(code);ready.reject(Error('Fixture exited '+code+': '+stderr));});
  const record={name,phase,baseline,directory,child,gate,closed,stdout:()=>stdout,stderr:()=>stderr};current=record;
  const binding=await bound(ready.promise,'Actual fixture did not start');Object.assign(record,binding);
  const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
  Object.assign(record,{context,page});page.setDefaultTimeout(16000);
  await context.route('**/*',route=>route.request().url().startsWith(binding.url+'/')||/^(data|blob):/.test(route.request().url())?route.continue():route.abort());
  page.on('pageerror',error=>pageErrors.push({case:name,error:String(error)}));
  page.on('response',response=>{if(response.url()===binding.url+'/')contentSecurityPolicies.push({case:name,policy:response.headers()['content-security-policy']||''});});
  record.events=()=>{const file=path.join(directory,'transport-events.json');return fs.existsSync(file)?JSON.parse(fs.readFileSync(file)):[];};
  record.quitEvents=()=>record.events().filter(row=>row.event==='quit-response');
  record.release=()=>child.stdin.write('RELEASE\n');
  record.getProject=async()=>{const response=await context.request.get(binding.url+'/api/projects/'+binding.project_id);if(!response.ok())throw Error('Project unavailable');return response.json();};
  // CFT 134 correctly enforces the product CSP against waitForFunction's
  // internal eval. Observe the shipped selector populated by adoptProject.
  record.waitReady=()=>page.locator('#project-select option[value="'+binding.project_id+'"]:checked').waitFor({state:'attached'});
  record.open=async()=>{await page.goto(binding.url);await record.waitReady();};
  record.edit=async()=>{await page.locator('#export-button').click();await page.locator('#movie-precision').selectOption('high16');await page.locator('#movie-transparent').check();await page.locator('#close-export').click();check(name+'-ordinary-unsaved-edit',await page.evaluate(()=>state.dirty));};
  record.end=async()=>{
    if(context)await context.close();
    if(child.exitCode===null){child.stdin.end('EXIT\n');await bound(closed.promise,'Owned fixture did not gracefully exit',10000);}
    fs.writeFileSync(path.join(directory,'server.stdout'),stdout);fs.writeFileSync(path.join(directory,'server.stderr'),stderr);
    check(name+'-graceful-fixture-exit',child.exitCode===0,child.exitCode);
    const exit=JSON.parse(fs.readFileSync(path.join(directory,'workspace/last-session-exit.json')));
    cases.push({name,phase,baseline,source_root:root,fixture:binding,events:record.events(),exit});current=null;return exit;
  };
  return record;
}

async function run(){
  browser=await chromium.launch({executablePath:options['--browser'],headless:true});browserVersion=browser.version();
  // Legacy replay needs explicitly supplied preserved source. CI exercises the
  // corrected production paths without inventing or downloading that source.
  for(const phase of legacyRequested?['app-script','bootstrap']:[]){
    const f=await fixture('baseline-'+phase,phase,{baseline:true});
    await f.page.goto(f.url,{waitUntil:phase==='app-script'?'commit':'domcontentloaded'});
    await bound(f.gate.promise,'Baseline barrier was not reached');
    const observation=await f.page.evaluate(()=>({url:location.href,loaded:document.readyState,api:typeof api,token:typeof state==='undefined'?null:state.token,project:typeof state==='undefined'?null:state.project}));
    check(phase+'-actual-baseline-not-bootstrapped',observation.project===null&&!observation.token,observation);
    let error;try{await f.page.evaluate('(async()=>{'+legacy+'})()');}catch(value){error=String(value);}
    check(phase+'-original-quit-failure-reproduced',phase==='app-script'?/api is not defined/.test(error):/Application token is missing or expired/.test(error),error);
    check(phase+'-baseline-never-approved-quit',f.quitEvents().every(row=>row.status!==200&&row.response.ready!==true),f.quitEvents());
    f.release();await f.waitReady();
    await f.end();
  }

  {
    const f=await fixture('await-real-bootstrap','bootstrap');
    await f.page.goto(f.url,{waitUntil:'domcontentloaded'});await bound(f.gate.promise,'Bootstrap barrier was not reached');
    const pending=await f.page.evaluate(()=>{window.ENGINE_TEST_quit=prepareNativeQuit(false).then(value=>({ok:true,value}),error=>({ok:false,error:error.message}));return {token:state.token,project:state.project};});
    check('new-quit-requested-before-token',pending.token===''&&pending.project===null,pending);
    check('no-premature-quit-request',f.quitEvents().length===0,f.quitEvents());
    f.release();const result=await f.page.evaluate(()=>window.ENGINE_TEST_quit);
    check('pending-quit-resumes-after-real-bootstrap',result.ok&&result.value.ready===true,result);
    const events=f.quitEvents();check('exactly-one-authenticated-quit-after-bootstrap',events.length===1&&events[0].authenticated&&events[0].status===200&&events[0].decision.cancel_active===false,events);
    const exit=await f.end();check('startup-no-job-quit-reason-preserved',exit.reason==='native-quit-no-active-jobs'&&exit.active_at_shutdown.length===0,exit);
  }

  {
    const f=await fixture('save-before-quit','normal');await f.open();
    const invalid=await f.page.evaluate(async()=>{try{await prepareNativeQuit('false');return '';}catch(error){return error.message;}});
    check('ambiguous-active-job-decision-refused',/explicit active-work decision/.test(invalid)&&f.quitEvents().length===0,invalid);
    await f.edit();const reached=deferred(),release=deferred();
    await f.page.route('**/api/projects/'+f.project_id,async route=>{if(route.request().method()!=='PUT')return route.continue();reached.resolve();await release.promise;await route.continue();});
    await f.page.evaluate(()=>{window.ENGINE_TEST_quit=prepareNativeQuit(false).then(value=>({ok:true,value}),error=>({ok:false,error:error.message}));});
    await bound(reached.promise,'Actual project save did not reach the barrier');
    check('quit-waits-for-actual-dirty-save',f.quitEvents().length===0&&await f.page.evaluate(()=>Boolean(state.savePromise)&&state.dirty));
    release.resolve();const result=await f.page.evaluate(()=>window.ENGINE_TEST_quit);
    check('successful-save-permits-quit',result.ok&&result.value.ready===true,result);
    const project=JSON.parse(fs.readFileSync(path.join(f.directory,'workspace/projects',f.project_id,'project.json')));check('ordinary-edit-durably-saved-before-quit',project.settings.transparent_background===true,project.settings);
    const events=f.events(),saved=events.findIndex(row=>row.event==='save-response'&&row.status===200),quit=events.findIndex(row=>row.event==='quit-response');
    check('actual-save-response-precedes-quit-response',saved>=0&&saved<quit,events);await f.end();
  }

  {
    const f=await fixture('save-conflict-protection','normal');await f.open();await f.edit();
    const stale=await f.getProject(),token=await f.page.evaluate(()=>state.token);stale.name='ENGINE TEST concurrent saved revision';
    const changed=await f.context.request.put(f.url+'/api/projects/'+f.project_id,{headers:{'X-Cinematicum-Token':token},data:stale});
    check('actual-concurrent-revision-created',changed.ok(),await changed.text());
    const result=await f.page.evaluate(async()=>{try{return {ok:true,value:await prepareNativeQuit(false)};}catch(error){return {ok:false,error:error.message,status:error.status,dirty:state.dirty};}});
    check('real-save-conflict-blocks-quit',!result.ok&&result.status===409&&result.dirty&&f.quitEvents().length===0,result);
    const saved=await f.getProject();check('conflicting-saved-work-preserved',saved.name===stale.name&&JSON.stringify(saved.settings)===JSON.stringify(stale.settings),saved.settings);
    const admitted=await f.context.request.post(f.url+'/api/projects',{headers:{'X-Cinematicum-Token':token},data:{name:'ENGINE TEST still open'}});
    check('failed-save-keeps-workspace-admission-open',admitted.ok(),admitted.status());await f.end();
  }

  {
    const f=await fixture('bootstrap-failure-protection','normal');
    await f.page.route('**/api/bootstrap',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'ENGINE TEST controlled transport failure'})}));
    await f.page.goto(f.url);const result=await f.page.evaluate(async()=>{try{return {ok:true,value:await prepareNativeQuit(false)};}catch(error){return {ok:false,error:error.message};}});
    check('failed-bootstrap-does-not-approve-quit',!result.ok&&/Editor startup did not complete/.test(result.error)&&f.quitEvents().length===0,result);await f.end();
  }

  {
    const f=await fixture('actual-worker-protection','protection');await f.open();
    await f.page.locator('#export-button').click();await f.page.locator('[data-export="master16"]').click();
    await f.page.locator('#job-bar:not([hidden]):has(#job-indicator.running) #job-progress:not([hidden]):not([value="0"])').waitFor({state:'attached'});
    const job=await f.page.evaluate(()=>({id:state.job.id,kind:state.job.kind,state:state.job.state,progress:state.job.progress}));
    check('actual-ffmpeg-work-progressed',job.kind==='render'&&job.state==='running'&&job.progress>0,job);await f.edit();
    const blocked=await f.page.evaluate(()=>prepareNativeQuit(false));
    check('active-worker-requires-explicit-choice',blocked.ready===false&&blocked.active_jobs.some(value=>value.id===job.id),blocked);
    const currentJob=await (await f.context.request.get(f.url+'/api/jobs/'+job.id)).json();
    check('declined-quit-keeps-real-worker-running',currentJob.state==='running',currentJob);
    check('dirty-save-happens-before-active-job-choice',(await f.getProject()).settings.transparent_background===true);
    const confirmed=await f.page.evaluate(()=>prepareNativeQuit(true));check('explicit-cancel-accepted',confirmed.ready===true,confirmed);
    const exit=await f.end(),durable=JSON.parse(fs.readFileSync(path.join(f.directory,'workspace/jobs',job.id+'.json')));
    check('confirmed-quit-settles-actual-cancellation',exit.reason==='native-user-confirmed-job-cancellation'&&durable.state==='cancelled'&&durable.result===null,{exit,state:durable.state});
    const source=path.join(f.directory,'workspace/projects',f.project_id,f.source.path);
    check('actual-source-media-preserved',sha(fs.readFileSync(source))===f.source.sha256);
  }
  check('no-unhandled-page-errors',pageErrors.length===0,pageErrors);
  check('production-csp-preserved',contentSecurityPolicies.length===cases.length&&contentSecurityPolicies.every(value=>value.policy.includes("script-src 'self'")&&!value.policy.includes("'unsafe-eval'")),contentSecurityPolicies);
}

(async()=>{
  let error;
  try{await run();}catch(value){error=String(value.stack||value);}
  finally{
    if(current){try{await current.end();}catch(value){error=(error||'')+'\nCleanup: '+String(value);}}
    if(browser)await browser.close();
    const sourceFiles=['macos/StudioApp.swift','web/app.js','server.py','startup_quit_fixture.py','test_startup_quit_browser.cjs'];
    const report={schema:'cinematicum-startup-quit-browser-v1',passed:!error&&checks.every(value=>value.passed),
      scope:'Actual Chromium page, real production HTTP authentication/save/admission, explicit transport barriers and actual FFmpeg worker. Native AppKit is not certified.',
      native_certified:false,engine_test_only:true,force_kill_used:false,elapsed_seconds:(Date.now()-began)/1000,
      browser:{executable:options['--browser'],version:browserVersion,playwright_version:require('playwright/package.json').version},
      legacy_reproduction:{requested:legacyRequested,status:legacyRequested?'requested':'not-requested'},content_security_policies:contentSecurityPolicies,
      source_sha256:Object.fromEntries(sourceFiles.map(name=>[name,sha(fs.readFileSync(path.join(__dirname,name)))])),
      baseline_sha256:legacyRequested?{'web/app.js':sha(fs.readFileSync(path.join(options['--baseline'],'scripts/studio/web/app.js')))}:null,checks,cases,page_errors:pageErrors};
    if(error)report.error=error;fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2)+'\n');
    console.log(JSON.stringify({passed:report.passed,checks:checks.length,failed:checks.filter(value=>!value.passed).map(value=>value.name),elapsed_seconds:report.elapsed_seconds,error,report:path.join(output,'report.json')}));
    process.exitCode=report.passed?0:1;
  }
})();
