#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

node <<'NODE'
const fs = require("fs");

function fail(msg) {
  console.error(`[FATAL] ${msg}`);
  process.exit(1);
}

function load(path) {
  if (!fs.existsSync(path)) fail(`missing ${path}`);
  return JSON.parse(fs.readFileSync(path, "utf8"));
}

function bool(obj, keys, fallback = false) {
  for (const k of keys) {
    if (Object.prototype.hasOwnProperty.call(obj, k)) return obj[k] === true;
  }
  return fallback;
}

function num(obj, keys, fallback = 0) {
  for (const k of keys) {
    if (Object.prototype.hasOwnProperty.call(obj, k)) return Number(obj[k]);
  }
  return fallback;
}

function str(obj, keys, fallback = "") {
  for (const k of keys) {
    if (Object.prototype.hasOwnProperty.call(obj, k)) return String(obj[k]);
  }
  return fallback;
}

function eq(actual, expected, label) {
  if (actual !== expected) fail(`${label}: expected ${expected}, got ${actual}`);
}

const gate = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE.json");
const law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE_LAW.json");
const status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE_STATUS.json");
const current = load("CINEMATICUM_CURRENT_STATE_INDEX.json");
const decision = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER_STATUS.json");

eq(gate.object_type, "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE", "gate object_type");
eq(law.object_type, "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE_LAW", "law object_type");
eq(status.object_type, "CINEMATICUM_CASE_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE_STATUS", "status object_type");

const currentState =
  str(status, ["current_state"]) ||
  str(gate, ["current_state"]) ||
  str(current, ["active_current_state", "current_active_state", "current_state"]);

eq(currentState, "REAL_CASE_AUTHORITY_OBJECTS_INSTANTIATED_PENDING_RELEASE_CANDIDATE_ARTIFACTS", "current_state");

const admissionRequestCount = num(status, ["admission_request_count"], num(decision, ["admission_request_count"], 0));
const decisionRecordCount = num(status, ["decision_record_count"], num(decision, ["decision_record_count"], 0));
const acceptedDecisionCount = num(status, ["accepted_decision_count"], num(decision, ["accepted_decision_count"], 0));
const rejectedDecisionCount = num(status, ["rejected_decision_count"], num(decision, ["rejected_decision_count"], 0));

eq(admissionRequestCount, 0, "admission_request_count");
eq(decisionRecordCount, 0, "decision_record_count");
eq(acceptedDecisionCount, 0, "accepted_decision_count");
eq(rejectedDecisionCount, 0, "rejected_decision_count");

eq(bool(status, ["all_live_requests_have_decisions"], true), true, "all_live_requests_have_decisions");
eq(bool(status, ["accepted_decision_for_each_instantiated_authority_object"], true), true, "accepted_decision_for_each_instantiated_authority_object");

eq(bool(gate, ["requires_valid_admission_request"]), true, "requires_valid_admission_request");
eq(bool(gate, ["requires_recorded_admission_decision"]), true, "requires_recorded_admission_decision");
eq(bool(gate, ["requires_accepted_admission_decision_for_instantiation"]), true, "requires_accepted_admission_decision_for_instantiation");

eq(bool(law, ["live_authority_object_requires_admission_decision"]), true, "live_authority_object_requires_admission_decision");
eq(bool(law, ["accepted_admission_decision_required_before_instantiation"]), true, "accepted_admission_decision_required_before_instantiation");
eq(bool(law, ["enforcement_gate_does_not_issue_motion_picture"]), true, "enforcement_gate_does_not_issue_motion_picture");

for (const [obj, name] of [[gate, "gate"], [law, "law"], [status, "status"]]) {
  eq(bool(obj, ["authority_satisfied"]), false, `${name}.authority_satisfied`);
  eq(bool(obj, ["may_advance_now"]), false, `${name}.may_advance_now`);
  eq(bool(obj, ["release_candidate_ready"]), false, `${name}.release_candidate_ready`);
  eq(bool(obj, ["issued"]), false, `${name}.issued`);
  eq(bool(obj, ["media_present"]), false, `${name}.media_present`);
}

eq(bool(status, ["enforcement_gate_passed"]), false, "enforcement_gate_passed");

console.log("CINEMATICUM AUTHORITY OBJECT ADMISSION ENFORCEMENT GATE: PASS");
console.log(`CURRENT_STATE=${currentState}`);
console.log(`ADMISSION_REQUEST_COUNT=${admissionRequestCount}`);
console.log(`DECISION_RECORD_COUNT=${decisionRecordCount}`);
console.log(`ACCEPTED_DECISION_COUNT=${acceptedDecisionCount}`);
console.log(`REJECTED_DECISION_COUNT=${rejectedDecisionCount}`);
console.log(`ALL_LIVE_REQUESTS_HAVE_DECISIONS=${bool(status, ["all_live_requests_have_decisions"], true)}`);
console.log(`ENFORCEMENT_GATE_PASSED=${bool(status, ["enforcement_gate_passed"])}`);
console.log(`AUTHORITY_SATISFIED=${bool(status, ["authority_satisfied"])}`);
console.log(`MAY_ADVANCE_NOW=${bool(status, ["may_advance_now"])}`);
console.log(`ISSUED=${bool(status, ["issued"])}`);
console.log(`MEDIA_PRESENT=${bool(status, ["media_present"])}`);
NODE

if [ "${CINEMATICUM_PR28_SKIP_UNITTEST:-false}" != "true" ]; then
  CINEMATICUM_PR28_SKIP_UNITTEST=true python3 -m unittest tests/test_authority_object_admission_enforcement_gate.py
fi
