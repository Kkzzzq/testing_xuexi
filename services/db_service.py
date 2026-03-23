import logging
import sqlite3
import time
from datetime import datetime

from config.settings import DB_PATH
from helpers.decorators import db_error_handler


class DBService:
    @staticmethod
    @db_error_handler
    def connect():
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute("PRAGMA busy_timeout = 5000")
        logging.info(f"Connected to {DB_PATH}")
        return conn

    @staticmethod
    def _checkpoint(connection):
        try:
            connection.execute("PRAGMA wal_checkpoint(PASSIVE)")
            logging.info("Executed PRAGMA wal_checkpoint(PASSIVE)")
        except sqlite3.DatabaseError as exc:
            logging.info("wal_checkpoint skipped: %s", exc)

    @staticmethod
    @db_error_handler
    def create_user(
        login,
        email,
        name,
        password,
        version=0,
        org_id=1,
        is_admin=0,
        created=0,
        updated=0,
    ):
        created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with DBService.connect() as connection:
            connection.execute(
                "INSERT INTO user (login, email, name, password, version, org_id, is_admin, created, updated) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (login, email, name, password, version, org_id, is_admin, created, updated),
            )
            logging.info(
                "Created user %s with parameters %s",
                login,
                (email, name, password, version, org_id, is_admin, created, updated),
            )

    @staticmethod
    @db_error_handler
    def find_user_by_email(email, retries=10, delay=0.5):
        for attempt in range(1, retries + 1):
            with DBService.connect() as connection:
                DBService._checkpoint(connection)
                cursor = connection.execute(
                    "SELECT login, email, name FROM user WHERE email = ?",
                    (email,),
                )
                row = cursor.fetchone()

            if row is not None:
                logging.info("Found user by email %s: %s", email, row)
                return row

            logging.info(
                "User %s not found yet (attempt %s/%s)",
                email,
                attempt,
                retries,
            )
            time.sleep(delay)

        logging.warning("User %s was not found after %s attempts", email, retries)
        return None

    @staticmethod
    @db_error_handler
    def find_user_by_login(login, retries=10, delay=0.5):
        for attempt in range(1, retries + 1):
            with DBService.connect() as connection:
                DBService._checkpoint(connection)
                cursor = connection.execute(
                    "SELECT id, login, email, name FROM user WHERE login = ?",
                    (login,),
                )
                row = cursor.fetchone()

            if row is not None:
                logging.info("Found user by login %s: %s", login, row)
                return row

            logging.info(
                "User with login %s not found yet (attempt %s/%s)",
                login,
                attempt,
                retries,
            )
            time.sleep(delay)

        logging.warning("User with login %s was not found after %s attempts", login, retries)
        return None

    @staticmethod
    @db_error_handler
    def delete_user_by_login(login):
        with DBService.connect() as connection:
            connection.execute("DELETE FROM user WHERE login = ?", (login,))
            logging.info(f"Deleted user {login}")
