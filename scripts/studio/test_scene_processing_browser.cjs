/* Actual scene-authoring and two-worker acceptance in disposable Chromium.
   Usage: node test_scene_processing_browser.cjs --python /absolute/python
     --browser /absolute/chrome --blender-dir /absolute/blender-directory
     --evidence /absolute/new-evidence-directory
   Every authoring/worker mutation uses the visible Studio controls. Fixture
   creation and independent reads/decode checks use only owned test workspaces.
   Invitations remain in memory and private workspace storage, never receipts. */
'use strict';
const fs = require('fs'), path = require('path'), crypto = require('crypto'), net = require('net');
const {spawn, spawnSync} = require('child_process'), {chromium} = require('playwright');
const args = {};
if ((process.argv.length - 2) % 2) throw Error('Use paired --option value arguments.');
for (let i = 2; i < process.argv.length; i += 2) {
  if (args[process.argv[i]]) throw Error('Duplicate option: ' + process.argv[i]);
  args[process.argv[i]] = process.argv[i + 1];
}
for (const key of ['--python', '--browser', '--blender-dir', '--evidence'])
  if (!args[key] || !path.isAbsolute(args[key])) throw Error(key + ' requires an absolute path');
if (Object.keys(args).some(key => !['--python', '--browser', '--blender-dir', '--evidence'].includes(key))) throw Error('Unknown argument.');
const studio = __dirname, evidence = args['--evidence'];
fs.mkdirSync(evidence); // A previous receipt is never overwritten by a rerun.
const env = {...process.env, PATH: args['--blender-dir'] + path.delimiter + process.env.PATH,
  PYTHONDONTWRITEBYTECODE: '1'};
const checks = [], errors = [], downloads = [], phases = [], participants = [], begun = Date.now();
let browser, ownedRoot;
const digest = data => crypto.createHash('sha256').update(data).digest('hex');
const browserSha256 = digest(fs.readFileSync(args['--browser']));
const stable = value => JSON.stringify(value, (_, item) => item && !Array.isArray(item) && typeof item === 'object'
  ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item);
const sourceNames = ['server.py', 'engine.py', 'studio_tools.py', 'project_archive.py', 'scene.py', 'scene_processing.py',
  'scene_processing_worker.py', 'scene_dispatch.py', 'scene_dispatch_store.py', 'collaboration.py', 'test_scene_processing.py',
  'web/app.js', 'web/index.html', 'web/scene-processing-ui.js', 'test_scene_processing_browser.cjs'];
const sourceInventory = () => Object.fromEntries(sourceNames.map(name => [name, digest(fs.readFileSync(path.join(studio, name)))]));
const sourceBefore = sourceInventory();
function report(error = null) {
  fs.writeFileSync(path.join(evidence, 'browser-report.json'), JSON.stringify({
    schema: 'cinematicum-scene-processing-real-browser-acceptance', version: 1,
    scope: 'Actual owned Linux Chromium, loopback Studios, pinned TLS workers and CPU Blender Cycles; not native macOS UI acceptance.',
    checks, phases, downloads, browser_errors: errors, error: error && String(error),
    source_before: sourceBefore, source_after: sourceInventory(), elapsed_ms: Date.now() - begun,
    chromium_executable_sha256: browserSha256,
    participants: participants.map(person => ({name: person.name, project_id: person.id, origin: person.origin})),
  }, null, 2) + '\n');
}
function check(name, passed, detail) {
  checks.push({name, passed: Boolean(passed), detail}); report();
  if (!passed) throw Error(name + ': ' + JSON.stringify(detail));
}
function phase(name) {phases.push({name, elapsed_ms: Date.now() - begun}); report();}
function python(code, additional = [], timeout = 30000) {
  const result = spawnSync(args['--python'], ['-I', '-B', '-c', code, studio, ...additional],
    {env, encoding: 'utf8', timeout, maxBuffer: 8 * 1024 * 1024});
  if (result.status !== 0) throw Error(result.stderr || String(result.error) || 'Independent Python check failed');
  return result.stdout;
}
async function launchServer(person, port = 0) {
  const child = spawn(args['--python'], ['-B', path.join(studio, 'server.py'), '--workspace', path.join(ownedRoot, person.name), '--port', String(port)],
    {cwd: studio, env: {...env, TMPDIR: path.join(ownedRoot, 'tmp')}, stdio: ['ignore', 'pipe', 'pipe']});
  person.child = child;
  child.stderr.pipe(fs.createWriteStream(path.join(evidence, person.name + '-server.stderr'), {flags: 'a'}));
  const origin = await new Promise((resolve, reject) => {
    let output = ''; const timer = setTimeout(() => reject(Error('Owned server did not start within 20 seconds')), 20000);
    child.stdout.on('data', chunk => {output += chunk; const match = output.match(/CINEMATICUM editor: (http:\/\/127\.0\.0\.1:\d+)/);
      if (match) {clearTimeout(timer); resolve(match[1]);}});
    child.once('exit', code => {clearTimeout(timer); reject(Error('Owned server exited: ' + code));});
  });
  if (person.origin && origin !== person.origin) throw Error('Restart changed the owned HTTP address');
  person.origin = origin;
}
async function stopServer(person) {
  const child = person.child;
  if (!child || child.exitCode !== null) return;
  await new Promise(resolve => {
    const timer = setTimeout(() => {child.kill('SIGKILL'); resolve();}, 10000);
    child.once('exit', () => {clearTimeout(timer); resolve();}); child.kill('SIGTERM');
  });
}
async function read(person, url) {
  const response = await person.page.request.get(person.origin + url);
  if (!response.ok()) throw Error('Owned read failed: ' + url + ' HTTP ' + response.status());
  return response.json();
}
const project = person => read(person, '/api/projects/' + person.id);
async function openPanel(person) {
  await person.page.locator('#authoring-tools').click();
  await person.page.locator('[data-authoring-tool="scene-processing"]').click();
  await person.page.locator('#scene-processing-dialog').waitFor({state: 'visible'});
  await person.page.locator('[data-sp-save]:not([disabled])').waitFor();
}
async function status(person, text) {
  await person.page.waitForFunction(value => document.querySelector('[data-sp-status]')?.textContent.includes(value), text);
}
async function saveMain(person) {
  await person.page.locator('#save-project').click();
  await person.page.waitForFunction(() => document.querySelector('#save-state')?.textContent === 'SAVED LOCALLY');
}
function jobs(person, kind) {
  return fs.readdirSync(path.join(ownedRoot, person.name, 'jobs')).filter(name => name.endsWith('.json'))
    .map(name => JSON.parse(fs.readFileSync(path.join(ownedRoot, person.name, 'jobs', name))))
    .filter(job => job.project_id === person.id && job.kind === kind && job.state === 'completed')
    .sort((a, b) => b.created_at - a.created_at);
}
async function download(person, job, filename, prefix) {
  const expected = filename === 'receipt.json' ? job.result.provenance.receipt_sha256
    : job.result.receipt.artifacts.find(item => item.filename === filename)?.sha256;
  if (!expected) throw Error('Published receipt omitted ' + filename);
  const promise = person.page.waitForEvent('download');
  await person.page.locator('[data-sp-artifacts] a').filter({hasText: new RegExp('^' + filename.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '$')}).click();
  const transfer = await promise, target = path.join(evidence, prefix + '-' + filename);
  await transfer.saveAs(target);
  const bytes = fs.readFileSync(target), actual = digest(bytes);
  downloads.push({name: prefix + '-' + filename, bytes: bytes.length, sha256: actual, suggested_filename: transfer.suggestedFilename()});
  check('exact_' + prefix + '_download_' + filename, actual === expected, {expected, actual});
  return target;
}
function decode(pathname) {
  const output = spawnSync('ffmpeg', ['-v', 'error', '-nostdin', '-i', pathname, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-threads', '1', '-'],
    {env, timeout: 30000, maxBuffer: 16 * 1024 * 1024});
  if (output.status !== 0) throw Error(output.stderr.toString() || 'Independent actual video decode failed');
  const size = 64 * 48 * 3;
  if (output.stdout.length % size) throw Error('Decoded picture contains a partial frame');
  const centers = [];
  for (let start = 0; start < output.stdout.length; start += size) {
    let total = 0, count = 0;
    for (let index = 0; index < size / 3; index++) {
      const offset = start + index * 3, [r, g, b] = output.stdout.subarray(offset, offset + 3);
      if (r > 90 && r > 2 * g && r > 2 * b) {total += index % 64; count++;}
    }
    if (!count) throw Error('Actual rendered picture lacks expected red geometry');
    centers.push(total / count);
  }
  return centers;
}
async function distributedSection(person) {
  const section = person.page.locator('[data-sp-distributed]');
  if (!await section.evaluate(node => node.open)) await section.locator('summary').first().click();
}
function endpointClosed(endpoint) {
  const parsed = new URL(endpoint);
  return new Promise(resolve => {
    const socket = net.createConnection({host: parsed.hostname, port: Number(parsed.port)});
    socket.setTimeout(1500); socket.once('connect', () => {socket.destroy(); resolve(false);});
    socket.once('error', error => {socket.destroy(); resolve(error.code === 'ECONNREFUSED');});
    socket.once('timeout', () => {socket.destroy(); resolve(false);});
  });
}
async function main() {
  phase('prepare_independent_owned_workspaces');
  const prepared = JSON.parse(python(`
import json,pathlib,sys,tempfile
sys.path.insert(0,sys.argv[1])
from server import Store
from test_scene_processing import fixture
root=pathlib.Path(tempfile.mkdtemp(prefix='cinematicum-scene-browser-',dir='/tmp'))
(root/'tmp').mkdir()
graph=fixture(animated=True);graph['assets'][0]['scene']['output']={'linear_exr':True,'passes':['depth','emission']}
identities={}
for name in ('owner','peer'):
    store=Store(root/name)
    try:
        project=store.new_project({'name':'ENGINE TEST scene browser '+name,'width':64,'height':48,'fps':24})
        project['settings']['scene']=graph['assets'][0]['scene'];project=store.save(project['id'],project)
        identities[name]=project['id']
    finally:store.shutdown()
print(json.dumps({'owned_root':str(root),'identities':identities}))
`));
  ownedRoot = prepared.owned_root;
  fs.writeFileSync(path.join(evidence, 'fixture-identity.json'), JSON.stringify(prepared, null, 2) + '\n');
  for (const name of ['owner', 'peer']) participants.push({name, id: prepared.identities[name]});
  for (const person of participants) await launchServer(person);
  browser = await chromium.launch({executablePath: args['--browser'], headless: true});
  for (const person of participants) {
    const context = await browser.newContext({viewport: {width: 1440, height: 1100}, acceptDownloads: true});
    await context.route('**/*', route => {
      const url = route.request().url();
      return url.startsWith(person.origin + '/') || url.startsWith('data:') || url.startsWith('blob:') ? route.continue() : route.abort();
    });
    person.page = await context.newPage(); person.page.setDefaultTimeout(60000);
    person.page.on('pageerror', error => {errors.push({participant: person.name, error: String(error)}); report();});
    await person.page.goto(person.origin);
    await person.page.waitForFunction(id => document.querySelector('#project-select')?.value === id, person.id);
    check(person.name + '_exact_project_loaded', await person.page.locator('#project-select').inputValue() === person.id);
    check(person.name + '_no_worker_at_startup', (await read(person, '/api/scene-workers')).workers.length === 0);
  }
  const [owner, peer] = participants, page = owner.page, original = await project(owner);
  phase('author_graph_using_actual_controls'); await openPanel(owner);
  check('actual_cycles_available', !await page.locator('[data-sp-render]').isDisabled());
  await page.locator('[data-sp-capture]').click(); await status(owner, 'Current 3D scene captured');
  await page.locator('[data-sp-name]').fill('ENGINE TEST typed scene workflow');
  await page.getByText('Edit typed context schema', {exact: true}).click();
  const schema = JSON.parse(await page.locator('[data-sp-schema]').inputValue());
  schema.offset = {type: 'float', default: 0, min: -2, max: 2};
  await page.locator('[data-sp-schema]').fill(JSON.stringify(schema));
  await page.locator('[data-sp-schema-update]').click();
  await page.locator('[data-sp-operation]').selectOption('set'); await page.locator('[data-sp-add]').click();
  const setNode = JSON.parse(await page.locator('[data-sp-node-json]').inputValue());
  setNode.name = 'hero'; setNode.filter = {paths: ['/world/objects/box']};
  await page.locator('[data-sp-node-json]').fill(JSON.stringify(setNode)); await page.locator('[data-sp-node-update]').click();
  await page.locator('[data-sp-operation]').selectOption('transform'); await page.locator('[data-sp-add]').click();
  const transformNode = JSON.parse(await page.locator('[data-sp-node-json]').inputValue());
  transformNode.space = 'parent'; transformNode.filter = {sets: 'hero'};
  transformNode.transform.position = [{context: 'offset'}, 0, 0];
  await page.locator('[data-sp-node-json]').fill(JSON.stringify(transformNode)); await page.locator('[data-sp-node-update]').click();
  await page.locator('[data-sp-save]').click(); await status(owner, 'Scene graph saved as one undoable edit');
  const saved = await project(owner);
  check('authored_typed_graph_saved', saved.scene_processing.nodes.length === 3 && saved.scene_processing.nodes[1].name === 'hero'
    && saved.scene_processing.context.offset.type === 'float' && saved.scene_processing.output === transformNode.id);
  check('graph_save_preserves_original_scene', stable(saved.settings.scene) === stable(original.settings.scene));
  await page.locator('[data-sp-close]').click(); await page.locator('#undo-button').click(); await saveMain(owner);
  check('graph_save_one_undo', !(await project(owner)).scene_processing);
  await page.locator('#redo-button').click(); await saveMain(owner);
  check('graph_redo_durable', stable((await project(owner)).scene_processing) === stable(saved.scene_processing));
  phase('real_path_set_context_evaluation'); await openPanel(owner);
  await page.locator('[data-context="frame"]').fill('3'); await page.locator('[data-context="offset"]').fill('-0.5');
  await page.locator('[data-sp-evaluate]').click(); await status(owner, 'Graph evaluation saved');
  const evaluated = jobs(owner, 'scene-processing')[0];
  check('owned_evaluation_job', evaluated?.result.operation === 'evaluate' && evaluated.result.output_id === evaluated.id);
  const evaluatedObject = evaluated.result.evaluation.locations.find(item => item.path === '/world/objects/box');
  check('actual_paths_sets_and_context_math', evaluatedObject.world_transform[12] === 0.5
    && stable(evaluated.result.evaluation.sets.hero) === stable(['/world/objects/box'])
    && evaluated.result.evaluation.context.frame === 3 && evaluated.result.evaluation.context.time === 0.125,
    {world_x: evaluatedObject.world_transform[12], context: evaluated.result.evaluation.context});
  check('evaluation_does_not_silently_apply', stable((await project(owner)).settings.scene) === stable(original.settings.scene));
  await page.locator('[data-sp-paths] tr').filter({hasText: '/world/objects/box'}).click();
  check('query_location_visible', JSON.parse(await page.locator('[data-sp-location]').textContent()).world_transform[12] === 0.5);
  const preStale = await project(owner);
  await page.locator('[data-context="offset"]').fill('0.7'); await page.locator('[data-sp-apply-scene]').click();
  await status(owner, 'graph or context changed');
  check('stale_context_application_rejected_without_mutation', stable(await project(owner)) === stable(preStale));
  await page.locator('[data-context="offset"]').fill('-0.5'); await page.locator('[data-sp-apply-scene]').click();
  await status(owner, 'Evaluated single-frame scene and graph saved');
  check('sampled_scene_applied_exactly', stable((await project(owner)).settings.scene) === stable(evaluated.result.scene));
  await page.locator('[data-sp-close]').click(); await page.locator('#undo-button').click(); await saveMain(owner);
  check('sampled_scene_one_undo', stable((await project(owner)).settings.scene) === stable(original.settings.scene)
    && stable((await project(owner)).scene_processing) === stable(saved.scene_processing));
  await page.locator('#redo-button').click(); await saveMain(owner); await page.reload();
  await page.waitForFunction(id => document.querySelector('#project-select')?.value === id, owner.id);
  check('scene_and_graph_reopen_durable', stable((await project(owner)).settings.scene) === stable(evaluated.result.scene)
    && stable((await project(owner)).scene_processing) === stable(saved.scene_processing));
  phase('actual_local_cycles_render'); await openPanel(owner);
  await page.locator('[data-context="frame"]').fill('3'); await page.locator('[data-context="offset"]').fill('-0.5');
  await page.locator('[data-sp-render]').click(); await status(owner, 'Actual Cycles frame and editable .blend saved');
  const rendered = jobs(owner, 'scene-processing')[0];
  check('actual_cycles_render_receipt', rendered.result.receipt.operation === 'render' && rendered.result.receipt.renderer
    && rendered.result.asset?.kind === 'video' && rendered.result.asset.provenance.type === 'cinematicum-scene-processing');
  await page.waitForFunction(() => document.querySelector('[data-sp-preview]')?.readyState >= 1);
  check('actual_render_preview_metadata', await page.locator('[data-sp-preview]').evaluate(node => node.videoWidth === 64 && node.videoHeight === 48));
  for (const filename of ['preview.mp4', 'authored.blend', 'linear-masters.zip', 'graph.json', 'receipt.json']) await download(owner, rendered, filename, 'local');
  const localCenters = decode(path.join(evidence, 'local-preview.mp4'));
  check('local_cycles_pixels_independently_decoded', localCenters.length === 1 && localCenters[0] > 32, {red_centers: localCenters});
  await page.screenshot({path: path.join(evidence, 'local-render.png')});
  await page.locator('[data-sp-close]').click(); await page.reload();
  await page.waitForFunction(id => document.querySelector('#project-select')?.value === id, owner.id); await openPanel(owner);
  await page.locator('[data-sp-history]').selectOption(rendered.id); await page.locator('[data-sp-load]').click();
  await status(owner, 'Saved result reopened');
  check('immutable_render_history_reopens', await page.locator('[data-sp-artifacts] a').count() === Object.keys(rendered.result.artifact_urls).length
    && (await page.locator('[data-sp-summary]').textContent()).includes('context frame 3'));
  fs.writeFileSync(path.join(evidence, 'local-render-job.json'), JSON.stringify(rendered, null, 2) + '\n');
  phase('explicit_worker_pairing'); await distributedSection(owner);
  await page.locator('[data-sp-worker-name]').fill('worker-a'); await page.locator('[data-sp-start]').click(); await status(owner, 'Worker start completed');
  const workerA = (await read(owner, '/api/scene-workers')).workers[0];
  check('owner_explicit_actual_worker_started', workerA.local === true && workerA.running === true && /^https:\/\/127\.0\.0\.1:/.test(workerA.endpoint));
  await page.locator('[data-sp-invite]').click(); await status(owner, 'One-use invitation created');
  let invitation = await page.locator('[data-sp-invitation]').inputValue();
  check('invitation_requires_explicit_action', Boolean(JSON.parse(invitation)) && (await read(peer, '/api/scene-workers')).workers.length === 0);
  await openPanel(peer); await peer.page.locator('[data-sp-import-file]').setInputFiles(path.join(evidence, 'local-graph.json'));
  await status(peer, 'Imported graph validated and saved');
  check('downloaded_graph_imported_and_saved', stable((await project(peer)).scene_processing) === stable(saved.scene_processing));
  await distributedSection(peer); await peer.page.locator('[data-sp-worker-name]').fill('worker-a');
  await peer.page.locator('[data-sp-participant]').fill('ENGINE TEST peer');
  await peer.page.locator('[data-sp-pair-invitation]').fill(invitation); await peer.page.locator('[data-sp-pair]').click(); await status(peer, 'Worker pair completed');
  invitation = ''; // No invitation bytes are written to a durable acceptance report.
  const remote = (await read(peer, '/api/scene-workers')).workers[0];
  check('actual_pinned_tls_pairing', remote.local === false && remote.worker_id === workerA.worker_id
    && remote.certificate_sha256 === workerA.certificate_sha256 && remote.client_id !== workerA.client_id
    && await peer.page.locator('[data-sp-pair-invitation]').inputValue() === '');
  await page.locator('[data-sp-close]').click(); // Clears the displayed one-use invitation.
  await peer.page.locator('[data-sp-worker-name]').fill('worker-b'); await peer.page.locator('[data-sp-start]').click(); await status(peer, 'Worker start completed');
  const peerWorkers = (await read(peer, '/api/scene-workers')).workers, workerB = peerWorkers.find(item => item.name === 'worker-b');
  check('two_distinct_actual_render_workers', peerWorkers.length === 2 && workerB.local && workerB.running && workerB.worker_id !== workerA.worker_id);
  for (const name of ['worker-a', 'worker-b']) await peer.page.locator('[data-sp-workers] input[value="' + name + '"]').check();
  await peer.page.locator('[data-sp-frames]').fill('1, 3'); await peer.page.locator('[data-sp-variations]').fill('[{"offset":0}]');
  phase('actual_distributed_cycles_frames'); await peer.page.locator('[data-sp-dispatch]').click(); await status(peer, 'Distributed result collected');
  const distributed = jobs(peer, 'scene-dispatch')[0];
  check('two_actual_workers_completed_owned_batch', distributed.result.receipt.worker_count === 2 && distributed.result.receipt.task_count === 2
    && distributed.result.receipt.batch_id === distributed.result.output_id);
  for (const filename of ['preview.mp4', 'dispatch.json', 'tasks.zip', 'receipt.json']) await download(peer, distributed, filename, 'distributed');
  const dispatchManifest = JSON.parse(fs.readFileSync(path.join(evidence, 'distributed-dispatch.json')));
  check('actual_task_order_and_worker_identities', stable(dispatchManifest.tasks.map(task => task.context.frame)) === stable([1, 3])
    && new Set(dispatchManifest.tasks.map(task => task.worker_identity.worker_id)).size === 2);
  const centers = decode(path.join(evidence, 'distributed-preview.mp4'));
  check('distributed_pixels_preserve_frame_order', centers.length === 2 && centers[1] > centers[0] + 8, {red_centers: centers});
  const batches = await read(peer, '/api/projects/' + peer.id + '/scene-dispatch');
  check('durable_batch_state_completed', batches.batches.some(batch => batch.id === distributed.result.output_id && batch.status === 'completed'));
  fs.writeFileSync(path.join(evidence, 'distributed-job.json'), JSON.stringify(distributed, null, 2) + '\n');
  await peer.page.screenshot({path: path.join(evidence, 'distributed-result.png')});
  await peer.page.locator('[data-sp-close]').click(); await peer.page.reload();
  await peer.page.waitForFunction(id => document.querySelector('#project-select')?.value === id, peer.id); await openPanel(peer);
  await peer.page.locator('[data-sp-history]').selectOption(distributed.result.output_id); await peer.page.locator('[data-sp-load]').click(); await status(peer, 'Saved result reopened');
  check('distributed_saved_result_reopens', (await peer.page.locator('[data-sp-summary]').textContent()).includes('2 actual frame tasks across 2 workers')
    && await peer.page.locator('[data-sp-apply-scene]').isDisabled());
  phase('explicit_stop_and_restart_do_not_listen'); await distributedSection(peer);
  await peer.page.locator('[data-sp-worker-name]').fill('worker-b'); await peer.page.locator('[data-sp-stop]').click(); await status(peer, 'Worker stop completed');
  check('peer_worker_stopped_through_ui', (await read(peer, '/api/scene-workers')).workers.find(item => item.name === 'worker-b').running === false
    && await endpointClosed(workerB.endpoint));
  await openPanel(owner); await distributedSection(owner); await page.locator('[data-sp-worker-name]').fill('worker-a');
  await page.locator('[data-sp-stop]').click(); await status(owner, 'Worker stop completed');
  check('owner_worker_stopped_through_ui', (await read(owner, '/api/scene-workers')).workers[0].running === false && await endpointClosed(workerA.endpoint));
  const persisted = await project(owner), port = Number(new URL(owner.origin).port);
  await stopServer(owner); await launchServer(owner, port); await page.reload();
  await page.waitForFunction(id => document.querySelector('#project-select')?.value === id, owner.id); await openPanel(owner);
  const restarted = (await read(owner, '/api/scene-workers')).workers[0];
  check('restart_preserves_worker_identity_without_listening', restarted.worker_id === workerA.worker_id && restarted.certificate_sha256 === workerA.certificate_sha256
    && restarted.running === false && await endpointClosed(workerA.endpoint));
  check('restart_preserves_project_exactly', stable(await project(owner)) === stable(persisted));
  check('no_uncaught_browser_errors', errors.length === 0, errors);
  check('tested_source_unchanged', stable(sourceInventory()) === stable(sourceBefore)); phase('complete');
  console.log(JSON.stringify({passed: checks.filter(item => item.passed).length, total: checks.length, elapsed_ms: Date.now() - begun,
    report: path.join(evidence, 'browser-report.json')}));
}
main().catch(async error => {
  // A failed pairing phase may still display an invitation. Capture only
  // ordinary status strings, never a full page/DOM containing credentials.
  const statuses = {};
  for (const person of participants) if (person.page) statuses[person.name] = await person.page.evaluate(() => document.querySelector('[data-sp-status]')?.textContent || 'unavailable').catch(() => 'unavailable');
  fs.writeFileSync(path.join(evidence, 'failure-status.json'), JSON.stringify(statuses, null, 2) + '\n');
  report(error); console.error(String(error.stack || error)); process.exitCode = 1;
}).finally(async () => {
  if (browser) await browser.close();
  for (const person of [...participants].reverse()) await stopServer(person);
});
