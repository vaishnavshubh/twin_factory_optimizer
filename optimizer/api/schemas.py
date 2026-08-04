"""Pydantic request/response models for the FastAPI optimize surface.

Kept separate from LangGraph TypedDicts so HTTP validation stays strict while
the graph state remains a plain dict-compatible TypedDict.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class OptimizeRequest(BaseModel):
    """Invocation payload for ``POST /optimize``.

    ``project_name`` selects which OFacT project twin to read (default matches
    the tutorial board-game factory).
    """

    project_name: str = Field(
        default="bicycle_world",
        description="OFacT project folder under projects/ (e.g. bicycle_world).",
        examples=["bicycle_world", "tutorial"],
    )
    state_model_file: Optional[str] = Field(
        default=None,
        description=(
            "Optional twin workbook filename. When omitted, settings default "
            "to bicycle_factory.xlsx for Bicycle World."
        ),
    )


class BottleneckOut(BaseModel):
    """Bottleneck record returned for observability alongside actions."""

    resource_id: str
    resource_name: str
    resource_type: str
    utilization: float
    threshold: float
    severity: str
    reason: str


class ProposedActionOut(BaseModel):
    """Rerouting / placement action intended for OFacT resource agents."""

    action_type: str
    source_station: str
    target_station: str
    resource_id: str
    rationale: str
    priority: int


class OptimizeResponse(BaseModel):
    """Optimize workflow result.

    ``proposed_actions`` is the primary Act-phase output. Bottlenecks and
    utilization are included so callers can audit why actions were proposed
    without a second round-trip.
    """

    project_name: str
    mode: str
    proposed_actions: list[ProposedActionOut]
    identified_bottlenecks: list[BottleneckOut] = Field(default_factory=list)
    current_utilization: dict[str, float] = Field(default_factory=dict)
    assembly_sequence: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """Liveness payload for Cloud Run / load balancers."""

    status: str = "ok"
    service: str = "smart-factory-optimizer"
