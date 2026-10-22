/* Real scientific Studio panels. Requires --python, --browser, --evidence and explicit CINEMATICUM_IMAGING_PYTHON, CINEMATICUM_OPTICS_PYTHON, CINEMATICUM_PHYSICAL_PYTHON; optional CINEMATICUM_PBRT. Uses only new owned /tmp projects. */
const fs = require('fs'), path = require('path'), crypto = require('crypto'), {spawn,spawnSync} = require('child_process');
const {chromium} = require('playwright');
const args={};
if((process.argv.length-2)%2)throw Error('Use paired --option value arguments.');
for(let i=2;i<process.argv.length;i+=2){if(args[process.argv[i]])throw Error('Duplicate option');args[process.argv[i]]=process.argv[i+1];}
for(const key of ['--python','--browser','--evidence'])if(!args[key]||!path.isAbsolute(args[key]))throw Error(key+' requires an absolute path');
if(Object.keys(args).some(key=>!['--python','--browser','--evidence'].includes(key)))throw Error('Unknown option');
const studio=__dirname,repo=path.resolve(studio,'../..');
for(const key of ["CINEMATICUM_IMAGING_PYTHON", "CINEMATICUM_OPTICS_PYTHON", "CINEMATICUM_PHYSICAL_PYTHON"])if(!process.env[key]||!path.isAbsolute(process.env[key]))throw Error(key+' requires an explicit accepted runtime path');
fs.mkdirSync(args['--evidence']); // Preserve every earlier attempt; use a fresh directory.
const browserIdentity=crypto.createHash('sha256').update(fs.readFileSync(args['--browser'])).digest('hex');
const prepared=spawnSync(args['--python'],['-I','-B','-c',"import sys,json,tempfile,hashlib\nfrom pathlib import Path\nstudio=Path(sys.argv[1]);sys.path.insert(0,str(studio));evidence=Path(sys.argv[2])\nfrom server import Store\nfrom test_physical_rendering import fixture\nfrom test_studio_tools import write_deep_fixture\nroot=Path(tempfile.mkdtemp(prefix='cinematicum-scientific-browser-',dir='/tmp'))\nwrite_deep_fixture(root/'ENGINE_TEST_depth.exr')\nstore=Store(root/'workspace')\ntry:\n    project=store.new_project({'name':'ENGINE TEST actual browser studio tools','width':32,'height':32,'fps':24})\n    scene,settings=fixture(32,32);settings['spp']=16\n    project['settings']['scene']=scene;project['physical_rendering']=settings\n    project=store.save(project['id'],project)\n    record={'id':project['id'],'owned_root':str(root),'source_exr_sha256':hashlib.sha256((root/'ENGINE_TEST_depth.exr').read_bytes()).hexdigest()}\n    (evidence/'project.json').write_text(json.dumps(record,indent=2)+'\\n')\n    print(json.dumps(record))\nfinally:store.shutdown()\n",studio,args['--evidence']],{env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'},encoding:'utf8',timeout:30000,maxBuffer:1024*1024});
if(prepared.status!==0)throw Error(prepared.stderr||String(prepared.error)||'Actual fixture preparation failed');
const root=args['--evidence'],config=JSON.parse(prepared.stdout),ownedRoot=config.owned_root,projectId=config.id;
const checks = [], errors = [], downloads = [], phases = []; let browser, server, origin, page;
const digest = data => crypto.createHash('sha256').update(data).digest('hex');
const sourceFiles = ['server.py','studio_tools.py','deep_compositing.py','deep_compositing_worker.py','ray_optics.py','ray_optics_worker.py','physical_rendering.py','physical_rendering_worker.py','runtime_management.py','web/app.js','web/index.html','web/deep-compositing-ui.js','web/ray-optics-ui.js','web/physical-rendering-ui.js','web/runtime-management-ui.js','engine.py','project_archive.py','test_physical_rendering.py','test_studio_tools.py','test_scientific_tools_browser.cjs'];
const sourceHashes = () => Object.fromEntries(sourceFiles.map(name=>[name,digest(fs.readFileSync(path.join(studio,name)))]));
const initial = sourceHashes(); const begun = Date.now();
function record(name, condition, detail) {checks.push({name,passed:!!condition,detail});write();if(!condition)throw Error(name+': '+JSON.stringify(detail));}
function phase(name) {phases.push({name,elapsed_ms:Date.now()-begun});write();}
function write(error) {fs.writeFileSync(path.join(root,'browser-report.json'),JSON.stringify({schema:'cinematicum-local-chromium-studio-acceptance',project_id:projectId,origin,chromium_executable_sha256:browserIdentity,owned_root:ownedRoot,started_source:initial,finished_source:sourceHashes(),phases,checks,downloads,page_errors:errors,error:error?String(error):null,elapsed_ms:Date.now()-begun},null,2)+'\n');}
async function project() {const response=await page.request.get(origin+'/api/projects/'+projectId);if(!response.ok())throw Error('Project read failed');return response.json();}
async function openTool(name, dialog) {await page.locator('#authoring-tools').click();await page.locator(`[data-authoring-tool="${name}"]`).click();await page.locator(dialog).waitFor({state:'visible'});}
async function saveMain() {await page.locator('#save-project').click();await page.waitForFunction(()=>document.querySelector('#save-state').textContent==='SAVED LOCALLY');}
function latestJob(kind) {return fs.readdirSync(path.join(ownedRoot,'workspace/jobs')).filter(name=>name.endsWith('.json')).map(name=>JSON.parse(fs.readFileSync(path.join(ownedRoot,'workspace/jobs',name)))).filter(j=>j.kind===kind&&j.project_id===projectId&&j.state==='completed').sort((a,b)=>b.created_at-a.created_at)[0];}
async function download(locator,filename,expected) {const event=page.waitForEvent('download');await locator.click();const item=await event;const target=path.join(root,filename);await item.saveAs(target);const bytes=fs.readFileSync(target);const actual=digest(bytes);downloads.push({filename,bytes:bytes.length,sha256:actual,suggested_filename:item.suggestedFilename()});record('download_'+filename,actual===expected,{expected,actual});}
async function run() {
  phase('launch_owned_server');
  const env={...process.env,TMPDIR:path.join(ownedRoot,'tmp'),PYTHONDONTWRITEBYTECODE:'1'};
  fs.mkdirSync(env.TMPDIR,{recursive:true});
  server=spawn(args['--python'],['-B',path.join(studio,'server.py'),'--workspace',path.join(ownedRoot,'workspace'),'--port','0'],{cwd:repo,env,stdio:['ignore','pipe','pipe']});
  const log=fs.createWriteStream(path.join(root,'server.stderr'));server.stderr.pipe(log);
  origin=await new Promise((resolve,reject)=>{let text='';const timer=setTimeout(()=>reject(Error('Owned server failed to start')),20000);server.stdout.on('data',chunk=>{text+=chunk.toString();const match=text.match(/CINEMATICUM editor: (http:\/\/127\.0\.0\.1:\d+)/);if(match){clearTimeout(timer);resolve(match[1]);}});server.on('exit',code=>{clearTimeout(timer);reject(Error('Owned server exited '+code));});});
  browser=await chromium.launch({executablePath:args['--browser'],headless:true});
  const context=await browser.newContext({viewport:{width:1440,height:1100},acceptDownloads:true});
  await context.route('**/*',route=>{const url=route.request().url();return url.startsWith(origin+'/')||url.startsWith('data:')||url.startsWith('blob:')?route.continue():route.abort();});
  page=await context.newPage();page.setDefaultTimeout(45000);page.on('pageerror',error=>{errors.push(String(error));write();});
  phase('bootstrap');await page.goto(origin);await page.waitForFunction(id=>document.querySelector('#project-select')?.value===id,projectId);
  record('exact_project_loaded',await page.locator('#project-select').inputValue()===projectId,projectId);

  phase('physical_save_undo_render');
  await openTool('physical-rendering','#physical-rendering-dialog');
  await page.locator('[data-physical-run]:not([disabled])').waitFor();
  record('physical_actual_runtime_ready',/Mitsuba 3\.9\.1/.test(await page.locator('[data-physical-runtime]').textContent()),await page.locator('[data-physical-runtime]').textContent());
  await page.locator('[data-physical-spp]').fill('32');await page.locator('[data-physical-save]').click();
  await page.waitForFunction(()=>document.querySelector('[data-physical-status]')?.textContent.includes('saved'));
  record('physical_saved_via_ui',(await project()).physical_rendering.spp===32);
  await page.locator('[data-physical-close]').click();await page.locator('#undo-button').click();await saveMain();
  record('physical_undo_saved',(await project()).physical_rendering.spp===16);
  await page.locator('#redo-button').click();await saveMain();record('physical_redo_saved',(await project()).physical_rendering.spp===32);
  await openTool('physical-rendering','#physical-rendering-dialog');await page.locator('[data-physical-run]:not([disabled])').waitFor();
  await page.locator('[data-physical-run]').click();await page.waitForFunction(()=>document.querySelector('[data-physical-status]')?.textContent.includes('Processing completed'));
  const physical=latestJob('physical-rendering');record('physical_completed_owned_job',!!physical,physical?.id);
  record('physical_float_rgb_radiance',physical.result.receipt.metrics.mean.every((v,i)=>Math.abs(v-[.2,.4,.6][i])<.03),physical.result.receipt.metrics.mean);
  await page.waitForFunction(()=>document.querySelector('[data-physical-preview]')?.naturalWidth===32);
  await page.screenshot({path:path.join(root,'physical-panel.png')});
  const physicalExr=physical.result.artifacts.find(a=>a.filename==='render.exr');
  await download(page.locator('[data-physical-artifacts] a').filter({hasText:'render.exr'}),'physical-render.exr',physicalExr.sha256);
  await page.locator('[data-physical-close]').click();

  phase('deep_import_apply_undo_render');
  await openTool('deep-compositing','dialog.deep-dialog');const deep=page.locator('dialog.deep-dialog');
  await deep.locator('[data-file]').setInputFiles(path.join(ownedRoot,'ENGINE_TEST_depth.exr'));
  await page.waitForFunction(()=>document.querySelector('.deep-dialog [data-status]')?.textContent.includes('EXR admitted'));
  await deep.locator('[data-add-source]').click();await deep.locator('[data-apply]').click();
  await page.waitForFunction(()=>document.querySelector('.deep-dialog [data-status]')?.textContent.includes('Graph applied'));
  const graph=(await project()).deep_compositing;record('deep_actual_source_and_saved_graph',graph?.nodes?.length===1&&graph.nodes[0].source_id.length===64);
  await deep.locator('[data-close]').click();await page.locator('#undo-button').click();await saveMain();record('deep_undo_saved',!(await project()).deep_compositing);
  await page.locator('#redo-button').click();await saveMain();record('deep_redo_saved',JSON.stringify((await project()).deep_compositing)===JSON.stringify(graph));
  await openTool('deep-compositing','dialog.deep-dialog');await deep.locator('[data-render]:not([disabled])').waitFor();await deep.locator('[data-render]').click();
  await page.waitForFunction(()=>document.querySelector('.deep-dialog [data-status]')?.textContent.includes('EXR rendered'));
  const deepJob=latestJob('deep-compositing');record('deep_completed_actual_samples',deepJob?.result.receipt.output.parts[0].deep===true&&deepJob.result.receipt.output.parts[0].total_samples===512,deepJob?.id);
  await page.waitForFunction(()=>document.querySelector('.deep-dialog [data-image]')?.naturalWidth===16);
  await page.screenshot({path:path.join(root,'deep-panel.png')});
  await download(deep.locator('[data-links] a').filter({hasText:'Download actual EXR'}),'deep-composite.exr',deepJob.result.artifacts.exr.sha256);
  await deep.locator('[data-close]').click();

  phase('optics_save_undo_analyze');
  await openTool('ray-optics','#ray-optics-dialog');await page.locator('[data-optics-analyze]:not([disabled])').waitFor();
  await page.locator('[data-optics-name]').fill('ENGINE TEST browser optical prescription');await page.locator('[data-optics-save]').click();
  await page.waitForFunction(()=>document.querySelector('[data-optics-status]')?.textContent.includes('saved'));
  const prescription=(await project()).ray_optics;record('optics_saved_via_ui',prescription?.name==='ENGINE TEST browser optical prescription');
  await page.locator('[data-optics-close]').click();await page.locator('#undo-button').click();await saveMain();record('optics_undo_saved',!(await project()).ray_optics);
  await page.locator('#redo-button').click();await saveMain();record('optics_redo_saved',(await project()).ray_optics?.name===prescription.name);
  await openTool('ray-optics','#ray-optics-dialog');await page.locator('[data-optics-analyze]:not([disabled])').waitFor();await page.locator('[data-optics-analyze]').click();
  await page.waitForFunction(()=>document.querySelector('[data-optics-results]')&&!document.querySelector('[data-optics-results]').hidden);
  const optics=latestJob('ray-optics');record('optics_completed_actual_analysis',!!optics,optics?.id);
  await page.locator('[data-optics-cancel]').waitFor({state:'hidden'});await page.screenshot({path:path.join(root,'optics-panel.png')});
  const analysis=optics.result.artifacts['analysis.json'];const jsonLink=page.locator('[data-optics-artifacts] a').filter({hasText:'Numerical analysis'});
  await download(jsonLink,'optics-analysis.json',analysis.sha256);await page.locator('[data-optics-close]').click();

  phase('runtime_information');await page.locator('#authoring-tools').click();await page.locator('#runtime-management-button').click();await page.locator('#runtime-management-dialog').waitFor();
  await page.waitForFunction(()=>document.querySelectorAll('[data-runtime-id]').length===4);
  record('runtime_fixed_cards',JSON.stringify((await page.locator('[data-runtime-id]').evaluateAll(nodes=>nodes.map(n=>n.dataset.runtimeId))).sort())===JSON.stringify(['learned','optiland','physical','reconstruction']));
  record('runtime_exact_pins_visible',await page.locator('[data-runtime-id="physical"] .runtime-lock').first().textContent()==='Lock SHA-256 '+digest(fs.readFileSync(path.join(studio,process.platform==='darwin'?'physical-rendering-macos-arm64-py313.lock.json':'physical-rendering-linux-x86_64-py312.lock.json'))));
  await page.screenshot({path:path.join(root,'runtime-panel.png')});await page.locator('[data-runtime-close]').click();
  phase('reopen');await page.reload();await page.waitForFunction(id=>document.querySelector('#project-select')?.value===id,projectId);
  const reopened=await project();record('documents_survive_browser_reload',reopened.physical_rendering.spp===32&&!!reopened.deep_compositing&&reopened.ray_optics.name===prescription.name);
  record('no_uncaught_browser_errors',errors.length===0,errors);record('tested_source_unchanged',JSON.stringify(sourceHashes())===JSON.stringify(initial));
  phase('complete');write();process.stdout.write(JSON.stringify({passed:checks.filter(c=>c.passed).length,total:checks.length,elapsed_ms:Date.now()-begun,report:path.join(root,'browser-report.json')})+'\n');
}
run().catch(async error=>{write(error);if(page){await page.screenshot({path:path.join(root,'failure.png')}).catch(()=>{});fs.writeFileSync(path.join(root,'failure-dom.txt'),await page.locator('body').innerText().catch(()=>''));}process.stderr.write(String(error.stack||error)+'\n');process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(server&&!server.killed){server.kill('SIGTERM');await new Promise(resolve=>{const timer=setTimeout(()=>{server.kill('SIGKILL');resolve();},10000);server.once('exit',()=>{clearTimeout(timer);resolve();});});}});
