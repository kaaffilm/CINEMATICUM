#!/usr/bin/env node
import fs from "node:fs";

const workflow = "production/THE_LAST_RENDER/workflows/comfyui-api.json";

function die(msg) {
  console.error(msg);
  process.exit(1);
}

if (!fs.existsSync(workflow)) {
  die(`NATIVE_WORKFLOW_NOT_READY=true\nREASON=WORKFLOW_MISSING\nREQUIRED=${workflow}`);
}

const j = JSON.parse(fs.readFileSync(workflow, "utf8"));
const api = j && typeof j === "object" && !Array.isArray(j) &&
  Object.values(j).length > 0 &&
  Object.values(j).every(v => v && typeof v === "object" && "class_type" in v && "inputs" in v);

if (!api) {
  die("NATIVE_WORKFLOW_NOT_READY=true\nREASON=WORKFLOW_NEEDS_AUTO_CONVERSION\nRUN=make convert-native-workflow");
}

console.log("NATIVE_WORKFLOW_READY=true");
console.log(`WORKFLOW_JSON=${workflow}`);
console.log(`API_NODE_COUNT=${Object.keys(j).length}`);
