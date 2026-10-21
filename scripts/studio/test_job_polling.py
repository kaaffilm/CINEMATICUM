"""The shipped job poller must not overwrite another owner or strand recovery."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which("node"), "Node required to evaluate the shipped job poller")
class JobPollingTests(unittest.TestCase):
    def test_replacement_race_recovery_and_missing_job(self):
        script = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const path=JSON.parse(fs.readFileSync(0,'utf8')).path,source=fs.readFileSync(path,'utf8');
const controls=new Map(),state={project:{id:'project',name:'ENGINE TEST'}};
const $=key=>{if(!controls.has(key))controls.set(key,{dataset:{}});return controls.get(key);};
let pending=[],finished=[];
const context={state,$,finite:(v,d=0)=>Number.isFinite(Number(v))?Number(v):d,toast:()=>{},
setTimeout:fn=>fn(),api:()=>new Promise((resolve,reject)=>pending.push({resolve,reject})),
finishJob:async job=>finished.push(job.id)};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('async function trackJob('),source.indexOf('\nasync function finishJob(')),context);
(async()=>{
 $('#open-restored-project').dataset.projectId='previous-restored-project';
 const first=context.trackJob({id:'old',state:'running'},'old','render');
 assert.strictEqual($('#open-restored-project').hidden,true);assert.strictEqual($('#open-restored-project').dataset.projectId,undefined);
 const second=context.trackJob({id:'new',state:'running'},'new','render');
 pending.shift().resolve({id:'old',state:'completed',result:{wrong:true}});
 assert.strictEqual(await first,null);assert.strictEqual(state.job.id,'new');assert.deepStrictEqual(finished,[]);
 pending.shift().resolve({id:'new',state:'completed',result:{correct:true}});
 assert.strictEqual((await second).result.correct,true);assert.deepStrictEqual(finished,['new']);
 context.api=async()=>{throw Error('temporary loopback interruption');};
 const interrupted=await context.trackJob({id:'recoverable',state:'running'},'recoverable','scene-modeling');
 assert.strictEqual(interrupted.pollingPaused,true);assert.strictEqual(interrupted.state,'running');
 assert.strictEqual($('#retry-job').hidden,false);assert.strictEqual($('#cancel-job').hidden,false);
 context.api=async()=>({id:'recoverable',state:'completed',result:{object:{id:'mesh'}}});
 const recovered=await context.trackJob(interrupted,interrupted.label,interrupted.kind);
 assert.strictEqual(recovered.state,'completed');assert.strictEqual($('#retry-job').hidden,true);
 context.api=async()=>{throw Object.assign(Error('Job does not exist'),{status:404});};
 const missing=await context.trackJob({id:'missing',state:'running'},'missing','render');
 assert.strictEqual(missing.state,'interrupted');assert.strictEqual($('#cancel-job').hidden,true);
 state.job={id:'paused-cancel',state:'running',pollingPaused:true,label:'Paused',kind:'render',projectId:'project'};
 const calls=[];context.api=async(path,options)=>{calls.push([path,options?.method]);return {id:'paused-cancel',state:'cancelled'};};
 await context.cancelOwnedJob();
 assert.strictEqual(calls.length,2);assert.strictEqual(calls[0][1],'POST');
 assert.strictEqual(state.job.state,'cancelled');assert.strictEqual(state.job.pollingPaused,false);
 assert.strictEqual($('#cancel-job').hidden,true);assert.strictEqual($('#cancel-job').disabled,false);
 state.job={id:'old-cancel',state:'running'};context.api=()=>new Promise(resolve=>pending.push({resolve}));
 const staleCancel=context.cancelOwnedJob();
 assert.strictEqual($('#cancel-job').disabled,true);
 const replacement=context.trackJob({id:'replacement',state:'running'},'Replacement','render');
 assert.strictEqual($('#cancel-job').disabled,false);
 pending.shift().resolve({id:'old-cancel',state:'cancelled'});await staleCancel;
 assert.strictEqual(state.job.id,'replacement');assert.strictEqual($('#job-detail').textContent,'Queued');
 assert.strictEqual($('#cancel-job').disabled,false);
 pending.shift().resolve({id:'replacement',state:'completed'});await replacement;
 process.stdout.write('passed');
})().catch(error=>{process.stderr.write(error.stack);process.exitCode=1;});
"""
        result = subprocess.run([shutil.which("node"), "-e", script],
                                input=json.dumps({"path": str(Path(__file__).parent / "web/app.js")}),
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "passed")


if __name__ == "__main__":
    unittest.main()
