"""POST /upload — upload file CSV/Excel cho một experiment."""

import os

import pandas as pd
from fastapi import APIRouter, File, Request, UploadFile

router = APIRouter()

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "raw", "uploads")


@router.post("/upload")
async def upload_file(request: Request, experiment_id: str, file: UploadFile = File(...)):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    path = os.path.join(UPLOAD_DIR, file.filename)

    contents = await file.read()
    with open(path, "wb") as f:
        f.write(contents)

    if file.filename.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)

    request.app.state.uploaded_files.setdefault(experiment_id, {})[file.filename] = df

    return {"filename": file.filename, "path": path}
