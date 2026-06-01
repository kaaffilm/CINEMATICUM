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


const CASE_ID = "CASE_001_THE_LAST_RENDER";
const manifestPath = `CASES/${CASE_ID}/DIRECTION/DIRECTOR_ENGINE_MANIFEST.json`;
const resultPath = `CASES/${CASE_ID}/PROOFS/director-engine-build-result.json`;

function sha256(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}
function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}
function fail(error) {
  console.log(JSON.stringify({
    object_type: "CINEMATICUM_DIRECTOR_ENGINE_VERIFICATION_RESULT",
    schema_version: "0.9.0",
    valid: false,
    errors: [error]
  }, null, 2));
  process.exit(1);
}
function assert(cond, msg) {
  if (!cond) fail(msg);
}

assert(existsSync(manifestPath), "missing director engine manifest");
assert(existsSync(resultPath), "missing director engine build result");

const manifest = readJson(manifestPath);
const result = readJson(resultPath);

assert(manifest.object_type === "CINEMATICUM_DIRECTOR_ENGINE_MANIFEST", "wrong manifest object type");
assert(manifest.schema_version === "0.9.0", "wrong manifest schema");
assert(manifest.case_id === CASE_ID, "wrong case id");
assert(manifest.status === "DIRECTOR_ENGINE_LOCKED", "director engine not locked");

assert(result.valid === true, "director build result invalid");
assert(result.manifest_sha256 === sha256(manifestPath), "director result manifest sha mismatch");

assert(existsSync(manifest.issued_artifact.path), "missing issued artifact");
assert(sha256(manifest.issued_artifact.path) === manifest.issued_artifact.sha256, "issued artifact sha mismatch");
assert(statSync(manifest.issued_artifact.path).size === manifest.issued_artifact.size_bytes, "issued artifact size mismatch");

for (const rec of manifest.upstream_proofs) {
  assert(existsSync(rec.path), `missing upstream proof: ${rec.path}`);
  assert(sha256(rec.path) === rec.sha256, `upstream proof sha mismatch: ${rec.path}`);
}

for (const rec of manifest.direction_objects) {
  assert(existsSync(rec.path), `missing direction object: ${rec.path}`);
  assert(sha256(rec.path) === rec.sha256, `direction object sha mismatch: ${rec.path}`);
  const obj = readJson(rec.path);
  assert(obj.proves_truth === false, `truth overclaim in ${rec.path}`);
  assert(obj.proves_admissibility === false, `admissibility overclaim in ${rec.path}`);
  assert(obj.proves_external_reality === false, `external reality overclaim in ${rec.path}`);
}

const grammar = readJson(`CASES/${CASE_ID}/DIRECTION/SHOT_GRAMMAR.json`);
assert(grammar.total_shots === manifest.issued_artifact.shots, "shot grammar count does not match issued artifact");
assert(Array.isArray(grammar.shots), "shot grammar missing shots array");
assert(grammar.shots.length === manifest.issued_artifact.shots, "shot grammar shot array mismatch");

for (const shot of grammar.shots) {
  assert(typeof shot.shot_id === "string" && shot.shot_id.length > 0, "shot missing id");
  assert(typeof shot.function === "string" && shot.function.length > 0, `shot ${shot.shot_id} missing function`);
  assert(typeof shot.camera_motion === "string" && shot.camera_motion.length > 0, `shot ${shot.shot_id} missing camera motion`);
  assert(typeof shot.score_cue === "string" && shot.score_cue.length > 0, `shot ${shot.shot_id} missing score cue`);
  assert(shot.proves_truth === false, `shot ${shot.shot_id} truth overclaim`);
  assert(shot.proves_admissibility === false, `shot ${shot.shot_id} admissibility overclaim`);
  assert(shot.proves_external_reality === false, `shot ${shot.shot_id} external reality overclaim`);
}

const graph = readJson(`CASES/${CASE_ID}/DIRECTION/DIRECTOR_DECISION_GRAPH.json`);
assert(Array.isArray(graph.nodes) && graph.nodes.length >= grammar.shots.length, "decision graph lacks shot nodes");
assert(Array.isArray(graph.edges) && graph.edges.length >= grammar.shots.length, "decision graph lacks causal edges");

assert(manifest.external_api_used === false, "external API flag not false");
assert(manifest.external_media_used === false, "external media flag not false");
assert(manifest.manual_media_selection_used === false, "manual media selection flag not false");
assert(manifest.candidate_selection_used === false, "candidate selection flag not false");
assert(manifest.network_runtime_required === false, "network runtime required");
assert(manifest.proves_director_engine_exists === true, "director engine proof missing");
assert(manifest.proves_compiler_generated_film === true, "compiler film proof missing");
assert(manifest.proves_film_issued === true, "film issuance proof missing");
assert(manifest.proves_truth === false, "manifest truth overclaim");
assert(manifest.proves_admissibility === false, "manifest admissibility overclaim");
assert(manifest.proves_external_reality === false, "manifest external reality overclaim");

const tracked = trackedFilesForVerification();
const rawFrames = tracked.filter((p) => p.endsWith(".ppm") || p.includes("/frames/"));
assert(rawFrames.length === 0, `raw frame files tracked: ${rawFrames.slice(0, 5).join(", ")}`);

console.log(JSON.stringify({
  object_type: "CINEMATICUM_DIRECTOR_ENGINE_VERIFICATION_RESULT",
  schema_version: "0.9.0",
  jurisdiction: "CINEMATICUM",
  case_id: CASE_ID,
  valid: true,
  errors: [],
  manifest_path: manifestPath,
  manifest_sha256: sha256(manifestPath),
  result_path: resultPath,
  artifact_path: manifest.issued_artifact.path,
  artifact_sha256: manifest.issued_artifact.sha256,
  width: manifest.issued_artifact.width,
  height: manifest.issued_artifact.height,
  duration_seconds: manifest.issued_artifact.duration_seconds,
  frame_count: manifest.issued_artifact.frame_count,
  shots: manifest.issued_artifact.shots,
  direction_object_count: manifest.direction_objects.length,
  external_api_used: false,
  external_media_used: false,
  manual_media_selection_used: false,
  candidate_selection_used: false,
  network_runtime_required: false,
  raw_frames_tracked: false,
  proves_director_engine_exists: true,
  proves_compiler_generated_film: true,
  proves_film_issued: true,
  proves_truth: false,
  proves_admissibility: false,
  proves_external_reality: false
}, null, 2));
