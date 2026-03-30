from __future__ import annotations

import os
import sys
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.agent_allure_reader import build_status_summary, load_allure_cases, select_failed_cases
from tools.agent_environment import AgentEnvironmentManager
from tools.agent_evidence import build_evidence_lines
from tools.agent_llm import maybe_generate_ai_summary
from tools.agent_report import write_reports
from tools.agent_stage_analysis import analyze_replay_result
from tools.agent_state import build_case_state
from tools.agent_test_replays import run_failed_test_replay

MAX_FAILED_CASES = int(os.getenv("FAULT_AGENT_MAX_FAILED_CASES", "20"))


@contextmanager
def managed_agent_environment():
    context = AgentEnvironmentManager.prepare_environment()
    try:
        yield context
    finally:
        AgentEnvironmentManager.cleanup_environment(context)


def _build_ai_case_payload(case_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "test_name": case_result["test_name"],
        "original_failure": case_result.get("original_failure", {}),
        "runtime": case_result.get("runtime", {}),
        "http_steps": case_result.get("http_steps", []),
        "facts": case_result.get("facts", {}),
        "chain_status": case_result.get("chain_status"),
        "first_abnormal_stage": case_result.get("first_abnormal_stage"),
        "suspected_segment": case_result.get("suspected_segment"),
        "confirmed_facts": case_result.get("confirmed_facts", []),
        "excluded_scope": case_result.get("excluded_scope", []),
        "remaining_scope": case_result.get("remaining_scope", []),
        "manual_checks": case_result.get("manual_checks", []),
        "snapshot": case_result.get("snapshot", {}),
        "evidence_lines": case_result.get("evidence_lines", []),
    }


def run_agent() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    allure_cases = load_allure_cases()
    allure_summary = build_status_summary(allure_cases)
    failed_cases = select_failed_cases(allure_cases, limit=MAX_FAILED_CASES)

    case_results: list[dict[str, Any]] = []
    for case in failed_cases:
        replay_target = case.replay_test_name
        with managed_agent_environment() as context:
            replay_result = run_failed_test_replay(replay_target, context)

        analysis = analyze_replay_result(replay_result)
        enriched_replay_result = {**replay_result, **analysis}
        evidence_lines = build_evidence_lines(enriched_replay_result)
        state = build_case_state(enriched_replay_result)

        case_results.append(
            {
                "test_name": case.name,
                "full_name": case.full_name,
                "replay_target": replay_target,
                "state": state,
                "facts": enriched_replay_result.get("facts", {}),
                "stage_results": enriched_replay_result.get("stage_results", {}),
                "reproduced_original_failure": enriched_replay_result.get("reproduced_original_failure", False),
                "chain_status": enriched_replay_result.get("chain_status"),
                "first_abnormal_stage": enriched_replay_result.get("first_abnormal_stage"),
                "suspected_segment": enriched_replay_result.get("suspected_segment"),
                "confirmed_facts": enriched_replay_result.get("confirmed_facts", []),
                "excluded_scope": enriched_replay_result.get("excluded_scope", []),
                "remaining_scope": enriched_replay_result.get("remaining_scope", []),
                "manual_checks": enriched_replay_result.get("manual_checks", []),
                "evidence_lines": evidence_lines,
                "snapshot": replay_result.get("snapshot", {}),
                "snapshot_diff": replay_result.get("snapshot", {}).get("diff", {}),
                "original_failure": {"message": case.message, "trace": case.trace},
                "runtime": replay_result.get("runtime", {}),
                "http_steps": replay_result.get("http_steps", []),
                "intermediate": replay_result.get("intermediate", {}),
                "execution_error": replay_result.get("execution_error"),
            }
        )

    replay_status_counter = Counter(item["state"]["replay_status"] for item in case_results)
    chain_counter = Counter(item.get("chain_status") for item in case_results if item.get("chain_status"))
    summary = {
        "allure": allure_summary,
        "replayed_cases": sum(1 for item in case_results if item["state"]["replay_status"] != "unsupported_test"),
        "reproduced_original_failures": sum(1 for item in case_results if item.get("reproduced_original_failure")),
        "chain_interrupted_cases": chain_counter.get("interrupted", 0),
        "replay_status_count": dict(replay_status_counter),
    }
    return summary, case_results


def main() -> None:
    summary, case_results = run_agent()
    ai_payload = {
        "run_observations": {
            "failed_or_broken_cases": summary["allure"]["failed_or_broken"],
            "diagnostic_case_count": len(case_results),
            "reproduced_original_failures": summary["reproduced_original_failures"],
        },
        "cases": [_build_ai_case_payload(item) for item in case_results],
    }
    ai_summary = maybe_generate_ai_summary(ai_payload)
    write_reports(summary, case_results, ai_summary)


if __name__ == "__main__":
    main()
