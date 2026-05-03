#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

node <<'NODE'
const fs = require("fs");

function load(path) {
  if (!fs.existsSync(path)) throw new Error("missing: " + path);
  return JSON.parse(fs.readFileSync(path, "utf8"));
}

function exists(path) {
  if (!fs.existsSync(path)) throw new Error("missing: " + path);
}

function bool(obj, key, expected) {
  if (obj[key] !== expected) {
    throw new Error(`${key} expected ${expected}, got ${obj[key]}`);
  }
}

function firstPresent(obj, keys, fallback = undefined) {
  if (!obj || typeof obj !== "object") return fallback;
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(obj, key)) return obj[key];
  }
  return fallback;
}

function deepFindState(node, wanted) {
  if (node === wanted) return wanted;
  if (Array.isArray(node)) {
    for (const item of node) {
      const found = deepFindState(item, wanted);
      if (found) return found;
    }
    return null;
  }
  if (node && typeof node === "object") {
    for (const [key, value] of Object.entries(node)) {
      const normalized = key.toLowerCase();
      if (
        typeof value === "string" &&
        value === wanted &&
        (
          normalized.includes("state") ||
          normalized.includes("active") ||
          normalized.includes("current")
        )
      ) {
        return value;
      }
      const found = deepFindState(value, wanted);
      if (found) return found;
    }
  }
  return null;
}

const CASE_ID = "CASE_001_THE_LAST_RENDER";
const CURRENT_STATE = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED";

const requiredFiles = [
  "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DOCKET.json",
  "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_SCHEMA.json",
  "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_VALIDATOR.json",
  "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REQUEST_REJECTION_CORPUS.json",
  "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_REJECTION_TAXONOMY.json",
  "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_DECISION_LEDGER.json",
  "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE.json",
  "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL.json",
  "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL_LAW.json",
  `CASES/${CASE_ID}/AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL_STATUS.json`,
  "CINEMATICUM_CURRENT_STATE_INDEX.json",
  `CASES/${CASE_ID}/CURRENT_CASE_STATE.json`
];

for (const path of requiredFiles) exists(path);

const currentIndex = load("CINEMATICUM_CURRENT_STATE_INDEX.json");
const currentCase = load(`CASES/${CASE_ID}/CURRENT_CASE_STATE.json`);
const seal = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL.json");
const law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL_LAW.json");
const status = load(`CASES/${CASE_ID}/AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL_STATUS.json`);
const enforcementStatus = load(`CASES/${CASE_ID}/AUTHORITY_OBJECT_ADMISSION_ENFORCEMENT_GATE_STATUS.json`);

const activeState =
  firstPresent(currentIndex, ["current_active_state", "active_current_state", "current_state"], null) ||
  firstPresent(currentCase, ["current_active_state", "active_current_state", "current_state", "state"], null) ||
  deepFindState(currentIndex, CURRENT_STATE) ||
  deepFindState(currentCase, CURRENT_STATE);

if (activeState !== CURRENT_STATE) {
  throw new Error("wrong current state: " + activeState);
}

if (seal.case_id !== CASE_ID) throw new Error("wrong seal case_id");
if (status.case_id !== CASE_ID) throw new Error("wrong status case_id");
if (seal.current_state !== CURRENT_STATE) throw new Error("wrong seal current_state");
if (status.current_state !== CURRENT_STATE) throw new Error("wrong status current_state");

bool(seal, "closure_seal_declared", true);
bool(seal, "admission_stack_closed", true);
bool(seal, "seal_does_not_admit_authority_objects", true);
bool(seal, "seal_does_not_satisfy_authority", true);
bool(seal, "seal_does_not_advance_state", true);
bool(seal, "seal_does_not_create_release_candidate", true);
bool(seal, "seal_does_not_issue_motion_picture", true);

bool(law, "law_declared", true);
bool(law, "closure_seal_required_after_enforcement_gate", true);
bool(law, "closure_seal_is_non_advancing", true);
bool(law, "closure_seal_is_not_authority_satisfaction", true);
bool(law, "closure_seal_is_not_release_readiness", true);
bool(law, "closure_seal_is_not_issuance", true);

bool(status, "closure_seal_declared", true);
bool(status, "admission_stack_closed", true);

if (status.admission_stack_layer_count !== 7) {
  throw new Error("admission_stack_layer_count expected 7");
}

if (status.admission_request_count !== 0) throw new Error("admission_request_count must remain 0");
if (status.decision_record_count !== 0) throw new Error("decision_record_count must remain 0");
if (status.accepted_decision_count !== 0) throw new Error("accepted_decision_count must remain 0");
if (status.rejected_decision_count !== 0) throw new Error("rejected_decision_count must remain 0");

bool(status, "enforcement_gate_passed", false);
bool(status, "authority_satisfied", false);
bool(status, "may_advance_now", false);
bool(status, "release_candidate_ready", false);
bool(status, "issued", false);
bool(status, "media_present", false);

bool(enforcementStatus, "authority_satisfied", false);
bool(enforcementStatus, "may_advance_now", false);
bool(enforcementStatus, "issued", false);
bool(enforcementStatus, "media_present", false);

console.log("CINEMATICUM AUTHORITY OBJECT ADMISSION CLOSURE SEAL: PASS");
console.log("CURRENT_STATE=" + CURRENT_STATE);
console.log("ADMISSION_STACK_CLOSED=true");
console.log("ADMISSION_STACK_LAYER_COUNT=7");
console.log("ADMISSION_REQUEST_COUNT=0");
console.log("DECISION_RECORD_COUNT=0");
console.log("ENFORCEMENT_GATE_PASSED=false");
console.log("AUTHORITY_SATISFIED=false");
console.log("MAY_ADVANCE_NOW=false");
console.log("ISSUED=false");
console.log("MEDIA_PRESENT=false");
NODE
