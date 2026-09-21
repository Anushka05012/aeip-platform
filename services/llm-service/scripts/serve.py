"""Start the local HTTP bridge between the AEIP RAG engine and frontend."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.web_api import serve


if __name__ == "__main__":
    serve(port=int(os.getenv("AEIP_INTELLIGENCE_PORT", "8001")))
