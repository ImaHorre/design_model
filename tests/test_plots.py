"""
Tests for stepgen.viz.plots.

Verifies that each plot function:
  - runs without raising an exception
  - returns a matplotlib Figure object

Visual correctness is not tested here.
"""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")   # force non-interactive backend before any other import
import matplotlib.figure
import numpy as np
import pandas as pd
import pytest

from stepgen.config import (
    DeviceConfig, DropletModelConfig, FluidConfig, GeometryConfig,
    JunctionConfig, MainChannelConfig, OperatingConfig, RungConfig,
)
from stepgen.design.operating_map import compute_operating_map
from stepgen.models.generator import iterative_solve
from stepgen.models.hydraulics import simulate
from stepgen.viz.plots import (
    plot_operating_map,
    plot_pareto,
    plot_pressure_profiles,
    plot_regime_map,
    plot_rung_dP,
    plot_rung_flows,
    plot_rung_frequencies,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PITCH = 3.0e-6


def _make_config(Nmc: int = 6, dP_cap_ow_mbar: float = 50.0) -> DeviceConfig:
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
            dP_cap_ow_mbar=dP_cap_ow_mbar, dP_cap_wo_mbar=30.0,
        ),
    )


@pytest.fixture(scope="module")
def sim_result():
    return simulate(_make_config())


@pytest.fixture(scope="module")
def iter_result():
    return iterative_solve(_make_config())


@pytest.fixture(scope="module")
def cfg():
    return _make_config()


@pytest.fixture(scope="module")
def map_result():
    return compute_operating_map(
        _make_config(),
        np.array([100.0, 200.0, 300.0]),
        np.array([2.0, 5.0]),
    )


# ---------------------------------------------------------------------------
# Simulation plots
# ---------------------------------------------------------------------------

def test_plot_pressure_profiles_returns_figure(sim_result):
    fig = plot_pressure_profiles(sim_result)
    assert isinstance(fig, matplotlib.figure.Figure)


def test_plot_pressure_profiles_with_config(sim_result, cfg):
    fig = plot_pressure_profiles(sim_result, config=cfg)
    assert isinstance(fig, matplotlib.figure.Figure)


def test_plot_rung_dP_returns_figure(sim_result):
    fig = plot_rung_dP(sim_result)
    assert isinstance(fig, matplotlib.figure.Figure)


def test_plot_rung_flows_returns_figure(sim_result):
    fig = plot_rung_flows(sim_result)
    assert isinstance(fig, matplotlib.figure.Figure)


def test_plot_rung_frequencies_returns_figure(iter_result, cfg):
    fig = plot_rung_frequencies(iter_result, cfg)
    assert isinstance(fig, matplotlib.figure.Figure)


def test_plot_regime_map_returns_figure(iter_result, cfg):
    fig = plot_regime_map(iter_result, cfg)
    assert isinstance(fig, matplotlib.figure.Figure)


# ---------------------------------------------------------------------------
# Operating map plots
# ---------------------------------------------------------------------------

def test_plot_operating_map_active_fraction(map_result):
    fig = plot_operating_map(map_result, metric="active_fraction")
    assert isinstance(fig, matplotlib.figure.Figure)


def test_plot_operating_map_reverse_fraction(map_result):
    fig = plot_operating_map(map_result, metric="reverse_fraction")
    assert isinstance(fig, matplotlib.figure.Figure)


def test_plot_operating_map_unknown_metric_raises(map_result):
    with pytest.raises(ValueError):
        plot_operating_map(map_result, metric="nonexistent_column")


# ---------------------------------------------------------------------------
# Pareto plot
# ---------------------------------------------------------------------------

def test_plot_pareto_returns_figure():
    df = pd.DataFrame({
        "throughput": [1.0, 2.0, 3.0, 1.5],
        "window_width": [10.0, 5.0, 2.0, 8.0],
    })
    fig = plot_pareto(df, x_col="throughput", y_col="window_width")
    assert isinstance(fig, matplotlib.figure.Figure)


def test_plot_pareto_all_pareto():
    """Points on the true Pareto front produce a Figure without error."""
    df = pd.DataFrame({
        "x": [1.0, 2.0, 3.0],
        "y": [3.0, 2.0, 1.0],
    })
    fig = plot_pareto(df, x_col="x", y_col="y")
    assert isinstance(fig, matplotlib.figure.Figure)
