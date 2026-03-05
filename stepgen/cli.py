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

Entry point (pyproject.toml):
    stepgen = "stepgen.cli:main"
"""

from __future__ import annotations

import argparse
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

    Qo = getattr(args, "Qo", None)
    row = evaluate_candidate(
        config,
        Po_in_mbar=args.Po,
        Qw_in_mlhr=args.Qw,
        Qo_in_mlhr=Qo,
        model_type=args.model,
    )

    print("=== simulate ===")
    print(f"  Config  : {args.config}")
    if "derived_Po_in_mbar" in row:
        print(f"  Mode    : B (flow-flow)")
        print(f"  Qo      : {row['Qo_in_mlhr']:.3f} mL/hr (requested)")
        print(f"  Po      : {row['derived_Po_in_mbar']:.1f} mbar (derived)")
    else:
        print(f"  Mode    : A (pressure-flow)")
        print(f"  Po      : {row['Po_in_mbar']:.1f} mbar")
    print(f"  Qw      : {row['Qw_in_mlhr']:.2f} mL/hr")
    q_oil   = row['Q_oil_total']
    q_water = row['Q_water_total']
    emulsion_ratio = q_oil / (q_oil + q_water) if (q_oil + q_water) > 0 else 0.0
    print(f"  Qo      : {q_oil*3.6e12:.1f} µL/hr")
    print(f"  emulsion: {emulsion_ratio:.3f}  ({emulsion_ratio*100:.1f}% oil by volume)")
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
    from stepgen.viz.plots import plot_layout_schematic, plot_combined_profiles

    config  = load_config(args.config)
    Po      = args.Po if args.Po is not None else config.operating.Po_in_mbar
    Qw      = args.Qw if args.Qw is not None else config.operating.Qw_in_mlhr

    print("=== report ===")
    print(f"  solving  Po={Po} mbar  Qw={Qw} mL/hr  Nmc={config.geometry.Nmc} ...")
    result  = iterative_solve(config, Po_in_mbar=Po, Qw_in_mlhr=Qw)
    layout  = compute_layout(config)
    print("  rendering plots ...")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    plot_fns = {
        "layout_schematic":  lambda: plot_layout_schematic(config, layout),
        "spatial_profiles":  lambda: plot_combined_profiles(result, config),
    }

    for name, fn in plot_fns.items():
        print(f"  {name} ...", end="", flush=True)
        fig  = fn()
        path = out_dir / f"{name}.png"
        fig.savefig(path, dpi=150)
        print(f"  saved")

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

    # ── report ────────────────────────────────────────────────────────────
    p_rep = sub.add_parser(
        "report",
        help="Generate simulation plots for a single config.",
    )
    p_rep.add_argument("config", help="Path to device YAML config.")
    p_rep.add_argument("--Po", type=float, default=None, metavar="MBAR")
    p_rep.add_argument("--Qw", type=float, default=None, metavar="MLHR")
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

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """
    Parse *argv* (defaults to sys.argv[1:]) and dispatch to the appropriate
    subcommand.  Returns an integer exit code (0 = success).
    """
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
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
