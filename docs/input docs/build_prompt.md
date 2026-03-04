You are a senior Python engineer implementing a microfluidic step-emulsification device design tool called stepgen. You are working from an existing script that solves a ladder hydraulic resistor network using sparse linear algebra. You must refactor and extend the repo into a config-driven pipeline with sweeps, operating maps, schematic layout preview, and experiment comparison. Do NOT implement CAD/GDS export.

High-level context:
- Device: two long main channels (oil and water) connected by N microchannels (rungs).
- Current code computes resistances from rectangular channel approximations and solves pressures with spsolve.
- Real physics: step droplet generators have capillary thresholds and can show reverse flow bands mid-device when water pressure exceeds oil locally. We will model this with a reduced-order threshold/hysteresis rung element (not CFD).
- User goals: design sweep to maximize throughput subject to constraints; evaluate tradeoff between uniformity constraints (e.g., ΔP flatness 5% vs 10%) and throughput; compute operating window width; show schematic footprint fit in 10 cm^2; predict droplet size via empirical mapping from exit width/depth; compare to experiments.

Must-have features (v1):
1) Refactor into a package stepgen/ with modules:
   - config.py: parse YAML into dataclasses, unit conversions
   - models/resistance.py: rectangular resistance formulas; support microchannel_profile with piecewise sections
   - models/hydraulics.py: build ladder sparse matrix and solve for pressures in the linear case
   - models/generator.py: threshold/hysteresis rung regime model with iterative solve wrapper
   - models/droplets.py: droplet diameter prediction from exit_width & exit_depth; default power-law D=k*w^a*h^b; compute frequency f_i = Q_d,i / Vd
   - models/metrics.py: Q uniformity, ΔP uniformity, active/reverse/off fractions, delam & collapse heuristic indices
   - design/layout.py: schematic block + serpentine packing within footprint_area_cm2; outputs fits_footprint, num_lanes, etc; plot schematic
   - design/sweep.py: run parameter sweep from YAML ranges; store results as DataFrame; apply hard constraints; compute soft metrics
   - design/operating_map.py: run grid over Po_in and Qw_in; compute heatmaps; extract operating windows (strict and relaxed)
   - io/results.py: save/load parquet/csv; export candidate JSON
   - io/experiments.py: read experiments CSV; compare predicted vs measured; calibration stub optional
   - viz/plots.py: standardized plots
   - cli.py: argparse/typer CLI (choose argparse if you want zero extra deps)
2) Mixed boundary condition simulation (primary):
   - Inputs: oil inlet pressure Po_in_mbar, water inlet flow Qw_in_mlhr, outlet pressure reference P_out_mbar (default 0).
   - Solve for full pressures and resulting oil flow Q_oil_total.
   - Provide a function simulate(candidate, Po_in_mbar, Qw_in_mlhr, P_out_mbar=0) -> result object with profiles + metrics.
   - Implement by augmenting the linear system to pin inlet node pressure on oil side while injecting known flow on water side (and a sink/outlet reference).
3) Threshold/hysteresis rung element:
   - For rung i, ΔP_i = P_o,i - P_w,i.
   - Regimes:
     * oil→water active if ΔP_i > dP_cap_ow
     * water→oil reverse if ΔP_i < -dP_cap_wo
     * otherwise off/pinned (Q≈0)
   - Implement iterative solve:
     a) solve linear open system to get initial ΔP
     b) classify each rung
     c) rebuild system: off rungs get very small conductance; active rungs include threshold offset as affine term
     d) resolve; repeat until classifications stable or max iterations
   - Keep numerically stable; avoid singular matrices.
4) Schematic layout preview (NOT CAD):
   - Two blocks for main channels and one block between for active region, scaled to widths/lengths.
   - Serpentine packing to fit within footprint_area_cm2 and a chosen aspect ratio. Do not draw microchannels individually.
   - Provide a check that Mcl fits or compute max Mcl feasible.
5) Sweep engine:
   - YAML ranges for variables (grid or sampling).
   - For each candidate, compute Nmc, check footprint fit, run simulation at a "design operating point" from config, compute metrics.
   - Additionally compute operating window widths by scanning Po at fixed Qw (at least one Qw).
   - Produce a results.parquet/csv with all metrics.
   - Provide Pareto plots: throughput vs window width; throughput vs uniformity.
6) Operating map:
   - Given candidate JSON and Po/Qw ranges, compute heatmaps for active_fraction, reverse_fraction, Q_uniformity_pct, ΔP_uniformity_pct, f_mean, max ΔP.
   - Extract operating windows with user-defined acceptance criteria (strict and relaxed thresholds).
7) Experiment comparison:
   - Read experiments CSV with columns: device_id, Po_in_mbar, Qw_in_mlhr, position, droplet_diameter_um, frequency_hz, notes.
   - Compare predicted diameter/frequency at approximate positions (start/mid/end mapping to indices).
   - Output plots and summary residuals. Calibration can be stubbed (function placeholders).
8) CLI commands:
   - stepgen simulate config.yaml --Po 200 --Qw 5
   - stepgen sweep config.yaml
   - stepgen report outputs/results.parquet --top 10
   - stepgen map candidate.json --Po 0:800:81 --Qw 0:20:41
   - stepgen compare candidate.json experiments.csv
9) Tests:
   - Unit tests for resistance calculations and ladder solver on small N.
   - Golden test to match current script outputs in linear mode (within tolerance).
   - Test for reverse band classification on a constructed scenario.

Constraints:
- Keep dependencies minimal: numpy, scipy, pandas, matplotlib, pyyaml.
- Use dataclasses and type hints.
- No global variables; all config-driven.
- Make outputs reproducible.
- Build an examples/ folder with at least:
  - example_single.yaml (simulate)
  - example_sweep.yaml (sweep)
  - example_operating_map.yaml (map settings)
- Save outputs to outputs/ by default.

Start by:
A) Summarizing the existing script behavior.
B) Refactoring the linear hydraulics solver into models/hydraulics.py + models/resistance.py with tests.
C) Adding mixed BC simulation.
D) Adding threshold/hysteresis solver wrapper.
E) Adding droplet model + metrics.
F) Adding layout preview.
G) Adding sweep + operating map.
H) Adding experiment compare.
I) Adding CLI.
J) Final README.

Deliverables:
- Updated repository code
- README with commands
- Example configs
- Tests that pass