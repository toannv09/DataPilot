"""CRUD bài toán."""

import uuid

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class ProblemCreate(BaseModel):
    name: str
    description: str = ""


@router.post("/problems")
def create_problem(problem: ProblemCreate, request: Request):
    problem_id = str(uuid.uuid4())
    record = {"id": problem_id, "name": problem.name, "description": problem.description}
    request.app.state.problems[problem_id] = record
    return record


@router.get("/problems")
def list_problems(request: Request):
    return list(request.app.state.problems.values())
