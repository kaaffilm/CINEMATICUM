/* Actual two-window editing acceptance. Run with Playwright and an explicitly
   selected disposable Chromium executable; no signed-in browser is reused. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {spawn, spawnSync} from 'node:child_process';
const require = createRequire(import.meta.url);
const {chromium} = require('playwright');
const args = Object.fromEntries(Array.from({length: Math.floor((process.argv.length - 2) / 2)}, (_, index) =>
  [process.argv[2 + index * 2], process.argv[3 + index * 2]]));
for (const key of ['--python', '--browser', '--evidence']) if (!args[key] || !path.isAbsolute(args[key])) throw Error(key + ' requires an absolute path');
const studio = path.dirname(fileURLToPath(import.meta.url)), root = args['--evidence'];
fs.mkdirSync(root); // Preserve any earlier attempt in its original directory.
const checks = [], errors = [], started = Date.now(), participants = [];
let browser;
const sourceNames = ['server.py', 'engine.py', 'project_archive.py', 'collaboration.py', 'collaboration_store.py',
  'web/app.js', 'web/index.html', 'web/collaboration-ui.js', 'test_collaboration_browser.mjs'];
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const inventory = () => Object.fromEntries(sourceNames.map(name => [name, hash(fs.readFileSync(path.join(studio, name)))]));
const before = inventory();
function report(error = null) {
  fs.writeFileSync(path.join(root, 'browser-report.json'), JSON.stringify({
    schema: 'cinematicum-two-workspace-collaboration-browser-acceptance', version: 1,
    environment: 'Owned loopback HTTP/TLS coordinators and disposable Chromium profiles; not native macOS acceptance',
    checks, browser_errors: errors, error: error && String(error), source: before, elapsed_ms: Date.now() - started
  }, null, 2) + '\n');
}
function check(name, condition, detail) {
  checks.push({name, passed: Boolean(condition), detail}); report();
  if (!condition) throw Error(name + ': ' + JSON.stringify(detail));
}
const preparation = `
import json, pathlib, subprocess, sys
sys.path.insert(0, sys.argv[1])
from server import Store
root = pathlib.Path(sys.argv[2])
source = root / 'ENGINE_TEST_original.png'
subprocess.run(['ffmpeg','-v','error','-nostdin','-f','lavfi','-i','color=c=red:s=64x48',
                '-frames:v','1','-threads','1',str(source)], check=True, capture_output=True, timeout=15)
ids = {}
for name in ('owner','peer'):
    store = Store(root / name)
    try:
        project = store.new_project({'name':'ENGINE TEST ' + name, 'width':64,'height':48,'fps':24})
        if name == 'owner':
            asset = store.admit(project['id'],source,'Original red image.png')
            project = store.get(project['id'])
            project['clips']=[{'id':'picture','asset_id':asset['id'],'start':0,'duration':48,'track':0}]
            project = store.save(project['id'],project)
        ids[name] = project['id']
    finally: store.shutdown()
(root / 'projects.json').write_text(json.dumps(ids))
`;
const prepared = spawnSync(args['--python'], ['-I', '-B', '-c', preparation, studio, root], {encoding: 'utf8', timeout: 30000});
if (prepared.status !== 0) throw Error(prepared.stderr || 'Fixture preparation failed');
const ids = JSON.parse(fs.readFileSync(path.join(root, 'projects.json')));
async function launchServer(person, port = 0) {
  const child = spawn(args['--python'], ['-B', path.join(studio, 'server.py'), '--workspace', path.join(root, person.name), '--port', String(port)],
    {cwd: studio, env: {...process.env, PYTHONDONTWRITEBYTECODE: '1'}, stdio: ['ignore', 'pipe', 'pipe']});
  person.child = child;
  child.stderr.pipe(fs.createWriteStream(path.join(root, person.name + '-server.stderr'), {flags: 'a'}));
  const origin = await new Promise((resolve, reject) => {
    let output = ''; const timer = setTimeout(() => reject(Error('Owned server did not start')), 20000);
    child.stdout.on('data', chunk => {output += chunk; const match = output.match(/CINEMATICUM editor: (http:\/\/127\.0\.0\.1:\d+)/);
      if (match) {clearTimeout(timer); resolve(match[1]);}});
    child.once('exit', code => {clearTimeout(timer); reject(Error('Owned server exited: ' + code));});
  });
  if (person.origin && person.origin !== origin) throw Error('Restart changed the explicitly owned server address');
  person.origin = origin;
}
async function stopServer(person) {
  const child = person.child;
  if (!child || child.exitCode !== null) return;
  await new Promise(resolve => {
    const timeout = setTimeout(() => {child.kill('SIGKILL'); resolve();}, 10000);
    child.once('exit', () => {clearTimeout(timeout); resolve();});
    child.kill('SIGINT');
  });
}
async function readProject(person) {
  const response = await person.page.request.get(person.origin + '/api/projects/' + person.id);
  if (!response.ok()) throw Error('Project read failed');
  return response.json();
}
async function openSharing(person) {
  const dialog = person.page.locator('#collaboration-dialog');
  if (!(await dialog.evaluate(element => element.open))) {
    await person.page.locator('#authoring-tools').click();
    await person.page.locator('#collaboration-button').click();
  }
  await dialog.waitFor({state: 'visible'});
  await person.page.waitForFunction(() => !document.querySelector('[data-collab-close]').disabled);
}
async function closeSharing(person) {await person.page.locator('[data-collab-close]').click();}
async function selectPicture(person) {
  await person.page.locator('.timeline-clip[data-clip="picture"]').click({position: {x: 15, y: 12}});
  if (await person.page.evaluate(() => state.mode !== 'composite')) await person.page.locator('[data-mode="composite"]').click();
}
async function editRange(person, field, key, count = 1) {
  const placement = person.page.locator('.clip-transform-details');
  if (!(await placement.evaluate(element => element.open))) await placement.locator('summary').click();
  const input = person.page.locator('#ctrl-' + field);
  await input.focus();
  for (let index = 0; index < count; index++) await input.press(key);
  await input.press('Tab');
}
async function bothPose(owner, peer, x, opacity) {
  await Promise.all([owner, peer].map(person => person.page.waitForFunction(([x, opacity]) =>
    !state.dirty && !state.savePromise && Math.abs(state.project.clips[0].x - x) < 1e-8
      && Math.abs(state.project.clips[0].opacity - opacity) < 1e-8, [x, opacity])));
}
function recoveryDrafts(person) {
  const directory = path.join(root, person.name, 'projects', person.id, 'recovery');
  return fs.existsSync(directory) ? fs.readdirSync(directory).filter(name => name.endsWith('.json'))
    .map(name => JSON.parse(fs.readFileSync(path.join(directory, name))).project) : [];
}
async function main() {
  browser = await chromium.launch({executablePath: args['--browser'], headless: true});
  for (const name of ['owner', 'peer']) {
    const person = {name, id: ids[name]}; participants.push(person);
    await launchServer(person);
    person.context = await browser.newContext({viewport: {width: 1440, height: 1000}, acceptDownloads: true});
    await person.context.route('**/*', route => {
      const url = route.request().url();
      return url.startsWith(person.origin + '/') || url.startsWith('data:') || url.startsWith('blob:') ? route.continue() : route.abort();
    });
    person.page = await person.context.newPage();
    person.page.setDefaultTimeout(20000);
    person.page.on('pageerror', error => {errors.push({participant: name, error: String(error)}); report();});
    await person.page.goto(person.origin);
    await person.page.waitForFunction(id => document.querySelector('#project-select')?.value === id, person.id);
  }
  const [owner, peer] = participants;
  await openSharing(owner);
  await owner.page.locator('[data-collab-create]:not([disabled])').click();
  await owner.page.waitForFunction(() => document.querySelector('[data-collab-heading]').textContent === 'You host this shared project');
  check('explicit_host_started_via_ui', await owner.page.locator('[data-collab-url]').textContent().then(text => /^https:\/\/127\.0\.0\.1:\d+$/.test(text)));
  await owner.page.locator('[data-collab-invite]:not([disabled])').click();
  await owner.page.waitForFunction(() => document.querySelector('[data-collab-invitation-output]').value.length > 100);
  const invitation = await owner.page.locator('[data-collab-invitation-output]').inputValue();
  await openSharing(peer);
  await peer.page.locator('[data-collab-invitation-input]').fill(invitation);
  await peer.page.locator('[data-collab-join]').click();
  await peer.page.waitForFunction(id => state.project?.id !== id && state.project.clips.length === 1, peer.id);
  peer.id = await peer.page.locator('#project-select').inputValue();
  check('joined_new_project_without_overwriting_anchor', peer.id !== ids.peer && (await peer.page.request.get(peer.origin + '/api/projects/' + ids.peer)).ok());
  const ownerProject = await readProject(owner), peerProject = await readProject(peer);
  const picture = peerProject.assets[0];
  check('shared_actual_media_hash_verified', ownerProject.assets[0].sha256 === hash(fs.readFileSync(path.join(root, 'peer', 'projects', peer.id, picture.path))));
  check('invitation_consumed_and_removed_from_join_field', await peer.page.locator('[data-collab-invitation-input]').inputValue() === '');
  await closeSharing(owner); await closeSharing(peer);
  await selectPicture(owner); await selectPicture(peer);
  await Promise.all([editRange(owner, 'x', 'ArrowRight'), editRange(peer, 'opacity', 'ArrowLeft')]);
  await bothPose(owner, peer, .01, .99);
  check('two_real_ui_edits_merge_and_propagate', (await readProject(owner)).clips[0].opacity === .99 && (await readProject(peer)).clips[0].x === .01);
  check('committed_shared_edit_clears_full_snapshot_undo', await owner.page.evaluate(() => state.history.length === 0 && state.future.length === 0));
  await owner.page.locator('#undo-button').click();
  await bothPose(owner, peer, 0, .99);
  check('toolbar_undo_is_selective_and_keeps_peer_edit', (await readProject(peer)).clips[0].opacity === .99);
  await closeSharing(owner);
  await selectPicture(owner); await selectPicture(peer);
  await Promise.all([editRange(owner, 'x', 'ArrowRight'), editRange(peer, 'x', 'ArrowRight', 2)]);
  await Promise.race(participants.map(person => person.page.waitForFunction(() => !document.querySelector('[data-collab-conflict]').hidden)));
  const conflicted = (await owner.page.locator('[data-collab-conflict]').evaluate(element => !element.hidden)) ? owner : peer;
  const accepted = conflicted === owner ? peer : owner;
  const retainedX = await conflicted.page.evaluate(() => state.project.clips[0].x);
  const acceptedX = (await readProject(accepted)).clips[0].x;
  check('same_property_conflict_retains_open_draft', retainedX !== acceptedX && await conflicted.page.evaluate(() => state.dirty));
  await openSharing(conflicted);
  await conflicted.page.locator('[data-collab-use-shared]').click();
  await bothPose(owner, peer, acceptedX, .99);
  check('discard_choice_preserves_durable_recovery_checkpoint', recoveryDrafts(conflicted).some(project => project.clips[0].x === retainedX));
  await closeSharing(conflicted);
  await openSharing(owner);
  await owner.page.screenshot({path: path.join(root, 'owner-shared-panel.png')});
  await closeSharing(owner);
  const port = new URL(owner.origin).port;
  await stopServer(owner);
  await launchServer(owner, port);
  await owner.page.reload();
  await owner.page.waitForFunction(() => state.project && collaborationEditor?.getStatus()?.host_running === false);
  await openSharing(owner);
  check('reopened_host_never_listens_automatically', await owner.page.locator('[data-collab-resume]').isVisible());
  await closeSharing(owner); await selectPicture(owner);
  await editRange(owner, 'y', 'ArrowRight');
  check('offline_host_edit_remains_unsaved', await owner.page.evaluate(() => state.dirty && state.project.clips[0].y === .01));
  await openSharing(owner);
  await owner.page.locator('[data-collab-resume]').click();
  await owner.page.waitForFunction(() => collaborationEditor?.getStatus()?.host_running && !state.dirty && state.project.clips[0].y === 0);
  check('explicit_resume_preserves_offline_draft_before_adopting_shared_state', recoveryDrafts(owner).some(project => project.clips[0].y === .01));
  check('same_tls_pairing_survives_actual_server_restart', await owner.page.locator('[data-collab-url]').textContent() === JSON.parse(invitation).url);
  await closeSharing(owner);
  await openSharing(peer);
  if (await peer.page.locator('[data-collab-conflict]').isVisible()) await peer.page.locator('[data-collab-use-shared]').click();
  else await peer.page.locator('[data-collab-sync]').click();
  await peer.page.waitForFunction(() => !state.dirty && document.querySelector('[data-collab-conflict]').hidden);
  await peer.page.locator('[data-collab-leave]').click();
  await peer.page.waitForFunction(() => collaborationEditor?.isActive() === false);
  check('leave_retains_local_media_and_project', (await readProject(peer)).assets.length === ownerProject.assets.length);
  await closeSharing(peer); await selectPicture(peer);
  await editRange(peer, 'y', 'ArrowRight', 2);
  await peer.page.locator('#save-project').click();
  await peer.page.waitForFunction(() => !state.dirty && !state.savePromise);
  check('disconnected_edit_is_local_only', (await readProject(peer)).clips[0].y === .02 && (await readProject(owner)).clips[0].y === 0);
  check('no_uncaught_browser_errors', errors.length === 0, errors);
  check('tested_source_unchanged', JSON.stringify(before) === JSON.stringify(inventory()));
  report();
  process.stdout.write(JSON.stringify({passed: checks.filter(check => check.passed).length, total: checks.length,
    elapsed_ms: Date.now() - started, report: path.join(root, 'browser-report.json')}) + '\n');
}
main().catch(async error => {
  report(error); process.stderr.write(String(error.stack || error) + '\n'); process.exitCode = 1;
  for (const person of participants) if (person.page) {
    // Invitation material is removed before evidence screenshots are captured.
    await person.page.evaluate(() => {for (const element of document.querySelectorAll('[data-collab-invitation-output],[data-collab-invitation-input]')) element.value = '';}).catch(() => {});
    await person.page.screenshot({path: path.join(root, person.name + '-failure.png')}).catch(() => {});
    fs.writeFileSync(path.join(root, person.name + '-failure-dom.txt'), await person.page.locator('body').innerText().catch(() => ''));
  }
}).finally(async () => {
  if (browser) await browser.close();
  for (const person of participants) await stopServer(person);
});
