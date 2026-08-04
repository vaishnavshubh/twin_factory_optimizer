"""Infrastructure adapters: OFacT twin I/O, config, and future GCP wiring."""

__all__ = [
    "list_twin_sheets",
    "read_assembly_sequence",
    "read_factory_floor_state",
    "read_static_resources",
    "resolve_twin_path",
    "write_routing_actions",
]


def __getattr__(name: str):
    if name in __all__:
        from optimizer.infrastructure import ofact_connector

        return getattr(ofact_connector, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
