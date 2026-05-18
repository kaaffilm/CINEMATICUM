#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fal } from "@fal-ai/client";

function die(msg) {
  console.error(msg);
  process.exit(1);
}

const out = process.env.CINEMATICUM_OUTPUT_MP4;
const promptJson = process.env.CINEMATICUM_PROMPT_JSON;
const shotId = process.env.CINEMATICUM_SHOT_ID || process.env.SHOT_ID || "unknown_shot";

if (!process.env.FAL_KEY) die("FAL_KEY_NOT_SET=true");
if (!out) die("CINEMATICUM_OUTPUT_MP4_NOT_SET=true");
if (!promptJson || !fs.existsSync(promptJson)) die(`PROMPT_JSON_NOT_FOUND=${promptJson}`);

const data = JSON.parse(fs.readFileSync(promptJson, "utf8"));

const prompt =
  data.prompt ||
  data.video_prompt ||
  data.cinematic_prompt ||
  data.text ||
  data.description ||
  JSON.stringify(data, null, 2);

const rawDuration =
  data.duration ||
  data.duration_seconds ||
  data.seconds ||
  5;

const duration = String(Math.max(4, Math.min(15, Math.round(Number(rawDuration) || 5))));

console.log(`REAL_BACKEND=fal-seedance`);
console.log(`SHOT_ID=${shotId}`);
console.log(`PROMPT_JSON=${promptJson}`);
console.log(`OUTPUT_MP4=${out}`);
console.log(`DURATION=${duration}`);

const result = await fal.subscribe("bytedance/seedance-2.0/text-to-video", {
  input: {
    prompt,
    duration,
    resolution: "720p",
    aspect_ratio: "16:9",
    generate_audio: true
  },
  logs: true,
  onQueueUpdate: (update) => {
    if (update.status === "IN_PROGRESS" && update.logs) {
      for (const log of update.logs) console.log(log.message);
    }
  }
});

const payload = result?.data ?? result;

function findMp4Url(x) {
  if (!x) return null;
  if (typeof x === "string" && /^https?:\/\/.+\.mp4(\?|$)/i.test(x)) return x;
  if (Array.isArray(x)) {
    for (const v of x) {
      const found = findMp4Url(v);
      if (found) return found;
    }
  }
  if (typeof x === "object") {
    for (const v of Object.values(x)) {
      const found = findMp4Url(v);
      if (found) return found;
    }
  }
  return null;
}

const videoUrl = payload?.video?.url || findMp4Url(payload);
if (!videoUrl) {
  console.error("BACKEND_RETURNED_NO_MP4_URL=true");
  console.error(JSON.stringify(payload, null, 2));
  process.exit(1);
}

const res = await fetch(videoUrl);
if (!res.ok) die(`MP4_DOWNLOAD_FAILED=${res.status}`);

fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(out, Buffer.from(await res.arrayBuffer()));

const size = fs.statSync(out).size;
if (size < 1000000) die(`OUTPUT_MP4_TOO_SMALL=${size}`);

console.log(`BACKEND_OUTPUT_MP4=${out}`);
console.log(`BACKEND_OUTPUT_BYTES=${size}`);
console.log("REAL_BACKEND_SHOT_PASS=true");
