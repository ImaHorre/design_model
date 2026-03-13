# Stage-Wise Model v2 Planning Document

**Date**: March 12, 2026
**Current Version**: v1 (Stage-Wise Physics)
**Planned Version**: v2 (Physics-First Architecture)
**Implementation Strategy**: New branch or versioned module within existing branch

## Executive Summary

Version 2 addresses the key physics limitations identified in the review while preserving the strong architectural foundation of v1. The focus shifts from calibrated corrections to competing physical mechanisms, with improved necking physics and enhanced regime detection.

## Core Philosophy Shift

**v1 Approach**: Structured surrogate with calibrated corrections
**v2 Approach**: Physics-first with competing mechanism selection

```python
# v1: Blended corrections
corrections = CorrectionFactors(
    interface_resistance=2.8 * calibrated_factor,
    adsorption_delay=fitted_delay,
    backflow_effect=1.9 * empirical_multiplier
)

# v2: Competing mechanisms
dominant_mechanism = select_dominant_physics(flow_conditions, geometry, fluids)
stage1_result = solve_mechanism_specific_physics(dominant_mechanism, ...)
```

## Major Changes Overview

### 1. Stage 1: Competing Mechanism Architecture
- **Replace**: Single blended correction model
- **With**: Branched physics mechanisms with auto-selection
- **Benefit**: Physics-based transferability across conditions

### 2. Stage 2: Corrected Necking Physics
- **Replace**: Dispersed-phase viscosity scaling
- **With**: Outer-phase viscosity + interfacial tension scaling
- **Benefit**: Literature-consistent necking time predictions

### 3. Regime Detection: Multi-Factor Classification
- **Replace**: Single Ca threshold
- **With**: Sequential validation with design feedback
- **Benefit**: Better regime boundaries + actionable guidance

### 4. Design-Oriented Diagnostics
- **Replace**: Model debugging diagnostics
- **With**: Device design guidance and optimization suggestions
- **Benefit**: Useful for experimental design, not just validation

---

## Section 1: Stage 1 Competing Mechanism Architecture

### Current Problem (from review)
Stage 1 uses calibrated correction factors that may not transfer across different geometries, fluid systems, or surfactant conditions.

### Solution: Physics-Based Mechanism Selection

```python
class Stage1Mechanism(enum.Enum):
    HYDRAULIC_DOMINATED = "hydraulic"          # Pure flow resistance
    INTERFACE_DOMINATED = "interface"          # Contact line effects
    ADSORPTION_DOMINATED = "adsorption"        # Surfactant kinetics
    BACKFLOW_DOMINATED = "backflow"            # Water displacement resistance

def select_dominant_stage1_mechanism(
    P_j: float,
    Q_nominal: float,
    config: "DeviceConfig"
) -> Stage1Mechanism:
    """
    Physics-based mechanism selection using dimensionless numbers
    """

    # Calculate characteristic numbers
    ca = calculate_capillary_number(Q_nominal, config)
    pe_ads = calculate_peclet_adsorption(config)
    pressure_ratio = P_j / reference_pressure

    # Mechanism selection logic
    if pe_ads < 1.0 and config.fluids.surfactant_concentration > threshold:
        return Stage1Mechanism.ADSORPTION_DOMINATED

    elif ca > contact_line_threshold:
        return Stage1Mechanism.INTERFACE_DOMINATED

    elif pressure_ratio > backflow_threshold:
        return Stage1Mechanism.BACKFLOW_DOMINATED

    else:
        return Stage1Mechanism.HYDRAULIC_DOMINATED
```

### Mechanism-Specific Physics

**1. Hydraulic-Dominated (baseline)**:
```python
def solve_hydraulic_dominated_stage1(P_j, Q_nominal, config):
    """Pure Poiseuille flow resistance"""
    reset_distance = config.geometry.junction.exit_width
    hydraulic_velocity = Q_nominal / channel_area
    t_displacement = reset_distance / hydraulic_velocity

    return Stage1Result(
        t_displacement=t_displacement,
        mechanism="hydraulic",
        confidence=1.0,
        diagnostics={"pure_flow": True}
    )
```

**2. Interface-Dominated (high Ca)**:
```python
def solve_interface_dominated_stage1(P_j, Q_nominal, config):
    """Contact line resistance from moving interface"""
    ca = calculate_capillary_number(Q_nominal, config)

    # Cox-Voinov law for dynamic contact angle
    theta_dynamic = theta_equilibrium + f(ca)  # Literature-based

    # Interface resistance from contact line pinning
    R_interface = calculate_contact_line_resistance(theta_dynamic, geometry)

    # Modified flow equation
    Q_effective = Q_nominal * interface_efficiency(R_interface)
    t_displacement = reset_distance / Q_effective

    return Stage1Result(
        t_displacement=t_displacement,
        mechanism="interface",
        confidence=confidence_from_ca_regime(ca),
        diagnostics={"ca": ca, "theta_dynamic": theta_dynamic}
    )
```

**3. Adsorption-Dominated (surfactant systems)**:
```python
def solve_adsorption_dominated_stage1(P_j, Q_nominal, config):
    """Surfactant adsorption kinetics"""
    pe_ads = calculate_peclet_adsorption(config)

    # Ward-Tordai adsorption model
    adsorption_time = calculate_ward_tordai_time(pe_ads, config)

    # Interface stall during adsorption
    t_displacement_base = reset_distance / Q_nominal
    t_displacement = t_displacement_base + adsorption_time

    return Stage1Result(
        t_displacement=t_displacement,
        mechanism="adsorption",
        confidence=confidence_from_pe_regime(pe_ads),
        diagnostics={"pe_ads": pe_ads, "adsorption_time_ms": adsorption_time*1000}
    )
```

**4. Backflow-Dominated (high pressure)**:
```python
def solve_backflow_dominated_stage1(P_j, Q_nominal, config):
    """Water backflow resistance effects"""
    pressure_ratio = P_j / reference_pressure

    # Backflow velocity from pressure gradient
    backflow_velocity = calculate_backflow_velocity(P_j, config)

    # Effective displacement velocity
    net_velocity = Q_nominal / channel_area - backflow_velocity
    t_displacement = reset_distance / net_velocity

    return Stage1Result(
        t_displacement=t_displacement,
        mechanism="backflow",
        confidence=confidence_from_pressure_regime(pressure_ratio),
        diagnostics={"backflow_velocity": backflow_velocity, "pressure_ratio": pressure_ratio}
    )
```

### Mechanism Selection Validation

```python
def validate_mechanism_selection(selected_mechanism, P_j, Q_nominal, config):
    """
    Cross-check mechanism selection with alternative indicators
    """

    # Calculate all mechanisms
    mechanisms = {
        Stage1Mechanism.HYDRAULIC_DOMINATED: solve_hydraulic_dominated_stage1(P_j, Q_nominal, config),
        Stage1Mechanism.INTERFACE_DOMINATED: solve_interface_dominated_stage1(P_j, Q_nominal, config),
        Stage1Mechanism.ADSORPTION_DOMINATED: solve_adsorption_dominated_stage1(P_j, Q_nominal, config),
        Stage1Mechanism.BACKFLOW_DOMINATED: solve_backflow_dominated_stage1(P_j, Q_nominal, config)
    }

    # Compare predictions and confidences
    selected_result = mechanisms[selected_mechanism]

    validation = {
        "selected_mechanism": selected_mechanism,
        "mechanism_confidence": selected_result.confidence,
        "alternative_predictions": {k.value: v.t_displacement for k, v in mechanisms.items()},
        "prediction_spread": calculate_prediction_spread(mechanisms),
        "selection_margin": calculate_selection_margin(mechanisms, selected_mechanism)
    }

    return selected_result, validation
```

---

## Section 2: Corrected Necking Physics

### Current Problem (from review)
The necking time law currently uses dispersed-phase viscosity, but literature suggests outer-phase viscosity dominates.

### Solution: Outer-Phase Viscosity Scaling

```python
def calculate_necking_time_v2(config: "DeviceConfig") -> tuple[float, dict]:
    """
    v2: Outer-phase viscosity + interfacial tension scaling
    Based on Eggers & Villermaux (Rep. Prog. Phys. 2008)
    """

    # Use outer phase (water) viscosity - CORRECTED
    mu_outer = config.fluids.mu_continuous  # Water viscosity
    mu_inner = config.fluids.mu_dispersed   # Oil viscosity
    gamma = config.fluids.gamma             # Interfacial tension
    rho_outer = config.fluids.rho_continuous

    # Characteristic neck radius
    R_neck = config.geometry.junction.exit_width / 4

    # Viscosity ratio effects
    lambda_visc = mu_inner / mu_outer

    # Ohnesorge number based on outer phase - CORRECTED
    Oh_outer = mu_outer / sqrt(rho_outer * gamma * R_neck)

    # Necking time scaling
    if Oh_outer < 0.1:  # Inertial regime
        # Rayleigh-Plateau time with viscosity ratio correction
        tau_inertial = sqrt(rho_outer * R_neck**3 / gamma)
        tau_necking = tau_inertial * viscosity_ratio_correction_inertial(lambda_visc)
        regime = "inertial"

    else:  # Viscous regime
        # Viscous necking with outer phase viscosity - CORRECTED
        tau_viscous = mu_outer * R_neck / gamma  # NOT mu_dispersed
        tau_necking = tau_viscous * viscosity_ratio_correction_viscous(lambda_visc)
        regime = "viscous"

    diagnostics = {
        "Oh_outer": Oh_outer,
        "lambda_visc": lambda_visc,
        "regime": regime,
        "neck_radius_um": R_neck * 1e6,
        "scaling_basis": "outer_phase_viscosity"  # v2 identifier
    }

    return tau_necking, diagnostics

def viscosity_ratio_correction_inertial(lambda_visc: float) -> float:
    """
    Viscosity ratio correction for inertial necking
    From Stone & Leal (1989), Lister & Stone (1998)
    """
    # For lambda << 1 (low viscosity droplet): minimal effect
    # For lambda >> 1 (high viscosity droplet): significant slowdown
    return 1.0 + 0.5 * lambda_visc**0.3

def viscosity_ratio_correction_viscous(lambda_visc: float) -> float:
    """
    Viscosity ratio correction for viscous necking
    From Cohen & Nagel (2001), Papageorgiou (1995)
    """
    # Stronger dependence in viscous regime
    return (1.0 + lambda_visc)**0.6
```

### Literature Validation Framework

```python
def validate_necking_physics(config: "DeviceConfig") -> dict:
    """
    Compare v1 vs v2 necking predictions with literature bounds
    """

    # v1 prediction (dispersed-phase based)
    tau_v1, diag_v1 = calculate_necking_time_v1(config)

    # v2 prediction (outer-phase based)
    tau_v2, diag_v2 = calculate_necking_time_v2(config)

    # Literature bounds (from experimental correlations)
    tau_eggers = estimate_eggers_correlation(config)
    tau_stone = estimate_stone_correlation(config)
    tau_literature_range = (min(tau_eggers, tau_stone), max(tau_eggers, tau_stone))

    validation = {
        "tau_v1_ms": tau_v1 * 1000,
        "tau_v2_ms": tau_v2 * 1000,
        "tau_literature_range_ms": [t*1000 for t in tau_literature_range],
        "v1_within_literature": tau_literature_range[0] <= tau_v1 <= tau_literature_range[1],
        "v2_within_literature": tau_literature_range[0] <= tau_v2 <= tau_literature_range[1],
        "improvement_factor": abs(tau_v2 - tau_eggers) / abs(tau_v1 - tau_eggers),
        "physics_basis": {
            "v1": "dispersed_phase_viscosity",
            "v2": "outer_phase_viscosity_with_ratio_correction"
        }
    }

    return validation
```

---

## Section 3: Multi-Factor Regime Classification

### Current Problem (from review)
Single Ca threshold is too simple. Needs pressure balance checks, flow capacity validation, and inertial effects.

### Solution: Sequential Validation Framework

```python
def classify_regime_v2(P_j: float, Q_avg: float, config: "DeviceConfig") -> tuple[RegimeClassification, dict]:
    """
    v2: Multi-factor regime classification with design feedback
    """

    # Primary screening: Capillary number
    ca = calculate_capillary_number(Q_avg, config)
    primary_regime = get_primary_regime_from_ca(ca, config)

    # Secondary validation checks
    pressure_check = validate_pressure_balance(P_j, config)
    flow_check = validate_flow_capacity_balance(Q_avg, config)
    inertial_check = validate_inertial_effects(Q_avg, config)

    # Regime refinement based on secondary checks
    final_regime, confidence = refine_regime_classification(
        primary_regime, pressure_check, flow_check, inertial_check
    )

    # Design feedback generation
    design_feedback = generate_design_feedback(
        final_regime, pressure_check, flow_check, inertial_check, config
    )

    diagnostics = {
        "primary_regime": primary_regime.value,
        "final_regime": final_regime.value,
        "confidence": confidence,
        "capillary_number": ca,
        "validation_checks": {
            "pressure": pressure_check,
            "flow_capacity": flow_check,
            "inertial": inertial_check
        },
        "design_feedback": design_feedback
    }

    return final_regime, diagnostics

def validate_pressure_balance(P_j: float, config: "DeviceConfig") -> dict:
    """
    Pressure balance validation for regime stability
    """

    # Laplace pressure for critical droplet
    R_critical = calculate_critical_radius(config)
    P_laplace = 2 * config.fluids.gamma / R_critical

    # Dynamic pressure from flow
    rho = config.fluids.rho_continuous
    v_channel = estimate_channel_velocity(config)
    P_dynamic = 0.5 * rho * v_channel**2

    # Pressure ratios
    laplace_ratio = P_laplace / P_j
    dynamic_ratio = P_dynamic / P_j

    # Stability assessment
    if laplace_ratio > 2.0:
        stability = "laplace_dominated"  # Stable droplet formation
    elif dynamic_ratio > 0.5:
        stability = "flow_dominated"     # Risk of jetting
    else:
        stability = "balanced"           # Normal operation

    return {
        "P_j_mbar": P_j / 100,
        "P_laplace_mbar": P_laplace / 100,
        "P_dynamic_mbar": P_dynamic / 100,
        "laplace_ratio": laplace_ratio,
        "dynamic_ratio": dynamic_ratio,
        "stability": stability
    }

def validate_flow_capacity_balance(Q_avg: float, config: "DeviceConfig") -> dict:
    """
    Flow rate vs droplet formation capacity validation
    """

    # Estimate maximum droplet formation rate
    tau_necking = calculate_necking_time_v2(config)[0]
    f_max = 1.0 / (tau_necking * formation_overhead_factor)

    # Estimate required flow rate for current conditions
    V_droplet = estimate_droplet_volume(config)
    Q_required = f_max * V_droplet

    # Capacity analysis
    flow_ratio = Q_avg / Q_required

    if flow_ratio > 1.5:
        capacity_status = "flow_exceeds_capacity"
        risk = "transitional_oversized"
    elif flow_ratio > 1.2:
        capacity_status = "near_capacity_limit"
        risk = "transitional"
    else:
        capacity_status = "within_capacity"
        risk = "none"

    return {
        "Q_avg_mlhr": Q_avg * 3.6e9,  # m³/s to mL/hr
        "Q_required_mlhr": Q_required * 3.6e9,
        "f_max_hz": f_max,
        "flow_ratio": flow_ratio,
        "capacity_status": capacity_status,
        "risk": risk
    }

def validate_inertial_effects(Q_avg: float, config: "DeviceConfig") -> dict:
    """
    Weber number and Reynolds number validation
    """

    # Weber number (inertial vs surface tension)
    rho = config.fluids.rho_dispersed
    v_exit = Q_avg / (config.geometry.junction.exit_width * config.geometry.junction.exit_depth)
    L_char = config.geometry.junction.exit_width
    gamma = config.fluids.gamma

    We = rho * v_exit**2 * L_char / gamma

    # Reynolds number (inertial vs viscous)
    mu = config.fluids.mu_dispersed
    Re = rho * v_exit * L_char / mu

    # Inertial regime assessment
    if We > 1.0:
        inertial_regime = "weber_dominated"
        risk = "jetting"
    elif Re > 100:
        inertial_regime = "reynolds_dominated"
        risk = "transitional"
    else:
        inertial_regime = "viscous_dominated"
        risk = "none"

    return {
        "weber_number": We,
        "reynolds_number": Re,
        "exit_velocity_m_s": v_exit,
        "inertial_regime": inertial_regime,
        "risk": risk
    }
```

### Design Feedback Generation

```python
def generate_design_feedback(
    regime: RegimeClassification,
    pressure_check: dict,
    flow_check: dict,
    inertial_check: dict,
    config: "DeviceConfig"
) -> dict:
    """
    Actionable design guidance based on regime analysis
    """

    feedback = {
        "current_regime": regime.value,
        "recommendations": [],
        "quantitative_suggestions": {},
        "risk_mitigation": []
    }

    # Pressure-based recommendations
    if pressure_check["stability"] == "flow_dominated":
        feedback["recommendations"].append("increase_microchannel_resistance")
        feedback["quantitative_suggestions"]["channel_length_multiplier"] = 2.0

    elif pressure_check["stability"] == "laplace_dominated":
        feedback["recommendations"].append("reduce_surface_tension")
        feedback["quantitative_suggestions"]["surfactant_concentration_increase"] = 0.5

    # Flow capacity recommendations
    if flow_check["capacity_status"] == "flow_exceeds_capacity":
        feedback["recommendations"].append("reduce_flow_rate_or_increase_channels")
        feedback["quantitative_suggestions"]["flow_reduction_factor"] = 0.7
        feedback["quantitative_suggestions"]["parallel_channels"] = 2

    # Inertial effect recommendations
    if inertial_check["risk"] == "jetting":
        feedback["recommendations"].append("modify_junction_geometry")
        feedback["quantitative_suggestions"]["exit_width_reduction_factor"] = 0.8
        feedback["risk_mitigation"].append("add_expansion_chamber")

    # Regime-specific suggestions
    if regime == RegimeClassification.TRANSITIONAL:
        feedback["recommendations"].append("optimize_for_stable_dripping")
        feedback["risk_mitigation"].append("monitor_flow_rate_stability")

    return feedback
```

---

## Section 4: Design-Oriented Diagnostics

### Current Problem
v1 diagnostics focus on model debugging rather than device design guidance.

### Solution: Device Design Assistant

```python
@dataclass(frozen=True)
class DesignOptimizationReport:
    """Device design guidance from physics analysis"""

    # Current performance assessment
    regime_stability: dict                    # Margin from regime boundaries
    performance_metrics: dict                 # Droplet size/frequency predictions

    # Optimization opportunities
    geometry_suggestions: dict                # Junction, channel modifications
    operating_suggestions: dict               # Pressure, flow rate adjustments
    fluid_suggestions: dict                   # Viscosity, surface tension optimization

    # Sensitivity analysis
    parameter_sensitivities: dict             # ∂(performance)/∂(parameter)
    robust_operating_window: dict             # Safe operating ranges

    # Risk assessment
    failure_mode_analysis: dict               # What could go wrong
    monitoring_recommendations: dict          # What to measure during operation

def generate_design_optimization_report(
    stage_wise_result: StageWiseResult,
    config: "DeviceConfig"
) -> DesignOptimizationReport:
    """
    Generate actionable device design guidance
    """

    # Regime stability analysis
    regime_stability = analyze_regime_stability_margins(stage_wise_result, config)

    # Performance optimization
    geometry_suggestions = suggest_geometry_optimizations(stage_wise_result, config)
    operating_suggestions = suggest_operating_optimizations(stage_wise_result, config)
    fluid_suggestions = suggest_fluid_optimizations(stage_wise_result, config)

    # Sensitivity analysis
    sensitivities = calculate_parameter_sensitivities(config)
    operating_window = calculate_robust_operating_window(config)

    # Risk analysis
    failure_modes = analyze_failure_modes(stage_wise_result, config)
    monitoring = recommend_monitoring_strategy(stage_wise_result, config)

    return DesignOptimizationReport(
        regime_stability=regime_stability,
        performance_metrics=extract_performance_metrics(stage_wise_result),
        geometry_suggestions=geometry_suggestions,
        operating_suggestions=operating_suggestions,
        fluid_suggestions=fluid_suggestions,
        parameter_sensitivities=sensitivities,
        robust_operating_window=operating_window,
        failure_mode_analysis=failure_modes,
        monitoring_recommendations=monitoring
    )

def suggest_geometry_optimizations(result: StageWiseResult, config: "DeviceConfig") -> dict:
    """
    Geometry modification suggestions based on physics analysis
    """

    suggestions = {}

    # Junction geometry
    if result.regime_classification == RegimeClassification.JETTING:
        suggestions["junction_exit_width"] = {
            "current_um": config.geometry.junction.exit_width * 1e6,
            "suggested_um": config.geometry.junction.exit_width * 0.8 * 1e6,
            "reason": "reduce_weber_number_for_dripping_regime",
            "expected_improvement": "Ca reduction by factor 0.64"
        }

    # Channel resistance
    if result.pressure_uniformity["requires_grouping"]:
        suggestions["channel_length"] = {
            "current_mm": config.geometry.channels.length * 1000,
            "suggested_mm": config.geometry.channels.length * 1.5 * 1000,
            "reason": "improve_pressure_uniformity",
            "expected_improvement": "CV reduction from {} to {}".format(
                result.pressure_uniformity["cv_pressure"],
                result.pressure_uniformity["cv_pressure"] * 0.67
            )
        }

    # Droplet size optimization
    if result.D_pred > target_droplet_size * 1.2:
        critical_radius_current = calculate_critical_radius(config)
        suggestions["junction_geometry_ratio"] = {
            "current_aspect_ratio": config.geometry.junction.exit_width / config.geometry.junction.exit_depth,
            "suggested_aspect_ratio": 1.5,
            "reason": "reduce_critical_droplet_size",
            "expected_size_reduction_um": (critical_radius_current - critical_radius_suggested) * 2e6
        }

    return suggestions

def calculate_parameter_sensitivities(config: "DeviceConfig") -> dict:
    """
    Numerical sensitivity analysis for key parameters
    """

    # Base case
    base_result = stage_wise_solve(config)
    base_frequency = base_result.f_pred
    base_size = base_result.D_pred

    sensitivities = {}

    # Test parameter variations
    test_parameters = {
        "Po_in_mbar": [0.9, 1.1],           # ±10% pressure
        "Qw_in_mlhr": [0.9, 1.1],           # ±10% flow rate
        "exit_width": [0.95, 1.05],         # ±5% geometry
        "surface_tension": [0.9, 1.1],      # ±10% fluid properties
        "viscosity_ratio": [0.8, 1.2]       # ±20% viscosity
    }

    for param_name, factors in test_parameters.items():
        config_modified = modify_parameter(config, param_name, factors)

        results_modified = [stage_wise_solve(cfg) for cfg in config_modified]

        # Calculate sensitivity: d(output)/d(input)
        d_frequency = [(r.f_pred - base_frequency)/base_frequency for r in results_modified]
        d_size = [(r.D_pred - base_size)/base_size for r in results_modified]

        sensitivities[param_name] = {
            "frequency_sensitivity": np.mean(np.abs(d_frequency)) / 0.1,  # Normalized
            "size_sensitivity": np.mean(np.abs(d_size)) / 0.1,
            "coupling": calculate_parameter_coupling(param_name, results_modified)
        }

    return sensitivities
```

---

## Section 5: Implementation Strategy

### Option A: New Branch Development

**Branch Structure**:
```
stage_wise_v2/
├── stepgen/models/stage_wise_v2.py        # New physics implementation
├── stepgen/models/mechanism_selection.py  # Stage 1 competing mechanisms
├── stepgen/models/necking_physics_v2.py   # Corrected necking models
├── stepgen/models/regime_classifier_v2.py # Multi-factor regime detection
├── stepgen/models/design_optimizer.py     # Design guidance system
└── tests/test_stage_wise_v2.py           # Comprehensive test suite
```

**Benefits**:
- Safe parallel development
- Easy comparison with v1
- Can merge when stable

**Integration Path**:
```python
# CLI support for both versions
stepgen simulate config.yaml --model stage_wise_v1
stepgen simulate config.yaml --model stage_wise_v2

# Comparison mode
stepgen compare config.yaml --models stage_wise_v1,stage_wise_v2
```

### Option B: Versioned Module Within Existing Branch

**Module Structure**:
```python
# stepgen/models/stage_wise.py
class StageWiseModel:
    def __init__(self, version="v2"):
        if version == "v1":
            self.physics = StageWisePhysicsV1()
        elif version == "v2":
            self.physics = StageWisePhysicsV2()
        else:
            raise ValueError(f"Unknown version: {version}")

# Configuration support
stage_wise:
  version: "v2"                    # v1 or v2
  v2_options:
    mechanism_selection: "auto"    # auto, manual, hybrid
    necking_model: "outer_phase"   # outer_phase, literature_blend
    regime_classifier: "multi_factor"  # multi_factor, ca_only
```

### Development Phases

**Phase 1: Core Physics (2-3 weeks)**
- [ ] Implement competing mechanism selection for Stage 1
- [ ] Correct necking physics to outer-phase viscosity scaling
- [ ] Basic multi-factor regime classification
- [ ] Unit tests for all new physics modules

**Phase 2: Integration & Validation (2 weeks)**
- [ ] Integrate with existing hydraulic backbone
- [ ] CLI support and configuration system
- [ ] Compare v1 vs v2 predictions on test cases
- [ ] Validate against literature benchmarks

**Phase 3: Design Optimization (2 weeks)**
- [ ] Design guidance system implementation
- [ ] Sensitivity analysis framework
- [ ] Failure mode analysis
- [ ] Comprehensive diagnostics output

**Phase 4: Testing & Documentation (1 week)**
- [ ] Experimental validation testing
- [ ] Performance benchmarking
- [ ] Documentation and examples
- [ ] Integration with existing workflows

### Validation Strategy

**Physics Validation**:
- Compare necking predictions with Eggers & Villermaux literature
- Validate mechanism selection with experimental regime maps
- Cross-check regime boundaries with published Ca thresholds

**Performance Validation**:
- Benchmark against v1 on existing test cases
- Measure improvement in RMSE for droplet size/frequency
- Validate computational performance (should be comparable)

**Design Validation**:
- Test design suggestions on known problematic geometries
- Validate sensitivity predictions with experimental parameter sweeps
- Check regime stability predictions with experimental data

---

## Section 6: Expected Improvements

### Physics Accuracy
- **Necking Time**: 30-50% improvement in necking time predictions
- **Transfer**: Better prediction across different fluid systems
- **Regime Boundaries**: More accurate transitional region detection

### Design Utility
- **Actionable Feedback**: Specific geometry/operating suggestions
- **Risk Assessment**: Failure mode prediction and mitigation
- **Optimization**: Automated design space exploration

### Model Transparency
- **Mechanism Selection**: Clear physics basis for predictions
- **Uncertainty**: Confidence intervals and prediction limits
- **Validation**: Built-in experimental comparison framework

### Example Improvement Case

**Scenario**: High viscosity oil droplets (μ_oil = 100 mPa·s)

**v1 Prediction**:
```
Necking time: 15.3 ms (dispersed-phase scaling)
Regime: DRIPPING (Ca = 0.25)
Confidence: Medium
Design guidance: None
```

**v2 Prediction**:
```
Mechanism: INTERFACE_DOMINATED (Ca = 0.25, high contact line resistance)
Necking time: 8.7 ms (outer-phase scaling with λ_visc = 112 correction)
Regime: DRIPPING (Ca + pressure + flow validation)
Confidence: High (mechanism selection margin: 0.4)
Design guidance:
  - Consider exit_width reduction to 12 μm (improve Ca margin)
  - Monitor contact angle for interface effects
  - Safe operating window: Po = 250-350 mbar, Qw = 1.2-1.8 mL/hr
```

---

## Section 7: Risk Assessment & Mitigation

### Development Risks

**Risk**: Increased model complexity reduces adoption
**Mitigation**: Provide simple default configuration that works out-of-box

**Risk**: v2 predictions worse than v1 in some cases
**Mitigation**: Extensive validation suite, ability to fall back to v1

**Risk**: Performance degradation from multiple mechanism evaluation
**Mitigation**: Cache mechanism selection, optimize critical paths

### Physics Risks

**Risk**: Mechanism selection logic is still too empirical
**Mitigation**: Extensive literature validation, experimental tuning

**Risk**: Multi-factor regime detection over-complicates simple cases
**Mitigation**: Graceful degradation to single-factor when appropriate

**Risk**: Design suggestions are not experimentally achievable
**Mitigation**: Validate suggestions against fabrication constraints

### Integration Risks

**Risk**: Breaking changes to existing workflow
**Mitigation**: Maintain API compatibility, provide migration tools

**Risk**: Configuration complexity increases support burden
**Mitigation**: Intelligent defaults, validation, clear error messages

---

## Conclusion

Version 2 represents a fundamental shift from calibrated corrections to competing physical mechanisms, addressing the key weaknesses identified in the review while preserving the strong architectural foundation of v1. The focus on physics-first design and actionable device guidance makes this a genuine advancement rather than incremental improvement.

**Key Value Propositions**:
1. **Physics Validity**: Mechanism-based selection improves transferability
2. **Literature Consistency**: Corrected necking physics aligns with established theory
3. **Design Utility**: Actionable optimization guidance beyond just prediction
4. **Model Transparency**: Clear physics basis and confidence assessment

**Implementation Priority**: Option B (versioned module) recommended for faster iteration and easier validation against v1.

**Timeline**: 7-8 weeks for full implementation with comprehensive validation.

**Success Metrics**:
- 30% improvement in prediction accuracy across diverse conditions
- Successful design optimization for 3+ experimental test cases
- Physics predictions within 20% of literature benchmarks
- No performance degradation compared to v1