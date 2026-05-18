#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

const root = process.cwd();
const comfy = process.env.COMFYUI_URL || "http://127.0.0.1:8188";
const shotId = process.env.CINEMATICUM_SHOT_ID || process.env.SHOT_ID || "unknown";
const promptJson = process.env.CINEMATICUM_PROMPT_JSON;
const workflowJson = process.env.CINEMATICUM_WORKFLOW_JSON || "production/THE_LAST_RENDER/workflows/comfyui-api.json";
const out = process.env.CINEMATICUM_OUTPUT_MP4;

function logTail() {
  const log = path.join(root, ".runtime", "comfyui-8188.log");
  if (fs.existsSync(log)) {
    console.log("=== COMFYUI_LOG_TAIL ===");
    console.log(fs.readFileSync(log, "utf8").split(/\r?\n/).slice(-180).join("\n"));
  }
}

function die(key) {
  console.log(`${key}=true`);
  logTail();
  process.exit(1);
}

if (!promptJson) die("PROMPT_JSON_NOT_SET");
if (!out) die("OUTPUT_MP4_NOT_SET");

console.log("CINEMATICUM_NATIVE_BACKEND=true");
console.log(`SHOT_ID=${shotId}`);
console.log(`PROMPT_JSON=${promptJson}`);
console.log(`WORKFLOW_JSON=${workflowJson}`);
console.log(`OUTPUT_MP4=${out}`);

const shot = JSON.parse(fs.readFileSync(promptJson, "utf8"));
const raw = JSON.parse(fs.readFileSync(workflowJson, "utf8"));
let prompt = raw.prompt && typeof raw.prompt === "object" ? raw.prompt : raw;

if (prompt.nodes && Array.isArray(prompt.nodes)) {
  console.log("COMFYUI_WORKFLOW_NOT_API_EXPORT=true");
  console.log("FIX=ComfyUI File > Export API");
  process.exit(1);
}

const positive = [
  shot.prompt,
  shot.positive,
  shot.description,
  shot.scene,
  shot.camera,
  shot.lighting,
  shot.motion
].filter(Boolean).join("\n");

const negative = [
  shot.negative,
  "toy, cartoon, slideshow, still image, title card, watermark, text, logo, low motion, static frame"
].filter(Boolean).join(", ");

for (const node of Object.values(prompt)) {
  if (!node || typeof node !== "object" || !node.inputs) continue;
  for (const [k, v] of Object.entries(node.inputs)) {
    if (typeof v !== "string") continue;
    const key = k.toLowerCase();
    if (v.includes("CINEMATICUM_POSITIVE_PROMPT") || key.includes("positive") || key === "text") node.inputs[k] = positive;
    if (v.includes("CINEMATICUM_NEGATIVE_PROMPT") || key.includes("negative")) node.inputs[k] = negative;
    if (v.includes("CINEMATICUM_SHOT_ID")) node.inputs[k] = shotId;
  }
}

async function httpJson(url, options = {}) {
  const r = await fetch(url, options);
  const text = await r.text();
  if (!r.ok) {
    console.log("COMFYUI_HTTP_FAIL=true");
    console.log(`URL=${url}`);
    console.log(`STATUS=${r.status}`);
    console.log("BODY=" + text.slice(0, 4000));
    logTail();
    process.exit(1);
  }
  return text ? JSON.parse(text) : {};
}

await httpJson(`${comfy}/system_stats`);

const client_id = "cinematicum-" + crypto.randomUUID();

const queued = await httpJson(`${comfy}/prompt`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ prompt, client_id })
});

const promptId = queued.prompt_id;
if (!promptId) {
  console.log("COMFYUI_NO_PROMPT_ID=true");
  console.log(JSON.stringify(queued, null, 2));
  process.exit(1);
}

console.log(`COMFYUI_PROMPT_ID=${promptId}`);

let history = null;
for (let i = 0; i < 720; i++) {
  await new Promise(r => setTimeout(r, 5000));
  const h = await httpJson(`${comfy}/history/${promptId}`);
  if (h[promptId]) {
    history = h[promptId];
    break;
  }
  process.stdout.write(".");
}
console.log("");

if (!history) die("COMFYUI_TIMEOUT");

if (history.status?.status_str !== "success" && history.status?.completed !== true) {
  console.log("COMFYUI_EXECUTION_FAIL=true");
  console.log(JSON.stringify(history.status || history, null, 2).slice(0, 4000));
  logTail();
  process.exit(1);
}

const mediaFiles = [];
for (const output of Object.values(history.outputs || {})) {
  for (const item of [...(output.videos || []), ...(output.gifs || []), ...(output.images || [])]) {
    if (item?.filename) mediaFiles.push(item);
  }
}

if (!mediaFiles.length) {
  console.log("COMFYUI_NO_MEDIA_OUTPUT=true");
  console.log(JSON.stringify(history.outputs || {}, null, 2).slice(0, 4000));
  process.exit(1);
}

const media = mediaFiles.find(f => /\.mp4$/i.test(f.filename)) || mediaFiles[0];

const params = new URLSearchParams({
  filename: media.filename,
  subfolder: media.subfolder || "",
  type: media.type || "output"
});

const mediaResp = await fetch(`${comfy}/view?${params}`);
if (!mediaResp.ok) {
  console.log("COMFYUI_MEDIA_DOWNLOAD_FAIL=true");
  console.log(`STATUS=${mediaResp.status}`);
  process.exit(1);
}

const buf = Buffer.from(await mediaResp.arrayBuffer());
fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(out, buf);

console.log(`BACKEND_OUTPUT_MP4=${out}`);
console.log(`BACKEND_OUTPUT_BYTES=${buf.length}`);
console.log("REAL_BACKEND_SHOT_PASS=true");
