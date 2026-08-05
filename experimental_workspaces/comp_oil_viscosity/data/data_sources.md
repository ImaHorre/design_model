# Data sources

This workspace holds **no copy** of its data. It re-analyses a dataset whose
primary workspace is `experimental_workspaces/po_sweep/`, per the multi-workspace
rule in `CLAUDE.md`: one identity, one physical location, referenced from here.

| Identity | Physical file | Device | Test date | Rows | Used here |
|---|---|---|---|---|---|
| `@exp-2026-04-24-v5-8-1` (pre-DB legacy identity) | `experimental_workspaces/po_sweep/data/stage_timings.csv` | V5-8-1 (V5-30 geometry, production 104, testing 2304) | 2026-04-24 | 278 | 158 |

`analysis.py` reads that path directly and applies the filters recorded in
`snapshots/run_manifest.md`. If it ever moves, this workspace fails loudly rather
than silently analysing something else.

## Other workspaces on the same dataset

| Workspace | Question it asks of this data |
|---|---|
| `po_sweep/` | **primary** — does a Poiseuille rung model predict Stage 1 vs Po? |
| `qw_sweep/` | how does Qw affect Stage 1 and Stage 2 timing? |
| `conc_sweep/` | what does [SDS] do below CMC? |
| `Po_Qw_conc_combined/` | the three-way synthesis |
| `comp_oil_viscosity/` (this one) | with the rung resistance exact, what µ does the data imply — and is it one number? |

`qw_sweep` is the direct neighbour: it independently found that Stage 2 is **not**
Qw-independent, which is the same residual this workspace arrives at from the
viscosity side.
