#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const wfPath = process.env.WORKFLOW_JSON || "production/THE_LAST_RENDER/workflows/comfyui-api.json";
const logPath = path.join(root, ".runtime", "comfyui-8188.log");

function tailLog() {
  if (fs.existsSync(logPath)) {
    console.log("=== COMFYUI_LOG_TAIL ===");
    console.log(fs.readFileSync(logPath, "utf8").split(/\r?\n/).slice(-160).join("\n"));
  }
}

function fail(reason, extra = "") {
  console.log("COMFYUI_API_DOCTOR_FAIL=true");
  console.log(`REASON=${reason}`);
  if (extra) console.log(extra);
  tailLog();
  process.exit(1);
}

const stats = await fetch("http://127.0.0.1:8188/system_stats").catch(() => null);
if (!stats || !stats.ok) fail("COMFYUI_NOT_RUNNING");

let raw;
try {
  raw = JSON.parse(fs.readFileSync(wfPath, "utf8"));
} catch {
  fail("WORKFLOW_JSON_NOT_READABLE", `WORKFLOW_JSON=${wfPath}`);
}

const prompt = raw.prompt && typeof raw.prompt === "object" ? raw.prompt : raw;

if (prompt.nodes && Array.isArray(prompt.nodes)) {
  fail("WORKFLOW_IS_UI_GRAPH_NOT_API_EXPORT", "FIX=ComfyUI File > Export API");
}

const entries = Object.entries(prompt);
if (!entries.length) fail("WORKFLOW_EMPTY");

const bad = [];
for (const [id, node] of entries) {
  if (!node || typeof node !== "object" || !node.class_type || !node.inputs) bad.push(id);
}
if (bad.length) fail("WORKFLOW_NOT_API_FORMAT", `BAD_NODE_IDS=${bad.slice(0, 40).join(",")}`);

const oiResp = await fetch("http://127.0.0.1:8188/object_info");
if (!oiResp.ok) fail(`OBJECT_INFO_HTTP_${oiResp.status}`);

const objectInfo = await oiResp.json();
const missing = [...new Set(entries.map(([, n]) => n.class_type).filter(c => !objectInfo[c]))].sort();

if (missing.length) {
  fail("MISSING_COMFYUI_NODE_CLASSES", `MISSING_CLASSES=${missing.join(",")}`);
}

console.log("COMFYUI_API_DOCTOR_PASS=true");
console.log(`WORKFLOW_NODE_COUNT=${entries.length}`);
