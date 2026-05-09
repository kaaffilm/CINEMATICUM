from __future__ import annotations

import json
from pathlib import Path

from cinematicum_studio.issuance_bridge.validate_external_execution import validate_external_execution_ready

CASE_ROOT = Path("CASES")
CREDENTIAL_CUSTODY_RECORD = "CREDENTIAL_CUSTODY_READINESS_RECORD.json"


def validate_credential_custody_ready(case_id: str) -> tuple[bool, list[str]]:
    film_dir = CASE_ROOT / case_id / "FILM"
    missing: list[str] = []

    external_ok, external_missing = validate_external_execution_ready(case_id)
    if not external_ok:
        missing.append("EXTERNAL_EXECUTION_READY_REQUIRED_FOR_CREDENTIAL_CUSTODY")
        missing.extend(f"EXTERNAL_EXECUTION::{item}" for item in external_missing)

    path = film_dir / CREDENTIAL_CUSTODY_RECORD
    if not path.exists():
        missing.append(CREDENTIAL_CUSTODY_RECORD)
    else:
        record = json.loads(path.read_text())
        if record.get("accepted") is not True:
            missing.append("CREDENTIAL_CUSTODY_READINESS_ACCEPTED")
        if record.get("credential_custody_allowed") is not True:
            missing.append("CREDENTIAL_CUSTODY_ALLOWED")
        if record.get("signing_key_use_allowed") is not True:
            missing.append("SIGNING_KEY_USE_ALLOWED")
        if record.get("deploy_key_use_allowed") is not True:
            missing.append("DEPLOY_KEY_USE_ALLOWED")
        if record.get("secret_material_access_allowed") is not True:
            missing.append("SECRET_MATERIAL_ACCESS_ALLOWED")
        if record.get("admin_token_use_allowed") is not True:
            missing.append("ADMIN_TOKEN_USE_ALLOWED")
        if record.get("production_write_credential_allowed") is not True:
            missing.append("PRODUCTION_WRITE_CREDENTIAL_ALLOWED")
        if record.get("release_notarization_allowed") is not True:
            missing.append("RELEASE_NOTARIZATION_ALLOWED")
        if record.get("custody_bearing_automation_allowed") is not True:
            missing.append("CUSTODY_BEARING_AUTOMATION_ALLOWED")

    return (len(missing) == 0, missing)
