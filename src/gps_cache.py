"""
Build the GPS heatmap cache from all running FIT files.

Usage:
    uv run python -m src.gps_cache
"""

from src.loaders import build_gps_cache

if __name__ == "__main__":
    build_gps_cache()
