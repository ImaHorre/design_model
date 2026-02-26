"""
stepgen.cli
===========
Command-line interface for StepGen Designer v1.

Commands
--------
    stepgen simulate <config.yaml>  [--Po P] [--Qw Q] [--out results.json]
    stepgen sweep    <cfg1> [cfg2 …] [--Po P] [--Qw Q] [--out sweep.csv]
    stepgen report   <config.yaml>  [--Po P] [--Qw Q] [--out-dir DIR]
    stepgen map      <config.yaml>  [--Po-min …] [--Po-max …] [--Po-n …]
                                    [--Qw-min …] [--Qw-max …] [--Qw-n …]
                                    [--out-dir DIR]
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
    row    = evaluate_candidate(config, Po_in_mbar=args.Po, Qw_in_mlhr=args.Qw)

    print("=== simulate ===")
    print(f"  Config  : {args.config}")
    print(f"  Po      : {row['Po_in_mbar']:.1f} mbar")
    print(f"  Qw      : {row['Qw_in_mlhr']:.2f} mL/hr")
    print(f"  Nmc     : {row['Nmc']}")
    print(f"  active  : {row['active_fraction']*100:.1f} %")
    print(f"  reverse : {row['reverse_fraction']*100:.1f} %")
    print(f"  Q_unif  : {row['Q_uniformity_pct']:.2f} %")
    print(f"  dP_unif : {row['dP_uniformity_pct']:.2f} %")
    print(f"  D_pred  : {row['D_pred']*1e6:.3f} µm")
    print(f"  f_mean  : {row['f_pred_mean']:.2f} Hz")
    print(f"  fits    : {row['fits_footprint']}")
    print(f"  hard OK : {row['passes_hard_constraints']}")

    if args.out:
        from stepgen.config import load_config as _lc
        from stepgen.models.generator import iterative_solve
        from stepgen.models.metrics import compute_metrics
        from stepgen.design.layout import compute_layout
        from stepgen.io.results import export_candidate_json

        Po = args.Po if args.Po is not None else config.operating.Po_in_mbar
        Qw = args.Qw if args.Qw is not None else config.operating.Qw_in_mlhr
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

    configs = [load_config(p) for p in args.configs]
    df      = sweep(configs, Po_in_mbar=args.Po, Qw_in_mlhr=args.Qw)

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
    from stepgen.models.generator import iterative_solve
    from stepgen.viz.plots import (
        plot_pressure_profiles, plot_rung_dP, plot_rung_flows,
        plot_rung_frequencies, plot_regime_map,
    )

    config  = load_config(args.config)
    Po      = args.Po if args.Po is not None else config.operating.Po_in_mbar
    Qw      = args.Qw if args.Qw is not None else config.operating.Qw_in_mlhr
    result  = iterative_solve(config, Po_in_mbar=Po, Qw_in_mlhr=Qw)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    plots = {
        "pressure_profiles": plot_pressure_profiles(result, config),
        "rung_dP":           plot_rung_dP(result, config),
        "rung_flows":        plot_rung_flows(result, config),
        "rung_frequencies":  plot_rung_frequencies(result, config),
        "regime_map":        plot_regime_map(result, config),
    }

    print("=== report ===")
    for name, fig in plots.items():
        path = out_dir / f"{name}.png"
        fig.savefig(path, dpi=150)
        print(f"  → {path}")

    return 0


def _cmd_map(args: argparse.Namespace) -> int:
    import matplotlib
    matplotlib.use("Agg")
    import numpy as np

    from stepgen.config import load_config
    from stepgen.design.operating_map import compute_operating_map
    from stepgen.viz.plots import plot_operating_map

    config   = load_config(args.config)
    Po_grid  = np.linspace(args.Po_min, args.Po_max, args.Po_n)
    Qw_grid  = np.linspace(args.Qw_min, args.Qw_max, args.Qw_n)

    map_result = compute_operating_map(config, Po_grid, Qw_grid)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    metrics = [
        "active_fraction", "reverse_fraction",
        "Q_uniformity_pct", "dP_uniformity_pct", "P_peak_Pa",
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


def _cmd_compare(args: argparse.Namespace) -> int:
    import matplotlib
    matplotlib.use("Agg")

    from stepgen.config import load_config
    from stepgen.io.experiments import (
        calibrate_droplet_model, compare_to_predictions,
        compute_compare_report, load_experiments,
    )
    from stepgen.viz.plots import plot_experiment_comparison

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
                       metavar="MBAR", help="Oil inlet pressure [mbar] (overrides config).")
    p_sim.add_argument("--Qw", type=float, default=None,
                       metavar="MLHR", help="Water inlet flow [mL/hr] (overrides config).")
    p_sim.add_argument("--out", type=str, default=None,
                       metavar="FILE", help="Save metrics JSON to FILE.")

    # ── sweep ─────────────────────────────────────────────────────────────
    p_sw = sub.add_parser(
        "sweep",
        help="Evaluate multiple config files and save a results table.",
    )
    p_sw.add_argument("configs", nargs="+", help="One or more device YAML configs.")
    p_sw.add_argument("--Po", type=float, default=None,
                      metavar="MBAR", help="Override oil pressure for all candidates.")
    p_sw.add_argument("--Qw", type=float, default=None,
                      metavar="MLHR", help="Override water flow for all candidates.")
    p_sw.add_argument("--out", type=str, default="sweep.csv",
                      metavar="FILE", help="Output CSV/parquet path (default: sweep.csv).")

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
    p_map.add_argument("--Po-min", type=float, default=50.0,  metavar="MBAR")
    p_map.add_argument("--Po-max", type=float, default=500.0, metavar="MBAR")
    p_map.add_argument("--Po-n",   type=int,   default=10,    metavar="N")
    p_map.add_argument("--Qw-min", type=float, default=1.0,   metavar="MLHR")
    p_map.add_argument("--Qw-max", type=float, default=20.0,  metavar="MLHR")
    p_map.add_argument("--Qw-n",   type=int,   default=5,     metavar="N")
    p_map.add_argument("--out-dir", type=str,  default=".",
                       metavar="DIR", help="Directory for output PNGs (default: .).")

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
        "compare":  _cmd_compare,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
