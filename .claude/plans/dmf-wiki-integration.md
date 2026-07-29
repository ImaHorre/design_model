# Plan: DMF Wiki ↔ design_model Integration

## Context

The DMF research wiki (`03_Research/Droplet-Microfluidics/` in the Obsidian vault) is a
persistent, LLM-maintained knowledge base of literature on droplet-based microfluidics.
`design_model` is where the physics model lives and where experimental workspaces run.

The goal is a compounding feedback loop — not a one-way reference:
- Literature/theory informs model development
- Experimental results test the model and feed back into both the wiki and the model
- Conflicts between theory, experiment, and model predictions are tracked explicitly
- Each cycle leaves both systems smarter

---

## Decisions settled (from design review)

1. **Both sides equally important** — query and ingest build together, not one before the other
2. **Conflicts documented symmetrically** — in the workspace report AND as a wiki contradiction page; the wiki contradiction page is the canonical durable record
3. **Ingest only at workspace completion** — loose ends become `wiki/open-questions/` entries, not blockers
4. **Model predictions filed in wiki** as `[model-v3, YYYY-MM]` — a third distinct evidence layer alongside `[theory]` and `[experimental]`
5. **Coarse version labelling** — date + major version is enough; implementation plan is the authoritative detail log
6. **Three triggers for model wiki updates**: completed implementation phase / physics assumption change / calibration result. Code refactors do not trigger.
7. **Manual trigger for now** — automation after the first few loops establish intuition
8. **`wiki/model/open-questions.md` is the load-bearing page** — this is what allows wiki Claude to flag paper snippets relevant to the model. Must be created as part of this implementation.
9. **Handoff pattern**: design_model Claude writes `wiki_ingest.md` in the workspace folder; wiki session does the actual filing
10. **Handoff is simple**: what was measured [experimental], what the model predicted [model-v3], obvious gaps already noticed, open questions surfaced. Cross-referencing against existing wiki pages is the wiki Claude's job, not design_model's.
11. **`wiki/model/` scope**: only `open-questions.md` in this implementation. Architecture summary and development history in a follow-on dedicated session.
12. **Index-first navigation always** — this is the core of Karpathy's LLM-wiki framework. Claude always reads `wiki/index.md` first, then drills into relevant pages. Never guesses paths.

---

## Key paths

All vault paths via PowerShell only (Read tool cannot reach `ConorO'Sullivan` path):

```powershell
$wiki = "$env:USERPROFILE\OneDrive - Peak Emulsions\Documents - Tech sharepoint\XX_Conor\PeakEmulsions\PeakEmulsions\03_Research\Droplet-Microfluidics"

# Navigation
Get-Content "$wiki\wiki\index.md"
Get-Content "$wiki\wiki\<category>\<page>.md"

# Filing
Set-Content "$wiki\wiki\<path>" -Value $content
```

Workspace paths (normal tools work here):
```
C:\LOCAL\Projects\PE\design_model\experimental_workspaces\<name>\report.md
C:\LOCAL\Projects\PE\design_model\experimental_workspaces\<name>\BRIEF.md
C:\LOCAL\Projects\PE\design_model\experimental_workspaces\<name>\wiki_ingest.md  ← new
```

---

## What gets created / changed

### 1. `design_model/CLAUDE.md` — new section: "DMF Research Wiki"

Content:
- Vault path (PowerShell form above)
- **Proactive check triggers** (without being asked):
  - Writing or reviewing a workspace `report.md`
  - Any physics question: snap-off, capillary number, surfactant effects, droplet size scaling, Stage 1/2 mechanisms, contact angle, interfacial tension
  - Comparing model outputs to experimental data
  - Proposing model parameter changes
  - Proposing a new experiment
- **How to read**: always `wiki/index.md` first, then drill into relevant pages via `Get-Content`
- **Manual trigger**: user says "check the wiki for X"
- **Ingest trigger**: when workspace `BRIEF.md` shows `Status: complete`, prompt user to confirm wiki ingest
- **Handoff format**: when ingest confirmed, write `wiki_ingest.md` to the workspace folder with four sections:
  1. What was measured `[experimental]`
  2. What the model predicted `[model-v3, YYYY-MM]`
  3. Obvious divergences already noticed during analysis
  4. Open questions surfaced

---

### 2. DMF wiki `CLAUDE.md` — new section: "design_model Workspaces as Evidence"

Content:
- What design_model workspaces are (model-vs-experiment comparison studies, not raw lab records)
- Citekey convention: `@ws-YYYY-MM-DD-workspace-name`
- Where findings land: `wiki/experiments/` + `wiki/contradictions/` + `wiki/claims/`
- **The three evidence layers — never conflate**:

  | Layer | Source | Label |
  |---|---|---|
  | Literature claim | Paper/review | `[theory]` |
  | Experimental observation | Lab measurement | `[experimental]` |
  | Model prediction | design_model v3 | `[model-v3, YYYY-MM]` |

- Ingest workflow for a completed workspace (triggered by `wiki_ingest.md` handoff):
  1. Read `wiki_ingest.md` and `report.md` from the workspace
  2. Read `wiki/index.md` — find all relevant existing pages
  3. Create `wiki/experiments/@ws-date-name.md`
  4. For each finding: check relevant `wiki/claims/` — add as supporting or conflicting evidence
  5. Where any two layers conflict: create/update `wiki/contradictions/` page
  6. File unresolved questions to `wiki/open-questions/`
  7. Update `wiki/index.md` and append `wiki/log.md`

- **Paper-flagging instruction**: when ingesting any paper, check `wiki/model/open-questions.md` — if a finding in the paper is relevant to a listed open question, flag it explicitly in the paper page and link to the open question

---

### 3. New section in wiki `CLAUDE.md`: "Model Development Tracking"

Content:
- `wiki/model/` is a dedicated folder for the design_model v3 architecture and development
- `wiki/model/open-questions.md` — what the model cannot yet explain, poorly constrained parameters, active gaps (this page drives paper-flagging)
- Future pages (not in this implementation): `stage-wise-v3.md`, `development-history.md`
- Model predictions in the wiki are labelled `[model-v3, YYYY-MM]` so they can be traced to the implementation plan's progress log for that date
- When a model update is significant (completed phase / physics change / calibration result), update `wiki/model/open-questions.md` and create/update any affected contradiction pages

---

### 4. New file: `wiki/model/open-questions.md`

Initial content populated from known gaps:
- C_visc: Stage 1 Poiseuille model predicts ~0.25–0.30s refill; experimental observation ~1s. C_visc correction factor needed, not yet calibrated from data.
- Stage 1 timing dependence: full Po-dependence shape not yet validated across operating range
- Any model-experiment mismatches visible in existing completed workspaces

---

### 5. New file template: `wiki_ingest.md` (in workspace folder, not wiki)

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

---

## Out of scope

- `wiki/model/stage-wise-v3.md` and `wiki/model/development-history.md` — follow-on session
- Search scripts or tooling
- Automatic ingest (always user-confirmed)
- Changes to paper ingest workflow or wiki folder structure

---

## Verification

1. Open a design_model session, ask a physics question about snap-off — Claude should read `wiki/index.md` then relevant claim/concept pages via PowerShell before answering
2. Mark a workspace `BRIEF.md` as `Status: complete` — Claude should prompt for ingest and offer to write `wiki_ingest.md`
3. Open a wiki session, point at `wiki_ingest.md` — wiki Claude should read the index, file the experiment page, update claims/contradictions, and add open questions
4. Add a new paper to the wiki raw folder — wiki Claude should check `wiki/model/open-questions.md` and flag any relevant findings
