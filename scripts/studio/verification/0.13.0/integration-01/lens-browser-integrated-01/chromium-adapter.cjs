#!/opt/codex/runtimes/codex-primary-runtime/dependencies/node/bin/node
process.argv.splice(2,0,"--helper","--browser","/tmp/cinematicum-next-verification-20261022-01/browser-runtime/chrome-linux64/chrome");
require("/workspace/scratch/091f394ee5df/cinematicum-013-candidate/scripts/studio/test_retime_browser.cjs");
