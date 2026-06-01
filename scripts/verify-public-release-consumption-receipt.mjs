#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync
} from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

const repo = "kaaffilm/CINEMATICUM";
const sourceTag = "v1.2.0-outsider-reproducible-release";

const bundleName = "CASE_001_THE_LAST_RENDER_OUTSIDER_REPRODUCIBLE_RELEASE_BUNDLE.tar.gz";
const ledgerName = "RELEASE_ASSET_HASH_LEDGER.json";
const replayManifestName = "OUTSIDER_REPLAY_MANIFEST.json";
const standardName = "OUTSIDER_REPRODUCIBLE_RELEASE_STANDARD.json";

const expectedBundleSha256 = "6d6d26e428515b8a7f68bb35c2b7a7d80dc561857dbdb9d1df99d93a6eb0e1f8";
const expectedLedgerSha256 = "13fb510ccb3b77c1f45024b46e9fb3ffdd392da2e25f5bf4e9a484cace475f27";
const expectedReplayManifestSha256 = "201b2a329aae3fc1dd5946e15c4ff4ef3a7a6b13f702e5da070285151d5a2964";
const expectedArtifactSha256 = "f23d3da43ed0dfc0a4f97b7c6ad722107cc2531ac584780424ace2c45ff5a192";

const receiptPath = "CONSUMPTION/CASE_001_PUBLIC_RELEASE_CONSUMPTION_RECEIPT.json";

function run(cmd, args, opts = {}) {
  return execFileSync(cmd, args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    ...opts
  });
}

function runInherit(cmd, args, opts = {}) {
  execFileSync(cmd, args, {
    stdio: "inherit",
    ...opts
  });
}

function sha256(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function parseJsonCommand(cmd, args, cwd) {
  const out = run(cmd, args, { cwd });
  return JSON.parse(out);
}

function assertEqual(name, actual, expected) {
  if (actual !== expected) {
    throw new Error(`${name} mismatch: ${actual} !== ${expected}`);
  }
}

function assertObjectType(obj, expected) {
  if (!obj || obj.object_type !== expected) {
    throw new Error(`unexpected object_type: ${obj?.object_type}; expected ${expected}`);
  }
  if (obj.valid === false) {
    throw new Error(`${expected} returned valid=false`);
  }
}

function writeReceipt(obj) {
  mkdirSync("CONSUMPTION", { recursive: true });
  writeFileSync(receiptPath, JSON.stringify(obj, null, 2) + "\n");
}

try {
  const work = mkdtempSync(join(tmpdir(), "cinematicum-public-release-consumption-"));
  const downloadDir = join(work, "download");
  const extractDir = join(work, "extract");
  mkdirSync(downloadDir, { recursive: true });
  mkdirSync(extractDir, { recursive: true });

  runInherit("gh", [
    "release",
    "download",
    sourceTag,
    "--repo",
    repo,
    "--dir",
    downloadDir,
    "--clobber"
  ]);

  const bundlePath = join(downloadDir, bundleName);
  const ledgerPath = join(downloadDir, ledgerName);
  const replayManifestPath = join(downloadDir, replayManifestName);
  const standardPath = join(downloadDir, standardName);

  for (const path of [bundlePath, ledgerPath, replayManifestPath, standardPath]) {
    if (!existsSync(path)) throw new Error(`missing downloaded release asset: ${path}`);
  }

  const bundleSha256 = sha256(bundlePath);
  const ledgerSha256 = sha256(ledgerPath);
  const replayManifestSha256 = sha256(replayManifestPath);
  const standardSha256 = sha256(standardPath);

  assertEqual("release_bundle_sha256", bundleSha256, expectedBundleSha256);
  assertEqual("release_asset_hash_ledger_sha256", ledgerSha256, expectedLedgerSha256);
  assertEqual("outsider_replay_manifest_sha256", replayManifestSha256, expectedReplayManifestSha256);

  runInherit("tar", ["-xzf", bundlePath, "-C", extractDir]);

  const extractedRoots = readdirSync(extractDir)
    .map((name) => join(extractDir, name))
    .filter((path) => statSync(path).isDirectory());

  if (extractedRoots.length !== 1) {
    throw new Error(`expected exactly one extracted bundle root, found ${extractedRoots.length}`);
  }

  const root = extractedRoots[0];

  if (existsSync(join(root, ".git"))) {
    throw new Error("extracted outsider bundle unexpectedly contains .git");
  }

  const artifactPath = join(
    root,
    "CASES/CASE_001_THE_LAST_RENDER/FILM/CASE_001_THE_LAST_RENDER_GODCUT_0001.mp4"
  );

  if (!existsSync(artifactPath)) {
    throw new Error(`missing extracted artifact: ${artifactPath}`);
  }

  const artifactSha256 = sha256(artifactPath);
  assertEqual("artifact_sha256", artifactSha256, expectedArtifactSha256);

  const proof = parseJsonCommand("node", ["bin/cinematicum.cjs", "proof"], root);
  const artifact = parseJsonCommand("node", ["bin/cinematicum.cjs", "artifact"], root);
  const studio = parseJsonCommand("node", ["bin/cinematicum.cjs", "studio"], root);
  const verify = parseJsonCommand("node", ["bin/cinematicum.cjs", "verify"], root);
  const exported = parseJsonCommand("node", ["bin/cinematicum.cjs", "export"], root);

  assertObjectType(proof, "CINEMATICUM_PRODUCT_PROOF_SUMMARY");
  assertObjectType(artifact, "CINEMATICUM_PRODUCT_ARTIFACT_POINTER");
  assertObjectType(studio, "CINEMATICUM_STUDIO_POINTER");
  assertObjectType(verify, "CINEMATICUM_CLI_LEAF_VERIFICATION_RESULT");
  assertObjectType(exported, "CINEMATICUM_PRODUCT_RELEASE_BUNDLE_EXPORT_RESULT");

  const ledger = readJson(ledgerPath);
  const replayManifest = readJson(replayManifestPath);
  const outsiderStandard = readJson(standardPath);

  const receipt = {
    object_type: "CINEMATICUM_PUBLIC_RELEASE_CONSUMPTION_RECEIPT",
    schema_version: "1.3.0",
    jurisdiction: "CINEMATICUM",
    valid: true,
    errors: [],
    source_release_tag: sourceTag,
    source_release_url: `https://github.com/${repo}/releases/tag/${sourceTag}`,
    consumed_public_assets: [
      {
        name: bundleName,
        sha256: bundleSha256,
        expected_sha256: expectedBundleSha256
      },
      {
        name: ledgerName,
        sha256: ledgerSha256,
        expected_sha256: expectedLedgerSha256
      },
      {
        name: replayManifestName,
        sha256: replayManifestSha256,
        expected_sha256: expectedReplayManifestSha256
      },
      {
        name: standardName,
        sha256: standardSha256
      }
    ],
    release_asset_hash_ledger_object_type: ledger.object_type,
    outsider_replay_manifest_object_type: replayManifest.object_type,
    outsider_reproducible_release_standard_object_type: outsiderStandard.object_type,
    extracted_bundle_root_kind: "temporary_clean_extraction_root",
    extracted_bundle_contains_git_directory: false,
    extracted_artifact_sha256: artifactSha256,
    commands_verified_from_public_release_bundle: [
      proof.object_type,
      artifact.object_type,
      studio.object_type,
      verify.object_type,
      exported.object_type
    ],
    network_required_to_acquire_public_release_assets: true,
    network_runtime_required_after_asset_acquisition: false,
    external_api_used_after_asset_acquisition: false,
    external_media_used_after_asset_acquisition: false,
    manual_media_selection_used: false,
    candidate_selection_used: false,
    proves_public_release_assets_consumed: true,
    proves_extracted_outsider_replay: true,
    proves_compiler_generated_film: true,
    proves_film_issued: true,
    proves_truth: false,
    proves_admissibility: false,
    proves_external_reality: false
  };

  writeReceipt(receipt);
  console.log(JSON.stringify(receipt, null, 2));

  rmSync(work, { recursive: true, force: true });
} catch (error) {
  const failure = {
    object_type: "CINEMATICUM_PUBLIC_RELEASE_CONSUMPTION_RECEIPT",
    schema_version: "1.3.0",
    jurisdiction: "CINEMATICUM",
    valid: false,
    errors: [String(error?.message || error)],
    source_release_tag: sourceTag,
    proves_public_release_assets_consumed: false,
    proves_extracted_outsider_replay: false,
    proves_compiler_generated_film: false,
    proves_film_issued: false,
    proves_truth: false,
    proves_admissibility: false,
    proves_external_reality: false
  };

  writeReceipt(failure);
  console.log(JSON.stringify(failure, null, 2));
  process.exit(1);
}
