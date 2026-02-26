"""
Tests for stepgen.cli.

Strategy: call main(argv_list) directly (no subprocess) with small/fast
configs (Nmc≈5) so tests stay within seconds.  File I/O goes to tmp_path.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pandas as pd
import pytest
import yaml

from stepgen.cli import main


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

_SMALL_YAML = textwrap.dedent("""\
    fluids:
      mu_continuous: 0.00089
      mu_dispersed:  0.03452
      emulsion_ratio: 0.3

    geometry:
      main:
        Mcd: 100.0e-6
        Mcw: 500.0e-6
        Mcl: 15.0e-6   # Nmc = floor(15e-6 / 3e-6) = 5

      rung:
        mcd: 1.0e-6
        mcw: 2.0e-6
        mcl: 200.0e-6
        pitch: 3.0e-6
        constriction_ratio: 1.0

      junction:
        exit_width: 1.0e-6
        exit_depth: 1.0e-6

    operating:
      Po_in_mbar: 200.0
      Qw_in_mlhr: 5.0

    droplet_model:
      dP_cap_ow_mbar: 50.0
      dP_cap_wo_mbar: 30.0
""")

_EXP_CSV = textwrap.dedent("""\
    device_id,Po_in_mbar,Qw_in_mlhr,position,droplet_diameter_um,frequency_hz
    dev1,200.0,5.0,0,10.0,50.0
    dev1,200.0,5.0,2,10.0,50.0
""")


@pytest.fixture()
def cfg(tmp_path) -> Path:
    p = tmp_path / "cfg.yaml"
    p.write_text(_SMALL_YAML)
    return p


@pytest.fixture()
def exp_csv(tmp_path) -> Path:
    p = tmp_path / "exp.csv"
    p.write_text(_EXP_CSV)
    return p


# ---------------------------------------------------------------------------
# No command → returns 1, prints help
# ---------------------------------------------------------------------------

class TestNoCommand:
    def test_returns_one(self, capsys):
        rc = main([])
        assert rc == 1

    def test_prints_help(self, capsys):
        main([])
        out = capsys.readouterr().out
        assert "stepgen" in out.lower() or "usage" in out.lower() or "COMMAND" in out


# ---------------------------------------------------------------------------
# simulate
# ---------------------------------------------------------------------------

class TestSimulate:
    def test_returns_zero(self, cfg):
        rc = main(["simulate", str(cfg)])
        assert rc == 0

    def test_prints_nmc(self, cfg, capsys):
        main(["simulate", str(cfg)])
        out = capsys.readouterr().out
        assert "Nmc" in out

    def test_po_override(self, cfg, capsys):
        main(["simulate", str(cfg), "--Po", "150"])
        out = capsys.readouterr().out
        assert "150.0" in out

    def test_qw_override(self, cfg, capsys):
        main(["simulate", str(cfg), "--Qw", "10"])
        out = capsys.readouterr().out
        assert "10.00" in out

    def test_out_json_created(self, cfg, tmp_path):
        out_path = tmp_path / "result.json"
        rc = main(["simulate", str(cfg), "--out", str(out_path)])
        assert rc == 0
        assert out_path.exists()

    def test_out_json_valid(self, cfg, tmp_path):
        import json
        out_path = tmp_path / "result.json"
        main(["simulate", str(cfg), "--out", str(out_path)])
        data = json.loads(out_path.read_text())
        assert "geometry" in data
        assert "metrics" in data
        assert "layout" in data


# ---------------------------------------------------------------------------
# sweep
# ---------------------------------------------------------------------------

class TestSweep:
    def test_returns_zero(self, cfg, tmp_path):
        out = tmp_path / "out.csv"
        rc  = main(["sweep", str(cfg), "--out", str(out)])
        assert rc == 0

    def test_creates_csv(self, cfg, tmp_path):
        out = tmp_path / "out.csv"
        main(["sweep", str(cfg), "--out", str(out)])
        assert out.exists()

    def test_csv_has_one_row(self, cfg, tmp_path):
        out = tmp_path / "out.csv"
        main(["sweep", str(cfg), "--out", str(out)])
        df = pd.read_csv(out)
        assert len(df) == 1

    def test_two_configs_two_rows(self, cfg, tmp_path):
        out = tmp_path / "out.csv"
        main(["sweep", str(cfg), str(cfg), "--out", str(out)])
        df = pd.read_csv(out)
        assert len(df) == 2

    def test_po_qw_override(self, cfg, tmp_path):
        out = tmp_path / "out.csv"
        main(["sweep", str(cfg), "--Po", "300", "--Qw", "8", "--out", str(out)])
        df = pd.read_csv(out)
        assert df["Po_in_mbar"].iloc[0] == pytest.approx(300.0)
        assert df["Qw_in_mlhr"].iloc[0] == pytest.approx(8.0)

    def test_prints_summary(self, cfg, tmp_path, capsys):
        out = tmp_path / "out.csv"
        main(["sweep", str(cfg), "--out", str(out)])
        stdout = capsys.readouterr().out
        assert "sweep" in stdout.lower()
        assert "Candidates" in stdout


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

class TestSimulateModeB:
    def test_mode_b_via_qo_flag(self, cfg, capsys):
        rc = main(["simulate", str(cfg), "--Qo", "0.5", "--Qw", "5"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Mode" in out and "B" in out
        assert "derived" in out.lower()

    def test_mode_b_prints_derived_po(self, cfg, capsys):
        main(["simulate", str(cfg), "--Qo", "0.5"])
        out = capsys.readouterr().out
        assert "derived" in out.lower()


class TestReport:
    def test_returns_zero(self, cfg, tmp_path):
        rc = main(["report", str(cfg), "--out-dir", str(tmp_path)])
        assert rc == 0

    def test_creates_png_files(self, cfg, tmp_path):
        main(["report", str(cfg), "--out-dir", str(tmp_path)])
        pngs = list(tmp_path.glob("*.png"))
        assert len(pngs) >= 5   # now includes layout_schematic

    def test_layout_schematic_png_exists(self, cfg, tmp_path):
        main(["report", str(cfg), "--out-dir", str(tmp_path)])
        assert (tmp_path / "layout_schematic.png").exists()

    def test_pressure_profiles_png_exists(self, cfg, tmp_path):
        main(["report", str(cfg), "--out-dir", str(tmp_path)])
        assert (tmp_path / "pressure_profiles.png").exists()

    def test_po_qw_override(self, cfg, tmp_path):
        rc = main(["report", str(cfg), "--Po", "250", "--Qw", "7", "--out-dir", str(tmp_path)])
        assert rc == 0


# ---------------------------------------------------------------------------
# map
# ---------------------------------------------------------------------------

class TestMap:
    def test_returns_zero(self, cfg, tmp_path):
        rc = main([
            "map", str(cfg),
            "--Po-min", "100", "--Po-max", "300", "--Po-n", "3",
            "--Qw-min", "2",   "--Qw-max", "10",  "--Qw-n",  "2",
            "--out-dir", str(tmp_path),
        ])
        assert rc == 0

    def test_creates_png_files(self, cfg, tmp_path):
        main([
            "map", str(cfg),
            "--Po-min", "100", "--Po-max", "300", "--Po-n", "3",
            "--Qw-min", "2",   "--Qw-max", "10",  "--Qw-n",  "2",
            "--out-dir", str(tmp_path),
        ])
        pngs = list(tmp_path.glob("map_*.png"))
        assert len(pngs) == 5   # one per metric

    def test_prints_window_summary(self, cfg, tmp_path, capsys):
        main([
            "map", str(cfg),
            "--Po-min", "100", "--Po-max", "300", "--Po-n", "3",
            "--Qw-min", "2",   "--Qw-max", "10",  "--Qw-n",  "2",
            "--out-dir", str(tmp_path),
        ])
        out = capsys.readouterr().out
        assert "windows" in out.lower()


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------

class TestCompare:
    def test_returns_zero(self, cfg, exp_csv, tmp_path):
        rc = main(["compare", str(cfg), str(exp_csv)])
        assert rc == 0

    def test_prints_report(self, cfg, exp_csv, capsys):
        main(["compare", str(cfg), str(exp_csv)])
        out = capsys.readouterr().out
        assert "MAE" in out
        assert "Points" in out

    def test_saves_comparison_csv(self, cfg, exp_csv, tmp_path):
        out = tmp_path / "compare.csv"
        main(["compare", str(cfg), str(exp_csv), "--out", str(out)])
        assert out.exists()
        df = pd.read_csv(out)
        assert "D_pred_um" in df.columns

    def test_creates_comparison_plots(self, cfg, exp_csv, tmp_path):
        out = tmp_path / "compare.csv"
        main(["compare", str(cfg), str(exp_csv), "--out", str(out)])
        assert (tmp_path / "compare_diameter.png").exists()
        assert (tmp_path / "compare_frequency.png").exists()

    def test_calibrate_flag(self, cfg, exp_csv, capsys):
        rc = main(["compare", str(cfg), str(exp_csv), "--calibrate"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "calibration" in out.lower()


# ---------------------------------------------------------------------------
# design
# ---------------------------------------------------------------------------

_SMALL_DESIGN_YAML = textwrap.dedent("""\
    design_targets:
      target_droplet_um: 15.0
      target_emulsion_ratio: 0.10
      Qw_in_mlhr: 5.0
    sweep_ranges:
      Mcd_um: [100]
      Mcw_um: [500]
      junction_ar: [2.75]
      mcw_um: [5]
      mcl_rung_um: [200]
""")


@pytest.fixture()
def design_spec(tmp_path) -> Path:
    p = tmp_path / "design.yaml"
    p.write_text(_SMALL_DESIGN_YAML)
    return p


class TestDesign:
    def test_returns_zero(self, design_spec, tmp_path):
        out = tmp_path / "res.csv"
        rc  = main(["design", str(design_spec), "--out", str(out)])
        assert rc == 0

    def test_creates_csv(self, design_spec, tmp_path):
        out = tmp_path / "res.csv"
        main(["design", str(design_spec), "--out", str(out)])
        assert out.exists()

    def test_csv_has_rank_column(self, design_spec, tmp_path):
        out = tmp_path / "res.csv"
        main(["design", str(design_spec), "--out", str(out)])
        df = pd.read_csv(out)
        assert "rank" in df.columns

    def test_csv_has_mcl_derived(self, design_spec, tmp_path):
        out = tmp_path / "res.csv"
        main(["design", str(design_spec), "--out", str(out)])
        df = pd.read_csv(out)
        assert "Mcl_derived_mm" in df.columns

    def test_prints_summary(self, design_spec, tmp_path, capsys):
        out = tmp_path / "res.csv"
        main(["design", str(design_spec), "--out", str(out)])
        stdout = capsys.readouterr().out
        assert "design" in stdout.lower()
        assert "Candidates" in stdout


# ---------------------------------------------------------------------------
# compare — spatial comparison output
# ---------------------------------------------------------------------------

class TestCompareSpatialt:
    def test_saves_spatial_comparison_png(self, cfg, exp_csv, tmp_path):
        out = tmp_path / "compare.csv"
        main(["compare", str(cfg), str(exp_csv), "--out", str(out)])
        assert (tmp_path / "spatial_comparison.png").exists()


# ---------------------------------------------------------------------------
# Parser-level checks
# ---------------------------------------------------------------------------

class TestParserErrors:
    def test_unknown_command_exits(self):
        with pytest.raises(SystemExit):
            main(["badcommand"])

    def test_simulate_missing_config_exits(self):
        with pytest.raises(SystemExit):
            main(["simulate"])

    def test_sweep_missing_configs_exits(self):
        with pytest.raises(SystemExit):
            main(["sweep"])

    def test_compare_missing_args_exits(self):
        with pytest.raises(SystemExit):
            main(["compare"])
