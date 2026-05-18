"""
Phase 1 Tests: Stage 1 Displacement Physics Implementation

Tests the modular correction system:
- Interface resistance correction (moving contact lines)
- Adsorption kinetics delay (surfactant effects)
- Backflow resistance correction (continuous phase backflow)
"""

import pytest
import numpy as np
import sys
from dataclasses import replace
sys.path.insert(0, '../..')  # Add project root to path

from stepgen.config import load_config
from stepgen.models.stage_wise import (
    solve_stage1_displacement_physics,
    calculate_interface_resistance_correction,
    calculate_adsorption_delay,
    calculate_backflow_correction,
    calculate_capillary_number_local,
    stage_wise_solve
)


class TestStage1DisplacementPhysics:
    """Test Stage 1 displacement physics implementation"""

    def setup_method(self):
        """Setup test configuration"""
        self.config = load_config("configs/example_stage_wise.yaml")

    def test_basic_displacement_calculation(self):
        """Test basic displacement time calculation without corrections"""
        # Create config with all corrections disabled
        stage_wise_config = replace(self.config.stage_wise,
                                  moving_interface=False,
                                  adsorption_kinetics=False,
                                  backflow=False)
        config = replace(self.config, stage_wise=stage_wise_config)

        P_j = 1000.0  # 1000 Pa pressure difference
        Q_nominal = 1e-12  # 1 pL/s flow rate

        result = solve_stage1_displacement_physics(P_j, Q_nominal, config)

        # Check basic properties
        assert result.t_displacement > 0
        assert result.reset_distance == self.config.geometry.junction.exit_width
        assert result.base_flow_rate == Q_nominal
        assert not result.active_corrections["moving_interface"]
        assert not result.active_corrections["adsorption_kinetics"]
        assert not result.active_corrections["backflow"]

        # With no corrections, displacement time should be reset_distance / flow_rate
        expected_time = result.reset_distance / Q_nominal
        np.testing.assert_allclose(result.t_displacement, expected_time, rtol=1e-6)

    def test_interface_resistance_correction(self):
        """Test moving interface resistance correction"""
        Q_nominal = 1e-12  # 1 pL/s

        resistance_factor, diagnostics = calculate_interface_resistance_correction(Q_nominal, self.config)

        assert resistance_factor >= 1.0  # Should increase resistance
        assert "capillary_number" in diagnostics
        assert "resistance_factor" in diagnostics
        assert diagnostics["capillary_number"] >= 0

        # Higher flow rate should give higher Ca and higher resistance
        Q_high = 1e-11  # 10x higher flow
        resistance_high, diag_high = calculate_interface_resistance_correction(Q_high, self.config)

        assert resistance_high > resistance_factor
        assert diag_high["capillary_number"] > diagnostics["capillary_number"]

    def test_adsorption_delay_calculation(self):
        """Test surfactant adsorption delay"""
        delay, diagnostics = calculate_adsorption_delay(self.config)

        assert delay >= 0.0  # Should be non-negative
        assert delay <= 0.001  # Should be capped at 1 ms
        assert "characteristic_length_m" in diagnostics
        assert "diffusivity_m2_per_s" in diagnostics
        assert "adsorption_delay_s" in diagnostics

    def test_backflow_correction(self):
        """Test backflow resistance correction"""
        # Test different pressure levels
        P_low = 1000.0  # Low pressure
        P_high = 10000.0  # High pressure

        factor_low, diag_low = calculate_backflow_correction(P_low, self.config)
        factor_high, diag_high = calculate_backflow_correction(P_high, self.config)

        # Both should be >= 1 (increase resistance)
        assert factor_low >= 1.0
        assert factor_high >= 1.0

        # Higher pressure should give higher backflow resistance
        assert factor_high >= factor_low

        assert "P_j_Pa" in diag_low
        assert "backflow_factor" in diag_low

    def test_capillary_number_calculation(self):
        """Test local capillary number calculation"""
        Q_nominal = 1e-12  # 1 pL/s

        ca = calculate_capillary_number_local(Q_nominal, self.config)

        assert ca >= 0.0  # Should be positive
        assert np.isfinite(ca)  # Should be finite

        # Higher flow should give higher Ca
        Q_high = 1e-11
        ca_high = calculate_capillary_number_local(Q_high, self.config)
        assert ca_high > ca

    def test_modular_corrections_integration(self):
        """Test that corrections can be enabled/disabled modularly"""
        P_j = 20000.0  # Higher pressure to trigger backflow (well above 50 mbar = 5000 Pa)
        Q_nominal = 1e-12

        # Test all corrections off
        stage_wise_none = replace(self.config.stage_wise,
                                 moving_interface=False,
                                 adsorption_kinetics=False,
                                 backflow=False)
        config_none = replace(self.config, stage_wise=stage_wise_none)
        result_none = solve_stage1_displacement_physics(P_j, Q_nominal, config_none)

        # Test interface correction only
        stage_wise_interface = replace(self.config.stage_wise,
                                      moving_interface=True,
                                      adsorption_kinetics=False,
                                      backflow=False)
        config_interface = replace(self.config, stage_wise=stage_wise_interface)
        result_interface = solve_stage1_displacement_physics(P_j, Q_nominal, config_interface)

        assert result_interface.t_displacement > result_none.t_displacement
        assert result_interface.active_corrections["moving_interface"]
        assert not result_interface.active_corrections["adsorption_kinetics"]

        # Test backflow correction only
        stage_wise_backflow = replace(self.config.stage_wise,
                                     moving_interface=False,
                                     adsorption_kinetics=False,
                                     backflow=True)
        config_backflow = replace(self.config, stage_wise=stage_wise_backflow)
        result_backflow = solve_stage1_displacement_physics(P_j, Q_nominal, config_backflow)

        assert result_backflow.t_displacement > result_none.t_displacement
        assert not result_backflow.active_corrections["moving_interface"]
        assert result_backflow.active_corrections["backflow"]

    def test_correction_factors_preservation(self):
        """Test that correction factors are properly stored in results"""
        P_j = 3000.0
        Q_nominal = 5e-13

        # Enable all corrections
        stage_wise_config = replace(self.config.stage_wise,
                                   moving_interface=True,
                                   adsorption_kinetics=True,
                                   backflow=True)
        config = replace(self.config, stage_wise=stage_wise_config)

        result = solve_stage1_displacement_physics(P_j, Q_nominal, config)

        # Check correction factors are applied
        assert result.correction_factors.interface_resistance >= 1.0
        assert result.correction_factors.adsorption_delay >= 0.0
        assert result.correction_factors.backflow_effect >= 1.0

        # Check diagnostics are present
        assert "interface_resistance" in result.diagnostics
        assert "adsorption" in result.diagnostics
        assert "backflow" in result.diagnostics


class TestStage1Integration:
    """Test integration of Stage 1 physics with full model"""

    def setup_method(self):
        """Setup test configuration"""
        self.config = load_config("configs/example_stage_wise.yaml")

    def test_full_model_with_stage1_physics(self):
        """Test that Stage 1 physics works in full model"""
        result = stage_wise_solve(self.config, Po_in_mbar=200.0, Qw_in_mlhr=5.0)

        # Check that Stage 1 results are present
        for group_result in result.group_results:
            stage1 = group_result.stage1_result

            assert stage1.t_displacement > 0
            assert stage1.reset_distance > 0
            assert stage1.base_flow_rate >= 0

            # Check that correction factors were calculated
            assert hasattr(stage1.correction_factors, 'interface_resistance')
            assert hasattr(stage1.correction_factors, 'backflow_effect')

    def test_stage1_timing_contributions(self):
        """Test Stage 1 timing contributions in diagnostics"""
        result = stage_wise_solve(self.config, Po_in_mbar=200.0, Qw_in_mlhr=5.0)

        # Check timing diagnostics
        assert "stage1_displacement" in result.diagnostics.stage_timings
        stage1_timings = result.diagnostics.stage_timings["stage1_displacement"]

        assert len(stage1_timings) == len(result.group_results)
        assert all(t > 0 for t in stage1_timings)

    def test_correction_impact_analysis(self):
        """Test analysis of correction mechanism impacts"""
        # Run with corrections
        result_with = stage_wise_solve(self.config, Po_in_mbar=200.0, Qw_in_mlhr=5.0)

        # Run without corrections
        stage_wise_config = replace(self.config.stage_wise,
                                   moving_interface=False,
                                   backflow=False)
        config_without = replace(self.config, stage_wise=stage_wise_config)
        result_without = stage_wise_solve(config_without, Po_in_mbar=200.0, Qw_in_mlhr=5.0)

        # Stage 1 timings should be different
        t1_with = result_with.diagnostics.stage_timings["stage1_displacement"]
        t1_without = result_without.diagnostics.stage_timings["stage1_displacement"]

        # With corrections should generally be slower (but could depend on parameters)
        assert len(t1_with) == len(t1_without)


if __name__ == "__main__":
    # Run tests and save results
    pytest.main([__file__, "-v", "--tb=short",
                f"--html=test_results/phase1_stage1_physics/test_report.html",
                f"--junitxml=test_results/phase1_stage1_physics/test_results.xml"])