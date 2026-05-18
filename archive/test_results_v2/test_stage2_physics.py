"""
Phase 2 Tests: Stage 2 Bulb Growth and Necking Physics Implementation

Tests the bulb growth and necking system:
- Geometry-controlled breakup (Dangla criterion)
- Necking time models (viscocapillary scaling)
- Simplified vs detailed bulb growth
- Droplet size calculation with necking inflation
"""

import pytest
import numpy as np
import sys
from dataclasses import replace
sys.path.insert(0, '../..')  # Add project root to path

from stepgen.config import load_config
from stepgen.models.stage_wise import (
    solve_stage2_bulb_physics,
    calculate_critical_radius,
    calculate_necking_time,
    solve_simplified_bulb_growth,
    solve_detailed_bulb_growth,
    analyze_stage2_regime,
    stage_wise_solve
)


class TestStage2BulbPhysics:
    """Test Stage 2 bulb growth and necking physics"""

    def setup_method(self):
        """Setup test configuration"""
        self.config = load_config("configs/example_stage_wise.yaml")

    def test_critical_radius_calculation(self):
        """Test Dangla criterion for critical radius"""
        R_critical = calculate_critical_radius(self.config)

        # Should be positive and related to geometry
        assert R_critical > 0
        step_height = self.config.geometry.junction.exit_depth
        channel_width = self.config.geometry.junction.exit_width

        # Should be at least half step height
        assert R_critical >= 0.5 * step_height

        # Should scale with geometry
        assert np.isfinite(R_critical)

        # Should be reasonable order of magnitude (micrometers for typical geometry)
        assert 1e-7 < R_critical < 1e-4  # 100 nm to 100 μm

    def test_necking_time_calculation(self):
        """Test viscocapillary necking time scaling"""
        tau_necking, diagnostics = calculate_necking_time(self.config)

        # Basic properties
        assert tau_necking > 0
        assert np.isfinite(tau_necking)
        assert 1e-6 <= tau_necking <= 1e-3  # Bounds: 1 μs to 1 ms

        # Diagnostics should contain expected keys
        assert "viscosity_ratio" in diagnostics
        assert "characteristic_length_m" in diagnostics
        assert "necking_time_s" in diagnostics

        # Viscosity ratio should be positive
        assert diagnostics["viscosity_ratio"] > 0

    def test_necking_time_models(self):
        """Test different necking time models"""
        # Test viscocapillary model
        config_visco = replace(self.config.stage_wise, necking_time_model="viscocapillary")
        config1 = replace(self.config, stage_wise=config_visco)

        tau1, diag1 = calculate_necking_time(config1)

        # Test empirical model
        config_emp = replace(self.config.stage_wise, necking_time_model="empirical")
        config2 = replace(self.config, stage_wise=config_emp)

        tau2, diag2 = calculate_necking_time(config2)

        # Both should be positive and finite
        assert tau1 > 0 and tau2 > 0
        assert np.isfinite(tau1) and np.isfinite(tau2)

        # Models should give different results (unless by coincidence)
        assert diag1["necking_model"] != diag2["necking_model"]

    def test_simplified_bulb_growth(self):
        """Test simplified bulb growth model"""
        t_growth, diagnostics = solve_simplified_bulb_growth(self.config)

        # Basic properties
        assert t_growth > 0
        assert np.isfinite(t_growth)
        assert 1e-6 <= t_growth <= 1e-2  # Bounds: 1 μs to 10 ms

        # Diagnostics should contain physics parameters
        assert "R_critical_m" in diagnostics
        assert "V_critical_m3" in diagnostics
        assert "P_laplace_Pa" in diagnostics
        assert "Q_characteristic_m3_per_s" in diagnostics

        # Physical consistency
        assert diagnostics["R_critical_m"] > 0
        assert diagnostics["V_critical_m3"] > 0
        assert diagnostics["P_laplace_Pa"] > 0

    def test_detailed_bulb_growth(self):
        """Test detailed bulb growth with Laplace pressure evolution"""
        P_j = 10000.0  # 10 kPa
        Q_nominal = 1e-12  # 1 pL/s
        R_critical = calculate_critical_radius(self.config)

        t_growth, diagnostics = solve_detailed_bulb_growth(P_j, Q_nominal, R_critical, self.config)

        # Basic properties
        assert t_growth > 0
        assert np.isfinite(t_growth)
        assert 1e-6 <= t_growth <= 1e-2

        # Detailed integration diagnostics
        assert diagnostics["detailed_integration"] is True
        assert "R_initial_m" in diagnostics
        assert "R_final_m" in diagnostics
        assert "P_laplace_avg_Pa" in diagnostics

        # Physical consistency
        assert diagnostics["R_final_m"] == R_critical
        assert diagnostics["R_initial_m"] < diagnostics["R_final_m"]

    def test_stage2_regime_analysis(self):
        """Test Stage 2 regime classification"""
        P_j = 5000.0
        Q_nominal = 1e-12
        R_critical = calculate_critical_radius(self.config)
        tau_necking, _ = calculate_necking_time(self.config)

        stage2_params = {
            "R_critical": R_critical,
            "necking_time": tau_necking,
            "inflation_fraction": 0.05  # 5% inflation
        }

        regime_indicators = analyze_stage2_regime(P_j, Q_nominal, self.config, stage2_params)

        # Should contain all expected indicators
        assert "pressure_driven" in regime_indicators
        assert "geometry_dominated" in regime_indicators
        assert "inflation_significant" in regime_indicators
        assert "necking_limited" in regime_indicators
        assert "pressure_ratio" in regime_indicators

        # Logical consistency
        pressure_driven = regime_indicators["pressure_driven"]
        geometry_dominated = regime_indicators["geometry_dominated"]

        # Should be mutually exclusive (in this simple model)
        assert pressure_driven != geometry_dominated

    def test_full_stage2_physics_integration(self):
        """Test complete Stage 2 physics solver"""
        P_j = 8000.0  # 8 kPa
        Q_nominal = 2e-12  # 2 pL/s

        result = solve_stage2_bulb_physics(P_j, Q_nominal, self.config)

        # Check all result fields are present and reasonable
        assert result.t_growth > 0
        assert result.t_necking > 0
        assert result.t_total == result.t_growth + result.t_necking
        assert result.D_droplet > 0
        assert result.V_droplet > 0
        assert result.R_critical > 0

        # Check droplet size is reasonable (micrometers)
        assert 1e-6 < result.D_droplet < 100e-6  # 1 μm to 100 μm

        # Check diagnostics are comprehensive
        assert "necking" in result.diagnostics
        assert "growth" in result.diagnostics
        assert "regime_analysis" in result.diagnostics

    def test_necking_inflation_effect(self):
        """Test that necking inflation increases droplet size"""
        P_j = 5000.0
        Q_low = 1e-13   # Low flow rate
        Q_high = 1e-11  # High flow rate

        result_low = solve_stage2_bulb_physics(P_j, Q_low, self.config)
        result_high = solve_stage2_bulb_physics(P_j, Q_high, self.config)

        # Higher flow rate should give larger final volume due to inflation
        assert result_high.V_droplet > result_low.V_droplet
        assert result_high.D_droplet > result_low.D_droplet

        # But critical radius should be the same (geometry-controlled)
        assert abs(result_high.R_critical - result_low.R_critical) < 1e-9


class TestStage2ModelSwitching:
    """Test switching between simplified and detailed growth models"""

    def setup_method(self):
        """Setup test configuration"""
        self.config = load_config("configs/example_stage_wise.yaml")

    def test_simplified_vs_detailed_models(self):
        """Test that simplified and detailed models give different but reasonable results"""
        P_j = 7000.0
        Q_nominal = 1.5e-12

        # Test simplified model
        config_simple = replace(self.config.stage_wise, use_detailed_growth=False)
        config1 = replace(self.config, stage_wise=config_simple)
        result_simple = solve_stage2_bulb_physics(P_j, Q_nominal, config1)

        # Test detailed model
        config_detailed = replace(self.config.stage_wise, use_detailed_growth=True)
        config2 = replace(self.config, stage_wise=config_detailed)
        result_detailed = solve_stage2_bulb_physics(P_j, Q_nominal, config2)

        # Both should be reasonable
        assert result_simple.t_growth > 0 and result_detailed.t_growth > 0
        assert result_simple.D_droplet > 0 and result_detailed.D_droplet > 0

        # Critical radius should be the same (geometry-controlled)
        assert abs(result_simple.R_critical - result_detailed.R_critical) < 1e-9

        # Necking time should be the same (fluid-property controlled)
        assert abs(result_simple.t_necking - result_detailed.t_necking) < 1e-9

        # Growth times might be different (different models)
        # But both should be in reasonable range
        assert 1e-6 <= result_simple.t_growth <= 1e-2
        assert 1e-6 <= result_detailed.t_growth <= 1e-2


class TestStage2Integration:
    """Test integration of Stage 2 physics with full model"""

    def setup_method(self):
        """Setup test configuration"""
        self.config = load_config("configs/example_stage_wise.yaml")

    def test_full_model_with_stage2_physics(self):
        """Test that Stage 2 physics works in full stage-wise model"""
        result = stage_wise_solve(self.config, Po_in_mbar=250.0, Qw_in_mlhr=4.0)

        # Check that Stage 2 results are present and reasonable
        for group_result in result.group_results:
            stage2 = group_result.stage2_result

            # Basic properties
            assert stage2.t_growth > 0
            assert stage2.t_necking > 0
            assert stage2.t_total > 0
            assert stage2.D_droplet > 0
            assert stage2.V_droplet > 0

            # Physics consistency
            assert stage2.t_total == stage2.t_growth + stage2.t_necking

            # Reasonable droplet size
            assert 1e-6 < stage2.D_droplet < 100e-6

    def test_stage2_timing_in_diagnostics(self):
        """Test Stage 2 timing appears in model diagnostics"""
        result = stage_wise_solve(self.config, Po_in_mbar=200.0, Qw_in_mlhr=5.0)

        # Check timing diagnostics include Stage 2 components
        assert "stage2_growth" in result.diagnostics.stage_timings
        assert "stage2_necking" in result.diagnostics.stage_timings

        stage2_growth_timings = result.diagnostics.stage_timings["stage2_growth"]
        stage2_necking_timings = result.diagnostics.stage_timings["stage2_necking"]

        assert len(stage2_growth_timings) == len(result.group_results)
        assert len(stage2_necking_timings) == len(result.group_results)
        assert all(t > 0 for t in stage2_growth_timings)
        assert all(t > 0 for t in stage2_necking_timings)

    def test_frequency_ceiling_concept(self):
        """Test that Stage 2 provides frequency ceiling (constant timing at high pressure)"""
        # Test at different pressures
        P_low = 100.0   # mbar
        P_high = 400.0  # mbar

        result_low = stage_wise_solve(self.config, Po_in_mbar=P_low, Qw_in_mlhr=5.0)
        result_high = stage_wise_solve(self.config, Po_in_mbar=P_high, Qw_in_mlhr=5.0)

        # Extract Stage 2 timings
        stage2_low = [gr.stage2_result.t_total for gr in result_low.group_results]
        stage2_high = [gr.stage2_result.t_total for gr in result_high.group_results]

        # Stage 2 timing should be relatively constant (frequency ceiling)
        avg_stage2_low = np.mean(stage2_low)
        avg_stage2_high = np.mean(stage2_high)

        # Should be closer than Stage 1 timings (which should vary more with pressure)
        stage2_variation = abs(avg_stage2_high - avg_stage2_low) / avg_stage2_low

        # Stage 2 variation should be small (< 50% for typical pressure range)
        assert stage2_variation < 0.5, f"Stage 2 varies too much with pressure: {stage2_variation:.2%}"


if __name__ == "__main__":
    # Run tests and save results
    pytest.main([__file__, "-v", "--tb=short"])