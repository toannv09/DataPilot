"""FastAPI app — entry point cho backend API."""

from dotenv import load_dotenv
from fastapi import FastAPI

from mlops.api.routes import experiments, problems, report, upload

load_dotenv()

app = FastAPI(title="DataPilot API")

app.state.problems = {}
app.state.experiments = {}
app.state.runs = {}
app.state.uploaded_files = {}
app.state.reports = {}

app.include_router(problems.router)
app.include_router(experiments.router)
app.include_router(upload.router)
app.include_router(report.router)
