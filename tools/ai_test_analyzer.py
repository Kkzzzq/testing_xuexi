from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from urllib import error, request


ALLURE_RESULTS_DIR = Path(os.getenv("ALLURE_RESULTS_DIR", "allure-results"))
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "deepseek-chat")
OUTPUT_FILE = Path(os.getenv("AI_ANALYSIS_REPORT_FILE", "ai_analysis_report.md"))

MAX_MESSAGE_CHARS = int(os.getenv("AI_ANALYSIS_MAX_MESSAGE_CHARS", "1000"))
MAX_TRACE_CHARS = int(os.getenv("AI_ANALYSIS_MAX_TRACE_CHARS", "3000"))
MAX_CASES = int(os.getenv("AI_ANALYSIS_MAX_CASES", "50"))
MAX_FAILED_CASES = int(os.getenv("AI_ANALYSIS_MAX_FAILED_CASES", "20"))
MAX_PASSED_CASES = int(os.getenv("AI_ANALYSIS_MAX_PASSED_CASES", "10"))
AI_TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT_SECONDS", "300"))


def _truncate(text: str | None, limit: int) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...<truncated>"


def collect_test_cases() -> list[dict]:
    cases: list[dict] = []

    if not ALLURE_RESULTS_DIR.exists():
        return cases

    for file in sorted(ALLURE_RESULTS_DIR.glob("*-result.json")):
        try:
            payload = json.loads(file.read_text(encoding="utf-8"))
        except Exception:
            continue

        status = payload.get("status", "unknown")

        cases.append(
            {
                "name": payload.get("name") or "unknown",
                "fullName": payload.get("fullName") or "unknown",
                "status": status,
                "message": _truncate(
                    payload.get("statusDetails", {}).get("message", ""),
                    MAX_MESSAGE_CHARS,
                ),
                "trace": _truncate(
                    payload.get("statusDetails", {}).get("trace", ""),
                    MAX_TRACE_CHARS,
                ),
            }
        )

        if len(cases) >= MAX_CASES:
            break

    return cases


def build_summary(cases: list[dict]) -> dict:
    counter = Counter(case["status"] for case in cases)

    failed_cases = [c for c in cases if c["status"] in {"failed", "broken"}][:MAX_FAILED_CASES]
    passed_cases = [c for c in cases if c["status"] == "passed"][:MAX_PASSED_CASES]
    skipped_cases = [c for c in cases if c["status"] == "skipped"][:10]

    return {
        "total": len(cases),
        "status_count": dict(counter),
        "failed_or_broken_cases": failed_cases,
        "passed_cases_sample": passed_cases,
        "skipped_cases_sample": skipped_cases,
    }


def build_prompt(summary: dict) -> str:
    return (
        "你是自动化测试分析助手。\n"
        "请基于下面的 Allure 测试结果，输出一份中文 Markdown 分析报告。\n"
        "要求：\n"
        "1. 先给出本次测试执行概览\n"
        "2. 如果存在失败/异常，用例逐条分析更可能的问题层：接口 / MySQL / Redis / Grafana依赖 / 测试代码\n"
        "3. 如果大部分通过，也要总结本次测试覆盖情况和潜在风险点\n"
        "4. 给出建议优先排查项和后续测试建议\n"
        "5. 不要编造仓库里没有的实现细节\n\n"
        f"测试结果摘要：\n{json.dumps(summary, ensure_ascii=False, indent=2)}"
    )


def ask_ai(summary: dict) -> str:
    payload = {
        "model": AI_MODEL,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "你是自动化测试分析助手。"},
            {"role": "user", "content": build_prompt(summary)},
        ],
    }

    req = request.Request(
        f"{AI_BASE_URL}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=AI_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AI request failed: {exc.code} {detail}") from exc
    except Exception as exc:
        raise RuntimeError(f"AI request failed: {exc}") from exc

    try:
        result = json.loads(raw)
        return result["choices"][0]["message"]["content"]
    except Exception as exc:
        raise RuntimeError(f"unexpected AI response: {raw}") from exc


def write_report(content: str) -> None:
    OUTPUT_FILE.write_text(content.strip() + "\n", encoding="utf-8")


def main() -> None:
    cases = collect_test_cases()

    if not cases:
        write_report("# AI Test Analysis Report\n\nNo allure test results found.\n")
        return

    summary = build_summary(cases)

    if not AI_API_KEY:
        write_report(
            "# AI Test Analysis Report\n\n"
            "AI_API_KEY is empty, skip AI analysis.\n\n"
            "## Test Result Summary\n\n"
            f"```json\n{json.dumps(summary, ensure_ascii=False, indent=2)}\n```\n"
        )
        return

    try:
        report = ask_ai(summary)
    except Exception as exc:
        report = (
            "# AI Test Analysis Report\n\n"
            f"AI analysis failed: {exc}\n\n"
            "## Test Result Summary\n\n"
            f"```json\n{json.dumps(summary, ensure_ascii=False, indent=2)}\n```\n"
        )

    write_report(report)


if __name__ == "__main__":
    main()
