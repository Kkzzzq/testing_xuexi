from __future__ import annotations

from typing import Any


def evaluate_evidence_status(route_status: str, scenario_result: dict[str, Any] | None) -> str:
    if route_status == "unroutable" or not scenario_result:
        return "insufficient"

    evidence_points = 0
    if scenario_result.get("http_steps"):
        evidence_points += 1
    if scenario_result.get("snapshot", {}).get("before") or scenario_result.get("snapshot", {}).get("after"):
        evidence_points += 1
    if scenario_result.get("snapshot", {}).get("diff"):
        evidence_points += 1
    if scenario_result.get("intermediate"):
        evidence_points += 1

    if evidence_points >= 3:
        return "sufficient"
    if evidence_points >= 1:
        return "partial"
    return "insufficient"


def evaluate_repro_status(route_status: str, scenario_result: dict[str, Any] | None) -> str:
    if route_status == "unroutable" or not scenario_result:
        return "not_reproduced"
    if scenario_result.get("execution_error"):
        return "repro_failed"
    if scenario_result.get("failure_reproduced"):
        return "reproduced"
    return "not_reproduced"


def evaluate_diagnosis_status(
    route_status: str,
    repro_status: str,
    evidence_status: str,
    scenario_result: dict[str, Any] | None,
) -> str:
    if route_status == "unroutable":
        return "manual_check_required"
    if repro_status == "repro_failed":
        return "manual_check_required"
    if repro_status == "reproduced" and evidence_status == "sufficient":
        return "high_confidence"
    if repro_status == "reproduced" and evidence_status == "partial":
        return "medium_confidence"
    if repro_status == "not_reproduced" and evidence_status in {"sufficient", "partial"}:
        return "low_confidence"
    return "manual_check_required"


def build_case_state(route_status: str, scenario_result: dict[str, Any] | None) -> dict[str, Any]:
    repro_status = evaluate_repro_status(route_status, scenario_result)
    evidence_status = evaluate_evidence_status(route_status, scenario_result)
    diagnosis_status = evaluate_diagnosis_status(route_status, repro_status, evidence_status, scenario_result)
    return {
        "route_status": route_status,
        "repro_status": repro_status,
        "evidence_status": evidence_status,
        "diagnosis_status": diagnosis_status,
    }
