#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import zlib from "node:zlib";

const CASE_ID = "CASE_001_THE_LAST_RENDER";
const DIST = "dist";
const BUNDLE_NAME = `${CASE_ID}_OUTSIDER_REPRODUCIBLE_RELEASE_BUNDLE`;
const BUNDLE_DIR = path.join(DIST, BUNDLE_NAME);
const BUNDLE_TAR = path.join(DIST, `${BUNDLE_NAME}.tar.gz`);
const LEDGER_PATH = "REPRODUCIBILITY/RELEASE_ASSET_HASH_LEDGER.json";
const OUTSIDER_MANIFEST_PATH = "REPRODUCIBILITY/OUTSIDER_REPLAY_MANIFEST.json";

const CANONICAL_ARTIFACT = "CASES/CASE_001_THE_LAST_RENDER/FILM/CASE_001_THE_LAST_RENDER_GODCUT_0001.mp4";
const CANONICAL_ARTIFACT_SHA256 = "f23d3da43ed0dfc0a4f97b7c6ad722107cc2531ac584780424ace2c45ff5a192";

const requiredCliRuntimeScripts = [
  "scripts/verify-case-001-godcut.mjs",
  "scripts/verify-case-001-godstudio.mjs",
  "scripts/verify-case-001-director-engine.mjs",
  "scripts/export-case-001-release-bundle.mjs"
];

const include = [
  "README.md",
  "LICENSE",
  "package.json",
  "bin/cinematicum",
  "bin/cinematicum.cjs",

  "PRODUCT/CASE_001_PRODUCT_BOUNDARY.json",
  "PRODUCT/INSTALLABLE_PRODUCT_BOUNDARY.json",

  "REPRODUCIBILITY/OUTSIDER_REPRODUCIBLE_RELEASE_STANDARD.json",

  "STUDIO/CASE_001_GODCUT/index.html",
  "STUDIO/CASE_001_GODCUT/studio-manifest.json",

  "ENGINES/GODCUT/GODCUT_ENGINE_STANDARD.json",
  "ENGINES/DIRECTOR/DIRECTOR_ENGINE_STANDARD.json",

  "CASES/CASE_001_THE_LAST_RENDER/FILM/CASE_001_THE_LAST_RENDER_GODCUT_0001.mp4",
  "CASES/CASE_001_THE_LAST_RENDER/FILM/GODCUT_0001_MANIFEST.json",
  "CASES/CASE_001_THE_LAST_RENDER/FILM/GODCUT_0001_TIMELINE.json",

  "CASES/CASE_001_THE_LAST_RENDER/PROOFS/godcut-compile-result.json",
  "CASES/CASE_001_THE_LAST_RENDER/PROOFS/godcut-verification-result.json",
  "CASES/CASE_001_THE_LAST_RENDER/PROOFS/director-engine-build-result.json",

  "CASES/CASE_001_THE_LAST_RENDER/DIRECTION/DIRECTOR_ENGINE_MANIFEST.json",
  "CASES/CASE_001_THE_LAST_RENDER/DIRECTION/DIRECTORIAL_PRINCIPLES.json",
  "CASES/CASE_001_THE_LAST_RENDER/DIRECTION/SHOT_GRAMMAR.json",
  "CASES/CASE_001_THE_LAST_RENDER/DIRECTION/CAMERA_LAW.json",
  "CASES/CASE_001_THE_LAST_RENDER/DIRECTION/CUT_RHYTHM_LAW.json",
  "CASES/CASE_001_THE_LAST_RENDER/DIRECTION/SCORE_LAW.json",
  "CASES/CASE_001_THE_LAST_RENDER/DIRECTION/DIRECTOR_DECISION_GRAPH.json",
  ...requiredCliRuntimeScripts
];

function sha256File(p) {
  return crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex");
}

function sha256Buf(b) {
  return crypto.createHash("sha256").update(b).digest("hex");
}

function mkdirp(p) {
  fs.mkdirSync(p, { recursive: true });
}

function rmrf(p) {
  fs.rmSync(p, { recursive: true, force: true });
}

function jsonStable(obj) {
  return JSON.stringify(obj, null, 2) + "\n";
}

function copyBundleFiles() {
  rmrf(BUNDLE_DIR);
  mkdirp(BUNDLE_DIR);

  const entries = [];

  for (const rel of include) {
    if (!fs.existsSync(rel)) throw new Error(`missing required bundle input: ${rel}`);
    const out = path.join(BUNDLE_DIR, rel);
    mkdirp(path.dirname(out));
    fs.copyFileSync(rel, out);
    const st = fs.statSync(rel);
    fs.chmodSync(out, rel.startsWith("bin/") ? 0o755 : 0o644);
    entries.push({
      path: rel,
      size_bytes: st.size,
      sha256: sha256File(rel),
      executable: rel.startsWith("bin/")
    });
  }

  const artifactHash = sha256File(CANONICAL_ARTIFACT);
  if (artifactHash !== CANONICAL_ARTIFACT_SHA256) {
    throw new Error(`canonical artifact hash mismatch: ${artifactHash}`);
  }

  const outsiderManifest = {
    object_type: "CINEMATICUM_OUTSIDER_REPLAY_MANIFEST",
    schema_version: "1.2.0",
    case_id: CASE_ID,
    deterministic: true,
    generated_at: "1970-01-01T00:00:00.000Z",
    bundle_name: BUNDLE_NAME,
    canonical_artifact_path: CANONICAL_ARTIFACT,
    canonical_artifact_sha256: CANONICAL_ARTIFACT_SHA256,
    runtime_requirements: {
      node: true,
      git_required: false,
      network_runtime_required: false,
      external_api_used: false,
      external_media_used: false,
      manual_media_selection_used: false,
      candidate_selection_used: false
    },
    commands_expected_single_json: [
      "cinematicum proof",
      "cinematicum artifact",
      "cinematicum studio",
      "cinematicum verify",
      "cinematicum export"
    ],
    entries
  };

  const manifestRel = "OUTSIDER_REPLAY_MANIFEST.json";
  const manifestInBundle = path.join(BUNDLE_DIR, manifestRel);
  fs.writeFileSync(manifestInBundle, jsonStable(outsiderManifest));
  fs.writeFileSync(OUTSIDER_MANIFEST_PATH, jsonStable(outsiderManifest));

  return { entries, outsiderManifest, manifestInBundle };
}

function splitTarPath(name) {
  const buf = Buffer.from(name);
  if (buf.length <= 100) return { name, prefix: "" };

  const parts = name.split("/");
  for (let i = 1; i < parts.length; i++) {
    const prefix = parts.slice(0, i).join("/");
    const base = parts.slice(i).join("/");
    if (Buffer.from(prefix).length <= 155 && Buffer.from(base).length <= 100) {
      return { name: base, prefix };
    }
  }
  throw new Error(`tar path too long for ustar: ${name}`);
}

function writeString(buf, offset, size, value) {
  const b = Buffer.from(value);
  if (b.length > size) throw new Error(`field too long: ${value}`);
  b.copy(buf, offset);
}

function writeOctal(buf, offset, size, value) {
  const s = value.toString(8).padStart(size - 1, "0").slice(-(size - 1)) + "\0";
  writeString(buf, offset, size, s);
}

function tarHeader(name, size, mode, typeflag) {
  const h = Buffer.alloc(512, 0);
  const sp = splitTarPath(name);

  writeString(h, 0, 100, sp.name);
  writeOctal(h, 100, 8, mode);
  writeOctal(h, 108, 8, 0);
  writeOctal(h, 116, 8, 0);
  writeOctal(h, 124, 12, size);
  writeOctal(h, 136, 12, 0);

  for (let i = 148; i < 156; i++) h[i] = 0x20;

  writeString(h, 156, 1, typeflag);
  writeString(h, 257, 6, "ustar");
  writeString(h, 263, 2, "00");
  writeString(h, 345, 155, sp.prefix);

  let sum = 0;
  for (const byte of h) sum += byte;

  const checksum = sum.toString(8).padStart(6, "0");
  writeString(h, 148, 6, checksum);
  h[154] = 0;
  h[155] = 0x20;

  return h;
}

function pad512(size) {
  const rem = size % 512;
  return rem === 0 ? Buffer.alloc(0) : Buffer.alloc(512 - rem);
}

function makeTarGz(rootDir, outTar) {
  const files = [];

  function walk(abs, rel) {
    const items = fs.readdirSync(abs, { withFileTypes: true })
      .sort((a, b) => a.name.localeCompare(b.name));
    for (const item of items) {
      const childAbs = path.join(abs, item.name);
      const childRel = path.posix.join(rel, item.name);
      if (item.isDirectory()) walk(childAbs, childRel);
      else if (item.isFile()) files.push({ abs: childAbs, rel: childRel });
      else throw new Error(`unsupported filesystem entry: ${childRel}`);
    }
  }

  walk(rootDir, BUNDLE_NAME);

  const chunks = [];

  const dirs = new Set();
  for (const f of files) {
    const parts = f.rel.split("/");
    for (let i = 1; i < parts.length; i++) {
      dirs.add(parts.slice(0, i).join("/") + "/");
    }
  }

  for (const d of [...dirs].sort()) {
    chunks.push(tarHeader(d, 0, 0o755, "5"));
  }

  for (const f of files.sort((a, b) => a.rel.localeCompare(b.rel))) {
    const data = fs.readFileSync(f.abs);
    const mode = f.rel.includes("/bin/") ? 0o755 : 0o644;
    chunks.push(tarHeader(f.rel, data.length, mode, "0"));
    chunks.push(data);
    chunks.push(pad512(data.length));
  }

  chunks.push(Buffer.alloc(1024, 0));
  const tar = Buffer.concat(chunks);
  const gz = zlib.gzipSync(tar, { level: 9 });
  gz[4] = 0; gz[5] = 0; gz[6] = 0; gz[7] = 0;
  gz[9] = 255;

  mkdirp(path.dirname(outTar));
  fs.writeFileSync(outTar, gz);
  return {
    tar_sha256: sha256Buf(gz),
    tar_size_bytes: gz.length
  };
}

mkdirp(DIST);
mkdirp("REPRODUCIBILITY");

const { outsiderManifest, manifestInBundle } = copyBundleFiles();
const tarInfo = makeTarGz(BUNDLE_DIR, BUNDLE_TAR);

const ledger = {
  object_type: "CINEMATICUM_RELEASE_ASSET_HASH_LEDGER",
  schema_version: "1.2.0",
  case_id: CASE_ID,
  deterministic: true,
  generated_at: "1970-01-01T00:00:00.000Z",
  release_bundle: BUNDLE_TAR,
  release_bundle_sha256: tarInfo.tar_sha256,
  release_bundle_size_bytes: tarInfo.tar_size_bytes,
  outsider_replay_manifest: OUTSIDER_MANIFEST_PATH,
  outsider_replay_manifest_sha256: sha256File(OUTSIDER_MANIFEST_PATH),
  bundle_embedded_manifest_sha256: sha256File(manifestInBundle),
  canonical_artifact_path: CANONICAL_ARTIFACT,
  canonical_artifact_sha256: CANONICAL_ARTIFACT_SHA256,
  proves_outsider_reproducible_release: true,
  proves_film_issued: true,
  proves_truth: false,
  proves_admissibility: false,
  proves_external_reality: false
};

fs.writeFileSync(LEDGER_PATH, jsonStable(ledger));

console.log(jsonStable({
  object_type: "CINEMATICUM_DETERMINISTIC_RELEASE_BUNDLE_EXPORT_RESULT",
  schema_version: "1.2.0",
  valid: true,
  errors: [],
  bundle_dir: BUNDLE_DIR,
  bundle_tar: BUNDLE_TAR,
  bundle_tar_sha256: tarInfo.tar_sha256,
  bundle_tar_size_bytes: tarInfo.tar_size_bytes,
  release_asset_hash_ledger: LEDGER_PATH,
  release_asset_hash_ledger_sha256: sha256File(LEDGER_PATH),
  outsider_replay_manifest: OUTSIDER_MANIFEST_PATH,
  outsider_replay_manifest_sha256: sha256File(OUTSIDER_MANIFEST_PATH),
  canonical_artifact_sha256: CANONICAL_ARTIFACT_SHA256,
  entries: outsiderManifest.entries.length,
  deterministic: true,
  proves_outsider_reproducible_release: true,
  proves_film_issued: true,
  proves_truth: false,
  proves_admissibility: false,
  proves_external_reality: false
}));
