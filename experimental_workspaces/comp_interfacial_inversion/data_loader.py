"""
data_loader.py — pooled experimental dataset for the interfacial inversion.
===========================================================================
There is ONE master dataset, not three: ``po_sweep/data/stage_timings.csv``
(device V5-8-1). The po / qw / conc "sweeps" are filtered views of it.

This module loads that master CSV, parses the SDS concentration out of the
``VideoFile`` string (it is NOT a column), restricts to the SDS / silicone-oil
system, tags each event's regime class (clean dripping interior vs held-out
out-of-regime), and computes the per-event reset volume ``V_reset`` used by the
Stage-1 refill inversion.

Concentration is carried in the ``ContPhase`` column (NOT a numeric field):
    0125pcSDS -> 0.125 %      025pcSDS -> 0.25 %      05pcSDS -> 0.5 %
    1pcSDS    -> 1.0 %        bare "SDS" -> 2.0 % (baseline)
    2-5NaCas  -> different surfactant  (EXCLUDED)

NOTE ON ABSOLUTE TIMES: this master CSV's stage times are a uniform 0.5x of the
values quoted in conc_sweep/analysis_notes.md (an FPS convention difference).
They are self-consistent here: the stages sum to the frequency reported in
po_sweep_droplet_summary.md (2% @ 200/5 -> ~1.24 Hz). The inversion below relies
only on Po-scaling SHAPE and cross-[SDS] RATIOS, both invariant to a global time
scale, so the fitted P_cap / gamma*cos(theta) are unaffected (a global factor is
absorbed by C_visc).

Clean dripping interior (used for calibration):  [SDS] >= 0.5 %  AND  200 <= Po <= 600 mbar.
Held-out (validation only):                       [SDS] == 0.125 %  (below CMC, different regime).
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

# ── Paths ───────────────────────────────────────────────────────────────────
HERE = Path(__file__).parent
PROJECT_ROOT = HERE.parents[1]                      # experimental_workspaces/.. = design_model
MASTER_CSV = PROJECT_ROOT / "experimental_workspaces" / "po_sweep" / "data" / "stage_timings.csv"

# ── Junction geometry (V5-8-1; matches configs/v5_30.yaml) ──────────────────
JUNCTION_W_UM = 30.0
JUNCTION_H_UM = 10.0
JUNCTION_AREA_UM2 = JUNCTION_W_UM * JUNCTION_H_UM   # exit cross-section

# ── Calibration-scope thresholds ────────────────────────────────────────────
CLEAN_SDS_MIN_PC = 0.5
CLEAN_PO_MIN_MBAR = 200.0
CLEAN_PO_MAX_MBAR = 600.0


_CONT_PHASE_TO_SDS_PC = {
    "SDS": 2.0,          # bare label = 2 % baseline
    "1pcSDS": 1.0,
    "05pcSDS": 0.5,
    "025pcSDS": 0.25,
    "0125pcSDS": 0.125,
}


def parse_sds_pc(cont_phase: str) -> float | None:
    """
    Map a ``ContPhase`` label to SDS mass %.

    Returns None for NaCas rows (different surfactant) or unrecognised labels.
    """
    if not isinstance(cont_phase, str):
        return None
    return _CONT_PHASE_TO_SDS_PC.get(cont_phase.strip())


def classify_regime(sds_pc: float, po_mbar: float) -> str:
    """Tag an event as 'clean' (calibration) or 'heldout' (validation)."""
    if sds_pc >= CLEAN_SDS_MIN_PC and CLEAN_PO_MIN_MBAR <= po_mbar <= CLEAN_PO_MAX_MBAR:
        return "clean"
    return "heldout"


def load_events(csv_path: Path | str = MASTER_CSV) -> pd.DataFrame:
    """
    Load and normalise the master event table for the SDS / silicone-oil system.

    Returns one row per formation event with tidy columns:
        sds_pc, Po_mbar, Qw_mlhr, S1_s, S2_s, S3_s, total_s,
        L_menpoint_um, L_men_um, D_um, V_reset_m3, regime_class
    NaCas rows and any row with a non-SDS/SO phase pair are dropped.
    """
    df = pd.read_csv(csv_path)

    # Restrict to silicone-oil dispersed phase; concentration is in ContPhase.
    df = df[df["DispPhase"] == "SO"].copy()

    df["sds_pc"] = df["ContPhase"].apply(parse_sds_pc)   # None for NaCas -> dropped
    df = df[df["sds_pc"].notna()].copy()

    out = pd.DataFrame({
        "sds_pc": df["sds_pc"].astype(float),
        "Po_mbar": df["DispPhasePressure"].astype(float),
        "Qw_mlhr": df["ContPhaseFlow"].astype(float),
        "S1_s": df["Stage1_s"].astype(float),
        "S2_s": df["Stage2_s"].astype(float),
        "S3_s": df["Stage3_s"].astype(float),
        "L_menpoint_um": df["L_menpoint_um"].astype(float),
        "L_men_um": df["L_men_um"].astype(float),
        "D_um": df["Droplet_diameter_um"].astype(float),
        "VideoFile": df["VideoFile"],
    })
    out["total_s"] = out["S1_s"] + out["S2_s"] + out["S3_s"]

    # Per-event reset volume: measured meniscus recession length x junction cross-section.
    # (This is the conc_sweep definition; it captures the concentration dependence of
    #  meniscus recession, unlike a fixed geometric V_reset.)
    out["V_reset_m3"] = (out["L_menpoint_um"] * JUNCTION_AREA_UM2) * 1e-18

    out["regime_class"] = [
        classify_regime(s, p) for s, p in zip(out["sds_pc"], out["Po_mbar"])
    ]

    return out.reset_index(drop=True)


def summarize_by_condition(df: pd.DataFrame) -> pd.DataFrame:
    """
    Group to (sds_pc, Po, Qw) means +/- SD +/- n. Used for the conc_sweep
    reproduction check and for the fits.
    """
    g = df.groupby(["sds_pc", "Po_mbar", "Qw_mlhr"])
    agg = g.agg(
        n=("S1_s", "count"),
        S1_mean=("S1_s", "mean"), S1_sd=("S1_s", "std"),
        S2_mean=("S2_s", "mean"), S2_sd=("S2_s", "std"),
        S3_mean=("S3_s", "mean"), S3_sd=("S3_s", "std"),
        Lmp_mean=("L_menpoint_um", "mean"),
        D_mean=("D_um", "mean"), D_sd=("D_um", "std"),
        V_reset_mean=("V_reset_m3", "mean"),
        regime_class=("regime_class", "first"),
    ).reset_index()
    return agg


if __name__ == "__main__":
    # Quick self-check + reproduction of key conc_sweep numbers.
    df = load_events()
    print(f"Loaded {len(df)} SDS/SO events "
          f"({(df.regime_class=='clean').sum()} clean, "
          f"{(df.regime_class=='heldout').sum()} held-out)")
    print("\n[SDS] levels present:", sorted(df.sds_pc.unique()))
    print("Po levels present:", sorted(df.Po_mbar.unique()))
    print("Qw levels present:", sorted(df.Qw_mlhr.unique()))

    print("\n--- Reproduce conc_sweep RATIOS (Po=200, Qw=5): S1/S2 ratio vs 2% baseline ---")
    print("    (conc_sweep S1 ratios: 2%=1.00 1%=1.05 0.5%=1.22 0.25%=1.33 0.125%=1.87)")
    sub = summarize_by_condition(df)
    sel = sub[(sub.Po_mbar == 200) & (sub.Qw_mlhr == 5)].sort_values("sds_pc", ascending=False)
    base_s1 = sel[sel.sds_pc == 2.0]["S1_mean"].iloc[0]
    base_s2 = sel[sel.sds_pc == 2.0]["S2_mean"].iloc[0]
    sel = sel.assign(S1_ratio=sel.S1_mean / base_s1, S2_ratio=sel.S2_mean / base_s2)
    print(sel[["sds_pc", "n", "S1_mean", "S1_ratio", "S2_mean", "S2_ratio", "Lmp_mean", "D_mean"]]
          .to_string(index=False, float_format="%.3f"))
