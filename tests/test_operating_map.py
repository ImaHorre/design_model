"""
Tests for stepgen.design.operating_map.

Covers:
  - OperatingMapResult shape and types
  - OperatingWindow field types and properties
  - Window closed when no criteria pass
  - Window open when criteria clearly pass
  - Relaxed window width ≥ strict window width
  - Contiguous-window logic
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from stepgen.config import (
    DeviceConfig, DropletModelConfig, FluidConfig, GeometryConfig,
    JunctionConfig, MainChannelConfig, OperatingConfig, RungConfig,
)
from stepgen.design.operating_map import (
    OperatingMapResult, OperatingWindow, _widest_contiguous_window,
    compute_operating_map,
)

# ---------------------------------------------------------------------------
# Config factory (small Nmc for speed)
# ---------------------------------------------------------------------------

_PITCH = 3.0e-6


def _make_config(
    Nmc: int = 5,
    dP_cap_ow_mbar: float = 50.0,
    dP_cap_wo_mbar: float = 30.0,
) -> DeviceConfig:
    return DeviceConfig(
        fluids=FluidConfig(
            mu_continuous=0.00089, mu_dispersed=0.03452, emulsion_ratio=0.3,
        ),
        geometry=GeometryConfig(
            main=MainChannelConfig(Mcd=100e-6, Mcw=500e-6, Mcl=_PITCH * Nmc),
            rung=RungConfig(
                mcd=0.3e-6, mcw=1e-6, mcl=200e-6,
                pitch=_PITCH, constriction_ratio=1.0,
            ),
            junction=JunctionConfig(exit_width=1e-6, exit_depth=0.3e-6),
        ),
        operating=OperatingConfig(Po_in_mbar=200.0, Qw_in_mlhr=5.0),
        droplet_model=DropletModelConfig(
            dP_cap_ow_mbar=dP_cap_ow_mbar, dP_cap_wo_mbar=dP_cap_wo_mbar,
        ),
    )


# Small grids for fast tests
_PO_SMALL  = np.array([50.0, 150.0, 300.0])
_QW_SMALL  = np.array([2.0, 5.0])


# ---------------------------------------------------------------------------
# _widest_contiguous_window (unit tests)
# ---------------------------------------------------------------------------

class TestWidestContiguousWindow:

    def test_all_false_returns_closed(self):
        Po = np.array([100.0, 200.0, 300.0])
        ok = np.array([False, False, False])
        w = _widest_contiguous_window(Po, ok, Qw_in_mlhr=5.0)
        assert w.is_open is False
        assert w.window_width == pytest.approx(0.0)
        assert math.isnan(w.window_center)

    def test_all_true_returns_full_range(self):
        Po = np.array([100.0, 200.0, 300.0])
        ok = np.array([True, True, True])
        w = _widest_contiguous_window(Po, ok, Qw_in_mlhr=5.0)
        assert w.is_open is True
        assert w.P_min_ok == pytest.approx(100.0)
        assert w.P_max_ok == pytest.approx(300.0)
        assert w.window_width == pytest.approx(200.0)
        assert w.window_center == pytest.approx(200.0)

    def test_single_true_gives_zero_width(self):
        Po = np.array([100.0, 200.0, 300.0])
        ok = np.array([False, True, False])
        w = _widest_contiguous_window(Po, ok, Qw_in_mlhr=5.0)
        assert w.is_open is True
        assert w.window_width == pytest.approx(0.0)
        assert w.P_min_ok == pytest.approx(200.0)
        assert w.P_max_ok == pytest.approx(200.0)

    def test_selects_widest_run(self):
        # Two runs: [0,1] width=100 and [3,4,5] width=200; widest is [3,5]
        Po  = np.array([0.0, 100.0, 200.0, 300.0, 400.0, 500.0])
        ok  = np.array([True, True, False, True, True, True])
        w = _widest_contiguous_window(Po, ok, Qw_in_mlhr=5.0)
        assert w.P_min_ok == pytest.approx(300.0)
        assert w.P_max_ok == pytest.approx(500.0)

    def test_qw_stored_correctly(self):
        Po = np.array([100.0])
        ok = np.array([True])
        w = _widest_contiguous_window(Po, ok, Qw_in_mlhr=7.5)
        assert w.Qw_in_mlhr == pytest.approx(7.5)


# ---------------------------------------------------------------------------
# compute_operating_map
# ---------------------------------------------------------------------------

class TestComputeOperatingMapShapes:

    def setup_method(self):
        self.cfg = _make_config()
        self.result = compute_operating_map(
            self.cfg, _PO_SMALL, _QW_SMALL,
        )

    def test_returns_operating_map_result(self):
        assert isinstance(self.result, OperatingMapResult)

    def test_po_grid_stored(self):
        np.testing.assert_array_equal(self.result.Po_grid, _PO_SMALL)

    def test_qw_grid_stored(self):
        np.testing.assert_array_equal(self.result.Qw_grid, _QW_SMALL)

    def test_metric_shapes(self):
        nQw, nPo = len(_QW_SMALL), len(_PO_SMALL)
        for arr in (
            self.result.active_fraction,
            self.result.reverse_fraction,
            self.result.Q_spread_pct,
            self.result.dP_spread_pct,
            self.result.P_peak_Pa,
            self.result.f_mean,
            self.result.dP_avg,
            self.result.Q_per_rung_avg,
        ):
            assert arr.shape == (nQw, nPo), f"expected ({nQw},{nPo}), got {arr.shape}"

    def test_windows_strict_length(self):
        assert len(self.result.windows_strict) == len(_QW_SMALL)

    def test_windows_relaxed_length(self):
        assert len(self.result.windows_relaxed) == len(_QW_SMALL)

    def test_active_fraction_in_unit_interval(self):
        assert np.all(self.result.active_fraction >= 0.0)
        assert np.all(self.result.active_fraction <= 1.0)

    def test_p_peak_positive(self):
        assert np.all(self.result.P_peak_Pa > 0.0)


class TestOperatingWindowFields:

    def test_window_is_operating_window(self):
        cfg    = _make_config()
        result = compute_operating_map(cfg, _PO_SMALL, _QW_SMALL)
        for w in result.windows_strict:
            assert isinstance(w, OperatingWindow)

    def test_window_width_nonnegative(self):
        cfg    = _make_config()
        result = compute_operating_map(cfg, _PO_SMALL, _QW_SMALL)
        for w in result.windows_strict + result.windows_relaxed:
            assert w.window_width >= 0.0

    def test_window_qw_matches_grid(self):
        cfg    = _make_config()
        result = compute_operating_map(cfg, _PO_SMALL, _QW_SMALL)
        for i, w in enumerate(result.windows_strict):
            assert w.Qw_in_mlhr == pytest.approx(float(_QW_SMALL[i]))

    def test_open_window_center_between_bounds(self):
        cfg    = _make_config()
        result = compute_operating_map(cfg, _PO_SMALL, _QW_SMALL)
        for w in result.windows_strict + result.windows_relaxed:
            if w.is_open:
                assert w.P_min_ok <= w.window_center <= w.P_max_ok


class TestWindowCriteria:

    def test_window_closed_when_all_off(self):
        """Very high threshold → no ACTIVE rungs → active_fraction=0 → window closed."""
        cfg = _make_config(dP_cap_ow_mbar=1e9, dP_cap_wo_mbar=1e9)
        result = compute_operating_map(
            cfg, _PO_SMALL, np.array([5.0]),
            active_fraction_min=0.5,
        )
        w = result.windows_strict[0]
        assert w.is_open is False

    def test_window_open_when_all_active(self):
        """Near-zero threshold → all rungs ACTIVE at any positive Po → window open."""
        cfg    = _make_config(dP_cap_ow_mbar=0.001, dP_cap_wo_mbar=0.001)
        Po_big = np.array([100.0, 200.0, 300.0])
        result = compute_operating_map(
            cfg, Po_big, np.array([5.0]),
            active_fraction_min=0.5,
            reverse_fraction_max=0.5,
            Q_spread_max_pct=100.0,
            dP_spread_max_pct=100.0,
        )
        w = result.windows_strict[0]
        assert w.is_open is True
        assert w.window_width == pytest.approx(200.0)

    def test_relaxed_window_ge_strict_width(self):
        """Relaxed window (fewer criteria) must be at least as wide as strict."""
        cfg    = _make_config()
        result = compute_operating_map(cfg, _PO_SMALL, _QW_SMALL)
        for w_s, w_r in zip(result.windows_strict, result.windows_relaxed):
            assert w_r.window_width >= w_s.window_width - 1e-12
