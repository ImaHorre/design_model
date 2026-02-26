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
    _max_mcl_for_footprint,
    run_design_search,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _small_spec(
    Mcd_um=(100,),
    Mcw_um=(500,),
    pitch_um=(40,),
    mcd_um=(5,),
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
            pitch_um=pitch_um,
            mcd_um=mcd_um,
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
        w, h = _derive_junction_geometry(spec)
        assert isinstance(w, float) and isinstance(h, float)

    def test_square_junction(self):
        spec = _small_spec()
        w, h = _derive_junction_geometry(spec)
        assert w == pytest.approx(h, rel=1e-9)

    def test_predicted_diameter_matches_target(self):
        spec = _small_spec(target_droplet_um=15.0)
        w, h = _derive_junction_geometry(spec)
        dm = spec.droplet_model
        D_pred = dm.k * (w ** dm.a) * (h ** dm.b)
        assert D_pred * 1e6 == pytest.approx(15.0, rel=1e-6)

    def test_larger_target_gives_larger_junction(self):
        spec25 = _small_spec(target_droplet_um=25.0)
        spec10 = _small_spec(target_droplet_um=10.0)
        _, h25 = _derive_junction_geometry(spec25)
        _, h10 = _derive_junction_geometry(spec10)
        assert h25 > h10


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
            "pitch_um", "mcd_um", "mcw_um", "mcl_rung_um",
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
        spec = _small_spec(Mcd_um=(100, 150), pitch_um=(40, 60))
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
  pitch_um: [40]
  mcd_um: [5]
  mcw_um: [5]
  mcl_rung_um: [200]
"""
        p = tmp_path / "mini.yaml"
        p.write_text(yaml_content)
        spec = load_design_search(p)
        assert spec.design_targets.target_droplet_um == pytest.approx(10.0)
        assert spec.sweep_ranges.Mcd_um == (100.0,)
