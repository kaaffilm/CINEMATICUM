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

function stateOf(obj) {
  return pick(obj, [
    "current_state",
    "active_current_state",
    "current_active_state",
    "state",
  ]);
}

const gate = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_VALIDATION_GATE.json");
const law = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_VALIDATION_GATE_LAW.json");
const status = readJson("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_VALIDATION_GATE_STATUS.json");
const currentCase = readJson("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json");
const currentIndex = readJson("CINEMATICUM_CURRENT_STATE_INDEX.json");
const closure = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL.json");
const intake = readJson("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_ORDER.json");

const activeState =
  stateOf(currentCase) ||
  stateOf(currentIndex) ||
  pick(currentIndex, ["current_active_state"]);

if (activeState !== CURRENT_STATE) throw new Error("wrong current state: " + activeState);
if (stateOf(gate) !== CURRENT_STATE) throw new Error("gate wrong state: " + stateOf(gate));
if (stateOf(status) !== CURRENT_STATE) throw new Error("status wrong state: " + stateOf(status));

if (gate.object_type !== "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_VALIDATION_GATE") {
  throw new Error("wrong gate object_type");
}
if (law.object_type !== "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_VALIDATION_GATE_LAW") {
  throw new Error("wrong law object_type");
}

const closureClosed = pick(closure, [
  "admission_stack_closed",
  "authority_object_admission_stack_closed",
  "closed",
], true);
if (closureClosed !== true) throw new Error("admission stack not closed");

const intakeClosed = pick(intake, [
  "admission_stack_closed",
  "authority_object_admission_stack_closed",
  "closure_seal_admission_stack_closed",
], true);
if (intakeClosed !== true) throw new Error("intake order does not see closed stack");

requireBool(gate, ["admission_stack_closed"], true, "admission_stack_closed");
requireNumber(gate, ["required_authority_object_count"], 8, "required_authority_object_count");
requireNumber(gate, ["admission_request_count"], 0, "admission_request_count");
requireNumber(gate, ["valid_admission_request_count"], 0, "valid_admission_request_count");
requireNumber(gate, ["accepted_decision_count"], 0, "accepted_decision_count");
requireBool(gate, ["intake_validation_gate_passed"], false, "intake_validation_gate_passed");
requireBool(gate, ["authority_satisfied"], false, "authority_satisfied");
requireBool(gate, ["may_advance_now"], false, "may_advance_now");
requireBool(gate, ["issued"], false, "issued");
requireBool(gate, ["media_present"], false, "media_present");

requireBool(status, ["admission_stack_closed"], true, "status.admission_stack_closed");
requireNumber(status, ["required_authority_object_count"], 8, "status.required_authority_object_count");
requireNumber(status, ["admission_request_count"], 0, "status.admission_request_count");
requireNumber(status, ["valid_admission_request_count"], 0, "status.valid_admission_request_count");
requireNumber(status, ["accepted_decision_count"], 0, "status.accepted_decision_count");
requireBool(status, ["intake_validation_gate_passed"], false, "status.intake_validation_gate_passed");
requireBool(status, ["authority_satisfied"], false, "status.authority_satisfied");
requireBool(status, ["may_advance_now"], false, "status.may_advance_now");
requireBool(status, ["issued"], false, "status.issued");
requireBool(status, ["media_present"], false, "status.media_present");

for (const key of [
  "validates_intake_order_only",
  "does_not_instantiate_authority_objects",
  "does_not_satisfy_authority",
  "does_not_advance_case_state",
  "does_not_issue",
  "does_not_admit_media",
]) {
  if (law[key] !== true) throw new Error("law flag not true: " + key);
}

console.log("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE VALIDATION GATE: PASS");
console.log("CURRENT_STATE=" + CURRENT_STATE);
console.log("ADMISSION_STACK_CLOSED=true");
console.log("REQUIRED_AUTHORITY_OBJECT_COUNT=8");
console.log("ADMISSION_REQUEST_COUNT=0");
console.log("VALID_ADMISSION_REQUEST_COUNT=0");
console.log("ACCEPTED_DECISION_COUNT=0");
console.log("INTAKE_VALIDATION_GATE_PASSED=false");
console.log("AUTHORITY_SATISFIED=false");
console.log("MAY_ADVANCE_NOW=false");
console.log("ISSUED=false");
console.log("MEDIA_PRESENT=false");
NODE
