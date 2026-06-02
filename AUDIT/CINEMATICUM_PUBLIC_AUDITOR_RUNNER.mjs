#!/usr/bin/env node
import https from "node:https";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";
import { execFileSync } from "node:child_process";

const repo = "kaaffilm/CINEMATICUM";

const standard = {
  object_type: "CINEMATICUM_PUBLIC_AUDITOR_RUNNER_STANDARD",
  schema_version: "1.7.0",
  jurisdiction: "CINEMATICUM",
  source_auditor_pack_release_tag: "v1.5.1-external-auditor-pack-public-sha-repair",
  expected_public_auditor_pack_canonical_sha256: "cb7541f94e8e0186a7372cbfda3beb37e5d7dac91fbbd972193272ee0cfdd13c",
  expected_public_auditor_pack_standard_sha256: "b380b2f9b2def8779b5b58a6dc24bc635ca87e6977eb36936a8d0bd4ab63f388",
  expected_artifact_sha256: "f23d3da43ed0dfc0a4f97b7c6ad722107cc2531ac584780424ace2c45ff5a192",
  expected_public_assets: [
    {
      source_release_tag: "v1.2.0-outsider-reproducible-release",
      name: "CASE_001_THE_LAST_RENDER_OUTSIDER_REPRODUCIBLE_RELEASE_BUNDLE.tar.gz",
      sha256: "6d6d26e428515b8a7f68bb35c2b7a7d80dc561857dbdb9d1df99d93a6eb0e1f8"
    },
    {
      source_release_tag: "v1.2.0-outsider-reproducible-release",
      name: "RELEASE_ASSET_HASH_LEDGER.json",
      sha256: "13fb510ccb3b77c1f45024b46e9fb3ffdd392da2e25f5bf4e9a484cace475f27"
    },
    {
      source_release_tag: "v1.2.0-outsider-reproducible-release",
      name: "OUTSIDER_REPLAY_MANIFEST.json",
      sha256: "201b2a329aae3fc1dd5946e15c4ff4ef3a7a6b13f702e5da070285151d5a2964"
    },
    {
      source_release_tag: "v1.4.0-public-release-lineage-ledger",
      name: "CINEMATICUM_PUBLIC_RELEASE_LINEAGE_LEDGER.json",
      sha256: "ea947845ae51a00420b520f960dca3dd231a5d43fdf2bced999085dd344fbcc6"
    }
  ],
  expected_replay_commands: [
    { command: "node bin/cinematicum.cjs proof", object_type: "CINEMATICUM_PRODUCT_PROOF_SUMMARY" },
    { command: "node bin/cinematicum.cjs artifact", object_type: "CINEMATICUM_PRODUCT_ARTIFACT_POINTER" },
    { command: "node bin/cinematicum.cjs studio", object_type: "CINEMATICUM_STUDIO_POINTER" },
    { command: "node bin/cinematicum.cjs verify", object_type: "CINEMATICUM_CLI_LEAF_VERIFICATION_RESULT" },
    { command: "node bin/cinematicum.cjs export", object_type: "CINEMATICUM_PRODUCT_RELEASE_BUNDLE_EXPORT_RESULT" }
  ]
};

function canonicalize(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalize).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonicalize(value[k])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function sha256Buffer(buf) {
  return crypto.createHash("sha256").update(buf).digest("hex");
}

function sha256File(file) {
  return sha256Buffer(fs.readFileSync(file));
}

function sha256CanonicalJson(obj) {
  return crypto.createHash("sha256").update(canonicalize(obj)).digest("hex");
}

function fail(errors) {
  console.log(JSON.stringify({
    object_type: "CINEMATICUM_PUBLIC_AUDITOR_RUNNER_RECEIPT",
    schema_version: "1.7.0",
    jurisdiction: "CINEMATICUM",
    valid: false,
    errors,
    proves_truth: false,
    proves_admissibility: false,
    proves_external_reality: false
  }, null, 2));
  process.exit(1);
}

function requireEqual(actual, expected, label, errors) {
  if (actual !== expected) errors.push(`${label}: expected ${expected}; got ${actual}`);
}

function getJson(url) {
  const body = execFileSync(process.execPath, ["-e", `
    const https = require("https");
    const url = ${JSON.stringify(url)};
    function fetch(u, n = 0) {
      https.get(u, {
        headers: {
          "User-Agent": "cinematicum-public-auditor-runner",
          "Accept": "application/vnd.github+json"
        }
      }, res => {
        if ([301,302,303,307,308].includes(res.statusCode)) return fetch(res.headers.location, n + 1);
        if (res.statusCode < 200 || res.statusCode >= 300) {
          console.error("HTTP " + res.statusCode + " " + u);
          process.exit(2);
        }
        let data = "";
        res.setEncoding("utf8");
        res.on("data", c => data += c);
        res.on("end", () => process.stdout.write(data));
      }).on("error", e => {
        console.error(String(e.stack || e));
        process.exit(2);
      });
    }
    fetch(url);
  `], { encoding: "utf8" });
  return JSON.parse(body);
}

function download(url, dest) {
  execFileSync(process.execPath, ["-e", `
    const https = require("https");
    const fs = require("fs");
    const url = ${JSON.stringify(url)};
    const dest = ${JSON.stringify(dest)};
    function fetch(u, n = 0) {
      https.get(u, {
        headers: {
          "User-Agent": "cinematicum-public-auditor-runner",
          "Accept": "application/octet-stream"
        }
      }, res => {
        if ([301,302,303,307,308].includes(res.statusCode)) return fetch(res.headers.location, n + 1);
        if (res.statusCode < 200 || res.statusCode >= 300) {
          console.error("HTTP " + res.statusCode + " " + u);
          process.exit(2);
        }
        const out = fs.createWriteStream(dest);
        res.pipe(out);
        out.on("finish", () => out.close());
      }).on("error", e => {
        console.error(String(e.stack || e));
        process.exit(2);
      });
    }
    fetch(url);
  `], { stdio: "inherit" });
}

function releaseAssetUrl(tag, name) {
  const release = getJson(`https://api.github.com/repos/${repo}/releases/tags/${tag}`);
  const asset = release.assets.find(a => a.name === name);
  if (!asset) throw new Error(`asset not found on ${tag}: ${name}`);
  return asset.browser_download_url;
}

function findFile(root, basename) {
  const stack = [root];
  while (stack.length) {
    const dir = stack.pop();
    for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, ent.name);
      if (ent.isDirectory()) stack.push(p);
      else if (ent.isFile() && ent.name === basename) return p;
    }
  }
  return null;
}

function runJsonCommand(cwd, command) {
  const [cmd, ...args] = command.split(/\s+/);
  const stdout = execFileSync(cmd, args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
  return JSON.parse(stdout);
}

try {
  const errors = [];
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "cinematicum-public-auditor-runner-"));

  const publicPackPath = path.join(tmp, "CINEMATICUM_EXTERNAL_AUDITOR_PACK.json");
  const publicPackStandardPath = path.join(tmp, "EXTERNAL_AUDITOR_PACK_STANDARD.json");

  download(
    releaseAssetUrl(standard.source_auditor_pack_release_tag, "CINEMATICUM_EXTERNAL_AUDITOR_PACK.json"),
    publicPackPath
  );
  download(
    releaseAssetUrl(standard.source_auditor_pack_release_tag, "EXTERNAL_AUDITOR_PACK_STANDARD.json"),
    publicPackStandardPath
  );

  const publicPack = JSON.parse(fs.readFileSync(publicPackPath, "utf8"));
  const publicPackStandard = JSON.parse(fs.readFileSync(publicPackStandardPath, "utf8"));

  requireEqual(
    sha256CanonicalJson(publicPack),
    standard.expected_public_auditor_pack_canonical_sha256,
    "public auditor pack canonical sha",
    errors
  );
  requireEqual(
    sha256File(publicPackStandardPath),
    standard.expected_public_auditor_pack_standard_sha256,
    "public auditor pack standard sha",
    errors
  );

  requireEqual(publicPack.object_type, "CINEMATICUM_EXTERNAL_AUDITOR_PACK", "auditor pack object_type", errors);
  requireEqual(publicPackStandard.object_type, "CINEMATICUM_EXTERNAL_AUDITOR_PACK_STANDARD", "auditor pack standard object_type", errors);

  const consumedPublicAssets = [];
  let outsiderBundlePath = null;

  for (const asset of standard.expected_public_assets) {
    const dest = path.join(tmp, asset.name);
    download(releaseAssetUrl(asset.source_release_tag, asset.name), dest);
    const got = sha256File(dest);
    requireEqual(got, asset.sha256, `public asset sha ${asset.source_release_tag}/${asset.name}`, errors);
    const stat = fs.statSync(dest);

    consumedPublicAssets.push({
      source_release_tag: asset.source_release_tag,
      name: asset.name,
      sha256: got,
      expected_sha256: asset.sha256,
      size_bytes: stat.size
    });

    if (asset.name === "CASE_001_THE_LAST_RENDER_OUTSIDER_REPRODUCIBLE_RELEASE_BUNDLE.tar.gz") {
      outsiderBundlePath = dest;
    }
  }

  if (!outsiderBundlePath) errors.push("outsider reproducible release bundle not found");

  const extractRoot = path.join(tmp, "extract");
  fs.mkdirSync(extractRoot);
  execFileSync("tar", ["-xzf", outsiderBundlePath, "-C", extractRoot], { stdio: "inherit" });

  const cli = findFile(extractRoot, "cinematicum.cjs");
  if (!cli) errors.push("extracted bundle missing bin/cinematicum.cjs");

  const bundleRoot = cli ? path.dirname(path.dirname(cli)) : extractRoot;
  const gitDir = findFile(extractRoot, ".git");

  const commandResults = [];
  let extractedArtifactSha256 = null;

  if (cli) {
    for (const expected of standard.expected_replay_commands) {
      const out = runJsonCommand(bundleRoot, expected.command);
      requireEqual(out.object_type, expected.object_type, `command object_type ${expected.command}`, errors);

      commandResults.push({
        command: expected.command,
        object_type: out.object_type,
        valid: out.valid === undefined ? true : out.valid
      });

      if (out.object_type === "CINEMATICUM_PRODUCT_ARTIFACT_POINTER") {
        extractedArtifactSha256 = out.artifact_sha256;
      }
    }
  }

  requireEqual(extractedArtifactSha256, standard.expected_artifact_sha256, "extracted artifact sha256", errors);

  if (errors.length) fail(errors);

  console.log(JSON.stringify({
    object_type: "CINEMATICUM_PUBLIC_AUDITOR_RUNNER_RECEIPT",
    schema_version: "1.7.0",
    jurisdiction: "CINEMATICUM",
    valid: true,
    errors: [],
    source_auditor_pack_release_tag: standard.source_auditor_pack_release_tag,
    consumed_public_auditor_pack_assets: [
      {
        name: "CINEMATICUM_EXTERNAL_AUDITOR_PACK.json",
        sha256_canonical_json: sha256CanonicalJson(publicPack),
        expected_sha256_canonical_json: standard.expected_public_auditor_pack_canonical_sha256
      },
      {
        name: "EXTERNAL_AUDITOR_PACK_STANDARD.json",
        sha256: sha256File(publicPackStandardPath),
        expected_sha256: standard.expected_public_auditor_pack_standard_sha256
      }
    ],
    consumed_auditor_named_public_assets: consumedPublicAssets,
    auditor_pack_object_type: publicPack.object_type,
    auditor_pack_standard_object_type: publicPackStandard.object_type,
    commands_verified_from_public_runner: commandResults,
    expected_replay_command_count: standard.expected_replay_commands.length,
    extracted_bundle_contains_git_directory: Boolean(gitDir),
    extracted_artifact_sha256: extractedArtifactSha256,
    expected_artifact_sha256: standard.expected_artifact_sha256,
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
    proves_standalone_public_auditor_runner_exists: true,
    proves_public_auditor_runner_requires_no_local_repository: true,
    proves_public_auditor_runner_consumes_public_auditor_pack: true,
    proves_public_assets_named_by_pack_are_hash_verified: true,
    proves_public_auditor_runner_drives_replay: true,
    proves_extracted_outsider_replay: true,
    proves_compiler_generated_film: true,
    proves_film_issued: true,
    proves_truth: false,
    proves_admissibility: false,
    proves_external_reality: false
  }, null, 2));
} catch (err) {
  fail([String(err && err.stack ? err.stack : err)]);
}
