"""
stepgen.io.results
==================
Save/load sweep DataFrames and export candidate JSON records.

Supported formats
-----------------
CSV     — always available (pandas built-in)
Parquet — requires pyarrow; graceful ImportError if unavailable

Usage
-----
    from stepgen.io.results import save_results, load_results, export_candidate_json

    save_results(df, "sweep.csv")
    save_results(df, "sweep.parquet")      # needs pyarrow

    df = load_results("sweep.csv")
    df = load_results("sweep.parquet")

    export_candidate_json(config, metrics, layout, "best_candidate.json")
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig
    from stepgen.design.layout import LayoutResult
    from stepgen.models.metrics import DeviceMetrics


def save_results(
    df: pd.DataFrame,
    path: str | Path,
    *,
    fmt: str | None = None,
) -> None:
    """
    Save a sweep results DataFrame to disk.

    The format is inferred from the file extension when ``fmt`` is not given:
    ``.csv`` → CSV, ``.parquet`` → Parquet (requires pyarrow).

    Parameters
    ----------
    df   : sweep DataFrame (from ``sweep()``)
    path : output file path
    fmt  : ``'csv'`` or ``'parquet'``; inferred from extension if None
    """
    path = Path(path)
    resolved_fmt = fmt or path.suffix.lstrip(".").lower()

    if resolved_fmt == "csv":
        df.to_csv(path, index=False)
    elif resolved_fmt == "parquet":
        try:
            df.to_parquet(path, index=False)
        except ImportError as exc:
            raise ImportError(
                "Parquet format requires pyarrow: pip install pyarrow"
            ) from exc
    else:
        raise ValueError(
            f"Unknown format {resolved_fmt!r}. Use 'csv' or 'parquet'."
        )


def load_results(path: str | Path) -> pd.DataFrame:
    """
    Load a sweep results DataFrame from disk.

    Format is inferred from the file extension (``.csv`` or ``.parquet``).

    Parameters
    ----------
    path : file path written by ``save_results``

    Returns
    -------
    pd.DataFrame
    """
    path = Path(path)
    ext  = path.suffix.lstrip(".").lower()

    if ext == "csv":
        return pd.read_csv(path)
    elif ext == "parquet":
        return pd.read_parquet(path)
    else:
        raise ValueError(
            f"Unrecognised file extension {path.suffix!r}. "
            "Expected .csv or .parquet."
        )


def _to_json_serialisable(value: object) -> object:
    """Recursively convert numpy scalars and other non-JSON types to Python natives."""
    import numpy as np  # local import; numpy is a hard dependency
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and (value != value):   # NaN
        return None
    return value


def export_candidate_json(
    config: "DeviceConfig",
    metrics: "DeviceMetrics",
    layout: "LayoutResult",
    path: str | Path,
) -> None:
    """
    Export a candidate's geometry, metrics, and layout as a JSON file.

    Parameters
    ----------
    config  : DeviceConfig
    metrics : DeviceMetrics (from compute_metrics)
    layout  : LayoutResult  (from compute_layout)
    path    : output .json file path
    """
    record: dict = {}

    # ── Geometry (SI) ──────────────────────────────────────────────────────
    geom = config.geometry
    record["geometry"] = {
        "Nmc":   geom.Nmc,
        "Mcd_m": geom.main.Mcd,
        "Mcw_m": geom.main.Mcw,
        "Mcl_m": geom.main.Mcl,
        "mcd_m": geom.rung.mcd,
        "mcw_m": geom.rung.mcw,
        "mcl_m": geom.rung.mcl,
        "pitch_m": geom.rung.pitch,
        "exit_width_m": geom.junction.exit_width,
        "exit_depth_m": geom.junction.exit_depth,
    }

    # ── Operating point ────────────────────────────────────────────────────
    record["operating"] = {
        "Po_in_mbar": config.operating.Po_in_mbar,
        "Qw_in_mlhr": config.operating.Qw_in_mlhr,
        "P_out_mbar": config.operating.P_out_mbar,
    }

    # ── Metrics ────────────────────────────────────────────────────────────
    record["metrics"] = {
        f.name: _to_json_serialisable(getattr(metrics, f.name))
        for f in dataclasses.fields(metrics)
    }

    # ── Layout ─────────────────────────────────────────────────────────────
    record["layout"] = {
        f.name: _to_json_serialisable(getattr(layout, f.name))
        for f in dataclasses.fields(layout)
    }

    path = Path(path)
    with open(path, "w") as fh:
        json.dump(record, fh, indent=2)
