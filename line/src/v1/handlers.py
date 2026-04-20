import binascii
import logging

from ..core.database import (
    create_session, end_session,
    get_student, get_student_session_status, get_session_materials,
    log_beacon_event, mark_absentees, register_student,
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
        dm = dm_hex  # fallback: use as-is if not valid hex

    # log.info("beacon type=%s dm=%r user=%s", beacon_type, dm, user_id[:8] + "…")

    if beacon_type != "enter":
        # log.info("ignored — not enter")
        return

    parts      = dm.split(":")
    session_id = parts[2] if len(parts) == 3 else "000"

    if dm.startswith("cls:idle") or not dm.startswith("cls:"):
        # log.info("ignored — idle or unknown dm")
        return

    student = get_student(user_id)
    if not student:
        # log.info("unregistered user — prompting registration")
        await reply(reply_tkn, "Welcome! Please register by sending your 10-digit student ID.\n\nTip: If you don't receive a reply, toggle Bluetooth off and on to re-trigger the beacon.")
        return

    display   = student["name"] or student["student_id"]
    materials = get_session_materials(session_id)
    slides    = materials["slides_url"]
    supp      = materials["supplementary_url"]

    def _materials_lines() -> str:
        lines = []
        if slides:
            lines.append(f"Slides: {slides}")
        if supp:
            lines.append(f"Supplementary: {supp}")
        return ("\n" + "\n".join(lines)) if lines else ""

    if dm.startswith("cls:open"):
        create_session(session_id, version="v1")
        log_beacon_event(user_id, student["student_id"], session_id, "PRESENT", dm)
        # log.info("PRESENT logged — student=%s session=%s", student["student_id"], session_id)
        await reply(reply_tkn, f"✅ Present! {display}{_materials_lines()}\n\nTip: Toggle Bluetooth off/on if you don't see this message.")

    elif dm.startswith("cls:run"):
        log_beacon_event(user_id, student["student_id"], session_id, "LATE", dm)
        # log.info("LATE logged — student=%s session=%s", student["student_id"], session_id)
        await reply(reply_tkn, f"⏰ Late noted. {display}{_materials_lines()}")

    elif dm.startswith("cls:qz"):
        log_beacon_event(user_id, student["student_id"], session_id, "QUIZ", dm)
        # log.info("QUIZ logged — student=%s session=%s", student["student_id"], session_id)
        await reply(reply_tkn, f"📝 Quiz is live!{_materials_lines()}")

    elif dm.startswith("cls:end"):
        mark_absentees(session_id)
        end_session(session_id)
        status = get_student_session_status(student["student_id"], session_id) or "ABSENT"
        # log.info("END — session=%s status=%s", session_id, status)
        await reply(reply_tkn, f"Class has ended. Your status: {status}")


async def _handle_message(event: dict):
    user_id   = event["source"]["userId"]
    reply_tkn = event["replyToken"]
    text      = event["message"]["text"].strip()

    if text.lower() in _GREETINGS:
        student = get_student(user_id)
        if student:
            name = student["name"] or student["student_id"]
            await reply(reply_tkn, f"สวัสดีครับ {name}! 👋\nระบบพร้อมใช้งานแล้ว ✅")
        else:
            await reply(reply_tkn, "สวัสดีครับ! 👋 ยังไม่ได้ลงทะเบียน\nกรุณาส่งรหัสนักศึกษา 10 หลักเพื่อลงทะเบียน")
        return

    if text.isdigit() and len(text) == 10:
        register_student(user_id, text)
        await reply(reply_tkn, f"Registered! 🎓 Student ID: {text}\nAll future classes are automatic.")
    else:
        await reply(reply_tkn, "Please send your 10-digit student ID to register.")
