# Experimental Workspaces

Each subfolder is a self-contained focused study. Workspaces use the core `stepgen/`
library but have their own brief, bespoke scripts, and results/figures.

## Study types

Workspaces declare a `study-type` in their `BRIEF.md`:

| Type | Meaning |
|---|---|
| `experimental` | Real lab data — model vs experiment comparison |
| `computational` | Model-only parameter sweep or sensitivity test |
| `synthesis` | Cross-workspace analysis that draws on multiple studies |

Computational workspaces use the `comp_` prefix so they sort visually apart from
experimental ones.

## Creating a new workspace

```
python scripts/new_workspace.py <name> "<one-line description>"
```

Example:
```
python scripts/new_workspace.py capillary_numbers "Capillary number scaling of Stage 2 snap-off"
```

This creates `experimental_workspaces/capillary_numbers/` with:
- `BRIEF.md` — fill in your research question and plan
- `CONTEXT.md` — auto-generated pointer to relevant model files and data

For computational workspaces, prefix the name with `comp_`:
```
python scripts/new_workspace.py comp_neck_sensitivity "Neck radius sensitivity to junction geometry"
```

## Giving Claude context for a fresh session

When starting a new Claude session on a workspace, paste this into your first message:

> Read `experimental_workspaces/<name>/BRIEF.md`.
> This is the context for our session. The core model is in `stepgen/models/stage_wise_v3/`.

## Workspace index

### Experimental — real lab data

| Workspace | Device | Parameter varied | Description |
|---|---|---|---|
| `po_sweep_v530/` | V5-30 (ID A) | Po (200–500 mbar) | Stage timing vs oil pressure; Poiseuille model validation |
| `qw_sweep_v581/` | V5-8-1 (ID B) | Qw × Po matrix | Stage timing vs water flowrate; Stage 2 Qw dependence |
| `conc_sweep_v581/` | V5-8-1 (ID B) | [SDS] (0.125–2%) | Surfactant concentration effects; contact-angle mechanism |
| `mfg050526_consistency/` | V5-30 (batch) | DFU position | Manufacturing batch consistency (3 devices) |
| `nacas_mct_comparison/` | V5-30 (ID A) | Emulsion system | NaCas/MCT vs SDS/silicone-oil comparison |

### Synthesis — cross-workspace analysis

| Workspace | Covers | Description |
|---|---|---|
| `sds_sweep_synthesis/` | po_sweep_v530, qw_sweep_v581, conc_sweep_v581 | Full SDS/silicone-oil characterisation; model tuning recommendations |

### Computational — model-only

| Workspace | Description |
|---|---|
| `comp_wo_hydraulics/` | W/O and O/W hydraulic pressure/flow sweeps across device geometries |
| `comp_viscosity_sweep/` | Oil and water viscosity sensitivity (Stage 1 timings, pressure profiles) |
