# Stage-Wise Model Code Review

**Date**: March 12, 2026
**Reviewer**: Code Simplifier
**Subject**: `stepgen/models/stage_wise.py` Integration Analysis
**File Size**: 50.5KB

## Executive Summary

The stage-wise model represents a significant advance in physics-based droplet formation modeling. The implementation demonstrates solid engineering with comprehensive physics modeling, proper configuration integration, and thorough diagnostics. However, the current implementation can be substantially simplified while preserving functionality and improving maintainability.

## Architectural Assessment

### ✅ Strengths

1. **Proper Integration**: Follows established patterns using `DeviceConfig` and building on `hydraulics.simulate()`
2. **Comprehensive Physics**: Three-stage decomposition with modular correction mechanisms
3. **Configuration Design**: Well-integrated `StageWiseConfig` with sensible defaults
4. **Diagnostic Framework**: Extensive debugging capabilities for model validation
5. **Performance Considerations**: Adaptive pressure grouping for computational efficiency

### ⚠️ Areas for Improvement

1. **File Size & Complexity**: 50.5KB single file with complex nested logic
2. **Code Clarity**: Many deeply nested functions that obscure the main flow
3. **Redundant Abstractions**: Some helper functions add complexity without clear benefit
4. **Inconsistent Patterns**: Deviates from simpler patterns used in `droplets.py` and `hydraulics.py`

---

## Priority 1: Critical Simplifications

### 1.1 Split Large File into Modules ⭐⭐⭐

**Issue**: Single 50.5KB file violates single responsibility principle

**Current Structure**:
```python
stage_wise.py  # Everything in one file
├── Enums and dataclasses (50+ lines)
├── Stage 1 physics (200+ lines)
├── Stage 2 physics (150+ lines)
├── Regime classification (100+ lines)
├── Pressure grouping (150+ lines)
├── Main solver (100+ lines)
└── Diagnostics (100+ lines)
```

**Recommended Structure**:
```python
stage_wise/
├── __init__.py           # Main entry points
├── core.py              # Main solver and result classes
├── stage1.py            # Stage 1 displacement physics
├── stage2.py            # Stage 2 bulb physics
├── regimes.py           # Regime classification
├── grouping.py          # Pressure uniformity and grouping
└── diagnostics.py       # Diagnostic framework
```

**Benefits**:
- Each module <200 lines
- Clear separation of concerns
- Easier testing and maintenance
- Follows patterns from other models

### 1.2 Eliminate Nested Function Definitions ⭐⭐⭐

**Issue**: Many physics calculations defined as nested functions obscure control flow

**Current Pattern**:
```python
def solve_stage1_displacement_physics(P_j, Q_nominal, config):
    def calculate_interface_resistance_correction(Q_nominal, config):
        def calculate_capillary_number(Q_nominal, config):
            # ... nested 3 levels deep
        # ...
    def calculate_adsorption_delay(config):
        # ...
    def calculate_backflow_correction(P_j, config):
        # ...

    # Main logic buried after 100+ lines of nested definitions
```

**Simplified Pattern** (following `droplets.py` style):
```python
def calculate_interface_resistance(Q_nominal: float, config: DeviceConfig) -> tuple[float, dict]:
    """Contact line resistance correction."""
    ca = calculate_capillary_number(Q_nominal, config)
    multiplier = config.stage_wise.contact_line_factor * (1 + ca**0.7)
    return multiplier, {"capillary_number": ca}

def calculate_backflow_resistance(P_j: float, config: DeviceConfig) -> tuple[float, dict]:
    """Water backflow resistance correction."""
    pressure_ratio = P_j / mbar_to_pa(config.operating.Po_in_mbar)
    multiplier = config.stage_wise.backflow_factor * (1 + pressure_ratio**0.5)
    return multiplier, {"pressure_ratio": pressure_ratio}

def solve_stage1_displacement_physics(P_j: float, Q_nominal: float, config: DeviceConfig) -> Stage1Result:
    """Stage 1 physics with clear top-level flow."""
    # Base calculation
    reset_distance = config.geometry.junction.exit_width
    t_base = reset_distance / abs(Q_nominal)

    # Apply corrections
    interface_mult, interface_diag = calculate_interface_resistance(Q_nominal, config)
    backflow_mult, backflow_diag = calculate_backflow_resistance(P_j, config)

    t_corrected = t_base * interface_mult * backflow_mult

    return Stage1Result(
        t_displacement=t_corrected,
        diagnostics={**interface_diag, **backflow_diag}
    )
```

**Benefits**:
- Clear top-to-bottom reading flow
- Functions testable in isolation
- Matches patterns in `droplets.py` and `resistance.py`
- Eliminates 3-level nesting

### 1.3 Simplify Configuration Parameters ⭐⭐⭐

**Issue**: Too many low-level physics parameters exposed in config

**Current Config** (15+ parameters):
```python
@dataclass(frozen=True)
class StageWiseConfig:
    # 15+ parameters including physics constants
    displacement_volume_fraction: float = 0.10
    contact_line_resistance_factor: float = 2.8
    prewetting_film_multiplier: float = 1.9
    bulb_growth_volume_fraction: float = 0.90
    laplace_acceleration_factor: float = 0.7
    # ... 10+ more parameters
```

**Simplified Config** (5-7 key parameters):
```python
@dataclass(frozen=True)
class StageWiseConfig:
    """High-level controls for stage-wise model."""
    enabled: bool = True

    # Model behavior controls
    enable_interface_resistance: bool = True
    enable_backflow_effects: bool = True
    enable_detailed_growth: bool = False

    # Regime detection
    ca_dripping_limit: float = 0.3
    pressure_uniformity_threshold: float = 0.05

    # Advanced users only (hidden in implementation)
    _physics_params: dict = field(default_factory=lambda: DEFAULT_PHYSICS_PARAMS)
```

**Benefits**:
- Users configure behavior, not physics constants
- Follows principle of "simple things simple, complex things possible"
- Matches simplicity of other model configs

---

## Priority 2: Code Quality Improvements

### 2.1 Remove Unnecessary Abstractions ⭐⭐

**Issue**: Over-engineered helper functions for simple calculations

**Current Code**:
```python
class CorrectionFactors:
    interface_resistance: float = 1.0
    adsorption_delay: float = 0.0
    backflow_effect: float = 1.0

def apply_stage1_corrections(base_time, factors, diagnostics):
    # 30 lines to multiply 3 numbers together
```

**Simplified Code**:
```python
def solve_stage1_displacement_physics(P_j: float, Q_nominal: float, config: DeviceConfig) -> Stage1Result:
    t_base = config.geometry.junction.exit_width / abs(Q_nominal)

    # Direct calculation - no unnecessary abstractions
    interface_mult = calculate_interface_resistance(Q_nominal, config) if config.stage_wise.enable_interface_resistance else 1.0
    backflow_mult = calculate_backflow_resistance(P_j, config) if config.stage_wise.enable_backflow_effects else 1.0

    t_total = t_base * interface_mult * backflow_mult
    return Stage1Result(t_displacement=t_total, ...)
```

### 2.2 Improve Error Handling Consistency ⭐⭐

**Issue**: Inconsistent error handling patterns across functions

**Current Patterns**:
```python
# Some functions return None on error
# Some raise exceptions
# Some return sentinel values
# Error messages not descriptive
```

**Improved Pattern** (matching `resistance.py` style):
```python
def calculate_critical_radius(config: DeviceConfig) -> float:
    """Geometry-controlled breakup radius with validation."""
    w = config.geometry.junction.exit_width
    h = config.geometry.junction.exit_depth

    if w <= 0 or h <= 0:
        raise ValueError(f"Invalid geometry: width={w*1e6:.1f}µm, depth={h*1e6:.1f}µm. Must be positive.")

    aspect_ratio = w / h
    if aspect_ratio > 3.0:
        return 0.9 * h  # Depth-limited
    else:
        return 0.7 * min(w, h)  # Geometric mean
```

### 2.3 Reduce Diagnostic Complexity ⭐⭐

**Issue**: Overly complex diagnostic framework

**Current Approach**:
- Nested diagnostic dictionaries
- Diagnostics gathered across multiple function calls
- Complex aggregation logic

**Simplified Approach**:
```python
@dataclass(frozen=True)
class StageWiseResult:
    """Main result with essential diagnostics only."""
    # Core results (matching other models)
    droplet_frequency_hz: float
    droplet_diameter_um: float
    regime: RegimeClassification

    # Essential diagnostics
    stage1_fraction: float
    stage2_fraction: float
    pressure_uniformity_cv: float

    # Optional detailed diagnostics for debugging
    detailed_diagnostics: dict = field(default_factory=dict)
```

---

## Priority 3: Integration and Consistency

### 3.1 Standardize Return Types ⭐⭐

**Issue**: Inconsistent return patterns compared to other models

**Align with `droplets.py` and `hydraulics.py`**:
```python
# Current: Complex nested results
def stage_wise_solve(...) -> StageWiseResult  # Custom complex type

# Should be: Simple numeric results like other models
def stage_wise_frequency(Q_rung: float, config: DeviceConfig) -> float:
    """Per-rung droplet frequency using stage-wise physics."""

def stage_wise_diameter(config: DeviceConfig) -> float:
    """Droplet diameter from stage-wise critical radius."""
```

### 3.2 Import Organization ⭐

**Current Imports** (scattered):
```python
import enum
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Dict, Any, Optional
import numpy as np
# ... scattered throughout file
```

**Organized Imports** (following `hydraulics.py` pattern):
```python
"""Stage-wise droplet formation physics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from stepgen.config import mbar_to_pa, mlhr_to_m3s
from stepgen.models.hydraulics import SimResult, simulate
from stepgen.models.resistance import rung_resistance

if TYPE_CHECKING:
    from stepgen.config import DeviceConfig
```

### 3.3 Function Naming Consistency ⭐

**Issue**: Inconsistent naming patterns

**Current Naming**:
```python
solve_stage1_displacement_physics()  # verbose
solve_stage2_bulb_physics()         # verbose
classify_regime()                   # concise
analyze_pressure_uniformity()      # verbose
```

**Consistent Naming** (following codebase patterns):
```python
stage1_displacement_time()  # clear, concise
stage2_growth_time()       # clear, concise
classify_regime()          # good as-is
pressure_uniformity()      # concise
```

---

## Priority 4: Performance and Maintenance

### 4.1 Reduce Computational Overhead ⭐

**Current Issue**: Unnecessary recalculations in tight loops

**Optimization**:
- Pre-calculate constants outside loops
- Cache repeated geometric calculations
- Vectorize operations where possible

### 4.2 Simplify Testing Surface ⭐

**Current Challenge**: Large file with many private functions hard to test

**Improved Testability**:
- Move physics functions to module level
- Reduce parameter coupling
- Clear input/output contracts

---

## Implementation Roadmap

### Phase 1: Core Simplification (1-2 days)
1. Split file into 6 focused modules
2. Flatten nested function definitions
3. Simplify configuration interface
4. Update imports and naming

### Phase 2: Quality Improvements (1 day)
1. Standardize error handling
2. Simplify diagnostics framework
3. Align return types with other models

### Phase 3: Integration Testing (1 day)
1. Verify CLI integration works
2. Test against existing model comparison framework
3. Validate performance benchmarks

## Conclusion

The stage-wise model demonstrates excellent physics understanding and thorough engineering. The recommended simplifications will:

1. **Improve maintainability**: Smaller, focused modules easier to understand and modify
2. **Enhance consistency**: Align with established patterns in `droplets.py` and `hydraulics.py`
3. **Preserve functionality**: All physics and capabilities maintained
4. **Simplify usage**: Cleaner configuration interface for most users
5. **Ease testing**: Better separation of concerns enables focused unit tests

The current implementation is functionally correct but can be significantly simplified without losing any capabilities. These changes will make the codebase more maintainable and approachable for future development.

---

**Next Steps**:
- [ ] Review and approve proposed simplifications
- [ ] Implement Phase 1 core simplification
- [ ] Update integration points and tests
- [ ] Document simplified interface