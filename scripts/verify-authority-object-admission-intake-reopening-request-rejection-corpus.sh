#!/usr/bin/env bash
set -euo pipefail

node <<'NODE'
const fs = require("fs");
const path = require("path");

const CURRENT_STATE = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED";
const LIVE_REQUEST_DIR = "CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUESTS";
const EXPECTED_REASONS = new Set([
  "missing_current_state",
  "wrong_current_state",
  "missing_authority_object_manifest",
  "silent_reopening_allowed",
  "media_present"
]);

function readJson(file) {
  if (!fs.existsSync(file)) throw new Error("missing file: " + file);
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function pick(obj, keys) {
  for (const key of keys) {
    if (obj && Object.prototype.hasOwnProperty.call(obj, key)) return obj[key];
  }
  return undefined;
}

function stateOf(obj) {
  return pick(obj, ["current_state", "active_current_state", "current_active_state", "state"]);
}

function requireBool(obj, keys, expected, label) {
  const value = pick(obj, keys);
  if (typeof value !== "boolean") throw new Error("missing boolean: " + label);
  if (value !== expected) throw new Error("wrong boolean " + label + ": " + value);
}

function requireNumber(obj, keys, expected, label) {
  const value = pick(obj, keys);
  if (typeof value !== "number") throw new Error("missing number: " + label);
  if (value !== expected) throw new Error("wrong number " + label + ": " + value);
}

function jsonFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  if (!fs.statSync(dir).isDirectory()) throw new Error("not directory: " + dir);
  return fs.readdirSync(dir).filter((name) => name.endsWith(".json")).map((name) => path.join(dir, name)).sort();
}

function validateReopeningRequest(req) {
  if (!req || typeof req !== "object") return "not_object";
  if (req.object_type !== "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST") return "wrong_object_type";
  if (!Object.prototype.hasOwnProperty.call(req, "current_state")) return "missing_current_state";
  if (req.current_state !== CURRENT_STATE) return "wrong_current_state";
  if (!Array.isArray(req.authority_object_manifest)) return "missing_authority_object_manifest";
  if (req.silent_reopening_forbidden !== true) return "silent_reopening_allowed";
  if (req.media_present !== false) return "media_present";
  if (req.issued !== false) return "issued_present";
  if (req.decision_required_before_reopening !== true) return "missing_decision_requirement";
  if (req.finality_recompute_required !== true) return "missing_finality_recompute";
  return null;
}

const corpus = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_CORPUS.json");
const law = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_CORPUS_LAW.json");
const status = readJson("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_CORPUS_STATUS.json");
const validator = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_VALIDATOR.json");
const schema = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_SCHEMA.json");
const currentCase = readJson("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json");
const currentIndex = readJson("CINEMATICUM_CURRENT_STATE_INDEX.json");

const activeState = stateOf(currentCase) || stateOf(currentIndex);
if (activeState !== CURRENT_STATE) throw new Error("wrong current state: " + activeState);

if (corpus.object_type !== "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_CORPUS") {
  throw new Error("wrong corpus object_type");
}
if (law.object_type !== "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_CORPUS_LAW") {
  throw new Error("wrong law object_type");
}
if (stateOf(corpus) !== CURRENT_STATE) throw new Error("corpus wrong state: " + stateOf(corpus));
if (stateOf(status) !== CURRENT_STATE) throw new Error("status wrong state: " + stateOf(status));

requireBool(schema, ["schema_does_not_reopen_intake"], true, "schema.schema_does_not_reopen_intake");
requireBool(validator, ["validator_does_not_reopen_intake"], true, "validator.validator_does_not_reopen_intake");
requireBool(validator, ["zero_reopening_requests_valid"], true, "validator.zero_reopening_requests_valid");

const liveFiles = jsonFiles(LIVE_REQUEST_DIR);
if (liveFiles.length !== 0) throw new Error("live reopening requests present: " + liveFiles.join(", "));

for (const obj of [corpus, status]) {
  requireNumber(obj, ["canonical_rejection_fixture_count"], 5, "canonical_rejection_fixture_count");
  requireNumber(obj, ["live_reopening_request_count"], 0, "live_reopening_request_count");
  requireNumber(obj, ["valid_reopening_request_count"], 0, "valid_reopening_request_count");
  requireNumber(obj, ["accepted_reopening_request_count"], 0, "accepted_reopening_request_count");
  requireBool(obj, ["fixtures_are_live_requests"], false, "fixtures_are_live_requests");
  requireBool(obj, ["all_fixtures_rejected"], true, "all_fixtures_rejected");
  requireBool(obj, ["rejection_corpus_declared"], true, "rejection_corpus_declared");
  requireBool(obj, ["rejection_corpus_does_not_create_live_request"], true, "rejection_corpus_does_not_create_live_request");
  requireBool(obj, ["rejection_corpus_does_not_reopen_intake"], true, "rejection_corpus_does_not_reopen_intake");
  requireBool(obj, ["rejection_corpus_does_not_satisfy_authority"], true, "rejection_corpus_does_not_satisfy_authority");
  requireBool(obj, ["rejection_corpus_does_not_advance_case_state"], true, "rejection_corpus_does_not_advance_case_state");
  requireBool(obj, ["silent_reopening_forbidden"], true, "silent_reopening_forbidden");
  requireBool(obj, ["authority_satisfied"], false, "authority_satisfied");
  requireBool(obj, ["may_advance_now"], false, "may_advance_now");
  requireBool(obj, ["issued"], false, "issued");
  requireBool(obj, ["media_present"], false, "media_present");
}

for (const key of [
  "rejection_corpus_declared",
  "all_fixtures_must_be_rejected",
  "fixtures_must_not_reopen_intake",
  "fixtures_must_not_satisfy_authority",
  "fixtures_must_not_advance_case_state",
  "fixtures_must_not_issue",
  "fixtures_must_not_admit_media",
  "live_reopening_request_count_must_remain_zero",
  "silent_reopening_forbidden"
]) {
  if (law[key] !== true) throw new Error("law flag not true: " + key);
}
if (law.fixtures_are_live_requests !== false) throw new Error("law fixtures_are_live_requests must be false");

const fixtureDir = corpus.fixture_directory;
const fixtureFiles = jsonFiles(fixtureDir);
if (fixtureFiles.length !== 5) throw new Error("wrong fixture count: " + fixtureFiles.length);

const seenReasons = new Set();
for (const file of fixtureFiles) {
  const fixture = readJson(file);
  if (fixture.fixture_type !== "CINEMATICUM_REOPENING_REQUEST_REJECTION_FIXTURE") {
    throw new Error("wrong fixture type: " + file);
  }
  if (fixture.fixture_is_live_request !== false) {
    throw new Error("fixture marked live: " + file);
  }
  if (fixture.expected_valid !== false) {
    throw new Error("fixture expected valid: " + file);
  }
  const expected = fixture.expected_rejection_reason;
  if (!EXPECTED_REASONS.has(expected)) throw new Error("unexpected rejection reason: " + expected);
  const actual = validateReopeningRequest(fixture.request);
  if (actual !== expected) throw new Error(`fixture ${file} expected ${expected} got ${actual}`);
  seenReasons.add(expected);
}

for (const reason of EXPECTED_REASONS) {
  if (!seenReasons.has(reason)) throw new Error("missing fixture reason: " + reason);
}

console.log("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST REJECTION CORPUS: PASS");
console.log("CURRENT_STATE=" + CURRENT_STATE);
console.log("REJECTION_FIXTURE_COUNT=5");
console.log("FIXTURES_ARE_LIVE_REQUESTS=false");
console.log("ALL_FIXTURES_REJECTED=true");
console.log("LIVE_REOPENING_REQUEST_COUNT=0");
console.log("VALID_REOPENING_REQUEST_COUNT=0");
console.log("ACCEPTED_REOPENING_REQUEST_COUNT=0");
console.log("AUTHORITY_SATISFIED=false");
console.log("MAY_ADVANCE_NOW=false");
console.log("ISSUED=false");
console.log("MEDIA_PRESENT=false");
NODE
