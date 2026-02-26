"""
stepgen.io.experiments
======================
Experiment ingestion and predicted-vs-measured comparison.

CSV Schema (required columns)
------------------------------
    device_id           : str
    Po_in_mbar          : float
    Qw_in_mlhr          : float
    position            : int or float  (rung index 0-based, OR fractional 0–1)
    droplet_diameter_um : float
    frequency_hz        : float

Optional column:
    notes               : str

``position`` accepts two formats:
  - Integer rung index (0, 1, 2, …, N-1) — original format
  - Fractional position in [0, 1] (e.g. 0.15, 0.50) — maps to nearest rung index

Usage
-----
    from stepgen.io.experiments import (
        load_experiments,
        compare_to_predictions,
        compute_compare_report,
        calibrate_droplet_model,
    )

    exp_df  = load_experiments("data/experiment.csv")
    comp_df = compare_to_predictions(config, exp_df)
    report  = compute_compare_report(comp_df)
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig


REQUIRED_COLUMNS: frozenset[str] = frozenset({
    "device_id",
    "Po_in_mbar",
    "Qw_in_mlhr",
    "position",
    "droplet_diameter_um",
    "frequency_hz",
})


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def load_experiments(path: str | Path) -> pd.DataFrame:
    """
    Load an experiment CSV and validate the schema.

    Required columns: device_id, Po_in_mbar, Qw_in_mlhr, position,
    droplet_diameter_um, frequency_hz.  An optional ``notes`` column is
    preserved if present; any additional columns are also preserved.

    Parameters
    ----------
    path : path to CSV file

    Returns
    -------
    pd.DataFrame with validated columns; ``position`` cast to int.

    Raises
    ------
    ValueError : if required columns are missing
    """
    df = pd.read_csv(Path(path))
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"Experiment CSV missing required columns: {sorted(missing)}"
        )
    # position: keep as float to support fractional 0–1 values;
    # integer rung indices round-trip faithfully as float.
    df["position"]            = df["position"].astype(float)
    df["Po_in_mbar"]          = df["Po_in_mbar"].astype(float)
    df["Qw_in_mlhr"]          = df["Qw_in_mlhr"].astype(float)
    df["droplet_diameter_um"] = df["droplet_diameter_um"].astype(float)
    df["frequency_hz"]        = df["frequency_hz"].astype(float)
    return df


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def compare_to_predictions(
    config: "DeviceConfig",
    exp_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Join model predictions to experiment records.

    For each unique (Po_in_mbar, Qw_in_mlhr) operating point in *exp_df*,
    the iterative solver is run and per-rung predictions are extracted.
    Results are joined back to each experiment row by its rung ``position``.

    Columns added to the returned DataFrame
    ----------------------------------------
    D_pred_um        : predicted droplet diameter [µm]  (geometry-based, same for all rungs)
    f_pred_hz        : predicted droplet frequency [Hz] at the rung position
    regime           : regime name at the rung position ("ACTIVE", "REVERSE", "OFF")
    diam_residual_um : D_pred_um − droplet_diameter_um
    freq_residual_hz : f_pred_hz  − frequency_hz

    Parameters
    ----------
    config : DeviceConfig
    exp_df : DataFrame from ``load_experiments``

    Returns
    -------
    pd.DataFrame — copy of exp_df with prediction columns appended
    """
    from stepgen.models.droplets import droplet_diameter, droplet_frequency
    from stepgen.models.generator import RungRegime, classify_rungs, iterative_solve

    D_pred_m  = droplet_diameter(config)
    D_pred_um = D_pred_m * 1e6

    # Cache solver results per unique (Po, Qw)
    cache: dict[tuple[float, float], object] = {}

    D_pred_list:  list[float] = []
    f_pred_list:  list[float] = []
    regime_list:  list[str]   = []

    for _, row in exp_df.iterrows():
        Po  = float(row["Po_in_mbar"])
        Qw  = float(row["Qw_in_mlhr"])
        key = (Po, Qw)
        if key not in cache:
            cache[key] = iterative_solve(config, Po_in_mbar=Po, Qw_in_mlhr=Qw)
        sim = cache[key]

        N   = len(sim.Q_rungs)
        pos = float(row["position"])
        # Accept fractional positions (0–1) or integer rung indices
        if 0.0 <= pos <= 1.0 and not pos.is_integer():
            idx = int(round(pos * (N - 1)))
        else:
            idx = int(round(pos))
        pos_clamped = max(0, min(idx, N - 1))

        dP      = sim.P_oil - sim.P_water
        regimes = classify_rungs(
            dP,
            config.droplet_model.dP_cap_ow_Pa,
            config.droplet_model.dP_cap_wo_Pa,
        )
        regime = regimes[pos_clamped]

        if regime == RungRegime.ACTIVE and sim.Q_rungs[pos_clamped] > 0:
            f_pred = float(droplet_frequency(sim.Q_rungs[pos_clamped], D_pred_m))
        else:
            f_pred = 0.0

        D_pred_list.append(D_pred_um)
        f_pred_list.append(f_pred)
        regime_list.append(regime.name)

    result_df = exp_df.copy()
    result_df["D_pred_um"]        = D_pred_list
    result_df["f_pred_hz"]        = f_pred_list
    result_df["regime"]           = regime_list
    result_df["diam_residual_um"] = result_df["D_pred_um"] - result_df["droplet_diameter_um"]
    result_df["freq_residual_hz"] = result_df["f_pred_hz"] - result_df["frequency_hz"]
    return result_df


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CompareReport:
    """Residual statistics comparing model predictions to measurements."""

    n_points:     int
    diam_mae_um:  float   # mean absolute error, diameter [µm]
    diam_rmse_um: float   # root-mean-square error, diameter [µm]
    diam_bias_um: float   # mean signed error (pred − meas), diameter [µm]
    freq_mae_hz:  float   # mean absolute error, frequency [Hz]
    freq_rmse_hz: float   # root-mean-square error, frequency [Hz]
    freq_bias_hz: float   # mean signed error (pred − meas), frequency [Hz]


def compute_compare_report(compare_df: pd.DataFrame) -> CompareReport:
    """
    Compute residual statistics from a comparison DataFrame.

    Parameters
    ----------
    compare_df : DataFrame returned by ``compare_to_predictions``

    Returns
    -------
    CompareReport with MAE, RMSE, and bias for diameter and frequency.

    Raises
    ------
    ValueError : if required residual columns are absent
    """
    required = {"diam_residual_um", "freq_residual_hz"}
    missing  = required - set(compare_df.columns)
    if missing:
        raise ValueError(
            f"compare_df missing columns: {sorted(missing)}. "
            "Run compare_to_predictions first."
        )

    d_err = compare_df["diam_residual_um"].to_numpy(dtype=float)
    f_err = compare_df["freq_residual_hz"].to_numpy(dtype=float)
    n     = len(d_err)

    if n == 0:
        nan = float("nan")
        return CompareReport(
            n_points=0,
            diam_mae_um=nan, diam_rmse_um=nan, diam_bias_um=nan,
            freq_mae_hz=nan, freq_rmse_hz=nan, freq_bias_hz=nan,
        )

    return CompareReport(
        n_points=n,
        diam_mae_um=float(np.mean(np.abs(d_err))),
        diam_rmse_um=float(np.sqrt(np.mean(d_err ** 2))),
        diam_bias_um=float(np.mean(d_err)),
        freq_mae_hz=float(np.mean(np.abs(f_err))),
        freq_rmse_hz=float(np.sqrt(np.mean(f_err ** 2))),
        freq_bias_hz=float(np.mean(f_err)),
    )


# ---------------------------------------------------------------------------
# Calibration stub
# ---------------------------------------------------------------------------

def calibrate_droplet_model(
    config: "DeviceConfig",
    exp_df: pd.DataFrame,
) -> "DeviceConfig":
    """
    Calibration stub: scale ``droplet_model.k`` to minimise mean diameter error.

    The scale factor is ``mean(measured_diameter) / predicted_diameter``.
    All other config fields are unchanged.

    Parameters
    ----------
    config  : DeviceConfig
    exp_df  : DataFrame from ``load_experiments`` (must contain 'droplet_diameter_um')

    Returns
    -------
    DeviceConfig with adjusted ``droplet_model.k``.
    """
    from stepgen.models.droplets import droplet_diameter

    D_pred_um    = droplet_diameter(config) * 1e6
    D_meas_mean  = float(exp_df["droplet_diameter_um"].mean())

    if D_pred_um <= 0 or D_meas_mean <= 0:
        return config

    scale    = D_meas_mean / D_pred_um
    new_dm   = dataclasses.replace(config.droplet_model, k=config.droplet_model.k * scale)
    return dataclasses.replace(config, droplet_model=new_dm)
