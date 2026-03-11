# Implementation Plan: Stage-Wise Droplet Formation Model

## Context

The current droplet formation model uses single-flow logic (`f = Q_rung / V_droplet`) with steady Hagen-Poiseuille resistance calculations, resulting in 5-6x frequency overprediction compared to experimental data. The Typst specification document (`docs/promt_2.typst`) provides detailed requirements to restructure the model around three distinct physical stages with different governing equations.

**Problem**: The existing approach assumes one oil flow rate governs the entire cycle, but experiments show that:
- **Stage 1** (confined water displacement): Dominates cycle time despite small volume
- **Stage 2** (bulb growth and necking): Shorter time despite larger volume
- **Stage 3** (snap-off): Instantaneous

This indicates fundamentally different transport laws govern each stage, invalidating the single-flow assumption.

## Implementation Strategy

### Core Architecture

**Approach**: Create a new `StageWiseModel` class implementing `HydraulicModelInterface` to leverage the existing pluggable model system. This preserves backward compatibility while implementing the required stage-wise physics.

**Key Files to Modify**:
- `stepgen/models/hydraulic_models.py` - Register new model in existing registry
- `stepgen/config.py` - Add stage-wise parameters to `DropletModelConfig`
- `stepgen/models/time_state/stage_wise_model.py` - Main implementation (new)
- `stepgen/models/time_state/stage_physics.py` - Physics calculations (new)

### Stage-Wise Physics Implementation

#### Stage 1: Confined Displacement (82.5% of cycle time)
```python
# Enhanced resistance (NOT using hydraulic_resistance_rectangular)
R_eff_displacement = R_base * f_contact_line(Ca) * f_prewetting_film

# Time calculation
T_1 = V_displacement / Q_1
where Q_1 = ΔP_local_1 / R_eff_displacement

# Control volume: reset meniscus → step edge
V_displacement ≈ 0.15 * V_final_droplet  # From experimental observations
```

#### Stage 2: Accelerating Bulb Growth (13.5% of cycle time)
```python
# Dynamic neck radius and Laplace pressure
r_neck(t) = f_geometry(V_accumulated)
P_laplace(t) = 2 * γ / r_neck(t)

# Accelerating flow rate
Q_2(t) = (ΔP_local_2 + P_laplace(t)) / R_eff_neck(r_neck)

# Time integration
T_2 = ∫[V_displacement to V_final] dV / Q_2(V)
```

#### Stage 3: Instantaneous Snap-off (4% of cycle time)
```python
T_3 ≈ 0  # Initially instantaneous
# Can be enhanced later with rapid pinch dynamics
```

### Configuration Parameters

Add to `DropletModelConfig`:
```python
# Stage-wise model selection
hydraulic_model: str = "stage_wise"

# Stage 1: Confined displacement physics
displacement_volume_fraction: float = 0.15    # V_stage1 / V_final
contact_line_resistance_factor: float = 2.5   # Moving interface enhancement
prewetting_film_multiplier: float = 1.8       # Film resistance effect

# Stage 2: Bulb growth physics
bulb_growth_volume_fraction: float = 0.85     # When Laplace effects dominate
laplace_acceleration_factor: float = 0.6      # Resistance reduction during necking
surface_tension_mN_m: float = 15.0            # Interfacial tension [mN/m]

# Stage timing validation targets (from experiments)
expected_stage1_fraction: float = 0.825       # 82.5% of cycle
expected_stage2_fraction: float = 0.135       # 13.5% of cycle
expected_stage3_fraction: float = 0.04        # 4% of cycle
```

### Network Integration Strategy

**Preserve existing hydraulics**: The stage-wise model will reuse the existing ladder network solver but with stage-dependent resistance modifications:

1. **Time Integration Loop**: Each timestep determines current stage for each rung
2. **Stage-Dependent Resistances**: Compute enhanced resistances based on current stage
3. **Network Solution**: Call existing `_simulate_pa` with modified conductances
4. **Stage Progression**: Update volume accumulation and stage transitions

This approach leverages proven network hydraulics while implementing the required stage-wise physics.

## Implementation Phases

### Phase 1: Core Model Structure (Week 1-2)

**File: `stepgen/models/time_state/stage_wise_model.py`**
```python
class StageWiseModel(HydraulicModelInterface):
    def solve(self, config, Po_Pa, Qw_m3s, P_out_Pa) -> HydraulicResult:
        # Initialize stage tracking
        stage_tracker = StageProgressTracker(config.geometry.Nmc, config)
        physics_calc = StagePhysicsCalculator(config)

        # Time integration with stage-dependent physics
        while t < t_end:
            current_stages = stage_tracker.get_current_stages(droplet_volumes)
            resistances = physics_calc.compute_stage_resistances(current_stages)
            conductances = 1.0 / resistances

            # Solve network with enhanced resistances
            result = _simulate_pa(config, Po_Pa, Qw_m3s, P_out_Pa, g_rungs=conductances)

            # Update stage progression
            stage_tracker.update_volumes_and_transitions(result.Q_rungs, dt)
```

**File: `stepgen/models/time_state/stage_physics.py`**
```python
class StagePhysicsCalculator:
    def compute_stage_resistances(self, stages, volumes, config) -> np.ndarray:
        # Stage-dependent resistance calculations
        # Stage 1: Enhanced displacement resistance (NOT hydraulic_resistance_rectangular)
        # Stage 2: Laplace-accelerated resistance
        # Stage 3: Minimal snap-off resistance
```

### Phase 2: Physics Implementation (Week 3-4)

**Stage 1 Enhanced Resistance**:
- Custom displacement resistance formula incorporating moving contact line effects
- Prewetted film resistance corrections
- Confined geometry effects

**Stage 2 Acceleration Physics**:
- Dynamic neck radius estimation from volume
- Laplace pressure contribution: P_laplace = 2γ/r_neck
- Accelerating flow rate calculation

**Stage 3 Rapid Transition**:
- Minimal resistance for fast snap-off
- Instantaneous volume reset

### Phase 3: Registry Integration (Week 5)

**Modify `stepgen/models/hydraulic_models.py`**:
- Add lazy loading for "stage_wise" model type
- Extend `list_models()` to include new option
- Ensure backward compatibility with existing models

### Phase 4: Configuration and Testing (Week 6-7)

**Extend `stepgen/config.py`**:
- Add stage-wise parameters to `DropletModelConfig`
- Maintain default values for backward compatibility

**Validation Framework**:
- Stage timing validation: Verify 82.5%/13.5%/4% timing split
- Volume ratio validation: Confirm ~6x ratio between final and displacement volume
- Frequency accuracy: Target elimination of 5-6x overprediction
- Cross-device validation: Test portability across geometries

## Critical Requirements (Non-Negotiable)

1. **Do NOT reuse `hydraulic_resistance_rectangular()` for Stage 1** - Must implement new displacement resistance formula
2. **Do NOT use single `Q_oil / V_total` calculation** - Must use stage-wise timing: `T_cycle = T_1 + T_2 + T_3`
3. **Must preserve network hydraulics** - Leverage existing ladder solver infrastructure
4. **Must expose stage diagnostics** - Output T_1, T_2, T_3 durations and stage fractions

## Success Criteria

**Minimum Success**:
- Implements explicit stage-wise structure
- Uses different governing laws for each stage
- Eliminates old single-rate logic
- Produces separate stage durations

**Scientific Success**:
- Explains why small Stage 1 volume dominates cycle time
- Captures different transport physics for each stage
- Reduces frequency overprediction without pure parameter fitting

**Quantitative Targets**:
- Frequency prediction within ±30% across validation set
- Stage fractions match experimental observations (80%/15%/5%)
- Correct directional response to pressure and flow changes

## Validation Plan

1. **Structural Tests**: Verify stage separation and different governing laws
2. **Single-Case Comparison**: Validate against specific experimental data
3. **Operating Condition Trends**: Test pressure and flow rate sensitivity
4. **Cross-Geometry Validation**: Ensure portability across devices
5. **Residual Analysis**: Identify specific failure modes for refinement

## Key Diagnostics to Export

The updated model must log for every simulation:
- Total cycle time and predicted frequency
- Stage 1, 2, 3 durations and fractions
- Stage 1 displacement volume vs final droplet volume ratio
- Stage-dependent resistances and local pressures
- Any empirical factors used (clearly labeled)

This comprehensive diagnostic output is essential for understanding model behavior and guiding future refinements based on comparison with experimental data.