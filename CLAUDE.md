# CLAUDE.md


## Project context

This repository contains the StepGen stage-wise droplet model and related tooling for
microfluidic step-emulsification device design.

The Stage-Wise V3 model is the current implemented model. It is not in progress — the
core physics are in place. The active focus is experimental validation: running lab
experiments across inlet conditions (Po, Qw, fluid systems), comparing results to
model outputs, and adjusting model parameters to achieve broad agreement. The goal is
a model that gives reliable operating predictions for new device designs.

Work in this repo spans three areas:
1. **Model development** — physics in `stepgen/models/stage_wise_v3/`
2. **Experimental comparison** — ingesting lab data and comparing to model via workspaces and scripts
3. **Design tooling** — `stepgen/design/` for operating maps, sweeps, and design search


## Repository layout

```
stepgen/                     core library
  models/
    stage_wise_v3/           current model (Stage 1 Poiseuille + Stage 2 Rcrit snap-off)
    hydraulic_models.py      steady-state ladder network
    model_comparison.py      model-vs-experiment comparison logic
  io/
    experiments.py           experiment data ingest
    results.py               results I/O
  design/
    design_search.py
    operating_map.py
    sweep.py
  viz/plots.py               result plotting
  cli.py                     stepgen CLI entry point

configs/                     device YAML config files (one per device geometry/fluid system)
experimental_workspaces/     focused studies (see Experimental Workflow below)
scripts/                     utility scripts (compare, workspace creation, parameter studies)
tests/                       pytest suite
docs/                        physics plans, implementation history
```


## Authoritative physics documents

When documents conflict on physics assumptions, use this order:

1. `docs/03_stage_wise_model/v3/stage_wise_v3_consolidated_physics_plan_REVISED.md`
2. `docs/03_stage_wise_model/v3/stage_wise_v3_implementation_plan_REVISED.md`
3. `docs/03_stage_wise_model/v3/v3_execution_summary_REVISED.md`
4. Previous v2 docs and existing codebase as reference only

Do not average conflicting physics assumptions across documents.
Do not reintroduce older assumptions if they conflict with the revised v3 physics plan.


## Current model state (v3)

Core physics — implemented:
- Stage 1: simplified Poiseuille model — rung-resistance-limited oil delivery, 1/Po scaling
- Stage 2: snap-off controlled by `Rcrit`; neck-state variables are diagnostic only
- Grouped rung simulation
- Regime classification is warning/diagnostic logic only — does not override snap-off
- `stage1_viscosity_correction` (C_visc) is a calibration scalar in config; default 1.0

Deferred (not yet implemented — do not add unless explicitly requested):
- Full mechanism auto-selection
- Predictive neck-instability snap-off
- Full adsorption kinetics
- Full dynamic hydraulic network with transient coupling


## Experimental workflow

Experimental workspaces are self-contained focused studies in `experimental_workspaces/`.

### Creating a workspace

```
python scripts/new_workspace.py <name> "<one-line description>"
```

Prefix the name with `comp_` for computational (model-only) workspaces.

Each workspace contains:
- `BRIEF.md` — research question, approach, findings; keep this current
- `analysis.py` — bespoke analysis script for this study
- `results/` — outputs (CSV, JSON)
- `figures/` — plots
- `report.md` — written summary of findings

Study types (declared in BRIEF.md):
- `experimental` — real lab data, model vs experiment comparison
- `computational` — model-only parameter sweep or sensitivity test
- `synthesis` — cross-workspace analysis

### Running model-experiment comparison

```
python scripts/compare_experiments.py --config configs/<device>.yaml

# with filters
python scripts/compare_experiments.py --config configs/v5_30.yaml --device V5-30 --cont-phase SDS

# or via CLI
stepgen compare <config.yaml> <experiments.csv>
```

### Data provenance — snapshots and run manifest

**Trigger**: any time you are working inside a workspace and running model solves, comparison scripts, or any analysis that produces results used in the report.

The goal is that the workspace is fully self-contained and auditable. Anyone opening it must be able to verify exactly what was run, with what inputs, at what state of the model — without relying on external files that may have changed since.

#### Workspace structure (extended)

```
workspace/
  BRIEF.md
  report.md                      ← links everything explicitly
  analysis.py                    ← scripts that live here; note if adapted from elsewhere
  snapshots/
    <config-name>_<YYYY-MM-DD>.yaml   ← verbatim copy of config at time of run
    run_manifest.md                   ← git hash, commands, timestamps, data sources
  data/
    <file>.csv                    ← copy raw data here if file is small (< ~500 rows or < 1 MB)
    data_sources.md               ← for large files: metadata to locate and verify source
  results/
    <output>.csv / .json          ← model outputs, never overwrite
  figures/
    fig_01.png …
```

#### On every model run or script execution

1. **Copy the config** into `snapshots/` with the date appended (e.g. `v5_30_2026-04-28.yaml`). Never reference the live config path — the snapshot is the record.

2. **Record the git commit hash** of the model at the time of the run. Do not copy model source code — the hash is sufficient and exact. Run `git rev-parse HEAD` and paste the result into `run_manifest.md`.

3. **Record the exact command(s)** run (CLI call or script invocation) in `run_manifest.md`.

4. **Handle experimental data by size**:
   - Small files (< ~500 rows, < 1 MB): copy verbatim into `data/` — this is the snapshot.
   - Large files: do not copy. Instead, record in `data/data_sources.md`: device ID(s), test date(s), original file path at time of analysis, row count. This is enough to cross-reference with the test database and verify the exact data used.

5. **Save all model outputs** to `results/` inside the workspace. Never write outputs to a shared or external location only.

#### `run_manifest.md` format

```markdown
# Run Manifest

## Run: <short description> — <YYYY-MM-DD>

**Model commit**: <git hash>
**Config snapshot**: snapshots/<filename>.yaml
**Command**: `<exact command run>`
**Outputs**: results/<filename>

### Experimental data used
| File | Device ID | Test date | Rows | Notes |
|---|---|---|---|---|
| data/<file>.csv (copy) | V5-30 ID A | 2026-03-12 | 48 | full copy in data/ |
| (large file — not copied) | V5-8-1 ID B | 2026-04-01 | 1240 | original: <path> |

### Key config parameters (verify against actual fluid)
| Parameter | Value in snapshot |
|---|---|
| Dispersed phase | sunflower oil |
| η_dispersed | … mPa·s |
| Continuous phase | 2% SDS-water |
| η_continuous | … mPa·s |
| Interfacial tension | … mN/m |
| Device geometry | … |
```

#### `report.md` linkage

The `## Data provenance` section of `report.md` must reference:
- Config snapshot: `snapshots/<file>`
- Run manifest: `snapshots/run_manifest.md`
- Each figure: which results file it was generated from (e.g. "Fig 2 — `results/compare_Po_sweep.csv`")
- Each table: same

If you notice a mismatch between the config snapshot values and the actual fluid system used in the experiment, flag it explicitly before writing the report — do not proceed.

**Fluid system note**: the dispersed phase in most Peak Emulsions workspaces is **sunflower oil** (sometimes abbreviated SO — never interpret SO as silicone oil). MCT oil is always written as MCT. Always confirm the fluid name and viscosity explicitly in the run manifest; never inherit it from a label in a prior file without checking.

### Repeat tests on a completed workspace

**Trigger**: new experimental data collected at the same conditions as an existing completed workspace.

Do not create a new workspace. Do not overwrite existing analysis. Instead:

1. Add the new dataset to the `data/` folder with a distinct filename (include date).
2. Add a new entry to `snapshots/run_manifest.md` for the new run.
3. Add a dated **"Consistency check — YYYY-MM-DD"** section to the report, after the original findings. This section states: what was repeated, how the new results compare to the original (numerically where possible), and what the agreement or deviation means.
4. Update the `## Consistency checks` table in `BRIEF.md`.
5. Do not alter the original findings sections — the comparison between old and new is the result.

### Multi-workspace data

**Trigger**: a single experimental session produces data relevant to more than one research question (and therefore more than one workspace).

The data has one identity (`test_id` from the DB, e.g. `TST-0042`). It lives physically in one place. Multiple workspaces reference it.

Protocol:
1. **Choose a primary workspace** — the one whose research question is most directly answered by this data. The data file (or a copy if small) lives in that workspace's `data/` folder.
2. **Secondary workspaces** reference the data by its identity in their `## Data sources` table, with a note pointing to the primary workspace for the physical file.
3. Each workspace runs its own analysis on the relevant slice of that data and keeps its own snapshot and report section.
4. The wiki is the integration point — claims pages accumulate supporting evidence from each workspace's independent analysis of the same underlying data.

Do not duplicate analysis across workspaces. Do not create a new workspace just to hold shared data — `test_id` is sufficient for cross-referencing.

### Getting data from the DB

Experimental data for design model workspaces comes from the DB web app:

1. Navigate to `/exports/design-model` in the DB web app
2. Filter by design ID, pressure range, flow rate, and fluid phases as needed
3. Download CSV → place in workspace `data/`
4. Record the `test_id`s used in `BRIEF.md ## Data sources` table
5. Record the DB filters applied in `snapshots/run_manifest.md`

For data that predates the DB (pre-2026 workspaces), the legacy identity `@exp-YYYY-MM-DD-device` is used. Do not migrate legacy workspace data into the DB.

### Giving Claude context for a workspace session

At the start of a session focused on a workspace:

> Read `experimental_workspaces/<name>/BRIEF.md`.
> The core model is in `stepgen/models/stage_wise_v3/`.


## CLI commands

```
stepgen simulate <config.yaml>   [--Po P] [--Qw Q] [--Qo Q] [--out results.json]
stepgen sweep    <config.yaml>   [--Po P] [--Qw Q] [--out sweep.csv]
stepgen report   <config.yaml>   [--Po P] [--Qw Q] [--out-dir DIR]
stepgen map      <config.yaml>   [--Po-min …] [--Po-max …] [--Qw-min …] [--Qw-max …] [--out-dir DIR]
stepgen design   <design_search.yaml>  [--out design_results.csv]
stepgen compare  <config.yaml>   <experiments.csv>  [--out compare.csv] [--calibrate]
```


## Testing

Run the full test suite:
```
pytest
```

Run targeted tests for a specific area:
```
pytest tests/test_stage_wise_v3_phase1.py
pytest tests/test_simulate.py
pytest tests/test_comparison.py
```

After any model or physics change:
- Run the smallest relevant test first
- Then run a broader regression check
- Do not declare work complete without reporting actual test results
- Always distinguish: implemented / partially implemented / not yet implemented


## Git workflow

### Commits

Commit per meaningful unit of completed work (a model change, an analysis, a new workspace).

Commit procedure:
1. Review `git status`
2. Stage only intentionally modified files — never `git add .` unless explicitly instructed
3. Write a structured commit message
4. Push to the repository

### Safety rules

- Never use `git add .` unless explicitly instructed
- Never force push
- Never rewrite history
- Never delete branches


## Code-change policy

- Prefer minimal, controlled edits over broad rewrites
- Preserve backward compatibility where reasonable
- Do not introduce speculative abstractions beyond what the current task requires
- Keep module boundaries clean and aligned with the physics plan
- Before implementing any model change: inspect the current code, identify reusable components,
  explicitly note where the change departs from existing behaviour


## Path access on this machine

Never hardcode `C:\Users\ConorO'Sullivan\` in any tool call — the apostrophe in the
username breaks path resolution in Bash, Read, Write, Glob, and Grep tools.
Always use `$env:USERPROFILE` in the PowerShell tool for any path under the user home.
Use `Get-Content` / `Get-ChildItem` / `Set-Content` for file operations that the Read
or Write tools cannot reach.

Save all plan files to the local `.claude/` folder in this project, not the global
`~/.claude/` folder — the global path has the same apostrophe access problem.

See `docs/claude_windows_apostrophe_path_fix.md` for full details and key paths.

## DMF Research Wiki

The DMF research wiki (`03_Research/Droplet-Microfluidics/`) is a persistent, LLM-maintained knowledge base of droplet microfluidics literature. It is a compounding feedback loop — literature informs model development, and model/experimental results feed back into the wiki.

### Vault path (PowerShell only — apostrophe in path)

```powershell
$wiki = "$env:USERPROFILE\OneDrive - Peak Emulsions\Documents - Tech sharepoint\XX_Conor\PeakEmulsions\PeakEmulsions\03_Research\Droplet-Microfluidics"

# Navigation: always read the index first
Get-Content "$wiki\wiki\index.md"
Get-Content "$wiki\wiki\<category>\<page>.md"
```

### When to check the wiki (proactively, without being asked)

Consult the wiki **before answering**, on your own initiative — do not wait for
the user to ask. Triggers:

- Writing or reviewing a workspace `report.md`
- Any physics question: snap-off, capillary number, surfactant effects, droplet size scaling, Stage 1/2 mechanisms, contact angle, interfacial tension
- Comparing model outputs to experimental data
- Proposing model parameter changes
- Proposing a new experiment
- **The user proposes a design target, number, or geometry** — a droplet
  diameter, DFU depth/width, operating pressure or flow, throughput goal, etc.

### Challenge design targets against the wiki (proactive, cite by default)

When the user proposes a target or design decision (e.g. "let's make 1000 µm
droplets"), do not just agree and proceed. First ground it in the wiki, then
answer in the form: *"From the Obsidian memory, citing `@source` (`[theory]`) …
this looks [sound / unwise / outside the validated envelope] because … — unless
you change x and y."* Specifically:

- State what the relevant scaling law / regime boundary predicts, with citekey.
- Say whether the proposal is inside or outside the validated envelope (Ca range,
  viscosity ratio λ, aspect ratio, geometry) of the supporting sources.
- If it conflicts with established theory, say how unwise it looks and what
  concrete changes would bring it back into a supported regime.
- Distinguish a hard physical limit from an untested extrapolation of the model.

This proactive grounding is the default for physics/design decisions; the
`dmf-wiki` skill packages the same read-only query workflow for explicit,
cross-project invocation (`/dmf-wiki <question>`).

### How to read

Always read `wiki/index.md` first via `Get-Content`, then drill into relevant pages. Never guess paths. Cite every factual claim with a citekey or page link, and label its evidence layer (`[theory]` / `[experimental]` / `[model-v3, YYYY-MM]`).

### Manual trigger

User says "check the wiki for X", or invokes the `dmf-wiki` skill.

### Ingest trigger

When a workspace `BRIEF.md` shows `Status: complete`, prompt the user to confirm wiki ingest. If confirmed, write `wiki_ingest.md` to the workspace folder.

### Handoff format (`wiki_ingest.md`)

Write to `experimental_workspaces/<name>/wiki_ingest.md` with four sections:

1. What was measured `[experimental]`
2. What the model predicted `[model-v3, YYYY-MM]`
3. Obvious divergences already noticed during analysis
4. Open questions surfaced

Template:

```markdown
# Wiki Ingest Handoff — <workspace-name>

**Date**: YYYY-MM-DD
**Workspace**: experimental_workspaces/<name>/
**Device**: 
**Citekey**: @ws-YYYY-MM-DD-<name>

## What was measured [experimental]

## What the model predicted [model-v3, YYYY-MM]

## Divergences noticed during analysis

## Open questions surfaced
```

### Model wiki updates

Three triggers for updating `wiki/model/open-questions.md` and affected wiki pages:
- Completed implementation phase
- Physics assumption change
- Calibration result

Code refactors do not trigger wiki updates.


## Session hygiene

For a workspace session: start by reading the workspace `BRIEF.md`.
For a model change session: re-read the consolidated physics plan and implementation plan first.
Use fresh context for substantially different task types.
