import sqlite3
import contextlib

DB_PATH = "classroom.db"


def init_db():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS students (
                user_id    TEXT PRIMARY KEY,
                student_id TEXT NOT NULL UNIQUE,
                name       TEXT DEFAULT ''
            )""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS beacon_events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    TEXT NOT NULL,
                student_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                status     TEXT NOT NULL,
                dm         TEXT,
                ts         DATETIME DEFAULT CURRENT_TIMESTAMP
            )""")
        # First-occurrence-wins: subquery picks the row with MIN(ts) per student+session
        c.execute("""
            CREATE VIEW IF NOT EXISTS attendance AS
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


@contextlib.contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def get_student(user_id: str) -> dict | None:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM students WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def register_student(user_id: str, student_id: str):
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO students(user_id, student_id) VALUES (?, ?)",
            (user_id, student_id),
        )


def log_beacon_event(
    user_id: str, student_id: str, session_id: str, status: str, dm: str
):
    """Append every beacon hit — no deduplication here (raw layer)."""
    with _conn() as c:
        c.execute(
            "INSERT INTO beacon_events(user_id, student_id, session_id, status, dm)"
            " VALUES (?, ?, ?, ?, ?)",
            (user_id, student_id, session_id, status, dm),
        )


def mark_absentees(session_id: str) -> list[str]:
    """Insert ABSENT rows for every student not seen this session.
    Returns list of absent student_ids for the summary reply.
    """
    with _conn() as c:
        seen = {
            r["student_id"]
            for r in c.execute(
                "SELECT DISTINCT student_id FROM beacon_events WHERE session_id = ?",
                (session_id,),
            ).fetchall()
        }
        all_students = c.execute(
            "SELECT user_id, student_id FROM students"
        ).fetchall()

        absent = []
        for s in all_students:
            if s["student_id"] not in seen:
                c.execute(
                    "INSERT INTO beacon_events(user_id, student_id, session_id, status, dm)"
                    " VALUES (?, ?, ?, 'ABSENT', ?)",
                    (s["user_id"], s["student_id"], session_id, f"cls:end:{session_id}"),
                )
                absent.append(s["student_id"])

        return absent
