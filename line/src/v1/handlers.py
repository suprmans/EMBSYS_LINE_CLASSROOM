import binascii
import logging

from ..core.database import (
    create_walkin_session, end_session, find_active_session,
    get_student, get_student_session_status, has_checkin,
    log_beacon_event, mark_absentees, register_student,
    transition_session,
)
from ..core.line_client import reply

log = logging.getLogger(__name__)

_GREETINGS = {"hello", "hi", "hey", "สวัสดี", "สวัสดีครับ", "สวัสดีค่ะ", "หวัดดี", "ดีครับ", "ดีค่ะ"}


async def dispatch(event: dict):
    etype = event.get("type")
    # log.info("event type=%s", etype)
    if etype == "beacon":
        await _handle_beacon(event)
    elif etype == "message" and event.get("message", {}).get("type") == "text":
        await _handle_message(event)


async def _handle_beacon(event: dict):
    user_id     = event["source"]["userId"]
    reply_tkn   = event["replyToken"]
    beacon      = event["beacon"]
    dm_hex      = beacon.get("dm", "")
    beacon_type = beacon.get("type", "")

    try:
        dm = binascii.unhexlify(dm_hex).decode("utf-8") if dm_hex else ""
    except Exception:
        dm = dm_hex

    # log.info("beacon type=%s dm=%r user=%s", beacon_type, dm, user_id[:8] + "…")

    if beacon_type != "enter":
        # log.info("ignored — not enter")
        return

    if dm.startswith("cls:idle") or not dm.startswith("cls:"):
        # log.info("ignored — idle or unknown dm")
        return

    student = get_student(user_id)
    if not student:
        # log.info("unregistered user — prompting registration")
        await reply(
            reply_tkn,
            "Welcome! Please register by sending your 10-digit student ID.\n\n"
            "Tip: If you don't get a reply after registering, toggle Bluetooth off/on "
            "to re-trigger the beacon and receive ✅ Present.",
        )
        return

    display = student["name"] or student["student_id"]

    # ── Resolve active session by time window ──────────────────
    session = find_active_session()

    if dm.startswith("cls:open"):
        if not session:
            session = create_walkin_session()
            log.warning("No scheduled session found — walk-in session created: %s", session["session_id"])
        else:
            transition_session(session["session_id"], "OPEN")

        session_id = session["session_id"]
        log_beacon_event(user_id, student["student_id"], session_id, "PRESENT", dm)
        # log.info("PRESENT logged — student=%s session=%s", student["student_id"], session_id)

        msg = f"✅ Checked-in ({student['student_id']})"
        msg += _materials(session)
        if session.get("auto_created"):
            msg += "\n\nℹ️ No session was scheduled — a walk-in session was created automatically."
        msg += "\n\nTip: Toggle Bluetooth off/on if you don't see this message right away."
        await reply(reply_tkn, msg)

    elif dm.startswith("cls:late"):
        if not session:
            return
        session_id = session["session_id"]
        transition_session(session_id, "LATE_CHECKIN")
        if has_checkin(student["student_id"], session_id):
            pass
        else:
            log_beacon_event(user_id, student["student_id"], session_id, "LATE", dm)
            # log.info("LATE logged — student=%s session=%s", student["student_id"], session_id)
            await reply(reply_tkn, f"⏰ Late noted. {display}{_materials(session)}")

    elif dm.startswith("cls:qz"):
        if not session:
            # log.info("cls:qz — no active session, ignored")
            return
        session_id = session["session_id"]
        transition_session(session_id, "QUIZ")
        log_beacon_event(user_id, student["student_id"], session_id, "QUIZ", dm)
        # log.info("QUIZ logged — student=%s session=%s", student["student_id"], session_id)
        await reply(reply_tkn, f"📝 Quiz is live!{_quiz_material(session)}")

    elif dm.startswith("cls:end"):
        if not session:
            # log.info("cls:end — no active session, ignored")
            return
        session_id = session["session_id"]
        mark_absentees(session_id)
        end_session(session_id)
        status = get_student_session_status(student["student_id"], session_id) or "ABSENT"
        # log.info("END — session=%s status=%s", session_id, status)
        await reply(reply_tkn, f"Class has ended. Your status: {status}")


def _materials(session: dict) -> str:
    lines = []
    if session.get("slides_url"):
        lines.append(f"Slides: {session['slides_url']}")
    if session.get("supplementary_url"):
        lines.append(f"Supplementary: {session['supplementary_url']}")
    return ("\n" + "\n".join(lines)) if lines else ""


def _quiz_material(session: dict) -> str:
    if session.get("quiz_url"):
        return f"\nQuiz: {session['quiz_url']}"
    return ""


async def _handle_message(event: dict):
    user_id   = event["source"]["userId"]
    reply_tkn = event["replyToken"]
    text      = event["message"]["text"].strip()

    if text.lower() in _GREETINGS:
        student = get_student(user_id)
        if student:
            name = student["name"] or student["student_id"]
            await reply(reply_tkn, f"Hello {name}! 👋\nSystem is ready ✅")
        else:
            await reply(reply_tkn, "Hello! 👋 You are not registered yet.\nPlease send your 10-digit student ID to register.")
        return

    if text.isdigit() and len(text) == 10:
        existing = get_student(user_id)
        if existing:
            await reply(
                reply_tkn,
                f"Already registered ✅ Student ID: {existing['student_id']}\n"
                "To change your ID, please contact the lecturer directly.",
            )
        else:
            register_student(user_id, text)
            await reply(
                reply_tkn,
                f"Registered! 🎓 Student ID: {text}\n"
                "All future classes are automatic.\n\n"
                "Tip: Toggle Bluetooth off/on now to check in if a class is already in session.",
            )
    else:
        await reply(reply_tkn, "Please send your 10-digit student ID to register.")
