#!/usr/bin/env node
import { createHash } from "node:crypto";
import { existsSync, readFileSync, statSync, writeFileSync } from "node:fs";

const CASE_ID = "CASE_001_THE_LAST_RENDER";
const VERSION = "0.7.0";
const MANIFEST = `CASES/${CASE_ID}/FILM/GODCUT_0001_MANIFEST.json`;
const TIMELINE = `CASES/${CASE_ID}/FILM/GODCUT_0001_TIMELINE.json`;
const PROOF = `CASES/${CASE_ID}/PROOFS/godcut-compile-result.json`;
const RESULT = `CASES/${CASE_ID}/PROOFS/godcut-verification-result.json`;

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function sha256File(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

const errors = [];

for (const path of [MANIFEST, TIMELINE, PROOF]) {
  if (!existsSync(path)) errors.push(`missing ${path}`);
}

let manifest = null;
let timeline = null;
let proof = null;

if (errors.length === 0) {
  manifest = readJson(MANIFEST);
  timeline = readJson(TIMELINE);
  proof = readJson(PROOF);

  const artifact = manifest.artifact_path;

  if (!existsSync(artifact)) errors.push("missing godcut artifact");
  if (manifest.schema_version !== VERSION) errors.push("wrong manifest schema");
  if (timeline.schema_version !== VERSION) errors.push("wrong timeline schema");
  if (proof.schema_version !== VERSION) errors.push("wrong compile result schema");

  if (existsSync(artifact)) {
    const sha = sha256File(artifact);
    const size = statSync(artifact).size;

    if (sha !== manifest.artifact_sha256) errors.push("manifest artifact sha mismatch");
    if (sha !== proof.artifact_sha256) errors.push("compile result artifact sha mismatch");
    if (size !== manifest.artifact_size_bytes) errors.push("manifest artifact size mismatch");
    if (size !== proof.artifact_size_bytes) errors.push("compile result artifact size mismatch");
    if (size < 1000000) errors.push("artifact too small for godcut");
  }

  if (sha256File(TIMELINE) !== manifest.timeline_sha256) errors.push("timeline sha mismatch");
  if (sha256File(MANIFEST) !== proof.manifest_sha256) errors.push("manifest sha mismatch");

  const requiredFalse = [
    "external_api_used",
    "external_media_used",
    "manual_media_selection_used",
    "candidate_selection_used",
    "proves_truth",
    "proves_admissibility",
    "proves_external_reality"
  ];

  for (const key of requiredFalse) {
    if (manifest[key] !== false) errors.push(`manifest forbidden claim: ${key}`);
    if (proof[key] !== false) errors.push(`compile result forbidden claim: ${key}`);
  }

  if (manifest.proves_compiler_generated_film !== true) errors.push("manifest does not prove compiler generation");
  if (manifest.proves_film_issued !== true) errors.push("manifest does not prove film issuance");
  if (proof.proves_compiler_generated_film !== true) errors.push("compile result does not prove compiler generation");
  if (proof.proves_film_issued !== true) errors.push("compile result does not prove film issuance");

  if (manifest.width !== 1280 || manifest.height !== 720) errors.push("wrong resolution");
  if (manifest.duration_seconds !== 60) errors.push("wrong duration");
  if (manifest.frame_count !== 1440) errors.push("wrong frame count");
  if (manifest.shots !== 10) errors.push("wrong shot count");
  if (!Array.isArray(timeline.shots) || timeline.shots.length !== 10) errors.push("timeline shot count mismatch");
}

const result = {
  object_type: "CINEMATICUM_GODCUT_VERIFICATION_RESULT",
  schema_version: VERSION,
  jurisdiction: "CINEMATICUM",
  case_id: CASE_ID,
  valid: errors.length === 0,
  errors,
  artifact_path: manifest?.artifact_path ?? null,
  artifact_sha256: manifest?.artifact_sha256 ?? null,
  artifact_size_bytes: manifest?.artifact_size_bytes ?? null,
  width: manifest?.width ?? null,
  height: manifest?.height ?? null,
  duration_seconds: manifest?.duration_seconds ?? null,
  frame_count: manifest?.frame_count ?? null,
  shots: manifest?.shots ?? null,
  external_api_used: false,
  external_media_used: false,
  manual_media_selection_used: false,
  candidate_selection_used: false,
  proves_compiler_generated_film: errors.length === 0,
  proves_film_issued: errors.length === 0,
  proves_truth: false,
  proves_admissibility: false,
  proves_external_reality: false
};

writeFileSync(RESULT, JSON.stringify(result, null, 2) + "\n");
console.log(JSON.stringify(result, null, 2));

if (!result.valid) process.exit(1);
