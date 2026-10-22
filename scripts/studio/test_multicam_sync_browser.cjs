#!/usr/bin/env node
/* Runs the same real shipped-control/media acceptance through Chromium.
 * Required: --python ABS --browser ABS --evidence NEW_ABS. The Python runtime
 * needs NumPy; FFmpeg/FFprobe must be on PATH. No native acceptance is claimed.
 */
'use strict';
const fs = require('fs'), path = require('path'), crypto = require('crypto');
const {spawnSync} = require('child_process');
const options = {}, values = process.argv.slice(2);
const helper = values[0] === '--helper'; if (helper) values.shift();
if (values.length % 2) throw Error('Use paired --option value arguments');
for (let i = 0; i < values.length; i += 2) {
  if (options[values[i]]) throw Error('Duplicate option'); options[values[i]] = values[i + 1];
}
const hash = data => crypto.createHash('sha256').update(data).digest('hex');
function absolute(key) {if (!options[key] || !path.isAbsolute(options[key])) throw Error(key + ' requires an absolute path'); return options[key];}

async function browserHelper() {
  const {chromium} = require('playwright');
  for (const key of ['--browser', '--output', '--script', '--download-dir']) absolute(key);
  const origin = new URL(options['--url']).origin;
  if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(origin)) throw Error('The helper only accepts its explicit loopback fixture');
  const seconds = Number(options['--timeout']); if (!Number.isFinite(seconds) || seconds <= 0 || seconds > 15) throw Error('The foreground browser timeout is invalid');
  const started = Date.now(), deadline = started + seconds * 1000, downloads = [], errors = [], downloadErrors = [];
  let browser, page, timer, finished = false, pending = [];
  async function close() {if (finished) return; finished = true; clearTimeout(timer); if (browser) await browser.close();}
  process.once('SIGTERM', () => {close().finally(() => process.exit(1));});
  try {
    browser = await chromium.launch({executablePath: options['--browser'], headless: true});
    const context = await browser.newContext({viewport: {width: 1440, height: 1100}, acceptDownloads: true});
    await context.route('**/*', route => {
      const url = route.request().url(); return url.startsWith(origin + '/') || url.startsWith('data:') || url.startsWith('blob:') ? route.continue() : route.abort();
    });
    page = await context.newPage(); page.setDefaultTimeout(Math.max(1, deadline - Date.now()));
    page.on('pageerror', error => errors.push(String(error)));
    page.on('download', download => {
      const promise = (async () => {
        const name = download.suggestedFilename(), target = path.join(options['--download-dir'], name);
        if (name !== path.basename(name) || fs.existsSync(target)) throw Error('Unexpected or duplicate owned download');
        await download.saveAs(target); const failure = await download.failure();
        if (failure) throw Error(failure);
        downloads.push({state: 'completed', url: download.url(), suggested_filename: name, path: target});
      })().catch(error => downloadErrors.push(String(error))); pending.push(promise);
    });
    const timeout = new Promise((_, reject) => {timer = setTimeout(() => reject(Error('Chromium foreground deadline exceeded')), Math.max(1, deadline - Date.now()));});
    const work = (async () => {
      await page.goto(options['--url']);
      const script = fs.readFileSync(options['--script'], 'utf8');
      const result = await page.evaluate(source => (new Function('return (async () => {' + source + '\n})();'))(), script);
      const explicitCount = result.expected_download_count;
      if (explicitCount !== undefined && (!Number.isInteger(explicitCount) || explicitCount < 0 || explicitCount > 32)) throw Error('Invalid expected download count');
      const minimumCount = explicitCount ?? (result.expect_download ? 1 : 0);
      // A click may return before the browser emits its download event. Wait
      // for the declared count as well as the currently registered promises.
      // An already completed ZIP must not conceal the still-pending MOV.
      while (result.passed === true && !downloadErrors.length && Date.now() < deadline - 350) {
        await Promise.all(pending);
        if (downloads.length >= minimumCount && downloads.length === pending.length) break;
        await new Promise(resolve => setTimeout(resolve, 25));
      }
      const countMatches = explicitCount === undefined ? downloads.length >= minimumCount : downloads.length === explicitCount;
      if (result.passed === true && (!countMatches || downloads.length !== pending.length)) throw Error('Downloads did not complete: expected ' + minimumCount + ', completed ' + downloads.length);
      await page.screenshot({path: options['--output']});
      return {...result, page_errors: errors, downloads, download_errors: downloadErrors, completed_download_count: downloads.length,
        passed: result.passed === true && !errors.length && !downloadErrors.length && countMatches && downloads.length === pending.length,
        transport: 'Chromium', native_certified: false, screenshot: options['--output']};
    })();
    const result = await Promise.race([work, timeout]); process.stdout.write(JSON.stringify(result) + '\n');
    if (!result.passed) process.exitCode = 1;
  } catch (error) {
    if (page) await page.screenshot({path: options['--output'], timeout: 500}).catch(() => {});
    process.stdout.write(JSON.stringify({passed: false, error: String(error), page_errors: errors, downloads, download_errors: downloadErrors, native_certified: false}) + '\n'); process.exitCode = 1;
  } finally {await close();}
}

function driver() {
  for (const key of ['--python', '--browser', '--evidence']) absolute(key);
  if (Object.keys(options).some(k => !['--python', '--browser', '--evidence'].includes(k))) throw Error('Unknown browser driver option');
  const evidence = options['--evidence']; fs.mkdirSync(evidence);
  const browserSha = hash(fs.readFileSync(options['--browser']));
  // The small executable adapter keeps the native coordinator's exact argv
  // contract. It executes this same reviewed file, with no shell interpolation.
  const adapter = path.join(evidence, 'chromium-adapter.cjs');
  fs.writeFileSync(adapter, '#!' + process.execPath + '\n' +
    "process.argv.splice(2,0,'--helper','--browser'," + JSON.stringify(options['--browser']) + ');\n' +
    'require(' + JSON.stringify(__filename) + ');\n', {mode: 0o700});
  const code = "import json,sys\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nfrom test_multicam_sync_macos import run,source_inventory,write_json\nevidence=Path(sys.argv[2]);manifest=source_inventory();write_json(evidence/'source-inventory.json',manifest)\nreports=[]\nfor phase in ('prepare','author','synchronize','render'):\n    result=run(Path(sys.argv[3]),evidence/phase,phase,evidence/'fixture',manifest,transport='Chromium')\n    reports.append({'operation':phase,'passed':result['passed'],'checks':len(result['checks']),'elapsed_seconds':result['elapsed_seconds'],'error':result.get('error')})\n    print(json.dumps(reports[-1]),flush=True)\n    write_json(evidence/'phase-summary.json',{'passed':all(r['passed'] for r in reports),'native_certified':False,'phases':reports})\n    if not result['passed']:raise SystemExit(1)\n";
  const begun = Date.now();
  const run = spawnSync(options['--python'], ['-I', '-B', '-c', code, __dirname, evidence, adapter], {
    env: {...process.env, CINEMATICUM_SYNC_PYTHON: process.env.CINEMATICUM_SYNC_PYTHON || options['--python'], PYTHONDONTWRITEBYTECODE: '1'},
    encoding: 'utf8', timeout: 80000, maxBuffer: 8 * 1024 * 1024,
  });
  fs.writeFileSync(path.join(evidence, 'driver.stdout'), run.stdout || ''); fs.writeFileSync(path.join(evidence, 'driver.stderr'), run.stderr || '');
  const summary = fs.existsSync(path.join(evidence, 'phase-summary.json')) ? JSON.parse(fs.readFileSync(path.join(evidence, 'phase-summary.json'))) : {passed: false, phases: []};
  const result = {...summary, passed: run.status === 0 && summary.passed && summary.phases.length === 4, native_certified: false,
    schema: 'cinematicum-actual-multicam-sync-chromium-acceptance-v1', chromium_executable_sha256: browserSha,
    elapsed_ms: Date.now() - begun, python_exit_code: run.status, error: run.error ? String(run.error) : null,
    report: path.join(evidence, 'browser-report.json')};
  fs.writeFileSync(result.report, JSON.stringify(result, null, 2) + '\n');
  process.stdout.write(JSON.stringify(result) + '\n'); if (!result.passed) process.exitCode = 1;
}

if (helper) browserHelper().catch(error => {process.stderr.write(String(error.stack || error) + '\n'); process.exitCode = 1;});
else driver();
