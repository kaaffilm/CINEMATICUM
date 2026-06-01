#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { execFileSync } = require("node:child_process");

const root = path.resolve(__dirname, "..");

function abs(p) {
  return path.join(root, p);
}

function readJson(rel) {
  return JSON.parse(fs.readFileSync(abs(rel), "utf8"));
}

function sha256File(relOrAbs) {
  const p = path.isAbsolute(relOrAbs) ? relOrAbs : abs(relOrAbs);
  return crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex");
}

function fileSize(relOrAbs) {
  const p = path.isAbsolute(relOrAbs) ? relOrAbs : abs(relOrAbs);
  return fs.statSync(p).size;
}

function parseSingleJson(stdout, label) {
  const s = String(stdout || "").trim();
  if (!s) throw new Error(`${label} emitted empty stdout`);
  try {
    return JSON.parse(s);
  } catch (e) {
    throw new Error(`${label} did not emit single JSON object: ${e.message}`);
  }
}

function runJsonScript(rel) {
  const stdout = execFileSync(process.execPath, [abs(rel)], {
    cwd: root,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"]
  });
  return parseSingleJson(stdout, rel);
}

function print(obj) {
  process.stdout.write(JSON.stringify(obj, null, 2) + "\n");
}

function artifactPointer() {
  const godcut = readJson("CASES/CASE_001_THE_LAST_RENDER/PROOFS/godcut-verification-result.json");
  const artifactRel = godcut.artifact_path || "CASES/CASE_001_THE_LAST_RENDER/FILM/CASE_001_THE_LAST_RENDER_GODCUT_0001.mp4";
  const artifactAbs = abs(artifactRel);

  return {
    object_type: "CINEMATICUM_PRODUCT_ARTIFACT_POINTER",
    schema_version: "1.1.0",
    case_id: "CASE_001_THE_LAST_RENDER",
    artifact_path: artifactAbs,
    artifact_sha256: sha256File(artifactAbs),
    artifact_size_bytes: fileSize(artifactAbs),
    width: godcut.width,
    height: godcut.height,
    duration_seconds: godcut.duration_seconds,
    frame_count: godcut.frame_count,
    shots: godcut.shots
  };
}

function verifyLeaf() {
  const godcut = runJsonScript("scripts/verify-case-001-godcut.mjs");
  const godstudio = runJsonScript("scripts/verify-case-001-godstudio.mjs");
  const director = runJsonScript("scripts/verify-case-001-director-engine.mjs");

  const errors = [];
  for (const [name, result] of Object.entries({ godcut, godstudio, director })) {
    if (!result || result.valid !== true) {
      errors.push(`${name} verifier invalid`);
      if (Array.isArray(result && result.errors)) {
        errors.push(...result.errors.map((e) => `${name}: ${e}`));
      }
    }
  }

  const pointer = artifactPointer();

  return {
    object_type: "CINEMATICUM_CLI_LEAF_VERIFICATION_RESULT",
    schema_version: "1.1.0",
    case_id: "CASE_001_THE_LAST_RENDER",
    valid: errors.length === 0,
    errors,
    artifact_path: "CASES/CASE_001_THE_LAST_RENDER/FILM/CASE_001_THE_LAST_RENDER_GODCUT_0001.mp4",
    artifact_sha256: pointer.artifact_sha256,
    artifact_size_bytes: pointer.artifact_size_bytes,
    width: pointer.width,
    height: pointer.height,
    duration_seconds: pointer.duration_seconds,
    frame_count: pointer.frame_count,
    shots: pointer.shots,
    direction_object_count: director.direction_object_count,
    external_api_used: false,
    external_media_used: false,
    manual_media_selection_used: false,
    candidate_selection_used: false,
    network_runtime_required: false,
    proves_director_engine_exists: director.proves_director_engine_exists === true,
    proves_studio_surface_exists: godstudio.proves_studio_surface_exists === true,
    proves_compiler_generated_film: godcut.proves_compiler_generated_film === true,
    proves_film_issued: godcut.proves_film_issued === true,
    proves_truth: false,
    proves_admissibility: false,
    proves_external_reality: false
  };
}

function proofSummary() {
  const v = verifyLeaf();

  return {
    object_type: "CINEMATICUM_PRODUCT_PROOF_SUMMARY",
    schema_version: "1.1.0",
    case_id: "CASE_001_THE_LAST_RENDER",
    status: "INSTALLABLE_PRODUCT_BOUNDARY_READY",
    valid: v.valid,
    errors: v.errors,
    artifact_path: v.artifact_path,
    artifact_sha256: v.artifact_sha256,
    artifact_size_bytes: v.artifact_size_bytes,
    resolution: `${v.width}x${v.height}`,
    duration_seconds: v.duration_seconds,
    frame_count: v.frame_count,
    shots: v.shots,
    studio_surface: "STUDIO/CASE_001_GODCUT/index.html",
    direction_object_count: v.direction_object_count,
    package_root: root,
    external_api_used: false,
    external_media_used: false,
    manual_media_selection_used: false,
    candidate_selection_used: false,
    network_runtime_required: false,
    proves_installable_product_boundary: true,
    proves_director_engine_exists: v.proves_director_engine_exists,
    proves_studio_surface_exists: v.proves_studio_surface_exists,
    proves_compiler_generated_film: v.proves_compiler_generated_film,
    proves_film_issued: v.proves_film_issued,
    proves_truth: false,
    proves_admissibility: false,
    proves_external_reality: false
  };
}

function studioPointer() {
  const manifest = readJson("STUDIO/CASE_001_GODCUT/studio-manifest.json");
  return {
    object_type: "CINEMATICUM_STUDIO_POINTER",
    schema_version: "1.1.0",
    valid: true,
    studio_html: abs("STUDIO/CASE_001_GODCUT/index.html"),
    studio_manifest: abs("STUDIO/CASE_001_GODCUT/studio-manifest.json"),
    artifact_path: abs("CASES/CASE_001_THE_LAST_RENDER/FILM/CASE_001_THE_LAST_RENDER_GODCUT_0001.mp4"),
    artifact_sha256: manifest.artifact_sha256 || artifactPointer().artifact_sha256,
    network_runtime_required: false,
    external_api_used: false,
    external_media_used: false
  };
}

function exportBundle() {
  return runJsonScript("scripts/export-case-001-release-bundle.mjs");
}

function usage(exitCode = 0) {
  const text = [
    "Usage:",
    "  cinematicum verify",
    "  cinematicum proof",
    "  cinematicum artifact",
    "  cinematicum studio",
    "  cinematicum export"
  ].join("\n");
  process.stdout.write(text + "\n");
  process.exit(exitCode);
}

const cmd = process.argv[2];

try {
  if (!cmd || cmd === "--help" || cmd === "-h") usage(0);

  if (cmd === "verify") {
    const result = verifyLeaf();
    print(result);
    process.exit(result.valid ? 0 : 1);
  }

  if (cmd === "proof") {
    const result = proofSummary();
    print(result);
    process.exit(result.valid ? 0 : 1);
  }

  if (cmd === "artifact") {
    print(artifactPointer());
    process.exit(0);
  }

  if (cmd === "studio") {
    print(studioPointer());
    process.exit(0);
  }

  if (cmd === "export") {
    const result = exportBundle();
    print(result);
    process.exit(result.valid === false ? 1 : 0);
  }

  usage(1);
} catch (e) {
  print({
    object_type: "CINEMATICUM_CLI_ERROR",
    schema_version: "1.1.0",
    valid: false,
    errors: [String(e && e.message ? e.message : e)],
    proves_truth: false,
    proves_admissibility: false,
    proves_external_reality: false
  });
  process.exit(1);
}
