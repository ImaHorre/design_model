# Design Studio — interactive UI (Phase 4)

The Design Studio has two front-ends over the **same** declarative pipeline
(`load_study → run_study → score_result → workbook`):

| Front-end | Command | Output |
|---|---|---|
| Batch (static) | `stepgen study <study.yaml> [--book DIR]` | self-contained HTML chapter + `book/index.html` |
| Interactive | `stepgen studio-ui [study.yaml] [--port N]` | live Streamlit app (exports the same HTML chapter) |

Both read the identical study schema (`configs/study_template.yaml`) and produce
identical scoring and plots — the UI is a thin, interactive skin, not a second
model.

## Install

Streamlit is an **optional** extra to keep the core lean (the 6 runtime deps are
unchanged). Install it once:

```
pip install -e .[ui]
```

## Launch

```
stepgen studio-ui                              # start empty, pick a config in-app
stepgen studio-ui configs/study_all_families.yaml
stepgen studio-ui configs/study_template.yaml --port 8502
```

Equivalently, without the CLI wrapper:

```
streamlit run stepgen/studio/ui.py -- configs/study_template.yaml
```

If Streamlit isn't installed, `stepgen studio-ui` prints the install hint and
exits — it never crashes the core CLI.

## What the app does

- **Sidebar** — pick a shipped `configs/study_*.yaml`, upload one, or paste/edit
  YAML directly. Press **▶ Run study**. Runs are cached on the YAML text, so
  re-editing and re-running is instant unless the config actually changed.
- **Decision tab** — what the study concluded. A winner per value axis, the
  Pareto set, an all-round pick and a *safest* pick. The composite weights are
  live sliders: moving one re-ranks instantly without re-running the physics,
  because re-ranking only reads the already-solved rows. Whatever the weights
  are left at is what gets written into the chapter — a composite whose weights
  are hidden is worse than no composite at all. Declare the axes with a
  `decide:` block; `goal: <one word>` still works as a one-axis shorthand.
- **Scored comparison tab** — the traffic-light table (worst-category-wins),
  filterable by family and verdict, with ★ marking the best rows all-round.
  **Margin %** is how far the weakest applicable metric sits from its red
  boundary as a fraction of the green→red span, discounted by how far the model
  is trusted for that number (100% = exactly the green bound; above 100% = extra
  headroom). **Valid** goes orange when the design sits outside the envelope the
  model has actually been checked in — never green there, and never red on those
  grounds alone. Pick any point to drill into its swept params, score reasons,
  per-metric margins and trust tiers, and raw family-native metrics.
- **Plots tab** — the standard plot set with the same *best-3* and *references*
  toggles as the static workbook.
- **Provenance & export tab** — model git hash, run timestamp, resolved
  constants, and the verbatim config. One button builds the self-contained HTML
  chapter into `book/` and offers it as a download.

## Notes

- The UI changes nothing about the model, the family contract, or the scoring —
  it calls `stepgen.studio` and `stepgen.families` exactly as the batch command
  does. A bad YAML edit surfaces an in-app error rather than crashing.
- The pure helpers in `stepgen/studio/ui.py` (`scored_dataframe`,
  `category_frame`, `plot_pngs`, …) are deliberately separated from the `st.*`
  rendering so they are unit-tested headless (`tests/test_studio_ui.py`), and the
  full app is smoke-tested via Streamlit's `AppTest` harness.
