#!/usr/bin/env bash
set -euo pipefail

node <<'NODE'
const fs = require("fs");

const CURRENT_STATE = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED";

function readJson(path) {
  if (!fs.existsSync(path)) throw new Error("missing file: " + path);
  return JSON.parse(fs.readFileSync(path, "utf8"));
}

function pick(obj, keys, fallback = undefined) {
  for (const key of keys) {
    if (obj && Object.prototype.hasOwnProperty.call(obj, key)) return obj[key];
  }
  return fallback;
}

function stateOf(obj) {
  return pick(obj, ["current_state", "active_current_state", "current_active_state", "state"]);
}

function requireBool(obj, keys, expected, label) {
  const value = pick(obj, keys);
  if (typeof value !== "boolean") throw new Error("missing boolean: " + label);
  if (value !== expected) throw new Error("wrong boolean " + label + ": " + value);
  return value;
}

function requireNumber(obj, keys, expected, label) {
  const value = pick(obj, keys);
  if (typeof value !== "number") throw new Error("missing number: " + label);
  if (value !== expected) throw new Error("wrong number " + label + ": " + value);
  return value;
}

const seal = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_FINALITY_SEAL.json");
const law = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_FINALITY_SEAL_LAW.json");
const status = readJson("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_FINALITY_SEAL_STATUS.json");
const currentCase = readJson("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json");
const currentIndex = readJson("CINEMATICUM_CURRENT_STATE_INDEX.json");
const ledger = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REJECTION_LEDGER.json");
const validation = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_VALIDATION_GATE.json");
const intake = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_ORDER.json");
const closure = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL.json");

const activeState = stateOf(currentCase) || stateOf(currentIndex);
if (activeState !== CURRENT_STATE) throw new Error("wrong current state: " + activeState);

if (seal.object_type !== "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_FINALITY_SEAL") {
  throw new Error("wrong seal object_type");
}
if (law.object_type !== "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_FINALITY_SEAL_LAW") {
  throw new Error("wrong law object_type");
}
if (stateOf(seal) !== CURRENT_STATE) throw new Error("seal wrong state: " + stateOf(seal));
if (stateOf(status) !== CURRENT_STATE) throw new Error("status wrong state: " + stateOf(status));

requireBool(closure, ["admission_stack_closed"], true, "closure.admission_stack_closed");
requireBool(intake, ["admission_stack_closed"], true, "intake.admission_stack_closed");
requireBool(validation, ["intake_validation_gate_passed"], false, "validation.intake_validation_gate_passed");
requireBool(ledger, ["rejection_ledger_closed"], true, "ledger.rejection_ledger_closed");
requireBool(ledger, ["all_invalid_intake_rejected"], true, "ledger.all_invalid_intake_rejected");
requireNumber(ledger, ["intake_rejection_record_count"], 0, "ledger.intake_rejection_record_count");

for (const obj of [seal, status]) {
  if (pick(obj, ["finality_scope"]) !== "CURRENT_STATE_ZERO_INTAKE_ONLY") {
    throw new Error("wrong finality scope");
  }
  requireBool(obj, ["finality_scope_current_state_only"], true, "finality_scope_current_state_only");
  requireBool(obj, ["does_not_bar_future_valid_intake_under_law"], true, "does_not_bar_future_valid_intake_under_law");
  requireBool(obj, ["admission_stack_closed"], true, "admission_stack_closed");
  requireNumber(obj, ["required_authority_object_count"], 8, "required_authority_object_count");
  requireNumber(obj, ["admission_request_count"], 0, "admission_request_count");
  requireNumber(obj, ["valid_admission_request_count"], 0, "valid_admission_request_count");
  requireNumber(obj, ["accepted_decision_count"], 0, "accepted_decision_count");
  requireBool(obj, ["intake_validation_gate_passed"], false, "intake_validation_gate_passed");
  requireNumber(obj, ["intake_rejection_record_count"], 0, "intake_rejection_record_count");
  requireBool(obj, ["rejection_ledger_closed"], true, "rejection_ledger_closed");
  requireBool(obj, ["all_invalid_intake_rejected"], true, "all_invalid_intake_rejected");
  requireBool(obj, ["no_open_intake_exceptions"], true, "no_open_intake_exceptions");
  requireBool(obj, ["no_unadjudicated_intake_records"], true, "no_unadjudicated_intake_records");
  requireBool(obj, ["intake_finality_sealed"], true, "intake_finality_sealed");
  requireBool(obj, ["authority_satisfied"], false, "authority_satisfied");
  requireBool(obj, ["may_advance_now"], false, "may_advance_now");
  requireBool(obj, ["issued"], false, "issued");
  requireBool(obj, ["media_present"], false, "media_present");
}

for (const key of [
  "seals_current_zero_intake_snapshot",
  "finality_scope_current_state_only",
  "requires_closed_rejection_ledger",
  "requires_zero_valid_admission_requests",
  "requires_zero_accepted_decisions",
  "requires_no_unadjudicated_intake_records",
  "does_not_bar_future_valid_intake_under_law",
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

console.log("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE FINALITY SEAL: PASS");
console.log("CURRENT_STATE=" + CURRENT_STATE);
console.log("FINALITY_SCOPE=CURRENT_STATE_ZERO_INTAKE_ONLY");
console.log("ADMISSION_STACK_CLOSED=true");
console.log("VALID_ADMISSION_REQUEST_COUNT=0");
console.log("INTAKE_REJECTION_RECORD_COUNT=0");
console.log("REJECTION_LEDGER_CLOSED=true");
console.log("NO_UNADJUDICATED_INTAKE_RECORDS=true");
console.log("INTAKE_FINALITY_SEALED=true");
console.log("AUTHORITY_SATISFIED=false");
console.log("MAY_ADVANCE_NOW=false");
console.log("ISSUED=false");
console.log("MEDIA_PRESENT=false");
NODE
