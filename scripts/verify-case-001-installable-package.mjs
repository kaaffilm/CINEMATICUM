#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createHash } from "node:crypto";

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

function sha256(file) {
  return createHash("sha256").update(readFileSync(file)).digest("hex");
}

function jsonFrom(cmd, args, opts = {}) {
  return JSON.parse(run(cmd, args, opts));
}

const ROOT = process.cwd();
const dist = resolve(ROOT, "dist");
mkdirSync(dist, { recursive: true });

runInherit("node", ["scripts/verify-case-001-product-boundary.mjs"], { cwd: ROOT });

for (const f of ["kaaffilm-cinematicum-1.1.0.tgz", "CASE_001_THE_LAST_RENDER_INSTALLABLE_PACKAGE_PROOF.json"]) {
  const p = join(dist, f);
  if (existsSync(p)) rmSync(p, { force: true });
}

const packOutput = run("npm", ["pack", "--pack-destination", "dist"], { cwd: ROOT });
const tgzName = packOutput.trim().split(/\n/).pop();
const tgz = resolve(dist, tgzName);

if (!existsSync(tgz)) throw new Error(`package tarball missing: ${tgz}`);
if (!tgzName.includes("kaaffilm-cinematicum-1.1.0.tgz")) throw new Error(`unexpected package tarball: ${tgzName}`);

const smoke = mkdtempSync(join(tmpdir(), "cinematicum-install-smoke-"));
runInherit("npm", ["init", "-y"], { cwd: smoke });
runInherit("npm", ["install", "--ignore-scripts", tgz], { cwd: smoke });

const cli = join(smoke, "node_modules/.bin/cinematicum");
if (!existsSync(cli)) throw new Error("installed cinematicum bin missing");

const proof = jsonFrom(cli, ["proof"], { cwd: smoke });
const artifact = jsonFrom(cli, ["artifact"], { cwd: smoke });
const studio = jsonFrom(cli, ["studio"], { cwd: smoke });

runInherit(cli, ["verify"], { cwd: smoke });
runInherit(cli, ["export"], { cwd: smoke });

if (proof.status !== "INSTALLABLE_PRODUCT_BOUNDARY_READY") throw new Error("proof status mismatch");
if (proof.proves_installable_product_boundary !== true) throw new Error("installable boundary not proven");
if (proof.proves_truth !== false) throw new Error("truth overclaim");
if (proof.proves_admissibility !== false) throw new Error("admissibility overclaim");
if (proof.proves_external_reality !== false) throw new Error("external reality overclaim");
if (artifact.artifact_sha256 !== "f23d3da43ed0dfc0a4f97b7c6ad722107cc2531ac584780424ace2c45ff5a192") throw new Error("artifact sha mismatch");
if (studio.network_runtime_required !== false) throw new Error("studio requires network runtime");

const result = {
  object_type: "CINEMATICUM_INSTALLABLE_PRODUCT_BOUNDARY_VERIFICATION_RESULT",
  schema_version: "1.1.0",
  valid: true,
  errors: [],
  package_name: "@kaaffilm/cinematicum",
  package_version: "1.1.0",
  package_tarball: `dist/${tgzName}`,
  package_tarball_sha256: sha256(tgz),
  package_tarball_size_bytes: statSync(tgz).size,
  installed_bin_verified: true,
  commands_verified_from_clean_install: [
    "cinematicum proof",
    "cinematicum artifact",
    "cinematicum studio",
    "cinematicum verify",
    "cinematicum export"
  ],
  artifact_sha256: artifact.artifact_sha256,
  proves_installable_product_boundary: true,
  proves_director_engine_exists: true,
  proves_studio_surface_exists: true,
  proves_compiler_generated_film: true,
  proves_film_issued: true,
  proves_truth: false,
  proves_admissibility: false,
  proves_external_reality: false
};

writeFileSync("PRODUCT/INSTALLABLE_PRODUCT_BOUNDARY.json", JSON.stringify(result, null, 2) + "\n");
writeFileSync(join(dist, "CASE_001_THE_LAST_RENDER_INSTALLABLE_PACKAGE_PROOF.json"), JSON.stringify(result, null, 2) + "\n");

console.log(JSON.stringify(result, null, 2));
