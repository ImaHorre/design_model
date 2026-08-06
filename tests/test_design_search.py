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
    footprint_area_cm2: float = 10.0,
) -> DesignSearchSpec:
    return DesignSearchSpec(
        design_targets=DesignTargets(
            target_droplet_um=target_droplet_um,
            target_emulsion_ratio=target_emulsion_ratio,
            Qw_in_mlhr=10.0,
        ),
        footprint=FootprintConfig(
            footprint_area_cm2=footprint_area_cm2,
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
        # 2 cm², not the 10 cm² default: see TestDefaultSpecIsOilStarved below.
        # This test is about the aspect-ratio gate, so its candidate has to be a
        # device that clears every *other* gate.
        spec = _small_spec(junction_ar=(2.75,), footprint_area_cm2=2.0)
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
        mcl = _max_mcl_for_footprint(fp, 500e-6, 200e-6)
        assert mcl > 0.0

    def test_wider_channel_gives_shorter_mcl(self):
        fp = FootprintConfig()
        mcl_narrow = _max_mcl_for_footprint(fp, 200e-6, 200e-6)
        mcl_wide   = _max_mcl_for_footprint(fp, 800e-6, 200e-6)
        assert mcl_narrow > mcl_wide

    def test_longer_rung_gives_shorter_mcl(self):
        """
        The rung array is part of the lane pair (W1-1). This site used to omit
        it entirely, so it over-stated Mcl_max against the model and against the
        drawing; a longer rung must now cost lanes.
        """
        fp = FootprintConfig()
        mcl_short = _max_mcl_for_footprint(fp, 500e-6, 200e-6)
        mcl_long  = _max_mcl_for_footprint(fp, 500e-6, 4.0e-3)
        assert mcl_short > mcl_long

    def test_channel_wider_than_footprint_returns_zero(self):
        fp = FootprintConfig(footprint_area_cm2=1.0, reserve_border=2e-3)
        # Mcw = 50 mm >> chip height → zero Mcl
        mcl = _max_mcl_for_footprint(fp, 50e-3, 200e-6)
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
            # F1 (2026-08-06): a verdict with no reason beside it is what made
            # the reverse-flow guard read as a blank table.
            "hard_constraint_failures", "reverse_fraction", "off_fraction",
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
        # DesignHardConstraints() defaults, on a device that is actually normal —
        # 2 cm² derives Po ≈ 220 mbar with every rung active.  The 10 cm² default
        # spec is not a normal design; see TestDefaultSpecIsOilStarved below.
        spec = _small_spec(footprint_area_cm2=2.0)
        df = run_design_search(spec)
        assert df["passes_hard"].any(), "Expected at least one passing candidate with default Po limits"


class TestDefaultSpecIsOilStarved:
    """
    Found by the reverse-flow guard (2026-08-06), and recorded rather than
    papered over: the 10 cm² default spec is **not a working device**.

    Mode B asks the *linear* solver for the Po that delivers Qo = 1.0 mL/hr.  The
    linear solve has no capillary thresholds, so it answers 65 mbar — and at
    65 mbar a 500 × 100 µm main cannot feed 13,326 rungs.  The far end sits below
    the water rail, water pushes back through it, and the net oil flow comes out
    **negative**: the device consumes oil.

    Two tests above asserted `passes_hard` on this candidate and were green only
    because nothing checked flow direction.  This is o/w (0.89 cP continuous,
    34.5 cP dispersed), so reverse flow is not a W/O-only pathology — it is what
    an oil-starved ladder does regardless of which phase is which.

    Not fixed here: Mode B deriving a drive pressure that yields negative
    throughput is a design-search defect, and correcting the oracle is a separate
    piece of work.  What must not happen again is it being reported as passing.
    """

    def test_ten_cm2_default_is_reported_as_failing(self):
        import stepgen.design.sweep as sweep_mod

        seen: list[dict] = []
        original = sweep_mod.evaluate_candidate

        def spy(*args, **kwargs):
            row = original(*args, **kwargs)
            seen.append(row)
            return row

        sweep_mod.evaluate_candidate = spy
        try:
            df = run_design_search(_small_spec())   # the 10 cm² default
        finally:
            sweep_mod.evaluate_candidate = original

        assert seen, "no candidate was solved"
        row = seen[-1]
        assert row["reverse_fraction"] > 0.4
        assert row["Q_oil_total"] < 0.0, "net oil flow is into the device"
        assert row["passes_hard_constraints"] is False
        assert not df["passes_hard"].any()

    def test_a_fully_active_candidate_still_passes(self):
        """The guard must not simply fail everything the design search proposes."""
        df = run_design_search(_small_spec(footprint_area_cm2=2.0))
        assert df["passes_hard"].any()

    def test_off_rungs_alone_do_not_fail_a_candidate(self):
        """
        At 4 cm² the candidate is 51 % active / 49 % off with no reverse flow.
        Half the DFUs dead is a low-drive-pressure operating point, not a broken
        design, and it must still pass — that is the off/reverse distinction.
        """
        df = run_design_search(_small_spec(footprint_area_cm2=4.0))
        assert df["passes_hard"].any()
        assert (df["active_fraction"] < 1.0).any()


class TestEveryFailureRecordsAReason:
    """
    F1 (2026-08-06).  The reverse-flow guard made the design search correctly
    reject the oil-starved default spec — and the search had no field for *why*,
    so the correct verdict arrived as a table of `passes_hard: False` with no
    reason anywhere in the CSV.

    `passes_hard` is a conjunction of FOUR screens (geometry pre-filter, derived
    Po limits, delamination, and `evaluate_candidate`'s own hard constraints).
    Only the last had a reason string in existence, and it was dropped.  These
    tests pin the invariant that matters: **no silent False.**
    """

    def test_the_verdict_is_derived_from_the_reasons_not_kept_beside_them(self):
        """
        The bug class this closes is a boolean and a reason list drifting apart.
        They cannot drift if one is computed from the other, and this asserts
        exactly that, on every row of a frame containing both outcomes.
        """
        df = run_design_search(_small_spec(Mcd_um=(100, 150), junction_ar=(2.5, 3.0)))
        for _, row in df.iterrows():
            has_reason = bool(str(row["hard_constraint_failures"]).strip())
            assert row["passes_hard"] is not has_reason, (
                f"passes_hard={row['passes_hard']} with "
                f"reasons={row['hard_constraint_failures']!r}"
            )

    def test_no_failing_row_is_silent(self):
        df = run_design_search(_small_spec())      # the oil-starved 10 cm² default
        failing = df[~df["passes_hard"]]
        assert len(failing) > 0, "fixture no longer fails; pick another"
        for blob in failing["hard_constraint_failures"]:
            assert str(blob).strip(), "a candidate failed with no reason recorded"

    def test_the_reverse_flow_failure_names_reverse_flow(self):
        """
        The specific regression: this is the guard's own verdict, and before F1
        it did not survive the trip from `evaluate_candidate` into the frame.
        """
        df = run_design_search(_small_spec())
        blobs = " ".join(df["hard_constraint_failures"].astype(str))
        assert "reverse_fraction" in blobs
        assert (df["reverse_fraction"] > 0.4).any(), (
            "the fraction that caused the failure must be a column too"
        )

    def test_a_geometry_failure_names_the_config_field(self):
        """
        A reason a reader cannot act on is barely better than none, so the
        message carries the YAML key and the value that breached it.
        """
        df = run_design_search(_small_spec(mcw_um=(0.1,)))   # < 0.5 µm min
        blobs = " ".join(df["hard_constraint_failures"].astype(str))
        assert "min_feature_width_um" in blobs
        assert "0.10" in blobs      # the offending value, in YAML units

    def test_no_reason_contains_the_separator_that_joins_reasons(self):
        """
        Reasons are joined with "; ", so no reason may contain "; " — otherwise
        the blob cannot be split back into fields.

        This is not hypothetical: the reverse-flow message read "... entering
        the dispersed main; device-level metrics are computed over the 36.0% of
        rungs still active", so `stepgen design`'s reason tally tore it in half
        and reported the tail — which carries a per-candidate percentage — as a
        constraint in its own right, once per distinct percentage.  On the
        checked-in 100 cm² spec that was 15 spurious tally lines under one real
        one.
        """
        df = run_design_search(_small_spec())      # reverse-flow failures
        blobs = list(df["hard_constraint_failures"].astype(str))
        assert any("reverse_fraction" in b for b in blobs), "fixture no longer reverses"
        for blob in blobs:
            for reason in blob.split("; "):
                assert ";" not in reason, (
                    f"reason contains the field separator: {reason!r}"
                )

    def test_a_collapse_index_tie_says_it_is_a_tie(self):
        """
        Found by the reason column on its first run.  `Mcw/Mcd` is a ratio of
        two values converted from µm, so an intended exact tie is not exact:
        2000/200 is 10.000000000000002 and fails `> 10.0`.  The comparison is
        deliberately unchanged — which candidates pass is a ruling — but the
        message must not read "10.0 > 10.0" and send the reader hunting.

        Asserted on the helper rather than end to end, because which ratios tie
        is a floating-point fact, not a modelling one: 800/100 is exactly 8.0
        and does not tie, so an end-to-end version of this test passes
        vacuously.  2000/200 is the case `configs/design_search_10um.yaml`
        actually hits.

        The unit conversion has to be written exactly as the search writes it.
        `200e-6` is a parsed literal and `200 * 1e-6` is a multiplication, and
        they are **different floats** (0.0002 vs 0.00019999999999999998) — so
        the literal form gives an exact 10.0 and no tie at all.  The tie is
        manufactured by the µm → m conversion, which is the loop's own first
        move.
        """
        from stepgen.design.design_search import _geometry_failure_reasons

        Mcd_m, Mcw_m = 200 * 1e-6, 2000 * 1e-6      # as design_search.py:253-254
        collapse_index = Mcw_m / max(Mcd_m, 1e-12)  # as design_search.py:269
        assert collapse_index != 10.0, "premise gone: this ratio is exact now"

        hc = DesignHardConstraints(max_collapse_index=10.0)
        reasons = _geometry_failure_reasons(
            hc, Mcd_m, Mcw_m, mcd_m=5e-6, mcw_m=5e-6,
            collapse_index=collapse_index, ar=2.75,
        )
        blob = " ".join(reasons)
        assert "max_collapse_index" in blob
        assert "floating-point tie" in blob
        assert "raise max_collapse_index" in blob

    def test_a_candidate_that_merely_does_not_fit_still_appears(self):
        """
        The extreme form of the same defect.  The footprint-reject append was
        guarded by `if not passes_hard_geom`, so a candidate whose geometry was
        FINE and which simply did not fit was dropped from the output entirely
        — no row, no reason, and (being the only candidate) an empty frame with
        no columns at all.
        """
        df = run_design_search(_small_spec(footprint_area_cm2=0.01))
        assert len(df) > 0, "candidate vanished instead of being reported"
        assert not df["passes_hard"].any()
        blobs = " ".join(df["hard_constraint_failures"].astype(str))
        assert "footprint" in blobs
        assert "min_feature_width_um" not in blobs, (
            "geometry is fine here; only the footprint should be blamed"
        )
