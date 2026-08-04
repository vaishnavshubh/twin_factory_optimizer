"""Container entrypoint for Cloud Run / Docker.

Explicitly puts ``/app`` on ``sys.path`` before importing the ASGI app so
Uvicorn never fails with \"Could not import module optimizer.api.app\" when
``PYTHONPATH`` is missing or overridden at runtime.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    app_root = Path(__file__).resolve().parents[2]  # /app when installed as /app/optimizer/...
    # In the image layout, entrypoint lives at /app/optimizer/api/entrypoint.py
    # parents[0]=api, [1]=optimizer, [2]=/app
    if str(app_root) not in sys.path:
        sys.path.insert(0, str(app_root))

    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(
        "optimizer.api.app:app",
        host="0.0.0.0",
        port=port,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
