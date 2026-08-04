"""LangGraph state schema for the Smart Factory Digital Twin Optimizer.

FactoryState is the single shared memory object passed between LangGraph nodes
(ofact_reader → bottleneck_predictor → rerouting_agent). Using TypedDict keeps
the graph serializable and matches LangGraph's preferred state style; nested
TypedDicts keep bottleneck and action payloads strict without adding Pydantic
until the FastAPI layer (Step 4) needs request/response validation.

Field shapes follow the tutorial twin (`projects/tutorial/models/twin/mini_model.xlsx`):
resource labels like ``packaging_station_ws``, process ids like ``packaging_vap``.
"""

from __future__ import annotations

from typing import Any, TypedDict


class ResourceUtilization(TypedDict):
    """Capacity snapshot for one twin resource (WorkStation, Warehouse, …)."""

    resource_id: str
    resource_name: str
    resource_type: str
    utilization: float
    capacity_units: int
    sheet_source: str


class AssemblyStep(TypedDict):
    """One step in the tutorial process chain (Process / ValueAddedProcess)."""

    step_id: str
    process_name: str
    station_id: str
    sequence_index: int
    estimated_duration_min: float


class Bottleneck(TypedDict):
    """A resource flagged as near or over capacity by the predictor node.

    Why a structured object instead of a bare string: the rerouting agent needs
    utilization, threshold, and station context to propose concrete actions
    without re-scanning the full utilization map.
    """

    resource_id: str
    resource_name: str
    resource_type: str
    utilization: float
    threshold: float
    severity: str
    reason: str


class ProposedAction(TypedDict):
    """Rerouting / placement decision intended for OFacT resource agents.

    Aligns with the connector write-back payload so Step 3 can call
    ``write_routing_actions`` without reshaping fields.
    """

    action_type: str
    source_station: str
    target_station: str
    resource_id: str
    rationale: str
    priority: int


class FactoryFloorSnapshot(TypedDict):
    """Connector ingest payload before LangGraph accumulators are filled."""

    project_name: str
    twin_path: str
    mode: str
    current_utilization: dict[str, float]
    resources: list[ResourceUtilization]
    assembly_sequence: list[AssemblyStep]
    metadata: dict[str, Any]


class FactoryState(TypedDict, total=False):
    """LangGraph state for the optimize workflow.

    Required graph fields (always present after the reader node):

    - ``current_utilization``: resource_id → utilization in ``[0.0, 1.0+]``
    - ``assembly_sequence``: ordered tutorial process steps
    - ``identified_bottlenecks``: filled by ``bottleneck_predictor_node``
    - ``proposed_actions``: filled by ``rerouting_agent_node``

    Context fields (``project_name``, ``resources``, …) are set by the reader
    so downstream nodes do not re-query OFacT. ``total=False`` allows an empty
    initial invoke payload; nodes treat missing lists as ``[]``.

    Nodes return full replacements for their owned fields (no list reducers),
    which keeps re-invokes idempotent after ``ofact_reader_node`` resets
    bottleneck/action accumulators.
    """

    # --- Required semantic fields (Step 2 contract) ---
    current_utilization: dict[str, float]
    assembly_sequence: list[AssemblyStep]
    identified_bottlenecks: list[Bottleneck]
    proposed_actions: list[ProposedAction]

    # --- Ingest / context (populated by ofact_reader_node) ---
    project_name: str
    state_model_file: str
    twin_path: str
    mode: str
    resources: list[ResourceUtilization]
    metadata: dict[str, Any]
    errors: list[str]


def empty_factory_state(
    *,
    project_name: str = "bicycle_world",
) -> FactoryState:
    """Return a blank state suitable as a LangGraph invoke seed.

    Starting from an explicit empty state avoids ``KeyError`` in nodes that
    append to bottleneck/action lists before the reader has run in tests.
    """
    return FactoryState(
        project_name=project_name,
        twin_path="",
        mode="",
        current_utilization={},
        assembly_sequence=[],
        identified_bottlenecks=[],
        proposed_actions=[],
        resources=[],
        metadata={},
        errors=[],
    )


def factory_state_from_floor_snapshot(
    snapshot: FactoryFloorSnapshot,
    *,
    identified_bottlenecks: list[Bottleneck] | None = None,
    proposed_actions: list[ProposedAction] | None = None,
) -> FactoryState:
    """Promote a connector floor snapshot into LangGraph FactoryState.

    Keeps ingest mapping in one place so Step 3 reader nodes stay thin and the
    tutorial field names cannot drift between connector and graph state.
    """
    return FactoryState(
        project_name=snapshot["project_name"],
        twin_path=snapshot["twin_path"],
        mode=snapshot["mode"],
        current_utilization=dict(snapshot["current_utilization"]),
        assembly_sequence=list(snapshot["assembly_sequence"]),
        resources=list(snapshot["resources"]),
        metadata=dict(snapshot.get("metadata", {})),
        identified_bottlenecks=list(identified_bottlenecks or []),
        proposed_actions=list(proposed_actions or []),
        errors=[],
    )


__all__ = [
    "AssemblyStep",
    "Bottleneck",
    "FactoryFloorSnapshot",
    "FactoryState",
    "ProposedAction",
    "ResourceUtilization",
    "empty_factory_state",
    "factory_state_from_floor_snapshot",
]
