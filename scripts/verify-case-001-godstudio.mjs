#!/usr/bin/env node
import { createHash } from "node:crypto";
import { execSync } from "node:child_process";
import { existsSync, readFileSync, statSync } from "node:fs";

function trackedFilesForVerification() {
  try {
    return execSync("git rev-parse --is-inside-work-tree >/dev/null 2>&1 && git ls-files", {
      encoding: "utf8",
      shell: "/bin/sh"
    }).split(/\r?\n/).filter(Boolean);
  } catch {
    return execSync("find . -type f | sed 's#^./##'", {
      encoding: "utf8",
      shell: "/bin/sh"
    })
      .split(/\r?\n/)
      .filter(Boolean)
      .filter((p) => !p.startsWith(".git/"))
      .filter((p) => !p.startsWith("node_modules/"))
      .filter((p) => !p.startsWith("dist/"));
  }
}


const studioManifestPath = "STUDIO/CASE_001_GODCUT/studio-manifest.json";
const studioHtmlPath = "STUDIO/CASE_001_GODCUT/index.html";

function sha256(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}
function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}
function fail(error) {
  console.log(JSON.stringify({
    object_type: "CINEMATICUM_GODSTUDIO_VERIFICATION_RESULT",
    schema_version: "0.8.0",
    valid: false,
    errors: [error]
  }, null, 2));
  process.exit(1);
}
function assert(cond, msg) {
  if (!cond) fail(msg);
}

assert(existsSync(studioManifestPath), "missing studio manifest");
assert(existsSync(studioHtmlPath), "missing studio html");

const manifest = readJson(studioManifestPath);
const html = readFileSync(studioHtmlPath, "utf8");

assert(manifest.object_type === "CINEMATICUM_GODSTUDIO_RELEASE_CONSOLE", "wrong studio object type");
assert(manifest.schema_version === "0.8.0", "wrong studio schema version");
assert(manifest.proves_studio_surface_exists === true, "studio surface proof missing");
assert(manifest.proves_compiler_generated_film === true, "compiler film proof missing");
assert(manifest.proves_film_issued === true, "film issuance proof missing");
assert(manifest.proves_truth === false, "truth overclaim");
assert(manifest.proves_admissibility === false, "admissibility overclaim");
assert(manifest.proves_external_reality === false, "external reality overclaim");
assert(manifest.external_api_used === false, "external API flag is not false");
assert(manifest.external_media_used === false, "external media flag is not false");
assert(manifest.manual_media_selection_used === false, "manual media selection flag is not false");
assert(manifest.candidate_selection_used === false, "candidate selection flag is not false");
assert(manifest.network_runtime_required === false, "network runtime required");

assert(existsSync(manifest.artifact_path), "missing GODCUT artifact");
assert(sha256(manifest.artifact_path) === manifest.artifact_sha256, "GODCUT artifact sha mismatch");
assert(statSync(manifest.artifact_path).size === manifest.artifact_size_bytes, "GODCUT artifact size mismatch");

for (const path of manifest.linked_objects) {
  assert(existsSync(path), `missing linked proof object: ${path}`);
}

const forbidden = [
  "https://",
  "http://",
  "cdn.",
  "fetch(",
  "XMLHttpRequest",
  "import("
];
for (const marker of forbidden) {
  assert(!html.includes(marker), `studio html contains forbidden external runtime marker: ${marker}`);
}

assert(html.includes("../../" + manifest.artifact_path), "studio html does not reference local GODCUT artifact");
assert(html.includes(manifest.artifact_sha256), "studio html does not surface artifact sha");
assert(html.includes("proves_truth: false"), "studio html missing truth boundary");
assert(html.includes("NO EXTERNAL API"), "studio html missing external API boundary");

const tracked = trackedFilesForVerification();
const rawFrames = tracked.filter((p) => p.endsWith(".ppm") || p.includes("/frames/"));
assert(rawFrames.length === 0, `raw frame files are tracked: ${rawFrames.slice(0, 5).join(", ")}`);

console.log(JSON.stringify({
  object_type: "CINEMATICUM_GODSTUDIO_VERIFICATION_RESULT",
  schema_version: "0.8.0",
  valid: true,
  errors: [],
  studio_manifest: studioManifestPath,
  studio_html: studioHtmlPath,
  artifact_path: manifest.artifact_path,
  artifact_sha256: manifest.artifact_sha256,
  artifact_size_bytes: manifest.artifact_size_bytes,
  width: manifest.width,
  height: manifest.height,
  duration_seconds: manifest.duration_seconds,
  frame_count: manifest.frame_count,
  shots: manifest.shots,
  network_runtime_required: false,
  external_api_used: false,
  external_media_used: false,
  manual_media_selection_used: false,
  candidate_selection_used: false,
  proves_studio_surface_exists: true,
  proves_compiler_generated_film: true,
  proves_film_issued: true,
  proves_truth: false,
  proves_admissibility: false,
  proves_external_reality: false
}, null, 2));
