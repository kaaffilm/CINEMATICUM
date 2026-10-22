#!/usr/bin/env node
/* Actual shipped still-photo controls, shared with bounded native phases.
 * This driver does not certify macOS WKWebView or the canonical installed app.
 */
'use strict';
const fs=require('fs'),path=require('path'),crypto=require('crypto'),{spawnSync}=require('child_process');
const values=process.argv.slice(2),options={};
if(values.length%2)throw Error('Use paired --option value arguments');
for(let i=0;i<values.length;i+=2){if(options[values[i]])throw Error('Duplicate option');options[values[i]]=values[i+1];}
for(const key of ['--python','--browser','--evidence'])if(!options[key]||!path.isAbsolute(options[key]))throw Error(key+' needs an absolute path');
if(Object.keys(options).some(key=>!['--python','--browser','--evidence'].includes(key)))throw Error('Unknown browser driver option');
const evidence=options['--evidence'];fs.mkdirSync(evidence);
const hash=data=>crypto.createHash('sha256').update(data).digest('hex');
const browserSHA=hash(fs.readFileSync(options['--browser']));
const adapter=path.join(evidence,'photograph-browser-adapter.cjs');
fs.writeFileSync(adapter,'#!'+process.execPath+'\n'+
  "process.argv.splice(2,0,'--helper','--browser',"+JSON.stringify(options['--browser'])+');\n'+
  'require('+JSON.stringify(path.join(__dirname,'test_multicam_sync_browser.cjs'))+');\n',{mode:0o700});
const code="import json,sys\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nfrom test_still_photography_ui import run,source_inventory,write_json,PHASES\nevidence=Path(sys.argv[2]);sources=source_inventory();write_json(evidence/'source-inventory.json',sources)\nreports=[]\nfor phase in PHASES:\n    result=run(Path(sys.argv[3]),evidence/phase,phase,evidence/'fixture',sources,transport='Chromium')\n    reports.append({'operation':phase,'passed':result['passed'],'checks':len(result['checks']),'elapsed_seconds':result['elapsed_seconds'],'error':result.get('error')})\n    print(json.dumps(reports[-1]),flush=True)\n    write_json(evidence/'phase-summary.json',{'passed':all(row['passed'] for row in reports),'native_certified':False,'phases':reports})\n    if not result['passed']:raise SystemExit(1)\n";
const began=Date.now();
const run=spawnSync(options['--python'],['-I','-B','-c',code,__dirname,evidence,adapter],{
  env:{...process.env,CINEMATICUM_IMAGING_PYTHON:process.env.CINEMATICUM_IMAGING_PYTHON||options['--python'],CINEMATICUM_TRACKING_PYTHON:process.env.CINEMATICUM_TRACKING_PYTHON||options['--python'],PYTHONDONTWRITEBYTECODE:'1'},
  encoding:'utf8',timeout:100000,maxBuffer:8*1024*1024});
fs.writeFileSync(path.join(evidence,'driver.stdout'),run.stdout||'');fs.writeFileSync(path.join(evidence,'driver.stderr'),run.stderr||'');
const summary=fs.existsSync(path.join(evidence,'phase-summary.json'))?JSON.parse(fs.readFileSync(path.join(evidence,'phase-summary.json'))):{passed:false,phases:[]};
const result={...summary,passed:run.status===0&&summary.passed&&summary.phases.length===5,schema:'cinematicum-actual-still-photography-browser-acceptance-v1',
  chromium_executable_sha256:browserSHA,elapsed_ms:Date.now()-began,python_exit_code:run.status,error:run.error?String(run.error):null,report:path.join(evidence,'browser-report.json')};
fs.writeFileSync(result.report,JSON.stringify(result,null,2)+'\n');process.stdout.write(JSON.stringify(result)+'\n');if(!result.passed)process.exitCode=1;
