from __future__ import annotations

import logging
import sqlite3

from config.settings import DB_PATH
from helpers.decorators import db_error_handler


class DBService:
    @staticmethod
    @db_error_handler
    def connect():
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.row_factory = sqlite3.Row
        logging.info("Connected to %s", DB_PATH)
        return conn

    @staticmethod
    @db_error_handler
    def find_user_by_login(login: str):
        with DBService.connect() as connection:
            cursor = connection.execute(
                "SELECT id, login, email, name FROM user WHERE login = ? ORDER BY id DESC LIMIT 1",
                (login,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    @db_error_handler
    def find_user_by_email(email: str):
        with DBService.connect() as connection:
            cursor = connection.execute(
                "SELECT id, login, email, name FROM user WHERE email = ? ORDER BY id DESC LIMIT 1",
                (email,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
