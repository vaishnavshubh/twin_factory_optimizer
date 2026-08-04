"""LangGraph agent nodes and compiled optimize graph."""

from typing import Any

__all__ = [
    "bottleneck_predictor_node",
    "build_optimize_graph",
    "compile_optimize_graph",
    "ofact_reader_node",
    "optimize_graph",
    "rerouting_agent_node",
    "run_optimize",
]


def __getattr__(name: str) -> Any:
    """Lazy exports so importing ``optimizer.agents`` does not compile the graph."""
    if name in {
        "build_optimize_graph",
        "compile_optimize_graph",
        "optimize_graph",
        "run_optimize",
    }:
        from optimizer.agents import graph as graph_module

        return getattr(graph_module, name)
    if name in {
        "bottleneck_predictor_node",
        "ofact_reader_node",
        "rerouting_agent_node",
    }:
        from optimizer.agents import nodes as nodes_module

        return getattr(nodes_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
