"""Aether UI server entry point and FastAPI application re-export."""

from __future__ import annotations

from ui.app import app
from ui.__main__ import main

__all__ = ["app", "main"]

if __name__ == "__main__":
    main()
