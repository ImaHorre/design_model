# StepGen Designer — Future Features & PRD v2

Features identified but deferred. Add new items here whenever an idea comes up
during a session rather than implementing immediately.

---

## Design Search — Automation & UX

### DS-1: `stepgen junction-geometry` CLI helper
Print derived geometry from droplet target so user doesn't have to calculate manually.
```
stepgen junction-geometry --target-droplet 15 --ar-min 2.5 --ar-max 3.0
→ mcd_derived:  6.3 µm  (set mcw_um to ~6.3 for rung AR ≈ 1)
→ exit_width:   16.8 µm (at AR midpoint 2.75)
→ pitch:        33.5 µm (2 × exit_width)
```

### DS-2: Auto-derive `mcw` from `mcd`
Remove `mcw_um` from `sweep_ranges`. Derive it from `mcd` using a configurable
rung cross-section AR (default 1.0). User sets `rung_ar: 1.0` in design_targets
or hard_constraints. This is the last manually-computed geometry the user has to
provide themselves.

### DS-3: Rung cross-section AR hard constraint
Add `min_rung_ar` / `max_rung_ar` to `DesignHardConstraints` (e.g. defaults
0.5 / 2.0). Checks `mcw / mcd` in the pre-filter. Catches rungs that are
pathologically wide or narrow relative to their depth.

### DS-4: `min_feature_width_um` auto-derived from `mcd`
Once `mcd` is fully derived from the droplet target, `min_feature_width_um`
becomes redundant as a separate user input — it should just equal `mcd`.
Remove from hard_constraints YAML and set internally.

### DS-5: Qw optimisation mode
Instead of evaluating at a fixed `Qw_in_mlhr`, find the maximum Qw that keeps
`Po_in_mbar` below `max_Po_in_mbar`. Makes `Qw_in_mlhr` a result not an input.
Requires a 1D search (bisection) per candidate geometry.

### DS-6: Smarter sampling — Latin hypercube / Bayesian optimisation
Replace brute-force Cartesian grid with Latin hypercube sampling for the first
pass, or Bayesian optimisation for iterative refinement. Reduces number of
solves needed to find the Pareto front.

### DS-7: Automated sensitivity / monotonicity detection
After a sweep, analyse which parameters trend monotonically with the objective
(e.g. Mcd always at max is always best). Flag these to the user so they can
be fixed on the next pass, reducing the sweep dimension.

### DS-8: Pareto front (deferred from roadmap Step 6)
`plot_pareto()` already exists. Needs integration with robustness sweep so the
front can be plotted over (throughput, window_width) axes. Waiting on DS-5 or
`compute_robustness=True` sweep integration.

---

## Physics Model

### PM-1: Blowout pressure model
Upper oil pressure limit for monodisperse droplet formation. Currently no model.
Physically: blowout occurs when ΔP_rung >> dP_cap_ow (capillary threshold).
Likely `ΔP_rung_max = f × dP_cap_ow` where `f` is empirical (~3–10×, geometry
dependent). Requires experimental calibration data. Hook into Stage H experiment
ingestion once data exists.

### PM-2: `max_freq_spread_pct` soft constraint not implemented
The check in `_check_soft_constraints` is a placeholder (`pass`). Needs a
dedicated `freq_spread_pct` metric computed per candidate and compared
against the soft limit.

### PM-3: Rung expansion section resistance
The pre-junction rung widening (last ~10% of rung length expands from `mcw` to
`exit_width`) is currently not modelled in hydraulic resistance. The full rung
is treated as uniform width `mcw`. A small correction term could be added once
the geometry is better characterised.

### DS-9: Multi-criteria scoring system
Add `score_candidates(df, weights=None) → pd.DataFrame` in a new `stepgen/design/scoring.py`.
Combines Q_total (positive), Po_required (negative), Q_spread (negative),
active_fraction (positive) into a single `score` column [0–100] after per-metric
normalisation to [0,1]. Hard-failing candidates always score 0. Default weights:
```python
DEFAULT_WEIGHTS = {
    "Q_total_mlhr":      1.0,
    "Po_required_mbar": -0.5,
    "Q_spread_pct":     -0.3,
    "active_fraction":   0.5,
}
```
Call automatically at end of `run_design_search`; add `score` column to CSV output.
Add `optimization_target: max_score` as alternative to `max_throughput`.

### DS-10: 3D design-space plot
Add `plot_design_space_3d(df, x_col='Mcw_um', y_col='mcl_rung_um', z_col='Q_total_mlhr',
color_col='score') → Figure` to `stepgen/viz/plots.py`.
Uses `mpl_toolkits.mplot3d` (no new dependency). Passing candidates coloured by
score (viridis), failing candidates as small grey dots. Shows the user the shape
of the feasible region and which direction to move the sweep.
Interactive/rotatable in notebook/GUI; saved as static PNG by CLI at
`design_results_3d.png` (elev=25, azim=45 default angle).
Inspired by legacy sweep visualisation code.

### DS-13: Add device area + Mcl to results output
Add a computed column `device_area_mm2 = Mcl_derived_mm × Mcw_um × 1e-3` to the
`run_design_search` output DataFrame. Update the `stepgen design` CLI summary line
to also print `Mcl` and `area`:
```
Top candidate : Mcd=200µm  Mcw=1000µm  Mcl=42.3mm  area=423mm²  Nmc=211  Q_total=10.00 mL/hr  Po=487.2 mbar
```
`Mcl_derived_mm` and `Mcw_um` are already in the CSV; this makes them visible at
a glance in the terminal without opening the file.

### DS-14: Rework design search plots — swept-parameter scatter grid
The current `plot_design_results` two-panel layout has poor signal-to-noise:
- **Left panel** (ranked bar chart of Q_total): useless — just re-shows the sorted
  CSV as a picture. Replace entirely.
- **Right panel** (Po vs Q scatter, pass/fail coloured): okay but anonymous — dots
  don't reveal which swept variables drove each result.

**Replacement**: a 2×3 grid of small scatter panels (one per swept axis), each
showing that axis vs `Q_total_mlhr`. Points coloured by `Po_required_mbar`
(viridis colormap with shared scale), passing candidates as filled circles,
failing as hollow crosses. A single shared colourbar on the right edge.

Swept axes to panel: `Mcd_um`, `Mcw_um`, `junction_ar`, `mcw_um`, `mcl_rung_um`
plus one summary panel of `device_area_mm2` vs `Q_total_mlhr`.

This directly answers "which swept variable drove throughput / pressure?"
and whether the optimum is at the boundary of the swept range (signalling the
range should be extended). Relates to DS-10: the 3D plot is the interactive/full
version; this grid is the static printable complement saved as `design_results_plot.png`.

### ~~UX-3: Rung plots use mm position on x-axis~~ ✓ IMPLEMENTED
All four rung-level report plots (`rung_dP`, `rung_flows`, `rung_frequencies`,
`regime_map`) now use position along channel [mm] on the x-axis instead of
rung index, consistent with `pressure_profiles`. Bar widths derived from pitch.
Also added `Qo` (total oil flow, mL/hr) to `simulate` output.

### UX-4: Interactive y-axis switching in `report` plots
Currently each metric (ΔP, Q_rung, frequency) is a separate saved PNG.
A future `stepgen report --interactive` flag (or Jupyter widget) would let the
user switch the y-variable on a single spatial plot without re-running.
Deferred — low priority since the separate PNGs cover the use case.

### ~~UX-2: Richer `simulate` output — absolute rung metrics~~ ✓ IMPLEMENTED
Added `f_pred_min`, `f_pred_max`, `dP_avg` to `DeviceMetrics`. The `simulate`
output now shows mean flow per rung (nL/hr), mean rung ΔP (mbar), and
frequency min/max alongside mean so non-uniformity percentages can be
interpreted in absolute terms.

### ~~UX-1: Hard constraint failure detail in `simulate` output~~ ✓ IMPLEMENTED
Replace the single `hard OK : False` line with a per-constraint breakdown showing
exactly which constraint was violated and by how much. Example:
```
  hard OK : False
    ✗ footprint too large for chip
    ✗ Mcd (250µm) > max_main_depth (200µm)
```
Requires refactoring `_passes_hard_constraints` in `sweep.py` to return
`list[str]` of failure messages instead of a bool, storing them in the row as
`hard_constraint_failures`, and updating `_cmd_simulate` in `cli.py` to print
each failure on its own indented line. `passes_hard_constraints` (bool) stays
in the row for CSV/sweep compatibility, derived as `len(failures) == 0`.

---

## Workflow

### WF-1: Iterative sweep automation
Allow chaining of design searches: first-pass results automatically tighten the
sweep ranges for a second pass. Could be a `stepgen design --refine` flag that
takes a previous results CSV and generates a narrowed YAML.

---

## Operating Pressure — Advanced Approaches

### DS-11: Mode A design search (fix Po, vary geometry)
Instead of Mode B (fix Qw + Qo, derive Po), accept `Po_target_mbar` and `Qw_in_mlhr`
as fixed design inputs and search for geometries that produce the target droplet size
at that operating point. Makes Po a first-class design input rather than a derived
result, eliminating the "optimizer rides to the pressure limit" problem. Requires a
Mode A evaluator path in `run_design_search` (call `evaluate_candidate` with `Po=`
rather than `Qo_in_mlhr=`). Bigger refactor but more physically principled for
users who know their pressure supply capability.

### DS-12: Droplet frequency target as hard constraint
Add `max_droplet_freq_hz` (and optionally `min_droplet_freq_hz`) to
`DesignHardConstraints`. A frequency ceiling bounds Q_oil per rung, which
indirectly caps the derived Po for Mode B searches. Less direct than DS-11
but simpler to implement and intuitive for users who think in terms of
droplet production rate rather than pressure.

### PM-4: Minimum Laplace / capillary pressure (low-Po stall)
Compute the minimum Po required for droplet formation at a junction:
`P_Laplace ≈ 4 × gamma_ow / exit_depth` (simplified spherical cap).
Use as a dynamic lower bound on the operating window — if derived Po < P_Laplace
the device cannot form droplets (oil stays in the rung). Extends PM-1 (blowout,
high-Po limit) to also cover the low-pressure stall regime.
Requires `gamma_ow` (oil-water interfacial tension, Pa·m) in `FluidConfig`
(currently absent; typical value ~5–15 mN/m for PDMS-oil/water systems).
