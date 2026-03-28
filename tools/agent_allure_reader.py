from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_RESULTS_DIR = Path(os.getenv("ALLURE_RESULTS_DIR", "allure-results"))
MAX_MESSAGE_CHARS = int(os.getenv("FAULT_AGENT_MAX_MESSAGE_CHARS", "1200"))
MAX_TRACE_CHARS = int(os.getenv("FAULT_AGENT_MAX_TRACE_CHARS", "4000"))


@dataclass(slots=True)
class AllureCase:
    name: str
    full_name: str
    status: str
    message: str
    trace: str
    labels: dict[str, list[str]] = field(default_factory=dict)

    @property
    def fault_scenario(self) -> str | None:
        values = self.labels.get("fault_scenario") or []
        return values[0] if values else None

    @property
    def short_test_name(self) -> str:
        if "." in self.full_name:
            return self.full_name.split(".")[-1]
        if "#" in self.full_name:
            return self.full_name.split("#")[-1]
        return self.name

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "full_name": self.full_name,
            "status": self.status,
            "message": self.message,
            "trace": self.trace,
            "labels": self.labels,
        }


def _truncate(text: str | None, limit: int) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...<truncated>"


def _extract_labels(payload: dict[str, Any]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for label in payload.get("labels", []) or []:
        name = str(label.get("name", "")).strip()
        value = str(label.get("value", "")).strip()
        if not name or not value:
            continue
        grouped.setdefault(name, []).append(value)
    return grouped


def load_allure_cases(results_dir: Path | None = None) -> list[AllureCase]:
    target_dir = results_dir or DEFAULT_RESULTS_DIR
    if not target_dir.exists():
        return []

    cases: list[AllureCase] = []
    for result_file in sorted(target_dir.glob("*-result.json")):
        try:
            payload = json.loads(result_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        details = payload.get("statusDetails", {}) or {}
        cases.append(
            AllureCase(
                name=str(payload.get("name") or "unknown"),
                full_name=str(payload.get("fullName") or payload.get("name") or "unknown"),
                status=str(payload.get("status") or "unknown"),
                message=_truncate(details.get("message", ""), MAX_MESSAGE_CHARS),
                trace=_truncate(details.get("trace", ""), MAX_TRACE_CHARS),
                labels=_extract_labels(payload),
            )
        )
    return cases


def build_status_summary(cases: list[AllureCase]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "total": len(cases),
        "status_count": {},
        "failed_or_broken": 0,
    }
    for case in cases:
        summary["status_count"][case.status] = summary["status_count"].get(case.status, 0) + 1
        if case.status in {"failed", "broken"}:
            summary["failed_or_broken"] += 1
    return summary


def select_failed_cases(cases: list[AllureCase], limit: int | None = None) -> list[AllureCase]:
    failed = [case for case in cases if case.status in {"failed", "broken"}]
    return failed[:limit] if limit is not None else failed
