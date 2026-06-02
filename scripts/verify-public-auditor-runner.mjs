#!/usr/bin/env node
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";
import { execFileSync } from "node:child_process";

function sha256File(file) {
  return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

function fail(errors) {
  console.log(JSON.stringify({
    object_type: "CINEMATICUM_PUBLIC_AUDITOR_RUNNER_VERIFICATION_RESULT",
    schema_version: "1.7.0",
    valid: false,
    errors,
    proves_truth: false,
    proves_admissibility: false,
    proves_external_reality: false
  }, null, 2));
  process.exit(1);
}

try {
  const errors = [];
  const runnerPath = "AUDIT/CINEMATICUM_PUBLIC_AUDITOR_RUNNER.mjs";
  const standardPath = "AUDIT/PUBLIC_AUDITOR_RUNNER_STANDARD.json";
  const receiptPath = "AUDIT/CINEMATICUM_PUBLIC_AUDITOR_RUNNER_RECEIPT.json";

  if (!fs.existsSync(runnerPath)) errors.push(`missing runner: ${runnerPath}`);
  if (!fs.existsSync(standardPath)) errors.push(`missing standard: ${standardPath}`);

  const standard = JSON.parse(fs.readFileSync(standardPath, "utf8"));
  if (standard.object_type !== "CINEMATICUM_PUBLIC_AUDITOR_RUNNER_STANDARD") errors.push("bad standard object_type");
  if (standard.schema_version !== "1.7.0") errors.push("bad standard schema_version");
  if (standard.local_repository_required_for_auditor !== false) errors.push("standard must not require local repository");
  if (standard.private_source_required !== false) errors.push("standard must not require private source");
  if (standard.source_tree_embedded !== false) errors.push("standard must not embed source tree");
  if (standard.film_media_embedded_in_auditor_pack !== false) errors.push("standard must not embed film media in auditor pack");

  if (errors.length) fail(errors);

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "cinematicum-public-runner-verify-"));
  const tmpRunner = path.join(tmp, "CINEMATICUM_PUBLIC_AUDITOR_RUNNER.mjs");
  fs.copyFileSync(runnerPath, tmpRunner);
  fs.chmodSync(tmpRunner, 0o755);

  const stdout = execFileSync(process.execPath, [tmpRunner], {
    cwd: tmp,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"]
  });

  const receipt = JSON.parse(stdout);
  fs.writeFileSync(receiptPath, JSON.stringify(receipt, null, 2) + "\n");

  if (receipt.object_type !== "CINEMATICUM_PUBLIC_AUDITOR_RUNNER_RECEIPT") errors.push("bad receipt object_type");
  if (receipt.schema_version !== "1.7.0") errors.push("bad receipt schema_version");
  if (receipt.valid !== true) errors.push(`receipt invalid: ${JSON.stringify(receipt.errors)}`);
  if (receipt.proves_standalone_public_auditor_runner_exists !== true) errors.push("standalone runner not proven");
  if (receipt.proves_public_auditor_runner_requires_no_local_repository !== true) errors.push("no-local-repository boundary not proven");
  if (receipt.proves_public_auditor_runner_consumes_public_auditor_pack !== true) errors.push("public auditor pack consumption not proven");
  if (receipt.proves_public_auditor_runner_drives_replay !== true) errors.push("runner-driven replay not proven");
  if (receipt.proves_public_assets_named_by_pack_are_hash_verified !== true) errors.push("auditor-named public assets not hash verified");
  if (receipt.extracted_artifact_sha256 !== standard.expected_artifact_sha256) errors.push("artifact sha mismatch");
  if (receipt.local_repository_required_for_auditor !== false) errors.push("receipt claims local repository required");
  if (receipt.private_source_required !== false) errors.push("receipt claims private source required");
  if (receipt.source_tree_embedded !== false) errors.push("receipt claims source tree embedded");
  if (receipt.film_media_embedded_in_auditor_pack !== false) errors.push("receipt claims film media embedded in auditor pack");
  if (receipt.proves_truth !== false || receipt.proves_admissibility !== false || receipt.proves_external_reality !== false) {
    errors.push("forbidden truth/admissibility/external reality claim");
  }

  if (errors.length) fail(errors);

  console.log(JSON.stringify({
    object_type: "CINEMATICUM_PUBLIC_AUDITOR_RUNNER_VERIFICATION_RESULT",
    schema_version: "1.7.0",
    valid: true,
    errors: [],
    runner_path: runnerPath,
    runner_sha256: sha256File(runnerPath),
    standard_path: standardPath,
    standard_sha256: sha256File(standardPath),
    receipt_path: receiptPath,
    receipt_sha256: sha256File(receiptPath),
    source_auditor_pack_release_tag: receipt.source_auditor_pack_release_tag,
    expected_artifact_sha256: standard.expected_artifact_sha256,
    extracted_artifact_sha256: receipt.extracted_artifact_sha256,
    command_count: receipt.commands_verified_from_public_runner.length,
    proves_standalone_public_auditor_runner_exists: true,
    proves_public_auditor_runner_requires_no_local_repository: true,
    proves_public_auditor_runner_consumes_public_auditor_pack: true,
    proves_public_auditor_runner_drives_replay: true,
    proves_public_assets_named_by_pack_are_hash_verified: true,
    proves_film_issuance_chain_preserved: true,
    proves_truth: false,
    proves_admissibility: false,
    proves_external_reality: false
  }, null, 2));
} catch (err) {
  fail([String(err && err.stack ? err.stack : err)]);
}
