from .database import get_student, log_beacon_event, mark_absentees, register_student
from .line_client import reply


async def dispatch(event: dict):
    etype = event.get("type")
    if etype == "beacon":
        await _handle_beacon(event)
    elif etype == "message" and event.get("message", {}).get("type") == "text":
        await _handle_registration(event)


async def _handle_beacon(event: dict):
    user_id     = event["source"]["userId"]
    reply_tkn   = event["replyToken"]
    beacon      = event["beacon"]
    dm          = beacon.get("dm", "")
    beacon_type = beacon.get("type", "")

    # Only act on entry — ignore leave/banner
    if beacon_type != "enter":
        return

    # dm format: "cls:<state>:<session_id>"
    parts = dm.split(":")
    session_id = parts[2] if len(parts) == 3 else "000"

    if dm.startswith("cls:idle") or not dm.startswith("cls:"):
        return

    student = get_student(user_id)
    if not student:
        await reply(reply_tkn, "Welcome! Please register by sending your 10-digit student ID.")
        return

    display = student["name"] or student["student_id"]

    if dm.startswith("cls:open"):
        log_beacon_event(user_id, student["student_id"], session_id, "PRESENT", dm)
        await reply(reply_tkn, f"✅ Present! {display}\nSlides: bit.ly/emb-w12")

    elif dm.startswith("cls:run"):
        log_beacon_event(user_id, student["student_id"], session_id, "LATE", dm)
        await reply(reply_tkn, f"⏰ Late noted. {display}\nSlides: bit.ly/emb-w12")

    elif dm.startswith("cls:qz"):
        log_beacon_event(user_id, student["student_id"], session_id, "QUIZ", dm)
        await reply(reply_tkn, "📝 Quiz is live!\nliff.line.me/quiz-emb")

    elif dm.startswith("cls:end"):
        absent_ids = mark_absentees(session_id)
        n = len(absent_ids)
        summary = f"Session {session_id} ended.\nAbsent: {n} student(s)."
        if absent_ids:
            # Trim to avoid hitting LINE's 5000-char message limit
            shown = ", ".join(absent_ids[:20])
            if n > 20:
                shown += f" … (+{n - 20} more)"
            summary += f"\n{shown}"
        await reply(reply_tkn, summary)


_GREETINGS = {"hello", "hi", "hey", "สวัสดี", "สวัสดีครับ", "สวัสดีค่ะ", "หวัดดี", "ดีครับ", "ดีค่ะ"}


async def _handle_registration(event: dict):
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
