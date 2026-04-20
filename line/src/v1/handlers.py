from ..core.database import (
    create_session, end_session,
    get_student, get_student_session_status,
    log_beacon_event, mark_absentees, register_student,
)
from ..core.line_client import reply

_GREETINGS = {"hello", "hi", "hey", "สวัสดี", "สวัสดีครับ", "สวัสดีค่ะ", "หวัดดี", "ดีครับ", "ดีค่ะ"}


async def dispatch(event: dict):
    etype = event.get("type")
    if etype == "beacon":
        await _handle_beacon(event)
    elif etype == "message" and event.get("message", {}).get("type") == "text":
        await _handle_message(event)


async def _handle_beacon(event: dict):
    user_id     = event["source"]["userId"]
    reply_tkn   = event["replyToken"]
    beacon      = event["beacon"]
    dm          = beacon.get("dm", "")
    beacon_type = beacon.get("type", "")

    if beacon_type != "enter":
        return

    parts      = dm.split(":")
    session_id = parts[2] if len(parts) == 3 else "000"

    if dm.startswith("cls:idle") or not dm.startswith("cls:"):
        return

    student = get_student(user_id)
    if not student:
        await reply(reply_tkn, "Welcome! Please register by sending your 10-digit student ID.")
        return

    display = student["name"] or student["student_id"]

    if dm.startswith("cls:open"):
        create_session(session_id, version="v1")
        log_beacon_event(user_id, student["student_id"], session_id, "PRESENT", dm)
        await reply(reply_tkn, f"✅ Present! {display}\nSlides: bit.ly/emb-w12")

    elif dm.startswith("cls:run"):
        log_beacon_event(user_id, student["student_id"], session_id, "LATE", dm)
        await reply(reply_tkn, f"⏰ Late noted. {display}\nSlides: bit.ly/emb-w12")

    elif dm.startswith("cls:qz"):
        log_beacon_event(user_id, student["student_id"], session_id, "QUIZ", dm)
        await reply(reply_tkn, "📝 Quiz is live!\nliff.line.me/quiz-emb")

    elif dm.startswith("cls:end"):
        mark_absentees(session_id)
        end_session(session_id)
        status = get_student_session_status(student["student_id"], session_id) or "ABSENT"
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
