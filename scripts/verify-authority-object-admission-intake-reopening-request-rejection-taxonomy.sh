#!/usr/bin/env bash
set -euo pipefail

node <<'NODE'
const fs = require("fs");
const path = require("path");

const CURRENT_STATE = "OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED";
const CASE_ID = "CASE_001_THE_LAST_RENDER";
const requiredCodes = new Set([
  "missing_current_state",
  "wrong_current_state",
  "missing_authority_object_manifest",
  "silent_reopening_allowed",
  "media_present",
  "accepted_reopening_request_present",
  "reopening_gate_open_now_true",
  "authority_satisfied_true",
  "may_advance_now_true"
]);

function load(file) { return JSON.parse(fs.readFileSync(file, "utf8")); }
function assert(cond, msg) { if (!cond) throw new Error(msg); }

[
  "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_TAXONOMY_LAW.json",
  "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_TAXONOMY.json",
  "AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_TAXONOMY.md",
  "CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_TAXONOMY_STATUS.json",
  "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_CORPUS.json",
  "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_VALIDATOR.json",
  "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_SCHEMA.json",
  "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_GATE.json",
  "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_FINALITY_SEAL.json"
].forEach(file => assert(fs.existsSync(file), `missing file: ${file}`));

const law = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_TAXONOMY_LAW.json");
const taxonomy = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_TAXONOMY.json");
const status = load("CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_TAXONOMY_STATUS.json");
const corpus = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_CORPUS.json");
const validator = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_VALIDATOR.json");
const gate = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_GATE.json");
const finality = load("CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_FINALITY_SEAL.json");
const index = load("CINEMATICUM_CURRENT_STATE_INDEX.json");
const caseState = load("CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json");
const registry = load("CINEMATICUM_OBJECT_REGISTRY.json");

assert(law.object_type === "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_TAXONOMY_LAW", "bad law object_type");
assert(taxonomy.object_type === "CINEMATICUM_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_TAXONOMY", "bad taxonomy object_type");
assert(status.object_type === "CINEMATICUM_CASE_AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_TAXONOMY_STATUS", "bad status object_type");

assert(taxonomy.case_id === CASE_ID, "bad case id");
assert(taxonomy.current_state === CURRENT_STATE, "bad taxonomy current state");
assert(status.current_state === CURRENT_STATE, "bad status current state");

[
  "all_reopening_rejection_reasons_must_be_canonical",
  "validator_may_not_emit_uncatalogued_reopening_rejection_reason",
  "rejection_corpus_must_cover_required_reopening_reason_codes",
  "taxonomy_does_not_create_live_request",
  "taxonomy_does_not_accept_reopening_request",
  "taxonomy_does_not_reopen_intake",
  "taxonomy_does_not_instantiate_authority_objects",
  "taxonomy_does_not_satisfy_authority",
  "taxonomy_does_not_advance_case_state",
  "silent_reopening_forbidden",
  "media_payload_forbidden"
].forEach(key => assert(law.law[key] === true, `law not true: ${key}`));

const codes = taxonomy.canonical_rejection_reasons.map(r => r.code);
assert(codes.length === 9, "wrong canonical code length");
assert(new Set(codes).size === 9, "duplicate canonical code");
assert(codes.every(code => requiredCodes.has(code)), "uncatalogued code present");
assert([...requiredCodes].every(code => codes.includes(code)), "missing required code");

const covered = new Set(taxonomy.covered_rejection_reasons);
const uncovered = new Set(taxonomy.uncovered_rejection_reasons);
assert(covered.size === 5, "bad covered count");
assert(uncovered.size === 4, "bad uncovered count");
assert([...covered].every(code => requiredCodes.has(code)), "bad covered code");
assert([...uncovered].every(code => requiredCodes.has(code)), "bad uncovered code");
assert([...covered].every(code => !uncovered.has(code)), "covered/uncovered overlap");

assert(taxonomy.canonical_rejection_reason_count === 9, "bad canonical count");
assert(status.canonical_rejection_reason_count === 9, "bad status canonical count");
assert(status.covered_rejection_reason_count === 5, "bad status covered count");
assert(status.uncovered_rejection_reason_count === 4, "bad status uncovered count");

assert(new Set(corpus.fixture_rejection_reasons).size === 5, "bad corpus reason size");
assert(corpus.fixture_rejection_reasons.every(code => covered.has(code)), "corpus reason outside covered set");
assert(corpus.canonical_rejection_fixture_count === 5, "bad corpus fixture count");
assert(corpus.fixtures_are_live_requests === false, "fixtures are live");
assert(corpus.all_fixtures_rejected === true, "fixtures not rejected");

const fixtureDir = corpus.fixture_directory;
assert(fs.existsSync(fixtureDir), `missing fixture dir: ${fixtureDir}`);
const fixtureFiles = fs.readdirSync(fixtureDir).filter(name => name.endsWith(".json")).sort();
assert(fixtureFiles.length === 5, "wrong fixture file count");
const fixtureReasons = new Set(fixtureFiles.map(name => load(path.join(fixtureDir, name)).expected_rejection_reason));
assert(fixtureReasons.size === 5, "wrong fixture reason count");
assert([...fixtureReasons].every(code => covered.has(code)), "fixture reason outside taxonomy coverage");

taxonomy.canonical_rejection_reasons.forEach(reason => {
  assert(reason.severity === "fatal", `nonfatal reason: ${reason.code}`);
  assert(typeof reason.meaning === "string" && reason.meaning.length > 0, `missing meaning: ${reason.code}`);
  assert(reason.covered_by_rejection_corpus === covered.has(reason.code), `coverage mismatch: ${reason.code}`);
});

assert(taxonomy.taxonomy_complete_for_current_validator === true, "taxonomy incomplete");
assert(taxonomy.corpus_complete_for_required_reasons === true, "corpus incomplete");
assert(status.taxonomy_complete_for_current_validator === true, "status taxonomy incomplete");
assert(status.corpus_complete_for_required_reasons === true, "status corpus incomplete");

["authority_satisfied", "may_advance_now", "issued", "media_present"].forEach(key => {
  [taxonomy, status, corpus, validator].forEach(obj => assert(obj[key] === false, `${obj.object_type}:${key}`));
});

["live_reopening_request_count", "valid_reopening_request_count", "accepted_reopening_request_count"].forEach(key => {
  [taxonomy, status, corpus, validator].forEach(obj => assert(obj[key] === 0, `${obj.object_type}:${key}`));
});

assert(gate.reopening_gate_open_now === false, "gate open now");
assert(gate.silent_reopening_forbidden === true, "silent reopening not forbidden");
assert(finality.intake_finality_sealed === true, "finality not sealed");
assert(index.active_case_states[CASE_ID] === CURRENT_STATE, "index state drift");
assert(caseState.current_state === CURRENT_STATE, "case state drift");
assert(registry.current_active_state === CURRENT_STATE, "registry state drift");

const md = fs.readFileSync("AUTHORITY_OBJECT_ADMISSION_INTAKE_REOPENING_REQUEST_REJECTION_TAXONOMY.md", "utf8");
[
  "canonical_rejection_reason_count=9",
  "covered_rejection_reason_count=5",
  "uncovered_rejection_reason_count=4",
  "taxonomy_complete_for_current_validator=true",
  "corpus_complete_for_required_reasons=true",
  "fixtures_are_live_requests=false",
  "live_reopening_request_count=0",
  "valid_reopening_request_count=0",
  "accepted_reopening_request_count=0",
  "silent_reopening_forbidden=true",
  "authority_satisfied=false",
  "may_advance_now=false",
  "issued=false",
  "media_present=false"
].forEach(needle => assert(md.includes(needle), `missing README token: ${needle}`));

console.log("CINEMATICUM AUTHORITY OBJECT ADMISSION INTAKE REOPENING REQUEST REJECTION TAXONOMY: PASS");
console.log("CURRENT_STATE=OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED");
console.log("CANONICAL_REJECTION_REASON_COUNT=9");
console.log("COVERED_REJECTION_REASON_COUNT=5");
console.log("UNCOVERED_REJECTION_REASON_COUNT=4");
console.log("TAXONOMY_COMPLETE_FOR_CURRENT_VALIDATOR=true");
console.log("CORPUS_COMPLETE_FOR_REQUIRED_REASONS=true");
console.log("LIVE_REOPENING_REQUEST_COUNT=0");
console.log("VALID_REOPENING_REQUEST_COUNT=0");
console.log("ACCEPTED_REOPENING_REQUEST_COUNT=0");
console.log("AUTHORITY_SATISFIED=false");
console.log("MAY_ADVANCE_NOW=false");
console.log("ISSUED=false");
console.log("MEDIA_PRESENT=false");
NODE

MEDIA_OR_MODEL="$(find . -type f \
  \( -iname '*.mp4' -o -iname '*.mov' -o -iname '*.m4v' -o -iname '*.avi' -o -iname '*.mkv' -o -iname '*.webm' \
     -o -iname '*.wav' -o -iname '*.aiff' -o -iname '*.flac' -o -iname '*.mp3' \
     -o -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.tiff' -o -iname '*.exr' -o -iname '*.dpx' \
     -o -iname '*.ckpt' -o -iname '*.safetensors' -o -iname '*.onnx' -o -iname '*.pt' -o -iname '*.pth' -o -iname '*.gguf' \) \
  -not -path './.git/*' | sort || true)"
test -z "$MEDIA_OR_MODEL"
