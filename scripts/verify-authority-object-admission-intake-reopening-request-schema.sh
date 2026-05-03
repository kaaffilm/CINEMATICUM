#!/usr/bin/env bash
set -euo pipefail

node <<'NODE'
const fs = require("fs");

const CURRENT_STATE = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED";

function readJson(path) {
  if (!fs.existsSync(path)) throw new Error("missing file: " + path);
  return JSON.parse(fs.readFileSync(path, "utf8"));
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

const schema = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_SCHEMA.json");
const law = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_SCHEMA_LAW.json");
const status = readJson("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_SCHEMA_STATUS.json");
const currentCase = readJson("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json");
const currentIndex = readJson("CINEMATICUM_CURRENT_STATE_INDEX.json");
const reopeningGate = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_GATE.json");
const finality = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_FINALITY_SEAL.json");

const activeState = stateOf(currentCase) || stateOf(currentIndex);
if (activeState !== CURRENT_STATE) throw new Error("wrong current state: " + activeState);

if (schema.object_type !== "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_SCHEMA") {
  throw new Error("wrong schema object_type");
}
if (law.object_type !== "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_SCHEMA_LAW") {
  throw new Error("wrong law object_type");
}
if (stateOf(schema) !== CURRENT_STATE) throw new Error("schema wrong state: " + stateOf(schema));
if (stateOf(status) !== CURRENT_STATE) throw new Error("status wrong state: " + stateOf(status));

requireBool(reopeningGate, ["future_intake_allowed_under_law"], true, "reopeningGate.future_intake_allowed_under_law");
requireBool(reopeningGate, ["silent_reopening_forbidden"], true, "reopeningGate.silent_reopening_forbidden");
requireBool(reopeningGate, ["reopening_gate_open_now"], false, "reopeningGate.reopening_gate_open_now");
requireBool(finality, ["intake_finality_sealed"], true, "finality.intake_finality_sealed");

const requiredFields = [
  "request_id",
  "case_id",
  "target_current_state",
  "requested_authority_object_ids",
  "director_authority_evidence_ref",
  "final_cut_jurisdiction_evidence_ref",
  "timeline_evidence_ref",
  "release_admissibility_evidence_ref",
  "audience_artifact_evidence_ref",
  "proof_artifact_evidence_ref",
  "outsider_replay_evidence_ref",
  "terminal_closure_evidence_ref",
  "reopening_reason",
  "requested_at_utc"
];

if (!Array.isArray(schema.required_reopening_request_fields)) {
  throw new Error("required_reopening_request_fields missing");
}
for (const field of requiredFields) {
  if (!schema.required_reopening_request_fields.includes(field)) {
    throw new Error("missing required reopening request field: " + field);
  }
}

for (const obj of [schema, status]) {
  requireBool(obj, ["schema_only"], true, "schema_only");
  requireBool(obj, ["template_only"], true, "template_only");
  requireNumber(obj, ["live_reopening_request_count"], 0, "live_reopening_request_count");
  requireNumber(obj, ["valid_reopening_request_count"], 0, "valid_reopening_request_count");
  requireNumber(obj, ["accepted_reopening_request_count"], 0, "accepted_reopening_request_count");
  requireBool(obj, ["schema_does_not_reopen_intake"], true, "schema_does_not_reopen_intake");
  requireBool(obj, ["schema_does_not_create_live_request"], true, "schema_does_not_create_live_request");
  requireBool(obj, ["schema_does_not_satisfy_authority"], true, "schema_does_not_satisfy_authority");
  requireBool(obj, ["future_request_requires_new_record"], true, "future_request_requires_new_record");
  requireBool(obj, ["future_request_requires_schema_validation"], true, "future_request_requires_schema_validation");
  requireBool(obj, ["future_request_requires_decision_record"], true, "future_request_requires_decision_record");
  requireBool(obj, ["future_request_requires_recomputed_rejection_ledger"], true, "future_request_requires_recomputed_rejection_ledger");
  requireBool(obj, ["future_request_requires_new_finality_seal"], true, "future_request_requires_new_finality_seal");
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
  "schema_only",
  "template_only",
  "schema_does_not_reopen_intake",
  "schema_does_not_create_live_request",
  "schema_does_not_accept_authority_objects",
  "schema_does_not_instantiate_authority_objects",
  "schema_does_not_satisfy_authority",
  "schema_does_not_advance_case_state",
  "schema_does_not_issue",
  "schema_does_not_admit_media",
  "future_request_requires_new_record",
  "future_request_requires_schema_validation",
  "future_request_requires_decision_record",
  "future_request_requires_recomputed_rejection_ledger",
  "future_request_requires_new_finality_seal",
  "silent_reopening_forbidden"
]) {
  if (law[key] !== true) throw new Error("law flag not true: " + key);
}

console.log("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST SCHEMA: PASS");
console.log("CURRENT_STATE=" + CURRENT_STATE);
console.log("SCHEMA_ONLY=true");
console.log("LIVE_REOPENING_REQUEST_COUNT=0");
console.log("VALID_REOPENING_REQUEST_COUNT=0");
console.log("ACCEPTED_REOPENING_REQUEST_COUNT=0");
console.log("SCHEMA_DOES_NOT_REOPEN_INTAKE=true");
console.log("SILENT_REOPENING_FORBIDDEN=true");
console.log("AUTHORITY_SATISFIED=false");
console.log("MAY_ADVANCE_NOW=false");
console.log("ISSUED=false");
console.log("MEDIA_PRESENT=false");
NODE
