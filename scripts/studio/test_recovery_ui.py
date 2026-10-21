"""Run the shipped checkpoint scheduler through asynchronous edit/save races."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which("node"), "Node is required")
class RecoverySchedulerTests(unittest.TestCase):
    def test_edits_saves_project_switches_and_failed_checkpoint_keep_ownership(self):
        script = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert'),crypto=require('crypto');
const events={},timers=new Map(),status={},button={addEventListener:(k,v)=>events[k]=v};let next=0;
const dialog={open:false,innerHTML:'',querySelector:()=>({innerHTML:''}),addEventListener(){},close(){this.open=false},showModal(){this.open=true}};
const sandbox={window:{},document:{createElement:()=>dialog,body:{append(){}},addEventListener(){}},crypto,
  setTimeout:(fn,delay)=>{timers.set(++next,{fn,delay});return next},clearTimeout:id=>timers.delete(id)};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync(JSON.parse(fs.readFileSync(0,'utf8')).path,'utf8'),sandbox);
let ctx={project:{id:'one',revision:1,name:'first',assets:[],clips:[],titles:[]},dirty:true,revision:1,saving:false,blocked:false};
const calls=[],notices=[],deferred=[];let wait=true,fail=false;
async function request(path,opts){if(!opts)return {drafts:[],versions:[],unreadable:0};calls.push({path,body:JSON.parse(JSON.stringify(opts.body))});if(fail)throw Error('ENGINE TEST offline');if(wait)return await new Promise(resolve=>deferred.push(resolve));return {checkpointed:true};}
const control=sandbox.window.CinematicumRecovery.mount({getContext:()=>ctx,request,onRecover(){},notify:(...args)=>notices.push(args),button,status});
(async()=>{
 control.reset();await Promise.resolve();control.schedule();assert(timers.size===1);
 const first=control.flush();await Promise.resolve();assert.equal(calls.length,1);assert.equal(calls[0].body.project.name,'first');
 ctx.project.name='second';ctx.revision++;control.schedule();const again=control.flush();await Promise.resolve();assert.equal(calls.length,1);
 deferred.shift()({checkpointed:true});await first;await again;
 wait=false;await control.flush();assert.equal(calls.length,2);assert.equal(calls[1].body.project.name,'second');assert.equal(calls[0].body.project.name,'first');
 assert.equal(calls[1].body.sequence,2);assert.equal(status.textContent,'Recovery checkpointed');
 ctx.saving=true;ctx.revision++;await control.flush();assert.equal(calls.length,2,'Do not race committed revision updates');
 ctx.saving=false;ctx.project.revision=2;control.saved();await control.flush();assert.equal(calls.at(-1).body.project.revision,2);
 // A prior project's request may finish after a new project was adopted.
 wait=true;ctx.revision++;const previous=control.flush();await Promise.resolve();const previousEditor=calls.at(-1).body.editor_id;
 ctx={project:{id:'two',revision:1,name:'other',assets:[],clips:[],titles:[]},dirty:true,revision:1,saving:false,blocked:false};
 control.reset();control.schedule();const current=control.flush();await Promise.resolve();assert.equal(calls.at(-1).path,'/api/projects/two/checkpoint');assert.notEqual(calls.at(-1).body.editor_id,previousEditor);
 deferred.shift()({checkpointed:true});await previous;assert.notEqual(status.textContent,'Recovery checkpointed');
 deferred.shift()({checkpointed:true});await current;assert.equal(status.textContent,'Recovery checkpointed');
 wait=false;fail=true;ctx.revision++;await control.flush();assert.equal(status.textContent,'Recovery unavailable');assert.equal(notices.length,1);
 fail=false;ctx.revision++;await control.flush();assert.equal(status.textContent,'Recovery checkpointed');
 assert.equal(control.receipt().sequence,calls.at(-1).body.sequence);
 console.log(JSON.stringify({passed:true,checkpoint_requests:calls.length,stale_project_write_isolated:true}));
})().catch(e=>{console.error(e);process.exit(1)});
"""
        result = subprocess.run([shutil.which("node"), "-e", script], input=json.dumps({
            "path": str(Path(__file__).parent / "web/recovery-ui.js")}), text=True,
            capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["passed"])


if __name__ == "__main__":
    unittest.main()
