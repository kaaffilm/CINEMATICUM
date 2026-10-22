#!node
process.argv.splice(2,0,"--helper","--browser","/workspace/scratch/091f394ee5df/cinematicum-runtimes/chrome-for-testing-134.0.6998.35/chrome-linux64/chrome");
require("/workspace/scratch/091f394ee5df/cinematicum-fcpxml-acceptance/scripts/studio/test_retime_browser.cjs");
