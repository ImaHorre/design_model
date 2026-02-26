"""
compare_models.py
=================
Side-by-side comparison: stepgen_seed (legacy) vs stepgen (new model)
for the same device geometry at MATCHED operating conditions.

Matching strategy
-----------------
Both models are run at the same physical flows (Q_oil, Q_water).
The seed accepts flows natively and returns the resulting pressures.
The new model is then given Po_in = seed's P_oil[-1] (the oil inlet
pressure that the seed predicts for those flows) and Qw_in = Q_water.
This way both models are solving for the same physical operating point.

Usage
-----
    # Uses defaults defined in this file:
    .venv/Scripts/python compare_models.py

    # Reads geometry from a YAML config; operating flows from FLOWS block below:
    .venv/Scripts/python compare_models.py examples/device_template.yaml
"""

from __future__ import annotations

import sys
import numpy as np


# =============================================================================
# USER-EDITABLE SECTION
# =============================================================================

# --- Geometry defaults (used when no YAML is passed) -------------------------
DEFAULT_GEOM = dict(
    Mcl=0.693,          # main channel routed length  [m]
    Mcd=200e-6,           # main channel depth           [m]
    Mcw=1000e-6,           # main channel width           [m]
    mcd=10e-6,           # rung depth                   [m]
    mcw=8e-6,           # rung width                   [m]
    mcl=4000e-6,           # rung length                  [m]
    pitch=60e-6,         # rung pitch                   [m]
    constriction_ratio=0.9,
)

DEFAULT_JUNCTION = dict(
    exit_width=30e-6,   # junction exit width [m]  (droplet size model input)
    exit_depth=10e-6,   # junction exit depth [m]
)

# --- Operating flows ---------------------------------------------------------
# These are the SHARED inputs to both models.
# Q_oil_mlhr   — volumetric oil   flow into the oil main channel  [mL/hr]
# Q_water_mlhr — volumetric water flow into the water main channel [mL/hr]
#
# The seed runs directly with these flows.
# The new model uses Po_in = oil inlet pressure returned by the seed (P_oil[-1] after reversal),
# and Qw_in = Q_water_mlhr.
#
# Tip: if you know your device's target droplet freq f [Hz], rung radius r [m],
# and Nmc rungs:  Q_oil_mlhr = f * (4/3*pi*r^3) * Nmc * 3.6e9
FLOWS = dict(
    Q_oil_mlhr=1.7,       # oil   main-channel inlet flow [mL/hr]
    Q_water_mlhr=15.3,     # water main-channel inlet flow [mL/hr]
)

# --- New model capillary thresholds ------------------------------------------
THRESHOLDS = dict(
    dP_cap_ow_mbar=50.0,   # oil-to-water capillary pressure [mbar]
    dP_cap_wo_mbar=30.0,   # water-to-oil capillary pressure [mbar]
)

# =============================================================================
# END OF USER-EDITABLE SECTION
# =============================================================================

_m3s_per_mlhr = 1.0 / 3.6e9   # 1 mL/hr in m³/s


# -----------------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------------

def _hr(label: str = "") -> None:
    w = 62
    if label:
        side = (w - len(label) - 2) // 2
        print("-" * side + f" {label} " + "-" * (w - side - len(label) - 2))
    else:
        print("-" * w)


def _row(label: str, *values: str) -> None:
    print(f"  {label:<30}", "  ".join(str(v) for v in values))


def _fmt_mbar(Pa: float) -> str:
    return f"{Pa / 100.0:>14.3f} mbar"


def _fmt_mlhr(m3s: float) -> str:
    return f"{m3s / _m3s_per_mlhr:>14.4f} mL/hr"


def _fmt_nlmin(m3s: float) -> str:
    return f"{m3s * 60.0e12:>14.4f} nL/min"


def _fmt_um(m: float) -> str:
    return f"{m * 1e6:>14.4f} um"


# -----------------------------------------------------------------------------
# SEED MODEL
# -----------------------------------------------------------------------------

def run_seed(geom_d: dict, Q_oil_m3s: float, Q_water_m3s: float) -> dict:
    """
    Run the legacy seed model with explicit Q_oil and Q_water inputs.
    Returns a flat dict of pressures, flows and derived metrics.
    """
    from stepgen_seed.resistance import (
        Geometry, Fluids, ModelParams,
        hydraulic_resistance_rectangular,
    )
    from stepgen_seed.hydraulics import solve_linear, summarize_solution

    g = geom_d
    Nmc = int(g["Mcl"] / g["pitch"])
    if Nmc < 2:
        raise ValueError(f"Nmc={Nmc} is too small.")

    fluids = Fluids(mu_water=0.00089, mu_oil=0.03452)

    constriction_l = g["mcl"] * g["constriction_ratio"]
    R_Omc = hydraulic_resistance_rectangular(
        fluids.mu_oil, constriction_l, g["mcw"], g["mcd"], correction=True
    )
    R_OMc = hydraulic_resistance_rectangular(
        fluids.mu_oil, g["pitch"], g["Mcw"], g["Mcd"], correction=True
    )
    R_WMc = hydraulic_resistance_rectangular(
        fluids.mu_water, g["pitch"], g["Mcw"], g["Mcd"], correction=True
    )

    params = ModelParams(
        Nmc=Nmc,
        R_OMc=R_OMc,
        R_WMc=R_WMc,
        R_Omc=R_Omc,
        Q_O=Q_oil_m3s,
        Q_W=Q_water_m3s,
    )

    sol = solve_linear(params, pitch=g["pitch"])
    s   = summarize_solution(sol, Mcw=g["Mcw"])

    dP = sol.P_oil - sol.P_water
    # After solve_linear()'s [::-1] reversal: index -1 = true inlet (high P),
    # index 0 = true dead-end (low P).  Map to physical convention shared with
    # the new model so all table labels are meaningful.
    return dict(
        Nmc=Nmc,
        P_oil_in_Pa=float(sol.P_oil[-1]),    # true inlet (high P)
        P_oil_end_Pa=float(sol.P_oil[0]),    # true dead-end (low P)
        P_water_in_Pa=float(sol.P_water[-1]),  # water inlet (high P)
        P_water_out_Pa=float(sol.P_water[0]),  # water outlet (~0)
        Q_oil_in_m3s=Q_oil_m3s,
        Q_water_in_m3s=Q_water_m3s,
        Q_rung_avg_m3s=float(np.mean(sol.Q_rungs)),
        Q_rung_min_m3s=float(np.min(sol.Q_rungs)),
        Q_rung_max_m3s=float(np.max(sol.Q_rungs)),
        flow_diff_pct=float(s["flow_difference_pct"]),
        delam_line_load_Nm=float(sol.P_oil[-1] * g["Mcw"]),  # inlet (max) pressure
        dP_rung_first_Pa=float(dP[-1]),   # at inlet end
        dP_rung_last_Pa=float(dP[0]),     # at dead-end
        R_Omc=R_Omc,
        R_OMc=R_OMc,
        R_WMc=R_WMc,
    )


# -----------------------------------------------------------------------------
# NEW MODEL
# -----------------------------------------------------------------------------

def _build_config(geom_d: dict, junc_d: dict, Po_mbar: float, Qw_mlhr: float, thresh: dict):
    from stepgen.config import (
        DeviceConfig, FluidConfig, GeometryConfig,
        MainChannelConfig, RungConfig, JunctionConfig,
        OperatingConfig, FootprintConfig, ManufacturingConfig,
        DropletModelConfig,
    )
    g = geom_d
    return DeviceConfig(
        fluids=FluidConfig(
            mu_continuous=0.00089, mu_dispersed=0.03452,
            emulsion_ratio=0.3, gamma=0.0, temperature_C=25.0,
        ),
        geometry=GeometryConfig(
            main=MainChannelConfig(Mcd=g["Mcd"], Mcw=g["Mcw"], Mcl=g["Mcl"]),
            rung=RungConfig(
                mcd=g["mcd"], mcw=g["mcw"], mcl=g["mcl"],
                pitch=g["pitch"], constriction_ratio=g["constriction_ratio"],
            ),
            junction=JunctionConfig(
                exit_width=junc_d["exit_width"],
                exit_depth=junc_d["exit_depth"],
                junction_type="step",
            ),
        ),
        operating=OperatingConfig(
            mode="A", Po_in_mbar=Po_mbar, Qw_in_mlhr=Qw_mlhr, P_out_mbar=0.0,
        ),
        footprint=FootprintConfig(
            footprint_area_cm2=10.0, footprint_aspect_ratio=1.5,
            lane_spacing=500e-6, turn_radius=500e-6, reserve_border=2e-3,
        ),
        manufacturing=ManufacturingConfig(
            max_main_depth=200e-6, min_feature_width=0.5e-6, max_main_width=1000e-6,
        ),
        droplet_model=DropletModelConfig(
            k=3.3935, a=0.3390, b=0.7198,
            dP_cap_ow_mbar=thresh["dP_cap_ow_mbar"],
            dP_cap_wo_mbar=thresh["dP_cap_wo_mbar"],
        ),
    )


def _extract_metrics(config, result) -> dict:
    from stepgen.models.metrics import compute_metrics
    m = compute_metrics(config, result)
    dP = result.P_oil - result.P_water
    return dict(
        Nmc=result.P_oil.shape[0],
        P_oil_in_Pa=float(result.P_oil[0]),
        P_oil_end_Pa=float(result.P_oil[-1]),
        P_water_in_Pa=float(result.P_water[0]),
        P_water_out_Pa=float(result.P_water[-1]),
        Q_oil_total_m3s=float(result.Q_oil_total),
        Q_water_total_m3s=float(result.Q_water_total),
        Q_rung_avg_m3s=float(np.mean(result.Q_rungs)),
        Q_rung_min_m3s=float(np.min(result.Q_rungs)),
        Q_rung_max_m3s=float(np.max(result.Q_rungs)),
        dP_rung_first_Pa=float(dP[0]),
        dP_rung_last_Pa=float(dP[-1]),
        Q_uniformity_pct=float(m.Q_uniformity_pct),
        dP_uniformity_pct=float(m.dP_uniformity_pct),
        P_peak_Pa=float(m.P_peak),
        active_fraction=float(m.active_fraction),
        reverse_fraction=float(m.reverse_fraction),
        off_fraction=float(m.off_fraction),
        delam_line_load_Nm=float(m.delam_line_load),
        D_pred_m=float(m.D_pred),
        f_pred_mean_Hz=float(m.f_pred_mean),
        collapse_index=float(m.collapse_index),
    )


def run_new_linear(config) -> dict:
    from stepgen.models.hydraulics import simulate
    result = simulate(config)
    return _extract_metrics(config, result)


def run_new_iterative(config) -> dict:
    from stepgen.models.generator import iterative_solve
    result = iterative_solve(config)
    return _extract_metrics(config, result)


# -----------------------------------------------------------------------------
# REPORT
# -----------------------------------------------------------------------------

def print_report(
    geom_d: dict, junc_d: dict,
    seed: dict, lin: dict, itr: dict,
    Q_oil_mlhr: float, Q_water_mlhr: float,
    Po_matched_mbar: float,
) -> None:

    def row3(label, sv, lv, iv):
        print(f"  {label:<32}  {sv:>16}  {lv:>16}  {iv:>16}")

    def row2(label, lv, iv):
        print(f"  {label:<32}  {'N/A (seed)':>16}  {lv:>16}  {iv:>16}")

    def hdr3():
        print(f"  {'Quantity':<32}  {'SEED':>16}  {'NEW linear':>16}  {'NEW iterative':>16}")
        print(f"  {'':-<32}  {'':->16}  {'':->16}  {'':->16}")

    def hdr2():
        print(f"  {'Quantity':<32}  {'NEW linear':>16}  {'NEW iterative':>16}")
        print(f"  {'':-<32}  {'':->16}  {'':->16}")

    print()
    _hr("GEOMETRY")
    _row("Mcl",          f"{geom_d['Mcl']*1e3:.1f} mm")
    _row("Mcd",          f"{geom_d['Mcd']*1e6:.2f} um  (main channel depth)")
    _row("Mcw",          f"{geom_d['Mcw']*1e6:.2f} um  (main channel width)")
    _row("mcd",          f"{geom_d['mcd']*1e6:.4f} um  (rung depth)")
    _row("mcw",          f"{geom_d['mcw']*1e6:.4f} um  (rung width)")
    _row("mcl",          f"{geom_d['mcl']*1e6:.1f} um  (rung length)")
    _row("pitch",        f"{geom_d['pitch']*1e6:.4f} um")
    _row("exit_width",   f"{junc_d['exit_width']*1e6:.4f} um  (droplet size model)")
    _row("exit_depth",   f"{junc_d['exit_depth']*1e6:.4f} um  (droplet size model)")
    _row("Nmc",          str(seed["Nmc"]))

    print()
    _hr("MATCHED OPERATING CONDITIONS")
    _row("Q_oil_in (both models)",
         f"{Q_oil_mlhr:.6f} mL/hr  ->  {Q_oil_mlhr * _m3s_per_mlhr:.4e} m3/s")
    _row("Q_water_in (both models)",
         f"{Q_water_mlhr:.6f} mL/hr  ->  {Q_water_mlhr * _m3s_per_mlhr:.4e} m3/s")
    _row("Po_in for new model",
         f"{Po_matched_mbar:.3f} mbar  (= seed P_oil[-1], oil inlet)")
    print()
    print("  NOTE: Seed uses Q_oil + Q_water as BCs (flow-controlled, both channels).")
    print("        New model uses Po_in (matched from seed oil inlet pressure) + Qw_in (water flow).")
    print("        This is the fairest possible comparison given the two solver architectures.")

    print()
    _hr("CHANNEL RESISTANCES  (Pa.s/m3)")
    _row("R_rung   (oil through rung)", f"{seed['R_Omc']:.4e}")
    _row("R_OMc_seg (oil main channel per pitch)",   f"{seed['R_OMc']:.4e}")
    _row("R_WMc_seg (water main channel per pitch)", f"{seed['R_WMc']:.4e}")
    print()
    print("  Rung resistance >> main channel resistance: this means the pressure drop")
    print("  occurs mostly across the rungs, not along the main channels.")
    print(f"  R_rung / R_OMc_seg = {seed['R_Omc'] / seed['R_OMc']:.1f}x")

    print()
    _hr("OIL MAIN CHANNEL PRESSURES")
    print("  (These reveal the key physics difference between the two models.)")
    hdr3()
    row3("P_oil[0]  (inlet, near water inlet)",
         _fmt_mbar(seed["P_oil_in_Pa"]),
         _fmt_mbar(lin["P_oil_in_Pa"]),
         _fmt_mbar(itr["P_oil_in_Pa"]))
    row3("P_oil[-1] (far end of oil rail)",
         _fmt_mbar(seed["P_oil_end_Pa"]),
         _fmt_mbar(lin["P_oil_end_Pa"]),
         _fmt_mbar(itr["P_oil_end_Pa"]))
    row3("P_oil spread (end - inlet)",
         _fmt_mbar(seed["P_oil_end_Pa"] - seed["P_oil_in_Pa"]),
         _fmt_mbar(lin["P_oil_end_Pa"] - lin["P_oil_in_Pa"]),
         _fmt_mbar(itr["P_oil_end_Pa"] - itr["P_oil_in_Pa"]))
    print()
    print("  NOTE: pressure arrays are shown inlet->dead-end for all three models.")

    print()
    _hr("WATER MAIN CHANNEL PRESSURES")
    hdr3()
    row3("P_water[0]  (near water inlet)",
         _fmt_mbar(seed["P_water_in_Pa"]),
         _fmt_mbar(lin["P_water_in_Pa"]),
         _fmt_mbar(itr["P_water_in_Pa"]))
    row3("P_water[-1] (outlet, reference=0)",
         _fmt_mbar(seed["P_water_out_Pa"]),
         _fmt_mbar(lin["P_water_out_Pa"]),
         _fmt_mbar(itr["P_water_out_Pa"]))

    print()
    _hr("RUNG DELTA-P  (P_oil - P_water at junction)")
    print("  Positive dP -> oil side higher -> oil can form droplets  (ACTIVE regime)")
    print("  Negative dP -> water side higher -> interface pushed back (REVERSE regime)")
    hdr3()
    row3("dP_rung[0]  (near water inlet)",
         _fmt_mbar(seed["dP_rung_first_Pa"]),
         _fmt_mbar(lin["dP_rung_first_Pa"]),
         _fmt_mbar(itr["dP_rung_first_Pa"]))
    row3("dP_rung[-1] (far end of device)",
         _fmt_mbar(seed["dP_rung_last_Pa"]),
         _fmt_mbar(lin["dP_rung_last_Pa"]),
         _fmt_mbar(itr["dP_rung_last_Pa"]))

    print()
    _hr("OIL AND WATER FLOWS")
    hdr3()
    row3("Q_oil total (main channel in)",
         _fmt_mlhr(seed["Q_oil_in_m3s"]),
         _fmt_mlhr(lin["Q_oil_total_m3s"]),
         _fmt_mlhr(itr["Q_oil_total_m3s"]))
    row3("Q_water total (main channel in)",
         _fmt_mlhr(seed["Q_water_in_m3s"]),
         _fmt_mlhr(lin["Q_water_total_m3s"]),
         _fmt_mlhr(itr["Q_water_total_m3s"]))

    print()
    _hr("RUNG FLOW DISTRIBUTION")
    hdr3()
    row3("Q_rung avg",
         _fmt_nlmin(seed["Q_rung_avg_m3s"]),
         _fmt_nlmin(lin["Q_rung_avg_m3s"]),
         _fmt_nlmin(itr["Q_rung_avg_m3s"]))
    row3("Q_rung min",
         _fmt_nlmin(seed["Q_rung_min_m3s"]),
         _fmt_nlmin(lin["Q_rung_min_m3s"]),
         _fmt_nlmin(itr["Q_rung_min_m3s"]))
    row3("Q_rung max",
         _fmt_nlmin(seed["Q_rung_max_m3s"]),
         _fmt_nlmin(lin["Q_rung_max_m3s"]),
         _fmt_nlmin(itr["Q_rung_max_m3s"]))
    seed_q_unif = (
        (seed["Q_rung_max_m3s"] - seed["Q_rung_min_m3s"]) / seed["Q_rung_avg_m3s"] * 100.0
        if seed["Q_rung_avg_m3s"] > 0 else float("nan")
    )
    row3("Q uniformity (max-min)/avg %",
         f"{seed_q_unif:>13.3f} %",
         f"{lin['Q_uniformity_pct']:>13.3f} %",
         f"{itr['Q_uniformity_pct']:>13.3f} %")
    row3("dP uniformity (max-min)/avg %",
         "      N/A (seed)",
         f"{lin['dP_uniformity_pct']:>13.3f} %",
         f"{itr['dP_uniformity_pct']:>13.3f} %")

    print()
    _hr("MECHANICAL RISK")
    hdr3()
    row3("Delam line load  P_peak * Mcw [N/m]",
         f"{seed['delam_line_load_Nm']:>13.4f} N/m",
         f"{lin['delam_line_load_Nm']:>13.4f} N/m",
         f"{itr['delam_line_load_Nm']:>13.4f} N/m")
    print(f"  {'Collapse index  Mcw/Mcd':<32}",
          f"{'N/A (seed)':>16}",
          f"{lin['collapse_index']:>15.2f}",
          f"{itr['collapse_index']:>15.2f}")

    print()
    _hr("REGIME CLASSIFICATION  (new model only)")
    print("  (Seed has no regime model — it is purely linear, all rungs treated equally.)")
    hdr2()
    for label, lk, ik in [
        ("Active rungs  (oil -> water, droplets)", "active_fraction",  "active_fraction"),
        ("Reverse rungs (water > oil at junction)", "reverse_fraction", "reverse_fraction"),
        ("Off rungs     (pinned by capillary)",     "off_fraction",     "off_fraction"),
    ]:
        print(f"  {label:<32}  {lin[lk]*100:>14.1f} %  {itr[ik]*100:>14.1f} %")

    print()
    _hr("DROPLET SIZE MODEL  (new model only)")
    print("  (Seed used a fixed droplet radius input; new model predicts from geometry.)")
    hdr2()
    print(f"  {'D_pred  [k * exit_w^a * exit_d^b]':<32}  {_fmt_um(lin['D_pred_m']):>16}  {_fmt_um(itr['D_pred_m']):>16}")
    print(f"  {'f_pred_mean over active rungs':<32}  {lin['f_pred_mean_Hz']:>14.3f} Hz  {itr['f_pred_mean_Hz']:>14.3f} Hz")

    print()
    _hr("SUMMARY")
    seed_q_unif2 = (
        (seed["Q_rung_max_m3s"] - seed["Q_rung_min_m3s"]) / seed["Q_rung_avg_m3s"] * 100.0
        if seed["Q_rung_avg_m3s"] > 0 else float("nan")
    )
    q_unif_diff = abs(seed_q_unif2 - lin["Q_uniformity_pct"])
    print(f"  Q uniformity: seed={seed_q_unif2:.3f}%  new_linear={lin['Q_uniformity_pct']:.3f}%"
          f"  |diff|={q_unif_diff:.3f}%")

    reverse_any = lin["reverse_fraction"] > 0 or itr["reverse_fraction"] > 0
    off_any     = lin["off_fraction"]     > 0 or itr["off_fraction"]     > 0
    if reverse_any or off_any:
        print(f"  Reverse rungs: linear={lin['reverse_fraction']*100:.1f}%  "
              f"iterative={itr['reverse_fraction']*100:.1f}%")
        print(f"  Off rungs:     linear={lin['off_fraction']*100:.1f}%  "
              f"iterative={itr['off_fraction']*100:.1f}%")
    else:
        print("  All rungs active (no reverse or off rungs at this operating point).")

    q_oil_lin = lin["Q_oil_total_m3s"] / _m3s_per_mlhr
    q_oil_itr = itr["Q_oil_total_m3s"] / _m3s_per_mlhr
    if q_oil_lin > 0:
        q_oil_discrepancy_pct = abs(q_oil_itr - q_oil_lin) / q_oil_lin * 100.0
        if q_oil_discrepancy_pct > 1.0:
            print(f"  Q_oil linear={q_oil_lin:.4f} mL/hr  iterative={q_oil_itr:.4f} mL/hr"
                  f"  discrepancy={q_oil_discrepancy_pct:.1f}%"
                  f"  (capillary thresholds alter effective conductance)")

    peak_delam = max(seed["delam_line_load_Nm"], lin["delam_line_load_Nm"], itr["delam_line_load_Nm"])
    print(f"  Peak delamination load: {peak_delam:.4f} N/m"
          f"  (= P_peak_inlet * Mcw)")
    _hr()


# -----------------------------------------------------------------------------
# ENTRY POINT
# -----------------------------------------------------------------------------

def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    yaml_path = sys.argv[1] if len(sys.argv) > 1 else None

    if yaml_path:
        from stepgen.config import load_config
        cfg = load_config(yaml_path)
        geom_d = dict(
            Mcl=cfg.geometry.main.Mcl,
            Mcd=cfg.geometry.main.Mcd,
            Mcw=cfg.geometry.main.Mcw,
            mcd=cfg.geometry.rung.mcd,
            mcw=cfg.geometry.rung.mcw,
            mcl=cfg.geometry.rung.mcl,
            pitch=cfg.geometry.rung.pitch,
            constriction_ratio=cfg.geometry.rung.constriction_ratio,
        )
        junc_d = dict(
            exit_width=cfg.geometry.junction.exit_width,
            exit_depth=cfg.geometry.junction.exit_depth,
        )
        thresh = dict(
            dP_cap_ow_mbar=cfg.droplet_model.dP_cap_ow_mbar,
            dP_cap_wo_mbar=cfg.droplet_model.dP_cap_wo_mbar,
        )
    else:
        geom_d = DEFAULT_GEOM
        junc_d = DEFAULT_JUNCTION
        thresh  = THRESHOLDS

    Q_oil_mlhr   = FLOWS["Q_oil_mlhr"]
    Q_water_mlhr = FLOWS["Q_water_mlhr"]
    Q_oil_m3s    = Q_oil_mlhr   * _m3s_per_mlhr
    Q_water_m3s  = Q_water_mlhr * _m3s_per_mlhr

    print()
    print("=" * 64)
    print("  MODEL COMPARISON -- stepgen_seed (legacy) vs stepgen (new)")
    print("=" * 64)

    Nmc_est = int(geom_d["Mcl"] / geom_d["pitch"])
    if Nmc_est > 5_000:
        print(f"\n  [!] Large Nmc ~ {Nmc_est:,} -- solvers may take several seconds.")
        print("      To test faster: reduce Mcl or increase pitch.\n")

    # ── Step 1: run seed to get pressures at these flows ──────────────────────
    print("  Step 1/3  Running seed model ...", end=" ", flush=True)
    seed = run_seed(geom_d, Q_oil_m3s, Q_water_m3s)
    print(f"done  (Nmc={seed['Nmc']:,})")

    # ── Step 2: derive matched Po_in from seed oil inlet pressure ────────────
    Po_matched_mbar = seed["P_oil_in_Pa"] / 100.0
    print(f"  Step 2/3  Matched Po_in = {Po_matched_mbar:.3f} mbar  (seed oil inlet pressure)")

    # ── Step 3: build new model config and run both solve modes ───────────────
    config = _build_config(geom_d, junc_d, Po_matched_mbar, Q_water_mlhr, thresh)

    print("  Step 3a/3 Running new model (linear)    ...", end=" ", flush=True)
    lin = run_new_linear(config)
    print("done")

    print("  Step 3b/3 Running new model (iterative) ...", end=" ", flush=True)
    itr = run_new_iterative(config)
    print("done")

    print_report(geom_d, junc_d, seed, lin, itr, Q_oil_mlhr, Q_water_mlhr, Po_matched_mbar)


if __name__ == "__main__":
    main()
