# Stage-Wise Model Implementation Design

**Date**: 2026-03-11
**Status**: Design Complete, Ready for Implementation
**Document**: Final design specification for new stage-wise droplet formation model

## Understanding Summary

• **Building**: A new stage-wise droplet formation model with three layers: (1) existing hydraulics backbone → (2) local droplet event law (Stage 1: confined displacement + Stage 2: bulb growth/necking) → (3) optional correction mechanisms for Stage 1 resistance

• **Why**: Current linear model fundamentally over-predicts Stage 1 flow rates due to "hidden resistance" mechanisms; need physics-based model that accurately represents observed stage timing and can predict device behavior

• **For**: Research team to design step-emulsification devices with reliable droplet frequency/size predictions and clear debugging of model-experiment mismatches

• **Key constraints**: Must integrate with existing config system, use same device YAML structure, build upon current hydraulics backbone; prioritize accuracy over speed

• **Non-goals**: No fallbacks to existing linear methods; not trying to optimize speed; not building general-purpose CFD

## Key Assumptions

• Reset distance ≈ exit_width (geometry-controlled, not flow-controlled)
• Stage 2 duration relatively constant for given geometry/fluids in normal regime
• P_j approximately constant across device (high upstream resistance assumption holds)
• Capillary number provides reliable regime detection with sequential validation
• Modular architecture allows adding Stage 1 correction mechanisms as research progresses

## Final Design Architecture

### Three-Layer Structure with Adaptive Grouping

```python
# stepgen/models/stage_wise.py

def stage_wise_solve(config, Po_in_mbar, Qw_in_mlhr) -> StageWiseResult:
    """Main entry point with adaptive rung grouping"""

    # Layer 1: Hydraulic Network (existing backbone)
    hydraulic_result = hydraulics.simulate(config, Po_in_mbar, Qw_in_mlhr)

    # Adaptive Grouping Decision
    pressure_variations = analyze_pressure_uniformity(hydraulic_result)
    if pressure_variations.requires_grouping:
        rung_groups = create_pressure_groups(hydraulic_result, target_groups=5-10)
    else:
        rung_groups = [UniformGroup(all_rungs)]  # Single group

    # Layer 2: Local Droplet Physics (per-group)
    stage_results = []
    for group in rung_groups:
        P_j_avg = group.average_pressures()
        group_stage_result = solve_local_droplet_physics(P_j_avg, config)
        stage_results.append(group_stage_result)

    # Layer 3: Optional Corrections & Regime Detection
    corrected_results = apply_stage1_corrections(stage_results, config)
    regime_info = classify_regimes(corrected_results, config)

    return StageWiseResult(...)
```

### Stage 1: Displacement Physics with Modular Corrections

```python
def solve_stage1_displacement(P_j, Q_nominal, config, corrections_enabled):
    """Stage 1: Meniscus displacement with optional resistance corrections"""

    # Base displacement time (if no corrections)
    reset_distance = config.geometry.junction.exit_width  # Experimental observation
    base_flow_rate = Q_nominal  # From hydraulic backbone
    t_displacement_base = reset_distance / base_flow_rate

    # Optional Correction Layer (modular)
    correction_factors = CorrectionFactors(
        interface_resistance=1.0,
        adsorption_delay=0.0,
        backflow_effect=1.0
    )

    if corrections_enabled.moving_interface:
        # Contact line resistance, dynamic contact angle effects
        ca_local = calculate_capillary_number(config, Q_nominal)
        correction_factors.interface_resistance = interface_resistance_model(ca_local, config)

    if corrections_enabled.adsorption_kinetics:
        # Surfactant adsorption causing temporary stall
        pe_ads = calculate_peclet_adsorption(config)
        correction_factors.adsorption_delay = adsorption_delay_model(pe_ads, config)

    if corrections_enabled.backflow:
        # Water backflow during displacement
        pressure_ratio = P_j / config.operating.Po_in_mbar
        correction_factors.backflow_effect = backflow_resistance_model(pressure_ratio, config)

    # Apply corrections
    t_displacement = (t_displacement_base * correction_factors.interface_resistance *
                     correction_factors.backflow_effect + correction_factors.adsorption_delay)

    return Stage1Result(t_displacement, correction_factors, diagnostics)
```

### Stage 2: Bulb Growth and Necking Physics

```python
def solve_stage2_growth(P_j, config):
    """Stage 2: Droplet bulb growth and necking - relatively constant timing"""

    # Geometry-controlled breakup condition (Dangla criterion)
    R_critical = calculate_critical_radius(config.geometry.junction)
    V_critical = (4/3) * np.pi * R_critical**3

    # Necking time model (fluid properties + geometry)
    tau_necking = necking_time_model(
        viscosity_ratio=config.fluids.mu_dispersed / config.fluids.mu_continuous,
        surface_tension=config.fluids.gamma,
        channel_width=config.geometry.junction.exit_width
    )

    # Bulb growth integration (simplified for constant P_j assumption)
    if config.stage_wise.use_detailed_growth:
        # Detailed: integrate dV/dt with evolving Laplace pressure
        t_growth = integrate_bulb_growth(P_j, R_critical, config)
        V_final = V_critical + inflation_correction(tau_necking, P_j, config)
    else:
        # Simplified: empirical fit to experimental stage timing
        t_growth = empirical_growth_time(config.fluids, config.geometry)
        V_final = geometry_dominated_volume(config) * (1 + small_pressure_correction(P_j))

    # Final droplet size
    D_droplet = (6 * V_final / np.pi)**(1/3)

    return Stage2Result(
        t_growth=t_growth,
        t_necking=tau_necking,
        D_droplet=D_droplet,
        regime_indicators=dict(
            pressure_driven=(P_j > threshold),
            geometry_dominated=(R_critical / channel_width > ratio_limit)
        )
    )
```

### Regime Detection: Sequential Validation

```python
def classify_regimes(stage_results, config):
    """Sequential validation: Ca primary + confidence checks"""

    regime_classifications = []

    for group_result in stage_results:
        # Primary Gate: Capillary Number
        ca = calculate_capillary_number(group_result.Q_avg, config)
        ca_regime = classify_ca_regime(ca, config.geometry.aspect_ratios)

        # Secondary Validation (only if Ca near threshold or transitional)
        confidence_level = "high"
        warnings = []

        if ca_regime in ["transitional", "near_threshold"]:
            # A) Flow rate vs Stage 2 capacity check
            flow_capacity_ratio = group_result.Q_avg / calculate_stage2_capacity(config)
            if flow_capacity_ratio > config.regime_thresholds.flow_ratio_limit:
                warnings.append("flow_exceeds_stage2_capacity")
                confidence_level = "medium"

            # B) Pressure balance check
            P_j = group_result.P_j_avg
            normal_range = config.regime_thresholds.Pj_normal_range
            if not (normal_range.min < P_j < normal_range.max):
                warnings.append("Pj_outside_normal_range")
                confidence_level = "low"

            # C) Growth rate mismatch check
            natural_growth_rate = estimate_natural_bulb_growth(config)
            supply_growth_rate = group_result.Q_avg / estimate_droplet_area(config)
            if supply_growth_rate > (2.0 * natural_growth_rate):
                warnings.append("growth_rate_mismatch")
                ca_regime = "transitional_oversized"  # Monodisperse-but-large regime

        regime_classifications.append(RegimeClassification(
            primary_regime=ca_regime,
            confidence=confidence_level,
            warnings=warnings,
            diagnostics=dict(ca=ca, P_j=P_j, flow_ratios=...)
        ))

    return regime_classifications
```

### Config System Extension

```python
@dataclass
class StageWiseConfig:
    """New section in device YAML files"""
    enabled: bool = True

    # Adaptive grouping
    pressure_uniformity_threshold: float = 0.05  # 5% P_j variation triggers grouping
    max_groups: int = 10

    # Stage 1 corrections (modular toggles)
    corrections: dict = field(default_factory=lambda: {
        "moving_interface": True,
        "adsorption_kinetics": False,  # Off by default, enable as needed
        "backflow": True
    })

    # Stage 2 physics
    use_detailed_growth: bool = False  # Start with simplified model
    necking_time_model: str = "viscocapillary"  # or "empirical"

    # Regime detection
    regime_thresholds: dict = field(default_factory=lambda: {
        "ca_dripping_limit": 0.3,  # Geometry-dependent, will be calibrated
        "flow_ratio_limit": 1.5,
        "Pj_normal_range": {"min": 50, "max": 300}  # mbar, device-specific
    })

# Backward-compatible interface
def solve_device(config, Po_in_mbar, Qw_in_mlhr, method="auto"):
    """Unified interface supporting both models"""
    if method == "auto":
        method = "stage_wise" if config.stage_wise.enabled else "iterative"

    if method == "stage_wise":
        return stage_wise_solve(config, Po_in_mbar, Qw_in_mlhr)
    else:
        return iterative_solve(config, Po_in_mbar, Qw_in_mlhr)  # Existing
```

### Comprehensive Diagnostic System

```python
@dataclass
class StageWiseDiagnostics:
    """Rich diagnostic output for debugging model-experiment mismatches"""

    # Stage timing breakdown
    stage_timings: dict = field(default_factory=lambda: {
        "stage1_base": [],      # Before corrections
        "stage1_corrected": [], # After corrections
        "stage2_growth": [],
        "stage2_necking": [],
        "total_cycle": []
    })

    # Correction factor impacts
    correction_analysis: dict = field(default_factory=lambda: {
        "interface_resistance_factor": [],
        "adsorption_delay_ms": [],
        "backflow_factor": [],
        "correction_contributions_pct": {}  # Which dominated
    })

    # Regime classification details
    regime_diagnostics: dict = field(default_factory=lambda: {
        "capillary_numbers": [],
        "regime_classifications": [],
        "confidence_levels": [],
        "warning_flags": [],
        "threshold_distances": {}  # How close to regime boundaries
    })

    # Experimental comparison utilities
    experimental_comparison: dict = field(default_factory=lambda: {
        "predicted_vs_measured_timing": {},
        "stage_fraction_comparison": {},
        "frequency_error_breakdown": {},
        "size_prediction_accuracy": {}
    })
```

## Decision Log

### **Decision 1: Model Architecture**
- **Decided**: New stage-wise module (`stepgen.models.stage_wise.py`) as separate component
- **Alternatives**: Extend existing generator.py, hybrid post-processing approach
- **Why**: Provides modularity for research extensions, clean separation for debugging, low integration risk

### **Decision 2: Stage Physics Focus**
- **Decided**: Prioritize both local droplet event law (A) and stage decomposition (B)
- **Alternatives**: Focus on one aspect first
- **Why**: They're deeply interconnected; Stage 1 displacement + Stage 2 bulb growth need to work together

### **Decision 3: Stage 1 Resistance Mechanisms**
- **Decided**: Modular correction approach with moving interface, surfactant/adsorption, and backflow effects
- **Alternatives**: Single dominant mechanism approach
- **Why**: Multiple effects likely contribute; modular design allows experimental determination of which matter most

### **Decision 4: Multi-Mechanism Complexity Handling**
- **Decided**: Layered approach (B) with regime detection (C) using experimental data navigation (D)
- **Alternatives**: Build all mechanisms simultaneously, pure regime detection, pure empirical switching
- **Why**: Provides physics-based foundation with data-driven calibration and extensible architecture

### **Decision 5: Regime Detection Strategy**
- **Decided**: Sequential validation - Capillary number as primary gate, flow/pressure/growth rate checks as secondary confidence measures
- **Alternatives**: Voting system with all methods, single Ca threshold, experimental pattern recognition
- **Why**: Literature-backed Ca approach with robust cross-validation; easier to debug and calibrate

### **Decision 6: Computational Grouping**
- **Decided**: Adaptive grouping - start uniform, detect when pressure variations require rung grouping
- **Alternatives**: Always uniform, always grouped, user-configurable
- **Why**: Computational efficiency when possible, accuracy when needed; extensible approach

### **Decision 7: Performance Priority**
- **Decided**: Accuracy and physical fidelity over computational speed, with optimization as secondary concern
- **Alternatives**: Speed-optimized approach, balanced approach
- **Why**: Better physics representation is primary goal; clear debugging more important than fast execution

### **Decision 8: Reliability Approach**
- **Decided**: Diagnostic mode with detailed logging, no fallback to existing methods
- **Alternatives**: Graceful degradation to linear models, strict validation with failures
- **Why**: Existing methods are "fundamentally wrong"; comprehensive diagnostics needed for research validation

### **Decision 9: Extensibility Priority**
- **Decided**: Modular extension - easy to add new Stage 1 corrections or Stage 2 refinements
- **Alternatives**: Documentation-heavy, experimental integration focus, research-friendly modification
- **Why**: Research is ongoing; model needs to evolve with new physics discoveries

## Testing Strategy

### Multi-Level Validation Approach

1. **Unit testing** of individual physics components (Stage 1 corrections, Stage 2 models, regime detection)
2. **Integration testing** with existing hydraulics backbone and config system
3. **Experimental validation** using stage timing data (when available)
4. **Cross-validation** between Ca and pressure-based regime indicators
5. **Regression testing** to ensure backward compatibility
6. **Comparative analysis** with existing linear/iterative models

### Key Test Cases

- **Stage 1 corrections**: Test each mechanism independently and in combination
- **Adaptive grouping**: Verify uniformity detection and computational efficiency
- **Regime detection**: Test transitional monodisperse regime and blow-out prediction
- **Experimental reproduction**: Use droplet generation rate data for initial validation
- **Config compatibility**: Ensure existing YAML files work unchanged

## Implementation Notes

- Start with simplified Stage 2 model, add detailed integration later as needed
- Begin with moving interface and backflow corrections; adsorption kinetics off by default
- Use experimental data to calibrate regime thresholds and correction factors
- Comprehensive diagnostics from day one for research validation
- Maintain backward compatibility with existing solver interface

## Next Steps

1. Implement basic three-layer architecture with adaptive grouping
2. Add Stage 1 modular correction framework
3. Implement simplified Stage 2 physics
4. Build regime detection with Ca + sequential validation
5. Integrate comprehensive diagnostic system
6. Validate against existing droplet generation rate data
7. Iteratively add stage timing data for detailed calibration

---

**Document Status**: Complete and ready for implementation handoff.