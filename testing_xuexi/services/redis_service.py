from __future__ import annotations

import json

import redis

import config.settings as settings
from helpers.decorators import db_error_handler


class RedisService:
    @staticmethod
    @db_error_handler
    def connect():
        return redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True,
        )

    @staticmethod
    def get_json(key: str):
        client = RedisService.connect()
        raw = client.get(key)
        return json.loads(raw) if raw else None

    @staticmethod
    def exists(key: str) -> bool:
        return bool(RedisService.connect().exists(key))
