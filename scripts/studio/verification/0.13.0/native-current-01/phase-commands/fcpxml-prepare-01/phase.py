
import os,sys,json,pathlib,hashlib,subprocess
source=pathlib.Path("/Users/midiakiasat/.midia-ai/gateway-live/workspaces/auto-ffd5bd15ebd1cc0813d35a31f6e27ced-next-013");base=pathlib.Path("/Users/midiakiasat/.midia-ai/gateway-live/acceptance/cinematicum-0.13-20261022-own-e980f36e")
EXPECTED_COMMIT="cdd15816c228fe4133fbb3ce6d90978333d699e6"
EXPECTED_TREE="a62ce29a8af68b38d14820c45fc42e1266762e34"
EXPECTED_MANIFEST="21034979d805cdf680c255720f6311319f3fc22c2b405dbd43294a5485d09f8d"
operation="prepare"
assert subprocess.check_output(["/usr/bin/git","-C",str(source),"rev-parse","HEAD"],text=True,timeout=2).strip()==EXPECTED_COMMIT
assert subprocess.check_output(["/usr/bin/git","-C",str(source),"write-tree"],text=True,timeout=2).strip()==EXPECTED_TREE
assert subprocess.run(["/usr/bin/git","-C",str(source),"diff","--quiet","HEAD","--"],timeout=2).returncode==0
assert hashlib.sha256((source/"scripts/studio/source-integrity.json").read_bytes()).hexdigest()==EXPECTED_MANIFEST
binary=pathlib.Path("/Users/midiakiasat/.midia-ai/gateway-live/acceptance/cinematicum-0.12-20261022-own-061702ff/native-smoke-build-02/cinematicum-native-smoke");assert hashlib.sha256(binary.read_bytes()).hexdigest()=="c6b70d236c056a6ed3eaa08ef44aaa1672ecce904f8004095b69ac2a60f3bee7"
assert hashlib.sha256((source/"scripts/studio/macos/SmokeTest.swift").read_bytes()).hexdigest()=="f6b3ee4295bcefe003c2220a7ed42a3dc4208a95ce6842936b8a901048aef6cd"
os.environ["PATH"]="/opt/homebrew/bin:"+os.environ.get("PATH","");os.environ["CINEMATICUM_TRACKING_PYTHON"]=sys.executable;os.environ["PYTHONDONTWRITEBYTECODE"]="1"
sys.path.insert(0,str(source/"scripts/studio"))
from test_fcpxml_macos import run,source_inventory,read_json,write_json
root=base/"fcpxml-native-01"
if operation=="prepare":
 assert not root.exists();root.mkdir();expected=source_inventory();write_json(root/"source-inventory.json",expected)
else: expected=read_json(root/"source-inventory.json")
r=run(binary,root/operation,operation,root/"fixture",expected)
summary={k:r.get(k) for k in ["passed","operation","elapsed_seconds","error","native_certified"]};summary["checks"]=r["checks"]
print(json.dumps({"native":summary,"source_commit":EXPECTED_COMMIT,"source_tree":EXPECTED_TREE,"source_manifest_sha256":EXPECTED_MANIFEST}))
raise SystemExit(0 if r["passed"] else 1)
