#!/usr/bin/env node
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync, statSync } from "node:fs";

const CASE_ID = "CASE_001_THE_LAST_RENDER";
const directionDir = `CASES/${CASE_ID}/DIRECTION`;
const proofDir = `CASES/${CASE_ID}/PROOFS`;

const godcutVerificationPath = `CASES/${CASE_ID}/PROOFS/godcut-verification-result.json`;
const godcutCompilePath = `CASES/${CASE_ID}/PROOFS/godcut-compile-result.json`;
const godstudioManifestPath = "STUDIO/CASE_001_GODCUT/studio-manifest.json";

function assert(cond, msg) {
  if (!cond) throw new Error(`CINEMATICUM_DIRECTOR_ENGINE_REJECTED: ${msg}`);
}
function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}
function sha256(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}
function writeJson(path, obj) {
  writeFileSync(path, JSON.stringify(obj, null, 2) + "\n");
}
function objectRecord(path) {
  return {
    path,
    sha256: sha256(path),
    size_bytes: statSync(path).size
  };
}

for (const path of [godcutVerificationPath, godcutCompilePath, godstudioManifestPath]) {
  assert(existsSync(path), `missing required upstream proof: ${path}`);
}

const godcutVerification = readJson(godcutVerificationPath);
const godstudioManifest = readJson(godstudioManifestPath);

assert(godcutVerification.valid === true, "GODCUT verification invalid");
assert(godcutVerification.proves_compiler_generated_film === true, "GODCUT compiler proof missing");
assert(godcutVerification.proves_film_issued === true, "GODCUT issuance proof missing");
assert(godcutVerification.proves_truth === false, "GODCUT truth overclaim");
assert(godcutVerification.proves_admissibility === false, "GODCUT admissibility overclaim");
assert(godcutVerification.proves_external_reality === false, "GODCUT external reality overclaim");
assert(godstudioManifest.proves_studio_surface_exists === true, "GODSTUDIO proof missing");

const artifactPath = godcutVerification.artifact_path;
assert(existsSync(artifactPath), `missing film artifact: ${artifactPath}`);
assert(sha256(artifactPath) === godcutVerification.artifact_sha256, "film artifact sha mismatch");

mkdirSync("ENGINES/DIRECTOR", { recursive: true });
mkdirSync(directionDir, { recursive: true });
mkdirSync(proofDir, { recursive: true });

const standardPath = "ENGINES/DIRECTOR/DIRECTOR_ENGINE_STANDARD.json";
const principlesPath = `${directionDir}/DIRECTORIAL_PRINCIPLES.json`;
const shotGrammarPath = `${directionDir}/SHOT_GRAMMAR.json`;
const cameraLawPath = `${directionDir}/CAMERA_LAW.json`;
const cutRhythmLawPath = `${directionDir}/CUT_RHYTHM_LAW.json`;
const scoreLawPath = `${directionDir}/SCORE_LAW.json`;
const decisionGraphPath = `${directionDir}/DIRECTOR_DECISION_GRAPH.json`;
const manifestPath = `${directionDir}/DIRECTOR_ENGINE_MANIFEST.json`;
const resultPath = `${proofDir}/director-engine-build-result.json`;

const standard = {
  object_type: "CINEMATICUM_DIRECTOR_ENGINE_STANDARD",
  schema_version: "0.9.0",
  jurisdiction: "CINEMATICUM",
  purpose: "Convert an issued compiler film from a binary artifact into a machine-verifiable directed work.",
  required_laws: [
    "directorial_principles",
    "shot_grammar",
    "camera_law",
    "cut_rhythm_law",
    "score_law",
    "director_decision_graph"
  ],
  prohibited_inputs: [
    "external API",
    "external media",
    "manual media selection",
    "candidate selection",
    "unverified binary artifact",
    "truth claim",
    "admissibility claim",
    "external reality claim"
  ],
  required_outputs: [
    "director engine manifest",
    "hash-bound direction objects",
    "proof of linkage to issued GODCUT artifact",
    "explicit non-truth boundary"
  ],
  proves_director_engine_exists: true,
  proves_truth: false,
  proves_admissibility: false,
  proves_external_reality: false
};

const principles = {
  object_type: "CINEMATICUM_DIRECTORIAL_PRINCIPLES",
  schema_version: "0.9.0",
  case_id: CASE_ID,
  film_title: "THE LAST RENDER",
  governing_sentence: "The last witness does not survive the collapse; he becomes the only frame the collapse cannot erase.",
  emotional_axis: [
    "abandonment",
    "recognition",
    "machine memory",
    "witness burden",
    "terminal authorship"
  ],
  negative_law: [
    "No shot may exist as decoration only.",
    "No transition may hide a missing causal relation.",
    "No image may claim external reality.",
    "No proof object may claim truth or admissibility."
  ],
  directorial_target: "Every shot must increase witness pressure or reduce epistemic escape.",
  proves_directorial_intent: true,
  proves_truth: false,
  proves_admissibility: false,
  proves_external_reality: false
};

const shots = [
  ["S001", "Dead Render Facility", "establish terminal architecture", "slow inward drift", "low drone / cold harmonic"],
  ["S002", "Signal Corridor", "introduce corrupted path", "lateral tracking", "granular pulse"],
  ["S003", "Witness Aperture", "isolate the admissible eye", "micro push-in", "single sine witness tone"],
  ["S004", "Burned Timeline", "show erased continuity", "fragmented parallax", "broken clock rhythm"],
  ["S005", "Memory Furnace", "turn loss into image pressure", "vertical rise", "sub-bass expansion"],
  ["S006", "Black Gate", "test refusal boundary", "locked symmetrical hold", "near silence"],
  ["S007", "Recovered Frame", "materialize first proof", "hard cut from void", "sharp transient"],
  ["S008", "False World Rejected", "deny external-reality overclaim", "reverse dolly", "descending minor interval"],
  ["S009", "Last Witness", "bind subject to record", "centered close authority", "heartbeat-form pulse"],
  ["S010", "Terminal Render", "complete issuance without truth claim", "final stillness", "resolved low chord"]
].map(([id, title, function_, camera_motion, score_cue], index) => ({
  shot_id: id,
  order: index + 1,
  title,
  duration_seconds: 6,
  function: function_,
  camera_motion,
  score_cue,
  admissible_role: "cinematic function only",
  proves_truth: false,
  proves_admissibility: false,
  proves_external_reality: false
}));

const shotGrammar = {
  object_type: "CINEMATICUM_SHOT_GRAMMAR",
  schema_version: "0.9.0",
  case_id: CASE_ID,
  total_shots: shots.length,
  shot_duration_rule: "Each shot must have a defined dramatic function, camera behavior, and score cue.",
  shots,
  forbidden_shot_states: [
    "decorative-only shot",
    "unmotivated cut",
    "external reality assertion",
    "truth assertion",
    "admissibility assertion"
  ],
  proves_shot_grammar_exists: true,
  proves_truth: false,
  proves_admissibility: false,
  proves_external_reality: false
};

const cameraLaw = {
  object_type: "CINEMATICUM_CAMERA_LAW",
  schema_version: "0.9.0",
  case_id: CASE_ID,
  camera_axioms: [
    "Camera motion is evidence pressure, not ornament.",
    "Symmetry means jurisdiction.",
    "Drift means uncertainty.",
    "Stillness means terminal recognition.",
    "Reverse motion means rejected claim."
  ],
  allowed_motion_classes: [
    "slow_inward_drift",
    "lateral_tracking",
    "micro_push_in",
    "fragmented_parallax",
    "vertical_rise",
    "locked_symmetrical_hold",
    "hard_cut_from_void",
    "reverse_dolly",
    "centered_close_authority",
    "terminal_stillness"
  ],
  disallowed_motion_classes: [
    "random shake",
    "style-only orbit",
    "unmotivated zoom",
    "decorative pan"
  ],
  proves_camera_law_exists: true,
  proves_truth: false,
  proves_admissibility: false,
  proves_external_reality: false
};

const cutRhythmLaw = {
  object_type: "CINEMATICUM_CUT_RHYTHM_LAW",
  schema_version: "0.9.0",
  case_id: CASE_ID,
  total_duration_seconds: godcutVerification.duration_seconds,
  frame_count: godcutVerification.frame_count,
  fps: 24,
  rhythm: [
    { segment: "opening", shots: ["S001", "S002"], function: "orientation under pressure" },
    { segment: "wound", shots: ["S003", "S004", "S005"], function: "continuity damage" },
    { segment: "refusal", shots: ["S006", "S007", "S008"], function: "claim filtering" },
    { segment: "witness", shots: ["S009", "S010"], function: "terminal recognition" }
  ],
  cut_rule: "Cuts must move from spatial condition to epistemic consequence.",
  forbidden_cut_states: [
    "montage without causal pressure",
    "beauty cut without function",
    "transition that hides missing proof"
  ],
  proves_cut_rhythm_law_exists: true,
  proves_truth: false,
  proves_admissibility: false,
  proves_external_reality: false
};

const scoreLaw = {
  object_type: "CINEMATICUM_SCORE_LAW",
  schema_version: "0.9.0",
  case_id: CASE_ID,
  score_axioms: [
    "Sound may intensify witness pressure.",
    "Sound may not certify truth.",
    "Silence is an admissible cut state.",
    "A resolved chord may close issuance but not external reality."
  ],
  cue_map: shots.map((s) => ({
    shot_id: s.shot_id,
    cue: s.score_cue,
    proves_truth: false
  })),
  procedural_audio_required: true,
  external_audio_forbidden: true,
  proves_score_law_exists: true,
  proves_truth: false,
  proves_admissibility: false,
  proves_external_reality: false
};

const decisionGraph = {
  object_type: "CINEMATICUM_DIRECTOR_DECISION_GRAPH",
  schema_version: "0.9.0",
  case_id: CASE_ID,
  nodes: [
    { id: "film_thesis", type: "thesis", value: principles.governing_sentence },
    ...shots.map((s) => ({ id: s.shot_id, type: "shot", value: s.function })),
    { id: "boundary", type: "negative_claim_boundary", value: "No truth, admissibility, or external reality claim." },
    { id: "issued_artifact", type: "binary_artifact", value: artifactPath, sha256: godcutVerification.artifact_sha256 }
  ],
  edges: [
    ...shots.slice(0, -1).map((s, i) => ({
      from: s.shot_id,
      to: shots[i + 1].shot_id,
      relation: "causal_cinematic_pressure"
    })),
    { from: "film_thesis", to: "S001", relation: "initiates" },
    { from: "S010", to: "issued_artifact", relation: "materializes_as" },
    { from: "boundary", to: "issued_artifact", relation: "limits_claim_scope" }
  ],
  graph_invariants: [
    "Every shot node has a function.",
    "Every shot node has a camera behavior.",
    "Every shot node has a score cue.",
    "No node proves truth.",
    "No node proves admissibility.",
    "No node proves external reality."
  ],
  proves_director_decision_graph_exists: true,
  proves_truth: false,
  proves_admissibility: false,
  proves_external_reality: false
};

writeJson(standardPath, standard);
writeJson(principlesPath, principles);
writeJson(shotGrammarPath, shotGrammar);
writeJson(cameraLawPath, cameraLaw);
writeJson(cutRhythmLawPath, cutRhythmLaw);
writeJson(scoreLawPath, scoreLaw);
writeJson(decisionGraphPath, decisionGraph);

const directionObjects = [
  standardPath,
  principlesPath,
  shotGrammarPath,
  cameraLawPath,
  cutRhythmLawPath,
  scoreLawPath,
  decisionGraphPath
];

const manifest = {
  object_type: "CINEMATICUM_DIRECTOR_ENGINE_MANIFEST",
  schema_version: "0.9.0",
  jurisdiction: "CINEMATICUM",
  case_id: CASE_ID,
  status: "DIRECTOR_ENGINE_LOCKED",
  issued_artifact: {
    path: artifactPath,
    sha256: godcutVerification.artifact_sha256,
    size_bytes: statSync(artifactPath).size,
    width: godcutVerification.width,
    height: godcutVerification.height,
    duration_seconds: godcutVerification.duration_seconds,
    frame_count: godcutVerification.frame_count,
    shots: godcutVerification.shots
  },
  upstream_proofs: [
    objectRecord(godcutVerificationPath),
    objectRecord(godcutCompilePath),
    objectRecord(godstudioManifestPath)
  ],
  direction_objects: directionObjects.map(objectRecord),
  director_engine_capabilities: [
    "shot-function grammar",
    "camera-motion law",
    "cut-rhythm law",
    "score-cue law",
    "decision graph",
    "binary artifact linkage",
    "claim-boundary enforcement"
  ],
  external_api_used: false,
  external_media_used: false,
  manual_media_selection_used: false,
  candidate_selection_used: false,
  network_runtime_required: false,
  proves_director_engine_exists: true,
  proves_compiler_generated_film: true,
  proves_film_issued: true,
  proves_truth: false,
  proves_admissibility: false,
  proves_external_reality: false
};

writeJson(manifestPath, manifest);

const result = {
  object_type: "CINEMATICUM_DIRECTOR_ENGINE_BUILD_RESULT",
  schema_version: "0.9.0",
  jurisdiction: "CINEMATICUM",
  case_id: CASE_ID,
  valid: true,
  manifest_path: manifestPath,
  manifest_sha256: sha256(manifestPath),
  direction_object_count: directionObjects.length,
  artifact_path: artifactPath,
  artifact_sha256: godcutVerification.artifact_sha256,
  shots: godcutVerification.shots,
  duration_seconds: godcutVerification.duration_seconds,
  external_api_used: false,
  external_media_used: false,
  manual_media_selection_used: false,
  candidate_selection_used: false,
  network_runtime_required: false,
  proves_director_engine_exists: true,
  proves_compiler_generated_film: true,
  proves_film_issued: true,
  proves_truth: false,
  proves_admissibility: false,
  proves_external_reality: false
};

writeJson(resultPath, result);
console.log(JSON.stringify(result, null, 2));
