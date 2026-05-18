# Plan: design_model Repo Cleanup & Organisation Strategy

## Context

The `design_model` repo has grown organically through three model generations (linear hydraulic → time-state → stage-wise v1/v2/v3), accumulating one-off analysis scripts, near-duplicate config files, multiple doc generations, and a mixed archiving approach. The goal is: a clean core environment for ongoing v3 physics work and future focused studies (e.g. capillary numbers), an archiving strategy that doesn't lose history, a principled approach to scripts, and a better experimental data system that ties model results to physical device records.

**Urgent issue**: CLAUDE.md references three REVISED docs that do not exist:
- `stage_wise_v3_consolidated_physics_plan_REVISED.md` → only `stage_wise_v3_consolidated_physics_plan.md` exists
- `stage_wise_v3_implementation_plan_REVISED.md` → only `stage_wise_v3_implementation_plan.md` exists  
- `v3_execution_summary_REVISED.md` → only `v3_execution_summary.md` exists

Fix by renaming the existing docs to add `_REVISED` suffix (makes CLAUDE.md's authority hierarchy work as intended).

---

## Part 1: Script Philosophy

**Recommendation: Parameterised reusable scripts + config files. Not a new script every time.**

### Why the current approach is painful
The repo has 23 scripts. The `wo_*.py` and `v5_8_1_*.py` scripts are almost identical — same sweep loop, same plotting setup, only the YAML config and axis parameter changes. Creating a new file each time:
- Scatters identical logic across files
- Makes bugs multiply silently (fix in one, broken in five others)
- Makes it impossible to run "the same analysis" consistently across devices

### The pattern to move to

| Layer | What lives here | Rule |
|-------|-----------------|------|
| `stepgen/` | Core library | No device-specific logic. Changes only when physics changes. |
| `configs/` | All device + operating parameters | One YAML per device/variant. Truth lives here. |
| `scripts/` | 5-8 reusable parameterised scripts | Accept `--config` + flags. Never hardcode device names. |
| `results/{study}/` | Run outputs | Each folder is self-contained with a `metadata.yaml` inside. |
| `workspaces/{name}/` | Focused research studies | Own brief, context doc, bespoke scripts. Not sweeps. |

**Examples of reusable script calls:**
```
python scripts/run_sweep.py --config configs/v5_30.yaml --axis Qw --out results/qw_sweep_v530
python scripts/compare_experiments.py --config configs/v5_30.yaml --data data/stage_timings.csv
```
These replace the 8+ one-off `v5_8_1_*.py` and `wo_*.py` scripts.

---

## Part 2: Repo Structure Cleanup

### Target structure

```
design_model/
├── stepgen/                        # Core library — stable, no clutter
│   ├── models/
│   │   ├── hydraulics.py
│   │   ├── generator.py
│   │   ├── resistance.py
│   │   ├── metrics.py
│   │   └── stage_wise_v3/          # ACTIVE DEVELOPMENT
│   ├── config.py
│   ├── cli.py
│   ├── design/
│   ├── viz/
│   └── io/
│
├── tests/                          # keep all
│
├── configs/
│   ├── templates/
│   ├── v5_30.yaml                  # active devices only
│   ├── w11.yaml
│   └── test_stage_wise_v3.yaml
│
├── scripts/                        # reusable scripts only
│   ├── run_sweep.py
│   ├── run_operating_map.py
│   ├── compare_experiments.py
│   ├── new_workspace.py            # workspace generator
│   └── debug/                      # keep, trim to active ones
│
├── workspaces/                     # focused research studies (see Part 3)
│   ├── README.md
│   ├── _template/
│   ├── parameter_sweeps/           # existing sweep analyses
│   └── [future: capillary_numbers/, etc.]
│
├── docs/
│   ├── 03_stage_wise_model/
│   │   └── v3/                     # active v3 docs only (renamed to REVISED)
│   └── archive/                    # all superseded docs
│
├── data/                           # experimental reference data
├── analysis/                       # keep, but prune into workspaces over time
├── results/                        # model run outputs, each with metadata.yaml
│
├── archive/                        # top-level archive — nothing deleted
│   ├── stepgen_seed/
│   ├── models_time_state/          # time_state/ with summary doc
│   ├── models_v2/                  # stage_wise.py
│   ├── scripts_legacy/
│   ├── scripts_experimental/
│   ├── configs_old/
│   └── docs_v1_v2/
│
├── CLAUDE.md                       # fixed doc references
└── pyproject.toml
```

### Disposition table

| Item | Action |
|------|--------|
| `stepgen/models/time_state/` | Archive → `archive/models_time_state/` + write summary doc |
| `stepgen/models/stage_wise.py` (v2) | Archive → `archive/models_v2/` |
| `stepgen_seed/` | Archive → `archive/stepgen_seed/` |
| `scripts/legacy/` | Archive → `archive/scripts_legacy/` |
| `scripts/experimental/` | Archive → `archive/scripts_experimental/` |
| `scripts/wo_*.py`, `v5_8_1_*.py` | Extract logic → reusable scripts; originals → archive |
| `docs/01_*`, `docs/02_*` | Archive → `docs/archive/` |
| `docs/03_stage_wise_model/v1/`, `v2/` | Archive → `docs/archive/` |
| `configs/w11_old.yaml`, `examples/w11_old.yaml` | Archive → `archive/configs_old/` |
| `obsidian_temp/` | Leave untouched (local DB testing notes, not committed) |

---

## Part 3: Archiving the time_state Model

Before moving `stepgen/models/time_state/` to archive, generate a summary document that captures what was understood and built there, so it's useful as a reference for future mechanism thinking (e.g. duty-factor gating, cycle-state tracking). 

**File to create**: `archive/models_time_state/TIME_STATE_SUMMARY.md`

Contents:
- What problem the time-state model was trying to solve
- Key concepts: duty factor (φ), DFU state machine, filling mechanics, cycle gating
- What it got right / what it didn't
- Why v3 stage-wise superseded it
- Pointer to relevant physics that may still apply (e.g. timing analysis, cycle fraction ideas)

This way the intellectual work isn't lost — it's just not cluttering the active codebase.

---

## Part 4: Workspace Approach for Sub-Studies

### The two types of sub-studies

**Type A — Parameter sweep studies** (Qw, Po, surfactant concentration, surfactant type)
These are model vs. experiment comparisons under varying inlet conditions. They use the core model directly, produce results that belong in `results/`, and are run via the reusable sweep scripts. They don't need their own workspace — they just need a proper config file and a named results folder.

```
# Run a Qw sweep on V5-30 with SDS
python scripts/run_sweep.py --config configs/v5_30.yaml --axis Qw
# → results/v5_30_qw_sweep/  (with metadata.yaml inside)
```

**Type B — Focused research studies** (capillary number relationships, new empirical fits, new physics concepts)
These involve literature, derivation, hypothesis, bespoke analysis scripts, and may eventually feed new physics back into v3. They benefit from a clean, self-contained workspace with their own context doc for fresh Claude sessions.

```
workspaces/
└── capillary_numbers/
    ├── BRIEF.md        # the research question + plan
    ├── CONTEXT.md      # auto-generated: points to relevant model files, key data
    ├── analysis.py     # bespoke script for this study
    └── results/
```

### Existing analyses → workspaces

The analyses in `analysis/` fit Type B. Move them into named workspaces:
- `analysis/mfg050526_consistency_analysis.py` → `workspaces/mfg050526_consistency/`
- `analysis/nacas_mct_analysis.py` → `workspaces/nacas_mct_comparison/`

### The context doc generator

`scripts/new_workspace.py <name> "<brief>"` creates the workspace folder and generates a `CONTEXT.md` that includes:
- Project overview (what stepgen is, current model version)
- Relevant source files for the topic (e.g. for capillary numbers: `stage2_physics.py`, `regime_classification.py`)
- Key config files to use
- Available experimental data
- How to run the model from this workspace

**When you say to Claude "look at this repo, I want to work on capillary numbers"**, you hand it:
- `workspaces/capillary_numbers/CONTEXT.md` — the repo context, pre-filtered
- `workspaces/capillary_numbers/BRIEF.md` — your research plan

Claude gets exactly what it needs without wading through archived v1 docs and old sweep scripts.

---

## Part 5: Experimental Database — Bringing It Together

### Current landscape

| System | What it is | State |
|--------|-----------|-------|
| `PE/test_database` | Flat CSV (1213+ records), terminal TUI, working | Production |
| `PE/DB` | Relational SQLite, 13 tables, manufacturing traceability | Design done, implementing |
| `design_model/data/` | Calibration data, stage timings CSV | Ad hoc |
| `design_model/results/` | Model sweep outputs | Unlinked to device records |

### The missing link

Model simulation results in `design_model/results/` are currently not linked to the physical device records in either database. You can't easily ask: "what did device V5-30-3D actually do vs what the model predicted?"

The link needs to be: **device_id** (present in PE/DB as `devices.uid` and in test_database as `device_id` column).

### Recommended cohesion strategy

**1. Add `metadata.yaml` to every results folder (immediate)**
```yaml
study: qw_sweep_v530
date: 2026-05-18
model_version: stage_wise_v3
config: configs/v5_30.yaml
device_ids: [V5-30-1B, V5-30-3D, V5-30-4C]  # maps to PE/DB device UIDs
experimental_data: data/stage_timings.csv
notes: Qw sweep 50-500 mL/hr at 200 mbar
```
This costs almost nothing and makes every results folder self-describing and linkable.

**2. Add `device_id` column to `data/stage_timings.csv`**
Map each measurement row to the PE/DB `devices.uid`. Then `compare_experiments.py` can do a clean join: model prediction ↔ measured timing ↔ full device lineage from PE/DB.

**3. `scripts/compare_experiments.py`** — the bridge script
- Takes a results folder + config as input
- Loads model predictions from the results CSV
- Loads experimental measurements (from stage_timings.csv or a PE/DB export)
- Joins on `device_id` + test conditions
- Produces comparison plots + stats
- Works with the old test_database export format now; can be wired to PE/DB exports later

**4. PE/DB export for model comparison**
Once PE/DB has data, add a standard export: `analysis_flat.csv` with full device lineage + measurement results. The compare script reads this flat file — it doesn't need to know whether it came from test_database or PE/DB.

**This means**: as PE/DB comes online, you just swap the input CSV to compare_experiments.py. The model-side workflow doesn't change.

**5. Don't merge the databases yet**
The test_database TUI is working and has 1213 records. Don't migrate it until PE/DB is fully implemented. Instead:
- New experimental results → go into PE/DB
- Old records → stay in test_database, flagged as legacy
- Both can export a flat CSV that compare_experiments.py can consume

### What "cohesive" looks like when done

```
# New experiment comes in (V5-30-5A, SDS, 200 mbar, 200 mL/hr)
# 1. Record in PE/DB (video → analysis → DB ingest)
# 2. Run model prediction
python scripts/run_sweep.py --config configs/v5_30.yaml --axis Qw --out results/v530_5a_qw
# 3. Compare
python scripts/compare_experiments.py --results results/v530_5a_qw --device V5-30-5A
# → results/v530_5a_qw/comparison/ with plots + stats
```

---

## Implementation Order

### Phase 0 — Fix CLAUDE.md (5 min)
Rename the three v3 docs to `_REVISED` suffix so CLAUDE.md references work.

### Phase 1 — time_state archive + summary doc (1 hour)
Write `archive/models_time_state/TIME_STATE_SUMMARY.md`, then move `stepgen/models/time_state/` to archive.

### Phase 2 — Structural archive (1-2 hours)
Create `archive/` at repo root. Move all items per the disposition table above. Commit: `chore: archive superseded models, scripts, and docs`.

### Phase 3 — Reusable scripts (2-3 hours)
Write `scripts/run_sweep.py`, `scripts/run_operating_map.py`, `scripts/compare_experiments.py`.

### Phase 4 — Workspace infrastructure (1 hour)
Create `workspaces/` with README + `_template/`. Write `scripts/new_workspace.py`. Move `analysis/mfg050526_*` and `analysis/nacas_mct_*` into named workspaces.

### Phase 5 — Results metadata (30 min)
Add `metadata.yaml` to all existing `results/` folders. Add `device_id` column to `data/stage_timings.csv`.

### Phase 6 — DB linkage (when PE/DB has data)
Wire `compare_experiments.py` to consume PE/DB `analysis_flat.csv` export format.

---

## Files to create or modify

| File | Action |
|------|--------|
| `CLAUDE.md` | Fix REVISED doc references |
| `docs/03_stage_wise_model/v3/*.md` | Rename to REVISED |
| `archive/models_time_state/TIME_STATE_SUMMARY.md` | Create — time_state knowledge summary |
| `scripts/run_sweep.py` | Create — replaces wo_*.py, v5_8_1_*.py |
| `scripts/run_operating_map.py` | Create |
| `scripts/compare_experiments.py` | Create |
| `scripts/new_workspace.py` | Create — workspace generator |
| `workspaces/README.md` | Create |
| `workspaces/_template/` | Create |
| `results/*/metadata.yaml` | Create in each existing results folder |
| `data/stage_timings.csv` | Add device_id column |
