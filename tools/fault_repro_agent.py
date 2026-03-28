from __future__ import annotations

import os
import sys
from pathlib import Path
from collections import Counter
from contextlib import contextmanager
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.agent_allure_reader import build_status_summary, load_allure_cases, select_failed_cases
from tools.agent_case_router import route_case
from tools.agent_environment import AgentEnvironmentManager
from tools.agent_evidence import build_evidence_lines, derive_likely_layer
from tools.agent_llm import maybe_generate_ai_summary
from tools.agent_report import write_reports
from tools.agent_scenarios import run_standard_scenario
from tools.agent_state import build_case_state

MAX_FAILED_CASES = int(os.getenv("FAULT_AGENT_MAX_FAILED_CASES", "20"))


@contextmanager
def managed_agent_environment():
    context = AgentEnvironmentManager.prepare_environment()
    try:
        yield context
    finally:
        AgentEnvironmentManager.cleanup_environment(context)


def _build_next_actions(likely_layer: str, anomalies: list[str], diagnosis_status: str) -> list[str]:
    actions: list[str] = []
    if diagnosis_status == "manual_check_required":
        actions.append("先人工确认该失败是否属于已有标准场景，必要时补新的 fault_scenario 元数据。")
    if likely_layer == "database":
        actions.extend([
            "检查 Dashboard Hub 对应表中的实际落库结果和唯一约束是否符合预期。",
            "检查事务提交、删除后残留数据和 view_count 更新逻辑。",
        ])
    elif likely_layer == "cache":
        actions.extend([
            "检查 Redis key 是否按预期建立、删除或更新。",
            "重点核对 create/list/get/delete 后的缓存失效逻辑。",
        ])
    elif likely_layer == "external_dependency_or_ai":
        actions.extend([
            "检查 Grafana 依赖是否可访问，以及摘要场景是否发生 fallback。",
            "检查 AI 配置、返回结果和 summary source 指标。",
        ])
    elif likely_layer == "interface":
        actions.extend([
            "先检查接口返回的状态码、错误体和入参校验。",
            "再核对是否由上游依赖异常引发了接口层错误。",
        ])
    else:
        actions.extend([
            "先确认失败是否能稳定复现，再检查环境抖动和测试数据污染。",
            "对照 Allure 原始报错和当前复现结果判断是否属于偶发问题。",
        ])
    if anomalies:
        actions.append(f"优先围绕这些异常点排查：{', '.join(anomalies[:3])}。")
    return actions


def run_agent() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    allure_cases = load_allure_cases()
    allure_summary = build_status_summary(allure_cases)
    failed_cases = select_failed_cases(allure_cases, limit=MAX_FAILED_CASES)

    case_results: list[dict[str, Any]] = []
    for case in failed_cases:
        scenario, route_source = route_case(case)
        if not scenario:
            state = build_case_state("unroutable", None)
            case_results.append(
                {
                    "test_name": case.name,
                    "full_name": case.full_name,
                    "scenario": None,
                    "route_source": route_source,
                    "state": state,
                    "likely_layer": "manual_check_required",
                    "anomalies": ["route_unmatched_case"],
                    "evidence_lines": [],
                    "snapshot_diff": {},
                    "next_actions": _build_next_actions(
                        "manual_check_required",
                        ["route_unmatched_case"],
                        state["diagnosis_status"],
                    ),
                    "original_failure": {"message": case.message, "trace": case.trace},
                }
            )
            continue

        with managed_agent_environment() as context:
            scenario_result = run_standard_scenario(scenario, context)

        state = build_case_state("routed", scenario_result)
        anomalies = scenario_result.get("anomalies", [])
        likely_layer = derive_likely_layer(anomalies)
        evidence_lines = build_evidence_lines(scenario_result)

        case_results.append(
            {
                "test_name": case.name,
                "full_name": case.full_name,
                "scenario": scenario,
                "route_source": route_source,
                "state": state,
                "likely_layer": likely_layer,
                "anomalies": anomalies,
                "evidence_lines": evidence_lines,
                "snapshot_diff": scenario_result.get("snapshot", {}).get("diff", {}),
                "next_actions": _build_next_actions(likely_layer, anomalies, state["diagnosis_status"]),
                "original_failure": {"message": case.message, "trace": case.trace},
                "runtime": scenario_result.get("runtime", {}),
            }
        )

    state_counter = Counter(item["state"]["diagnosis_status"] for item in case_results)
    summary = {
        "allure": allure_summary,
        "routed_cases": sum(1 for item in case_results if item["state"]["route_status"] == "routed"),
        "reproduced_failures": sum(1 for item in case_results if item["state"]["repro_status"] == "reproduced"),
        "high_confidence_cases": state_counter.get("high_confidence", 0),
        "diagnosis_status_count": dict(state_counter),
    }
    return summary, case_results


def main() -> None:
    summary, case_results = run_agent()
    ai_payload = {"summary": summary, "cases": case_results}
    ai_summary = maybe_generate_ai_summary(ai_payload)
    write_reports(summary, case_results, ai_summary)


if __name__ == "__main__":
    main()
