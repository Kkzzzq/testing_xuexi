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
from tools.agent_evidence import build_evidence_lines, derive_likely_layer
from tools.agent_llm import maybe_generate_ai_summary
from tools.agent_report import write_reports
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


def _build_next_actions(likely_layer: str, observations: list[str], diagnosis_status: str) -> list[str]:
    actions: list[str] = []
    if diagnosis_status == "manual_check_required":
        actions.append("先人工确认该失败是否属于当前已支持的失败测试用例重放范围。")
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
    elif likely_layer == "service_execution_path":
        actions.extend([
            "优先检查服务端结构化日志里的关键业务分支是否已执行。",
            "核对数据库提交、缓存失效和 AI/fallback 分支的执行轨迹。",
        ])
    elif likely_layer == "interface":
        actions.extend([
            "先检查接口返回的状态码、错误体和入参校验。",
            "再核对是否由上游依赖异常引发了接口层错误。",
        ])
    else:
        actions.extend([
            "先确认失败是否能稳定复现，再检查环境抖动和测试数据污染。",
            "对照 Allure 原始报错和当前重放结果判断是否属于偶发问题。",
        ])
    if observations:
        actions.append(f"优先围绕这些观测现象排查：{', '.join(observations[:3])}。")
    return actions


def _build_ai_case_payload(case_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "test_name": case_result["test_name"],
        "original_failure": case_result.get("original_failure", {}),
        "runtime": case_result.get("runtime", {}),
        "http_steps": case_result.get("http_steps", []),
        "intermediate": case_result.get("intermediate", {}),
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

        state = build_case_state(replay_result)
        observations = replay_result.get("observations", [])
        service_logs = replay_result.get("snapshot", {}).get("after", {}).get("service_logs", {}).get("items", [])
        likely_layer = derive_likely_layer(observations, service_logs)
        evidence_lines = build_evidence_lines(replay_result)

        case_results.append(
            {
                "test_name": case.name,
                "full_name": case.full_name,
                "replay_target": replay_target,
                "state": state,
                "likely_layer": likely_layer,
                "observations": observations,
                "evidence_lines": evidence_lines,
                "snapshot": replay_result.get("snapshot", {}),
                "snapshot_diff": replay_result.get("snapshot", {}).get("diff", {}),
                "next_actions": _build_next_actions(likely_layer, observations, state["diagnosis_status"]),
                "original_failure": {"message": case.message, "trace": case.trace},
                "runtime": replay_result.get("runtime", {}),
                "http_steps": replay_result.get("http_steps", []),
                "intermediate": replay_result.get("intermediate", {}),
            }
        )

    state_counter = Counter(item["state"]["diagnosis_status"] for item in case_results)
    summary = {
        "allure": allure_summary,
        "replayed_cases": sum(1 for item in case_results if item["state"]["replay_status"] != "unsupported_test"),
        "reproduced_failures": sum(1 for item in case_results if item["state"]["replay_status"] == "reproduced"),
        "high_confidence_cases": state_counter.get("high_confidence", 0),
        "diagnosis_status_count": dict(state_counter),
    }
    return summary, case_results


def main() -> None:
    summary, case_results = run_agent()
    ai_payload = {
        "run_observations": {
            "failed_or_broken_cases": summary["allure"]["failed_or_broken"],
            "diagnostic_case_count": len(case_results),
        },
        "cases": [_build_ai_case_payload(item) for item in case_results],
    }
    ai_summary = maybe_generate_ai_summary(ai_payload)
    write_reports(summary, case_results, ai_summary)


if __name__ == "__main__":
    main()
