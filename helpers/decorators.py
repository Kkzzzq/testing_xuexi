from __future__ import annotations

import functools
import logging
import sqlite3
import time
from typing import Callable

import pymysql
import redis
import requests


def retry(attempts: int = 3, delay: float = 1.0):
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    logging.warning("Attempt %s/%s failed in %s: %s", attempt, attempts, func.__name__, exc)
                    if attempt < attempts:
                        time.sleep(delay)
            raise last_exc
        return wrapper
    return decorator


def api_error_handler(func: Callable):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except requests.RequestException as exc:
            logging.exception("HTTP error in %s: %s", func.__name__, exc)
            raise
    return wrapper


def db_error_handler(func: Callable):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (sqlite3.DatabaseError, pymysql.MySQLError, redis.RedisError) as exc:
            logging.exception("DB/cache error in %s: %s", func.__name__, exc)
            raise
    return wrapper
