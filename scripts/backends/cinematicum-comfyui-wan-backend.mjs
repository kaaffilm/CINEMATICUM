#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { spawnSync } from "node:child_process";

const die = (msg, code = 1) => {
console.error(msg);
process.exit(code);
};

const env = process.env;
const out = env.CINEMATICUM_OUTPUT_MP4;
if (!out) die("CINEMATICUM_NATIVE_BACKEND_REFUSED=true\nREASON=CINEMATICUM_OUTPUT_MP4_NOT_SET");

const shotId =
env.CINEMATICUM_SHOT_ID ||
env.SHOT_ID ||
path.basename(out, path.extname(out));

const promptJson =
env.CINEMATICUM_PROMPT_JSON ||
env.PROMPT_JSON ||
`production/THE_LAST_RENDER/prompts/${shotId}.json`;

const workflowPath =
env.COMFYUI_WORKFLOW_JSON ||
"production/THE_LAST_RENDER/workflows/comfyui-wan-api.json";

const comfyUrl = (env.COMFYUI_URL || "[http://127.0.0.1:8188").replace(/\/+$/](http://127.0.0.1:8188%22%29.replace%28/\/+$/), "");
const timeoutSeconds = Number(env.COMFYUI_TIMEOUT_SECONDS || "3600");

if (!fs.existsSync(workflowPath)) {
die([
"CINEMATICUM_NATIVE_BACKEND_REFUSED=true",
"REASON=COMFYUI_API_WORKFLOW_MISSING",
`REQUIRED=${workflowPath}`,
"EXPORT_FROM_COMFYUI=Save API Format workflow as production/THE_LAST_RENDER/workflows/comfyui-wan-api.json"
].join("\n"));
}

let promptData = {};
if (fs.existsSync(promptJson)) {
promptData = JSON.parse(fs.readFileSync(promptJson, "utf8"));
}

function collectStrings(obj, pathKey = "") {
const out = [];
if (typeof obj === "string") {
const k = pathKey.toLowerCase();
if (
k.includes("prompt") ||
k.includes("description") ||
k.includes("camera") ||
k.includes("lighting") ||
k.includes("action") ||
k.includes("movement") ||
k.includes("environment") ||
k.includes("visual") ||
k.includes("lens") ||
k.includes("shot")
) out.push(obj);
return out;
}
if (Array.isArray(obj)) {
obj.forEach((v, i) => out.push(...collectStrings(v, `${pathKey}.${i}`)));
return out;
}
if (obj && typeof obj === "object") {
for (const [k, v] of Object.entries(obj)) {
out.push(...collectStrings(v, pathKey ? `${pathKey}.${k}` : k));
}
}
return out;
}

const positive =
promptData.prompt ||
promptData.positive_prompt ||
promptData.video_prompt ||
collectStrings(promptData).join("\n") ||
`Realistic cinematic live-action shot: ${shotId}`;

const negative =
promptData.negative_prompt ||
"cartoon, anime, illustration, slideshow, still frame, CGI toy look, plastic skin, low motion, text overlay, watermark, logo, malformed body, warped hands";

const seed = Number(
env.SEED ||
parseInt(crypto.createHash("sha256").update(shotId).digest("hex").slice(0, 8), 16)
);

const replacements = {
"{{PROMPT}}": JSON.stringify(positive).slice(1, -1),
"{{NEGATIVE_PROMPT}}": JSON.stringify(negative).slice(1, -1),
"{{SEED}}": String(seed),
"{{WIDTH}}": String(env.WIDTH || promptData.width || 1280),
"{{HEIGHT}}": String(env.HEIGHT || promptData.height || 720),
"{{FRAMES}}": String(env.FRAMES || promptData.frames || 121),
"{{FPS}}": String(env.FPS || promptData.fps || 24),
"{{OUTPUT_PREFIX}}": JSON.stringify(`cinematicum_${shotId}`).slice(1, -1)
};

let workflowText = fs.readFileSync(workflowPath, "utf8");
for (const [k, v] of Object.entries(replacements)) {
workflowText = workflowText.split(k).join(v);
}

let workflow;
try {
workflow = JSON.parse(workflowText);
} catch (e) {
die(`CINEMATICUM_NATIVE_BACKEND_REFUSED=true\nREASON=WORKFLOW_JSON_PARSE_FAIL\nFILE=${workflowPath}\nERROR=${e.message}`);
}

async function httpJson(url, options = {}) {
const r = await fetch(url, options);
const t = await r.text();
if (!r.ok) die(`COMFYUI_HTTP_FAIL=true\nURL=${url}\nSTATUS=${r.status}\nBODY=${t}`);
return t ? JSON.parse(t) : {};
}

function findVideoObjects(x, acc = []) {
if (!x || typeof x !== "object") return acc;
if (Array.isArray(x)) {
for (const v of x) findVideoObjects(v, acc);
return acc;
}
if (typeof x.filename === "string") {
const ext = path.extname(x.filename).toLowerCase();
if ([".mp4", ".webm", ".mov", ".mkv"].includes(ext)) acc.push(x);
}
for (const v of Object.values(x)) findVideoObjects(v, acc);
return acc;
}

async function main() {
fs.mkdirSync(path.dirname(out), { recursive: true });

console.log(`CINEMATICUM_NATIVE_BACKEND=true`);
console.log(`SHOT_ID=${shotId}`);
console.log(`PROMPT_JSON=${promptJson}`);
console.log(`WORKFLOW_JSON=${workflowPath}`);
console.log(`COMFYUI_URL=${comfyUrl}`);
console.log(`OUTPUT_MP4=${out}`);

await httpJson(`${comfyUrl}/system_stats`).catch(e => {
die([
"CINEMATICUM_NATIVE_BACKEND_REFUSED=true",
"REASON=LOCAL_COMFYUI_NOT_RUNNING",
`COMFYUI_URL=${comfyUrl}`,
"START_LOCAL_COMFYUI_ON_PORT_8188=true"
].join("\n"));
});

const clientId = `cinematicum-${crypto.randomUUID()}`;
const queued = await httpJson(`${comfyUrl}/prompt`, {
method: "POST",
headers: { "Content-Type": "application/json" },
body: JSON.stringify({ prompt: workflow, client_id: clientId })
});

const promptId = queued.prompt_id;
if (!promptId) die(`COMFYUI_QUEUE_FAIL=true\nRESPONSE=${JSON.stringify(queued)}`);

const deadline = Date.now() + timeoutSeconds * 1000;
let media = null;

while (Date.now() < deadline) {
await new Promise(r => setTimeout(r, 5000));
const hist = await httpJson(`${comfyUrl}/history/${promptId}`).catch(() => ({}));
const job = hist[promptId];
if (!job) continue;
const vids = findVideoObjects(job.outputs || job);
if (vids.length) {
media = vids[0];
break;
}
if (job.status?.status_str === "error") {
die(`COMFYUI_RENDER_FAIL=true\nPROMPT_ID=${promptId}\nSTATUS=${JSON.stringify(job.status)}`);
}
}

if (!media) {
die(`COMFYUI_RENDER_FAIL=true\nREASON=NO_VIDEO_OUTPUT_FOUND\nPROMPT_ID=${promptId}`);
}

const view = new URL(`${comfyUrl}/view`);
view.searchParams.set("filename", media.filename);
view.searchParams.set("subfolder", media.subfolder || "");
view.searchParams.set("type", media.type || "output");

const rr = await fetch(view);
if (!rr.ok) die(`COMFYUI_DOWNLOAD_FAIL=true\nSTATUS=${rr.status}\nFILE=${media.filename}`);

const tmp = `${out}.download${path.extname(media.filename) || ".bin"}`;
fs.writeFileSync(tmp, Buffer.from(await rr.arrayBuffer()));

const ext = path.extname(tmp).toLowerCase();
if (ext === ".mp4") {
fs.copyFileSync(tmp, out);
} else {
const ff = spawnSync("ffmpeg", [
"-y", "-i", tmp,
"-c:v", "libx264", "-pix_fmt", "yuv420p",
"-c:a", "aac", "-movflags", "+faststart",
out
], { stdio: "inherit" });
if (ff.status !== 0) die(`FFMPEG_TRANSCODE_FAIL=true\nINPUT=${tmp}\nOUTPUT=${out}`);
}

const size = fs.statSync(out).size;
if (size < 1000000) {
die(`BACKEND_OUTPUT_CONTRACT_FAIL=true\nREASON=output_mp4_too_small\nOUTPUT_MP4=${out}\nSIZE_BYTES=${size}`);
}

console.log(`BACKEND_OUTPUT_MP4=${out}`);
console.log(`BACKEND_OUTPUT_BYTES=${size}`);
console.log("CINEMATICUM_NATIVE_BACKEND_SHOT_PASS=true");
}

main().catch(e => die(`CINEMATICUM_NATIVE_BACKEND_FAIL=true\nERROR=${e.stack || e.message}`));
