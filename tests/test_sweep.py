"""
Tests for stepgen.design.sweep and stepgen.io.results.

Covers:
  - evaluate_candidate schema (all PRD §4.1 fields present)
  - sweep DataFrame structure and row count
  - hard-constraint logic
  - save_results / load_results CSV round-trip
  - export_candidate_json output
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import pytest

from stepgen.config import (
    DeviceConfig, DropletModelConfig, FluidConfig, FootprintConfig,
    GeometryConfig, JunctionConfig, MainChannelConfig, ManufacturingConfig,
    OperatingConfig, RungConfig,
)
from stepgen.design.layout import compute_layout
from stepgen.design.sweep import REQUIRED_KEYS, evaluate_candidate, sweep
from stepgen.io.results import export_candidate_json, load_results, save_results
from stepgen.models.metrics import compute_metrics
from stepgen.models.generator import iterative_solve


# ---------------------------------------------------------------------------
# Config factory
# ---------------------------------------------------------------------------

_PITCH = 3.0e-6


def _make_config(
    Nmc: int = 10,
    Po_in_mbar: float = 200.0,
    Qw_in_mlhr: float = 5.0,
    dP_cap_ow_mbar: float = 50.0,
    Mcd: float = 100e-6,
    Mcw: float = 500e-6,
    mcd: float = 1e-6,    # ≥ min_feature_width (0.5 µm) so hard constraints pass
    mcw: float = 1e-6,
) -> DeviceConfig:
    return DeviceConfig(
        fluids=FluidConfig(
            mu_continuous=0.00089, mu_dispersed=0.03452, emulsion_ratio=0.3,
        ),
        geometry=GeometryConfig(
            main=MainChannelConfig(Mcd=Mcd, Mcw=Mcw, Mcl=_PITCH * Nmc),
            rung=RungConfig(
                mcd=mcd, mcw=mcw, mcl=200e-6,
                pitch=_PITCH, constriction_ratio=1.0,
            ),
            junction=JunctionConfig(exit_width=1e-6, exit_depth=0.3e-6),
        ),
        operating=OperatingConfig(
            Po_in_mbar=Po_in_mbar, Qw_in_mlhr=Qw_in_mlhr, P_out_mbar=0.0,
        ),
        droplet_model=DropletModelConfig(
            dP_cap_ow_mbar=dP_cap_ow_mbar, dP_cap_wo_mbar=30.0,
        ),
    )


# ---------------------------------------------------------------------------
# evaluate_candidate
# ---------------------------------------------------------------------------

class TestEvaluateCandidate:

    def test_returns_dict(self):
        row = evaluate_candidate(_make_config())
        assert isinstance(row, dict)

    def test_required_keys_present(self):
        row = evaluate_candidate(_make_config())
        for key in REQUIRED_KEYS:
            assert key in row, f"Missing required key: {key}"

    def test_operating_point_keys(self):
        row = evaluate_candidate(_make_config(), Po_in_mbar=150.0, Qw_in_mlhr=8.0)
        assert row["Po_in_mbar"] == pytest.approx(150.0)
        assert row["Qw_in_mlhr"] == pytest.approx(8.0)

    def test_geometry_keys_present(self):
        row = evaluate_candidate(_make_config())
        for key in ("Mcd_um", "Mcw_um", "Mcl_mm", "mcd_um", "mcw_um"):
            assert key in row

    def test_nmc_matches_config(self):
        cfg = _make_config(Nmc=12)
        row = evaluate_candidate(cfg)
        assert row["Nmc"] == 12

    def test_active_fraction_in_unit_interval(self):
        row = evaluate_candidate(_make_config())
        assert 0.0 <= row["active_fraction"] <= 1.0

    def test_fractions_sum_to_one(self):
        row = evaluate_candidate(_make_config())
        total = row["active_fraction"] + row["reverse_fraction"] + row["off_fraction"]
        assert total == pytest.approx(1.0, abs=1e-10)

    def test_passes_hard_constraints_present(self):
        row = evaluate_candidate(_make_config())
        assert "passes_hard_constraints" in row
        assert isinstance(row["passes_hard_constraints"], bool)

    def test_override_defaults_from_config(self):
        cfg = _make_config(Po_in_mbar=100.0)
        row = evaluate_candidate(cfg, Po_in_mbar=300.0)
        assert row["Po_in_mbar"] == pytest.approx(300.0)


# ---------------------------------------------------------------------------
# Hard constraints
# ---------------------------------------------------------------------------

class TestHardConstraints:

    def test_default_config_passes(self):
        row = evaluate_candidate(_make_config())
        assert row["passes_hard_constraints"] is True

    def test_exceeding_max_main_depth_fails(self):
        # Default max_main_depth = 200 µm; set Mcd = 300 µm → violation
        cfg = _make_config(Mcd=300e-6)
        row = evaluate_candidate(cfg)
        assert row["passes_hard_constraints"] is False

    def test_exceeding_max_main_width_fails(self):
        # Default max_main_width = 1000 µm; set Mcw = 1500 µm → violation
        cfg = _make_config(Mcw=1500e-6)
        row = evaluate_candidate(cfg)
        assert row["passes_hard_constraints"] is False

    def test_rung_below_min_feature_fails(self):
        # Default min_feature_width = 0.5 µm; set mcd = 0.1 µm → violation
        cfg = _make_config(mcd=0.1e-6)
        row = evaluate_candidate(cfg)
        assert row["passes_hard_constraints"] is False


# ---------------------------------------------------------------------------
# sweep
# ---------------------------------------------------------------------------

class TestSweep:

    def test_returns_dataframe(self):
        cfgs = [_make_config(Nmc=n) for n in [5, 8, 10]]
        df = sweep(cfgs)
        assert isinstance(df, pd.DataFrame)

    def test_row_count(self):
        cfgs = [_make_config(Nmc=n) for n in [5, 8, 10]]
        df = sweep(cfgs)
        assert len(df) == 3

    def test_nmc_column_correct(self):
        cfgs = [_make_config(Nmc=n) for n in [5, 8, 10]]
        df = sweep(cfgs)
        assert list(df["Nmc"]) == [5, 8, 10]

    def test_required_columns_present(self):
        df = sweep([_make_config()])
        for col in REQUIRED_KEYS:
            assert col in df.columns, f"Missing column: {col}"

    def test_empty_configs_returns_empty_df(self):
        df = sweep([])
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_override_operating_point(self):
        cfgs = [_make_config(), _make_config()]
        df = sweep(cfgs, Po_in_mbar=250.0, Qw_in_mlhr=3.0)
        assert list(df["Po_in_mbar"]) == pytest.approx([250.0, 250.0])
        assert list(df["Qw_in_mlhr"]) == pytest.approx([3.0, 3.0])


# ---------------------------------------------------------------------------
# io/results — CSV round-trip
# ---------------------------------------------------------------------------

class TestResultsIO:

    def test_save_load_csv_roundtrip(self, tmp_path):
        df = sweep([_make_config(Nmc=n) for n in [5, 8]])
        path = tmp_path / "results.csv"
        save_results(df, path)
        df2 = load_results(path)
        assert list(df2.columns) == list(df.columns)
        assert len(df2) == len(df)

    def test_load_csv_nmc_values(self, tmp_path):
        df = sweep([_make_config(Nmc=n) for n in [5, 8]])
        path = tmp_path / "r.csv"
        save_results(df, path)
        df2 = load_results(path)
        assert list(df2["Nmc"].astype(int)) == [5, 8]

    def test_save_unknown_format_raises(self, tmp_path):
        df = sweep([_make_config()])
        with pytest.raises(ValueError):
            save_results(df, tmp_path / "r.xyz")

    def test_load_unknown_extension_raises(self, tmp_path):
        p = tmp_path / "r.xyz"
        p.write_text("x")
        with pytest.raises(ValueError):
            load_results(p)

    def test_export_candidate_json_is_valid(self, tmp_path):
        cfg     = _make_config()
        result  = iterative_solve(cfg)
        metrics = compute_metrics(cfg, result)
        layout  = compute_layout(cfg)
        path    = tmp_path / "candidate.json"
        export_candidate_json(cfg, metrics, layout, path)
        with open(path) as fh:
            data = json.load(fh)
        assert "geometry" in data
        assert "metrics"  in data
        assert "layout"   in data
        assert "operating" in data

    def test_export_json_nmc_correct(self, tmp_path):
        cfg     = _make_config(Nmc=12)
        result  = iterative_solve(cfg)
        metrics = compute_metrics(cfg, result)
        layout  = compute_layout(cfg)
        path    = tmp_path / "c.json"
        export_candidate_json(cfg, metrics, layout, path)
        data = json.load(open(path))
        assert data["geometry"]["Nmc"] == 12


# ---------------------------------------------------------------------------
# Mode B (flow-flow BC)
# ---------------------------------------------------------------------------

class TestModeB:

    def test_mode_b_returns_derived_po(self):
        cfg = _make_config()
        row = evaluate_candidate(cfg, Qw_in_mlhr=5.0, Qo_in_mlhr=0.5)
        assert "derived_Po_in_mbar" in row
        assert row["derived_Po_in_mbar"] > 0.0

    def test_mode_b_records_qo(self):
        cfg = _make_config()
        row = evaluate_candidate(cfg, Qw_in_mlhr=5.0, Qo_in_mlhr=0.5)
        assert row["Qo_in_mlhr"] == pytest.approx(0.5)

    def test_mode_b_po_used_as_operating_po(self):
        """The derived Po should match what is stored in Po_in_mbar."""
        cfg = _make_config()
        row = evaluate_candidate(cfg, Qw_in_mlhr=5.0, Qo_in_mlhr=0.5)
        assert row["Po_in_mbar"] == pytest.approx(row["derived_Po_in_mbar"])

    def test_mode_a_has_no_derived_po(self):
        row = evaluate_candidate(_make_config())
        assert "derived_Po_in_mbar" not in row

    def test_mode_b_sweep(self):
        cfgs = [_make_config(), _make_config(Nmc=8)]
        df = sweep(cfgs, Qw_in_mlhr=5.0, Qo_in_mlhr=0.5)
        assert "derived_Po_in_mbar" in df.columns
        assert all(df["derived_Po_in_mbar"] > 0.0)

    def test_mode_b_from_config_operating(self):
        """mode='B' with Qo_in_mlhr in OperatingConfig triggers Mode B."""
        cfg = DeviceConfig(
            fluids=FluidConfig(
                mu_continuous=0.00089, mu_dispersed=0.03452, emulsion_ratio=0.3,
            ),
            geometry=GeometryConfig(
                main=MainChannelConfig(Mcd=100e-6, Mcw=500e-6, Mcl=_PITCH * 10),
                rung=RungConfig(
                    mcd=1e-6, mcw=1e-6, mcl=200e-6,
                    pitch=_PITCH, constriction_ratio=1.0,
                ),
                junction=JunctionConfig(exit_width=1e-6, exit_depth=0.3e-6),
            ),
            operating=OperatingConfig(
                Po_in_mbar=200.0, Qw_in_mlhr=5.0, mode="B", Qo_in_mlhr=0.5,
            ),
            droplet_model=DropletModelConfig(
                dP_cap_ow_mbar=50.0, dP_cap_wo_mbar=30.0,
            ),
        )
        row = evaluate_candidate(cfg)
        assert "derived_Po_in_mbar" in row
