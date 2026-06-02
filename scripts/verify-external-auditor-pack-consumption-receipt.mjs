#!/usr/bin/env node
import { execFileSync, execSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync
} from "node:fs";
import { tmpdir } from "node:os";
import { basename, join, resolve } from "node:path";
import { createHash } from "node:crypto";
import { readFileSync as readConsumptionStandardFileSync } from "node:fs";

const expectedPublicAuditorPackCanonicalSha256 = JSON.parse(
  readConsumptionStandardFileSync("CONSUMPTION/EXTERNAL_AUDITOR_PACK_CONSUMPTION_STANDARD.json", "utf8")
).expected_public_auditor_pack_canonical_sha256;

const repo = "kaaffilm/CINEMATICUM";
const sourceReleaseTag = "v1.5.1-external-auditor-pack-public-sha-repair";

const expectedAuditorPackAsset = "CINEMATICUM_EXTERNAL_AUDITOR_PACK.json";
const expectedStandardAsset = "EXTERNAL_AUDITOR_PACK_STANDARD.json";
const receiptPath = "CONSUMPTION/EXTERNAL_AUDITOR_PACK_CONSUMPTION_RECEIPT.json";

function run(cmd, args, opts = {}) {
  return execFileSync(cmd, args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    ...opts
  });
}

function runInherited(cmd, args, opts = {}) {
  return execFileSync(cmd, args, {
    stdio: "inherit",
    ...opts
  });
}

function sha256Bytes(buf) {
  return createHash("sha256").update(buf).digest("hex");
}

function sha256File(file) {
  return sha256Bytes(readFileSync(file));
}

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonical(value[k])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function sha256CanonicalJson(value) {
  return sha256Bytes(Buffer.from(canonical(value), "utf8"));
}

function parseSingleJson(text, label) {
  const trimmed = String(text).trim();
  const obj = JSON.parse(trimmed);
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) {
    throw new Error(`${label} did not parse to a JSON object`);
  }
  return obj;
}

function requireEqual(actual, expected, label) {
  if (actual !== expected) throw new Error(`${label}: expected ${expected}; got ${actual}`);
}

function requireFalse(value, label) {
  if (value !== false) throw new Error(`${label}: expected false; got ${value}`);
}

function requireTrue(value, label) {
  if (value !== true) throw new Error(`${label}: expected true; got ${value}`);
}

function downloadReleaseAsset(tag, name, dir) {
  mkdirSync(dir, { recursive: true });
  runInherited("gh", [
    "release",
    "download",
    tag,
    "--repo",
    repo,
    "--pattern",
    name,
    "--dir",
    dir,
    "--clobber"
  ]);
  const out = join(dir, name);
  if (!existsSync(out)) throw new Error(`missing downloaded asset: ${tag}/${name}`);
  return out;
}

function releaseAssetNames(tag) {
  const raw = run("gh", [
    "release",
    "view",
    tag,
    "--repo",
    repo,
    "--json",
    "tagName,isDraft,isPrerelease,url,assets"
  ]);
  const release = JSON.parse(raw);
  requireEqual(release.tagName, tag, "release tag");
  requireFalse(release.isDraft, "release isDraft");
  requireFalse(release.isPrerelease, "release isPrerelease");
  return new Set((release.assets || []).map(a => a.name));
}

function findExtractedRoot(dir) {
  const dirs = readdirSync(dir, { withFileTypes: true }).filter(d => d.isDirectory()).map(d => join(dir, d.name));
  if (dirs.length !== 1) throw new Error(`expected exactly one extracted root; got ${dirs.length}`);
  return dirs[0];
}

function noGitDirectory(root) {
  if (existsSync(join(root, ".git"))) return false;
  const found = execSync(`find ${JSON.stringify(root)} -type d -name .git -print -quit`, {
    encoding: "utf8"
  }).trim();
  return found === "";
}

const errors = [];

try {
  const tmp = mkdtempSync(join(tmpdir(), "cinematicum-auditor-pack-consumption-"));
  const publicAuditDir = join(tmp, "public-auditor-pack-assets");
  const publicNamedAssetDir = join(tmp, "public-named-assets");
  const extractDir = join(tmp, "extract");

  mkdirSync(publicAuditDir, { recursive: true });
  mkdirSync(publicNamedAssetDir, { recursive: true });
  mkdirSync(extractDir, { recursive: true });

  const releaseNames = releaseAssetNames(sourceReleaseTag);
  for (const required of [expectedAuditorPackAsset, expectedStandardAsset]) {
    if (!releaseNames.has(required)) throw new Error(`public v1.5 release missing asset: ${required}`);
  }

  const publicPackPath = downloadReleaseAsset(sourceReleaseTag, expectedAuditorPackAsset, publicAuditDir);
  const publicStandardPath = downloadReleaseAsset(sourceReleaseTag, expectedStandardAsset, publicAuditDir);

  const publicPack = parseSingleJson(readFileSync(publicPackPath, "utf8"), expectedAuditorPackAsset);
  const publicStandard = parseSingleJson(readFileSync(publicStandardPath, "utf8"), expectedStandardAsset);

  const localPack = JSON.parse(readFileSync("AUDIT/CINEMATICUM_EXTERNAL_AUDITOR_PACK.json", "utf8"));
  const localStandardSha = sha256File("AUDIT/EXTERNAL_AUDITOR_PACK_STANDARD.json");

  requireEqual(publicPack.object_type, "CINEMATICUM_EXTERNAL_AUDITOR_PACK", "auditor pack object_type");
  requireEqual(publicPack.schema_version, "1.5.0", "auditor pack schema_version");
  requireEqual(publicPack.valid, true, "auditor pack valid");
  requireEqual(publicPack.standard.object_type, "CINEMATICUM_EXTERNAL_AUDITOR_PACK_STANDARD", "standard pointer object_type");
  requireEqual(publicStandard.object_type, "CINEMATICUM_EXTERNAL_AUDITOR_PACK_STANDARD", "public standard object_type");

  requireEqual(sha256CanonicalJson(publicPack), expectedPublicAuditorPackCanonicalSha256, "public auditor pack canonical sha");
  requireEqual(sha256File(publicStandardPath), localStandardSha, "public standard raw sha");
  requireEqual(sha256File(publicStandardPath), publicPack.standard.sha256, "standard sha named inside pack");

  if ("generated_from_head" in publicPack) throw new Error("auditor pack must not embed generated_from_head");
  requireEqual(
    publicPack.generated_from_head_kind,
    "intentionally_not_embedded_to_avoid_self_referential_commit_binding",
    "non-self-referential head boundary"
  );

  const boundary = publicPack.dependency_boundary || {};
  requireFalse(boundary.private_source_required, "private_source_required");
  requireFalse(boundary.local_repository_required_for_auditor, "local_repository_required_for_auditor");
  requireFalse(boundary.git_required_after_extraction, "git_required_after_extraction");
  requireFalse(boundary.source_tree_embedded, "source_tree_embedded");
  requireFalse(boundary.film_media_embedded_in_auditor_pack, "film_media_embedded_in_auditor_pack");
  requireTrue(boundary.public_network_required_to_acquire_assets, "public_network_required_to_acquire_assets");
  requireFalse(boundary.network_runtime_required_after_asset_acquisition, "network_runtime_required_after_asset_acquisition");
  requireFalse(boundary.external_api_used_after_asset_acquisition, "external_api_used_after_asset_acquisition");
  requireFalse(boundary.external_media_used_after_asset_acquisition, "external_media_used_after_asset_acquisition");
  requireFalse(boundary.manual_media_selection_used, "manual_media_selection_used");
  requireFalse(boundary.candidate_selection_used, "candidate_selection_used");

  const expectedAssets = publicPack.expected_public_assets_to_acquire || [];
  const expectedCommands = publicPack.expected_replay_commands_after_asset_acquisition || [];

  if (expectedAssets.length < 4) throw new Error(`expected at least 4 public assets; got ${expectedAssets.length}`);
  if (expectedCommands.length !== 5) throw new Error(`expected 5 replay commands; got ${expectedCommands.length}`);

  const consumedNamedAssets = [];
  let outsiderBundlePath = null;

  for (const asset of expectedAssets) {
    if (!asset.source_release_tag || !asset.name || !asset.sha256) {
      throw new Error(`malformed expected public asset: ${JSON.stringify(asset)}`);
    }

    const actualPath = downloadReleaseAsset(asset.source_release_tag, asset.name, publicNamedAssetDir);
    const actualSha = sha256File(actualPath);
    requireEqual(actualSha, asset.sha256, `public asset sha ${asset.source_release_tag}/${asset.name}`);

    consumedNamedAssets.push({
      source_release_tag: asset.source_release_tag,
      name: asset.name,
      sha256: actualSha,
      expected_sha256: asset.sha256,
      size_bytes: statSync(actualPath).size
    });

    if (asset.name === "CASE_001_THE_LAST_RENDER_OUTSIDER_REPRODUCIBLE_RELEASE_BUNDLE.tar.gz") {
      outsiderBundlePath = actualPath;
    }
  }

  if (!outsiderBundlePath) throw new Error("auditor pack did not name outsider reproducible release bundle");

  runInherited("tar", ["-xzf", outsiderBundlePath, "-C", extractDir]);
  const extractedRoot = findExtractedRoot(extractDir);

  if (!noGitDirectory(extractedRoot)) throw new Error("extracted outsider bundle contains .git");

  const commandResults = [];
  for (const spec of expectedCommands) {
    if (!spec.command || !spec.expected_object_type) throw new Error(`malformed replay command: ${JSON.stringify(spec)}`);

    const output = execSync(spec.command, {
      cwd: extractedRoot,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"]
    });

    const parsed = parseSingleJson(output, spec.command);
    requireEqual(parsed.object_type, spec.expected_object_type, `object_type for ${spec.command}`);

    commandResults.push({
      command: spec.command,
      object_type: parsed.object_type,
      valid: parsed.valid !== false
    });
  }

  const artifactPath = join(
    extractedRoot,
    "CASES/CASE_001_THE_LAST_RENDER/FILM/CASE_001_THE_LAST_RENDER_GODCUT_0001.mp4"
  );

  if (!existsSync(artifactPath)) throw new Error(`missing extracted GODCUT artifact: ${artifactPath}`);

  const extractedArtifactSha256 = sha256File(artifactPath);
  requireEqual(extractedArtifactSha256, publicPack.expected_artifact_sha256, "extracted artifact sha256");

  const receipt = {
    object_type: "CINEMATICUM_EXTERNAL_AUDITOR_PACK_CONSUMPTION_RECEIPT",
    schema_version: "1.6.0",
    jurisdiction: "CINEMATICUM",
    valid: true,
    errors: [],
    source_release_tag: sourceReleaseTag,
    source_release_url: `https://github.com/${repo}/releases/tag/${sourceReleaseTag}`,
    consumed_public_auditor_pack_assets: [
      {
        name: expectedAuditorPackAsset,
        sha256_canonical_json: sha256CanonicalJson(publicPack),
        expected_sha256_canonical_json: expectedPublicAuditorPackCanonicalSha256
      },
      {
        name: expectedStandardAsset,
        sha256: sha256File(publicStandardPath),
        expected_sha256: localStandardSha
      }
    ],
    consumed_auditor_named_public_assets: consumedNamedAssets,
    auditor_pack_object_type: publicPack.object_type,
    auditor_pack_standard_object_type: publicStandard.object_type,
    expected_replay_command_count: expectedCommands.length,
    commands_verified_from_auditor_pack: commandResults,
    extracted_bundle_contains_git_directory: false,
    extracted_artifact_sha256: extractedArtifactSha256,
    expected_artifact_sha256: publicPack.expected_artifact_sha256,
    private_source_required: false,
    local_repository_required_for_auditor: false,
    git_required_after_extraction: false,
    source_tree_embedded: false,
    film_media_embedded_in_auditor_pack: false,
    network_required_to_acquire_public_assets: true,
    network_runtime_required_after_asset_acquisition: false,
    external_api_used_after_asset_acquisition: false,
    external_media_used_after_asset_acquisition: false,
    manual_media_selection_used: false,
    candidate_selection_used: false,
    proves_external_auditor_pack_publicly_consumed: true,
    proves_auditor_pack_drives_public_replay: true,
    proves_public_assets_named_by_pack_are_hash_verified: true,
    proves_extracted_outsider_replay: true,
    proves_compiler_generated_film: true,
    proves_film_issued: true,
    proves_truth: false,
    proves_admissibility: false,
    proves_external_reality: false
  };

  mkdirSync("CONSUMPTION", { recursive: true });
  writeFileSync(receiptPath, JSON.stringify(receipt, null, 2) + "\n");
  console.log(JSON.stringify(receipt, null, 2));

  rmSync(tmp, { recursive: true, force: true });
} catch (err) {
  errors.push(String(err && err.message ? err.message : err));
  const receipt = {
    object_type: "CINEMATICUM_EXTERNAL_AUDITOR_PACK_CONSUMPTION_RECEIPT",
    schema_version: "1.6.0",
    jurisdiction: "CINEMATICUM",
    valid: false,
    errors,
    proves_truth: false,
    proves_admissibility: false,
    proves_external_reality: false
  };
  console.log(JSON.stringify(receipt, null, 2));
  process.exit(1);
}
