"""
Build the technique cache from all FIT files.

Usage:
    uv run python -m src.cache
"""

from src.loaders import build_technique_cache

if __name__ == "__main__":
    build_technique_cache()
