import fs from "node:fs";
import process from "node:process";

function fail(message) {
  console.error(`FAIL=${message}`);
  process.exit(1);
}

const path =
  "AUTHORITY/CINEMATICUM_PRODUCTION_REPOSITORY_AUTHORITY_ACKNOWLEDGEMENT.json";

const ack = JSON.parse(
  fs.readFileSync(path, "utf8")
);

if (
  ack.object_type !==
  "CINEMATICUM_PRODUCTION_REPOSITORY_AUTHORITY_ACKNOWLEDGEMENT"
) fail("OBJECT_TYPE");

if (ack.schema_version !== "1.0.0") fail("SCHEMA");

if (ack.jurisdiction !== "CINEMATICUM") fail("JURISDICTION");

if (
  ack.acknowledgement_stage !==
  "RECIPROCAL_PRODUCTION_REPOSITORY_ACKNOWLEDGEMENT"
) fail("ACK_STAGE");

if (
  ack.production_replay_track.repository !==
  "kaaffilm/CINEMATICUM"
) fail("PRODUCTION_REPOSITORY");

if (
  ack.production_replay_track.acknowledged_base_head !==
  "e4c4afccce1d2bd8ec280c5eb0d177142ec1c82d"
) fail("PRODUCTION_BASE");

if (
  ack.production_replay_track.role !==
  "CANONICAL_PINNED_PRODUCTION_REPLAY_ARTIFACT_TRACK"
) fail("PRODUCTION_ROLE");

if (
  ack.production_replay_track.truth_authority !== false
) fail("PRODUCTION_TRUTH_AUTHORITY");

if (
  ack.production_replay_track.admissibility_authority !== false
) fail("PRODUCTION_ADMISSIBILITY_AUTHORITY");

if (
  ack.production_replay_track
    .admissible_motion_picture_issuance_authority !== false
) fail("PRODUCTION_ISSUANCE_AUTHORITY");

if (
  ack.issuance_jurisdiction.repository !==
  "CINEMATICUM/CINEMATICUM"
) fail("ISSUANCE_REPOSITORY");

if (
  ack.issuance_jurisdiction.accepted_merge_sha !==
  "517fd51f43ae8a17db219da352f5b83998d45fbd"
) fail("ISSUANCE_MERGE");

if (
  ack.issuance_jurisdiction.accepted_candidate_head !==
  "94ead911b0868b0458b3af22f5af711c43291a26"
) fail("ISSUANCE_CANDIDATE");

if (
  ack.issuance_jurisdiction.authority_binding_blob !==
  "1b3c1a0da80aa4055193f13c4063eae4e3b060dc"
) fail("ISSUANCE_AUTHORITY_BLOB");

if (
  ack.issuance_jurisdiction.authority_binding_sha256 !==
  "f2966e7e2b758cf5c6355db0bf8d8587bcfad750fd30f3bfef77b40434593e41"
) fail("ISSUANCE_AUTHORITY_SHA256");

if (
  ack.issuance_jurisdiction.role !==
  "CANONICAL_ISSUANCE_JURISDICTION"
) fail("ISSUANCE_ROLE");

if (
  ack.case_001.case_id !==
  "CASE_001_THE_LAST_RENDER"
) fail("CASE_ID");

if (
  ack.case_001.acknowledged_issuance_status !==
  "CASE_OPEN_NOT_ISSUED"
) fail("CASE_STATUS");

if (
  ack.case_001.production_artifact.sha256 !==
  "f23d3da43ed0dfc0a4f97b7c6ad722107cc2531ac584780424ace2c45ff5a192"
) fail("GODCUT_SHA256");

if (
  ack.case_001.production_artifact_implies_admissibility !== false
) fail("ARTIFACT_ADMISSIBILITY_BOUNDARY");

if (
  ack.case_001
    .production_replay_success_implies_admissible_motion_picture_issuance !==
  false
) fail("REPLAY_ISSUANCE_BOUNDARY");

if (
  ack.case_001
    .compiler_cut_artifact_issuance_is_not_admissible_motion_picture_issuance !==
  true
) fail("COMPILER_CUT_ISSUANCE_DISTINCTION");

if (
  ack.reciprocal_binding
    .issuance_authority_declaration_accepted !== true
) fail("ISSUANCE_DECLARATION_NOT_ACCEPTED");

if (
  ack.reciprocal_binding
    .production_repository_acknowledgement_this_object !== true
) fail("ACK_OBJECT");

if (
  ack.reciprocal_binding
    .acknowledgement_effective_when_merged_to_production_main !== true
) fail("ACK_EFFECT");

if (
  ack.governance_transition
    .pre_merge_full_cross_repository_canonicality_resolved !== false
) fail("PREMATURE_CANONICALITY");

if (
  ack.governance_transition
    .pre_merge_adapter_implementation_eligible !== false
) fail("PREMATURE_ADAPTER");

if (
  ack.governance_transition
    .on_accepted_merge_full_cross_repository_canonicality_resolved !== true
) fail("MERGE_CANONICALITY_EFFECT");

if (
  ack.governance_transition
    .on_accepted_merge_adapter_implementation_eligible !== true
) fail("MERGE_ADAPTER_EFFECT");

if (
  ack.adapter_boundary.source_merge_allowed !== false
) fail("SOURCE_MERGE_BOUNDARY");

if (
  ack.adapter_boundary.kaaffilm_is_issuance_authority !== false
) fail("KAAFFILM_ISSUANCE_AUTHORITY");

if (
  ack.adapter_boundary.adapter_only_integration_required !== true
) fail("ADAPTER_ONLY_BOUNDARY");

if (
  ack.prohibited_operations.repository_delete_authorized !== false
) fail("DELETE_BOUNDARY");

if (
  ack.prohibited_operations.repository_archive_authorized !== false
) fail("ARCHIVE_BOUNDARY");

if (
  ack.prohibited_operations.history_rewrite_authorized !== false
) fail("HISTORY_REWRITE_BOUNDARY");

if (
  ack.prohibited_operations.source_merge_authorized !== false
) fail("SOURCE_MERGE_AUTHORIZATION");

if (
  ack.prohibited_operations.case_status_mutation_authorized !== false
) fail("CASE_STATUS_MUTATION");

console.log(
  "CINEMATICUM_PRODUCTION_AUTHORITY_ACKNOWLEDGEMENT=PASS"
);
console.log(
  "PRODUCTION_REPLAY_TRACK=kaaffilm/CINEMATICUM"
);
console.log(
  "ISSUANCE_JURISDICTION=CINEMATICUM/CINEMATICUM"
);
console.log(
  "ISSUANCE_AUTHORITY_MERGE=517fd51f43ae8a17db219da352f5b83998d45fbd"
);
console.log(
  "CASE_STATUS=CASE_OPEN_NOT_ISSUED"
);
console.log(
  "PRODUCTION_ADMISSIBILITY_AUTHORITY=false"
);
console.log(
  "PRODUCTION_ADMISSIBLE_MOTION_PICTURE_ISSUANCE_AUTHORITY=false"
);
console.log(
  "SOURCE_MERGE_ALLOWED=false"
);
console.log(
  "ACKNOWLEDGEMENT_EFFECTIVE_ON_MERGE=true"
);
console.log(
  "FULL_CROSS_REPOSITORY_CANONICALITY_RESOLVES_ON_MERGE=true"
);
console.log(
  "KAAFFILM_ADAPTER_ELIGIBLE_AFTER_ACK_MERGE=true"
);
