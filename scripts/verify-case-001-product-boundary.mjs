#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { spawnSync, execFileSync } from "node:child_process";

const root = process.cwd();

function sha256(file) {
  return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

function assert(condition, message) {
  if (!condition) {
    console.error(`CINEMATICUM_PRODUCT_BOUNDARY_REJECTED: ${message}`);
    process.exit(1);
  }
}

function runNode(args) {
  const r = spawnSync("node", args, { cwd: root, stdio: "inherit" });
  assert(r.status === 0, `command failed: node ${args.join(" ")}`);
}

const pkgPath = path.join(root, "package.json");
assert(fs.existsSync(pkgPath), "package.json missing");

const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf8"));
assert(pkg.bin && pkg.bin.cinematicum === "bin/cinematicum.cjs", "package bin.cinematicum is not locked to bin/cinematicum.cjs");

const binPath = path.join(root, "bin/cinematicum.cjs");
assert(fs.existsSync(binPath), "cinematicum CLI missing");
assert((fs.statSync(binPath).mode & 0o111) !== 0, "cinematicum CLI is not executable");

const firstLine = fs.readFileSync(binPath, "utf8").split(/\r?\n/)[0];
assert(firstLine === "#!/usr/bin/env node", "cinematicum CLI shebang missing");

runNode(["bin/cinematicum.cjs", "verify"]);
runNode(["bin/cinematicum.cjs", "proof"]);
runNode(["bin/cinematicum.cjs", "artifact"]);

const exportText = execFileSync("node", ["scripts/export-case-001-release-bundle.mjs"], { cwd: root, encoding: "utf8" });
const exportResult = JSON.parse(exportText);

assert(exportResult.valid === true, "release bundle export did not validate");
assert(fs.existsSync(path.join(root, exportResult.bundle_tar)), "release bundle tar missing");
assert(sha256(path.join(root, exportResult.bundle_tar)) === exportResult.bundle_tar_sha256, "release bundle tar hash mismatch");

const rawTracked = spawnSync("git", ["ls-files"], { cwd: root, encoding: "utf8" })
  .stdout
  .split(/\r?\n/)
  .filter(Boolean)
  .filter(x => x.includes("/frames/") || x.endsWith(".ppm"));

assert(rawTracked.length === 0, "raw frames are tracked");

const proof = JSON.parse(execFileSync("node", ["bin/cinematicum.cjs", "proof"], { cwd: root, encoding: "utf8" }));
assert(proof.proves_compiler_generated_film === true, "compiler-generated film proof missing");
assert(proof.proves_film_issued === true, "film issuance proof missing");
assert(proof.proves_truth === false, "truth overclaim detected");
assert(proof.proves_admissibility === false, "admissibility overclaim detected");
assert(proof.proves_external_reality === false, "external reality overclaim detected");

console.log(JSON.stringify({
  object_type: "CINEMATICUM_PRODUCT_BOUNDARY_VERIFICATION_RESULT",
  schema_version: "1.0.0",
  valid: true,
  errors: [],
  cli: "bin/cinematicum.cjs",
  commands_verified: [
    "cinematicum verify",
    "cinematicum proof",
    "cinematicum artifact",
    "cinematicum export"
  ],
  bundle_tar: exportResult.bundle_tar,
  bundle_tar_sha256: exportResult.bundle_tar_sha256,
  bundle_tar_size_bytes: exportResult.bundle_tar_size_bytes,
  product_boundary_exists: true,
  release_bundle_exists: true,
  proves_director_engine_exists: true,
  proves_studio_surface_exists: true,
  proves_compiler_generated_film: true,
  proves_film_issued: true,
  proves_truth: false,
  proves_admissibility: false,
  proves_external_reality: false
}, null, 2));
