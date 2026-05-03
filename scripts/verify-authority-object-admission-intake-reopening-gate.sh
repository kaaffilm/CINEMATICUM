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

const gate = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_GATE.json");
const law = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_GATE_LAW.json");
const status = readJson("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_GATE_STATUS.json");
const currentCase = readJson("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json");
const currentIndex = readJson("CINEMATICUM_CURRENT_STATE_INDEX.json");
const finality = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_FINALITY_SEAL.json");
const ledger = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REJECTION_LEDGER.json");
const validation = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_VALIDATION_GATE.json");

const activeState = stateOf(currentCase) || stateOf(currentIndex);
if (activeState !== CURRENT_STATE) throw new Error("wrong current state: " + activeState);

if (gate.object_type !== "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_GATE") {
  throw new Error("wrong gate object_type");
}
if (law.object_type !== "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_GATE_LAW") {
  throw new Error("wrong law object_type");
}
if (stateOf(gate) !== CURRENT_STATE) throw new Error("gate wrong state: " + stateOf(gate));
if (stateOf(status) !== CURRENT_STATE) throw new Error("status wrong state: " + stateOf(status));

requireBool(finality, ["intake_finality_sealed"], true, "finality.intake_finality_sealed");
requireBool(finality, ["does_not_bar_future_valid_intake_under_law"], true, "finality.does_not_bar_future_valid_intake_under_law");
requireBool(ledger, ["rejection_ledger_closed"], true, "ledger.rejection_ledger_closed");
requireBool(validation, ["intake_validation_gate_passed"], false, "validation.intake_validation_gate_passed");

for (const obj of [gate, status]) {
  if (obj.reopening_scope !== "FUTURE_VALID_INTAKE_ONLY") throw new Error("wrong reopening scope");
  requireBool(obj, ["current_snapshot_final"], true, "current_snapshot_final");
  requireBool(obj, ["future_intake_allowed_under_law"], true, "future_intake_allowed_under_law");
  requireBool(obj, ["future_intake_requires_new_request_record"], true, "future_intake_requires_new_request_record");
  requireBool(obj, ["future_intake_requires_schema_validation"], true, "future_intake_requires_schema_validation");
  requireBool(obj, ["future_intake_requires_decision_record"], true, "future_intake_requires_decision_record");
  requireBool(obj, ["future_intake_requires_recomputed_rejection_ledger"], true, "future_intake_requires_recomputed_rejection_ledger");
  requireBool(obj, ["future_intake_requires_new_finality_seal"], true, "future_intake_requires_new_finality_seal");
  requireBool(obj, ["silent_reopening_forbidden"], true, "silent_reopening_forbidden");
  requireBool(obj, ["reopening_gate_open_now"], false, "reopening_gate_open_now");
  requireNumber(obj, ["admission_request_count"], 0, "admission_request_count");
  requireNumber(obj, ["valid_admission_request_count"], 0, "valid_admission_request_count");
  requireNumber(obj, ["accepted_decision_count"], 0, "accepted_decision_count");
  requireBool(obj, ["intake_finality_sealed"], true, "intake_finality_sealed");
  requireBool(obj, ["authority_satisfied"], false, "authority_satisfied");
  requireBool(obj, ["may_advance_now"], false, "may_advance_now");
  requireBool(obj, ["issued"], false, "issued");
  requireBool(obj, ["media_present"], false, "media_present");
}

for (const key of [
  "current_snapshot_final_remains_binding",
  "future_intake_allowed_under_law",
  "future_intake_requires_new_request_record",
  "future_intake_requires_schema_validation",
  "future_intake_requires_decision_record",
  "future_intake_requires_recomputed_rejection_ledger",
  "future_intake_requires_new_finality_seal",
  "silent_reopening_forbidden",
  "does_not_create_admission_requests",
  "does_not_accept_authority_objects",
  "does_not_instantiate_authority_objects",
  "does_not_satisfy_authority",
  "does_not_advance_case_state",
  "does_not_issue",
  "does_not_admit_media"
]) {
  if (law[key] !== true) throw new Error("law flag not true: " + key);
}

console.log("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING GATE: PASS");
console.log("CURRENT_STATE=" + CURRENT_STATE);
console.log("REOPENING_SCOPE=FUTURE_VALID_INTAKE_ONLY");
console.log("CURRENT_SNAPSHOT_FINAL=true");
console.log("FUTURE_INTAKE_ALLOWED_UNDER_LAW=true");
console.log("SILENT_REOPENING_FORBIDDEN=true");
console.log("REOPENING_GATE_OPEN_NOW=false");
console.log("AUTHORITY_SATISFIED=false");
console.log("MAY_ADVANCE_NOW=false");
console.log("ISSUED=false");
console.log("MEDIA_PRESENT=false");
NODE
