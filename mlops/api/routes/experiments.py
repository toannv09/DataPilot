"""CRUD experiment + chạy experiment."""

import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from agents.base_agent import ExperimentContext
from agents.router import route

router = APIRouter()


class ExperimentCreate(BaseModel):
    problem_id: str
    experiment_type: str
    user_query: str = ""
    domain_context: str = ""


@router.post("/experiments")
def create_experiment(exp: ExperimentCreate, request: Request):
    if exp.problem_id not in request.app.state.problems:
        raise HTTPException(status_code=404, detail="Problem không tồn tại")

    experiment_id = str(uuid.uuid4())
    record = {"id": experiment_id, **exp.model_dump()}
    request.app.state.experiments[experiment_id] = record
    request.app.state.runs[experiment_id] = []
    return record


@router.post("/experiments/{experiment_id}/run")
async def run_experiment(experiment_id: str, request: Request):
    exp = request.app.state.experiments.get(experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment không tồn tại")

    files = request.app.state.uploaded_files.get(experiment_id, {})

    context = ExperimentContext(
        experiment_type=exp["experiment_type"],
        user_query=exp["user_query"],
        domain_context=exp["domain_context"],
        files=files,
    )

    agent = route(exp["experiment_type"], context)
    if agent is None:
        raise HTTPException(status_code=400, detail="Loại experiment này không có agent xử lý")

    result = await agent.run(context)

    job_id = str(uuid.uuid4())
    run_record = {
        "job_id": job_id,
        "success": result.success,
        "summary": result.summary,
        "data": result.data,
        "charts": result.charts,
        "error": result.error,
    }
    request.app.state.runs[experiment_id].append(run_record)

    report_path = result.data.get("report_path") if result.data else None
    if report_path:
        request.app.state.reports[job_id] = report_path

    return {"job_id": job_id, "success": result.success}


@router.get("/experiments/{experiment_id}/runs")
def list_runs(experiment_id: str, request: Request):
    return request.app.state.runs.get(experiment_id, [])
