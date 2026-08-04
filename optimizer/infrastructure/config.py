"""Environment-driven settings for the optimizer layer.

Centralizing configuration here keeps secrets out of source and lets the same
code path run locally (stub twin data) or later against live OFacT + Cloud Run
without rewriting agent nodes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load a local .env if present; never commit secrets. Existing repo .env is
# left untouched — we only read values that are already in the process env.
load_dotenv(override=False)

# Repo root is three levels above this file: optimizer/infrastructure/config.py
_REPO_ROOT: Path = Path(__file__).resolve().parents[2]


class OFactMode(str, Enum):
    """How the connector obtains factory-floor state.

    stub: Light-parse OFacT Excel twins (Bicycle World / tutorial) without SPADE.
    live: Call into OFacT persistence (scaffolded; full wiring comes later).
    """

    STUB = "stub"
    LIVE = "live"


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings resolved once from the environment.

    Attributes:
        ofact_mode: Whether to use stub or live twin I/O.
        repo_root: Absolute path to the monorepo root containing `projects/`.
        default_project: OFacT project folder name under `projects/`.
        default_state_model_file: Default Excel twin workbook filename.
        twin_relative_dir: Relative twin directory inside a project (plural
            `models/twin/` matches OFacT's `get_state_model_file_path`).
        openai_api_key: Optional LLM key for later enrichment; never
            hardcoded — must be supplied via env / Cloud Run secrets.
        stub_actions_output_dir: Where stub write-backs dump proposed actions.
        bottleneck_threshold: Utilization at/above which a resource is flagged
            (Bicycle World painting/body-kit stubs sit near capacity).
    """

    ofact_mode: OFactMode
    repo_root: Path
    default_project: str
    default_state_model_file: str
    twin_relative_dir: str
    openai_api_key: Optional[str]
    stub_actions_output_dir: Path
    bottleneck_threshold: float


def _parse_mode(raw: str) -> OFactMode:
    """Map an env string to OFactMode; fall back to stub for safety."""
    normalized = raw.strip().lower()
    try:
        return OFactMode(normalized)
    except ValueError:
        return OFactMode.STUB


def get_settings() -> Settings:
    """Build Settings from environment variables.

    Why a factory instead of module-level constants: Cloud Run injects `$PORT`
    and secrets at process start; re-reading via this function keeps tests and
    future hot-reload paths honest about where values come from.
    """
    repo_root = Path(os.getenv("OPTIMIZER_REPO_ROOT", str(_REPO_ROOT))).resolve()
    actions_dir = Path(
        os.getenv(
            "OPTIMIZER_STUB_ACTIONS_DIR",
            str(repo_root / "optimizer" / ".stub_output"),
        )
    )

    return Settings(
        ofact_mode=_parse_mode(os.getenv("OFACT_MODE", OFactMode.STUB.value)),
        repo_root=repo_root,
        # Bicycle World scenario twin is the default portfolio model.
        default_project=os.getenv("OFACT_PROJECT", "bicycle_world"),
        default_state_model_file=os.getenv(
            "OFACT_STATE_MODEL_FILE", "bicycle_factory.xlsx"
        ),
        twin_relative_dir=os.getenv(
            "OFACT_TWIN_DIR", "scenarios/current/models/twin"
        ),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        stub_actions_output_dir=actions_dir,
        bottleneck_threshold=float(os.getenv("BOTTLENECK_THRESHOLD", "0.80")),
    )
