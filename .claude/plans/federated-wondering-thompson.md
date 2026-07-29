# Plan: Standardise the analysis pipeline to DB format

## Context

Three tools exist that should form a clean pipeline but currently don't:

1. **`combined_measure.py`** (`drop_freq` repo) — video annotation tool that outputs `stage_timings.csv` with CamelCase columns and an old filename convention.
2. **`analysis_ingest.py`** (`DB` repo) — imports analysis CSVs into the DB, but expects lowercase columns and a formal filename convention.
3. **`design_model`** — needs a CSV with `frequency_hz` (derived from stage times) and design-level identifiers — not currently produced by either tool.

The fix: standardise everything to the DB convention. Videos get the formal name, `combined_measure.py` outputs the format `analysis_ingest.py` already expects, and the DB web app gains a filtered export that produces design_model-ready CSVs. Old workspace data (V5-8-1 / po_sweep) predates the DB entirely and is not migrated — it stays as-is in the workspace.

---

## Formal filename convention (already defined in `DB/scripts/analysis_ingest.py`)

```
V5-30_M002_S017_20260405-1A_BD0505_SDS_SO_200mbar_5mlhr_DFU1.mp4
^^^^^                design_id
       ^^^^          master_num  (M001 → 1)
            ^^^^     shim_num    (sequential per master)
                 ^^^^^^^^ replica press date YYYYMMDD
                          ^^  run_num
                            ^ position (A–D)
                              ^^^^  bond_date DDMM
                                   ^^^  cont_phase
                                        ^^  disp_phase
                                            ^^^^^^  pressure_mbar
                                                    ^^^^^  flow_rate_mlhr
                                                           ^^^^  DFU id
```

The `_FNAME_RE` regex in `analysis_ingest.py` (line 54) is the authoritative parser.

---

## Repo 1 — `drop_freq` → `combined_measure.py`

### A. `parse_filename_metadata()` (lines 604–676)

Rewrite to use `_FNAME_RE` (copy the regex from `analysis_ingest.py` — the repos have no import relationship). Extend the regex with an optional note suffix before the extension:

```python
_FNAME_RE = re.compile(
    r'^(?P<design>.+?)_M(?P<mnum>\d+)_S(?P<shim>\d+)'
    r'_(?P<rd>\d{8})-(?P<run>\d+)(?P<pos>[A-Da-d])'
    r'_BD(?P<bd>\d{4})'
    r'_(?P<cont>[^_]+)_(?P<disp>[^_]+)'
    r'_(?P<pmbar>\d+(?:\.\d+)?)mbar'
    r'_(?P<mlhr>\d+(?:\.\d+)?)mlhr'
    r'_DFU(?P<dfu>\d+)'
    r'(?:_(?P<note>[^.]+))?'        # optional trailing annotation e.g. _defect
    r'\.(mp4|avi|mov)$',
    re.IGNORECASE,
)
```

- If no match: abort Mode 2 immediately with a printed error showing the expected format. No fallback to the old convention.
- Return dict with keys: `design_id`, `master_num`, `shim_num`, `run_num`, `position`, `cont_phase`, `disp_phase`, `pressure_mbar`, `flow_rate_mlhr`, `dfu_id`, `note`, `analysis_date`.

The validation fires at line 896 in `run_stage_timing_mode()`, where `parse_filename_metadata()` is called — this is at Mode 2 entry, before any stage-click interaction. Mode 1 (ROI / meniscus annotation) is unaffected.

Update the console print at line 899 to show the new field names.

### B. `save_stage_timings()` (lines 1085–1128)

Change output columns from CamelCase metadata-heavy format to the format expected by `analysis_ingest.py` bulk CSV mode:

```
video_filename, roi_id, stage1_s, stage2_s, stage3_s,
l_menpoint_um, l_men_um, droplet_diameter_um,
calibration_px_per_um, analysis_version, analysis_date, note
```

- `video_filename` = `self.video_name` (basename only — including any `_defect` suffix, so the full actual filename is preserved)
- `roi_id` = `self.rois[self.mode2_roi_idx]['id']`
- `analysis_version` = `"combined_measure_v2"`
- `note` = parsed from filename (e.g. `"defect"`, or empty string)
- Remove all old metadata columns (DeviceID, ContPhase, etc.) — now in filename, parsed by `analysis_ingest.py`
- Output file: same path (`<video_dir>/results/stage_timings.csv`), append mode preserved
- **Old-format guard**: if the existing CSV has `VideoFile` (CamelCase) as a column, it is old-format. Print a clear warning and refuse to append — operator must rename the old file before continuing. Do not silently overwrite or corrupt old data.

### C. `analysis_ingest.py` — regex extension only

Add the same optional note suffix group to `_FNAME_RE` in `analysis_ingest.py` (one line addition). The `note` column in the CSV is not in `_ROI_COLS` and is silently ignored on ingest — it does not enter the DB. No other changes to `analysis_ingest.py`.

### D. No other changes needed

`_extract_dfu_info()`, `find_sibling_videos()`, `find_next_video()` all pattern-match on `_DFU<n>` which is present in the new convention. No changes required.

---

## Repo 2 — `DB`

### A. `scripts/export.py` — new export function

Add `export_design_model_csv()` following the exact pattern of the existing three functions (`export_analysis_flat`, `export_device_history`, `export_qc_summary`).

Core SQL:

```sql
SELECT
    d.design_id                                        AS device_id,
    t.pressure_mbar                                    AS Po_in_mbar,
    t.flow_rate_mlhr                                   AS Qw_in_mlhr,
    ar.dfu_id                                          AS position,
    ar.droplet_diameter_um,
    CASE
        WHEN ar.stage1_s > 0
         AND ar.stage2_s > 0
         AND ar.stage3_s IS NOT NULL AND ar.stage3_s > 0
        THEN 1.0 / (ar.stage1_s + ar.stage2_s + ar.stage3_s)
        ELSE NULL
    END                                                AS frequency_hz,
    ar.stage1_s, ar.stage2_s, ar.stage3_s,
    ar.l_menpoint_um, ar.l_men_um,
    t.cont_phase, t.disp_phase, t.cont_conc,
    ar.test_id, dev.device_uid
FROM analysis_results ar
JOIN tests t     ON ar.test_id      = t.test_id
JOIN devices dev ON t.device_uid    = dev.device_uid
JOIN replicas r  ON dev.replica_id  = r.replica_id
JOIN shims s     ON r.shim_id       = s.shim_id
JOIN designs d   ON s.design_id     = d.design_id
WHERE ar.stage1_s IS NOT NULL
  AND ar.stage2_s IS NOT NULL
```

Function signature:
```python
def export_design_model_csv(conn, out_path: Path,
                             design_id: str | None = None,
                             pressure_mbar: list[float] | None = None,
                             flow_rate_mlhr: list[float] | None = None,
                             cont_phase: str | None = None,
                             disp_phase: str | None = None) -> int
```

Appends WHERE clauses dynamically using parameterised queries (no string interpolation).

### B. `web/blueprints/exports.py` — new route

Add `/exports/design-model` (GET only). If query params are absent, render the filter form template. If params are present, stream the CSV download — same `_stream_csv` helper pattern extended to pass filter kwargs. Calls `export_design_model_csv()`.

### C. `web/templates/exports/index.html` — 4th button

Add a 4th link button in the existing `d-grid gap-2` div, matching the style of the other three:
```html
<a href="{{ url_for('exports.design_model') }}" class="btn btn-outline-primary">
  <strong>design_model.csv</strong>
  <br><small class="text-muted">Filtered export for design model input</small>
</a>
```

### D. New template `web/templates/exports/design_model.html`

Filter form page. On GET with no params: renders the form. Form submits `method="get"` to itself. On GET with params present: route handler streams the CSV download (see route above).

Form fields:
- Design ID `<select>` (populated from `SELECT DISTINCT design_id FROM designs ORDER BY design_id`)
- Continuous phase `<select>` (populated from distinct `cont_phase` values in `tests`)
- Dispersed phase `<select>` (populated from distinct `disp_phase` values in `tests`)
- Pressure `<select multiple>` (populated from distinct `pressure_mbar` values in `tests`)
- Flow rate `<select multiple>` (populated from distinct `flow_rate_mlhr` values in `tests`)
- Download button (submits the form)

### E. `web/blueprints/tests.py` — analysis upload route

Add a `POST /tests/upload-analysis` route. `tests.py` already imports from `analysis_ingest`, so `_process_bulk_csv` is directly importable.

Flow:
1. Operator clicks an "Upload Analysis" button (anywhere sensible — dashboard or tests index page)
2. File picker opens, operator selects their `stage_timings.csv`
3. Server saves to a temp file, calls `_process_bulk_csv(tmp_path, conn, stats)`, deletes the temp file
4. Redirects back with a flash message: "Ingest complete — N rows added, M skipped, K failed"

No new template needed — use `flash()` and redirect to referer. A simple `<form action="/tests/upload-analysis" method="post" enctype="multipart/form-data">` with a file input and submit button. Place this form on the tests index page or dashboard, wherever the operator naturally lands after annotation.

---

## Repo 3 — `design_model`

### A. `CLAUDE.md` — update data sourcing section

In the "Data provenance" section, replace `@exp-YYYY-MM-DD-device` identity convention with `test_id` from the DB.

Add a "Getting data from the DB" subsection:
- Navigate to DB web app `/exports/design-model`
- Filter by design ID, pressure range, flow rate, phases
- Download CSV → place in workspace `data/`
- Record `test_id`s used in `BRIEF.md ## Data sources` table
- Run manifest records which DB filters were applied

### B. `experimental_workspaces/_template/BRIEF.md`

Update `## Data sources` table — change `ID` column from `@exp-YYYY-MM-DD-device` to `test_id` (DB primary key). Add note: "query via DB web app or `legacy` if pre-DB data."

---

## Verification (end-to-end)

1. **`combined_measure.py`**: Record a test video named with the formal convention, run Mode 2, confirm `stage_timings.csv` has `video_filename` (first column) and all lowercase column names.
2. **Web upload**: Use the upload form to submit the new `stage_timings.csv` — flash message reports rows added with no failures.
3. **DB records**: Query `tests` and `analysis_results` — new rows present with correct device_uid, conditions, and `analysis_version = "combined_measure_v2"`.
4. **DB export**: Open `/exports/design-model`, filter by `V5-30`, download CSV — columns `device_id, Po_in_mbar, Qw_in_mlhr, position, droplet_diameter_um, frequency_hz` present and `frequency_hz` > 0.
5. **design_model load**: Pass exported CSV to `load_experiments()` — passes schema validation, no missing-column errors.
