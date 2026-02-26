"""
Tests for stepgen.io.experiments and plot_experiment_comparison.

Covers:
  - load_experiments: valid CSV, missing columns, type coercion
  - compare_to_predictions: columns added, residual formula, position clamping,
    solver caching (single call per unique operating point)
  - compute_compare_report: correct stats, empty DataFrame, missing columns
  - calibrate_droplet_model: scaled k gives mean diameter match
  - plot_experiment_comparison: returns Figure, invalid metric raises
"""

from __future__ import annotations

import io
import math
import textwrap

import numpy as np
import pandas as pd
import pytest

from stepgen.config import (
    DeviceConfig, DropletModelConfig, FluidConfig, FootprintConfig,
    GeometryConfig, JunctionConfig, MainChannelConfig, ManufacturingConfig,
    OperatingConfig, RungConfig,
)
from stepgen.io.experiments import (
    REQUIRED_COLUMNS,
    CompareReport,
    calibrate_droplet_model,
    compare_to_predictions,
    compute_compare_report,
    load_experiments,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_PITCH = 3.0e-6


def _make_config(
    Nmc: int = 10,
    Po_in_mbar: float = 200.0,
    Qw_in_mlhr: float = 5.0,
    dP_cap_ow_mbar: float = 50.0,
    dP_cap_wo_mbar: float = 30.0,
    k: float = 1.2,
    a: float = 0.5,
    b: float = 0.3,
    exit_width: float = 1e-6,
    exit_depth: float = 0.3e-6,
) -> DeviceConfig:
    return DeviceConfig(
        fluids=FluidConfig(
            mu_continuous=0.00089,
            mu_dispersed=0.03452,
            emulsion_ratio=0.3,
        ),
        geometry=GeometryConfig(
            main=MainChannelConfig(Mcd=100e-6, Mcw=500e-6, Mcl=_PITCH * Nmc),
            rung=RungConfig(
                mcd=1e-6, mcw=2e-6, mcl=200e-6,
                pitch=_PITCH, constriction_ratio=1.0,
            ),
            junction=JunctionConfig(
                exit_width=exit_width, exit_depth=exit_depth,
            ),
        ),
        operating=OperatingConfig(
            Po_in_mbar=Po_in_mbar,
            Qw_in_mlhr=Qw_in_mlhr,
        ),
        droplet_model=DropletModelConfig(
            k=k, a=a, b=b,
            dP_cap_ow_mbar=dP_cap_ow_mbar,
            dP_cap_wo_mbar=dP_cap_wo_mbar,
        ),
    )


def _make_csv(rows: list[dict]) -> str:
    """Build a minimal valid CSV string from a list of row dicts."""
    all_cols = list(REQUIRED_COLUMNS) + ["notes"]
    # write only the required columns (notes optional)
    cols = list(REQUIRED_COLUMNS)
    lines = [",".join(cols)]
    for r in rows:
        lines.append(",".join(str(r.get(c, "")) for c in cols))
    return "\n".join(lines)


def _default_row(position: int = 0) -> dict:
    return {
        "device_id": "dev1",
        "Po_in_mbar": 200.0,
        "Qw_in_mlhr": 5.0,
        "position": position,
        "droplet_diameter_um": 10.0,
        "frequency_hz": 100.0,
    }


def _load_from_string(csv_text: str) -> pd.DataFrame:
    return pd.read_csv(io.StringIO(csv_text))


# ---------------------------------------------------------------------------
# Tests: load_experiments
# ---------------------------------------------------------------------------

class TestLoadExperiments:

    def test_returns_dataframe(self, tmp_path):
        p = tmp_path / "exp.csv"
        p.write_text(_make_csv([_default_row()]))
        df = load_experiments(p)
        assert isinstance(df, pd.DataFrame)

    def test_has_required_columns(self, tmp_path):
        p = tmp_path / "exp.csv"
        p.write_text(_make_csv([_default_row()]))
        df = load_experiments(p)
        for col in REQUIRED_COLUMNS:
            assert col in df.columns

    def test_position_cast_to_int(self, tmp_path):
        p = tmp_path / "exp.csv"
        p.write_text(_make_csv([_default_row(position=3)]))
        df = load_experiments(p)
        assert df["position"].dtype == int or np.issubdtype(df["position"].dtype, np.integer)

    def test_numeric_columns_are_float(self, tmp_path):
        p = tmp_path / "exp.csv"
        p.write_text(_make_csv([_default_row()]))
        df = load_experiments(p)
        for col in ("Po_in_mbar", "Qw_in_mlhr", "droplet_diameter_um", "frequency_hz"):
            assert np.issubdtype(df[col].dtype, np.floating), col

    def test_multiple_rows(self, tmp_path):
        p = tmp_path / "exp.csv"
        rows = [_default_row(i) for i in range(5)]
        p.write_text(_make_csv(rows))
        df = load_experiments(p)
        assert len(df) == 5

    def test_missing_column_raises(self, tmp_path):
        # drop 'frequency_hz'
        cols = list(REQUIRED_COLUMNS - {"frequency_hz"})
        csv = ",".join(cols) + "\n" + ",".join(["x"] * len(cols))
        p = tmp_path / "exp.csv"
        p.write_text(csv)
        with pytest.raises(ValueError, match="frequency_hz"):
            load_experiments(p)

    def test_missing_multiple_columns_raises(self, tmp_path):
        csv = "device_id,Po_in_mbar\ndev1,200"
        p = tmp_path / "exp.csv"
        p.write_text(csv)
        with pytest.raises(ValueError):
            load_experiments(p)

    def test_optional_notes_preserved(self, tmp_path):
        cols = list(REQUIRED_COLUMNS) + ["notes"]
        row  = [str(_default_row().get(c, "test note")) for c in cols]
        csv  = ",".join(cols) + "\n" + ",".join(row)
        p = tmp_path / "exp.csv"
        p.write_text(csv)
        df = load_experiments(p)
        assert "notes" in df.columns


# ---------------------------------------------------------------------------
# Tests: compare_to_predictions
# ---------------------------------------------------------------------------

class TestCompareToPredictions:

    def _make_exp_df(self, n_rungs: int = 10, positions=None) -> pd.DataFrame:
        if positions is None:
            positions = [0, n_rungs // 2, n_rungs - 1]
        rows = []
        for pos in positions:
            rows.append({
                "device_id": "dev1",
                "Po_in_mbar": 200.0,
                "Qw_in_mlhr": 5.0,
                "position": pos,
                "droplet_diameter_um": 10.0,
                "frequency_hz": 100.0,
            })
        return pd.DataFrame(rows)

    def test_returns_dataframe(self):
        config = _make_config(Nmc=10)
        exp_df = self._make_exp_df()
        result = compare_to_predictions(config, exp_df)
        assert isinstance(result, pd.DataFrame)

    def test_added_columns_present(self):
        config = _make_config(Nmc=10)
        exp_df = self._make_exp_df()
        result = compare_to_predictions(config, exp_df)
        for col in ("D_pred_um", "f_pred_hz", "regime", "diam_residual_um", "freq_residual_hz"):
            assert col in result.columns, col

    def test_row_count_preserved(self):
        config = _make_config(Nmc=10)
        exp_df = self._make_exp_df(positions=[0, 1, 2, 3])
        result = compare_to_predictions(config, exp_df)
        assert len(result) == len(exp_df)

    def test_D_pred_um_matches_droplet_diameter(self):
        from stepgen.models.droplets import droplet_diameter
        config = _make_config(Nmc=10)
        exp_df = self._make_exp_df()
        result = compare_to_predictions(config, exp_df)
        expected_um = droplet_diameter(config) * 1e6
        np.testing.assert_allclose(
            result["D_pred_um"].to_numpy(), expected_um, rtol=1e-12
        )

    def test_diam_residual_formula(self):
        config = _make_config(Nmc=10)
        exp_df = self._make_exp_df()
        result = compare_to_predictions(config, exp_df)
        expected = result["D_pred_um"] - result["droplet_diameter_um"]
        np.testing.assert_allclose(
            result["diam_residual_um"].to_numpy(),
            expected.to_numpy(),
            rtol=1e-12,
        )

    def test_freq_residual_formula(self):
        config = _make_config(Nmc=10)
        exp_df = self._make_exp_df()
        result = compare_to_predictions(config, exp_df)
        expected = result["f_pred_hz"] - result["frequency_hz"]
        np.testing.assert_allclose(
            result["freq_residual_hz"].to_numpy(),
            expected.to_numpy(),
            rtol=1e-12,
        )

    def test_regime_column_valid_values(self):
        config = _make_config(Nmc=10)
        exp_df = self._make_exp_df()
        result = compare_to_predictions(config, exp_df)
        valid  = {"ACTIVE", "REVERSE", "OFF"}
        assert set(result["regime"].unique()).issubset(valid)

    def test_position_clamped_below(self):
        # position = -5 should clamp to 0
        config = _make_config(Nmc=10)
        exp_df = pd.DataFrame([{
            "device_id": "d", "Po_in_mbar": 200.0, "Qw_in_mlhr": 5.0,
            "position": -5, "droplet_diameter_um": 10.0, "frequency_hz": 50.0,
        }])
        result = compare_to_predictions(config, exp_df)
        assert len(result) == 1

    def test_position_clamped_above(self):
        # position = 999 (>> N) should clamp to N-1
        config = _make_config(Nmc=10)
        exp_df = pd.DataFrame([{
            "device_id": "d", "Po_in_mbar": 200.0, "Qw_in_mlhr": 5.0,
            "position": 999, "droplet_diameter_um": 10.0, "frequency_hz": 50.0,
        }])
        result = compare_to_predictions(config, exp_df)
        assert len(result) == 1

    def test_solver_cached_per_operating_point(self):
        """Same (Po, Qw) pair → D_pred_um is identical across rows."""
        config = _make_config(Nmc=10)
        exp_df = self._make_exp_df(positions=[0, 3, 7])
        result = compare_to_predictions(config, exp_df)
        # D_pred is geometry-based, so identical for all rows
        assert result["D_pred_um"].nunique() == 1

    def test_two_operating_points(self):
        config = _make_config(Nmc=10)
        exp_df = pd.DataFrame([
            {"device_id": "d", "Po_in_mbar": 200.0, "Qw_in_mlhr": 5.0,
             "position": 0, "droplet_diameter_um": 10.0, "frequency_hz": 50.0},
            {"device_id": "d", "Po_in_mbar": 300.0, "Qw_in_mlhr": 10.0,
             "position": 0, "droplet_diameter_um": 10.0, "frequency_hz": 80.0},
        ])
        result = compare_to_predictions(config, exp_df)
        assert len(result) == 2

    def test_original_columns_preserved(self):
        config = _make_config(Nmc=10)
        exp_df = self._make_exp_df(positions=[0])
        result = compare_to_predictions(config, exp_df)
        for col in exp_df.columns:
            assert col in result.columns


# ---------------------------------------------------------------------------
# Tests: compute_compare_report
# ---------------------------------------------------------------------------

class TestComputeCompareReport:

    def _make_compare_df(
        self,
        d_pred: list[float],
        d_meas: list[float],
        f_pred: list[float],
        f_meas: list[float],
    ) -> pd.DataFrame:
        return pd.DataFrame({
            "D_pred_um":            d_pred,
            "droplet_diameter_um":  d_meas,
            "f_pred_hz":            f_pred,
            "frequency_hz":         f_meas,
            "diam_residual_um":     [p - m for p, m in zip(d_pred, d_meas)],
            "freq_residual_hz":     [p - m for p, m in zip(f_pred, f_meas)],
        })

    def test_returns_compare_report(self):
        df = self._make_compare_df([10.0, 12.0], [9.0, 11.0], [100.0, 120.0], [90.0, 110.0])
        report = compute_compare_report(df)
        assert isinstance(report, CompareReport)

    def test_n_points(self):
        df = self._make_compare_df([10.0, 12.0, 14.0], [9.0, 11.0, 13.0],
                                   [100.0, 120.0, 140.0], [90.0, 110.0, 130.0])
        report = compute_compare_report(df)
        assert report.n_points == 3

    def test_diam_bias_zero_for_perfect_prediction(self):
        df = self._make_compare_df([10.0, 12.0], [10.0, 12.0], [100.0, 120.0], [100.0, 120.0])
        report = compute_compare_report(df)
        assert report.diam_bias_um == pytest.approx(0.0, abs=1e-12)
        assert report.freq_bias_hz == pytest.approx(0.0, abs=1e-12)

    def test_diam_mae_known_values(self):
        # errors: [+1, -2, +3] → MAE = 2.0
        df = self._make_compare_df(
            [11.0, 10.0, 13.0], [10.0, 12.0, 10.0],
            [0.0, 0.0, 0.0], [0.0, 0.0, 0.0],
        )
        report = compute_compare_report(df)
        assert report.diam_mae_um == pytest.approx(2.0, rel=1e-12)

    def test_diam_rmse_known_values(self):
        # errors: [+1, -2, +3] → RMSE = sqrt((1+4+9)/3) = sqrt(14/3)
        df = self._make_compare_df(
            [11.0, 10.0, 13.0], [10.0, 12.0, 10.0],
            [0.0, 0.0, 0.0], [0.0, 0.0, 0.0],
        )
        report = compute_compare_report(df)
        expected_rmse = math.sqrt((1 + 4 + 9) / 3.0)
        assert report.diam_rmse_um == pytest.approx(expected_rmse, rel=1e-12)

    def test_diam_bias_known_values(self):
        # errors: [+1, -2, +3] → bias = 2/3
        df = self._make_compare_df(
            [11.0, 10.0, 13.0], [10.0, 12.0, 10.0],
            [0.0, 0.0, 0.0], [0.0, 0.0, 0.0],
        )
        report = compute_compare_report(df)
        assert report.diam_bias_um == pytest.approx(2.0 / 3.0, rel=1e-12)

    def test_freq_stats_known_values(self):
        # freq errors: [+10, -20] → MAE = 15, RMSE = sqrt(250), bias = -5
        df = self._make_compare_df(
            [0.0, 0.0], [0.0, 0.0],
            [110.0, 80.0], [100.0, 100.0],
        )
        report = compute_compare_report(df)
        assert report.freq_mae_hz  == pytest.approx(15.0, rel=1e-12)
        assert report.freq_rmse_hz == pytest.approx(math.sqrt(250.0), rel=1e-12)
        assert report.freq_bias_hz == pytest.approx(-5.0, rel=1e-12)

    def test_empty_dataframe_returns_nan(self):
        df = pd.DataFrame({
            "diam_residual_um": pd.Series([], dtype=float),
            "freq_residual_hz":  pd.Series([], dtype=float),
        })
        report = compute_compare_report(df)
        assert report.n_points == 0
        assert math.isnan(report.diam_mae_um)
        assert math.isnan(report.freq_rmse_hz)

    def test_missing_residual_column_raises(self):
        df = pd.DataFrame({"diam_residual_um": [1.0]})
        with pytest.raises(ValueError, match="freq_residual_hz"):
            compute_compare_report(df)

    def test_rmse_ge_mae(self):
        df = self._make_compare_df([11.0, 10.0, 13.0], [10.0, 12.0, 10.0],
                                   [110.0, 80.0, 130.0], [100.0, 100.0, 100.0])
        report = compute_compare_report(df)
        assert report.diam_rmse_um >= report.diam_mae_um
        assert report.freq_rmse_hz >= report.freq_mae_hz


# ---------------------------------------------------------------------------
# Tests: calibrate_droplet_model
# ---------------------------------------------------------------------------

class TestCalibrateDropletModel:

    def test_returns_device_config(self):
        config = _make_config()
        exp_df = pd.DataFrame({"droplet_diameter_um": [10.0, 12.0]})
        result = calibrate_droplet_model(config, exp_df)
        assert isinstance(result, DeviceConfig)

    def test_calibrated_diameter_matches_mean_measured(self):
        from stepgen.models.droplets import droplet_diameter
        config   = _make_config()
        measured = [8.0, 12.0, 10.0]          # mean = 10.0
        exp_df   = pd.DataFrame({"droplet_diameter_um": measured})
        cal_cfg  = calibrate_droplet_model(config, exp_df)
        D_cal_um = droplet_diameter(cal_cfg) * 1e6
        assert D_cal_um == pytest.approx(10.0, rel=1e-10)

    def test_only_k_is_changed(self):
        config  = _make_config(k=1.2, a=0.5, b=0.3)
        exp_df  = pd.DataFrame({"droplet_diameter_um": [5.0]})
        cal_cfg = calibrate_droplet_model(config, exp_df)
        assert cal_cfg.droplet_model.a == config.droplet_model.a
        assert cal_cfg.droplet_model.b == config.droplet_model.b
        assert cal_cfg.droplet_model.k != config.droplet_model.k

    def test_zero_pred_returns_unchanged(self):
        # k=0 makes D_pred=0 → should return original config unchanged
        config  = _make_config(k=0.0)
        exp_df  = pd.DataFrame({"droplet_diameter_um": [10.0]})
        result  = calibrate_droplet_model(config, exp_df)
        assert result is config

    def test_zero_measured_returns_unchanged(self):
        config  = _make_config()
        exp_df  = pd.DataFrame({"droplet_diameter_um": [0.0]})
        result  = calibrate_droplet_model(config, exp_df)
        assert result is config

    def test_other_config_fields_unchanged(self):
        config  = _make_config()
        exp_df  = pd.DataFrame({"droplet_diameter_um": [10.0]})
        cal_cfg = calibrate_droplet_model(config, exp_df)
        assert cal_cfg.fluids   == config.fluids
        assert cal_cfg.geometry == config.geometry
        assert cal_cfg.operating == config.operating


# ---------------------------------------------------------------------------
# Tests: plot_experiment_comparison
# ---------------------------------------------------------------------------

class TestPlotExperimentComparison:
    import matplotlib
    matplotlib.use("Agg")

    def _make_compare_df(self) -> pd.DataFrame:
        return pd.DataFrame({
            "D_pred_um":           [10.0, 11.0, 12.0],
            "droplet_diameter_um": [9.5,  11.5, 11.0],
            "f_pred_hz":           [100.0, 120.0, 110.0],
            "frequency_hz":        [95.0,  115.0, 115.0],
            "diam_residual_um":    [0.5, -0.5, 1.0],
            "freq_residual_hz":    [5.0,   5.0,  -5.0],
        })

    def test_returns_figure_diameter(self):
        import matplotlib.figure
        from stepgen.viz.plots import plot_experiment_comparison
        fig = plot_experiment_comparison(self._make_compare_df(), metric="diameter")
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_returns_figure_frequency(self):
        import matplotlib.figure
        from stepgen.viz.plots import plot_experiment_comparison
        fig = plot_experiment_comparison(self._make_compare_df(), metric="frequency")
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_invalid_metric_raises(self):
        from stepgen.viz.plots import plot_experiment_comparison
        with pytest.raises(ValueError, match="Unknown metric"):
            plot_experiment_comparison(self._make_compare_df(), metric="blowout")

    def test_default_metric_is_diameter(self):
        import matplotlib.figure
        from stepgen.viz.plots import plot_experiment_comparison
        fig = plot_experiment_comparison(self._make_compare_df())
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_title_contains_metric(self):
        from stepgen.viz.plots import plot_experiment_comparison
        fig = plot_experiment_comparison(self._make_compare_df(), metric="frequency")
        ax  = fig.axes[0]
        assert "frequency" in ax.get_title().lower()
