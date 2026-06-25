"""Entry point Streamlit — khởi tạo session state và routing."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from views import (
    create_problem,
    experiment_config,
    home,
    report,
    run_experiment,
    run_history,
    select_experiment,
)

st.set_page_config(page_title="AutoEDA", layout="wide")

DEFAULTS = {
    "page": "home",
    "problems": [],
    "current_problem_idx": None,
    "current_experiment_type": None,
    "files": {},
    "domain_context": "",
    "user_query": "",
    "context": None,
    "detection": None,
    "merge_decision": None,
    "agent_result": None,
    "report_path": None,
    "runs": [],
    "pipeline_steps": {},
    "pipeline_stage_idx": 0,
    "pipeline_result": None,
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value

PAGES = {
    "home": home,
    "create_problem": create_problem,
    "select_experiment": select_experiment,
    "experiment_config": experiment_config,
    "run_experiment": run_experiment,
    "run_history": run_history,
    "report": report,
}

PAGES[st.session_state.page].render()
