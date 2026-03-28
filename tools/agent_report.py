from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

MD_OUTPUT = Path(os.getenv("FAULT_REPRO_MD_FILE", "fault_repro_report.md"))
JSON_OUTPUT = Path(os.getenv("FAULT_REPRO_JSON_FILE", "fault_repro_report.json"))


def _md_escape(value: str) -> str:
    return value.replace("```", "''' ")


def build_markdown_report(summary: dict[str, Any], case_results: list[dict[str, Any]], ai_summary: str | None) -> str:
    lines: list[str] = ["# Fault Reproduction & Troubleshooting Report", ""]
    lines.append("## Run Overview")
    lines.append("")
    lines.append(f"- Allure total cases: {summary['allure']['total']}")
    lines.append(f"- Failed/Broken cases: {summary['allure']['failed_or_broken']}")
    lines.append(f"- Routed cases: {summary['routed_cases']}")
    lines.append(f"- Reproduced failures: {summary['reproduced_failures']}")
    lines.append(f"- High confidence diagnoses: {summary['high_confidence_cases']}")
    lines.append("")

    if ai_summary:
        lines.append("## AI Diagnosis Summary")
        lines.append("")
        lines.append(ai_summary.strip())
        lines.append("")

    lines.append("## Case Diagnostics")
    lines.append("")
    if not case_results:
        lines.append("No failed or broken cases were found in allure results.")
        return "\n".join(lines) + "\n"

    for index, item in enumerate(case_results, start=1):
        state = item["state"]
        lines.append(f"### {index}. {item['test_name']}")
        lines.append("")
        lines.append(f"- Scenario: {item.get('scenario') or 'unroutable'}")
        lines.append(f"- Route source: {item.get('route_source')}")
        lines.append(f"- Route status: {state['route_status']}")
        lines.append(f"- Repro status: {state['repro_status']}")
        lines.append(f"- Evidence status: {state['evidence_status']}")
        lines.append(f"- Diagnosis status: {state['diagnosis_status']}")
        lines.append(f"- Likely layer: {item.get('likely_layer')}")
        lines.append("")

        if item.get("original_failure"):
            lines.append("**Original failure summary**")
            lines.append("")
            lines.append(f"- Message: {_md_escape(item['original_failure'].get('message', ''))}")
            lines.append("")

        anomalies = item.get("anomalies") or []
        if anomalies:
            lines.append("**Observed anomalies**")
            lines.append("")
            for anomaly in anomalies:
                lines.append(f"- {anomaly}")
            lines.append("")

        evidence_lines = item.get("evidence_lines") or []
        if evidence_lines:
            lines.append("**Evidence**")
            lines.append("")
            for evidence in evidence_lines:
                lines.append(f"- {_md_escape(evidence)}")
            lines.append("")

        next_actions = item.get("next_actions") or []
        if next_actions:
            lines.append("**Suggested checks**")
            lines.append("")
            for action in next_actions:
                lines.append(f"1. {action}")
            lines.append("")

        snapshot_diff = item.get("snapshot_diff")
        if snapshot_diff:
            lines.append("**Snapshot diff**")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(snapshot_diff, ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("")

    return "\n".join(lines).strip() + "\n"


def write_reports(summary: dict[str, Any], case_results: list[dict[str, Any]], ai_summary: str | None) -> None:
    markdown = build_markdown_report(summary, case_results, ai_summary)
    MD_OUTPUT.write_text(markdown, encoding="utf-8")
    JSON_OUTPUT.write_text(
        json.dumps({"summary": summary, "cases": case_results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
