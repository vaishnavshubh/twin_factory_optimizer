"""OFacT twin connector with stubbed read/write for offline LangGraph work.

OFacT's full stack (SPADE agents, XMPP, Excel deserialization into StateModel)
is heavy for early agent-graph iteration. This module exposes a narrow I/O
surface that:

1. Resolves real `projects/{name}/models/twin/*.xlsx` paths (same convention as
   OFacT's `get_state_model_file_path` and the tutorial simulation scripts).
2. Can list sheets on a real workbook when one is present.
3. In stub mode, mirrors the tutorial board-game factory twin
   (`mini_model.xlsx`: packaging station, warehouse, packaging → delivery)
   so LangGraph can be tested without SPADE/XMPP.
4. Scaffolds a live branch that will later call
   `ofact.planning_services.model_generation.persistence.deserialize_state_model`.

Stub labels, names, capacities, and process order follow the tutorial Excel
sheets (`WorkStation`, `Warehouse`, `Storage`, `Process`, `ProcessTimeModel`).
Utilization is not stored in the static twin — stub mode attaches deterministic
synthetic utilization onto those real resource labels for bottleneck logic.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional, Sequence, Union

import pandas as pd
from openpyxl import load_workbook

from optimizer.infrastructure.config import OFactMode, Settings, get_settings
from optimizer.models.factory_state import (
    AssemblyStep,
    FactoryFloorSnapshot,
    ProposedAction,
    ResourceUtilization,
)

# Backward-compatible aliases for Step 1 call sites / docs.
FactoryFloorState = FactoryFloorSnapshot
RoutingAction = ProposedAction


PathLike = Union[str, Path]

# Prefer shop-floor control points; skip huge part-storage catalogs (Bicycle World).
_RESOURCE_SHEET_CLASSES: dict[str, tuple[str, ...]] = {
    "WorkStation": ("WorkStation",),
    "Warehouse": ("Warehouse",),
    "Storage": ("Storage",),
    "ActiveMovingResource": ("ActiveMovingResource",),
}
_MAX_STORAGE_ROWS = 80
_MAX_PROCESS_STEPS = 40

# Deterministic stub utilization keyed by twin labels (tutorial + Bicycle World).
_STUB_UTILIZATION_BY_LABEL: dict[str, float] = {
    # tutorial
    "packaging_station_ws": 0.92,
    "warehouse_w": 0.48,
    "staff_amr": 0.85,
    "board_storage_s": 0.35,
    "pieces_storage_s": 0.40,
    "box_storage_s": 0.30,
    "assembly_station_board_storage_s": 0.55,
    "assembly_station_pieces_storage_s": 0.60,
    "assembly_station_box_storage_s": 0.50,
    "assembly_station_worker_storage_s": 0.70,
    # bicycle world
    "body_kit_ws": 0.91,
    "gear_shift_brakes_ws": 0.84,
    "lightning_pedal_saddle_ws": 0.72,
    "wheel_ws": 0.88,
    "painting_ws": 0.94,
    "main_warehouse_w": 0.57,
}

# Fallback when the twin workbook is missing — Bicycle World line shape.
_FALLBACK_RESOURCES: list[ResourceUtilization] = [
    {
        "resource_id": "body_kit_ws",
        "resource_name": "frame and handlebar",
        "resource_type": "WorkStation",
        "utilization": 0.91,
        "capacity_units": 1,
        "sheet_source": "WorkStation",
    },
    {
        "resource_id": "gear_shift_brakes_ws",
        "resource_name": "gear shift and brakes",
        "resource_type": "WorkStation",
        "utilization": 0.84,
        "capacity_units": 1,
        "sheet_source": "WorkStation",
    },
    {
        "resource_id": "lightning_pedal_saddle_ws",
        "resource_name": "lightning and pedal and saddle",
        "resource_type": "WorkStation",
        "utilization": 0.72,
        "capacity_units": 1,
        "sheet_source": "WorkStation",
    },
    {
        "resource_id": "wheel_ws",
        "resource_name": "wheel",
        "resource_type": "WorkStation",
        "utilization": 0.88,
        "capacity_units": 1,
        "sheet_source": "WorkStation",
    },
    {
        "resource_id": "painting_ws",
        "resource_name": "painting",
        "resource_type": "WorkStation",
        "utilization": 0.94,
        "capacity_units": 1,
        "sheet_source": "WorkStation",
    },
    {
        "resource_id": "main_warehouse_w",
        "resource_name": "Main Warehouse",
        "resource_type": "Warehouse",
        "utilization": 0.57,
        "capacity_units": 1,
        "sheet_source": "Warehouse",
    },
]

_FALLBACK_ASSEMBLY_SEQUENCE: list[AssemblyStep] = [
    {
        "step_id": "body_kit_ws",
        "process_name": "frame and handlebar",
        "station_id": "body_kit_ws",
        "sequence_index": 0,
        "estimated_duration_min": 30.0,
    },
    {
        "step_id": "gear_shift_brakes_ws",
        "process_name": "gear shift and brakes",
        "station_id": "gear_shift_brakes_ws",
        "sequence_index": 1,
        "estimated_duration_min": 30.0,
    },
    {
        "step_id": "lightning_pedal_saddle_ws",
        "process_name": "lightning and pedal and saddle",
        "station_id": "lightning_pedal_saddle_ws",
        "sequence_index": 2,
        "estimated_duration_min": 30.0,
    },
    {
        "step_id": "wheel_ws",
        "process_name": "wheel",
        "station_id": "wheel_ws",
        "sequence_index": 3,
        "estimated_duration_min": 30.0,
    },
    {
        "step_id": "painting_ws",
        "process_name": "painting",
        "station_id": "painting_ws",
        "sequence_index": 4,
        "estimated_duration_min": 30.0,
    },
]

_TWIN_DIR_FALLBACKS: tuple[str, ...] = (
    "scenarios/current/models/twin",
    "models/twin",
)


def resolve_twin_path(
    project_name: str,
    state_model_file: Optional[str] = None,
    *,
    settings: Optional[Settings] = None,
) -> Path:
    """Resolve an absolute path to an OFacT static twin workbook.

    Tries the configured ``twin_relative_dir`` first, then common OFacT layouts
    (Bicycle World ``scenarios/current/models/twin`` and classic ``models/twin``).
    """
    cfg = settings or get_settings()
    filename = state_model_file or cfg.default_state_model_file
    project_root = cfg.repo_root / "projects" / project_name

    candidates: list[Path] = []
    for relative in (cfg.twin_relative_dir, *_TWIN_DIR_FALLBACKS):
        candidate = (project_root / relative / filename).resolve()
        if candidate not in candidates:
            candidates.append(candidate)

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def list_twin_sheets(path: PathLike) -> list[str]:
    """Return Excel sheet names from a twin workbook.

    Useful for validating that a real OFacT model is reachable before
    attempting a live deserialize, without pulling in the full StateModel stack.
    """
    workbook_path = Path(path)
    if not workbook_path.is_file():
        raise FileNotFoundError(
            f"Twin workbook not found at {workbook_path}. "
            "Confirm project_name and OFACT_STATE_MODEL_FILE."
        )
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    try:
        return list(workbook.sheetnames)
    finally:
        workbook.close()


def read_static_resources(
    path: PathLike,
    *,
    settings: Optional[Settings] = None,
) -> list[ResourceUtilization]:
    """Load workstation / storage / warehouse / staff snapshots from the twin.

    Stub mode light-parses tutorial Excel sheets for labels, names, and capacity,
    then attaches deterministic utilization. Live mode will use StateModel.
    """
    cfg = settings or get_settings()
    twin_path = Path(path)

    if cfg.ofact_mode is OFactMode.LIVE:
        return _read_static_resources_live(twin_path)

    if twin_path.exists() and not twin_path.is_file():
        raise IsADirectoryError(f"Expected an .xlsx file, got directory: {twin_path}")

    if twin_path.is_file():
        parsed = _parse_resources_from_excel(twin_path)
        if parsed:
            return parsed
    return deepcopy(_FALLBACK_RESOURCES)


def read_assembly_sequence(
    path: PathLike,
    *,
    settings: Optional[Settings] = None,
) -> list[AssemblyStep]:
    """Load the ordered process sequence from the twin Process sheet.

    Tutorial value-added flow is packaging_vap → delivery_vap, with
    transferprocess_Buffer_WS_p moving material between warehouse buffers and
    the packaging workstation.
    """
    cfg = settings or get_settings()
    twin_path = Path(path)

    if cfg.ofact_mode is OFactMode.LIVE:
        return _read_assembly_sequence_live(twin_path)

    if twin_path.is_file():
        parsed = _parse_assembly_sequence_from_excel(twin_path)
        if parsed:
            return parsed
    return deepcopy(_FALLBACK_ASSEMBLY_SEQUENCE)


def read_factory_floor_state(
    project_name: Optional[str] = None,
    state_model_file: Optional[str] = None,
    *,
    settings: Optional[Settings] = None,
) -> FactoryFloorState:
    """Facade that aggregates twin reads into one LangGraph-ready payload.

    Separating path resolution from resource/sequence reads lets tests swap
    stubs without reimplementing agent ingest logic.
    """
    cfg = settings or get_settings()
    project = project_name or cfg.default_project
    twin_path = resolve_twin_path(project, state_model_file, settings=cfg)

    if cfg.ofact_mode is OFactMode.LIVE:
        return _read_factory_floor_state_live(project, twin_path, cfg)

    resources = read_static_resources(twin_path, settings=cfg)
    sequence = read_assembly_sequence(twin_path, settings=cfg)
    utilization: dict[str, float] = {
        item["resource_id"]: float(item["utilization"]) for item in resources
    }

    sheets: list[str] = []
    twin_exists = twin_path.is_file()
    if twin_exists:
        try:
            sheets = list_twin_sheets(twin_path)
        except OSError:
            sheets = []

    plant = _infer_plant_label(twin_path) if twin_exists else ""
    return {
        "project_name": project,
        "twin_path": str(twin_path),
        "mode": cfg.ofact_mode.value,
        "current_utilization": utilization,
        "resources": resources,
        "assembly_sequence": sequence,
        "metadata": {
            "twin_file_exists": twin_exists,
            "sheet_names": sheets,
            "data_source": "ofact_twin_stub",
            "plant": plant,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "note": (
                f"Stub light-parse of {twin_path.name} for project '{project}'. "
                "Utilization is synthetic; workstation/warehouse labels come from "
                "the Excel twin. Large Storage catalogs are skipped for performance. "
                "Set OFACT_MODE=live once deserialize_state_model wiring is ready."
            ),
        },
    }


def write_routing_actions(
    actions: Sequence[Mapping[str, Any]],
    *,
    project_name: Optional[str] = None,
    settings: Optional[Settings] = None,
) -> Path:
    """Persist proposed routing actions for handoff to OFacT resource agents.

    Stub mode writes a JSON dump under `optimizer/.stub_output/` so the Act
    phase is observable without mutating twin Excel or negotiating via SPADE.
    Live mode will later map these into agent control inputs.
    """
    cfg = settings or get_settings()
    project = project_name or cfg.default_project
    payload = [dict(action) for action in actions]

    if cfg.ofact_mode is OFactMode.LIVE:
        return _write_routing_actions_live(payload, project, cfg)

    output_dir = cfg.stub_actions_output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"{project}_routing_actions_{timestamp}.json"
    document: MutableMapping[str, Any] = {
        "project_name": project,
        "mode": cfg.ofact_mode.value,
        "written_at": datetime.now(timezone.utc).isoformat(),
        "actions": payload,
        "handoff_note": (
            "Stub write-back only. Live mode will push these decisions toward "
            "OFacT ResourceDigitalTwinAgent / WorkStationAgent consumers "
            "(see projects/tutorial agents model board_game.xlsx)."
        ),
    }
    output_path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return output_path


def _parse_resources_from_excel(twin_path: Path) -> list[ResourceUtilization]:
    """Light-parse resource sheets; skip oversized Storage catalogs."""
    resources: list[ResourceUtilization] = []

    for sheet_name, class_names in _RESOURCE_SHEET_CLASSES.items():
        try:
            df = pd.read_excel(twin_path, sheet_name=sheet_name, header=None)
        except ValueError:
            continue
        if df.empty or df.shape[1] < 2:
            continue
        # Bicycle World Storage has thousands of part bins — not useful for demo KPIs.
        if sheet_name == "Storage" and len(df) > _MAX_STORAGE_ROWS:
            continue

        columns = _infer_attribute_row(df)
        label_col = _find_col(columns, "label")
        name_col = _find_col(columns, "name")
        capacity_col = _find_col(columns, "capacity")
        if label_col is None:
            continue

        last_class = ""
        for _, row in df.iterrows():
            cell0 = row.iloc[0]
            if isinstance(cell0, str) and cell0.strip() in class_names:
                last_class = cell0.strip()

            label_val = row.iloc[label_col]
            if not isinstance(label_val, str):
                continue
            label_val = label_val.strip()
            if not _looks_like_ofact_label(label_val):
                continue
            if not last_class:
                continue

            name_val = row.iloc[name_col] if name_col is not None else label_val
            capacity_raw = row.iloc[capacity_col] if capacity_col is not None else 1
            resources.append(
                {
                    "resource_id": label_val,
                    "resource_name": (
                        str(name_val).strip() if pd.notna(name_val) else label_val
                    ),
                    "resource_type": last_class,
                    "utilization": _stub_utilization_for(label_val),
                    "capacity_units": _as_positive_int(capacity_raw, default=1),
                    "sheet_source": sheet_name,
                }
            )

    return _dedupe_resources(resources)


def _parse_assembly_sequence_from_excel(twin_path: Path) -> list[AssemblyStep]:
    """Build assembly order from WorkStations (multi-station) or Process chain."""
    workstation_steps = _parse_workstation_sequence(twin_path)
    if len(workstation_steps) >= 2:
        return workstation_steps

    try:
        process_df = pd.read_excel(twin_path, sheet_name="Process", header=None)
        time_df = pd.read_excel(twin_path, sheet_name="ProcessTimeModel", header=None)
    except ValueError:
        return workstation_steps

    durations = _parse_process_times(time_df)
    processes = _parse_process_rows(process_df)
    if not processes:
        return workstation_steps

    transfers = [p for p in processes if p["kind"] == "Process"]
    vaps = [p for p in processes if p["kind"] == "ValueAddedProcess"]
    ordered = (transfers + _order_vaps_by_successors(vaps))[:_MAX_PROCESS_STEPS]

    default_station = (
        workstation_steps[0]["station_id"] if workstation_steps else "unknown_ws"
    )
    steps: list[AssemblyStep] = []
    for index, proc in enumerate(ordered):
        duration = durations.get(
            proc["time_model_key"], durations.get(proc["label"], 0.0)
        )
        steps.append(
            {
                "step_id": proc["label"],
                "process_name": proc["name"],
                "station_id": default_station,
                "sequence_index": index,
                "estimated_duration_min": float(duration) if duration else 30.0,
            }
        )
    return steps


def _parse_workstation_sequence(twin_path: Path) -> list[AssemblyStep]:
    """Use WorkStation sheet order as the physical assembly line sequence."""
    resources = [
        item
        for item in _parse_resources_from_excel(twin_path)
        if item["resource_type"] == "WorkStation"
    ]
    steps: list[AssemblyStep] = []
    for index, item in enumerate(resources):
        steps.append(
            {
                "step_id": item["resource_id"],
                "process_name": item["resource_name"],
                "station_id": item["resource_id"],
                "sequence_index": index,
                "estimated_duration_min": 30.0,
            }
        )
    return steps


def _stub_utilization_for(label: str) -> float:
    """Return known stub util or a stable pseudo-random value in [0.45, 0.94]."""
    if label in _STUB_UTILIZATION_BY_LABEL:
        return float(_STUB_UTILIZATION_BY_LABEL[label])
    digest = sum(ord(char) for char in label) % 50
    return round(0.45 + digest / 100.0, 2)


def _infer_plant_label(twin_path: Path) -> str:
    try:
        df = pd.read_excel(twin_path, sheet_name="Plant", header=None)
    except ValueError:
        return ""
    columns = _infer_attribute_row(df)
    label_col = _find_col(columns, "label")
    if label_col is None:
        return ""
    for _, row in df.iterrows():
        label_val = row.iloc[label_col]
        if isinstance(label_val, str) and (
            label_val.endswith("_pl") or label_val.endswith("_p")
        ):
            if " " not in label_val and "\n" not in label_val:
                return label_val.strip()
    return ""


def _parse_process_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Extract Process / ValueAddedProcess object rows from the Process sheet."""
    if df.empty or df.shape[1] < 5:
        return []

    # Tutorial Process sheet: row 1 has attribute names (index, label, ...).
    columns = [str(c).strip().lower() if pd.notna(c) else "" for c in df.iloc[1].tolist()]
    label_col = columns.index("label") if "label" in columns else 1
    name_col = columns.index("name") if "name" in columns else 4
    # lead_time_controller column links to ProcessTimeModel labels (*_ptc → *_ptm).
    lead_col = (
        columns.index("lead_time_controller")
        if "lead_time_controller" in columns
        else 5
    )
    succ_col = columns.index("successors") if "successors" in columns else None

    results: list[dict[str, Any]] = []
    last_kind = ""
    for _, row in df.iterrows():
        cell0 = row.iloc[0]
        if isinstance(cell0, str) and cell0.strip() in {"Process", "ValueAddedProcess"}:
            last_kind = cell0.strip()

        label_val = row.iloc[label_col] if label_col < len(row) else None
        if not isinstance(label_val, str):
            continue
        label_val = label_val.strip()
        # Reject notation/example blobs; keep packaging_vap / transferprocess_Buffer_WS_p.
        if " " in label_val or "\n" in label_val:
            continue
        if not (
            label_val.endswith("_vap")
            or label_val.endswith("_p")
        ):
            continue
        if not last_kind:
            continue

        name_val = row.iloc[name_col] if name_col < len(row) else label_val
        lead_val = row.iloc[lead_col] if lead_col < len(row) else ""
        successors_raw = row.iloc[succ_col] if succ_col is not None else ""
        time_model_key = _controller_to_time_model(
            str(lead_val) if pd.notna(lead_val) else ""
        )
        results.append(
            {
                "kind": last_kind,
                "label": label_val,
                "name": str(name_val).strip() if pd.notna(name_val) else label_val,
                "time_model_key": time_model_key,
                "successors": _parse_successor_labels(successors_raw),
            }
        )
    return results


def _parse_process_times(df: pd.DataFrame) -> dict[str, float]:
    """Map ProcessTimeModel labels → duration (value or mue from tutorial sheet)."""
    if df.empty or df.shape[1] < 5:
        return {}

    columns = [str(c).strip().lower() if pd.notna(c) else "" for c in df.iloc[1].tolist()]
    label_col = columns.index("label") if "label" in columns else 1
    value_col = columns.index("value") if "value" in columns else 4
    mue_col = columns.index("mue") if "mue" in columns else 5

    times: dict[str, float] = {}
    for _, row in df.iterrows():
        label_val = row.iloc[label_col] if label_col < len(row) else None
        if not isinstance(label_val, str):
            continue
        label_val = label_val.strip()
        # Tutorial object labels are single tokens like packaging_ptm (skip notation/example).
        if " " in label_val or "\n" in label_val or not label_val.endswith("_ptm"):
            continue
        value = row.iloc[value_col] if value_col < len(row) else None
        mue = row.iloc[mue_col] if mue_col < len(row) else None
        numeric = _as_optional_float(value)
        if numeric is None:
            numeric = _as_optional_float(mue)
        if numeric is not None:
            times[label_val] = numeric
    return times


def _as_optional_float(value: Any) -> Optional[float]:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _order_vaps_by_successors(vaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Topological-ish order using tutorial successor lists (packaging → delivery)."""
    if not vaps:
        return []
    by_label = {v["label"]: v for v in vaps}
    successors = {v["label"]: v["successors"] for v in vaps}
    # Roots: never listed as someone else's successor.
    referenced = {s for succ in successors.values() for s in succ}
    roots = [v for v in vaps if v["label"] not in referenced]
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    queue = list(roots) if roots else list(vaps)
    while queue:
        current = queue.pop(0)
        if current["label"] in seen:
            continue
        seen.add(current["label"])
        ordered.append(current)
        for succ_label in current["successors"]:
            if succ_label in by_label and succ_label not in seen:
                queue.append(by_label[succ_label])
    for vap in vaps:
        if vap["label"] not in seen:
            ordered.append(vap)
    return ordered


def _controller_to_time_model(controller_label: str) -> str:
    """Map packaging_ptc → packaging_ptm (tutorial naming convention)."""
    label = controller_label.strip()
    if label.endswith("_ptc"):
        return label[:-4] + "_ptm"
    return label


def _parse_successor_labels(raw: Any) -> list[str]:
    if not isinstance(raw, str) or not raw.strip():
        return []
    # Tutorial stores python-ish lists, e.g. "['delivery_vap']".
    cleaned = raw.strip().strip("[]")
    if not cleaned:
        return []
    parts = [p.strip().strip("'\"") for p in cleaned.split(",")]
    return [p for p in parts if p.endswith("_vap") or p.endswith("_p")]


def _infer_attribute_row(df: pd.DataFrame) -> list[str]:
    """Return lowercased attribute names from the 'index' header row."""
    for _, row in df.head(6).iterrows():
        first = row.iloc[0]
        if isinstance(first, str) and first.strip().lower() == "index":
            return [
                str(c).strip().lower() if pd.notna(c) else "" for c in row.tolist()
            ]
    # Fallback: second row often holds attribute names in tutorial workbooks.
    if len(df) > 1:
        return [
            str(c).strip().lower() if pd.notna(c) else "" for c in df.iloc[1].tolist()
        ]
    return []


def _find_col(columns: Sequence[str], name: str) -> Optional[int]:
    target = name.lower()
    for idx, col in enumerate(columns):
        if col == target:
            return idx
    return None


def _looks_like_ofact_label(label: str) -> bool:
    """Tutorial labels end with short class suffixes (_ws, _w, _s, _amr, ...)."""
    suffixes = ("_ws", "_w", "_s", "_amr", "_pmr", "_cb", "_sr", "_pl", "_et")
    return any(label.endswith(suffix) for suffix in suffixes)


def _as_positive_int(value: Any, *, default: int) -> int:
    try:
        if pd.isna(value):
            return default
        return max(1, int(float(value)))
    except (TypeError, ValueError):
        return default


def _dedupe_resources(
    resources: Sequence[ResourceUtilization],
) -> list[ResourceUtilization]:
    seen: set[str] = set()
    unique: list[ResourceUtilization] = []
    for item in resources:
        key = item["resource_id"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _read_static_resources_live(twin_path: Path) -> list[ResourceUtilization]:
    """Live branch: deserialize OFacT StateModel and extract resource utilization."""
    _ensure_twin_file(twin_path)
    raise NotImplementedError(
        "Live resource extraction is not wired yet. Integration point: "
        "ofact.planning_services.model_generation.persistence.deserialize_state_model"
        f"(state_model_file_path={twin_path!s}). Keep OFACT_MODE=stub until Step "
        "3+ live adapters land."
    )


def _read_assembly_sequence_live(twin_path: Path) -> list[AssemblyStep]:
    """Live branch: derive ordered process steps from the StateModel."""
    _ensure_twin_file(twin_path)
    raise NotImplementedError(
        "Live assembly-sequence extraction is not wired yet. Integration point: "
        "ofact.planning_services.model_generation.persistence.deserialize_state_model "
        "followed by Process / ValueAddedProcess traversal on the StateModel. "
        "Keep OFACT_MODE=stub for LangGraph development."
    )


def _read_factory_floor_state_live(
    project_name: str,
    twin_path: Path,
    settings: Settings,
) -> FactoryFloorState:
    """Live facade scaffolding — documents the OFacT entrypoint for reviewers."""
    _ = settings
    _ensure_twin_file(twin_path)
    raise NotImplementedError(
        "Live factory-floor ingest is scaffolded only. Call chain to implement:\n"
        "  1. ofact.planning_services.model_generation.persistence."
        "deserialize_state_model(...)\n"
        "  2. Map StateModel WorkStation / Warehouse / Storage → utilization\n"
        "  3. Map Process graph → assembly_sequence\n"
        f"Target twin: {twin_path} (project={project_name})."
    )


def _write_routing_actions_live(
    actions: list[dict[str, Any]],
    project_name: str,
    settings: Settings,
) -> Path:
    """Live write-back scaffolding for OFacT resource-agent handoff."""
    _ = (actions, project_name, settings)
    raise NotImplementedError(
        "Live routing write-back is not implemented. Future work: translate "
        "proposed_actions into inputs consumable by ofact.twin.agent_control "
        "ResourceDigitalTwinAgent / WorkStationAgent behaviours."
    )


def _ensure_twin_file(twin_path: Path) -> None:
    """Fail fast with a clear path error before raising NotImplementedError."""
    if not twin_path.is_file():
        raise FileNotFoundError(
            f"Cannot enter live mode: twin workbook missing at {twin_path}."
        )


def utilization_map_from_resources(
    resources: Sequence[ResourceUtilization],
) -> dict[str, float]:
    """Convenience helper for nodes that only need id → utilization."""
    return {item["resource_id"]: float(item["utilization"]) for item in resources}


__all__ = [
    "AssemblyStep",
    "FactoryFloorState",
    "ResourceUtilization",
    "RoutingAction",
    "list_twin_sheets",
    "read_assembly_sequence",
    "read_factory_floor_state",
    "read_static_resources",
    "resolve_twin_path",
    "utilization_map_from_resources",
    "write_routing_actions",
]
