from __future__ import annotations

import json
import os
from urllib import error, request

AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "deepseek-chat")
AI_TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT_SECONDS", "180"))


def _build_prompt(payload: dict) -> str:
    return (
        "你是测试故障复现与排障助手。\n"
        "下面提供的是：\n"
        "1. 原始 Allure 失败信息\n"
        "2. 标准故障场景\n"
        "3. 自动复现结果\n"
        "4. 复现前后快照 diff\n"
        "5. HTTP / MySQL / Redis / Metrics 证据\n"
        "6. 当前状态机结果\n\n"
        "请输出中文 Markdown 诊断总结，要求：\n"
        "- 先说明本次失败是否被成功路由和复现\n"
        "- 判断更可能的问题层：接口 / 数据库 / 缓存 / 外部依赖 / 测试代码或环境\n"
        "- 所有结论必须引用给定证据，不能编造\n"
        "- 如果证据不足，明确说证据不足\n"
        "- 给出优先级最高的人工排查顺序\n\n"
        f"输入数据：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def maybe_generate_ai_summary(payload: dict) -> str | None:
    if not AI_API_KEY:
        return None

    req_payload = {
        "model": AI_MODEL,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "你是测试故障复现与排障助手。"},
            {"role": "user", "content": _build_prompt(payload)},
        ],
    }

    req = request.Request(
        f"{AI_BASE_URL}/chat/completions",
        data=json.dumps(req_payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=AI_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError:
        return None
    except Exception:
        return None

    try:
        payload = json.loads(raw)
        return payload["choices"][0]["message"]["content"].strip()
    except Exception:
        return None
