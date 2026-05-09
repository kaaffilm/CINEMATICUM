from __future__ import annotations

import argparse
import json
from pathlib import Path

from cinematicum_studio.core.db import connect, init_db
from cinematicum_studio.generation.job_runner import generate_all, generate_shot
from cinematicum_studio.issuance_bridge.validate_master import validate_master_ready
from cinematicum_studio.issuance_bridge.validate_admissibility import validate_admissible_motion_picture
from cinematicum_studio.issuance_bridge.validate_acceptance import validate_cinematic_acceptance
from cinematicum_studio.issuance_bridge.validate_postproduction import validate_postproduction_acceptance
from cinematicum_studio.issuance_bridge.validate_issuance import validate_issuance_ready
from cinematicum_studio.issuance_bridge.validate_state_advancement import validate_state_advancement
from cinematicum_studio.issuance_bridge.validate_publication import validate_publication_ready
from cinematicum_studio.issuance_bridge.validate_distribution import validate_distribution_ready
from cinematicum_studio.issuance_bridge.validate_release_artifact import validate_release_artifact_ready
from cinematicum_studio.issuance_bridge.validate_permanence import validate_permanence_ready
from cinematicum_studio.issuance_bridge.validate_public_index import validate_public_index_ready
from cinematicum_studio.issuance_bridge.validate_public_claim import validate_public_claim_ready
from cinematicum_studio.issuance_bridge.validate_audience_surface import validate_audience_surface_ready
from cinematicum_studio.issuance_bridge.validate_exhibition import validate_exhibition_ready
from cinematicum_studio.issuance_bridge.validate_screening_event import validate_screening_event_ready
from cinematicum_studio.issuance_bridge.validate_audience_attendance import validate_audience_attendance_ready
from cinematicum_studio.issuance_bridge.validate_audience_reception import validate_audience_reception_ready
from cinematicum_studio.render.render_master import render_master
from cinematicum_studio.review.select_take import select_take
from cinematicum_studio.timeline.build_otio import build_timeline


def load_case_film_state(case_id: str) -> dict:
    path = Path("CASES") / case_id / "FILM" / "FILM_STATE.json"
    return json.loads(path.read_text())


def cmd_bootstrap_case(args: argparse.Namespace) -> None:
    init_db()

    case_id = args.case_id
    film_state = load_case_film_state(case_id)
    scene_graph = json.loads((Path("CASES") / case_id / "FILM" / "SCENE_GRAPH.json").read_text())
    shot_graph = json.loads((Path("CASES") / case_id / "FILM" / "SHOT_GRAPH.json").read_text())

    conn = connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO film_cases (id, title, state) VALUES (?, ?, ?)",
            (case_id, film_state["title"], "PRODUCTION"),
        )

        for scene in scene_graph["scenes"]:
            conn.execute(
                "INSERT OR REPLACE INTO scenes (id, case_id, title, scene_order, dramatic_function) VALUES (?, ?, ?, ?, ?)",
                (scene["id"], case_id, scene["title"], scene["order"], scene["dramatic_function"]),
            )

        for shot in shot_graph["shots"]:
            conn.execute(
                "INSERT OR REPLACE INTO shots (id, case_id, scene_id, shot_order, duration, prompt, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (shot["id"], case_id, shot["scene_id"], shot["order"], shot["duration"], shot["prompt"], "PLANNED"),
            )

        conn.commit()
    finally:
        conn.close()

    print(f"BOOTSTRAPPED {case_id}")


def cmd_init_db(args: argparse.Namespace) -> None:
    path = init_db()
    print(path)


def cmd_generate_shot(args: argparse.Namespace) -> None:
    results = generate_shot(args.case_id, args.shot_id, args.takes, backend=args.backend)
    print(json.dumps(results, indent=2))


def cmd_generate_all(args: argparse.Namespace) -> None:
    generate_all(args.case_id, args.takes_per_shot, backend=args.backend)
    print(f"GENERATED_ALL {args.case_id}")


def cmd_select_take(args: argparse.Namespace) -> None:
    path = select_take(args.case_id, args.shot_id, args.take_id)
    print(path)


def cmd_timeline_build(args: argparse.Namespace) -> None:
    path = build_timeline(args.case_id)
    print(path)


def cmd_render(args: argparse.Namespace) -> None:
    path = render_master(args.case_id, args.version)
    print(path)



def cmd_admissibility_check(args: argparse.Namespace) -> None:
    ok, missing = validate_admissible_motion_picture(args.case_id)
    print(json.dumps({
        "case_id": args.case_id,
        "admissible_motion_picture": ok,
        "missing": missing,
    }, indent=2))

def cmd_issue_check(args: argparse.Namespace) -> None:
    ok, missing = validate_master_ready(args.case_id)
    print(json.dumps({"case_id": args.case_id, "master_ready": ok, "missing": missing}, indent=2))
    raise SystemExit(0 if ok else 1)



def cmd_acceptance_check(args):
    ok, missing = validate_cinematic_acceptance(args.case_id)
    print(json.dumps({
        "case_id": args.case_id,
        "cinematic_acceptance": ok,
        "missing": missing,
    }, indent=2))


def cmd_postproduction_check(args):
    ok, missing = validate_postproduction_acceptance(args.case_id)
    print(json.dumps({
        "case_id": args.case_id,
        "postproduction_acceptance": ok,
        "missing": missing,
    }, indent=2))



def cmd_issuance_check(args):
    ok, missing = validate_issuance_ready(args.case_id)
    print(json.dumps({
        "case_id": args.case_id,
        "issuance_ready": ok,
        "missing": missing,
    }, indent=2))


def cmd_state_advancement_check(args):
    ok, missing = validate_state_advancement(args.case_id, args.target_state)
    print(json.dumps({
        "case_id": args.case_id,
        "target_state": args.target_state,
        "state_advancement_allowed": ok,
        "missing": missing,
    }, indent=2))

def cmd_publication_check(args):
    ok, missing = validate_publication_ready(args.case_id)
    print(json.dumps({
        "case_id": args.case_id,
        "publication_ready": ok,
        "missing": missing,
    }, indent=2))


def cmd_distribution_check(args):
    ok, missing = validate_distribution_ready(args.case_id)
    print(json.dumps({
        "case_id": args.case_id,
        "distribution_ready": ok,
        "missing": missing,
    }, indent=2))


def cmd_release_artifact_check(args):
    ok, missing = validate_release_artifact_ready(args.case_id)
    print(json.dumps({
        "case_id": args.case_id,
        "release_artifact_ready": ok,
        "missing": missing,
    }, indent=2))


def cmd_permanence_check(args):
    ok, missing = validate_permanence_ready(args.case_id)
    print(json.dumps({
        "case_id": args.case_id,
        "permanence_ready": ok,
        "missing": missing,
    }, indent=2))


def cmd_public_index_check(args):
    ok, missing = validate_public_index_ready(args.case_id)
    print(json.dumps({
        "case_id": args.case_id,
        "public_index_ready": ok,
        "missing": missing,
    }, indent=2))


def cmd_public_claim_check(args):
    ok, missing = validate_public_claim_ready(args.case_id)
    print(json.dumps({
        "case_id": args.case_id,
        "public_claim_ready": ok,
        "missing": missing,
    }, indent=2))


def cmd_audience_surface_check(args):
    ok, missing = validate_audience_surface_ready(args.case_id)
    print(json.dumps({
        "case_id": args.case_id,
        "audience_surface_ready": ok,
        "missing": missing,
    }, indent=2))


def cmd_exhibition_check(args):
    ok, missing = validate_exhibition_ready(args.case_id)
    print(json.dumps({
        "case_id": args.case_id,
        "exhibition_ready": ok,
        "missing": missing,
    }, indent=2))


def cmd_screening_event_check(args):
    ok, missing = validate_screening_event_ready(args.case_id)
    print(json.dumps({
        "case_id": args.case_id,
        "screening_event_ready": ok,
        "missing": missing,
    }, indent=2))


def cmd_audience_attendance_check(args):
    ok, missing = validate_audience_attendance_ready(args.case_id)
    print(json.dumps({
        "case_id": args.case_id,
        "audience_attendance_ready": ok,
        "missing": missing,
    }, indent=2))


def cmd_audience_reception_check(args):
    ok, missing = validate_audience_reception_ready(args.case_id)
    print(json.dumps({
        "case_id": args.case_id,
        "audience_reception_ready": ok,
        "missing": missing,
    }, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(prog="cinematicum")
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("init-db")
    p.set_defaults(func=cmd_init_db)

    p = sub.add_parser("bootstrap-case")
    p.add_argument("case_id")
    p.set_defaults(func=cmd_bootstrap_case)

    p = sub.add_parser("generate-shot")
    p.add_argument("case_id")
    p.add_argument("shot_id")
    p.add_argument("--takes", type=int, default=1)
    p.add_argument("--backend", default="command")
    p.set_defaults(func=cmd_generate_shot)

    p = sub.add_parser("generate-all")
    p.add_argument("case_id")
    p.add_argument("--takes-per-shot", type=int, default=5)
    p.add_argument("--backend", default="command")
    p.set_defaults(func=cmd_generate_all)

    p = sub.add_parser("select-take")
    p.add_argument("case_id")
    p.add_argument("shot_id")
    p.add_argument("take_id")
    p.set_defaults(func=cmd_select_take)

    p = sub.add_parser("timeline-build")
    p.add_argument("case_id")
    p.set_defaults(func=cmd_timeline_build)

    p = sub.add_parser("render")
    p.add_argument("case_id")
    p.add_argument("--version", default="v001")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("issue-check")
    p.add_argument("case_id")
    p.set_defaults(func=cmd_issue_check)

    p = sub.add_parser("acceptance-check")
    p.add_argument("case_id")
    p.set_defaults(func=cmd_acceptance_check)

    p = sub.add_parser("postproduction-check")
    p.add_argument("case_id")
    p.set_defaults(func=cmd_postproduction_check)

    p = sub.add_parser("admissibility-check")
    p.add_argument("case_id")
    p.set_defaults(func=cmd_admissibility_check)

    p = sub.add_parser("issuance-check")
    p.add_argument("case_id")
    p.set_defaults(func=cmd_issuance_check)

    p = sub.add_parser("publication-check")
    p.add_argument("case_id")
    p.set_defaults(func=cmd_publication_check)

    p = sub.add_parser("distribution-check")
    p.add_argument("case_id")
    p.set_defaults(func=cmd_distribution_check)

    p = sub.add_parser("release-artifact-check")
    p.add_argument("case_id")
    p.set_defaults(func=cmd_release_artifact_check)

    p = sub.add_parser("permanence-check")
    p.add_argument("case_id")
    p.set_defaults(func=cmd_permanence_check)

    p = sub.add_parser("public-index-check")
    p.add_argument("case_id")
    p.set_defaults(func=cmd_public_index_check)

    p = sub.add_parser("public-claim-check")
    p.add_argument("case_id")
    p.set_defaults(func=cmd_public_claim_check)

    p = sub.add_parser("audience-surface-check")
    p.add_argument("case_id")
    p.set_defaults(func=cmd_audience_surface_check)

    p = sub.add_parser("exhibition-check")
    p.add_argument("case_id")
    p.set_defaults(func=cmd_exhibition_check)

    p = sub.add_parser("screening-event-check")
    p.add_argument("case_id")
    p.set_defaults(func=cmd_screening_event_check)

    p = sub.add_parser("audience-attendance-check")
    p.add_argument("case_id")
    p.set_defaults(func=cmd_audience_attendance_check)

    p = sub.add_parser("audience-reception-check")
    p.add_argument("case_id")
    p.set_defaults(func=cmd_audience_reception_check)

    p = sub.add_parser("state-advancement-check")
    p.add_argument("case_id")
    p.add_argument("target_state")
    p.set_defaults(func=cmd_state_advancement_check)


    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
