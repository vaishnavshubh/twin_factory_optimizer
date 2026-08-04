"""LangGraph node functions for the factory optimization pipeline.

Each node receives ``FactoryState`` and returns a partial state update. Nodes are
deliberately rule-based (no LLM required) so the tutorial twin can be optimized
offline; ``OPENAI_API_KEY`` remains available via settings for later enrichment.
"""

from __future__ import annotations

from typing import Any

from optimizer.infrastructure.config import get_settings
from optimizer.infrastructure.ofact_connector import (
    read_factory_floor_state,
    write_routing_actions,
)
from optimizer.models.factory_state import (
    Bottleneck,
    FactoryState,
    ProposedAction,
    ResourceUtilization,
    factory_state_from_floor_snapshot,
)

# Prefer these tutorial resource types when ranking bottlenecks for actioning.
_PRIMARY_BOTTLENECK_TYPES: frozenset[str] = frozenset(
    {"WorkStation", "ActiveMovingResource"}
)


def ofact_reader_node(state: FactoryState) -> dict[str, Any]:
    """Ingest current floor data from the OFacT connector into FactoryState.

    Why first in the graph: downstream predictor/rerouter must operate on a
    consistent twin snapshot. Project name may be supplied in the invoke
    payload; otherwise settings default to the tutorial project.
    """
    settings = get_settings()
    project_name = state.get("project_name") or settings.default_project
    state_model_file = state.get("state_model_file") or None
    errors: list[str] = list(state.get("errors") or [])

    try:
        snapshot = read_factory_floor_state(
            project_name,
            state_model_file,
        )
        seeded = factory_state_from_floor_snapshot(snapshot)
        return {
            "project_name": seeded["project_name"],
            "state_model_file": state_model_file
            or settings.default_state_model_file,
            "twin_path": seeded["twin_path"],
            "mode": seeded["mode"],
            "current_utilization": seeded["current_utilization"],
            "assembly_sequence": seeded["assembly_sequence"],
            "resources": seeded["resources"],
            "metadata": seeded["metadata"],
            # Reset accumulators on each fresh read so re-invokes do not stack.
            "identified_bottlenecks": [],
            "proposed_actions": [],
            "errors": errors,
        }
    except Exception as exc:  # noqa: BLE001 — surface twin I/O failures in state
        errors.append(f"ofact_reader_node failed: {exc}")
        return {
            "project_name": project_name,
            "current_utilization": state.get("current_utilization") or {},
            "assembly_sequence": state.get("assembly_sequence") or [],
            "resources": state.get("resources") or [],
            "identified_bottlenecks": [],
            "proposed_actions": [],
            "errors": errors,
        }


def bottleneck_predictor_node(state: FactoryState) -> dict[str, Any]:
    """Flag resources at or above the utilization threshold as bottlenecks.

    Tutorial stub puts ``packaging_station_ws`` near capacity (~0.92) and
    ``staff_amr`` high (~0.85), which should surface under the default 0.80
    threshold so the rerouting node has concrete targets.
    """
    settings = get_settings()
    threshold = settings.bottleneck_threshold
    utilization = state.get("current_utilization") or {}
    resources = state.get("resources") or []
    resource_index = {item["resource_id"]: item for item in resources}

    bottlenecks: list[Bottleneck] = []
    for resource_id, util in sorted(
        utilization.items(), key=lambda item: item[1], reverse=True
    ):
        if util < threshold:
            continue
        detail: ResourceUtilization | dict[str, Any] = resource_index.get(
            resource_id,
            {
                "resource_id": resource_id,
                "resource_name": resource_id,
                "resource_type": "Unknown",
                "utilization": util,
                "capacity_units": 1,
                "sheet_source": "",
            },
        )
        severity = _severity_for_utilization(util, threshold)
        bottlenecks.append(
            Bottleneck(
                resource_id=resource_id,
                resource_name=str(detail.get("resource_name", resource_id)),
                resource_type=str(detail.get("resource_type", "Unknown")),
                utilization=float(util),
                threshold=threshold,
                severity=severity,
                reason=(
                    f"{detail.get('resource_name', resource_id)} at "
                    f"{util:.0%} utilization (threshold {threshold:.0%})"
                ),
            )
        )

    return {"identified_bottlenecks": bottlenecks}


def rerouting_agent_node(state: FactoryState) -> dict[str, Any]:
    """Propose load-balancing / material actions for identified bottlenecks.

    Works for multi-station plants (Bicycle World) and the single-station
    tutorial twin. Prefer shifting work toward lower-utilization workstations
    and staging kits from the main warehouse.
    """
    settings = get_settings()
    bottlenecks = state.get("identified_bottlenecks") or []
    sequence = state.get("assembly_sequence") or []
    utilization = state.get("current_utilization") or {}
    resources = state.get("resources") or []
    project_name = state.get("project_name") or settings.default_project

    actions: list[ProposedAction] = []
    if not bottlenecks:
        return {"proposed_actions": actions}

    station_ids = {
        step["station_id"] for step in sequence if step.get("station_id")
    } or {
        item["resource_id"]
        for item in resources
        if item.get("resource_type") == "WorkStation"
    }
    warehouses = [
        item["resource_id"]
        for item in resources
        if item.get("resource_type") == "Warehouse"
    ]
    primary = [
        bn
        for bn in bottlenecks
        if bn.get("resource_type") in _PRIMARY_BOTTLENECK_TYPES
    ] or list(bottlenecks)

    for index, bottleneck in enumerate(primary):
        actions.extend(
            _actions_for_bottleneck(
                bottleneck=bottleneck,
                station_ids=station_ids,
                warehouses=warehouses,
                utilization=utilization,
                priority_base=index + 1,
            )
        )

    actions = _dedupe_actions(actions)

    try:
        write_routing_actions(actions, project_name=project_name, settings=settings)
    except Exception as exc:  # noqa: BLE001 — write-back is best-effort in stub
        errors = list(state.get("errors") or [])
        errors.append(f"rerouting_agent_node write-back failed: {exc}")
        return {"proposed_actions": actions, "errors": errors}

    return {"proposed_actions": actions}


def _severity_for_utilization(utilization: float, threshold: float) -> str:
    """Map utilization headroom above threshold to a coarse severity label."""
    if utilization >= 0.95:
        return "critical"
    if utilization >= threshold + 0.10:
        return "high"
    if utilization >= threshold:
        return "medium"
    return "low"


def _actions_for_bottleneck(
    *,
    bottleneck: Bottleneck,
    station_ids: set[str],
    warehouses: list[str],
    utilization: dict[str, float],
    priority_base: int,
) -> list[ProposedAction]:
    """Generate concrete actions for one bottleneck using available twin topology."""
    resource_id = bottleneck["resource_id"]
    resource_type = bottleneck["resource_type"]
    actions: list[ProposedAction] = []
    warehouse_id = warehouses[0] if warehouses else "main_warehouse_w"
    spare_station = _lowest_utilization_among(
        utilization, candidates=station_ids, exclude={resource_id}
    )

    if resource_type == "WorkStation" or resource_id.endswith("_ws"):
        if spare_station and spare_station != resource_id:
            actions.append(
                ProposedAction(
                    action_type="balance_load",
                    source_station=resource_id,
                    target_station=spare_station,
                    resource_id=resource_id,
                    rationale=(
                        f"Shift non-critical work from {resource_id} "
                        f"({bottleneck['utilization']:.0%}) toward {spare_station} "
                        f"({utilization.get(spare_station, 0):.0%}) to relieve the bottleneck."
                    ),
                    priority=priority_base,
                )
            )
        actions.append(
            ProposedAction(
                action_type="advance_material_staging",
                source_station=warehouse_id,
                target_station=resource_id,
                resource_id=warehouse_id,
                rationale=(
                    f"Pre-stage kits from {warehouse_id} into buffers at {resource_id} "
                    "so the station is not blocked waiting on material."
                ),
                priority=priority_base + 1,
            )
        )

    if resource_type == "ActiveMovingResource":
        target = spare_station or next(iter(station_ids), resource_id)
        actions.append(
            ProposedAction(
                action_type="reallocate_mobile_resource",
                source_station=resource_id,
                target_station=target,
                resource_id=resource_id,
                rationale=(
                    f"Reassign {resource_id} toward {target} until utilization "
                    f"falls below {bottleneck['threshold']:.0%}."
                ),
                priority=priority_base,
            )
        )

    if resource_type == "Warehouse" or resource_id.endswith("_w"):
        hottest = _highest_utilization_among(utilization, candidates=station_ids)
        actions.append(
            ProposedAction(
                action_type="stage_kit_at_buffers",
                source_station=resource_id,
                target_station=hottest or next(iter(station_ids), resource_id),
                resource_id=resource_id,
                rationale=(
                    f"Pull staged kits from {resource_id} into the hottest downstream "
                    "workstation buffers to shorten material wait time."
                ),
                priority=priority_base,
            )
        )

    if not actions:
        target = spare_station or next(iter(station_ids), resource_id)
        actions.append(
            ProposedAction(
                action_type="balance_load",
                source_station=resource_id,
                target_station=target,
                resource_id=resource_id,
                rationale=bottleneck.get("reason")
                or f"Balance load away from {resource_id}",
                priority=priority_base,
            )
        )

    return actions


def _lowest_utilization_among(
    utilization: dict[str, float],
    *,
    candidates: set[str],
    exclude: set[str],
) -> str | None:
    pool = [
        (rid, util)
        for rid, util in utilization.items()
        if rid in candidates and rid not in exclude
    ]
    if not pool:
        return _lowest_utilization_resource(utilization, exclude=exclude)
    return min(pool, key=lambda item: item[1])[0]


def _highest_utilization_among(
    utilization: dict[str, float],
    *,
    candidates: set[str],
) -> str | None:
    pool = [
        (rid, util) for rid, util in utilization.items() if rid in candidates
    ]
    if not pool:
        return None
    return max(pool, key=lambda item: item[1])[0]


def _lowest_utilization_resource(
    utilization: dict[str, float],
    *,
    exclude: set[str],
) -> str | None:
    candidates = [
        (rid, util) for rid, util in utilization.items() if rid not in exclude
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[1])[0]


def _dedupe_actions(actions: list[ProposedAction]) -> list[ProposedAction]:
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[ProposedAction] = []
    for action in actions:
        key = (
            action["action_type"],
            action["resource_id"],
            action["source_station"],
            action["target_station"],
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(action)
    return unique


__all__ = [
    "bottleneck_predictor_node",
    "ofact_reader_node",
    "rerouting_agent_node",
]
