"""
Test suite for stage-wise droplet formation model.

Tests the three-layer architecture:
1. Hydraulic Network (existing backbone)
2. Local Droplet Event Law (Stage 1 + Stage 2 physics)
3. Optional Correction Mechanisms
"""

import pytest
import numpy as np
from stepgen.config import load_config
from stepgen.models.stage_wise import (
    stage_wise_solve,
    analyze_pressure_uniformity,
    create_uniform_group,
    create_pressure_groups,
    solve_device,
    StageWiseResult,
    RegimeClassification
)


class TestStageWiseBasics:
    """Basic functionality tests for stage-wise model"""

    def test_stage_wise_solve_basic(self):
        """Test basic stage-wise solve functionality"""
        config = load_config("configs/example_stage_wise.yaml")

        result = stage_wise_solve(config, Po_in_mbar=200.0, Qw_in_mlhr=5.0)

        assert isinstance(result, StageWiseResult)
        assert len(result.group_results) > 0
        assert "average_frequency_hz" in result.global_metrics
        assert "average_diameter_m" in result.global_metrics


class TestAdaptiveGrouping:
    """Test adaptive grouping logic"""

    def test_pressure_uniformity_analysis(self):
        """Test pressure uniformity detection"""
        config = load_config("configs/example_stage_wise.yaml")

        # Get hydraulic result for analysis
        from stepgen.models.hydraulics import simulate
        hydraulic_result = simulate(config, Po_in_mbar=200.0, Qw_in_mlhr=5.0)

        analysis = analyze_pressure_uniformity(hydraulic_result, config)

        assert "requires_grouping" in analysis
        assert "P_j_range_Pa" in analysis
        assert "relative_variation" in analysis
        assert isinstance(analysis["requires_grouping"], bool)

    def test_uniform_group_creation(self):
        """Test uniform group creation"""
        config = load_config("configs/example_stage_wise.yaml")

        from stepgen.models.hydraulics import simulate
        hydraulic_result = simulate(config, Po_in_mbar=200.0, Qw_in_mlhr=5.0)

        groups = create_uniform_group(hydraulic_result, config)

        assert len(groups) == 1
        assert groups[0]["group_id"] == 0
        assert len(groups[0]["rung_indices"]) == len(hydraulic_result.P_oil)

    def test_multiple_group_creation(self):
        """Test multiple group creation"""
        config = load_config("configs/example_stage_wise.yaml")

        from stepgen.models.hydraulics import simulate
        hydraulic_result = simulate(config, Po_in_mbar=200.0, Qw_in_mlhr=5.0)

        groups = create_pressure_groups(hydraulic_result, config)

        assert len(groups) > 1
        assert len(groups) <= config.stage_wise.max_groups

        # Check all rungs are assigned to exactly one group
        all_rung_indices = []
        for group in groups:
            all_rung_indices.extend(group["rung_indices"])

        assert sorted(all_rung_indices) == list(range(len(hydraulic_result.P_oil)))


class TestUnifiedInterface:
    """Test unified solver interface"""

    def test_solve_device_auto_selection(self):
        """Test automatic method selection"""
        config = load_config("configs/example_stage_wise.yaml")

        # Should auto-select stage_wise because config.stage_wise.enabled = True
        result = solve_device(config, method="auto")

        assert isinstance(result, StageWiseResult)

    def test_solve_device_explicit_method(self):
        """Test explicit method selection"""
        config = load_config("configs/example_stage_wise.yaml")

        # Test stage_wise method
        result_stage = solve_device(config, method="stage_wise")
        assert isinstance(result_stage, StageWiseResult)

        # Test iterative method (existing)
        result_iter = solve_device(config, method="iterative")
        assert hasattr(result_iter, "P_oil")  # Should be SimResult

        # Test linear method (existing)
        result_linear = solve_device(config, method="linear")
        assert hasattr(result_linear, "P_oil")  # Should be SimResult

    def test_solve_device_invalid_method(self):
        """Test error handling for invalid method"""
        config = load_config("configs/example_stage_wise.yaml")

        with pytest.raises(ValueError, match="Unknown method"):
            solve_device(config, method="invalid_method")


class TestConfigIntegration:
    """Test config system integration"""

    def test_stage_wise_config_loading(self):
        """Test that stage_wise config section loads properly"""
        config = load_config("configs/example_stage_wise.yaml")

        assert hasattr(config, 'stage_wise')
        assert config.stage_wise.enabled is True
        assert config.stage_wise.pressure_uniformity_threshold == 0.05
        assert config.stage_wise.max_groups == 10

        # Test correction toggles
        assert config.stage_wise.moving_interface is True
        assert config.stage_wise.adsorption_kinetics is False
        assert config.stage_wise.backflow is True

        # Test regime thresholds
        assert config.stage_wise.ca_dripping_limit == 0.3
        assert config.stage_wise.Pj_normal_min_mbar == 50.0

    def test_backward_compatibility(self):
        """Test that existing configs still work without stage_wise section"""
        config = load_config("configs/test_device.yaml")  # Existing config

        # Should have default stage_wise config
        assert hasattr(config, 'stage_wise')
        assert config.stage_wise.enabled is True  # Default value


class TestDiagnostics:
    """Test diagnostic output and debugging features"""

    def test_diagnostic_output_structure(self):
        """Test that diagnostic output has expected structure"""
        config = load_config("configs/example_stage_wise.yaml")

        result = stage_wise_solve(config, Po_in_mbar=200.0, Qw_in_mlhr=5.0)

        diagnostics = result.diagnostics

        # Check required diagnostic sections
        assert hasattr(diagnostics, 'pressure_uniformity')
        assert hasattr(diagnostics, 'grouping_triggered')
        assert hasattr(diagnostics, 'stage_timings')
        assert hasattr(diagnostics, 'regime_diagnostics')

        # Check stage timing breakdown
        assert 'stage1_displacement' in diagnostics.stage_timings
        assert 'stage2_growth' in diagnostics.stage_timings
        assert 'total_cycle' in diagnostics.stage_timings

    def test_regime_classification_output(self):
        """Test regime classification in diagnostics"""
        config = load_config("configs/example_stage_wise.yaml")

        result = stage_wise_solve(config, Po_in_mbar=200.0, Qw_in_mlhr=5.0)

        # Check that regime classification is present for each group
        for group_result in result.group_results:
            assert isinstance(group_result.regime, RegimeClassification)
            assert group_result.confidence_level in ["high", "medium", "low"]
            assert isinstance(group_result.warnings, list)


if __name__ == "__main__":
    pytest.main([__file__])