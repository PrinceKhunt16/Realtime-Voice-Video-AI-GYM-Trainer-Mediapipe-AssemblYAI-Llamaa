"""
SQLite database utilities for persistent exercise tracking.
"""

from __future__ import annotations

import sqlite3
import streamlit as st

from pathlib import Path
from typing import Optional

_DB_PATH = str(Path(__file__).parent.parent / "database.db")


@st.cache_resource
def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they do not exist."""
    conn = _get_connection()
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                username   TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS exercises (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL REFERENCES users(id),
                exercise_name TEXT    NOT NULL,
                reps          INTEGER NOT NULL DEFAULT 0,
                sets          INTEGER NOT NULL DEFAULT 0,
                time          INTEGER NOT NULL DEFAULT 0,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def get_user(username: str) -> Optional[sqlite3.Row]:
    """Return the user row for *username*, or None if not found."""
    conn = _get_connection()
    return conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()


def create_user(username: str) -> sqlite3.Row:
    """
    Insert a new user and return the resulting row.
    Raises ``sqlite3.IntegrityError`` if *username* already exists.
    """
    conn = _get_connection()
    with conn:
        conn.execute(
            "INSERT INTO users (username) VALUES (?)", (username,)
        )
    return get_user(username)  # type: ignore[return-value]


def get_or_create_user(username: str) -> sqlite3.Row:
    """Return existing user or create a new one."""
    user = get_user(username)
    if user is None:
        user = create_user(username)
    return user


def add_exercise(
    user_id: int,
    exercise_name: str,
    reps: int,
    sets: int,
    time: int,
) -> None:
    """Insert or merge an exercise record for *user_id*.

    If the same exercise was already logged today, the reps are added
    to the existing total and sets are incremented instead of creating
    a duplicate row.
    """
    conn = _get_connection()
    with conn:
        existing = conn.execute(
            """
            SELECT id, reps, sets, time FROM exercises
            WHERE user_id = ? AND exercise_name = ?
              AND DATE(created_at) = DATE('now')
            """,
            (user_id, exercise_name),
        ).fetchone()

        if existing:
            conn.execute(
                """
                UPDATE exercises
                SET reps = reps + ?, sets = sets + ?, time = time + ?
                WHERE id = ?
                """,
                (reps, sets, time, existing["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO exercises (user_id, exercise_name, reps, sets, time)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, exercise_name, reps, sets, time),
            )


def get_user_exercises(user_id: int) -> list[sqlite3.Row]:
    """Return all exercise rows for *user_id*, newest first."""
    conn = _get_connection()
    return conn.execute(
        """
        SELECT exercise_name, reps, sets, time, created_at
        FROM exercises
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (user_id,),
    ).fetchall()


def get_user_exercise_count(user_id: int) -> int:
    """Return total number of exercise records logged by *user_id*."""
    conn = _get_connection()
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM exercises WHERE user_id = ?", (user_id,)
    ).fetchone()
    return int(row["cnt"]) if row else 0
