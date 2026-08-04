"""FastAPI surface that serves the compiled LangGraph workflow."""

from __future__ import annotations

from typing import Any

__all__ = ["app", "create_app"]


def __getattr__(name: str) -> Any:
    # Lazy export avoids circular import when uvicorn loads optimizer.api.app.
    if name in {"app", "create_app"}:
        import importlib

        app_module = importlib.import_module("optimizer.api.app")
        return getattr(app_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
