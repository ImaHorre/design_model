# Run Manifest

## Run: Large-DFU Stage-1 hydraulic screen — 2026-07-06

**Model commit**: 4f415877968db6c34eda03905cbb516778238067
**Config snapshot**: snapshots/study_config_2026-07-06.yaml
**Command**: `python experimental_workspaces/comp_large_dfu_stage1_screen/analysis.py`
**Run started**: 2026-07-06T09:58:31
**Outputs**: results/candidate_summary.csv, results/per_pressure_long.csv,
results/results_summary.md, figures/fig_01–fig_05

### Experimental data used

None — computational/model-only workspace. No `data/` folder exists by design;
this study screens model candidates only and uses no lab data.

### Key config parameters (verify against actual fluid)

| Parameter | Value in snapshot |
|---|---|
| Dispersed phase | sunflower oil |
| η_dispersed | 60 mPa·s |
| Continuous phase | water |
| η_continuous | 0.89 mPa·s |
| Interfacial tension | 15 mN/m |
| Phase system | o/w |
| Device geometry | synthetic sweep grid (576 candidates; see snapshots/study_config_2026-07-06.yaml) |
| Qw (continuous) | 5 mL/hr fixed |
| Po sweep | 50–1000 mbar, step 50 |
| Stage-1 back-pressure | 12 mbar (flat constant) |
| t_S1 pass threshold | 1 s (every DFU) |
