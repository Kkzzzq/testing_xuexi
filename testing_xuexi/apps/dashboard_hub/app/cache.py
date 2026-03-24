from __future__ import annotations

import json

import redis

from app.config import REDIS_DB, REDIS_HOST, REDIS_PORT


client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)


def set_json(key: str, value: dict, ex: int | None = None):
    client.set(key, json.dumps(value, ensure_ascii=False), ex=ex)


def get_json(key: str):
    raw = client.get(key)
    return json.loads(raw) if raw else None


def delete(key: str):
    client.delete(key)
