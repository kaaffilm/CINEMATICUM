#!/usr/bin/env bash
set -euo pipefail

node <<'NODE'
const fs = require("fs");

function load(path) {
  if (!fs.existsSync(path)) throw new Error("missing: " + path);
  return JSON.parse(fs.readFileSync(path, "utf8"));
}

function pick(obj, keys) {
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(obj, key)) return obj[key];
  }
  return undefined;
}

function bool(obj, key) {
  if (obj[key] !== true && obj[key] !== false) throw new Error("non-boolean " + key);
  return obj[key];
}

const CASE_ID = "CASE_001_THE_LAST_RENDER";
const CURRENT_STATE = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED";

function deepState(obj) {
  const keys = new Set([
    "active_current_state",
    "current_active_state",
    "current_state",
    "active_state",
    "state",
    "state_name",
    "case_state"
  ]);

  function walk(value) {
    if (!value || typeof value !== "object") return undefined;
    if (Array.isArray(value)) {
      for (const item of value) {
        const found = walk(item);
        if (found) return found;
      }
      return undefined;
    }

    for (const [key, val] of Object.entries(value)) {
      if (keys.has(key) && typeof val === "string") return val;
    }
    for (const val of Object.values(value)) {
      const found = walk(val);
      if (found) return found;
    }
    return undefined;
  }

  return walk(obj);
}

const currentIndex = load("CINEMATICUM_CURRENT_STATE_INDEX.json");
let activeState = deepState(currentIndex);

if (!activeState && fs.existsSync("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json")) {
  activeState = deepState(load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json"));
}

if (activeState !== CURRENT_STATE) throw new Error("wrong current state: " + activeState);

const closure = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_CLOSURE_SEAL.json");
if (closure.case_id !== CASE_ID) throw new Error("closure seal wrong case");
if (closure.current_state !== CURRENT_STATE) throw new Error("closure seal wrong state");
if (closure.admission_stack_closed !== true) throw new Error("admission stack not closed");

const order = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_ORDER.json");
const law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_ORDER_LAW.json");
const status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_ORDER_STATUS.json");

if (order.object_type !== "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_ORDER") throw new Error("wrong intake object_type");
if (law.object_type !== "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_ORDER_LAW") throw new Error("wrong intake law object_type");
if (status.object_type !== "CINEMATICUM_CASE_AUTHORITY_OBJECT_ADMISSION_INTAKE_ORDER_STATUS") throw new Error("wrong intake status object_type");

for (const obj of [order, law, status]) {
  if (obj.case_id !== CASE_ID) throw new Error("wrong case_id");
  if (obj.current_state !== CURRENT_STATE) throw new Error("wrong current_state");
  if (bool(obj, "authority_satisfied") !== false) throw new Error("authority satisfied illegally");
  if (bool(obj, "may_advance_now") !== false) throw new Error("may advance illegally");
  if (bool(obj, "issued") !== false) throw new Error("issued illegally");
  if (bool(obj, "media_present") !== false) throw new Error("media present illegally");
}

if (order.depends_on_admission_closure_seal !== true) throw new Error("closure dependency missing");
if (order.intake_order_is_not_authority_satisfaction !== true) throw new Error("intake order incorrectly satisfies authority");
if (order.intake_order_does_not_admit_media !== true) throw new Error("intake order admits media");
if (order.intake_order_does_not_issue_film !== true) throw new Error("intake order issues film");
if (order.intake_order_does_not_advance_state !== true) throw new Error("intake order advances state");

const required = order.required_authority_objects;
if (!Array.isArray(required)) throw new Error("required authority objects not array");
if (required.length !== 8) throw new Error("wrong required authority object count");
if (order.required_authority_object_count !== required.length) throw new Error("count mismatch");
if (status.required_authority_object_count !== required.length) throw new Error("status count mismatch");

const expected = [
  "DIRECTOR_ACCEPTANCE_OBJECT",
  "FINAL_CUT_TIMELINE_LOCK",
  "MEDIA_HASH_MANIFEST",
  "COLOR_GRADE_LOCK",
  "SOUND_MIX_LOCK",
  "REPLAY_EXECUTION_REPORT",
  "ADMISSIBILITY_VERDICT",
  "TERMINAL_CLOSURE_CANDIDATE"
];

for (let i = 0; i < expected.length; i++) {
  const entry = required[i];
  if (!entry) throw new Error("missing required entry " + (i + 1));
  if (entry.order !== i + 1) throw new Error("wrong order for " + expected[i]);
  if (entry.authority_object_type !== expected[i]) throw new Error("wrong authority object at order " + (i + 1));
  if (!entry.template_path || !fs.existsSync(entry.template_path)) throw new Error("missing template path: " + entry.template_path);
  if (!entry.schema_path || !fs.existsSync(entry.schema_path)) throw new Error("missing schema path: " + entry.schema_path);
}

if (order.live_admission_requests_present !== false) throw new Error("live requests present illegally");
if (order.admission_request_count !== 0) throw new Error("admission request count nonzero");
if (order.accepted_decision_count !== 0) throw new Error("accepted decision count nonzero");
if (order.instantiated_authority_objects_present !== false) throw new Error("instantiated authority objects present illegally");

if (law.closure_seal_must_precede_intake_order !== true) throw new Error("law missing closure precedence");
if (law.templates_do_not_satisfy_authority_objects !== true) throw new Error("law allows templates to satisfy");
if (law.schemas_do_not_satisfy_authority_objects !== true) throw new Error("law allows schemas to satisfy");
if (law.each_required_authority_object_requires_live_admission_request !== true) throw new Error("law missing live request requirement");
if (law.accepted_decision_required_before_instantiation !== true) throw new Error("law missing accepted decision requirement");
if (law.no_media_payload_may_be_admitted_by_intake_order !== true) throw new Error("law admits media");
if (law.no_state_transition_may_be_unblocked_by_intake_order !== true) throw new Error("law unblocks transition");

console.log("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE ORDER: PASS");
console.log("CURRENT_STATE=" + CURRENT_STATE);
console.log("ADMISSION_STACK_CLOSED=true");
console.log("REQUIRED_AUTHORITY_OBJECT_COUNT=" + required.length);
console.log("ADMISSION_REQUEST_COUNT=0");
console.log("ACCEPTED_DECISION_COUNT=0");
console.log("INSTANTIATED_AUTHORITY_OBJECTS_PRESENT=false");
console.log("AUTHORITY_SATISFIED=false");
console.log("MAY_ADVANCE_NOW=false");
console.log("ISSUED=false");
console.log("MEDIA_PRESENT=false");
NODE
