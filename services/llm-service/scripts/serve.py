"""Start the AEIP intelligence API."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")  # before importing the API, which reads settings at import time

from src.web_api import serve  # noqa: E402


if __name__ == "__main__":
    # Containers and hosts need 0.0.0.0; locally 127.0.0.1 keeps the API off the network.
    serve(host=os.getenv("AEIP_HOST", "127.0.0.1"), port=int(os.getenv("PORT", os.getenv("AEIP_INTELLIGENCE_PORT", "8001"))))
