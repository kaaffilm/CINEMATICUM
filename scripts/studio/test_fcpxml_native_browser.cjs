#!/usr/bin/env node
/* Exercise the exact native FCPXML phase coordinator with caller-owned
 * Chromium. The report explicitly excludes native macOS and ProRes decoder
 * certification. No runtime or fixture is downloaded by this adapter.
 */
'use strict';
const fs=require('fs'),path=require('path'),crypto=require('crypto'),{spawnSync}=require('child_process');
const values=process.argv.slice(2),options={};
if(values.length%2)throw Error('Use paired --option value arguments');
for(let i=0;i<values.length;i+=2){if(options[values[i]])throw Error('Duplicate option');options[values[i]]=values[i+1];}
for(const key of ['--python','--browser','--evidence'])if(!options[key]||!path.isAbsolute(options[key]))throw Error(key+' requires an absolute path');
if(Object.keys(options).some(key=>!['--python','--browser','--evidence'].includes(key)))throw Error('Unknown argument');
const evidence=options['--evidence'];fs.mkdirSync(evidence);
const hash=value=>crypto.createHash('sha256').update(value).digest('hex');
const browserHash=hash(fs.readFileSync(options['--browser']));
const adapter=path.join(evidence,'chromium-adapter.cjs');
fs.writeFileSync(adapter,'#!'+process.execPath+'\n'+
  'process.argv.splice(2,0,"--helper","--browser",'+JSON.stringify(options['--browser'])+');\n'+
  'require('+JSON.stringify(path.join(__dirname,'test_retime_browser.cjs'))+');\n',{mode:0o700});
const code=`import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from test_fcpxml_macos import run,source_inventory,write_json
root=Path(sys.argv[2]);sources=source_inventory();write_json(root/'source-inventory.json',sources)
reports=[]
for phase in ('prepare','author','render'):
    result=run(Path(sys.argv[3]),root/phase,phase,root/'fixture',sources,transport='Chromium')
    summary={'operation':phase,'passed':result['passed'],'checks':len(result['checks']),'elapsed_seconds':result['elapsed_seconds'],'error':result.get('error'),'native_certified':result['native_certified']}
    reports.append(summary);print(json.dumps(summary),flush=True)
    write_json(root/'phase-summary.json',{'passed':all(row['passed'] for row in reports),'native_certified':False,'phases':reports})
    if not result['passed']:raise SystemExit(1)
`;
const began=Date.now(),run=spawnSync(options['--python'],['-I','-B','-c',code,__dirname,evidence,adapter],
  {env:{...process.env,PYTHONDONTWRITEBYTECODE:'1',CINEMATICUM_TRACKING_PYTHON:process.env.CINEMATICUM_TRACKING_PYTHON||options['--python']},encoding:'utf8',timeout:58000,maxBuffer:4*1024*1024});
fs.writeFileSync(path.join(evidence,'driver.stdout'),run.stdout||'');fs.writeFileSync(path.join(evidence,'driver.stderr'),run.stderr||'');
const summary=fs.existsSync(path.join(evidence,'phase-summary.json'))?JSON.parse(fs.readFileSync(path.join(evidence,'phase-summary.json'))):{passed:false,phases:[]};
const afterHash=hash(fs.readFileSync(options['--browser']));
const result={schema:'cinematicum-phased-fcpxml-browser-check-v1',...summary,
  passed:run.status===0&&summary.passed&&summary.phases.length===3&&afterHash===browserHash,native_certified:false,
  native_prores_playback_certified:false,browser_sha256:browserHash,browser_sha256_after:afterHash,
  elapsed_ms:Date.now()-began,python_exit_code:run.status,error:run.error?String(run.error):null};
fs.writeFileSync(path.join(evidence,'browser-report.json'),JSON.stringify(result,null,2)+'\n');
process.stdout.write(JSON.stringify(result)+'\n');if(!result.passed)process.exitCode=1;
