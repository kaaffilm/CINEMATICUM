"""Keep decoder identity strict after audio scheduling, allowing silent bootstrap."""
from pathlib import Path
import subprocess
import unittest


class AudioObserverIdentityTests(unittest.TestCase):
    def test_only_paused_unscheduled_decoder_can_be_replaced(self):
        source = Path(__file__).with_name('macos').joinpath('AudioRoutingSmoke.js')
        script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(process.argv[1],'utf8');
const start=source.indexOf('    if(voice&&voice.media!==media){');
const end=source.indexOf('    voice.route=result;',start);
assert(start>=0&&end>start);
const code=source.slice(start,end),processor={},media={},spec={},result={};
function check(paused,chunks,connected){
 const disconnected=[];
 const old={el:{paused,pcmState:{scheduled_chunks:chunks}},source:{disconnect:p=>{assert.strictEqual(p,processor);disconnected.push('source');}},audioGate:{disconnect:p=>{assert.strictEqual(p,processor);disconnected.push('gate');}}};
 const original={media:old,connected},voices=new Map([['primary',original]]);
 const sandbox={voice:original,media,spec,result,voices,clip:{id:'primary'},processor,Error};
 if(paused&&chunks===0){
  vm.runInNewContext(code,sandbox);assert.strictEqual(voices.get('primary').media,media);
  assert.deepStrictEqual(disconnected,connected?['source','gate']:[]);
 }else{
  assert.throws(()=>vm.runInNewContext(code,sandbox),/changed decoder during playback/);
  assert.strictEqual(voices.get('primary'),original);assert.deepStrictEqual(disconnected,[]);
 }
}
for(const connected of [false,true])for(const paused of [false,true])for(const chunks of [0,1,20,undefined])check(paused,chunks,connected);
'''
        result = subprocess.run(['node', '-e', script, str(source)], text=True,
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
