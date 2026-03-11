# Edge Emulsion Linear Model Updates - Implementation Plan

## Phase 1: Initial Understanding

### Requirements Summary
From user request and `/docs/edge_emulsion_linear_model_updates.md`:
- Add toggle on/off feature for linear model
- Include "refill volume" to reduce effective droplet production flow
- Calculate refill volume as: `V_refill = exit_width × exit_height × L` where `L = 2 × exit_height`
- Modify frequency: `f = Q_open / (V_drop + V_refill)` when enabled
- Focus only on linear model (ignore time-state)
- Make adjustable for future tuning

### Current Linear Model Structure
**Key Files:**
- `stepgen/models/droplets.py` - Core droplet calculations (diameter, volume, frequency)
- `stepgen/config.py` - Configuration with `DropletModelConfig` dataclass
- `stepgen/models/generator.py` - Main linear solver entry point

**Current Implementation:**
- Droplet volume: `V = (π/6) × D³` (spherical)
- Frequency: `f = Q_rung / V_droplet`
- Configuration via YAML with CLI overrides supported

**Existing Patterns:**
- Feature toggles via config flags (e.g., `hydraulic_model` selector)
- CLI parameter overrides established
- Enhanced volume calculations already exist in time-state models (`filling_mechanics.py`)

## Phase 2: Design

