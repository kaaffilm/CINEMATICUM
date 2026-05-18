#!/usr/bin/env node
import fs from "node:fs";

const wf = "production/THE_LAST_RENDER/workflows/comfyui-api.json";

function fail(reason, extra = "") {
  console.log("NATIVE_WORKFLOW_NOT_READY=true");
  console.log(`REASON=${reason}`);
  if (extra) console.log(extra);
  process.exit(1);
}

let raw;
try {
  raw = JSON.parse(fs.readFileSync(wf, "utf8"));
} catch {
  fail("WORKFLOW_JSON_MISSING_OR_BAD", `REQUIRED=${wf}`);
}

const prompt = raw.prompt && typeof raw.prompt === "object" ? raw.prompt : raw;

if (prompt.nodes && Array.isArray(prompt.nodes)) {
  fail("WORKFLOW_IS_UI_GRAPH_NOT_API_EXPORT", "FIX=ComfyUI File > Export API, then save with scripts/local/save-comfyui-current-api-workflow.mjs");
}

for (const [id, node] of Object.entries(prompt)) {
  if (!node || typeof node !== "object" || !node.class_type || !node.inputs) {
    fail("WORKFLOW_NOT_API_FORMAT", `BAD_NODE=${id}`);
  }
}

const stats = await fetch("http://127.0.0.1:8188/system_stats").catch(() => null);
if (!stats || !stats.ok) fail("LOCAL_COMFYUI_NOT_RUNNING", "START=scripts/local/start-comfyui-daemon.sh");

console.log("NATIVE_WORKFLOW_READY=true");
console.log(`WORKFLOW_JSON=${wf}`);
console.log(`NODE_COUNT=${Object.keys(prompt).length}`);
