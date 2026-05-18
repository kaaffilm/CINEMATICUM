#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const out = process.argv[2] || "production/THE_LAST_RENDER/workflows/comfyui-api.json";
const src = process.argv[3] || "";

function fail(reason, extra = "") {
  console.log("COMFYUI_API_WORKFLOW_SAVE_FAIL=true");
  console.log(`REASON=${reason}`);
  if (extra) console.log(extra);
  process.exit(1);
}

if (!src) {
  fail("NO_INPUT_FILE", "USAGE=node scripts/local/save-comfyui-current-api-workflow.mjs production/THE_LAST_RENDER/workflows/comfyui-api.json /path/to/exported-api.json");
}

let raw;
try {
  raw = JSON.parse(fs.readFileSync(src, "utf8"));
} catch {
  fail("INPUT_NOT_VALID_JSON", `INPUT=${src}`);
}

const prompt = raw.prompt && typeof raw.prompt === "object" ? raw.prompt : raw;

if (prompt.nodes && Array.isArray(prompt.nodes)) {
  fail("INPUT_IS_UI_WORKFLOW_NOT_API_EXPORT", "IN_COMFYUI_USE=File > Export API");
}

const bad = [];
for (const [id, node] of Object.entries(prompt)) {
  if (!node || typeof node !== "object" || !node.class_type || !node.inputs) bad.push(id);
}

if (bad.length) {
  fail("INPUT_NOT_COMFYUI_API_FORMAT", `BAD_KEYS=${bad.slice(0, 30).join(",")}`);
}

fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(out, JSON.stringify(prompt, null, 2) + "\n");
console.log("COMFYUI_API_WORKFLOW_SAVED=true");
console.log(`WORKFLOW_JSON=${out}`);
console.log(`NODE_COUNT=${Object.keys(prompt).length}`);
