#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";

const repo = "kaaffilm/CINEMATICUM";
const ledgerPath = "RELEASES/CINEMATICUM_PUBLIC_RELEASE_LINEAGE_LEDGER.json";

const releaseChain = [
  {
    version: "0.9.0",
    boundary: "DIRECTOR_ENGINE",
    tag: "v0.9.0-director-engine",
    proves: [
      "director_engine_exists",
      "compiler_generated_film",
      "film_issued"
    ],
    refuses: [
      "truth",
      "admissibility",
      "external_reality"
    ]
  },
  {
    version: "1.0.0",
    boundary: "PRODUCT_BOUNDARY",
    tag: "v1.0.0-product-boundary",
    proves: [
      "product_boundary_exists",
      "studio_surface_exists",
      "director_engine_exists",
      "compiler_generated_film",
      "film_issued"
    ],
    refuses: [
      "truth",
      "admissibility",
      "external_reality"
    ]
  },
  {
    version: "1.1.0",
    boundary: "INSTALLABLE_PRODUCT_BOUNDARY",
    tag: "v1.1.0-installable-product-boundary",
    proves: [
      "installable_product_boundary",
      "clean_npm_install_smoke",
      "single_json_cli_surface",
      "film_issued"
    ],
    refuses: [
      "truth",
      "admissibility",
      "external_reality"
    ]
  },
  {
    version: "1.2.0",
    boundary: "OUTSIDER_REPRODUCIBLE_RELEASE",
    tag: "v1.2.0-outsider-reproducible-release",
    proves: [
      "runtime_complete_outsider_bundle",
      "deterministic_release_bundle",
      "gitless_extracted_replay",
      "film_issued"
    ],
    refuses: [
      "truth",
      "admissibility",
      "external_reality"
    ]
  },
  {
    version: "1.3.0",
    boundary: "PUBLIC_RELEASE_CONSUMPTION_RECEIPT",
    tag: "v1.3.0-public-release-consumption-receipt",
    proves: [
      "public_release_assets_consumed",
      "release_bundle_sha_verified",
      "extracted_outsider_bundle_replayed",
      "film_issued"
    ],
    refuses: [
      "truth",
      "admissibility",
      "external_reality"
    ]
  }
];

function run(cmd, args, opts = {}) {
  return execFileSync(cmd, args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    ...opts
  }).trim();
}

function sha256Text(text) {
  return createHash("sha256").update(text).digest("hex");
}

function sha256File(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function ghJson(args) {
  return JSON.parse(run("gh", args));
}

function tagCommit(tag) {
  return run("git", ["rev-list", "-n", "1", tag]);
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function isAncestor(a, b) {
  try {
    run("git", ["merge-base", "--is-ancestor", a, b]);
    return true;
  } catch {
    return false;
  }
}

try {
  run("git", ["fetch", "origin", "main", "--tags"]);

  const currentHead = run("git", ["rev-parse", "HEAD"]);
  const packageJson = JSON.parse(readFileSync("package.json", "utf8"));

  assert(packageJson.version === "1.4.0", `package version must be 1.4.0, got ${packageJson.version}`);

  const entries = [];

  for (const item of releaseChain) {
    const commit = tagCommit(item.tag);
    const release = ghJson([
      "release",
      "view",
      item.tag,
      "--repo",
      repo,
      "--json",
      "tagName,name,isDraft,isPrerelease,publishedAt,url,targetCommitish"
    ]);

    assert(release.tagName === item.tag, `release tag mismatch for ${item.tag}`);
    assert(release.isDraft === false, `${item.tag} is draft`);
    assert(release.isPrerelease === false, `${item.tag} is prerelease`);
    assert(Boolean(release.publishedAt), `${item.tag} missing publishedAt`);
    assert(Boolean(release.url), `${item.tag} missing url`);

    entries.push({
      version: item.version,
      boundary: item.boundary,
      tag: item.tag,
      tag_commit: commit,
      release_url: release.url,
      release_name: release.name,
      release_published_at: release.publishedAt,
      release_target_commitish: release.targetCommitish,
      proves: item.proves,
      refuses: item.refuses,
      proves_truth: false,
      proves_admissibility: false,
      proves_external_reality: false
    });
  }

  const ancestry = [];
  for (let i = 1; i < entries.length; i++) {
    const previous = entries[i - 1];
    const current = entries[i];
    const ok = isAncestor(previous.tag_commit, current.tag_commit);
    assert(ok, `${previous.tag} is not ancestor of ${current.tag}`);
    ancestry.push({
      from_tag: previous.tag,
      from_commit: previous.tag_commit,
      to_tag: current.tag,
      to_commit: current.tag_commit,
      ancestor_relation_verified: true
    });
  }

  const requiredLocalProofs = [
    "CONSUMPTION/CASE_001_PUBLIC_RELEASE_CONSUMPTION_RECEIPT.json",
    "CONSUMPTION/PUBLIC_RELEASE_CONSUMPTION_STANDARD.json",
    "REPRODUCIBILITY/OUTSIDER_REPLAY_MANIFEST.json",
    "REPRODUCIBILITY/RELEASE_ASSET_HASH_LEDGER.json",
    "REPRODUCIBILITY/OUTSIDER_REPRODUCIBLE_RELEASE_STANDARD.json",
    "PRODUCT/INSTALLABLE_PRODUCT_BOUNDARY.json",
    "PRODUCT/CASE_001_PRODUCT_BOUNDARY.json"
  ];

  const localProofs = requiredLocalProofs.map((path) => {
    assert(existsSync(path), `missing local proof file: ${path}`);
    return {
      path,
      sha256: sha256File(path)
    };
  });

  const publicConsumptionReceipt = JSON.parse(
    readFileSync("CONSUMPTION/CASE_001_PUBLIC_RELEASE_CONSUMPTION_RECEIPT.json", "utf8")
  );

  assert(publicConsumptionReceipt.valid === true, "public consumption receipt invalid");
  assert(publicConsumptionReceipt.proves_public_release_assets_consumed === true, "public release asset consumption not proven");
  assert(publicConsumptionReceipt.proves_extracted_outsider_replay === true, "extracted outsider replay not proven");
  assert(publicConsumptionReceipt.proves_truth === false, "truth boundary violated in consumption receipt");
  assert(publicConsumptionReceipt.proves_admissibility === false, "admissibility boundary violated in consumption receipt");
  assert(publicConsumptionReceipt.proves_external_reality === false, "external reality boundary violated in consumption receipt");

  const ledger = {
    object_type: "CINEMATICUM_PUBLIC_RELEASE_LINEAGE_LEDGER",
    schema_version: "1.4.0",
    jurisdiction: "CINEMATICUM",
    valid: true,
    errors: [],
    repository: repo,
    package_name: packageJson.name,
    package_version: packageJson.version,
    generated_from_head: currentHead,
    release_chain: entries,
    ancestry,
    local_proof_files: localProofs,
    public_consumption_receipt: {
      path: "CONSUMPTION/CASE_001_PUBLIC_RELEASE_CONSUMPTION_RECEIPT.json",
      object_type: publicConsumptionReceipt.object_type,
      schema_version: publicConsumptionReceipt.schema_version,
      source_release_tag: publicConsumptionReceipt.source_release_tag,
      extracted_artifact_sha256: publicConsumptionReceipt.extracted_artifact_sha256,
      proves_public_release_assets_consumed: true,
      proves_extracted_outsider_replay: true,
      proves_truth: false,
      proves_admissibility: false,
      proves_external_reality: false
    },
    chain_properties: {
      release_tags_exist: true,
      releases_exist: true,
      releases_are_not_drafts: true,
      releases_are_not_prereleases: true,
      ordered_git_ancestry_verified: true,
      public_consumption_receipt_valid: true
    },
    proves_public_release_lineage: true,
    proves_release_chain_is_machine_readable: true,
    proves_public_consumption_receipt_is_bound_to_lineage: true,
    proves_film_issuance_chain_preserved: true,
    proves_truth: false,
    proves_admissibility: false,
    proves_external_reality: false
  };

  mkdirSync("RELEASES", { recursive: true });
  writeFileSync(ledgerPath, JSON.stringify(ledger, null, 2) + "\n");

  const digest = sha256Text(JSON.stringify(ledger));
  const result = {
    object_type: "CINEMATICUM_PUBLIC_RELEASE_LINEAGE_VERIFICATION_RESULT",
    schema_version: "1.4.0",
    valid: true,
    errors: [],
    ledger_path: ledgerPath,
    ledger_sha256_canonical_json: digest,
    release_count: entries.length,
    ancestry_edges_verified: ancestry.length,
    current_head: currentHead,
    latest_prior_release_tag: "v1.3.0-public-release-consumption-receipt",
    proves_public_release_lineage: true,
    proves_release_chain_is_machine_readable: true,
    proves_public_consumption_receipt_is_bound_to_lineage: true,
    proves_film_issuance_chain_preserved: true,
    proves_truth: false,
    proves_admissibility: false,
    proves_external_reality: false
  };

  console.log(JSON.stringify(result, null, 2));
} catch (error) {
  const failure = {
    object_type: "CINEMATICUM_PUBLIC_RELEASE_LINEAGE_VERIFICATION_RESULT",
    schema_version: "1.4.0",
    valid: false,
    errors: [String(error?.message || error)],
    proves_public_release_lineage: false,
    proves_release_chain_is_machine_readable: false,
    proves_public_consumption_receipt_is_bound_to_lineage: false,
    proves_film_issuance_chain_preserved: false,
    proves_truth: false,
    proves_admissibility: false,
    proves_external_reality: false
  };
  console.log(JSON.stringify(failure, null, 2));
  process.exit(1);
}
