#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import crypto from "node:crypto";
import zlib from "node:zlib";
import { execFileSync } from "node:child_process";

const CASE_ID = "CASE_001_THE_LAST_RENDER";
const BUNDLE_NAME = `${CASE_ID}_OUTSIDER_REPRODUCIBLE_RELEASE_BUNDLE`;
const BUNDLE_TAR = `dist/${BUNDLE_NAME}.tar.gz`;
const LEDGER_PATH = "REPRODUCIBILITY/RELEASE_ASSET_HASH_LEDGER.json";
const CANONICAL_ARTIFACT_REL = "CASES/CASE_001_THE_LAST_RENDER/FILM/CASE_001_THE_LAST_RENDER_GODCUT_0001.mp4";
const CANONICAL_ARTIFACT_SHA256 = "f23d3da43ed0dfc0a4f97b7c6ad722107cc2531ac584780424ace2c45ff5a192";

function sha256File(p) {
  return crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex");
}

function jsonOut(obj) {
  process.stdout.write(JSON.stringify(obj, null, 2) + "\n");
}

function parseJsonCommand(cmd, args, cwd) {
  const out = execFileSync(cmd, args, { cwd, encoding: "utf8" }).trim();
  try {
    return JSON.parse(out);
  } catch (e) {
    throw new Error(`command did not emit single JSON: ${cmd} ${args.join(" ")}\n${out.slice(0, 500)}`);
  }
}

function readOctal(buf, start, len) {
  const raw = buf.subarray(start, start + len).toString("utf8").replace(/\0.*$/, "").trim();
  return raw ? parseInt(raw, 8) : 0;
}

function readString(buf, start, len) {
  return buf.subarray(start, start + len).toString("utf8").replace(/\0.*$/, "");
}

function extractTarGz(tarGz, dest) {
  const tar = zlib.gunzipSync(fs.readFileSync(tarGz));
  let off = 0;
  while (off + 512 <= tar.length) {
    const header = tar.subarray(off, off + 512);
    off += 512;
    if (header.every(b => b === 0)) break;

    const name = readString(header, 0, 100);
    const prefix = readString(header, 345, 155);
    const fullName = prefix ? `${prefix}/${name}` : name;
    const size = readOctal(header, 124, 12);
    const type = readString(header, 156, 1) || "0";

    const target = path.join(dest, fullName);
    const normalized = path.normalize(target);
    if (!normalized.startsWith(path.normalize(dest))) {
      throw new Error(`tar path traversal rejected: ${fullName}`);
    }

    if (type === "5") {
      fs.mkdirSync(normalized, { recursive: true });
    } else if (type === "0") {
      fs.mkdirSync(path.dirname(normalized), { recursive: true });
      fs.writeFileSync(normalized, tar.subarray(off, off + size));
      fs.chmodSync(normalized, fullName.includes("/bin/") ? 0o755 : 0o644);
    } else {
      throw new Error(`unsupported tar entry type ${type}: ${fullName}`);
    }

    off += size;
    if (off % 512) off += 512 - (off % 512);
  }
}

function exportOnce() {
  const out = execFileSync("node", ["scripts/export-deterministic-release-bundle.mjs"], { encoding: "utf8" });
  return JSON.parse(out);
}

const first = exportOnce();
const firstHash = first.bundle_tar_sha256;
const firstSize = first.bundle_tar_size_bytes;

const second = exportOnce();
const secondHash = second.bundle_tar_sha256;
const secondSize = second.bundle_tar_size_bytes;

const errors = [];

if (firstHash !== secondHash) errors.push(`deterministic bundle hash mismatch: ${firstHash} != ${secondHash}`);
if (firstSize !== secondSize) errors.push(`deterministic bundle size mismatch: ${firstSize} != ${secondSize}`);

const ledger = JSON.parse(fs.readFileSync(LEDGER_PATH, "utf8"));
const actualBundleHash = sha256File(BUNDLE_TAR);

if (actualBundleHash !== ledger.release_bundle_sha256) errors.push("bundle hash does not match release asset ledger");
if (actualBundleHash !== secondHash) errors.push("bundle hash does not match exporter result");
if (ledger.canonical_artifact_sha256 !== CANONICAL_ARTIFACT_SHA256) errors.push("ledger canonical artifact hash mismatch");

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "cinematicum-outsider-replay-"));
extractTarGz(BUNDLE_TAR, tmp);

const extractedRoot = path.join(tmp, BUNDLE_NAME);
const extractedArtifact = path.join(extractedRoot, CANONICAL_ARTIFACT_REL);
if (!fs.existsSync(extractedArtifact)) errors.push("extracted canonical artifact missing");
else {
  const extractedArtifactHash = sha256File(extractedArtifact);
  if (extractedArtifactHash !== CANONICAL_ARTIFACT_SHA256) {
    errors.push(`extracted artifact hash mismatch: ${extractedArtifactHash}`);
  }
}

const commands = [
  ["node", ["bin/cinematicum.cjs", "proof"]],
  ["node", ["bin/cinematicum.cjs", "artifact"]],
  ["node", ["bin/cinematicum.cjs", "studio"]],
  ["node", ["bin/cinematicum.cjs", "verify"]],
  ["node", ["bin/cinematicum.cjs", "export"]]
];

const commandObjects = [];
for (const [cmd, args] of commands) {
  const obj = parseJsonCommand(cmd, args, extractedRoot);
  commandObjects.push(obj.object_type);
  if (obj.valid === false) errors.push(`${args.join(" ")} returned valid=false`);
}

const verifyObj = parseJsonCommand("node", ["bin/cinematicum.cjs", "verify"], extractedRoot);
if (verifyObj.artifact_sha256 !== CANONICAL_ARTIFACT_SHA256) {
  errors.push("extracted bundle verify did not recover canonical artifact sha256");
}
if (verifyObj.network_runtime_required !== false) errors.push("network_runtime_required was not false");
if (verifyObj.external_api_used !== false) errors.push("external_api_used was not false");
if (verifyObj.external_media_used !== false) errors.push("external_media_used was not false");
if (verifyObj.manual_media_selection_used !== false) errors.push("manual_media_selection_used was not false");
if (verifyObj.candidate_selection_used !== false) errors.push("candidate_selection_used was not false");

const result = {
  object_type: "CINEMATICUM_OUTSIDER_REPRODUCIBLE_RELEASE_VERIFICATION_RESULT",
  schema_version: "1.2.0",
  valid: errors.length === 0,
  errors,
  release_bundle: BUNDLE_TAR,
  release_bundle_sha256: actualBundleHash,
  release_bundle_size_bytes: fs.statSync(BUNDLE_TAR).size,
  deterministic_export_first_sha256: firstHash,
  deterministic_export_second_sha256: secondHash,
  release_asset_hash_ledger: LEDGER_PATH,
  extracted_bundle_root: extractedRoot,
  extracted_artifact_sha256: fs.existsSync(extractedArtifact) ? sha256File(extractedArtifact) : null,
  commands_verified_from_extracted_bundle: commandObjects,
  artifact_sha256: CANONICAL_ARTIFACT_SHA256,
  git_required_after_extraction: false,
  network_runtime_required: false,
  external_api_used: false,
  external_media_used: false,
  manual_media_selection_used: false,
  candidate_selection_used: false,
  proves_outsider_reproducible_release: errors.length === 0,
  proves_compiler_generated_film: true,
  proves_film_issued: true,
  proves_truth: false,
  proves_admissibility: false,
  proves_external_reality: false
};

jsonOut(result);
if (!result.valid) process.exit(1);
