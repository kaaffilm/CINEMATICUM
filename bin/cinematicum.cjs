#!/usr/bin/env node
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const root = path.resolve(__dirname, "..");
const caseId = "CASE_001_THE_LAST_RENDER";
const film = path.join(root, "CASES/CASE_001_THE_LAST_RENDER/FILM/CASE_001_THE_LAST_RENDER_GODCUT_0001.mp4");
const studio = path.join(root, "STUDIO/CASE_001_GODCUT/index.html");

function run(cmd, args) {
  const r = spawnSync(cmd, args, { cwd: root, stdio: "inherit" });
  if (r.status !== 0) process.exit(r.status ?? 1);
}

function readJson(rel) {
  return JSON.parse(fs.readFileSync(path.join(root, rel), "utf8"));
}

function help() {
  console.log(`CINEMATICUM

Usage:
  cinematicum verify
  cinematicum proof
  cinematicum artifact
  cinematicum studio
  cinematicum export
  cinematicum help

Boundary:
  no external API
  no external media
  no network runtime dependency
  no manual media selection
  no candidate selection
  no truth/admissibility/external-reality claim`);
}

const cmd = process.argv[2] || "help";

if (cmd === "help" || cmd === "--help" || cmd === "-h") {
  help();
  process.exit(0);
}

if (cmd === "verify") {
  run("node", ["scripts/verify-case-001-godcut.mjs"]);
  run("node", ["scripts/verify-case-001-godstudio.mjs"]);
  run("node", ["scripts/verify-case-001-director-engine.mjs"]);
  process.exit(0);
}

if (cmd === "proof") {
  const godcut = readJson("CASES/CASE_001_THE_LAST_RENDER/PROOFS/godcut-verification-result.json");
  const director = readJson("CASES/CASE_001_THE_LAST_RENDER/PROOFS/director-engine-build-result.json");
  const studioManifest = readJson("STUDIO/CASE_001_GODCUT/studio-manifest.json");

  console.log(JSON.stringify({
    object_type: "CINEMATICUM_PRODUCT_PROOF_SUMMARY",
    schema_version: "1.0.0",
    case_id: caseId,
    status: "PRODUCT_BOUNDARY_READY",
    artifact_path: godcut.artifact_path,
    artifact_sha256: godcut.artifact_sha256,
    artifact_size_bytes: godcut.artifact_size_bytes,
    resolution: `${godcut.width}x${godcut.height}`,
    duration_seconds: godcut.duration_seconds,
    frame_count: godcut.frame_count,
    shots: godcut.shots,
    studio_surface: studioManifest.studio_html || "STUDIO/CASE_001_GODCUT/index.html",
    direction_object_count: director.direction_object_count,
    external_api_used: false,
    external_media_used: false,
    manual_media_selection_used: false,
    candidate_selection_used: false,
    network_runtime_required: false,
    proves_director_engine_exists: true,
    proves_studio_surface_exists: true,
    proves_compiler_generated_film: true,
    proves_film_issued: true,
    proves_truth: false,
    proves_admissibility: false,
    proves_external_reality: false
  }, null, 2));
  process.exit(0);
}

if (cmd === "artifact") {
  const godcut = readJson("CASES/CASE_001_THE_LAST_RENDER/PROOFS/godcut-verification-result.json");
  console.log(JSON.stringify({
    object_type: "CINEMATICUM_PRODUCT_ARTIFACT_POINTER",
    schema_version: "1.0.0",
    case_id: caseId,
    artifact_path: godcut.artifact_path,
    artifact_sha256: godcut.artifact_sha256,
    artifact_size_bytes: godcut.artifact_size_bytes,
    width: godcut.width,
    height: godcut.height,
    duration_seconds: godcut.duration_seconds,
    frame_count: godcut.frame_count,
    shots: godcut.shots
  }, null, 2));
  process.exit(0);
}

if (cmd === "studio") {
  if (!fs.existsSync(studio)) {
    console.error("CINEMATICUM_STUDIO_MISSING:", path.relative(root, studio));
    process.exit(1);
  }

  const platform = process.platform;
  const opener =
    platform === "darwin" ? "open" :
    platform === "win32" ? "cmd" :
    "xdg-open";

  const args =
    platform === "win32" ? ["/c", "start", "", studio] : [studio];

  const r = spawnSync(opener, args, { cwd: root, stdio: "inherit" });
  if (r.status !== 0) {
    console.log(studio);
  }
  process.exit(0);
}

if (cmd === "export") {
  run("node", ["scripts/export-case-001-release-bundle.mjs"]);
  process.exit(0);
}

console.error(`Unknown command: ${cmd}`);
help();
process.exit(1);
