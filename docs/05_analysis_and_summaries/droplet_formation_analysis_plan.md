# Plan: Droplet Formation Multi-Stage Physics Analysis

## Context
User has made detailed experimental observations of droplet formation in the v5_30.yaml device that reveal a significant discrepancy between theoretical/simulated models and actual physics:

### Experimental Observations:
- **Stage 1 (80-85%)**: Oil meniscus moving at constant flow, expelling water ahead
- **Stage 2 (12-15%)**: Necking/pinching with Laplace-driven bulb growth
- **Stage 3 (1-2%)**: Droplet pinch-off and reset

### Key Discrepancy:
- Water expulsion volume: 1.415e-15 m³ (stage 1)
- Final droplet volume: 8.18e-15 m³ (8× larger)
- But water expulsion takes 5× longer than bulb filling
- Theoretical flow rate (1.32e-14 m³/s) is much faster than observed water expulsion

Need to understand gaps in current modeling and potential improvements.

## Phase 1: Exploration - Key Findings

### Current Model Capabilities
The codebase has sophisticated time-dependent models that partially address your observations:

**Time-State Models Available:**
- **3-Phase State Machine**: OPEN → PINCH → RESET cycles
- **Dynamic Conductance**: Reduces flow during pinch (g_pinch_frac = 1%)
- **Event-Triggered Transitions**: Volume threshold triggers OPEN → PINCH
- **Timer-Based Recovery**: Fixed tau_pinch_ms (50ms) and tau_reset_ms (20ms)

**Current Time Split Capability:**
- Can achieve 80-85%/12-15%/1-2% split by tuning timer parameters
- BUT uses **fixed durations**, not physics-based dynamic transitions

### Critical Gaps Identified

**1. Laplace Pressure Modeling:**
- Surface tension `gamma = 0.0` in configs (not used in calculations)
- Capillary thresholds (dP_cap_ow/wo) are hardcoded empirical values (30-50 mbar)
- No dynamic Young-Laplace pressure during bulb growth: `dP = 2γ/r(t)`
- Missing the "speedup effect" you observed during necking

**2. Water Expulsion vs Bulb Filling Physics:**
- Current model assumes uniform flow throughout cycle
- No separate treatment of water displacement vs oil accumulation phases
- Missing the 8× volume ratio (water expulsion vs final droplet) dynamics

**3. Known 5-6× Flow Rate Overprediction:**
- Documented issue: theoretical rung flow is 5-6× higher than experimental
- Your calculation (1.32e-14 m³/s theoretical vs observed slower water expulsion) confirms this
- Current "fix" is empirical duty factor (φ ≈ 0.18) rather than physics-based

### Your Experimental Insight - Key Discovery
Your observation that **water expulsion takes 5× longer than bulb filling despite 8× smaller volume** suggests:
- Different flow regimes/resistances during stages
- Laplace pressure acceleration effect not captured
- Possible pressure-dependent or geometry-dependent resistance changes

## Phase 2: Design Analysis - Completed

### Recommended Approach: Physics-Enhanced Time-State Model

**Core Strategy:** Extend existing time-state framework with physics-based enhancements while maintaining backward compatibility.

**Key Implementation Areas:**
1. **Dynamic Laplace Pressure Module** - Real Young-Laplace calculations with γ values
2. **Multi-Stage Flow Physics** - Stage-dependent resistance and flow regimes
3. **Enhanced State Machine** - OPEN_EXPULSION → OPEN_NECKING → OPEN_SPEEDUP sub-phases
4. **Volume Ratio Corrections** - Physics-based or empirical handling of 8× volume difference

**Alternative Empirical Approach:** If physics proves too complex, implement stage-dependent duty factors and volume ratio corrections based on your experimental observations.

## Phase 4: Final Implementation Plan

### Context
Your experimental observations reveal fundamental physics gaps in the current droplet formation models:
- **Water expulsion** (1.415e-15 m³) takes 5× longer than **bulb filling** (8.18e-15 m³, 8× larger volume)
- **Theoretical flow rate** (1.32e-14 m³/s) is dramatically faster than observed water expulsion
- **Stage timing**: 80-85% water expulsion, 12-15% necking/bulb growth, 1-2% pinch-off
- **Missing physics**: Laplace pressure acceleration during necking, stage-dependent flow regimes

### Recommended Implementation Strategy

#### **Approach: Enhanced Time-State Model with Physics Corrections**
Extend the existing sophisticated time-state framework (`time_state_filling.py`) with targeted physics improvements while maintaining empirical fallbacks.

#### **Phase 1: Enhanced Multi-Stage State Machine (Weeks 1-2)**

**File: `stepgen/models/time_state/enhanced_state_machines.py`**

Extend existing `PhaseStateMachine` with sub-phases within OPEN:

```python
class EnhancedPhaseStateMachine:
    class SubPhase(enum.Enum):
        EXPULSION = "water_expulsion"    # 80-85% of cycle
        NECKING = "necking_bulb_growth"  # 12-15% of cycle
        SPEEDUP = "laplace_speedup"      # transition within necking

    def get_stage_dependent_conductance(self, volume_accumulated, target_volume):
        # Stage-dependent flow resistance based on your observations
        volume_fraction = volume_accumulated / target_volume

        if volume_fraction < 0.15:  # Water expulsion stage
            return base_conductance * 0.3  # Lower conductance (higher resistance)
        elif volume_fraction < 0.85:  # Necking/bulb growth
            # Laplace acceleration effect - increasing conductance
            speedup_factor = 1.0 + 2.0 * (volume_fraction - 0.15) / 0.7
            return base_conductance * speedup_factor
        else:  # Pinch-off
            return base_conductance * self.g_pinch_frac
```

#### **Phase 2: Volume-Based Physics Corrections (Week 3)**

**File: `stepgen/models/time_state/volume_physics.py`**

Implement corrections based on your experimental volume ratios:

```python
class VolumePhysicsModel:
    def compute_stage_volumes(self, config):
        # Based on your experimental observations
        water_expulsion_volume = self.compute_water_expulsion_volume(config)
        final_droplet_volume = self.compute_droplet_volume(config)

        # Your observed ratio: droplet_vol / expulsion_vol = 8.18e-15 / 1.415e-15 ≈ 5.8
        volume_ratio = final_droplet_volume / water_expulsion_volume

        return {
            'expulsion_volume': water_expulsion_volume,
            'final_volume': final_droplet_volume,
            'volume_ratio': volume_ratio,
            'stage_fractions': [0.825, 0.135, 0.04]  # Your observed timing
        }

    def compute_water_expulsion_volume(self, config):
        # Your calculation: (mcd*mcw*exit_width) - 0.5*(oil meniscus volume)
        exit_area = config.geometry.rung.mcd * config.geometry.rung.mcw
        length = config.geometry.junction.exit_width
        meniscus_volume = 0.5 * np.pi * (config.geometry.junction.exit_width/2)**3
        return exit_area * length - meniscus_volume
```

#### **Phase 3: Flow Rate Corrections (Week 4)**

**File: `stepgen/models/resistance.py` (enhance existing)**

Address the 5-6× flow overprediction with physics-based corrections:

```python
def enhanced_rung_resistance(config, formation_stage="steady"):
    """Enhanced resistance calculation with formation stage dependency."""
    base_resistance = rung_resistance(config)  # Existing calculation

    # Your observation: theoretical gives 1.32e-14 m³/s, but experiment shows much slower
    # This suggests effective resistance is 5-6× higher during water expulsion

    if formation_stage == "water_expulsion":
        # Higher resistance during water expulsion phase
        # Possible causes: entrance effects, two-phase flow, meniscus pinning
        return base_resistance * 5.5
    elif formation_stage == "bulb_growth":
        # Lower resistance during bulb growth (Laplace acceleration)
        return base_resistance * 0.8
    else:
        return base_resistance  # Steady-state value
```

#### **Phase 4: Enhanced Time-State Model Integration (Week 5)**

**File: `stepgen/models/time_state/physics_enhanced_filling.py`**

Create enhanced version of `time_state_filling.py`:

```python
class PhysicsEnhancedFillingModel(TimeStateFillingModel):
    def solve(self, config, Po_Pa, Qw_m3s, P_out_Pa):
        # Use enhanced state machine with sub-phases
        enhanced_state_machine = EnhancedPhaseStateMachine(config.geometry.Nmc)
        volume_physics = VolumePhysicsModel()

        # Main time integration loop with stage-dependent physics
        for t_ms in np.arange(0, simulation_time_ms, dt_ms):
            # Get current formation stage for each rung
            formation_stages = self.determine_formation_stages(droplet_volumes, target_volumes)

            # Compute stage-dependent conductances
            stage_conductances = enhanced_state_machine.get_stage_dependent_conductance(
                droplet_volumes, target_volumes
            )

            # Solve hydraulics with enhanced resistances
            enhanced_g_rungs = self.apply_formation_stage_corrections(
                base_g_rungs, formation_stages
            )

            result = _simulate_pa(..., g_rungs=enhanced_g_rungs, ...)

            # Volume accumulation with stage-dependent rates
            self.accumulate_volume_with_stage_physics(result, formation_stages, dt_s)
```

#### **Phase 5: Configuration and Validation (Week 6)**

**File: `stepgen/config.py` (enhance existing `DropletModelConfig`)**

```python
class DropletModelConfig:
    # Existing parameters...

    # Enhanced physics parameters
    enable_stage_dependent_physics: bool = True

    # Stage timing fractions (from your observations)
    stage1_time_fraction: float = 0.825  # Water expulsion (80-85%)
    stage2_time_fraction: float = 0.135  # Necking/bulb growth (12-15%)
    stage3_time_fraction: float = 0.040  # Pinch-off (1-2%)

    # Flow physics corrections
    expulsion_resistance_multiplier: float = 5.5  # Address 5-6× overprediction
    bulb_growth_resistance_multiplier: float = 0.8  # Laplace speedup effect
    laplace_speedup_factor: float = 2.0  # Max acceleration during necking

    # Volume ratio parameters (from your calculations)
    expected_volume_ratio: float = 5.8  # droplet_vol / expulsion_vol
    volume_ratio_tolerance: float = 0.5  # Validation range

    # Empirical surface tension (if unavailable)
    effective_gamma_mN_m: float = 15.0  # Effective value for empirical calculations
```

### **Validation Strategy**

1. **Baseline Comparison**: Test against existing duty factor model (φ=0.18)
2. **Flow Rate Validation**: Compare predicted vs. your observed flow rates
3. **Stage Timing Validation**: Verify 80-85%/12-15%/1-2% timing split
4. **Volume Ratio Validation**: Check droplet_vol/expulsion_vol ≈ 5.8

### **Empirical Fallback Rules**

If physics-based approach proves too complex:

```python
# Simple empirical corrections based on your observations
def empirical_flow_correction(Q_theoretical, formation_stage):
    if formation_stage == "water_expulsion":
        return Q_theoretical * 0.18  # Based on duty factor model
    elif formation_stage == "bulb_growth":
        return Q_theoretical * 0.25  # Slightly higher due to speedup
    else:
        return Q_theoretical * 0.18

def empirical_timing_correction(base_frequency):
    # Apply your observed stage fractions
    effective_frequency = base_frequency * (0.825 + 0.135 * 1.5 + 0.040 * 0.1)
    return effective_frequency
```

### **Success Metrics**

1. **Flow Rate Accuracy**: Predicted flows within 20% of experimental observations
2. **Frequency Accuracy**: Eliminate 5-6× overprediction (get within 1.5× of experimental)
3. **Stage Timing**: Model captures 80-85%/12-15%/1-2% split
4. **Volume Ratios**: Correctly predict ~6× ratio between droplet and expulsion volumes

### **Critical Files to Modify**

- **`stepgen/models/time_state/time_state_filling.py`** - Main model to enhance
- **`stepgen/models/time_state/state_machines.py`** - Add sub-phase state machine
- **`stepgen/models/resistance.py`** - Add stage-dependent resistance calculations
- **`stepgen/config.py`** - Add physics and empirical correction parameters
- **`stepgen/models/time_state/filling_mechanics.py`** - Enhance volume calculations

### **Implementation Priority**

1. **High Priority**: Flow rate corrections (address 5-6× overprediction)
2. **Medium Priority**: Stage-dependent timing (capture time split observations)
3. **Lower Priority**: Full Laplace pressure physics (can be added later)

This approach leverages your detailed experimental observations to create targeted improvements while building on the existing sophisticated time-state framework.