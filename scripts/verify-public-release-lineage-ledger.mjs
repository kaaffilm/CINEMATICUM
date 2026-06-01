#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";

const repo = "kaaffilm/CINEMATICUM";
const ledgerPath = "RELEASES/CINEMATICUM_PUBLIC_RELEASE_LINEAGE_LEDGER.json";

function run(cmd, args, opts = {}) {
  return execFileSync(cmd, args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    ...opts
  }).trim();
}

function ghJson(args) {
  return JSON.parse(run("gh", args));
}

function sha256Text(text) {
  return createHash("sha256").update(text).digest("hex");
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function tagCommit(tag) {
  return run("git", ["rev-list", "-n", "1", tag]);
}

function isAncestor(a, b) {
  try {
    execFileSync("git", ["merge-base", "--is-ancestor", a, b], {
      stdio: ["ignore", "ignore", "ignore"]
    });
    return true;
  } catch {
    return false;
  }
}

function tagFromEntry(entry) {
  if (typeof entry === "string") return entry;
  return entry.tag || entry.release_tag || entry.tagName || entry.name;
}

try {
  assert(existsSync(ledgerPath), `missing lineage ledger: ${ledgerPath}`);

  run("git", ["fetch", "origin", "main", "--tags"]);

  const ledgerRaw = readFileSync(ledgerPath, "utf8");
  const ledger = JSON.parse(ledgerRaw);

  assert(ledger.object_type === "CINEMATICUM_PUBLIC_RELEASE_LINEAGE_LEDGER", "bad ledger object_type");
  assert(ledger.valid === true, "ledger valid must be true");
  assert(ledger.proves_public_release_lineage === true, "ledger does not prove public release lineage");
  assert(ledger.proves_release_chain_is_machine_readable === true, "ledger release chain is not machine-readable");
  assert(ledger.proves_public_consumption_receipt_is_bound_to_lineage === true, "public consumption receipt not bound to lineage");
  assert(ledger.proves_film_issuance_chain_preserved === true, "film issuance chain not preserved");
  assert(ledger.proves_truth === false, "truth boundary violated");
  assert(ledger.proves_admissibility === false, "admissibility boundary violated");
  assert(ledger.proves_external_reality === false, "external reality boundary violated");

  const releaseChain = Array.isArray(ledger.release_chain) ? ledger.release_chain : [];
  assert(releaseChain.length >= 5, `release_chain too short: ${releaseChain.length}`);

  const releaseTags = releaseChain.map(tagFromEntry).filter(Boolean);
  assert(releaseTags.length === releaseChain.length, "could not resolve all release tags from ledger");

  const releaseRecords = releaseTags.map((tag) => {
    const release = ghJson([
      "release",
      "view",
      tag,
      "--repo",
      repo,
      "--json",
      "tagName,name,isDraft,isPrerelease,publishedAt,url,targetCommitish"
    ]);

    assert(release.tagName === tag, `GitHub release tag mismatch for ${tag}`);
    assert(release.isDraft === false, `${tag} is draft`);
    assert(release.isPrerelease === false, `${tag} is prerelease`);
    assert(Boolean(release.publishedAt), `${tag} missing publishedAt`);
    assert(Boolean(release.url), `${tag} missing url`);

    return {
      tag,
      commit: tagCommit(tag),
      release_url: release.url,
      published_at: release.publishedAt
    };
  });

  let ancestryEdgesVerified = 0;
  for (let i = 1; i < releaseRecords.length; i++) {
    const previous = releaseRecords[i - 1];
    const current = releaseRecords[i];
    assert(
      isAncestor(previous.commit, current.commit),
      `${previous.tag} is not ancestor of ${current.tag}`
    );
    ancestryEdgesVerified++;
  }

  const latestReleased = releaseRecords[releaseRecords.length - 1];
  const workingHead = run("git", ["rev-parse", "HEAD"]);

  /*
    Critical v1.5 repair:
    A feature branch may advance beyond the latest public lineage release.
    The invariant is not "working HEAD equals released lineage head".
    The invariant is "released lineage head is an ancestor of working HEAD".
  */
  assert(
    isAncestor(latestReleased.commit, workingHead),
    `latest released lineage head ${latestReleased.tag} is not ancestor of working head`
  );

  const consumptionReceiptPath = "CONSUMPTION/CASE_001_PUBLIC_RELEASE_CONSUMPTION_RECEIPT.json";
  assert(existsSync(consumptionReceiptPath), `missing consumption receipt: ${consumptionReceiptPath}`);
  const receipt = JSON.parse(readFileSync(consumptionReceiptPath, "utf8"));
  assert(receipt.object_type === "CINEMATICUM_PUBLIC_RELEASE_CONSUMPTION_RECEIPT", "bad consumption receipt object_type");
  assert(receipt.valid === true, "consumption receipt invalid");
  assert(receipt.proves_public_release_assets_consumed === true, "public release assets not consumed");
  assert(receipt.proves_extracted_outsider_replay === true, "outsider replay not proven from public assets");
  assert(receipt.proves_truth === false, "receipt truth boundary violated");
  assert(receipt.proves_admissibility === false, "receipt admissibility boundary violated");
  assert(receipt.proves_external_reality === false, "receipt external reality boundary violated");

  const result = {
    object_type: "CINEMATICUM_PUBLIC_RELEASE_LINEAGE_VERIFICATION_RESULT",
    schema_version: "1.4.1",
    valid: true,
    errors: [],
    ledger_path: ledgerPath,
    ledger_sha256_canonical_json: sha256Text(JSON.stringify(ledger)),
    release_count: releaseRecords.length,
    ancestry_edges_verified: ancestryEdgesVerified,
    latest_released_lineage_tag: latestReleased.tag,
    latest_released_lineage_commit: latestReleased.commit,
    working_head: workingHead,
    latest_released_lineage_is_ancestor_of_working_head: true,
    public_consumption_receipt_bound_into_lineage: true,
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
    schema_version: "1.4.1",
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
