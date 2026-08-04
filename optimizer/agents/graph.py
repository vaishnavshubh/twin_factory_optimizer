"""Compiled LangGraph workflow for factory-floor optimization.

Graph topology (linear, deterministic):

    START → ofact_reader → bottleneck_predictor → rerouting_agent → END

Compiled once at import so FastAPI (Step 4) and local smoke tests share the
same graph object. Invoke with an optional seed, e.g.
``optimize_graph.invoke({"project_name": "tutorial"})``.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from optimizer.agents.nodes import (
    bottleneck_predictor_node,
    ofact_reader_node,
    rerouting_agent_node,
)
from optimizer.models.factory_state import FactoryState, empty_factory_state


def build_optimize_graph() -> StateGraph:
    """Construct the uncompiled StateGraph (useful for tests/extensions)."""
    graph = StateGraph(FactoryState)
    graph.add_node("ofact_reader", ofact_reader_node)
    graph.add_node("bottleneck_predictor", bottleneck_predictor_node)
    graph.add_node("rerouting_agent", rerouting_agent_node)

    graph.add_edge(START, "ofact_reader")
    graph.add_edge("ofact_reader", "bottleneck_predictor")
    graph.add_edge("bottleneck_predictor", "rerouting_agent")
    graph.add_edge("rerouting_agent", END)
    return graph


def compile_optimize_graph() -> Any:
    """Compile the optimize workflow for ``.invoke`` / ``.stream``."""
    return build_optimize_graph().compile()


# Shared compiled graph — built lazily so Cloud Run can bind PORT before
# LangGraph finishes importing/compiling.
_optimize_graph: Any | None = None


def get_optimize_graph() -> Any:
    """Return the singleton compiled graph, compiling on first use."""
    global _optimize_graph
    if _optimize_graph is None:
        _optimize_graph = compile_optimize_graph()
    return _optimize_graph


def run_optimize(
    *,
    project_name: str = "bicycle_world",
    state_model_file: str | None = None,
    initial_state: FactoryState | None = None,
) -> FactoryState:
    """Convenience runner used by smoke tests and FastAPI handlers.

    Returns the full terminal ``FactoryState``, including
    ``identified_bottlenecks`` and ``proposed_actions``.
    """
    seed = dict(initial_state or empty_factory_state(project_name=project_name))
    seed["project_name"] = project_name
    if state_model_file:
        seed["state_model_file"] = state_model_file
    result = get_optimize_graph().invoke(seed)
    return result  # type: ignore[return-value]


def __getattr__(name: str) -> Any:
    """Module-level lazy attribute for ``optimize_graph`` compatibility."""
    if name == "optimize_graph":
        return get_optimize_graph()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "build_optimize_graph",
    "compile_optimize_graph",
    "get_optimize_graph",
    "optimize_graph",
    "run_optimize",
]
