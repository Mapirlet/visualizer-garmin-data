"""
Shared application state — loaded once at startup, injected via Depends.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd


@dataclass
class AppState:
    activities: pd.DataFrame = field(default_factory=pd.DataFrame)
    sleep: pd.DataFrame = field(default_factory=pd.DataFrame)
    technique: Optional[pd.DataFrame] = None
    gps: Optional[pd.DataFrame] = None


# Single global instance populated by the lifespan handler in main.py
state = AppState()
