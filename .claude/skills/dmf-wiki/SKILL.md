---
name: dmf-wiki
description: Query the Peak Emulsions DMF (droplet-microfluidics) research wiki to ground physics/design answers in the literature. Use for any droplet-microfluidics physics or design question — droplet size scaling, step-emulsification / snap-off mechanisms, capillary/Weber number, surfactant and interfacial-tension effects, Stage 1/2 physics, regime transitions (dripping/SE/jetting/balloon), contact angle, viscosity-ratio effects — and whenever the user proposes a design target or number (droplet diameter, DFU geometry, operating pressure/flow) that theory could confirm or challenge. READ-ONLY: this skill only reads the wiki; it never writes. Filing findings back (ingest) is a separate, human-confirmed workflow.
---

# DMF Research Wiki — Query (read-only)

Answer droplet-microfluidics physics and design questions by grounding them in
the Peak Emulsions DMF research wiki, citing sources. This is the query half of
the compounding model↔wiki loop. **You never write to the vault in this skill**
— ingest/filing is a separate, user-confirmed workflow (`wiki_ingest.md`).

## Vault path — PowerShell only (apostrophe in username breaks other tools)

```powershell
$wiki = "$env:USERPROFILE\OneDrive - Peak Emulsions\Documents - Tech sharepoint\XX_Conor\PeakEmulsions\PeakEmulsions\03_Research\Droplet-Microfluidics"
```

Use `Get-Content` for every read. Never hardcode `C:\Users\ConorO'Sullivan\...`.
Never use the Read/Grep/Glob tools on this path — they cannot resolve the
apostrophe. See `docs/claude_windows_apostrophe_path_fix.md`.

## Query workflow (follow in order)

1. **Index first, always.** `Get-Content "$wiki\wiki\index.md"`. The index is the
   catalog of every page with a one-line description and source count. Never
   guess page paths — find them in the index.
2. **Drill into the relevant pages** via `Get-Content` — typically the matching
   `claims/`, `concepts/`, `equations/`, `devices/`, and `papers/` pages, plus
   any `contradictions/` or `open-questions/` they link to. Follow `[[wikilinks]]`.
3. **For physics/design questions, always also check** `wiki/model/open-questions.md`
   — the model's known gaps and poorly-constrained parameters. If the question
   touches one, say so.
4. **Answer with citations.** Cite every factual claim with its citekey
   (`@firstauthorYYYY-keyword`, `@ws-YYYY-MM-DD-name`, `@exp-...`) or wiki page
   link. No factual claim without a source — that is the wiki's non-negotiable rule.
5. **Label the evidence layer** for each claim, and never conflate them:
   - `[theory]` — from a paper/review
   - `[experimental]` — a lab measurement
   - `[model-v3, YYYY-MM]` — a design_model prediction
   Theory and experiment have equal standing; if they diverge, report both and
   state the divergence rather than picking one.
6. **Surface conflicts and gaps.** If the wiki has a `contradictions/` or
   `open-questions/` page bearing on the answer, name it — don't paper over it.
   If evidence is weak, single-source, or from a low-quality source, say so.
7. **Only go to `raw/` or `01_Product/`** if the wiki pages lack the exact data
   needed. Those folders are immutable — read, never modify.

## When challenging a design target

If the user proposes a number or geometry (e.g. "let's make 1000 µm droplets",
"a 50 µm-deep DFU"), don't just answer — pressure-test it against the wiki:
- What does the relevant scaling law / regime boundary predict? Cite it.
- Is the proposal inside or outside the validated envelope (Ca range, viscosity
  ratio λ, aspect ratio, geometry) of the supporting sources? Say which.
- If it conflicts with established theory, state how unwise it looks and what
  `x`/`y` changes (geometry, flow, fluid) would bring it back into a supported
  regime — with citations.
- Distinguish a hard physical limit from an untested extrapolation.

## Output shape

Lead with the direct answer, then the supporting evidence with citekeys and
evidence-layer labels, then any divergences/open-questions. Open with the source,
e.g. "Per the DMF wiki (`@montessori2020-step-emulsification`, `[theory]`) …".

## Offer to file back (do not do it here)

If the exchange produced a durable, reusable finding (a new prediction, a
model-vs-theory divergence, a fresh open question), *offer* to file it via the
ingest workflow — but that is a separate, user-confirmed step, not part of this
read-only skill. Per protocol, ingest happens at workspace completion.
