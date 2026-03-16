"""
Build the FIT file index (activity_id → fit path).

Usage:
    uv run python -m src.fit_index
"""

from src.loaders import build_fit_index

if __name__ == "__main__":
    build_fit_index()
