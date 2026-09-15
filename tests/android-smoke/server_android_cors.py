import argparse
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=("standard", "fault"), default="standard")
parser.add_argument("--port", type=int, default=18010)
args = parser.parse_args()

from server.server import app, server_config  # noqa: E402

if args.mode == "fault":
    origins = server_config.get_cors("allowed_origins", [])
    if isinstance(origins, str):
        origins = [value.strip() for value in origins.split(",") if value.strip()]
    server_config.config_data.setdefault("cors", {})["allowed_origins"] = [
        origin for origin in origins if origin != "https://localhost"
    ]

uvicorn.run(app, host="127.0.0.1", port=args.port)
