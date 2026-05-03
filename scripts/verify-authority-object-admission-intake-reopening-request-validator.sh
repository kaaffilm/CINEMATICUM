#!/usr/bin/env bash
set -euo pipefail

node <<'NODE'
const fs = require("fs");
const path = require("path");

const CURRENT_STATE = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED";
const REQUEST_DIR = "CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUESTS";

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

function listRequestFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  if (!fs.statSync(dir).isDirectory()) throw new Error("request path is not directory: " + dir);
  return fs.readdirSync(dir)
    .filter((name) => name.endsWith(".json"))
    .map((name) => path.join(dir, name))
    .sort();
}

const validator = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_VALIDATOR.json");
const law = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_VALIDATOR_LAW.json");
const status = readJson("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_VALIDATOR_STATUS.json");
const schema = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_SCHEMA.json");
const reopeningGate = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_GATE.json");
const finality = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_FINALITY_SEAL.json");
const currentCase = readJson("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json");
const currentIndex = readJson("CINEMATICUM_CURRENT_STATE_INDEX.json");

const activeState = stateOf(currentCase) || stateOf(currentIndex);
if (activeState !== CURRENT_STATE) throw new Error("wrong current state: " + activeState);

if (validator.object_type !== "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_VALIDATOR") {
  throw new Error("wrong validator object_type");
}
if (law.object_type !== "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_VALIDATOR_LAW") {
  throw new Error("wrong law object_type");
}
if (stateOf(validator) !== CURRENT_STATE) throw new Error("validator wrong state: " + stateOf(validator));
if (stateOf(status) !== CURRENT_STATE) throw new Error("status wrong state: " + stateOf(status));

requireBool(schema, ["schema_does_not_reopen_intake"], true, "schema.schema_does_not_reopen_intake");
requireBool(schema, ["schema_does_not_create_live_request"], true, "schema.schema_does_not_create_live_request");
requireBool(reopeningGate, ["future_intake_allowed_under_law"], true, "reopeningGate.future_intake_allowed_under_law");
requireBool(reopeningGate, ["silent_reopening_forbidden"], true, "reopeningGate.silent_reopening_forbidden");
requireBool(reopeningGate, ["reopening_gate_open_now"], false, "reopeningGate.reopening_gate_open_now");
requireBool(finality, ["intake_finality_sealed"], true, "finality.intake_finality_sealed");

const requestFiles = listRequestFiles(REQUEST_DIR);
if (requestFiles.length !== 0) {
  throw new Error("live reopening requests present: " + requestFiles.join(", "));
}

const requiredFields = schema.required_reopening_request_fields;
if (!Array.isArray(requiredFields) || requiredFields.length < 14) {
  throw new Error("schema required fields not established");
}

for (const obj of [validator, status]) {
  requireNumber(obj, ["live_reopening_request_count"], 0, "live_reopening_request_count");
  requireNumber(obj, ["valid_reopening_request_count"], 0, "valid_reopening_request_count");
  requireNumber(obj, ["invalid_reopening_request_count"], 0, "invalid_reopening_request_count");
  requireNumber(obj, ["accepted_reopening_request_count"], 0, "accepted_reopening_request_count");
  requireBool(obj, ["zero_reopening_requests_valid"], true, "zero_reopening_requests_valid");
  requireBool(obj, ["validator_declared"], true, "validator_declared");
  requireBool(obj, ["validator_does_not_create_live_request"], true, "validator_does_not_create_live_request");
  requireBool(obj, ["validator_does_not_reopen_intake"], true, "validator_does_not_reopen_intake");
  requireBool(obj, ["validator_does_not_satisfy_authority"], true, "validator_does_not_satisfy_authority");
  requireBool(obj, ["validator_does_not_advance_case_state"], true, "validator_does_not_advance_case_state");
  requireBool(obj, ["future_request_must_match_schema"], true, "future_request_must_match_schema");
  requireBool(obj, ["future_request_must_have_decision_before_reopening"], true, "future_request_must_have_decision_before_reopening");
  requireBool(obj, ["future_request_must_recompute_finality"], true, "future_request_must_recompute_finality");
  requireBool(obj, ["silent_reopening_forbidden"], true, "silent_reopening_forbidden");
  requireBool(obj, ["reopening_gate_open_now"], false, "reopening_gate_open_now");
  requireBool(obj, ["current_snapshot_final"], true, "current_snapshot_final");
  requireBool(obj, ["intake_finality_sealed"], true, "intake_finality_sealed");
  requireBool(obj, ["authority_satisfied"], false, "authority_satisfied");
  requireBool(obj, ["may_advance_now"], false, "may_advance_now");
  requireBool(obj, ["issued"], false, "issued");
  requireBool(obj, ["media_present"], false, "media_present");
}

for (const key of [
  "validator_declared",
  "zero_reopening_requests_valid",
  "validator_does_not_create_live_request",
  "validator_does_not_reopen_intake",
  "validator_does_not_accept_authority_objects",
  "validator_does_not_instantiate_authority_objects",
  "validator_does_not_satisfy_authority",
  "validator_does_not_advance_case_state",
  "validator_does_not_issue",
  "validator_does_not_admit_media",
  "future_request_must_match_schema",
  "future_request_must_target_current_state",
  "future_request_must_reference_all_required_authority_objects",
  "future_request_must_have_decision_before_reopening",
  "future_request_must_recompute_finality",
  "silent_reopening_forbidden"
]) {
  if (law[key] !== true) throw new Error("law flag not true: " + key);
}

console.log("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST VALIDATOR: PASS");
console.log("CURRENT_STATE=" + CURRENT_STATE);
console.log("LIVE_REOPENING_REQUEST_COUNT=0");
console.log("VALID_REOPENING_REQUEST_COUNT=0");
console.log("INVALID_REOPENING_REQUEST_COUNT=0");
console.log("ACCEPTED_REOPENING_REQUEST_COUNT=0");
console.log("ZERO_REOPENING_REQUESTS_VALID=true");
console.log("VALIDATOR_DOES_NOT_REOPEN_INTAKE=true");
console.log("AUTHORITY_SATISFIED=false");
console.log("MAY_ADVANCE_NOW=false");
console.log("ISSUED=false");
console.log("MEDIA_PRESENT=false");
NODE
