"""Smart Factory Digital Twin Optimizer — LangGraph orchestration layer.

This package sits beside the OFacT framework (`ofact/`) and owns the
multi-agent factory-floor optimization pipeline destined for Google Cloud Run.
Keeping it separate avoids colliding with OFacT's SPADE agent control and Flask
analytics API while still reading the same twin Excel models under
`projects/*/models/twin/`.
"""

__version__ = "0.1.0"
