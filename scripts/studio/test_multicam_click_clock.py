"""Exercise the shipped camera-monitor bridge with a stalled animation clock."""
from pathlib import Path
import re
import shutil
import subprocess
import unittest


class MulticamClickClockTests(unittest.TestCase):
    def test_input_event_samples_live_pcm_clock_without_advancing_buffered_or_paused_transport(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "The monitor clock regression requires Node")
        source = (Path(__file__).parent / "web/app.js").read_text()
        bridge = source.split("multicamMonitor??=window.CinematicumMulticam.mount", 1)[1]
        getter = re.search(r"getFrame:(.*?),isPlaying:", bridge, re.S).group(1)
        script = r"""
const vm=require('vm'),assert=require('assert');
let observed={frame:48.75},calls=0;
const sandbox={state:{playing:true,frame:24},playbackAudioFrame:31,
 window:{CinematicumSequencePlayback:{clock(){calls++;return observed;}}}};
vm.createContext(sandbox);
const getFrame=vm.runInContext('('+process.argv[1]+')',sandbox);
// Audio has advanced while requestAnimationFrame has not run for 17 frames.
assert.strictEqual(Math.floor(getFrame()),48);
assert.strictEqual(calls,1);
assert.strictEqual(sandbox.playbackAudioFrame,31,'An input read must not mutate transport');
observed={waiting:true,frame:60};
assert.strictEqual(getFrame(),31,'Buffering freezes the accepted transport position');
observed=null;assert.strictEqual(getFrame(),31);
observed={frame:NaN};assert.strictEqual(getFrame(),31);
observed={frame:Infinity};assert.strictEqual(getFrame(),31);
observed={frame:30};assert.strictEqual(getFrame(),31,'Never move an edit backwards from its accepted clock');
sandbox.state.playing=false;
const before=calls;assert.strictEqual(getFrame(),24);assert.strictEqual(calls,before);
"""
        result = subprocess.run([node, "-e", script, getter], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
