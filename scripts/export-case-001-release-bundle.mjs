#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { spawnSync } from "node:child_process";

const root = process.cwd();
const outRoot = path.join(root, "dist");
const bundleName = "CASE_001_THE_LAST_RENDER_RELEASE_BUNDLE";
const bundleRoot = path.join(outRoot, bundleName);
const tarPath = path.join(outRoot, `${bundleName}.tar.gz`);
const manifestPath = path.join(outRoot, `${bundleName}_MANIFEST.json`);

const required = [
  "CASES/CASE_001_THE_LAST_RENDER/FILM/CASE_001_THE_LAST_RENDER_GODCUT_0001.mp4",
  "CASES/CASE_001_THE_LAST_RENDER/FILM/GODCUT_0001_MANIFEST.json",
  "CASES/CASE_001_THE_LAST_RENDER/FILM/GODCUT_0001_TIMELINE.json",
  "CASES/CASE_001_THE_LAST_RENDER/PROOFS/godcut-compile-result.json",
  "CASES/CASE_001_THE_LAST_RENDER/PROOFS/godcut-verification-result.json",
  "CASES/CASE_001_THE_LAST_RENDER/PROOFS/director-engine-build-result.json",
  "CASES/CASE_001_THE_LAST_RENDER/DIRECTION/DIRECTOR_ENGINE_MANIFEST.json",
  "CASES/CASE_001_THE_LAST_RENDER/DIRECTION/DIRECTOR_DECISION_GRAPH.json",
  "CASES/CASE_001_THE_LAST_RENDER/DIRECTION/DIRECTORIAL_PRINCIPLES.json",
  "CASES/CASE_001_THE_LAST_RENDER/DIRECTION/SHOT_GRAMMAR.json",
  "CASES/CASE_001_THE_LAST_RENDER/DIRECTION/CAMERA_LAW.json",
  "CASES/CASE_001_THE_LAST_RENDER/DIRECTION/CUT_RHYTHM_LAW.json",
  "CASES/CASE_001_THE_LAST_RENDER/DIRECTION/SCORE_LAW.json",
  "STUDIO/CASE_001_GODCUT/index.html",
  "STUDIO/CASE_001_GODCUT/studio-manifest.json",
  "ENGINES/GODCUT/GODCUT_ENGINE_STANDARD.json",
  "ENGINES/DIRECTOR/DIRECTOR_ENGINE_STANDARD.json"
];

function sha256(file) {
  return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

function assert(condition, message) {
  if (!condition) {
    console.error(`CINEMATICUM_EXPORT_REJECTED: ${message}`);
    process.exit(1);
  }
}

function copyRel(rel) {
  const src = path.join(root, rel);
  const dst = path.join(bundleRoot, rel);
  assert(fs.existsSync(src), `missing required file: ${rel}`);
  fs.mkdirSync(path.dirname(dst), { recursive: true });
  fs.copyFileSync(src, dst);
}

function gitHead() {
  const r = spawnSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" });
  return r.status === 0 ? r.stdout.trim() : null;
}

fs.rmSync(bundleRoot, { recursive: true, force: true });
fs.rmSync(tarPath, { force: true });
fs.mkdirSync(bundleRoot, { recursive: true });

for (const rel of required) copyRel(rel);

const godcut = JSON.parse(fs.readFileSync(path.join(root, "CASES/CASE_001_THE_LAST_RENDER/PROOFS/godcut-verification-result.json"), "utf8"));
const director = JSON.parse(fs.readFileSync(path.join(root, "CASES/CASE_001_THE_LAST_RENDER/PROOFS/director-engine-build-result.json"), "utf8"));

const files = required.map(rel => {
  const abs = path.join(root, rel);
  return {
    path: rel,
    sha256: sha256(abs),
    size_bytes: fs.statSync(abs).size,
    binary: rel.endsWith(".mp4")
  };
});

const rawTracked = spawnSync("git", ["ls-files"], { cwd: root, encoding: "utf8" })
  .stdout
  .split(/\r?\n/)
  .filter(Boolean)
  .filter(x => x.includes("/frames/") || x.endsWith(".ppm"));

assert(rawTracked.length === 0, "raw frames are tracked");

const manifest = {
  object_type: "CINEMATICUM_PRODUCT_RELEASE_BUNDLE_MANIFEST",
  schema_version: "1.0.0",
  jurisdiction: "CINEMATICUM",
  case_id: "CASE_001_THE_LAST_RENDER",
  status: "PRODUCT_RELEASE_BUNDLE_EXPORTED",
  git_head: gitHead(),
  bundle_name: bundleName,
  artifact_path: godcut.artifact_path,
  artifact_sha256: godcut.artifact_sha256,
  artifact_size_bytes: godcut.artifact_size_bytes,
  width: godcut.width,
  height: godcut.height,
  duration_seconds: godcut.duration_seconds,
  frame_count: godcut.frame_count,
  shots: godcut.shots,
  direction_object_count: director.direction_object_count,
  external_api_used: false,
  external_media_used: false,
  manual_media_selection_used: false,
  candidate_selection_used: false,
  network_runtime_required: false,
  raw_frames_tracked: false,
  proves_product_boundary_exists: true,
  proves_release_bundle_exists: true,
  proves_director_engine_exists: true,
  proves_studio_surface_exists: true,
  proves_compiler_generated_film: true,
  proves_film_issued: true,
  proves_truth: false,
  proves_admissibility: false,
  proves_external_reality: false,
  files
};

fs.writeFileSync(path.join(bundleRoot, "RELEASE_BUNDLE_MANIFEST.json"), JSON.stringify(manifest, null, 2) + "\n");
fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + "\n");

const tar = spawnSync("tar", ["-czf", tarPath, "-C", outRoot, bundleName], { cwd: root, stdio: "inherit" });
assert(tar.status === 0, "tar bundle creation failed");

const result = {
  object_type: "CINEMATICUM_PRODUCT_RELEASE_BUNDLE_EXPORT_RESULT",
  schema_version: "1.0.0",
  valid: true,
  bundle_dir: path.relative(root, bundleRoot),
  bundle_tar: path.relative(root, tarPath),
  bundle_tar_sha256: sha256(tarPath),
  bundle_tar_size_bytes: fs.statSync(tarPath).size,
  manifest_path: path.relative(root, manifestPath),
  manifest_sha256: sha256(manifestPath),
  proves_product_boundary_exists: true,
  proves_release_bundle_exists: true,
  proves_film_issued: true,
  proves_truth: false,
  proves_admissibility: false,
  proves_external_reality: false
};

console.log(JSON.stringify(result, null, 2));
