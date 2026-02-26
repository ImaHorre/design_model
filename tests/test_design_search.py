"""
Tests for stepgen.design.design_search and stepgen.config.load_design_search.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stepgen.config import (
    DesignHardConstraints, DesignSearchSpec, DesignSoftConstraints,
    DesignTargets, DropletModelConfig, FluidConfig, FootprintConfig,
    ManufacturingConfig, SweepRanges, load_design_search,
)
from stepgen.design.design_search import (
    _derive_junction_geometry,
    _derive_mcd_from_ar,
    _max_mcl_for_footprint,
    run_design_search,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _small_spec(
    Mcd_um=(100,),
    Mcw_um=(500,),
    junction_ar=(2.75,),
    mcw_um=(5,),
    mcl_rung_um=(200,),
    target_droplet_um: float = 15.0,
    target_emulsion_ratio: float = 0.10,
    optimization_target: str = "max_throughput",
) -> DesignSearchSpec:
    return DesignSearchSpec(
        design_targets=DesignTargets(
            target_droplet_um=target_droplet_um,
            target_emulsion_ratio=target_emulsion_ratio,
            Qw_in_mlhr=10.0,
        ),
        footprint=FootprintConfig(
            footprint_area_cm2=10.0,
            footprint_aspect_ratio=1.5,
            lane_spacing=500e-6,
            turn_radius=500e-6,
            reserve_border=2e-3,
        ),
        hard_constraints=DesignHardConstraints(),
        soft_constraints=DesignSoftConstraints(),
        optimization_target=optimization_target,
        sweep_ranges=SweepRanges(
            Mcd_um=Mcd_um,
            Mcw_um=Mcw_um,
            junction_ar=junction_ar,
            mcw_um=mcw_um,
            mcl_rung_um=mcl_rung_um,
        ),
        fluids=FluidConfig(
            mu_continuous=0.00089,
            mu_dispersed=0.03452,
            emulsion_ratio=target_emulsion_ratio,
        ),
        droplet_model=DropletModelConfig(),
        manufacturing=ManufacturingConfig(),
    )


# ---------------------------------------------------------------------------
# Junction geometry derivation
# ---------------------------------------------------------------------------

class TestDeriveJunctionGeometry:

    def test_returns_two_floats(self):
        spec = _small_spec()
        w, h = _derive_junction_geometry(spec, mcd_m=5e-6)
        assert isinstance(w, float) and isinstance(h, float)

    def test_depth_equals_mcd(self):
        """exit_depth must equal the rung depth passed in (constant etch depth)."""
        spec = _small_spec()
        mcd_m = 6.3e-6
        w, h = _derive_junction_geometry(spec, mcd_m=mcd_m)
        assert h == pytest.approx(mcd_m)

    def test_predicted_diameter_matches_target(self):
        spec = _small_spec(target_droplet_um=15.0)
        mcd_m = 5e-6
        w, h = _derive_junction_geometry(spec, mcd_m=mcd_m)
        dm = spec.droplet_model
        D_pred = dm.k * (w ** dm.a) * (h ** dm.b)
        assert D_pred * 1e6 == pytest.approx(15.0, rel=1e-6)

    def test_larger_target_gives_larger_exit_width(self):
        """With fixed mcd, a larger droplet target requires a wider junction exit."""
        spec25 = _small_spec(target_droplet_um=25.0)
        spec10 = _small_spec(target_droplet_um=10.0)
        mcd_m = 5e-6
        w25, _ = _derive_junction_geometry(spec25, mcd_m=mcd_m)
        w10, _ = _derive_junction_geometry(spec10, mcd_m=mcd_m)
        assert w25 > w10


# ---------------------------------------------------------------------------
# Junction aspect ratio enforcement
# ---------------------------------------------------------------------------

class TestJunctionAspectRatio:

    def test_ar_outside_range_fails_hard(self):
        """junction_ar=5.0 is outside max_junction_aspect_ratio=3.0 → passes_hard=False."""
        spec = _small_spec(junction_ar=(5.0,))
        df = run_design_search(spec)
        assert not df["passes_hard"].all()

    def test_valid_ar_passes_hard(self):
        """junction_ar=2.75 is within [2.5, 3.0] → candidate can pass hard constraints."""
        spec = _small_spec(junction_ar=(2.75,))
        df = run_design_search(spec)
        assert df["passes_hard"].any()

    def test_exit_depth_equals_mcd_derived(self):
        """exit_depth_um must equal mcd_derived_um (depth is constant = rung etch depth)."""
        spec = _small_spec(junction_ar=(2.75,))
        df = run_design_search(spec)
        assert "exit_depth_um" in df.columns
        assert "mcd_derived_um" in df.columns
        assert df["exit_depth_um"].iloc[0] == pytest.approx(
            df["mcd_derived_um"].iloc[0], rel=1e-6
        )

    def test_pitch_equals_two_exit_widths(self):
        """pitch_derived_um must equal 2 × exit_width_um."""
        spec = _small_spec(junction_ar=(2.75,))
        df = run_design_search(spec)
        assert df["pitch_derived_um"].iloc[0] == pytest.approx(
            2.0 * df["exit_width_um"].iloc[0], rel=1e-6
        )

    def test_derive_mcd_from_ar_roundtrip(self):
        """mcd derived from AR should reproduce the target droplet diameter."""
        spec = _small_spec(target_droplet_um=15.0)
        dm = spec.droplet_model
        for ar in (2.5, 2.75, 3.0):
            mcd_m = _derive_mcd_from_ar(spec, ar)
            exit_w = ar * mcd_m
            D_pred = dm.k * (exit_w ** dm.a) * (mcd_m ** dm.b)
            assert D_pred * 1e6 == pytest.approx(15.0, rel=1e-6)


# ---------------------------------------------------------------------------
# Mcl_max computation
# ---------------------------------------------------------------------------

class TestMaxMclForFootprint:

    def test_returns_positive(self):
        fp = FootprintConfig()
        mcl = _max_mcl_for_footprint(fp, 500e-6)
        assert mcl > 0.0

    def test_wider_channel_gives_shorter_mcl(self):
        fp = FootprintConfig()
        mcl_narrow = _max_mcl_for_footprint(fp, 200e-6)
        mcl_wide   = _max_mcl_for_footprint(fp, 800e-6)
        assert mcl_narrow > mcl_wide

    def test_channel_wider_than_footprint_returns_zero(self):
        fp = FootprintConfig(footprint_area_cm2=1.0, reserve_border=2e-3)
        # Mcw = 50 mm >> chip height → zero Mcl
        mcl = _max_mcl_for_footprint(fp, 50e-3)
        assert mcl == 0.0


# ---------------------------------------------------------------------------
# run_design_search
# ---------------------------------------------------------------------------

class TestRunDesignSearch:

    def test_returns_dataframe(self):
        import pandas as pd
        spec = _small_spec()
        df = run_design_search(spec)
        assert hasattr(df, "columns")

    def test_rank_column_present(self):
        spec = _small_spec()
        df = run_design_search(spec)
        assert "rank" in df.columns

    def test_mcl_derived_column_present(self):
        """Mcl_derived_mm must appear (it is computed, not user-specified)."""
        spec = _small_spec()
        df = run_design_search(spec)
        assert "Mcl_derived_mm" in df.columns

    def test_nmc_derived_column_present(self):
        spec = _small_spec()
        df = run_design_search(spec)
        assert "Nmc_derived" in df.columns

    def test_required_output_columns(self):
        required = {
            "rank", "Mcd_um", "Mcw_um", "Mcl_derived_mm", "Nmc_derived",
            "junction_ar", "mcd_derived_um", "pitch_derived_um",
            "mcw_um", "mcl_rung_um",
            "Q_total_mlhr", "Po_required_mbar", "active_fraction",
            "D_pred_um", "passes_hard", "soft_flags",
        }
        spec = _small_spec()
        df = run_design_search(spec)
        missing = required - set(df.columns)
        assert not missing, f"Missing columns: {missing}"

    def test_rank_is_ascending_from_one(self):
        spec = _small_spec(Mcd_um=(100, 150), Mcw_um=(500,))
        df = run_design_search(spec)
        assert list(df["rank"]) == list(range(1, len(df) + 1))

    def test_top_candidate_sorted_by_q_total(self):
        spec = _small_spec(Mcd_um=(100, 150), junction_ar=(2.5, 3.0))
        df = run_design_search(spec)
        q = df["Q_total_mlhr"].dropna()
        assert q.iloc[0] >= q.iloc[-1] or q.isna().all()

    def test_hard_constraint_violation_flagged(self):
        """Rung width below min_feature_width → passes_hard=False."""
        spec = _small_spec(mcw_um=(0.1,))   # 0.1 µm < 0.5 µm min
        df = run_design_search(spec)
        assert not df["passes_hard"].all()

    def test_d_pred_um_close_to_target(self):
        """Predicted droplet diameter should match the target."""
        spec = _small_spec(target_droplet_um=15.0)
        df = run_design_search(spec)
        valid = df["D_pred_um"].dropna()
        if len(valid) > 0:
            assert valid.iloc[0] == pytest.approx(15.0, rel=0.01)


# ---------------------------------------------------------------------------
# load_design_search YAML round-trip
# ---------------------------------------------------------------------------

class TestLoadDesignSearch:

    def test_load_template_yaml(self):
        path = Path(__file__).parent.parent / "examples" / "design_search_template.yaml"
        if not path.exists():
            pytest.skip("design_search_template.yaml not found")
        spec = load_design_search(path)
        assert isinstance(spec, DesignSearchSpec)
        assert spec.design_targets.target_droplet_um == pytest.approx(15.0)

    def test_load_minimal_yaml(self, tmp_path):
        yaml_content = """
design_targets:
  target_droplet_um: 10.0
  target_emulsion_ratio: 0.05
  Qw_in_mlhr: 5.0
sweep_ranges:
  Mcd_um: [100]
  Mcw_um: [500]
  junction_ar: [2.75]
  mcw_um: [5]
  mcl_rung_um: [200]
"""
        p = tmp_path / "mini.yaml"
        p.write_text(yaml_content)
        spec = load_design_search(p)
        assert spec.design_targets.target_droplet_um == pytest.approx(10.0)
        assert spec.sweep_ranges.Mcd_um == (100.0,)

    def test_load_yaml_with_pressure_hard_constraints(self, tmp_path):
        """New Po hard constraint fields should be parsed from YAML."""
        yaml_content = """
design_targets:
  target_droplet_um: 15.0
  target_emulsion_ratio: 0.10
sweep_ranges:
  Mcd_um: [100]
  Mcw_um: [500]
  junction_ar: [2.75]
  mcw_um: [5]
  mcl_rung_um: [200]
hard_constraints:
  min_Po_in_mbar: 50.0
  max_Po_in_mbar: 800.0
  max_delam_line_load_N_per_m: 120.0
"""
        p = tmp_path / "pressure.yaml"
        p.write_text(yaml_content)
        spec = load_design_search(p)
        assert spec.hard_constraints.min_Po_in_mbar == pytest.approx(50.0)
        assert spec.hard_constraints.max_Po_in_mbar == pytest.approx(800.0)
        assert spec.hard_constraints.max_delam_line_load_N_per_m == pytest.approx(120.0)


# ---------------------------------------------------------------------------
# Pressure hard constraints
# ---------------------------------------------------------------------------

class TestPressureHardConstraints:

    def test_hard_Po_max_excludes_high_pressure_candidates(self):
        """max_Po_in_mbar=1 mbar is impossibly tight — all candidates fail passes_hard."""
        spec = DesignSearchSpec(
            design_targets=_small_spec().design_targets,
            footprint=_small_spec().footprint,
            hard_constraints=DesignHardConstraints(max_Po_in_mbar=1.0),
            soft_constraints=DesignSoftConstraints(),
            optimization_target="max_throughput",
            sweep_ranges=_small_spec().sweep_ranges,
            fluids=_small_spec().fluids,
            droplet_model=_small_spec().droplet_model,
            manufacturing=_small_spec().manufacturing,
        )
        df = run_design_search(spec)
        passing = df[df["passes_hard"] == True]
        assert len(passing) == 0, "Expected zero passing candidates at max_Po=1 mbar"

    def test_hard_Po_min_excludes_low_pressure_candidates(self):
        """min_Po_in_mbar=1e9 is impossibly high — all candidates fail passes_hard."""
        spec = DesignSearchSpec(
            design_targets=_small_spec().design_targets,
            footprint=_small_spec().footprint,
            hard_constraints=DesignHardConstraints(min_Po_in_mbar=1e9),
            soft_constraints=DesignSoftConstraints(),
            optimization_target="max_throughput",
            sweep_ranges=_small_spec().sweep_ranges,
            fluids=_small_spec().fluids,
            droplet_model=_small_spec().droplet_model,
            manufacturing=_small_spec().manufacturing,
        )
        df = run_design_search(spec)
        passing = df[df["passes_hard"] == True]
        assert len(passing) == 0, "Expected zero passing candidates at min_Po=1e9 mbar"

    def test_default_Po_limits_allow_normal_design(self):
        """Default max_Po_in_mbar=1000 should allow typical designs to pass hard constraints."""
        spec = _small_spec()  # uses DesignHardConstraints() defaults
        df = run_design_search(spec)
        assert df["passes_hard"].any(), "Expected at least one passing candidate with default Po limits"
