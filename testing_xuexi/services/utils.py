from __future__ import annotations

import json
import logging
from typing import Type

from pydantic import BaseModel


def safe_json(response):
    try:
        return response.json()
    except Exception:  # noqa: BLE001
        return {"raw": response.text}


def total_log_in_method(response):
    payload = safe_json(response)
    logging.info("status=%s payload=%s", response.status_code, json.dumps(payload, ensure_ascii=False))


def validate_schema(schema: Type[BaseModel], payload: dict):
    return schema.model_validate(payload)
