#!/usr/bin/env node
import { createHash } from "node:crypto";
import { createWriteStream, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { spawn } from "node:child_process";
import { once } from "node:events";

const CASE_ID = "CASE_001_THE_LAST_RENDER";
const JURISDICTION = "CINEMATICUM";
const VERSION = "0.7.0";

const W = 1280;
const H = 720;
const FPS = 24;
const DURATION_SECONDS = 60;
const FRAME_COUNT = FPS * DURATION_SECONDS;

const OUT = `CASES/${CASE_ID}/FILM/CASE_001_THE_LAST_RENDER_GODCUT_0001.mp4`;
const MANIFEST = `CASES/${CASE_ID}/FILM/GODCUT_0001_MANIFEST.json`;
const TIMELINE = `CASES/${CASE_ID}/FILM/GODCUT_0001_TIMELINE.json`;
const PROOF = `CASES/${CASE_ID}/PROOFS/godcut-compile-result.json`;
const BUILD = `.cinematicum-build/${CASE_ID}/godcut-v070`;
const SCORE = `${BUILD}/godcut-score.wav`;

const SHOTS = [
  ["S001", "dead_render_facility", 0, 6, "A dark autonomous render chamber wakes without outside media."],
  ["S002", "legal_slit", 6, 12, "A thin luminous admissibility slit opens across a black wall."],
  ["S003", "witness_plate", 12, 18, "A witness plate enters frame under procedural light pressure."],
  ["S004", "memory_grid", 18, 24, "A corrupted memory grid stabilizes into cinematic order."],
  ["S005", "black_box_corridor", 24, 30, "The black-box corridor records motion without judging it."],
  ["S006", "pressure_field", 30, 36, "A pressure field bends toward the last admissible witness."],
  ["S007", "archive_gate", 36, 42, "The archive gate seals the generated motion object."],
  ["S008", "witness_aperture", 42, 48, "The witness aperture becomes the center of the film."],
  ["S009", "terminal_cut", 48, 54, "The terminal cut collapses the world into a verified frame."],
  ["S010", "final_silence", 54, 60, "The film ends as an issued compiler artifact, not a truth claim."]
];

mkdirSync(dirname(OUT), { recursive: true });
mkdirSync(dirname(PROOF), { recursive: true });
mkdirSync(BUILD, { recursive: true });

function sha256File(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function clamp(v) {
  return v < 0 ? 0 : v > 255 ? 255 : v | 0;
}

function setPix(buf, x, y, r, g, b) {
  if (x < 0 || x >= W || y < 0 || y >= H) return;
  const i = (y * W + x) * 3;
  buf[i] = clamp(r);
  buf[i + 1] = clamp(g);
  buf[i + 2] = clamp(b);
}

function rect(buf, x0, y0, x1, y1, r, g, b) {
  x0 = Math.max(0, x0 | 0); y0 = Math.max(0, y0 | 0);
  x1 = Math.min(W, x1 | 0); y1 = Math.min(H, y1 | 0);
  for (let y = y0; y < y1; y++) {
    let i = (y * W + x0) * 3;
    for (let x = x0; x < x1; x++) {
      buf[i++] = clamp(r); buf[i++] = clamp(g); buf[i++] = clamp(b);
    }
  }
}

function circle(buf, cx, cy, radius, r, g, b, alpha = 1) {
  const rr = radius * radius;
  const x0 = Math.max(0, Math.floor(cx - radius));
  const x1 = Math.min(W - 1, Math.ceil(cx + radius));
  const y0 = Math.max(0, Math.floor(cy - radius));
  const y1 = Math.min(H - 1, Math.ceil(cy + radius));
  for (let y = y0; y <= y1; y++) {
    for (let x = x0; x <= x1; x++) {
      const dx = x - cx, dy = y - cy;
      if (dx * dx + dy * dy <= rr) {
        const i = (y * W + x) * 3;
        buf[i] = clamp(buf[i] * (1 - alpha) + r * alpha);
        buf[i + 1] = clamp(buf[i + 1] * (1 - alpha) + g * alpha);
        buf[i + 2] = clamp(buf[i + 2] * (1 - alpha) + b * alpha);
      }
    }
  }
}

function lineH(buf, y, x0, x1, r, g, b) {
  rect(buf, x0, y, x1, y + 2, r, g, b);
}

function baseFrame(t, shotIndex) {
  const buf = Buffer.alloc(W * H * 3);
  const pulse = 0.5 + 0.5 * Math.sin(t * 0.7);
  for (let y = 0; y < H; y++) {
    const v = y / H;
    const fog = Math.pow(1 - Math.abs(v - 0.56), 3) * 18;
    const top = 3 + shotIndex * 0.2;
    const r = top + fog + pulse * 2;
    const g = top + fog + pulse * 2;
    const b = top + fog + pulse * 3;
    let i = y * W * 3;
    for (let x = 0; x < W; x++) {
      const vignette = Math.abs((x / W) - 0.5) * 18;
      buf[i++] = clamp(r - vignette);
      buf[i++] = clamp(g - vignette);
      buf[i++] = clamp(b - vignette + 2);
    }
  }
  rect(buf, 0, 0, W, 84, 0, 0, 0);
  rect(buf, 0, H - 84, W, H, 0, 0, 0);
  return buf;
}

function renderFrame(n) {
  const t = n / FPS;
  const shotIndex = Math.min(SHOTS.length - 1, Math.floor(t / 6));
  const local = (t - shotIndex * 6) / 6;
  const buf = baseFrame(t, shotIndex);

  const breathe = Math.sin(local * Math.PI);
  const cx = W / 2;
  const cy = H / 2;

  if (shotIndex === 0) {
    for (let k = 0; k < 9; k++) {
      const x = 120 + k * 130 + Math.sin(t * 0.4 + k) * 8;
      rect(buf, x, 130, x + 32, 590, 7, 7, 8);
      lineH(buf, 190 + k * 17, x - 18, x + 50, 36, 36, 38);
    }
    rect(buf, 0, 510, W, 560, 5, 5, 6);
    circle(buf, cx, 382, 38 + breathe * 16, 170, 170, 165, 0.18);
  }

  if (shotIndex === 1) {
    rect(buf, 0, 318, W, 328, 170 + 60 * breathe, 170 + 60 * breathe, 165 + 70 * breathe);
    rect(buf, 0, 330, W, 333, 38, 38, 42);
    for (let k = 0; k < 12; k++) rect(buf, k * 120, 120, k * 120 + 8, 600, 3, 3, 4);
  }

  if (shotIndex === 2) {
    rect(buf, 420, 452, 860, 502, 18, 18, 20);
    rect(buf, 455, 430, 825, 455, 42 + 30 * breathe, 42 + 30 * breathe, 44 + 30 * breathe);
    circle(buf, cx, 350, 72, 110, 110, 108, 0.16);
    lineH(buf, 360, 280, 1000, 80, 80, 84);
  }

  if (shotIndex === 3) {
    for (let x = 80; x < W - 80; x += 52) rect(buf, x, 120, x + 2, 600, 20, 20, 23);
    for (let y = 130; y < 590; y += 42) lineH(buf, y, 80, W - 80, 20, 20, 23);
    const sweep = 80 + local * (W - 160);
    rect(buf, sweep, 120, sweep + 8, 600, 160, 160, 158);
  }

  if (shotIndex === 4) {
    for (let k = 0; k < 18; k++) {
      const z = k / 18;
      const w = 920 * (1 - z);
      const h = 420 * (1 - z);
      rect(buf, cx - w / 2, cy - h / 2, cx - w / 2 + 4, cy + h / 2, 18 + k, 18 + k, 20 + k);
      rect(buf, cx + w / 2, cy - h / 2, cx + w / 2 + 4, cy + h / 2, 18 + k, 18 + k, 20 + k);
      lineH(buf, cy - h / 2, cx - w / 2, cx + w / 2, 18 + k, 18 + k, 20 + k);
    }
    circle(buf, cx, cy, 34 + 20 * breathe, 190, 190, 184, 0.12);
  }

  if (shotIndex === 5) {
    for (let k = 0; k < 22; k++) {
      const y = 110 + k * 22;
      const x0 = 200 + Math.sin(t * 1.5 + k) * 80;
      lineH(buf, y, x0, W - x0, 40 + k, 40 + k, 44 + k);
    }
    circle(buf, cx + Math.sin(t) * 90, cy, 118, 110, 110, 108, 0.11);
  }

  if (shotIndex === 6) {
    rect(buf, 260, 160, 1020, 560, 8, 8, 10);
    rect(buf, 290, 190, 990, 530, 2, 2, 3);
    rect(buf, 610, 150, 670, 570, 48 + 35 * breathe, 48 + 35 * breathe, 52 + 35 * breathe);
    circle(buf, cx, cy, 220, 22, 22, 24, 0.08);
  }

  if (shotIndex === 7) {
    circle(buf, cx, cy, 210, 16, 16, 18, 0.55);
    circle(buf, cx, cy, 144, 70, 70, 72, 0.18);
    circle(buf, cx, cy, 52 + 22 * breathe, 210, 210, 200, 0.22);
    rect(buf, 0, cy - 4, W, cy + 4, 120, 120, 118);
  }

  if (shotIndex === 8) {
    const close = 1 - local;
    rect(buf, 0, 84, W, 240 + close * 180, 0, 0, 0);
    rect(buf, 0, H - 240 - close * 180, W, H - 84, 0, 0, 0);
    rect(buf, 180, 340, 1100, 380, 120 + 50 * breathe, 120 + 50 * breathe, 118 + 50 * breathe);
    for (let k = 0; k < 7; k++) circle(buf, 260 + k * 125, 360, 8 + k, 200, 200, 190, 0.2);
  }

  if (shotIndex === 9) {
    const fade = 1 - local;
    circle(buf, cx, cy, 260 * fade + 20, 150, 150, 145, 0.10 * fade);
    rect(buf, 0, 340, W, 344, 80 * fade, 80 * fade, 78 * fade);
    rect(buf, 0, 0, W, H, 0, 0, 0 + 3 * fade);
  }

  // deterministic grain, sparse
  let seed = (n * 1103515245 + 12345) >>> 0;
  for (let g = 0; g < 3200; g++) {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    const x = seed % W;
    seed = (seed * 1664525 + 1013904223) >>> 0;
    const y = seed % H;
    const i = (y * W + x) * 3;
    const add = (seed & 7) - 3;
    buf[i] = clamp(buf[i] + add);
    buf[i + 1] = clamp(buf[i + 1] + add);
    buf[i + 2] = clamp(buf[i + 2] + add);
  }

  return buf;
}

function writeWav(path) {
  const sampleRate = 48000;
  const samples = DURATION_SECONDS * sampleRate;
  const dataSize = samples * 2;
  const header = Buffer.alloc(44);
  header.write("RIFF", 0);
  header.writeUInt32LE(36 + dataSize, 4);
  header.write("WAVE", 8);
  header.write("fmt ", 12);
  header.writeUInt32LE(16, 16);
  header.writeUInt16LE(1, 20);
  header.writeUInt16LE(1, 22);
  header.writeUInt32LE(sampleRate, 24);
  header.writeUInt32LE(sampleRate * 2, 28);
  header.writeUInt16LE(2, 32);
  header.writeUInt16LE(16, 34);
  header.write("data", 36);
  header.writeUInt32LE(dataSize, 40);

  const out = createWriteStream(path);
  out.write(header);

  const chunk = Buffer.alloc(48000 * 2);
  for (let offset = 0; offset < samples; offset += 48000) {
    const len = Math.min(48000, samples - offset);
    for (let i = 0; i < len; i++) {
      const t = (offset + i) / sampleRate;
      const shotPulse = Math.sin(2 * Math.PI * (0.1 + Math.floor(t / 6) * 0.013) * t);
      const drone =
        Math.sin(2 * Math.PI * 41.2 * t) * 0.32 +
        Math.sin(2 * Math.PI * 55.0 * t) * 0.22 +
        Math.sin(2 * Math.PI * 82.4 * t) * 0.12 +
        Math.sin(2 * Math.PI * 164.8 * t) * 0.04;
      const gate = 0.65 + 0.25 * shotPulse;
      const v = Math.max(-1, Math.min(1, drone * gate));
      chunk.writeInt16LE((v * 28000) | 0, i * 2);
    }
    out.write(chunk.subarray(0, len * 2));
  }

  out.end();
}

async function compile() {
  writeWav(SCORE);

  const ffmpeg = spawn("ffmpeg", [
    "-y",
    "-f", "image2pipe",
    "-vcodec", "ppm",
    "-framerate", String(FPS),
    "-i", "pipe:0",
    "-i", SCORE,
    "-c:v", "libx264",
    "-pix_fmt", "yuv420p",
    "-profile:v", "high",
    "-crf", "18",
    "-preset", "slow",
    "-movflags", "+faststart",
    "-c:a", "aac",
    "-b:a", "192k",
    OUT
  ], { stdio: ["pipe", "inherit", "inherit"] });

  const header = Buffer.from(`P6\n${W} ${H}\n255\n`);

  for (let n = 0; n < FRAME_COUNT; n++) {
    const frame = renderFrame(n);
    if (!ffmpeg.stdin.write(header)) await once(ffmpeg.stdin, "drain");
    if (!ffmpeg.stdin.write(frame)) await once(ffmpeg.stdin, "drain");
  }

  ffmpeg.stdin.end();

  const [code] = await once(ffmpeg, "close");
  if (code !== 0) throw new Error(`ffmpeg failed with code ${code}`);

  const artifactSha = sha256File(OUT);
  const artifactSize = statSync(OUT).size;

  const timeline = {
    object_type: "CINEMATICUM_GODCUT_TIMELINE",
    schema_version: VERSION,
    jurisdiction: JURISDICTION,
    case_id: CASE_ID,
    artifact_path: OUT,
    width: W,
    height: H,
    fps: FPS,
    duration_seconds: DURATION_SECONDS,
    frame_count: FRAME_COUNT,
    shots: SHOTS.map(([shot_id, name, start, end, function_text]) => ({
      shot_id,
      name,
      start_seconds: start,
      end_seconds: end,
      duration_seconds: end - start,
      function: function_text
    })),
    external_api_used: false,
    external_media_used: false,
    manual_media_selection_used: false,
    candidate_selection_used: false
  };

  writeFileSync(TIMELINE, JSON.stringify(timeline, null, 2) + "\n");

  const manifest = {
    object_type: "CINEMATICUM_GODCUT_MANIFEST",
    schema_version: VERSION,
    jurisdiction: JURISDICTION,
    case_id: CASE_ID,
    artifact_path: OUT,
    artifact_sha256: artifactSha,
    artifact_size_bytes: artifactSize,
    timeline_path: TIMELINE,
    timeline_sha256: sha256File(TIMELINE),
    width: W,
    height: H,
    fps: FPS,
    duration_seconds: DURATION_SECONDS,
    frame_count: FRAME_COUNT,
    shots: SHOTS.length,
    audio: "procedural generated mono score encoded to AAC",
    external_api_used: false,
    external_media_used: false,
    manual_media_selection_used: false,
    candidate_selection_used: false,
    proves_compiler_generated_film: true,
    proves_film_issued: true,
    proves_truth: false,
    proves_admissibility: false,
    proves_external_reality: false
  };

  writeFileSync(MANIFEST, JSON.stringify(manifest, null, 2) + "\n");

  const result = {
    object_type: "CINEMATICUM_GODCUT_COMPILE_RESULT",
    schema_version: VERSION,
    jurisdiction: JURISDICTION,
    case_id: CASE_ID,
    valid: true,
    artifact_path: OUT,
    artifact_sha256: artifactSha,
    artifact_size_bytes: artifactSize,
    manifest_path: MANIFEST,
    manifest_sha256: sha256File(MANIFEST),
    timeline_path: TIMELINE,
    timeline_sha256: sha256File(TIMELINE),
    width: W,
    height: H,
    duration_seconds: DURATION_SECONDS,
    frame_count: FRAME_COUNT,
    shots: SHOTS.length,
    external_api_used: false,
    external_media_used: false,
    manual_media_selection_used: false,
    candidate_selection_used: false,
    raw_frames_tracked: false,
    proves_compiler_generated_film: true,
    proves_film_issued: true,
    proves_truth: false,
    proves_admissibility: false,
    proves_external_reality: false
  };

  writeFileSync(PROOF, JSON.stringify(result, null, 2) + "\n");
  console.log(JSON.stringify(result, null, 2));
}

compile().catch((err) => {
  console.error(err);
  process.exit(1);
});
