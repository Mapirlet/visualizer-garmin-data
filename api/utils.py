"""
Helper utilities shared across routers.
"""
from __future__ import annotations
import math
from typing import Any
import pandas as pd


def df_to_records(df: pd.DataFrame) -> list[dict]:
    """
    Convert a DataFrame to a list of JSON-safe dicts.
    Converts date/datetime columns to ISO strings and replaces NaN/inf with None.
    """
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime("%Y-%m-%d")
        elif out[col].dtype == object:
            # date objects (not datetime)
            try:
                sample = out[col].dropna().iloc[0] if not out[col].dropna().empty else None
                if sample is not None and hasattr(sample, "isoformat"):
                    out[col] = out[col].apply(lambda v: v.isoformat() if v is not None and not _is_nan(v) else None)
            except (IndexError, TypeError):
                pass

    records = out.to_dict(orient="records")
    return [_clean(r) for r in records]


def _is_nan(v: Any) -> bool:
    try:
        return math.isnan(v)
    except TypeError:
        return False


def _clean(record: dict) -> dict:
    return {
        k: (None if _is_nan(v) or v == float("inf") or v == float("-inf") else v)
        for k, v in record.items()
    }


def ols_line(x: pd.Series, y: pd.Series) -> dict | None:
    """Return OLS slope, intercept, r2 for a simple linear regression."""
    import numpy as np
    mask = x.notna() & y.notna()
    xv, yv = x[mask].values, y[mask].values
    if len(xv) < 3:
        return None
    coeffs = np.polyfit(xv, yv, 1)
    slope, intercept = coeffs
    y_pred = slope * xv + intercept
    ss_res = ((yv - y_pred) ** 2).sum()
    ss_tot = ((yv - yv.mean()) ** 2).sum()
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    x_range = [float(xv.min()), float(xv.max())]
    return {
        "slope": float(slope),
        "intercept": float(intercept),
        "r2": float(r2),
        "x": x_range,
        "y": [float(slope * x_range[0] + intercept), float(slope * x_range[1] + intercept)],
    }
