"""
stepgen.cli
===========
Command-line interface for StepGen Designer v1.

Commands
--------
    stepgen simulate <config.yaml>  [--Po P] [--Qw Q] [--Qo Q] [--out results.json]
    stepgen sweep    <cfg1> [cfg2 …] [--Po P] [--Qw Q] [--Qo Q] [--out sweep.csv]
    stepgen report   <config.yaml>  [--Po P] [--Qw Q] [--out-dir DIR]
    stepgen map      <config.yaml>  [--Po-min …] [--Po-max …] [--Po-n …]
                                    [--Qw-min …] [--Qw-max …] [--Qw-n …]
                                    [--out-dir DIR]
    stepgen design   <design_search.yaml>  [--out design_results.csv]
    stepgen compare  <config.yaml>  <experiments.csv>
                                    [--out compare.csv] [--calibrate]
    stepgen study    <study.yaml>   [--book DIR] [--diagnose auto|always|never]
                                    [--production-threshold] [--extends PARENT.json]
    stepgen studio-ui [study.yaml]  [--port N]   (interactive Design Studio; needs .[ui])

Experimental Testing Commands
-----------------------------
    stepgen test-experimental <config.yaml> <experiments.csv> [--output-dir test_results]
    stepgen test-duty-factor  <config.yaml> <experiments.csv> [--output-dir DIR]
    stepgen test-time-state   <config.yaml> <experiments.csv> [--output-dir DIR] [--params PARAM_LIST]
    stepgen verify-pcap       <config.yaml> [--test-conditions experiments.csv] [--output-dir DIR]

Entry point (pyproject.toml):
    stepgen = "stepgen.cli:main"
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def _cmd_simulate(args: argparse.Namespace) -> int:
    from stepgen.config import load_config
    from stepgen.design.sweep import evaluate_candidate

    config = load_config(args.config)

    # Apply CLI parameter overrides for time-state models
    if hasattr(args, 'dt') and args.dt is not None:
        config.droplet_model.__dict__['dt_ms'] = args.dt
        print(f"  Override: dt = {args.dt} ms")

    if hasattr(args, 't_end') and getattr(args, 't_end', None) is not None:
        config.droplet_model.__dict__['simulation_time_ms'] = args.t_end
        print(f"  Override: t_end = {args.t_end} ms")

    if hasattr(args, 'tau_pinch') and getattr(args, 'tau_pinch', None) is not None:
        config.droplet_model.__dict__['tau_pinch_ms'] = args.tau_pinch
        print(f"  Override: tau_pinch = {args.tau_pinch} ms")

    if hasattr(args, 'tau_reset') and getattr(args, 'tau_reset', None) is not None:
        config.droplet_model.__dict__['tau_reset_ms'] = args.tau_reset
        print(f"  Override: tau_reset = {args.tau_reset} ms")

    if hasattr(args, 'g_pinch_frac') and getattr(args, 'g_pinch_frac', None) is not None:
        config.droplet_model.__dict__['g_pinch_frac'] = args.g_pinch_frac
        print(f"  Override: g_pinch_frac = {args.g_pinch_frac}")

    # Apply CLI parameter overrides for refill volume
    if hasattr(args, 'enable_refill') and args.enable_refill:
        config.droplet_model.__dict__['enable_refill_volume'] = True
        print("  Override: enable_refill_volume = True")

    if hasattr(args, 'disable_refill') and args.disable_refill:
        config.droplet_model.__dict__['enable_refill_volume'] = False
        print("  Override: enable_refill_volume = False")

    if hasattr(args, 'refill_factor') and args.refill_factor is not None:
        config.droplet_model.__dict__['refill_length_factor'] = args.refill_factor
        print(f"  Override: refill_length_factor = {args.refill_factor}")

    Qo = getattr(args, "Qo", None)
    row = evaluate_candidate(
        config,
        Po_in_mbar=args.Po,
        Qw_in_mlhr=args.Qw,
        Qo_in_mlhr=Qo,
        model_type=args.model,
    )

    disp_lbl, cont_lbl = config.fluids.channel_labels
    print("=== simulate ===")
    print(f"  Config  : {args.config}")
    print(f"  System  : {config.fluids.phase_system}  (dispersed={disp_lbl}, continuous={cont_lbl})")
    if "derived_Po_in_mbar" in row:
        print(f"  Mode    : B (flow-flow)")
        print(f"  Q_disp  : {row['Qo_in_mlhr']:.3f} mL/hr [{disp_lbl}] (requested)")
        print(f"  P_disp  : {row['derived_Po_in_mbar']:.1f} mbar [{disp_lbl}] (derived)")
    else:
        print(f"  Mode    : A (pressure-flow)")
        print(f"  P_disp  : {row['Po_in_mbar']:.1f} mbar  [{disp_lbl} inlet pressure]")
    print(f"  Q_cont  : {row['Qw_in_mlhr']:.2f} mL/hr  [{cont_lbl} inlet flow]")
    q_oil_total    = row['Q_oil_total']
    q_oil_droplets = row['Q_oil_droplets']
    q_water = row['Q_water_total']
    emulsion_ratio = q_oil_droplets / (q_oil_droplets + q_water) if (q_oil_droplets + q_water) > 0 else 0.0
    print(f"  Q_disp_total : {q_oil_total*3.6e12:.1f} µL/hr (hydraulic dispersed flow)")
    print(f"  Q_disp_drops : {q_oil_droplets*3.6e12:.1f} µL/hr (effective droplet production)")
    print(f"  emulsion     : {emulsion_ratio:.3f}  ({emulsion_ratio*100:.1f}% {disp_lbl} by volume)")
    print(f"  Nmc     : {row['Nmc']}")
    print(f"  active  : {row['active_fraction']*100:.1f} %")
    print(f"  reverse : {row['reverse_fraction']*100:.1f} %")
    print(f"  Q_spread: {row['Q_spread_pct']:.2f} %  (mean {row['Q_per_rung_avg']*1e9*3600:.1f} nL/hr per rung)")
    print(f"  dP_spread: {row['dP_spread_pct']:.2f} %  (mean {row['dP_avg']*1e-2:.1f} mbar per rung)")
    print(f"  D_pred  : {row['D_pred']*1e6:.3f} µm")
    print(f"  f_mean  : {row['f_pred_mean']:.2f} Hz  (min {row['f_pred_min']:.2f}  max {row['f_pred_max']:.2f})")
    print(f"  fits    : {row['fits_footprint']}")
    if row['passes_hard_constraints']:
        print(f"  hard OK : True")
    else:
        failures = row.get('hard_constraint_failures', '')
        print(f"  hard OK : False")
        for msg in failures.split('; '):
            if msg:
                print(f"    ✗ {msg}")

    if args.out:
        from stepgen.models.generator import iterative_solve
        from stepgen.models.metrics import compute_metrics
        from stepgen.design.layout import compute_layout
        from stepgen.io.results import export_candidate_json

        Po = row["Po_in_mbar"]
        Qw = row["Qw_in_mlhr"]
        result  = iterative_solve(config, Po_in_mbar=Po, Qw_in_mlhr=Qw)
        metrics = compute_metrics(config, result)
        layout  = compute_layout(config)
        export_candidate_json(config, metrics, layout, args.out)
        print(f"  → saved {args.out}")

    return 0


def _cmd_sweep(args: argparse.Namespace) -> int:
    from stepgen.config import load_config
    from stepgen.design.sweep import sweep
    from stepgen.io.results import save_results

    Qo = getattr(args, "Qo", None)
    configs = [load_config(p) for p in args.configs]

    # Apply CLI parameter overrides for time-state models
    for config in configs:
        if hasattr(args, 'dt') and args.dt is not None:
            config.droplet_model.__dict__['dt_ms'] = args.dt

        if hasattr(args, 't_end') and getattr(args, 't_end', None) is not None:
            config.droplet_model.__dict__['simulation_time_ms'] = args.t_end

        if hasattr(args, 'tau_pinch') and getattr(args, 'tau_pinch', None) is not None:
            config.droplet_model.__dict__['tau_pinch_ms'] = args.tau_pinch

        if hasattr(args, 'tau_reset') and getattr(args, 'tau_reset', None) is not None:
            config.droplet_model.__dict__['tau_reset_ms'] = args.tau_reset

        if hasattr(args, 'g_pinch_frac') and getattr(args, 'g_pinch_frac', None) is not None:
            config.droplet_model.__dict__['g_pinch_frac'] = args.g_pinch_frac

        # Apply CLI parameter overrides for refill volume
        if hasattr(args, 'enable_refill') and args.enable_refill:
            config.droplet_model.__dict__['enable_refill_volume'] = True

        if hasattr(args, 'disable_refill') and args.disable_refill:
            config.droplet_model.__dict__['enable_refill_volume'] = False

        if hasattr(args, 'refill_factor') and args.refill_factor is not None:
            config.droplet_model.__dict__['refill_length_factor'] = args.refill_factor
    df      = sweep(configs, Po_in_mbar=args.Po, Qw_in_mlhr=args.Qw, Qo_in_mlhr=Qo, model_type=args.model)

    out = args.out
    save_results(df, out)
    print(f"=== sweep ===")
    print(f"  Candidates : {len(df)}")
    passed = int(df["passes_hard_constraints"].sum()) if "passes_hard_constraints" in df else "n/a"
    print(f"  Hard-pass  : {passed}")
    print(f"  → saved {out}")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    import matplotlib
    matplotlib.use("Agg")

    from stepgen.config import load_config
    from stepgen.design.layout import compute_layout
    from stepgen.models.generator import iterative_solve
    from stepgen.viz.plots import plot_layout_schematic, plot_pressure_sweep

    config  = load_config(args.config)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=== report ===")
    print(f"  Config : {args.config}")
    print(f"  System : {config.fluids.phase_system}  {config.fluids.channel_labels}")

    # ── Determine sweep values ────────────────────────────────────────────────
    # Priority: CLI flags > YAML operating_map.Po_values/Qw_values > single point
    cli_Po = args.Po  # list[float] | None
    cli_Qw = args.Qw  # list[float] | None

    om = config.operating_map
    yaml_Po = list(om.Po_values) if om.Po_values else None
    yaml_Qw = list(om.Qw_values) if om.Qw_values else None

    Po_vals = cli_Po or yaml_Po
    Qw_vals = cli_Qw or yaml_Qw

    sweep_mode = (Po_vals is not None and len(Po_vals) > 1) or \
                 (Qw_vals is not None and len(Qw_vals) > 1)

    if not sweep_mode:
        # Single operating point — fall back to scalar
        Po_single = (Po_vals[0] if Po_vals else None) or config.operating.Po_in_mbar
        Qw_single = (Qw_vals[0] if Qw_vals else None) or config.operating.Qw_in_mlhr
        Po_vals = [Po_single]
        Qw_vals = [Qw_single]

    print(f"  Po sweep : {Po_vals} mbar")
    print(f"  Qw sweep : {Qw_vals} mL/hr")
    print(f"  Nmc      : {config.geometry.Nmc}")

    # ── Layout schematic (always) ─────────────────────────────────────────────
    layout = compute_layout(config)
    fig = plot_layout_schematic(config, layout)
    path = out_dir / "layout_schematic.png"
    fig.savefig(path, dpi=150)
    print(f"  layout_schematic saved")

    # ── Pressure sweep plot ───────────────────────────────────────────────────
    print(f"  running pressure sweep ({len(Po_vals)} × {len(Qw_vals)} points) ...")
    fig = plot_pressure_sweep(config, Po_vals, Qw_vals)
    path = out_dir / "pressure_sweep.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    print(f"  pressure_sweep saved -> {path}")

    return 0


def _cmd_map(args: argparse.Namespace) -> int:
    import matplotlib
    matplotlib.use("Agg")
    import numpy as np

    from stepgen.config import load_config
    from stepgen.design.operating_map import compute_operating_map
    from stepgen.viz.plots import plot_operating_map

    config   = load_config(args.config)
    om       = config.operating_map
    Po_min   = args.Po_min if args.Po_min is not None else om.Po_min_mbar
    Po_max   = args.Po_max if args.Po_max is not None else om.Po_max_mbar
    Po_n     = args.Po_n   if args.Po_n   is not None else om.Po_n
    Qw_min   = args.Qw_min if args.Qw_min is not None else om.Qw_min_mlhr
    Qw_max   = args.Qw_max if args.Qw_max is not None else om.Qw_max_mlhr
    Qw_n     = args.Qw_n   if args.Qw_n   is not None else om.Qw_n
    Po_grid  = np.linspace(Po_min, Po_max, Po_n)
    Qw_grid  = np.linspace(Qw_min, Qw_max, Qw_n)

    map_result = compute_operating_map(config, Po_grid, Qw_grid)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    metrics = [
        "active_fraction", "reverse_fraction",
        "Q_spread_pct", "dP_spread_pct", "P_peak_Pa",
        "f_mean", "dP_avg_mbar", "Q_rung_nL_hr",
    ]

    print("=== map ===")
    for m in metrics:
        fig  = plot_operating_map(map_result, metric=m)
        path = out_dir / f"map_{m}.png"
        fig.savefig(path, dpi=150)
        print(f"  → {path}")

    # Window summary
    print(f"  Strict windows computed : {len(map_result.windows_strict)}")
    print(f"  Relaxed windows computed: {len(map_result.windows_relaxed)}")
    return 0


def _cmd_design(args: argparse.Namespace) -> int:
    import matplotlib
    matplotlib.use("Agg")

    from stepgen.config import load_design_search
    from stepgen.design.design_search import run_design_search
    from stepgen.io.results import save_results
    from stepgen.viz.plots import plot_design_results

    spec = load_design_search(args.spec)
    print("=== design ===")
    print(f"  Spec            : {args.spec}")
    print(f"  Target droplet  : {spec.design_targets.target_droplet_um} µm")
    print(f"  Emulsion ratio  : {spec.design_targets.target_emulsion_ratio}")
    print(f"  Qw              : {spec.design_targets.Qw_in_mlhr} mL/hr")
    print(f"  Objective       : {spec.optimization_target}")

    df = run_design_search(spec)
    print(f"  Candidates      : {len(df)}")
    if "passes_hard" in df.columns:
        n_pass = int(df["passes_hard"].sum())
        print(f"  Hard-pass       : {n_pass}")
        if n_pass > 0:
            top = df[df["passes_hard"]].iloc[0]
            print(f"  Top candidate   : Mcd={top['Mcd_um']:.0f}µm  Mcw={top['Mcw_um']:.0f}µm  "
                  f"Nmc={top['Nmc_derived']}  Q_total={top['Q_total_mlhr']:.2f} mL/hr  "
                  f"Po={top['Po_required_mbar']:.1f} mbar")

    out = args.out
    save_results(df, out)
    print(f"  → saved {out}")

    # Optional plot
    if "rank" in df.columns and len(df) > 0:
        try:
            fig = plot_design_results(df)
            plot_path = Path(out).with_suffix("") / ".." / "design_results_plot.png"
            # Save alongside output
            import os
            plot_path = Path(os.path.splitext(out)[0] + "_plot.png")
            fig.savefig(plot_path, dpi=150)
            print(f"  → {plot_path}")
        except Exception:
            pass   # plot failure never blocks the main result

    return 0


def _print_per_condition_breakdown(comp_df: "pandas.DataFrame") -> None:
    """Print detailed breakdown by operating condition."""
    import pandas as pd

    print("\n=== Per-Condition Breakdown ===")

    # Group by operating conditions
    if "Po_in_mbar" not in comp_df.columns or "Qw_in_mlhr" not in comp_df.columns:
        print("  (Operating conditions not available)")
        return

    conditions = comp_df.groupby(["Po_in_mbar", "Qw_in_mlhr"])

    # Global percentage tracking
    global_diam_pct_errors = []
    global_freq_pct_errors = []

    for (Po, Qw), group in conditions:
        n_points = len(group)

        # Calculate means
        diam_exp = group["droplet_diameter_um"].mean()
        diam_pred = group["D_pred_um"].mean()
        freq_exp = group["frequency_hz"].mean()
        freq_pred = group["f_pred_hz"].mean()

        # Calculate differences
        diam_diff = diam_pred - diam_exp
        freq_diff = freq_pred - freq_exp

        # Calculate percentage differences (avoid division by zero)
        diam_pct = (diam_diff / diam_exp * 100) if diam_exp != 0 else float('nan')
        freq_pct = (freq_diff / freq_exp * 100) if freq_exp != 0 else float('nan')

        # Track global percentages
        if not pd.isna(diam_pct):
            global_diam_pct_errors.append(abs(diam_pct))
        if not pd.isna(freq_pct):
            global_freq_pct_errors.append(abs(freq_pct))

        print(f"\n  Po={Po:.0f}mbar, Qw={Qw:.1f}mL/hr ({n_points} points):")
        print(f"    Diameter:  {diam_exp:.2f}um (exp) vs {diam_pred:.2f}um (pred) | diff: {diam_diff:+.3f}um ({diam_pct:+.1f}%)")
        print(f"    Frequency: {freq_exp:.2f}Hz (exp) vs {freq_pred:.2f}Hz (pred) | diff: {freq_diff:+.2f}Hz ({freq_pct:+.1f}%)")

    # Global averages
    if global_diam_pct_errors and global_freq_pct_errors:
        avg_diam_pct_error = sum(global_diam_pct_errors) / len(global_diam_pct_errors)
        avg_freq_pct_error = sum(global_freq_pct_errors) / len(global_freq_pct_errors)

        print(f"\n=== Global Averages ===")
        print(f"  Average diameter error: {avg_diam_pct_error:.1f}%")
        print(f"  Average frequency error: {avg_freq_pct_error:.1f}%")


def _cmd_compare(args: argparse.Namespace) -> int:
    import matplotlib
    matplotlib.use("Agg")

    from stepgen.config import load_config
    from stepgen.io.experiments import (
        calibrate_droplet_model, compare_to_predictions,
        compute_compare_report, load_experiments,
    )
    from stepgen.models.generator import iterative_solve
    from stepgen.viz.plots import plot_experiment_comparison, plot_spatial_comparison

    config = load_config(args.config)
    exp_df = load_experiments(args.experiments)

    # Apply CLI parameter overrides for refill volume
    if hasattr(args, 'enable_refill') and args.enable_refill:
        config.droplet_model.__dict__['enable_refill_volume'] = True
        print("  Override: enable_refill_volume = True")

    if hasattr(args, 'disable_refill') and args.disable_refill:
        config.droplet_model.__dict__['enable_refill_volume'] = False
        print("  Override: enable_refill_volume = False")

    if hasattr(args, 'refill_factor') and args.refill_factor is not None:
        config.droplet_model.__dict__['refill_length_factor'] = args.refill_factor
        print(f"  Override: refill_length_factor = {args.refill_factor}")

    if args.calibrate:
        config = calibrate_droplet_model(config, exp_df)
        print("  (calibration applied: k adjusted to match mean measured diameter)")

    comp_df = compare_to_predictions(config, exp_df)
    report  = compute_compare_report(comp_df)

    print("=== compare ===")
    print(f"  Points         : {report.n_points}")
    print(f"  Diam MAE       : {report.diam_mae_um:.3f} µm")
    print(f"  Diam RMSE      : {report.diam_rmse_um:.3f} µm")
    print(f"  Diam bias      : {report.diam_bias_um:+.3f} µm")
    print(f"  Freq MAE       : {report.freq_mae_hz:.3f} Hz")
    print(f"  Freq RMSE      : {report.freq_rmse_hz:.3f} Hz")
    print(f"  Freq bias      : {report.freq_bias_hz:+.3f} Hz")

    # Per-condition breakdown
    _print_per_condition_breakdown(comp_df)

    if args.out:
        comp_df.to_csv(args.out, index=False)
        print(f"  → saved {args.out}")

    # Always save comparison plots alongside output
    out_dir = Path(args.out).parent if args.out else Path(".")
    for metric in ("diameter", "frequency"):
        fig  = plot_experiment_comparison(comp_df, metric=metric)
        path = out_dir / f"compare_{metric}.png"
        fig.savefig(path, dpi=150)
        print(f"  → {path}")

    # Spatial comparison: use first unique (Po, Qw) operating point
    if len(exp_df) > 0:
        first_row = exp_df.iloc[0]
        Po_sp = float(first_row["Po_in_mbar"])
        Qw_sp = float(first_row["Qw_in_mlhr"])
        result_sp = iterative_solve(config, Po_in_mbar=Po_sp, Qw_in_mlhr=Qw_sp)
        fig_sp = plot_spatial_comparison(config, result_sp, comp_df)
        path_sp = out_dir / "spatial_comparison.png"
        fig_sp.savefig(path_sp, dpi=150)
        print(f"  → {path_sp}")

    return 0


def _cmd_study(args: argparse.Namespace) -> int:
    """Run a unified design study across topology families -> scored HTML chapter."""
    import matplotlib
    matplotlib.use("Agg")

    from stepgen.studio import (
        diagnose, load_study, run_study, score_result, write_book_index, write_workbook,
    )

    study = load_study(args.study)
    print("=== study ===")
    print(f"  Study     : {args.study}")
    print(f"  Title     : {study.title}")
    if study.from_intent:
        s = study.intent_plan.summary()
        print(f"  Intent    : {s['droplet_um']:g} µm droplets at "
              f"{s['throughput_mlhr']:g} mL/hr under {s['max_Po_mbar']:g} mbar "
              f"(fab: {s['fab']})")
        if study.intent_plan.skipped:
            for name, why in study.intent_plan.skipped.items():
                print(f"  ! skipped : {name} — {why}")
    print(f"  Families  : {', '.join(study.families)}")
    print(f"  Points    : {len(study.points)}")

    result = run_study(study, progress=True)
    if getattr(args, "production_threshold", False):
        from stepgen.studio.run import fill_production_thresholds
        print("  Po min production: ~40 solves per DESIGN (not per point)…")
        n = fill_production_thresholds(result)
        print(f"  Po min production: {n} design(s) solved")
    scored = score_result(result, study.scoring)

    diag = diagnose(study, scored, price=getattr(args, "diagnose", "auto"),
                    progress=False)

    book_dir = Path(args.book)
    chapter = book_dir / (Path(args.study).stem + ".html")
    parent = getattr(args, "extends", None)
    if parent:
        print(f"  Extends   : {parent}")
    write_workbook(result, chapter, diagnosis=diag, parent=parent)
    index = write_book_index(book_dir)

    if parent:
        # Fail loudly HERE rather than when someone later tries to read the two
        # together: a lineage that cannot be pooled is worth knowing about at the
        # moment it is created, while re-running the parent is still cheap.
        from stepgen.studio.workbook import LineageError, load_lineage
        try:
            chain = load_lineage(chapter.with_suffix(".json"))
            print(f"  Lineage   : {len(chain)} chapters, poolable")
        except LineageError as exc:
            print(f"  ! lineage : {exc}")

    n_err = sum(1 for m in result.metrics if m.error)
    print(f"  Solved    : {len(result.metrics) - n_err}/{len(result.metrics)} "
          f"({n_err} errors)")
    print(f"  Verdicts  : {diag.n_green} green / {diag.n_orange} orange / "
          f"{diag.n_red} red")
    print(f"  Model     : {result.provenance.git_hash}")
    print()
    print("  === diagnosis ===")
    for line in _wrap(diag.headline(), 74):
        print(f"  {line}")
    for p in diag.prices:
        print(f"    · {p.describe()}")
    if diag.theory_limited:
        lo, hi = diag.gamma_range[0] * 1e3, diag.gamma_range[1] * 1e3
        print()
        print(f"  Build-and-see candidates (green except exit Ca): "
              f"{len(diag.theory_limited)}")
        if diag.gamma_dependent_ca or diag.robustly_red_ca:
            print(f"    γ is unmeasured; Ca re-checked across {lo:g}-{hi:g} mN/m")
            print(f"    · red at EVERY plausible γ (believe it): "
                  f"{len(diag.robustly_red_ca)}")
            print(f"    · red only at PART of the band (the shortlist): "
                  f"{len(diag.gamma_dependent_ca)}")
        shown = diag.gamma_dependent_labels or diag.theory_limited_labels
        for lbl in shown[:5]:
            print(f"      - {lbl}")
        if len(shown) > 5:
            print(f"      - …and {len(shown) - 5} more (full list in the chapter)")
    print()
    print(f"  -> chapter : {chapter}")
    print(f"  -> sidecar : {chapter.with_suffix('.json')}")
    print(f"  -> book    : {index}")

    return 0


def _wrap(text: str, width: int) -> list[str]:
    import textwrap
    return textwrap.wrap(text, width) or [""]


def _cmd_studio_ui(args: argparse.Namespace) -> int:
    """Launch the interactive Design Studio (Phase 4) via `streamlit run`."""
    try:
        import streamlit  # noqa: F401
    except ImportError:
        print("The interactive Design Studio needs the optional UI extra.\n"
              "Install it with:\n\n    pip install -e .[ui]\n")
        return 1

    ui_path = Path(__file__).resolve().parent / "studio" / "ui.py"
    cmd = [sys.executable, "-m", "streamlit", "run", str(ui_path)]
    if args.port:
        cmd += ["--server.port", str(args.port)]
    if args.study:
        cmd += ["--", args.study]

    print(f"Launching Design Studio: {' '.join(cmd)}")
    return subprocess.call(cmd)
    return 0


def _cmd_test_experimental(args: argparse.Namespace) -> int:
    """Run comprehensive experimental testing framework."""
    from stepgen.testing.experimental_test_suite import run_experimental_testing_cli

    results = run_experimental_testing_cli(
        config_file=args.config,
        experiment_file=args.experiments,
        output_dir=args.output_dir,
        include_duty_factor=not args.skip_duty_factor,
        include_time_state=not args.skip_time_state,
        include_pcap=not args.skip_pcap,
        include_performance=not args.skip_performance
    )

    print(f"\nTesting complete! Results saved to {args.output_dir}/")
    return 0


def _cmd_test_duty_factor(args: argparse.Namespace) -> int:
    """Run duty factor analysis only."""
    from stepgen.testing.duty_factor_analyzer import DutyFactorAnalyzer
    from stepgen.config import load_config
    from stepgen.io.experiments import load_experiments

    config = load_config(args.config)
    experiments_df = load_experiments(args.experiments)

    analyzer = DutyFactorAnalyzer(config, experiments_df)
    results = analyzer.run_cross_condition_analysis()

    if args.output_dir:
        import json
        from pathlib import Path
        output_path = Path(args.output_dir)
        output_path.mkdir(exist_ok=True, parents=True)

        # Save results as JSON
        results_dict = {
            "optimal_duty_factor": results.optimal_duty_factor,
            "execution_time_s": results.execution_time_s,
            "cross_condition_results": [
                {
                    "Po_mbar": r.Po_mbar,
                    "Qw_mlhr": r.Qw_mlhr,
                    "frequency_rmse_hz": r.frequency_rmse_hz,
                    "frequency_bias_hz": r.frequency_bias_hz
                } for r in results.cross_condition_results
            ]
        }

        json_path = output_path / "duty_factor_analysis.json"
        with open(json_path, 'w') as f:
            json.dump(results_dict, f, indent=2)
        print(f"Results saved to {json_path}")

    return 0


def _cmd_test_time_state(args: argparse.Namespace) -> int:
    """Run time-state evaluation with parameter sweep."""
    from stepgen.testing.time_state_evaluator import TimeStateEvaluator
    from stepgen.config import load_config
    from stepgen.io.experiments import load_experiments

    config = load_config(args.config)
    experiments_df = load_experiments(args.experiments)

    # Apply parameter overrides if specified
    if args.params:
        param_overrides = {}
        for param_spec in args.params.split(','):
            param_spec = param_spec.strip()
            if '=' in param_spec:
                param_name, param_value = param_spec.split('=', 1)
                try:
                    param_overrides[param_name.strip()] = float(param_value.strip())
                except ValueError:
                    print(f"Warning: Could not parse parameter value {param_spec}")
            else:
                print(f"Parameter {param_spec} will be analyzed for sensitivity")

        # Apply overrides to config
        for param_name, value in param_overrides.items():
            if not hasattr(config.droplet_model, param_name):
                config.droplet_model.__dict__[param_name] = value
            else:
                setattr(config.droplet_model, param_name, value)
            print(f"Applied override: {param_name} = {value}")

    evaluator = TimeStateEvaluator(config, experiments_df)
    results = evaluator.run_evaluation()

    if args.output_dir:
        import json
        from pathlib import Path
        output_path = Path(args.output_dir)
        output_path.mkdir(exist_ok=True, parents=True)

        # Save simplified results
        results_dict = {
            "execution_time_s": results.execution_time_s,
            "baseline_comparisons": [
                {
                    "condition": comp.condition_description,
                    "linear_rmse_hz": comp.linear_rmse_hz,
                    "time_state_rmse_hz": comp.time_state_rmse_hz,
                    "improvement_vs_linear": comp.improvement_vs_linear,
                    "time_penalty_factor": comp.time_penalty_factor
                } for comp in results.baseline_comparisons
            ],
            "parameter_sensitivity": {
                param_name: {
                    "optimal_value": sens.optimal_value,
                    "optimal_rmse": sens.optimal_rmse,
                    "improvement_factor": sens.improvement_factor
                } for param_name, sens in results.parameter_sensitivity.items()
            }
        }

        json_path = output_path / "time_state_evaluation.json"
        with open(json_path, 'w') as f:
            json.dump(results_dict, f, indent=2, default=str)
        print(f"Results saved to {json_path}")

    return 0


def _cmd_verify_pcap(args: argparse.Namespace) -> int:
    """Verify Pcap implementation consistency across models."""
    from stepgen.testing.pcap_verifier import PcapVerifier
    from stepgen.config import load_config
    from stepgen.io.experiments import load_experiments

    config = load_config(args.config)

    # Load experimental data if provided, otherwise create dummy data
    if args.test_conditions:
        experiments_df = load_experiments(args.test_conditions)
    else:
        # Create minimal test data for verification
        import pandas as pd
        experiments_df = pd.DataFrame({
            'device_id': ['test'] * 3,
            'Po_in_mbar': [35.0, 50.0, 40.0],
            'Qw_in_mlhr': [1.0, 5.0, 1.0],
            'position': [0.5, 0.5, 0.5],
            'droplet_diameter_um': [12.0, 12.0, 12.0],
            'frequency_hz': [0.1, 0.1, 1.0]  # Expected frequencies for verification
        })

    verifier = PcapVerifier(config, experiments_df)
    results = verifier.verify_implementation()

    if args.output_dir:
        import json
        from pathlib import Path
        output_path = Path(args.output_dir)
        output_path.mkdir(exist_ok=True, parents=True)

        # Save verification results
        results_dict = {
            "cross_model_consistency": results.cross_model_consistency,
            "experimental_validation": results.experimental_validation,
            "implementation_issues": results.implementation_issues,
            "execution_time_s": results.execution_time_s
        }

        json_path = output_path / "pcap_verification.json"
        with open(json_path, 'w') as f:
            json.dump(results_dict, f, indent=2, default=str)
        print(f"Verification results saved to {json_path}")

    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stepgen",
        description="StepGen Designer v1 — microfluidic step-emulsification design tool.",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # ── simulate ──────────────────────────────────────────────────────────
    p_sim = sub.add_parser(
        "simulate",
        help="Simulate a single config at one operating point.",
    )
    p_sim.add_argument("config", help="Path to device YAML config.")
    p_sim.add_argument("--Po", type=float, default=None,
                       metavar="MBAR", help="Oil inlet pressure [mbar] (overrides config; Mode A).")
    p_sim.add_argument("--Qw", type=float, default=None,
                       metavar="MLHR", help="Water inlet flow [mL/hr] (overrides config).")
    p_sim.add_argument("--Qo", type=float, default=None,
                       metavar="MLHR", help="Oil inlet flow [mL/hr] (Mode B: derives Po).")
    p_sim.add_argument("--out", type=str, default=None,
                       metavar="FILE", help="Save metrics JSON to FILE.")
    p_sim.add_argument("--model", type=str, default=None,
                       choices=["steady", "duty_factor", "time_state", "time_state_filling"],
                       help="Hydraulic model variant (default: config or steady).")
    p_sim.add_argument("--dt", type=float, default=None,
                       metavar="MS", help="Time step for time-state models [ms] (overrides config).")
    p_sim.add_argument("--t-end", type=float, default=None,
                       metavar="MS", help="Simulation time for time-state models [ms] (overrides config).")
    p_sim.add_argument("--tau-pinch", type=float, default=None,
                       metavar="MS", help="Pinch phase duration [ms] (overrides config).")
    p_sim.add_argument("--tau-reset", type=float, default=None,
                       metavar="MS", help="Reset phase duration [ms] (overrides config).")
    p_sim.add_argument("--g-pinch-frac", type=float, default=None,
                       metavar="FRAC", help="Pinch conductance fraction (overrides config).")
    p_sim.add_argument("--enable-refill", action="store_true",
                       help="Enable refill volume calculation (overrides config).")
    p_sim.add_argument("--disable-refill", action="store_true",
                       help="Disable refill volume calculation (overrides config).")
    p_sim.add_argument("--refill-factor", type=float, default=None,
                       metavar="FACTOR", help="Refill length factor: L = factor × exit_height (overrides config).")

    # ── sweep ─────────────────────────────────────────────────────────────
    p_sw = sub.add_parser(
        "sweep",
        help="Evaluate multiple config files and save a results table.",
    )
    p_sw.add_argument("configs", nargs="+", help="One or more device YAML configs.")
    p_sw.add_argument("--Po", type=float, default=None,
                      metavar="MBAR", help="Override oil pressure for all candidates (Mode A).")
    p_sw.add_argument("--Qw", type=float, default=None,
                      metavar="MLHR", help="Override water flow for all candidates.")
    p_sw.add_argument("--Qo", type=float, default=None,
                      metavar="MLHR", help="Oil inlet flow [mL/hr] (Mode B: derives Po).")
    p_sw.add_argument("--out", type=str, default="sweep.csv",
                      metavar="FILE", help="Output CSV/parquet path (default: sweep.csv).")
    p_sw.add_argument("--model", type=str, default=None,
                      choices=["steady", "duty_factor", "time_state", "time_state_filling"],
                      help="Hydraulic model variant (default: config or steady).")
    p_sw.add_argument("--dt", type=float, default=None,
                      metavar="MS", help="Time step for time-state models [ms] (overrides config).")
    p_sw.add_argument("--t-end", type=float, default=None,
                      metavar="MS", help="Simulation time for time-state models [ms] (overrides config).")
    p_sw.add_argument("--tau-pinch", type=float, default=None,
                      metavar="MS", help="Pinch phase duration [ms] (overrides config).")
    p_sw.add_argument("--tau-reset", type=float, default=None,
                      metavar="MS", help="Reset phase duration [ms] (overrides config).")
    p_sw.add_argument("--g-pinch-frac", type=float, default=None,
                      metavar="FRAC", help="Pinch conductance fraction (overrides config).")
    p_sw.add_argument("--enable-refill", action="store_true",
                      help="Enable refill volume calculation (overrides config).")
    p_sw.add_argument("--disable-refill", action="store_true",
                      help="Disable refill volume calculation (overrides config).")
    p_sw.add_argument("--refill-factor", type=float, default=None,
                      metavar="FACTOR", help="Refill length factor: L = factor × exit_height (overrides config).")

    # ── report ────────────────────────────────────────────────────────────
    p_rep = sub.add_parser(
        "report",
        help="Generate simulation plots for a single config.",
    )
    p_rep.add_argument("config", help="Path to device YAML config.")
    p_rep.add_argument("--Po", type=float, nargs="+", default=None, metavar="MBAR",
                       help="Dispersed-phase inlet pressure(s) [mbar]. "
                            "Multiple values → sweep plot. Overrides YAML operating_map.Po_values.")
    p_rep.add_argument("--Qw", type=float, nargs="+", default=None, metavar="MLHR",
                       help="Continuous-phase flow(s) [mL/hr]. "
                            "Multiple values → sweep plot. Overrides YAML operating_map.Qw_values.")
    p_rep.add_argument("--out-dir", type=str, default=".",
                       metavar="DIR", help="Directory for output PNGs (default: .).")

    # ── map ───────────────────────────────────────────────────────────────
    p_map = sub.add_parser(
        "map",
        help="Compute operating map over a (Po, Qw) grid and save heatmaps.",
    )
    p_map.add_argument("config", help="Path to device YAML config.")
    p_map.add_argument("--Po-min", type=float, default=None, metavar="MBAR",
                       help="Min oil pressure [mbar] (overrides operating_map.Po_min_mbar in YAML).")
    p_map.add_argument("--Po-max", type=float, default=None, metavar="MBAR",
                       help="Max oil pressure [mbar] (overrides operating_map.Po_max_mbar in YAML).")
    p_map.add_argument("--Po-n",   type=int,   default=None, metavar="N",
                       help="Number of Po steps (overrides operating_map.Po_n in YAML).")
    p_map.add_argument("--Qw-min", type=float, default=None, metavar="MLHR",
                       help="Min water flow [mL/hr] (overrides operating_map.Qw_min_mlhr in YAML).")
    p_map.add_argument("--Qw-max", type=float, default=None, metavar="MLHR",
                       help="Max water flow [mL/hr] (overrides operating_map.Qw_max_mlhr in YAML).")
    p_map.add_argument("--Qw-n",   type=int,   default=None, metavar="N",
                       help="Number of Qw steps (overrides operating_map.Qw_n in YAML).")
    p_map.add_argument("--out-dir", type=str,  default=".",
                       metavar="DIR", help="Directory for output PNGs (default: .).")

    # ── design ────────────────────────────────────────────────────────────
    p_des = sub.add_parser(
        "design",
        help="Design-from-targets sweep: find best geometry for a droplet size target.",
    )
    p_des.add_argument("spec", help="Path to design_search YAML file.")
    p_des.add_argument("--out", type=str, default="design_results.csv",
                       metavar="FILE", help="Output CSV path (default: design_results.csv).")

    # ── compare ───────────────────────────────────────────────────────────
    p_cmp = sub.add_parser(
        "compare",
        help="Compare model predictions to measured experiment data.",
    )
    p_cmp.add_argument("config",      help="Path to device YAML config.")
    p_cmp.add_argument("experiments", help="Path to experiment CSV file.")
    p_cmp.add_argument("--out", type=str, default=None,
                       metavar="FILE", help="Save comparison DataFrame to FILE (CSV).")
    p_cmp.add_argument("--calibrate", action="store_true",
                       help="Scale droplet model k to minimise diameter error before comparing.")
    p_cmp.add_argument("--enable-refill", action="store_true",
                       help="Enable refill volume calculation (overrides config).")
    p_cmp.add_argument("--disable-refill", action="store_true",
                       help="Disable refill volume calculation (overrides config).")
    p_cmp.add_argument("--refill-factor", type=float, default=None,
                       metavar="FACTOR", help="Refill length factor: L = factor × exit_height (overrides config).")

    # ── study ─────────────────────────────────────────────────────────────
    p_study = sub.add_parser(
        "study",
        help="Run a unified design study (topology families) → scored HTML workbook.",
    )
    p_study.add_argument("study", help="Path to a study YAML (see configs/study_template.yaml).")
    p_study.add_argument("--book", type=str, default="book",
                         metavar="DIR", help="Book directory for the chapter + index (default: book).")
    p_study.add_argument("--diagnose", choices=["auto", "always", "never"], default="auto",
                         help="Price what relaxing each active constraint would buy. "
                              "Costs one full re-run per constraint, so the default "
                              "`auto` only prices when nothing scored green.")
    p_study.add_argument("--extends", type=str, default=None, metavar="PARENT.json",
                         help="Record this chapter as extending PARENT (its JSON "
                              "sidecar), making the two a lineage that may be read "
                              "as one table. Pooling is refused unless both agree "
                              "on model commit AND chapter schema.")
    p_study.add_argument("--production-threshold", action="store_true",
                         help="Also solve the lowest Po at which EVERY DFU produces, "
                              "and add it as a column. ~40 network solves per DESIGN "
                              "(not per point) — it does not depend on the swept Po. "
                              "Serpentine only; other families stay N-A.")

    # ── studio-ui ─────────────────────────────────────────────────────────
    p_ui = sub.add_parser(
        "studio-ui",
        help="Launch the interactive Design Studio (Streamlit; needs `pip install -e .[ui]`).",
    )
    p_ui.add_argument("study", nargs="?", default=None,
                      help="Optional study YAML to open on launch.")
    p_ui.add_argument("--port", type=int, default=None,
                      help="Port for the Streamlit server (default: Streamlit's own).")

    # ── test-experimental ─────────────────────────────────────────────────
    p_exp = sub.add_parser(
        "test-experimental",
        help="Run comprehensive experimental testing framework.",
    )
    p_exp.add_argument("config", help="Path to device YAML config.")
    p_exp.add_argument("experiments", help="Path to experiment CSV file.")
    p_exp.add_argument("--output-dir", type=str, default="test_results",
                       metavar="DIR", help="Directory for results output (default: test_results).")
    p_exp.add_argument("--skip-duty-factor", action="store_true",
                       help="Skip duty factor analysis.")
    p_exp.add_argument("--skip-time-state", action="store_true",
                       help="Skip time-state model evaluation.")
    p_exp.add_argument("--skip-pcap", action="store_true",
                       help="Skip Pcap verification.")
    p_exp.add_argument("--skip-performance", action="store_true",
                       help="Skip performance analysis.")

    # ── test-duty-factor ──────────────────────────────────────────────────
    p_duty = sub.add_parser(
        "test-duty-factor",
        help="Run duty factor analysis across operating conditions.",
    )
    p_duty.add_argument("config", help="Path to device YAML config.")
    p_duty.add_argument("experiments", help="Path to experiment CSV file.")
    p_duty.add_argument("--output-dir", type=str, default=None,
                        metavar="DIR", help="Directory for results output.")

    # ── test-time-state ───────────────────────────────────────────────────
    p_time = sub.add_parser(
        "test-time-state",
        help="Run time-state model evaluation with parameter sensitivity.",
    )
    p_time.add_argument("config", help="Path to device YAML config.")
    p_time.add_argument("experiments", help="Path to experiment CSV file.")
    p_time.add_argument("--output-dir", type=str, default=None,
                        metavar="DIR", help="Directory for results output.")
    p_time.add_argument("--params", type=str, default=None,
                        metavar="PARAM_LIST",
                        help="Comma-separated list of parameters to analyze (e.g., 'tau_pinch_ms=50,dt_ms').")

    # ── verify-pcap ───────────────────────────────────────────────────────
    p_pcap = sub.add_parser(
        "verify-pcap",
        help="Verify Pcap implementation consistency across model types.",
    )
    p_pcap.add_argument("config", help="Path to device YAML config.")
    p_pcap.add_argument("--test-conditions", type=str, default=None,
                        metavar="CSV", help="Path to experiment CSV for validation (optional).")
    p_pcap.add_argument("--output-dir", type=str, default=None,
                        metavar="DIR", help="Directory for results output.")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _force_utf8_console() -> None:
    """
    Make stdout/stderr tolerate the non-ASCII glyphs this CLI prints.

    On Windows the console defaults to cp1252, which cannot encode the box-drawing
    rules (`─`), arrows (`→`), `γ` or `✗` used throughout the study output.  Without
    this, `stepgen study` writes its chapter *and then dies* printing the summary —
    a completed run lost to a console encoding.

    `errors="replace"` is deliberate: a glyph the terminal cannot render must never
    kill a run that has already produced its results.  Streams that do not support
    `reconfigure` (pytest capture, pipes replaced by StringIO) are left alone.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    """
    Parse *argv* (defaults to sys.argv[1:]) and dispatch to the appropriate
    subcommand.  Returns an integer exit code (0 = success).
    """
    _force_utf8_console()

    parser = _build_parser()
    args   = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 1

    dispatch = {
        "simulate": _cmd_simulate,
        "sweep":    _cmd_sweep,
        "report":   _cmd_report,
        "map":      _cmd_map,
        "design":   _cmd_design,
        "compare":  _cmd_compare,
        "study":    _cmd_study,
        "studio-ui": _cmd_studio_ui,
        "test-experimental": _cmd_test_experimental,
        "test-duty-factor": _cmd_test_duty_factor,
        "test-time-state": _cmd_test_time_state,
        "verify-pcap": _cmd_verify_pcap,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
