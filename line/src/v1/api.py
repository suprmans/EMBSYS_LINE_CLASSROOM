import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..core.auth import require_lecturer
from ..core.database import (
    delete_student,
    get_session,
    list_attendance,
    list_sessions,
    list_students,
    override_attendance,
    update_session_materials,
)

router = APIRouter(prefix="/api/v1", tags=["Lecturer Admin — v1"])


# ── Sessions ──────────────────────────────────────────────────

@router.get("/sessions/", summary="List all sessions with attendance counts")
def get_sessions(
    date: str | None = Query(None, description="Filter by date YYYY-MM-DD"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: str = Depends(require_lecturer),
):
    return list_sessions(date=date, limit=limit, offset=offset)


@router.get("/sessions/{session_id}/", summary="Single session detail")
def get_session_detail(
    session_id: str,
    _: str = Depends(require_lecturer),
):
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


class SessionMaterialsRequest(BaseModel):
    slides_url: str = ""
    supplementary_url: str = ""


@router.patch("/sessions/{session_id}/", summary="Set slides and supplementary URLs for a session")
def patch_session_materials(
    session_id: str,
    body: SessionMaterialsRequest,
    _: str = Depends(require_lecturer),
):
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    update_session_materials(session_id, body.slides_url, body.supplementary_url)
    return {"updated": True, "session_id": session_id, "slides_url": body.slides_url, "supplementary_url": body.supplementary_url}


# ── Attendance ────────────────────────────────────────────────

@router.get("/sessions/{session_id}/attendance", summary="View attendance records")
def get_attendance(
    session_id: str,
    status: Literal["PRESENT", "LATE", "ABSENT", "QUIZ"] | None = Query(
        None, description="Filter by status"
    ),
    order: Literal["asc", "desc"] = Query("asc", description="Sort by timestamp"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: str = Depends(require_lecturer),
):
    return list_attendance(
        session_id=session_id,
        status=status,
        order=order,
        limit=limit,
        offset=offset,
    )


class OverrideRequest(BaseModel):
    student_id: str
    status: Literal["PRESENT", "LATE", "ABSENT"]
    reason: str


@router.patch("/sessions/{session_id}/attendance", summary="Manual status override")
def patch_attendance(
    session_id: str,
    body: OverrideRequest,
    _: str = Depends(require_lecturer),
):
    result = override_attendance(
        session_id=session_id,
        student_id=body.student_id,
        status=body.status,
        reason=body.reason,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Student or session not found")
    return {"updated": True, **result}


@router.get("/sessions/{session_id}/export", summary="Export attendance as CSV or JSON")
def export_attendance(
    session_id: str,
    status: Literal["PRESENT", "LATE", "ABSENT"] | None = Query(None),
    format: Literal["csv", "json"] = Query("csv"),
    _: str = Depends(require_lecturer),
):
    records = list_attendance(session_id=session_id, status=status, limit=500)

    if format == "json":
        return records

    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=["student_id", "status", "ts"],
        extrasaction="ignore",
    )
    writer.writeheader()
    writer.writerows(records)
    buf.seek(0)

    filename = f"session_{session_id}_attendance.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Students ──────────────────────────────────────────────────

@router.get("/students/", summary="List registered students")
def get_students(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: str = Depends(require_lecturer),
):
    return list_students(limit=limit, offset=offset)


@router.delete("/students/{student_id}", summary="Unregister a student")
def remove_student(
    student_id: str,
    _: str = Depends(require_lecturer),
):
    deleted = delete_student(student_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Student not found")
    return {"deleted": True, "student_id": student_id}
