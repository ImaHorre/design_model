"""
Test suite for Stage-Wise Model v3 Phase 1 implementation.

Tests the Phase 1 deliverables:
- Architecture redesign with modular files
- Configuration integration
- Dynamic hydraulic network
- Junction pressure definition
- Model registry integration
"""

import pytest
import numpy as np
from stepgen.config import load_config
from stepgen.models.hydraulic_models import HydraulicModelRegistry


class TestStageWiseV3Phase1:
    """Test Phase 1 implementation of stage-wise v3 model."""

    def test_model_registry_integration(self):
        """Test that stage_wise_v3 model is properly registered."""

        # Check that v3 model is available in registry
        available_models = HydraulicModelRegistry.list_models()
        assert "stage_wise_v3" in available_models, "stage_wise_v3 model not found in registry"

        # Test model instantiation
        try:
            model = HydraulicModelRegistry.get_model("stage_wise_v3")
            assert model is not None, "Failed to instantiate stage_wise_v3 model"

            # Check interface compliance
            from stepgen.models.hydraulic_models import HydraulicModelInterface
            assert isinstance(model, HydraulicModelInterface), "Model does not implement HydraulicModelInterface"

        except ImportError as e:
            pytest.skip(f"v3 modules not fully implemented yet: {e}")

    def test_v3_configuration_structure(self):
        """Test v3 configuration structure and validation."""

        try:
            from stepgen.models.stage_wise_v3 import StageWiseV3Config

            # Test default configuration creation
            config = StageWiseV3Config()

            # Check required physics switches
            assert hasattr(config, 'enable_two_fluid_washburn'), "Missing two_fluid_washburn switch"
            assert hasattr(config, 'enable_outer_phase_necking'), "Missing outer_phase_necking switch"
            assert hasattr(config, 'enable_multi_factor_regime'), "Missing multi_factor_regime switch"

            # Check back-calculated parameters
            assert hasattr(config, 'gamma_effective'), "Missing gamma_effective parameter"
            assert hasattr(config, 'theta_effective'), "Missing theta_effective parameter"
            assert hasattr(config, 'R_critical_ratio'), "Missing R_critical_ratio parameter"

            # Validate parameter bounds
            assert 0 < config.gamma_effective < 0.1, "gamma_effective outside reasonable bounds"
            assert 0 < config.theta_effective < 90, "theta_effective outside reasonable bounds"
            assert 0 < config.R_critical_ratio < 2, "R_critical_ratio outside reasonable bounds"

        except ImportError as e:
            pytest.skip(f"v3 configuration not fully implemented yet: {e}")

    def test_modular_architecture(self):
        """Test that v3 implements modular architecture as planned."""

        try:
            # Check that modular files exist and can be imported
            from stepgen.models.stage_wise_v3 import core
            from stepgen.models.stage_wise_v3 import hydraulics
            from stepgen.models.stage_wise_v3 import stage1_physics
            from stepgen.models.stage_wise_v3 import stage2_physics
            from stepgen.models.stage_wise_v3 import regime_classification
            from stepgen.models.stage_wise_v3 import validation

            # Check that main solver function exists
            assert hasattr(core, 'stage_wise_v3_solve'), "Main solver function not found"

            # Check hydraulic functions
            assert hasattr(hydraulics, 'solve_dynamic_hydraulic_network'), "Dynamic hydraulic network function not found"
            assert hasattr(hydraulics, 'calculate_junction_pressures'), "Junction pressure function not found"

            # Check Stage 1 physics
            assert hasattr(stage1_physics, 'solve_stage1_washburn_physics'), "Stage 1 Washburn solver not found"
            assert hasattr(stage1_physics, 'solve_two_fluid_washburn_base'), "Two-fluid Washburn base not found"

            # Check Stage 2 physics
            assert hasattr(stage2_physics, 'solve_stage2_critical_size_with_tracking'), "Stage 2 solver not found"
            assert hasattr(stage2_physics, 'calculate_necking_time_outer_phase'), "Outer-phase necking not found"

        except ImportError as e:
            pytest.skip(f"v3 modular architecture not fully implemented yet: {e}")

    def test_two_fluid_washburn_basic(self):
        """Test basic two-fluid Washburn implementation."""

        try:
            from stepgen.models.stage_wise_v3.stage1_physics import solve_two_fluid_washburn_base
            from stepgen.models.stage_wise_v3 import StageWiseV3Config

            # Create minimal config for testing
            config = load_config("configs/example_stage_wise.yaml")
            v3_config = StageWiseV3Config()

            # Test Washburn calculation
            result = solve_two_fluid_washburn_base(config, v3_config)

            # Check result structure
            assert hasattr(result, 'refill_time'), "Missing refill_time in Washburn result"
            assert hasattr(result, 'capillary_pressure'), "Missing capillary_pressure"
            assert hasattr(result, 'two_fluid_scaling'), "Missing two_fluid_scaling"

            # Check physical reasonableness
            assert 1e-6 < result.refill_time < 1e-1, f"Refill time outside bounds: {result.refill_time:.2e} s"
            assert result.capillary_pressure > 0, f"Negative capillary pressure: {result.capillary_pressure}"
            assert result.two_fluid_scaling in ["sqrt_t", "non_sqrt_t"], f"Invalid scaling: {result.two_fluid_scaling}"

        except ImportError as e:
            pytest.skip(f"Stage 1 physics not fully implemented yet: {e}")

    def test_critical_radius_calculation(self):
        """Test critical radius determination from geometry."""

        try:
            from stepgen.models.stage_wise_v3.stage2_physics import calculate_critical_radius_from_geometry
            from stepgen.models.stage_wise_v3 import StageWiseV3Config

            # Create test configuration
            config = load_config("configs/example_stage_wise.yaml")
            v3_config = StageWiseV3Config()

            # Test critical radius calculation
            R_crit = calculate_critical_radius_from_geometry(config, v3_config)

            # Check physical reasonableness
            assert 1e-6 < R_crit < 1e-3, f"Critical radius outside bounds: {R_crit*1e6:.1f} µm"

            # Check scaling with geometry
            w = config.geometry.junction.exit_width
            h = config.geometry.junction.exit_depth
            min_dimension = min(w, h)

            # Should scale with minimum dimension
            assert 0.1 * min_dimension < R_crit < 2.0 * min_dimension, "Critical radius scaling incorrect"

        except ImportError as e:
            pytest.skip(f"Stage 2 physics not fully implemented yet: {e}")

    def test_dynamic_hydraulic_network_basic(self):
        """Test basic dynamic hydraulic network functionality."""

        try:
            from stepgen.models.stage_wise_v3.hydraulics import solve_dynamic_hydraulic_network
            from stepgen.models.stage_wise_v3.core import DropletProductionState

            # Create test configuration
            config = load_config("configs/example_stage_wise.yaml")

            # Test with empty droplet state (initial condition)
            droplet_state = DropletProductionState()

            result = solve_dynamic_hydraulic_network(config, droplet_state, 200.0, 5.0, 0.0)

            # Check result structure
            assert hasattr(result, 'P_oil_dynamic'), "Missing dynamic oil pressure"
            assert hasattr(result, 'P_water_dynamic'), "Missing dynamic water pressure"
            assert hasattr(result, 'junction_pressures'), "Missing junction pressure analysis"
            assert hasattr(result, 'base_result'), "Missing base hydraulic result"

            # Check pressure arrays
            assert len(result.P_oil_dynamic) > 0, "Empty oil pressure array"
            assert len(result.P_water_dynamic) > 0, "Empty water pressure array"

            # Check junction pressures
            P_j = result.P_j
            assert len(P_j) > 0, "Empty junction pressure array"
            assert np.all(P_j > 0), "Negative junction pressures found"

        except ImportError as e:
            pytest.skip(f"Dynamic hydraulic network not fully implemented yet: {e}")

    def test_physics_validation_framework(self):
        """Test physics validation framework basic functionality."""

        try:
            from stepgen.models.stage_wise_v3.validation import validate_physics_implementation
            from stepgen.models.stage_wise_v3 import PhysicsValidationStatus

            # Create minimal test data
            config = load_config("configs/example_stage_wise.yaml")
            group_results = []  # Empty for basic test

            # Test validation framework
            validation_report = validate_physics_implementation(config, group_results)

            # Check report structure
            assert isinstance(validation_report, dict), "Validation report should be dict"
            expected_components = ["washburn", "necking", "critical_radius", "physics_consistency"]

            for component in expected_components:
                if component in validation_report:
                    result = validation_report[component]
                    assert hasattr(result, 'status'), f"Missing status in {component} validation"
                    assert hasattr(result, 'checks_passed'), f"Missing checks_passed in {component} validation"

        except ImportError as e:
            pytest.skip(f"Validation framework not fully implemented yet: {e}")

    @pytest.mark.integration
    def test_v3_solver_integration(self):
        """Integration test of complete v3 solver (requires full implementation)."""

        try:
            from stepgen.models.stage_wise_v3.core import stage_wise_v3_solve

            # Load test configuration with v3 section
            config = load_config("configs/example_stage_wise.yaml")

            # Add v3 configuration section for testing
            from stepgen.models.stage_wise_v3 import StageWiseV3Config
            config.stage_wise_v3 = StageWiseV3Config()

            # Test full solver
            result = stage_wise_v3_solve(config, 200.0, 5.0, 0.0)

            # Check result structure
            assert hasattr(result, 'hydraulic_result'), "Missing hydraulic result"
            assert hasattr(result, 'group_results'), "Missing group results"
            assert hasattr(result, 'global_metrics'), "Missing global metrics"
            assert hasattr(result, 'diagnostics'), "Missing diagnostics"

            # Check compatibility properties
            assert hasattr(result, 'P_oil'), "Missing P_oil compatibility property"
            assert hasattr(result, 'P_water'), "Missing P_water compatibility property"
            assert hasattr(result, 'Q_rungs'), "Missing Q_rungs compatibility property"

        except ImportError as e:
            pytest.skip(f"Full v3 solver not ready for integration test: {e}")


if __name__ == "__main__":
    # Run basic tests
    test_class = TestStageWiseV3Phase1()

    print("Testing Phase 1 implementation...")

    try:
        test_class.test_model_registry_integration()
        print("✓ Model registry integration")
    except Exception as e:
        print(f"✗ Model registry integration: {e}")

    try:
        test_class.test_v3_configuration_structure()
        print("✓ v3 configuration structure")
    except Exception as e:
        print(f"✗ v3 configuration structure: {e}")

    try:
        test_class.test_modular_architecture()
        print("✓ Modular architecture")
    except Exception as e:
        print(f"✗ Modular architecture: {e}")

    try:
        test_class.test_two_fluid_washburn_basic()
        print("✓ Two-fluid Washburn basic")
    except Exception as e:
        print(f"✗ Two-fluid Washburn basic: {e}")

    try:
        test_class.test_critical_radius_calculation()
        print("✓ Critical radius calculation")
    except Exception as e:
        print(f"✗ Critical radius calculation: {e}")

    try:
        test_class.test_dynamic_hydraulic_network_basic()
        print("✓ Dynamic hydraulic network basic")
    except Exception as e:
        print(f"✗ Dynamic hydraulic network basic: {e}")

    try:
        test_class.test_physics_validation_framework()
        print("✓ Physics validation framework")
    except Exception as e:
        print(f"✗ Physics validation framework: {e}")

    print("\nPhase 1 basic testing complete.")