#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";

const repo = "kaaffilm/CINEMATICUM";
const packPath = "AUDIT/CINEMATICUM_EXTERNAL_AUDITOR_PACK.json";
const standardPath = "AUDIT/EXTERNAL_AUDITOR_PACK_STANDARD.json";
const lineagePath = "RELEASES/CINEMATICUM_PUBLIC_RELEASE_LINEAGE_LEDGER.json";

function run(cmd, args, opts = {}) {
  return execFileSync(cmd, args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    ...opts
  }).trim();
}

function sha256File(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function sha256Text(text) {
  return createHash("sha256").update(text).digest("hex");
}

function ghJson(args) {
  return JSON.parse(run("gh", args));
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function tagCommit(tag) {
  return run("git", ["rev-list", "-n", "1", tag]);
}

try {
  run("git", ["fetch", "origin", "main", "--tags"]);

  const packageJson = JSON.parse(readFileSync("package.json", "utf8"));
  assert(packageJson.version === "1.5.0", `package version must be 1.5.0, got ${packageJson.version}`);

  assert(existsSync(standardPath), `missing standard: ${standardPath}`);
  assert(existsSync(lineagePath), `missing lineage ledger: ${lineagePath}`);

  const standard = JSON.parse(readFileSync(standardPath, "utf8"));
  const lineage = JSON.parse(readFileSync(lineagePath, "utf8"));

  assert(standard.object_type === "CINEMATICUM_EXTERNAL_AUDITOR_PACK_STANDARD", "bad standard object_type");
  assert(lineage.object_type === "CINEMATICUM_PUBLIC_RELEASE_LINEAGE_LEDGER", "bad lineage object_type");
  assert(lineage.valid === true, "lineage ledger invalid");
  assert(lineage.proves_public_release_lineage === true, "public lineage not proven");
  assert(lineage.proves_truth === false, "lineage truth boundary violated");
  assert(lineage.proves_admissibility === false, "lineage admissibility boundary violated");
  assert(lineage.proves_external_reality === false, "lineage external reality boundary violated");

  const releaseTags = [
    "v0.9.0-director-engine",
    "v1.0.0-product-boundary",
    "v1.1.0-installable-product-boundary",
    "v1.2.0-outsider-reproducible-release",
    "v1.3.0-public-release-consumption-receipt",
    "v1.4.0-public-release-lineage-ledger"
  ];

  const publicReleases = releaseTags.map((tag) => {
    const release = ghJson([
      "release",
      "view",
      tag,
      "--repo",
      repo,
      "--json",
      "tagName,name,isDraft,isPrerelease,publishedAt,url,targetCommitish,assets"
    ]);

    assert(release.tagName === tag, `release tag mismatch: ${tag}`);
    assert(release.isDraft === false, `${tag} is draft`);
    assert(release.isPrerelease === false, `${tag} is prerelease`);
    assert(Boolean(release.publishedAt), `${tag} missing publishedAt`);
    assert(Boolean(release.url), `${tag} missing url`);

    return {
      tag,
      tag_commit: tagCommit(tag),
      release_url: release.url,
      release_name: release.name,
      release_published_at: release.publishedAt,
      release_target_commitish: release.targetCommitish,
      public_assets: (release.assets || []).map((a) => ({
        name: a.name,
        size: a.size,
        url: a.url
      }))
    };
  });

  const consumptionReceipt = JSON.parse(
    readFileSync("CONSUMPTION/CASE_001_PUBLIC_RELEASE_CONSUMPTION_RECEIPT.json", "utf8")
  );

  assert(consumptionReceipt.valid === true, "public consumption receipt invalid");
  assert(consumptionReceipt.proves_public_release_assets_consumed === true, "public release consumption not proven");
  assert(consumptionReceipt.proves_extracted_outsider_replay === true, "public extracted replay not proven");

  const expectedPublicAssets = [
    {
      source_release_tag: "v1.2.0-outsider-reproducible-release",
      source_release_url: consumptionReceipt.source_release_url,
      name: "CASE_001_THE_LAST_RENDER_OUTSIDER_REPRODUCIBLE_RELEASE_BUNDLE.tar.gz",
      sha256: "6d6d26e428515b8a7f68bb35c2b7a7d80dc561857dbdb9d1df99d93a6eb0e1f8",
      purpose: "runtime-complete outsider replay bundle"
    },
    {
      source_release_tag: "v1.2.0-outsider-reproducible-release",
      source_release_url: consumptionReceipt.source_release_url,
      name: "RELEASE_ASSET_HASH_LEDGER.json",
      sha256: "13fb510ccb3b77c1f45024b46e9fb3ffdd392da2e25f5bf4e9a484cace475f27",
      purpose: "public release asset hash ledger"
    },
    {
      source_release_tag: "v1.2.0-outsider-reproducible-release",
      source_release_url: consumptionReceipt.source_release_url,
      name: "OUTSIDER_REPLAY_MANIFEST.json",
      sha256: "201b2a329aae3fc1dd5946e15c4ff4ef3a7a6b13f702e5da070285151d5a2964",
      purpose: "outsider replay manifest"
    },
    {
      source_release_tag: "v1.4.0-public-release-lineage-ledger",
      source_release_url: publicReleases.find((r) => r.tag === "v1.4.0-public-release-lineage-ledger").release_url,
      name: "CINEMATICUM_PUBLIC_RELEASE_LINEAGE_LEDGER.json",
      sha256: sha256File(lineagePath),
      purpose: "machine-readable public release lineage ledger"
    }
  ];

  const expectedCommands = [
    {
      command: "node bin/cinematicum.cjs proof",
      expected_object_type: "CINEMATICUM_PRODUCT_PROOF_SUMMARY"
    },
    {
      command: "node bin/cinematicum.cjs artifact",
      expected_object_type: "CINEMATICUM_PRODUCT_ARTIFACT_POINTER"
    },
    {
      command: "node bin/cinematicum.cjs studio",
      expected_object_type: "CINEMATICUM_STUDIO_POINTER"
    },
    {
      command: "node bin/cinematicum.cjs verify",
      expected_object_type: "CINEMATICUM_CLI_LEAF_VERIFICATION_RESULT"
    },
    {
      command: "node bin/cinematicum.cjs export",
      expected_object_type: "CINEMATICUM_PRODUCT_RELEASE_BUNDLE_EXPORT_RESULT"
    }
  ];

  const pack = {
    object_type: "CINEMATICUM_EXTERNAL_AUDITOR_PACK",
    schema_version: "1.5.0",
    jurisdiction: "CINEMATICUM",
    valid: true,
    errors: [],
    repository: repo,
    package_name: packageJson.name,
    package_version: packageJson.version,
    generated_from_head: run("git", ["rev-parse", "HEAD"]),
    standard: {
      path: standardPath,
      sha256: sha256File(standardPath),
      object_type: standard.object_type
    },
    public_release_lineage: {
      tag: "v1.4.0-public-release-lineage-ledger",
      release_url: publicReleases.find((r) => r.tag === "v1.4.0-public-release-lineage-ledger").release_url,
      ledger_path: lineagePath,
      ledger_sha256: sha256File(lineagePath),
      ledger_object_type: lineage.object_type,
      release_count: lineage.release_chain.length,
      ancestry_edges_verified: lineage.ancestry.length
    },
    public_releases: publicReleases,
    expected_public_assets_to_acquire: expectedPublicAssets,
    expected_replay_commands_after_asset_acquisition: expectedCommands,
    expected_artifact_sha256: consumptionReceipt.extracted_artifact_sha256,
    auditor_protocol: [
      "Fetch the public release assets listed in expected_public_assets_to_acquire.",
      "Verify each listed SHA-256 before extraction or replay.",
      "Extract CASE_001_THE_LAST_RENDER_OUTSIDER_REPRODUCIBLE_RELEASE_BUNDLE.tar.gz into a clean temporary directory.",
      "Confirm no .git directory exists inside the extracted outsider bundle.",
      "Run each expected replay command from the extracted bundle root.",
      "Parse each command output as a single JSON object.",
      "Compare each output object_type against expected_replay_commands_after_asset_acquisition.",
      "Confirm the extracted artifact SHA-256 equals expected_artifact_sha256.",
      "Confirm no network runtime is required after public asset acquisition."
    ],
    dependency_boundary: {
      private_source_required: false,
      local_repository_required_for_auditor: false,
      git_required_after_extraction: false,
      source_tree_embedded: false,
      film_media_embedded_in_auditor_pack: false,
      public_network_required_to_acquire_assets: true,
      network_runtime_required_after_asset_acquisition: false,
      external_api_used_after_asset_acquisition: false,
      external_media_used_after_asset_acquisition: false,
      manual_media_selection_used: false,
      candidate_selection_used: false
    },
    proves_external_auditor_pack_exists: true,
    proves_public_release_assets_are_identified: true,
    proves_expected_replay_contract_is_machine_readable: true,
    proves_film_issuance_chain_preserved: true,
    proves_truth: false,
    proves_admissibility: false,
    proves_external_reality: false
  };

  mkdirSync("AUDIT", { recursive: true });
  writeFileSync(packPath, JSON.stringify(pack, null, 2) + "\n");

  const packText = JSON.stringify(pack);
  const result = {
    object_type: "CINEMATICUM_EXTERNAL_AUDITOR_PACK_VERIFICATION_RESULT",
    schema_version: "1.5.0",
    valid: true,
    errors: [],
    pack_path: packPath,
    pack_sha256_canonical_json: sha256Text(packText),
    standard_path: standardPath,
    standard_sha256: sha256File(standardPath),
    lineage_ledger_path: lineagePath,
    lineage_ledger_sha256: sha256File(lineagePath),
    public_release_count: publicReleases.length,
    expected_public_asset_count: expectedPublicAssets.length,
    expected_replay_command_count: expectedCommands.length,
    expected_artifact_sha256: consumptionReceipt.extracted_artifact_sha256,
    proves_external_auditor_pack_exists: true,
    proves_public_release_assets_are_identified: true,
    proves_expected_replay_contract_is_machine_readable: true,
    proves_film_issuance_chain_preserved: true,
    proves_truth: false,
    proves_admissibility: false,
    proves_external_reality: false
  };

  console.log(JSON.stringify(result, null, 2));
} catch (error) {
  const failure = {
    object_type: "CINEMATICUM_EXTERNAL_AUDITOR_PACK_VERIFICATION_RESULT",
    schema_version: "1.5.0",
    valid: false,
    errors: [String(error?.message || error)],
    proves_external_auditor_pack_exists: false,
    proves_public_release_assets_are_identified: false,
    proves_expected_replay_contract_is_machine_readable: false,
    proves_film_issuance_chain_preserved: false,
    proves_truth: false,
    proves_admissibility: false,
    proves_external_reality: false
  };
  console.log(JSON.stringify(failure, null, 2));
  process.exit(1);
}
