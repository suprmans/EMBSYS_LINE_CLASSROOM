import contextlib
import os

import psycopg
from psycopg.rows import dict_row


def _dsn() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return url


@contextlib.contextmanager
def _conn():
    with psycopg.connect(_dsn(), row_factory=dict_row) as con:
        yield con


# ── Schema ────────────────────────────────────────────────────

def init_db():
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS students (
                user_id       TEXT PRIMARY KEY,
                student_id    TEXT NOT NULL UNIQUE,
                name          TEXT NOT NULL DEFAULT '',
                registered_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                version    TEXT NOT NULL DEFAULT 'v1',
                opened_at  TIMESTAMPTZ DEFAULT NOW(),
                ended_at   TIMESTAMPTZ
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS beacon_events (
                id         SERIAL PRIMARY KEY,
                user_id    TEXT NOT NULL,
                student_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                status     TEXT NOT NULL,
                dm         TEXT,
                ts         TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS overrides (
                student_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                status     TEXT NOT NULL,
                reason     TEXT NOT NULL,
                ts         TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (student_id, session_id)
            )
        """)
        con.execute("""
            CREATE OR REPLACE VIEW attendance AS
            SELECT be.student_id, be.session_id, be.status, be.ts
            FROM beacon_events be
            INNER JOIN (
                SELECT student_id, session_id, MIN(ts) AS first_ts
                FROM beacon_events
                GROUP BY student_id, session_id
            ) first
                ON  be.student_id = first.student_id
                AND be.session_id = first.session_id
                AND be.ts         = first.first_ts
        """)
        con.commit()


# ── Students ──────────────────────────────────────────────────

def get_student(user_id: str) -> dict | None:
    with _conn() as con:
        return con.execute(
            "SELECT * FROM students WHERE user_id = %s", (user_id,)
        ).fetchone()


def register_student(user_id: str, student_id: str):
    with _conn() as con:
        con.execute(
            """
            INSERT INTO students (user_id, student_id) VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET student_id = EXCLUDED.student_id
            """,
            (user_id, student_id),
        )
        con.commit()


def list_students(limit: int = 50, offset: int = 0) -> dict:
    with _conn() as con:
        total = con.execute("SELECT COUNT(*) AS n FROM students").fetchone()["n"]
        rows  = con.execute(
            "SELECT student_id, registered_at FROM students ORDER BY registered_at LIMIT %s OFFSET %s",
            (limit, offset),
        ).fetchall()
        return {"total": total, "students": rows}


def delete_student(student_id: str) -> bool:
    with _conn() as con:
        cur = con.execute("DELETE FROM students WHERE student_id = %s", (student_id,))
        con.commit()
        return cur.rowcount > 0


# ── Sessions ──────────────────────────────────────────────────

def create_session(session_id: str, version: str = "v1"):
    with _conn() as con:
        con.execute(
            "INSERT INTO sessions (session_id, version) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (session_id, version),
        )
        con.commit()


def end_session(session_id: str):
    with _conn() as con:
        con.execute(
            "UPDATE sessions SET ended_at = NOW() WHERE session_id = %s", (session_id,)
        )
        con.commit()


def list_sessions(date: str | None = None, limit: int = 20, offset: int = 0) -> list[dict]:
    where  = "WHERE DATE(s.opened_at) = %s" if date else ""
    params: list = ([date] if date else []) + [limit, offset]
    with _conn() as con:
        return con.execute(f"""
            SELECT
                s.session_id, s.version, s.opened_at, s.ended_at,
                COUNT(CASE WHEN a.status = 'PRESENT' THEN 1 END) AS present,
                COUNT(CASE WHEN a.status = 'LATE'    THEN 1 END) AS late,
                COUNT(CASE WHEN a.status = 'ABSENT'  THEN 1 END) AS absent,
                (SELECT COUNT(*) FROM students)                   AS total_registered
            FROM sessions s
            LEFT JOIN attendance a ON a.session_id = s.session_id
            {where}
            GROUP BY s.session_id, s.version, s.opened_at, s.ended_at
            ORDER BY s.opened_at DESC
            LIMIT %s OFFSET %s
        """, params).fetchall()


def get_session(session_id: str) -> dict | None:
    with _conn() as con:
        return con.execute(
            """
            SELECT
                s.session_id, s.version, s.opened_at, s.ended_at,
                COUNT(CASE WHEN a.status = 'PRESENT' THEN 1 END) AS present,
                COUNT(CASE WHEN a.status = 'LATE'    THEN 1 END) AS late,
                COUNT(CASE WHEN a.status = 'ABSENT'  THEN 1 END) AS absent,
                (SELECT COUNT(*) FROM students) AS total_registered
            FROM sessions s
            LEFT JOIN attendance a ON a.session_id = s.session_id
            WHERE s.session_id = %s
            GROUP BY s.session_id, s.version, s.opened_at, s.ended_at
            """,
            (session_id,),
        ).fetchone()


# ── Attendance ────────────────────────────────────────────────

def log_beacon_event(user_id: str, student_id: str, session_id: str, status: str, dm: str):
    with _conn() as con:
        con.execute(
            "INSERT INTO beacon_events (user_id, student_id, session_id, status, dm)"
            " VALUES (%s, %s, %s, %s, %s)",
            (user_id, student_id, session_id, status, dm),
        )
        con.commit()


def list_attendance(
    session_id: str,
    status: str | None = None,
    order: str = "asc",
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    direction = "ASC" if order == "asc" else "DESC"
    where     = "AND a.status = %s" if status else ""
    params: list = [session_id] + ([status] if status else []) + [limit, offset]
    with _conn() as con:
        return con.execute(f"""
            SELECT
                a.student_id,
                COALESCE(o.status, a.status)    AS status,
                COALESCE(o.ts,     a.ts)        AS ts,
                (o.student_id IS NOT NULL)::int AS overridden,
                o.reason
            FROM attendance a
            LEFT JOIN overrides o
                ON o.student_id = a.student_id AND o.session_id = a.session_id
            WHERE a.session_id = %s {where}
            ORDER BY ts {direction}
            LIMIT %s OFFSET %s
        """, params).fetchall()


def override_attendance(session_id: str, student_id: str, status: str, reason: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            """
            SELECT COALESCE(o.status, a.status) AS prev
            FROM attendance a
            LEFT JOIN overrides o ON o.student_id = a.student_id AND o.session_id = a.session_id
            WHERE a.student_id = %s AND a.session_id = %s
            """,
            (student_id, session_id),
        ).fetchone()
        previous = row["prev"] if row else None

        con.execute(
            """
            INSERT INTO overrides (student_id, session_id, status, reason)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (student_id, session_id) DO UPDATE
                SET status = EXCLUDED.status, reason = EXCLUDED.reason, ts = NOW()
            """,
            (student_id, session_id, status, reason),
        )
        con.commit()
        return {"previous_status": previous, "new_status": status}


def get_student_session_status(student_id: str, session_id: str) -> str | None:
    with _conn() as con:
        row = con.execute(
            "SELECT status FROM overrides WHERE student_id = %s AND session_id = %s",
            (student_id, session_id),
        ).fetchone()
        if row:
            return row["status"]
        row = con.execute(
            "SELECT status FROM attendance WHERE student_id = %s AND session_id = %s",
            (student_id, session_id),
        ).fetchone()
        return row["status"] if row else None


def mark_absentees(session_id: str) -> list[str]:
    with _conn() as con:
        seen = {
            r["student_id"]
            for r in con.execute(
                "SELECT DISTINCT student_id FROM beacon_events WHERE session_id = %s",
                (session_id,),
            ).fetchall()
        }
        all_students = con.execute("SELECT user_id, student_id FROM students").fetchall()

        absent = []
        for s in all_students:
            if s["student_id"] not in seen:
                con.execute(
                    "INSERT INTO beacon_events (user_id, student_id, session_id, status, dm)"
                    " VALUES (%s, %s, %s, 'ABSENT', %s)",
                    (s["user_id"], s["student_id"], session_id, f"cls:end:{session_id}"),
                )
                absent.append(s["student_id"])
        con.commit()
        return absent
