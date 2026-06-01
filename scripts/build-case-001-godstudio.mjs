#!/usr/bin/env node
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync, statSync } from "node:fs";
import { dirname } from "node:path";

const CASE_ID = "CASE_001_THE_LAST_RENDER";
const film = `CASES/${CASE_ID}/FILM/CASE_001_THE_LAST_RENDER_GODCUT_0001.mp4`;
const godcutManifestPath = `CASES/${CASE_ID}/FILM/GODCUT_0001_MANIFEST.json`;
const godcutTimelinePath = `CASES/${CASE_ID}/FILM/GODCUT_0001_TIMELINE.json`;
const compileProofPath = `CASES/${CASE_ID}/PROOFS/godcut-compile-result.json`;
const verifyProofPath = `CASES/${CASE_ID}/PROOFS/godcut-verification-result.json`;
const studioDir = "STUDIO/CASE_001_GODCUT";
const studioManifestPath = `${studioDir}/studio-manifest.json`;
const studioHtmlPath = `${studioDir}/index.html`;

function sha256(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}
function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}
function assert(cond, msg) {
  if (!cond) throw new Error(`CINEMATICUM_GODSTUDIO_BUILD_REJECTED: ${msg}`);
}

for (const path of [film, godcutManifestPath, godcutTimelinePath, compileProofPath, verifyProofPath]) {
  assert(existsSync(path), `missing required GODCUT object: ${path}`);
}

const verification = readJson(verifyProofPath);
assert(verification.valid === true, "GODCUT verification is not valid");
assert(verification.proves_compiler_generated_film === true, "compiler-generated film proof missing");
assert(verification.proves_film_issued === true, "film issuance proof missing");
assert(verification.external_api_used === false, "external API use detected");
assert(verification.external_media_used === false, "external media use detected");
assert(verification.manual_media_selection_used === false, "manual media selection detected");
assert(verification.candidate_selection_used === false, "candidate selection detected");

const artifactSha = sha256(film);
assert(artifactSha === verification.artifact_sha256, "artifact sha mismatch against verification proof");

mkdirSync(studioDir, { recursive: true });

const studioManifest = {
  object_type: "CINEMATICUM_GODSTUDIO_RELEASE_CONSOLE",
  schema_version: "0.8.0",
  jurisdiction: "CINEMATICUM",
  case_id: CASE_ID,
  title: "CASE 001 — THE LAST RENDER",
  status: "GODSTUDIO_RELEASE_CONSOLE_READY",
  artifact_path: film,
  artifact_sha256: artifactSha,
  artifact_size_bytes: statSync(film).size,
  width: verification.width,
  height: verification.height,
  duration_seconds: verification.duration_seconds,
  frame_count: verification.frame_count,
  shots: verification.shots,
  linked_objects: [
    godcutManifestPath,
    godcutTimelinePath,
    compileProofPath,
    verifyProofPath
  ],
  studio_capabilities: [
    "local_playback",
    "shot_timeline_inspection",
    "proof_surface",
    "release_manifest_surface",
    "binary_hash_surface",
    "no_external_runtime_dependency"
  ],
  external_api_used: false,
  external_media_used: false,
  manual_media_selection_used: false,
  candidate_selection_used: false,
  network_runtime_required: false,
  proves_studio_surface_exists: true,
  proves_compiler_generated_film: true,
  proves_film_issued: true,
  proves_truth: false,
  proves_admissibility: false,
  proves_external_reality: false
};

writeFileSync(studioManifestPath, JSON.stringify(studioManifest, null, 2) + "\n");

const videoSrc = "../../" + film;
const manifest = JSON.stringify(studioManifest, null, 2)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;");

const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CINEMATICUM GODSTUDIO — CASE 001</title>
<style>
:root {
  --bg: #050505;
  --panel: #101010;
  --line: #262626;
  --text: #e7e7e7;
  --muted: #8a8a8a;
  --hard: #ffffff;
}
* { box-sizing: border-box; }
html, body {
  margin: 0;
  min-height: 100%;
  background: radial-gradient(circle at 50% 0%, #171717 0%, #050505 44%, #000 100%);
  color: var(--text);
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
main {
  max-width: 1280px;
  margin: 0 auto;
  padding: 44px 28px 72px;
}
.kicker {
  color: var(--muted);
  letter-spacing: .24em;
  font-size: 12px;
  text-transform: uppercase;
}
h1 {
  margin: 14px 0 8px;
  font-size: clamp(42px, 7vw, 108px);
  line-height: .86;
  letter-spacing: -.07em;
}
.thesis {
  max-width: 780px;
  color: #bdbdbd;
  font-size: 18px;
  line-height: 1.55;
}
.screen {
  margin-top: 34px;
  border: 1px solid var(--line);
  border-radius: 24px;
  overflow: hidden;
  background: #000;
  box-shadow: 0 40px 120px rgba(0,0,0,.65);
}
video {
  display: block;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: #000;
}
.grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-top: 18px;
}
.card {
  border: 1px solid var(--line);
  border-radius: 18px;
  background: rgba(16,16,16,.78);
  padding: 16px;
}
.label {
  color: var(--muted);
  font-size: 11px;
  letter-spacing: .16em;
  text-transform: uppercase;
}
.value {
  margin-top: 8px;
  color: var(--hard);
  font-size: 18px;
  font-weight: 650;
}
.hash {
  overflow-wrap: anywhere;
  font-size: 13px;
  line-height: 1.45;
}
.timeline {
  display: grid;
  grid-template-columns: repeat(10, 1fr);
  gap: 8px;
  margin-top: 28px;
}
.shot {
  height: 86px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background:
    linear-gradient(180deg, rgba(255,255,255,.08), transparent),
    repeating-linear-gradient(90deg, #111 0 10px, #151515 10px 20px);
  display: flex;
  align-items: end;
  padding: 10px;
  color: #aaa;
  font-size: 12px;
}
.proofs {
  margin-top: 28px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}
pre {
  margin: 0;
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: #090909;
  color: #d5d5d5;
  overflow: auto;
  max-height: 460px;
  font-size: 12px;
  line-height: 1.45;
}
.boundary {
  margin-top: 30px;
  color: var(--muted);
  border-top: 1px solid var(--line);
  padding-top: 20px;
  font-size: 14px;
}
@media (max-width: 820px) {
  .grid, .proofs { grid-template-columns: 1fr; }
  .timeline { grid-template-columns: repeat(2, 1fr); }
}
</style>
</head>
<body>
<main>
  <div class="kicker">CINEMATICUM GODSTUDIO / v0.8.0 / CASE 001</div>
  <h1>THE LAST RENDER</h1>
  <p class="thesis">
    A self-contained release console for the compiler-issued GODCUT. Local playback, proof inspection,
    timeline surface, binary hash surface, and no external runtime dependency.
  </p>

  <section class="screen">
    <video controls preload="metadata" src="${videoSrc}"></video>
  </section>

  <section class="grid">
    <div class="card"><div class="label">Resolution</div><div class="value">${studioManifest.width}×${studioManifest.height}</div></div>
    <div class="card"><div class="label">Duration</div><div class="value">${studioManifest.duration_seconds}s</div></div>
    <div class="card"><div class="label">Frames</div><div class="value">${studioManifest.frame_count}</div></div>
    <div class="card"><div class="label">Shots</div><div class="value">${studioManifest.shots}</div></div>
    <div class="card"><div class="label">External API</div><div class="value">false</div></div>
    <div class="card"><div class="label">External Media</div><div class="value">false</div></div>
    <div class="card"><div class="label">Manual Selection</div><div class="value">false</div></div>
    <div class="card"><div class="label">Film Issued</div><div class="value">true</div></div>
  </section>

  <section class="card" style="margin-top:18px">
    <div class="label">Artifact SHA-256</div>
    <div class="value hash">${studioManifest.artifact_sha256}</div>
  </section>

  <section class="timeline">
    ${Array.from({ length: studioManifest.shots }, (_, i) => `<div class="shot">SHOT ${String(i + 1).padStart(2, "0")}</div>`).join("")}
  </section>

  <section class="proofs">
    <pre>${manifest}</pre>
    <pre>BOUNDARY:
proves_studio_surface_exists: true
proves_compiler_generated_film: true
proves_film_issued: true
proves_truth: false
proves_admissibility: false
proves_external_reality: false

NO NETWORK.
NO EXTERNAL API.
NO EXTERNAL MEDIA.
NO MANUAL MEDIA SELECTION.
NO CANDIDATE SELECTION.</pre>
  </section>

  <div class="boundary">
    CINEMATICUM does not prove truth, admissibility, or external reality. It proves this compiler-issued film artifact and this studio surface.
  </div>
</main>
</body>
</html>
`;

writeFileSync(studioHtmlPath, html);
console.log(JSON.stringify({
  object_type: "CINEMATICUM_GODSTUDIO_BUILD_RESULT",
  schema_version: "0.8.0",
  valid: true,
  studio_manifest: studioManifestPath,
  studio_html: studioHtmlPath,
  artifact_sha256: artifactSha,
  proves_studio_surface_exists: true,
  proves_compiler_generated_film: true,
  proves_film_issued: true,
  proves_truth: false,
  proves_admissibility: false,
  proves_external_reality: false
}, null, 2));
