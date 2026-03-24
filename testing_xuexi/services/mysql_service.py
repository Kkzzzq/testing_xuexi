from __future__ import annotations

import pymysql

import config.settings as settings
from helpers.decorators import db_error_handler


class MySQLService:
    @staticmethod
    @db_error_handler
    def connect():
        return pymysql.connect(
            host=settings.MYSQL_HOST,
            port=settings.MYSQL_PORT,
            user=settings.MYSQL_USER,
            password=settings.MYSQL_PASSWORD,
            database=settings.MYSQL_DB,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )

    @staticmethod
    def fetch_subscription_by_id(subscription_id: int):
        with MySQLService.connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM subscriptions WHERE id=%s", (subscription_id,))
                return cursor.fetchone()

    @staticmethod
    def fetch_share_link_by_token(token: str):
        with MySQLService.connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM share_links WHERE token=%s", (token,))
                return cursor.fetchone()
