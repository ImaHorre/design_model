# Workspaces

Each subfolder is a self-contained focused study. Workspaces use the core `stepgen/`
library but have their own brief, context doc, bespoke scripts, and results.

## When to create a workspace

Use a workspace for **Type B studies** — focused research with a specific question:
- New physical relationships (e.g. capillary number scaling)
- New empirical fits
- Multi-device comparisons
- Literature-driven analysis

For **Type A studies** (routine parameter sweeps: Qw, Po, concentration) just use:
```
python scripts/run_parameter_study.py --config configs/v5_30.yaml --axis Qw
```
Those results go directly into `results/`.

## Creating a new workspace

```
python scripts/new_workspace.py <name> "<one-line description>"
```

Example:
```
python scripts/new_workspace.py capillary_numbers "Capillary number scaling of Stage 2 snap-off"
```

This creates `workspaces/capillary_numbers/` with:
- `BRIEF.md` — fill in your research question and plan
- `CONTEXT.md` — auto-generated pointer to relevant model files and data
- `results/` — for outputs from this workspace

## Giving Claude context for a fresh session

When starting a new Claude session on a workspace, paste this into your first message:

> Read `workspaces/<name>/CONTEXT.md` and `workspaces/<name>/BRIEF.md`.
> This is the context for our session. The core model is in `stepgen/models/stage_wise_v3/`.

Claude can then work on the study without needing to understand all the historical context.

## Existing workspaces

| Workspace | Description |
|-----------|-------------|
| `mfg050526_consistency/` | Manufacturing batch consistency analysis (V5-30 devices) |
| `nacas_mct_comparison/` | NaCas vs MCT surfactant system comparison |
