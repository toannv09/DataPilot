"""GET /report/{job_id} — lấy báo cáo đã sinh."""

import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

router = APIRouter()


@router.get("/report/{job_id}")
def get_report(job_id: str, request: Request):
    path = request.app.state.reports.get(job_id)
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Báo cáo không tồn tại")
    return FileResponse(path)
