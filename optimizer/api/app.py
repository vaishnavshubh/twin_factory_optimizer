"""FastAPI application serving the compiled LangGraph optimize workflow.

Also hosts the portfolio demo UI at ``/`` so recruiters get a clickable surface
on the same Cloud Run URL as the API.

Run locally (repo root)::

    PYTHONPATH=. uvicorn optimizer.api.app:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from optimizer.agents.graph import run_optimize
from optimizer.api.schemas import (
    BottleneckOut,
    HealthResponse,
    OptimizeRequest,
    OptimizeResponse,
    ProposedActionOut,
)
from optimizer.infrastructure.config import get_settings

_STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Smart Factory Digital Twin Optimizer",
    description=(
        "LangGraph multi-agent optimizer over OFacT twin state. "
        "POST /optimize returns proposed routing actions for resource agents. "
        "GET / serves the portfolio demo UI."
    ),
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def demo_home() -> FileResponse:
    """Portfolio demo — brand-first UI that invokes ``POST /optimize``."""
    return FileResponse(_STATIC_DIR / "index.html")


@app.get("/health", response_model=HealthResponse, tags=["ops"])
def health() -> HealthResponse:
    """Cheap liveness check — does not touch the twin or LangGraph."""
    return HealthResponse()


@app.post(
    "/optimize",
    response_model=OptimizeResponse,
    status_code=status.HTTP_200_OK,
    tags=["optimize"],
    summary="Run the LangGraph optimize workflow",
)
def optimize(payload: OptimizeRequest) -> OptimizeResponse:
    """Accept an invocation request, run the compiled graph, return actions.

    Secrets such as ``OPENAI_API_KEY`` are never accepted in the body — they
    must come from the process environment / Cloud Run secret mounts.
    """
    settings = get_settings()
    project_name = payload.project_name or settings.default_project

    try:
        result: dict[str, Any] = run_optimize(
            project_name=project_name,
            state_model_file=payload.state_model_file,
        )
    except Exception as exc:  # noqa: BLE001 — map unexpected failures to 500
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Optimize workflow failed: {exc}",
        ) from exc

    errors = list(result.get("errors") or [])
    if errors and not result.get("proposed_actions") and not result.get(
        "current_utilization"
    ):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": "Twin ingest failed", "errors": errors},
        )

    return OptimizeResponse(
        project_name=str(result.get("project_name") or project_name),
        mode=str(result.get("mode") or settings.ofact_mode.value),
        proposed_actions=[
            ProposedActionOut(**action)
            for action in (result.get("proposed_actions") or [])
        ],
        identified_bottlenecks=[
            BottleneckOut(**item)
            for item in (result.get("identified_bottlenecks") or [])
        ],
        current_utilization=dict(result.get("current_utilization") or {}),
        assembly_sequence=list(result.get("assembly_sequence") or []),
        errors=errors,
    )


def create_app() -> FastAPI:
    """Factory for tests and alternative ASGI loaders."""
    return app
