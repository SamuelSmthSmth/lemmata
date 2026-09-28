"""Run the Aether UI server:  uv run python -m ui

For live reload during development use uvicorn directly:

    uv run uvicorn ui.app:app --reload
"""

from __future__ import annotations

import argparse

import uvicorn

from .app import app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Aether proof-checker UI.")
    parser.add_argument("--host", default="127.0.0.1", help="bind address")
    parser.add_argument("--port", type=int, default=8000, help="bind port")
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
