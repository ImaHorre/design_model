"""
stepgen.studio.ui
=================
Phase 4 — the interactive Design Studio (Streamlit front-end).

This is a thin, *interactive* skin over the exact same declarative pipeline the
``stepgen study`` CLI already uses::

    load_study_text -> run_study -> score_result -> _build_plots -> workbook

Nothing here changes the model, the family contract, or the scoring. It lets you
edit a study YAML live, run it, browse the scored comparison table, drill into
any point, view the standard plots (with the same best-3 / references toggles as
the static workbook), and export the self-contained HTML chapter.

Both study front doors work here: a hand-written grid, or an ``intent:`` block
that generates one. The Diagnosis tab shows what an intent turned into, which
gate is standing in the way, and — behind a button, because it costs a full
re-run per constraint — what relaxing each active constraint would buy.

Launch::

    stepgen studio-ui [study.yaml]          # via the CLI wrapper
    streamlit run stepgen/studio/ui.py -- [study.yaml]   # directly

Design note
-----------
The module is split so that everything *not* requiring a running Streamlit
context (``scored_dataframe``, ``category_frame``, ``plot_pngs``) is a plain
function that unit tests can call without a browser. The ``st.*`` calls all live
inside :func:`render` / :func:`main`, which run only under ``streamlit run``.
"""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from stepgen.families import list_families
from stepgen.studio.run import StudyResult, resolved_constants, run_study
from stepgen.studio.scoring import ScoredRow, score_result
from stepgen.studio.study import Study, load_study_text
from stepgen.studio.workbook import (
    _CAT_COLOR,
    _COLUMNS,
    _best_indices,
    _build_plots,
    write_workbook,
)

# repo root (…/design_model) — used to locate configs/ and default the book dir
_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_DIR = _REPO_ROOT / "configs"

# columns of the scored table that carry a traffic-light category
_VALUE_KEYS = [k for k, _ in _COLUMNS]


# ---------------------------------------------------------------------------
# Pure helpers (no Streamlit runtime required — unit-testable)
# ---------------------------------------------------------------------------

def scored_dataframe(scored: list[ScoredRow], best: set[int]) -> pd.DataFrame:
    """
    One display row per scored point, in the same column order as the static
    workbook's overview table. Values are formatted for display; the traffic
    light categories live in the parallel :func:`category_frame`.
    """
    rows: list[dict[str, Any]] = []
    for i, sr in enumerate(scored):
        m = sr.metrics
        row: dict[str, Any] = {
            "#": i + 1,
            "★": "★" if i in best else "",
            "Config": m.label,
            "Family": m.family,
            "Verdict": sr.overall,
        }
        for key, header in _COLUMNS:
            row[header] = getattr(m, key, None)
        disc = sr.min_margin_discounted
        row["Margin %"] = None if disc is None else round(disc * 100, 1)
        row["Weakest link"] = sr.weakest_metric or ""
        build = sr.cells.get("build")
        row["Build"] = build.category if build else "grey"
        validity = sr.cells.get("validity")
        row["Valid"] = validity.category if validity else "grey"
        row["Reasons"] = " · ".join(sr.chips)
        rows.append(row)
    return pd.DataFrame(rows)


def category_frame(scored: list[ScoredRow], df: pd.DataFrame) -> pd.DataFrame:
    """
    A frame the same shape as *df* whose cells hold the traffic-light category
    (``green``/``orange``/``red``/``grey``) for the coloured columns, and ``""``
    elsewhere. Consumed by the Streamlit Styler.
    """
    cats = pd.DataFrame("", index=df.index, columns=df.columns)
    for i, sr in enumerate(scored):
        cats.at[i, "Verdict"] = sr.overall
        build = sr.cells.get("build")
        cats.at[i, "Build"] = build.category if build else "grey"
        validity = sr.cells.get("validity")
        cats.at[i, "Valid"] = validity.category if validity else "grey"
        for key, header in _COLUMNS:
            cell = sr.cells.get(key)
            if cell is not None:
                cats.at[i, header] = cell.category
        # a margin under a fifth of the green->red span is marginal, not safe
        disc = sr.min_margin_discounted
        if disc is not None:
            cats.at[i, "Margin %"] = ("red" if disc < 0.2
                                      else "orange" if disc < 0.5 else "green")
    return cats


def plot_pngs(scored: list[ScoredRow], goal: str, refs=None) -> list[dict[str, Any]]:
    """
    Build the standard plot set and decode each variant's base64 data-URI into
    raw PNG bytes so Streamlit can render them with ``st.image``. Reuses the
    workbook's plot builders verbatim, so the app and the exported HTML show the
    identical figures.
    """
    out: list[dict[str, Any]] = []
    for p in _build_plots(scored, goal, refs or []):
        images = {
            key: base64.b64decode(uri.split(",", 1)[1])
            for key, uri in p["variants"].items()
        }
        out.append({
            "title": p["title"],
            "caption": p["caption"],
            "has_best": p.get("has_best", False),
            "has_ref": p.get("has_ref", False),
            "images": images,
        })
    return out


def variant_key(best: bool, ref: bool) -> str:
    """Pick the plot-variant key for the requested toggle state."""
    if best and ref:
        return "bestref"
    if best:
        return "best"
    if ref:
        return "ref"
    return "base"


def discover_studies() -> list[Path]:
    """Every ``study_*.yaml`` shipped in ``configs/`` (newest study configs)."""
    if not _CONFIG_DIR.is_dir():
        return []
    return sorted(_CONFIG_DIR.glob("study_*.yaml"))


# ---------------------------------------------------------------------------
# Cached compute (Streamlit) — keyed on the study text so edits re-run
# ---------------------------------------------------------------------------

def _compute(text: str, source_path: str | None) -> dict[str, Any]:
    """
    Run the whole pipeline for a study *text* and package everything the view
    needs. Pulled out of :func:`render` so it can be wrapped in ``st.cache_data``
    (see :func:`_cached_compute`).
    """
    from stepgen.studio.references import resolve_references

    study = load_study_text(text, source_path=source_path)
    result = run_study(study)
    scored = score_result(result, study.scoring)
    refs = resolve_references(study)
    best = set(_best_indices(scored, study.goal, spec=study.decide))

    df = scored_dataframe(scored, best)
    cats = category_frame(scored, df)
    plots = plot_pngs(scored, study.goal, refs)

    return {
        "study": study,
        "result": result,
        "scored": scored,
        "refs": refs,
        "best": best,
        "df": df,
        "cats": cats,
        "plots": plots,
    }


# ---------------------------------------------------------------------------
# Streamlit rendering (requires a running `streamlit run` context)
# ---------------------------------------------------------------------------

def _style_cell(category: str) -> str:
    if category in _CAT_COLOR:
        colour = _CAT_COLOR[category]
        # tint the background, keep text legible
        return f"background-color:{colour}22;color:{colour};font-weight:600"
    return ""


def render(initial_path: str | None = None) -> None:
    """The whole interactive app. Imports Streamlit lazily so unit tests that
    import this module never require a Streamlit runtime."""
    import streamlit as st

    st.set_page_config(page_title="StepGen Design Studio", layout="wide",
                       page_icon="🔬")

    cached_compute = st.cache_data(show_spinner="Running study…")(_compute)

    st.title("🔬 StepGen Design Studio")
    st.caption("Edit a study, run it, and compare topology families on one "
               "scored table — the same pipeline as `stepgen study`, live.")

    # ── sidebar: choose + edit the study YAML ───────────────────────────────
    with st.sidebar:
        st.header("Study")
        studies = discover_studies()
        options = ["(paste / upload below)"] + [str(p.relative_to(_REPO_ROOT)) for p in studies]

        default_idx = 0
        if initial_path:
            rel = _rel_to_repo(initial_path)
            if rel in options:
                default_idx = options.index(rel)
        chosen = st.selectbox("Config", options, index=default_idx)

        uploaded = st.file_uploader("…or upload a study YAML", type=["yaml", "yml"])

        text = _initial_text(chosen, uploaded, initial_path)
        source_path = None if chosen == options[0] else str(_REPO_ROOT / chosen)

        text = st.text_area("Study YAML (edit freely)", value=text, height=380,
                            key="study_text")
        run = st.button("▶ Run study", type="primary", width="stretch")

    if run:
        st.session_state["run_text"] = text
        st.session_state["run_source"] = source_path

    run_text = st.session_state.get("run_text")
    if not run_text:
        st.info("Pick or paste a study on the left, then press **Run study**.")
        _families_hint(st)
        return

    try:
        data = cached_compute(run_text, st.session_state.get("run_source"))
    except Exception as exc:  # a bad YAML edit must not crash the app
        st.error(f"Could not run this study: {exc}")
        return

    _render_results(st, data)


def _render_results(st, data: dict[str, Any]) -> None:
    study: Study = data["study"]
    result: StudyResult = data["result"]
    scored: list[ScoredRow] = data["scored"]
    df: pd.DataFrame = data["df"]
    cats: pd.DataFrame = data["cats"]

    n_green = sum(1 for s in scored if s.overall == "green")
    n_orange = sum(1 for s in scored if s.overall == "orange")
    n_red = sum(1 for s in scored if s.overall == "red")

    from stepgen.studio.ranking import resolve_axes

    axis_names = ", ".join(a.key for a in resolve_axes(study.decide, study.goal))
    st.subheader(study.title or "Untitled study")
    st.caption(f"Deciding on: **{axis_names}**  ·  Families: "
               f"{', '.join(study.families)}  ·  {len(scored)} configs")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Configs", len(scored))
    c2.metric("🟢 Green", n_green)
    c3.metric("🟠 Orange", n_orange)
    c4.metric("🔴 Red", n_red)

    tab_decide, tab_diag, tab_table, tab_plots, tab_prov = st.tabs(
        ["Decision", "Diagnosis", "Scored comparison", "Plots",
         "Provenance & export"])

    with tab_decide:
        _render_decision(st, scored, study)

    with tab_diag:
        _render_diagnosis(st, study, scored)

    with tab_table:
        _render_table(st, scored, df, cats)

    with tab_plots:
        _render_plots(st, data["plots"])

    with tab_prov:
        _render_provenance(st, result, study)


def _render_decision(st, scored: list[ScoredRow], study: Study) -> None:
    """
    The decide layer, with the composite weights live on sliders.

    Re-ranking is pure — it reads the already-solved rows — so moving a slider
    never re-runs the physics, and the batch and interactive paths still produce
    identical numbers for identical weights.
    """
    from stepgen.studio.ranking import (
        axis_value, decide, resolve_axes, resolve_weights, row_specific_breaches,
    )

    if not scored:
        st.info("No rows to decide between.")
        return

    axes = resolve_axes(study.decide, study.goal)
    defaults = resolve_weights(study.decide, axes)

    st.caption("Per-axis winners and the Pareto set are the finding. The composite "
               "is a convenience for ordering — its weights are yours to set, and "
               "whatever you leave them at is what gets recorded in the chapter.")

    with st.expander("Composite weights", expanded=True):
        cols = st.columns(len(axes))
        weights = {
            axis.key: col.slider(axis.label, 0.0, 1.0,
                                 float(defaults.get(axis.key, 0.0)), 0.05,
                                 key=f"w_{axis.key}")
            for axis, col in zip(axes, cols)
        }
        if sum(weights.values()) <= 0:
            st.warning("All weights are zero — falling back to the study's weights.")
            weights = defaults

    dec = decide(scored, study.decide, study.goal, weights_override=weights)

    # ── the four picks ──────────────────────────────────────────────────────
    st.markdown("#### Per-axis winners")
    cols = st.columns(len(dec.axes))
    for axis, col in zip(dec.axes, cols):
        i = dec.per_axis.get(axis.key)
        if i is None:
            col.metric(axis.label, "—", help="N-A for every row")
            continue
        value = axis_value(scored[i], axis)
        shown = f"{value * 100:.0f}%" if axis.key == "margin" else f"{value:.4g}"
        col.metric(axis.label, shown, help=scored[i].metrics.label)
        col.caption(scored[i].metrics.label)

    st.markdown("#### All-round and safest")
    c1, c2 = st.columns(2)
    if dec.all_round is not None:
        c1.metric("All-round", scored[dec.all_round].metrics.label,
                  help=f"composite {dec.composite.get(dec.all_round, 0):.3f}")
        c1.caption("weights: " + ", ".join(f"{k} {v:.2f}" for k, v in dec.weights.items()))
    if dec.safest is not None:
        row = scored[dec.safest]
        c2.metric("Safest to build first", row.metrics.label,
                  help="highest confidence-discounted margin")
        c2.caption(f"discounted margin {(row.min_margin_discounted or 0) * 100:.0f}% "
                   f"· weakest link: {row.weakest_metric or '—'}")

    # ── Pareto ──────────────────────────────────────────────────────────────
    st.markdown("#### Pareto set")
    if dec.pareto:
        if dec.is_conflicted():
            st.info("The axes disagree — no single design wins on everything. "
                    "This set is the honest answer.")
        st.dataframe(
            pd.DataFrame([
                {"Config": scored[i].metrics.label,
                 **{a.label: axis_value(scored[i], a) for a in dec.axes}}
                for i in dec.pareto
            ]),
            width="stretch", hide_index=True,
        )
    else:
        st.caption("No design can be compared across all declared axes.")

    incomparable = [i for i in dec.candidates if i not in set(dec.pareto)
                    and any(axis_value(scored[i], a) is None for a in dec.axes)]
    if incomparable:
        missing = sorted({a.label for i in incomparable for a in dec.axes
                          if axis_value(scored[i], a) is None})
        st.caption(
            f"{len(incomparable)} design{'s' if len(incomparable) != 1 else ''} "
            f"left off the front — N-A on {', '.join(missing)}. A design that "
            f"cannot be measured on an axis is not given a substitute value, so "
            f"it cannot be called non-dominated across all of them.")

    # ── honesty notes ───────────────────────────────────────────────────────
    if dec.all_red:
        st.error("Every design scored red. These picks are the least-bad of an "
                 "unbuildable set, not recommendations.")
    elif len(dec.candidates) < len(scored):
        n = len(scored) - len(dec.candidates)
        st.caption(f"{n} red row{'s' if n != 1 else ''} excluded from selection — "
                   f"a winner should be buildable.")

    for name, i in (("all-round", dec.all_round), ("safest", dec.safest)):
        if i is None:
            continue
        keys = [k for k in scored[i].extrapolated_keys if k != "validity"]
        if keys:
            st.warning(f"The **{name}** pick rests on extrapolated "
                       f"{', '.join(keys)} — the model has not been checked there.")
        specific = row_specific_breaches(scored[i], dec.caveats)
        if specific:
            st.warning(f"**{name}** — outside the validated envelope: "
                       + "; ".join(specific))

    for caveat in dec.caveats:
        st.warning(f"Applies to **every** design in this study: {caveat}")


def _render_diagnosis(st, study: Study, scored: list[ScoredRow]) -> None:
    """
    Why the study came back the way it did — and what would change it.

    Binding-constraint analysis is free (it reads the already-scored rows) so it
    always renders.  Relaxation pricing costs a full re-run of the study per
    constraint, so it sits behind a button: the user decides when that is worth
    waiting for, rather than paying for it on every edit.
    """
    from stepgen.studio.diagnosis import (
        active_knobs, binding_gates, diagnose, knobs_for_gate, price_relaxations,
    )

    if not scored:
        st.info("No rows to diagnose.")
        return

    if study.from_intent:
        s = study.intent_plan.summary()
        st.markdown("#### The question, as asked")
        c1, c2, c3 = st.columns(3)
        c1.metric("Droplet target", f"{s['droplet_um']:g} µm")
        c2.metric("Throughput target", f"{s['throughput_mlhr']:g} mL/hr")
        c3.metric("Pressure ceiling", f"{s['max_Po_mbar']:g} mbar")
        st.caption(
            f"Fab **{s['fab']}** — depth ≤ {s['max_main_depth_um']:g} µm, "
            f"width ≤ {s['max_main_width_um']:g} µm, min wall {s['min_wall_um']:g} µm "
            f"· die {s['square_side_mm']:g} mm · exploring "
            f"{', '.join(s['explore'])}. Generated blocks: "
            f"{', '.join(s['generated_blocks'])}.")
        for name, why in (s["skipped_families"] or {}).items():
            st.warning(f"**{name}** was skipped — no geometry was invented for "
                       f"it: {why}")
        with st.expander("Show the study this intent generated"):
            from stepgen.studio.intent import generated_yaml
            st.code(generated_yaml(study.intent_raw or study.raw), language="yaml")
            st.caption("Intent is a front door, not a lock-in — copy this into "
                       "the editor to take manual control of any of it.")

    diag = diagnose(study, scored, price="never")
    st.markdown("#### Verdict")
    (st.success if diag.n_green else st.warning)(diag.headline())

    # ── buildable, blocked only by our weakest theory ───────────────────────
    if diag.theory_limited:
        from stepgen.studio.diagnosis import ca_gamma_robustness

        lo, hi = diag.gamma_range[0] * 1e3, diag.gamma_range[1] * 1e3
        st.markdown("#### Build-and-see candidates")
        st.info(
            f"**{len(diag.theory_limited)} designs are green on everything "
            f"except exit Ca.** They pass every gate that rests on geometry, "
            f"fabrication limits or hydraulics. The only objection is the "
            f"step-emulsification ceiling — borrowed from literature at λ ≈ 1 "
            f"while we run at λ ≈ 0.015, and never approached within 7× on a "
            f"Peak device. The verdict stays red because an unmeasured risk "
            f"should not be quietly downgraded, but whether these work is a "
            f"question the model cannot settle.")

        if diag.gamma_dependent_ca or diag.robustly_red_ca:
            st.caption(
                f"Exit Ca scales as 1/γ, and γ has never been measured for this "
                f"fluid system (configs here assume 5, 15 and 0 mN/m). Each "
                f"verdict below is re-checked across **{lo:g}–{hi:g} mN/m** — "
                f"free, because γ enters only this diagnostic and never the flow "
                f"solve. **{len(diag.robustly_red_ca)}** stay red at every "
                f"plausible γ and should be believed; "
                f"**{len(diag.gamma_dependent_ca)}** are red only at part of the "
                f"band and are the real shortlist.")

        order = diag.gamma_dependent_ca or diag.theory_limited
        rows = []
        for i in order:
            rb = ca_gamma_robustness(scored[i], study.scoring,
                                     gamma_ref=diag.gamma_ref,
                                     gamma_range=diag.gamma_range)
            rows.append({
                "Config": scored[i].metrics.label,
                "Family": scored[i].metrics.family,
                "Exit Ca": scored[i].metrics.regime_Ca,
                "Clears above γ (mN/m)": (None if rb is None or rb.gamma_to_clear_red is None
                                          else round(rb.gamma_to_clear_red * 1e3, 2)),
                "Throughput mL/hr": scored[i].metrics.throughput_mlhr,
                "ΔP spread %": scored[i].metrics.uniformity_pct,
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True,
                     height=min(70 + 35 * len(rows), 400))
        st.caption("“Clears above γ” is the interfacial tension at which this "
                   "design would stop being red. Lower is a better bet — a "
                   "design needing 6 mN/m is far more likely to be in regime "
                   "than one needing 19.")

    # ── which gate is in the way ────────────────────────────────────────────
    shown = [f for f in diag.failures if f.n_red or f.n_sole_cause]
    if shown:
        st.markdown("#### What is in the way")
        st.dataframe(
            pd.DataFrame([
                {"Gate": f.label,
                 "Sole cause of red": f.n_sole_cause,
                 "Red": f.n_red,
                 "Non-green": f.n_non_green,
                 "Relaxable by": ", ".join(k.label for k in knobs_for_gate(f.key))
                                 or "physics — no process knob"}
                for f in shown
            ]),
            width="stretch", hide_index=True,
        )
        st.caption("“Sole cause” counts rows where this gate is the *only* red "
                   "one — relaxing it alone would change those verdicts. A gate "
                   "that reds many rows but is never the sole cause is a "
                   "symptom, not the constraint.")
    else:
        st.caption("No gate is failing on any row.")

    # ── relaxation pricing (opt-in: one full re-run per constraint) ─────────
    st.markdown("#### What relaxing a constraint would buy")
    raw = study.intent_raw or study.raw
    knobs = active_knobs(raw, diag.failures)
    if not knobs:
        st.caption("No constraint in this study owns a gate that is failing — "
                   "there is nothing to price.")
        return

    st.caption("Each constraint below is re-run as a full study with that one "
               "value stepped a notch. For an intent study the whole grid is "
               "regenerated from the relaxed constraint, so a deeper permitted "
               "etch changes the geometry that gets tried — not merely the gate "
               "that judges it.")
    pick = st.multiselect(
        "Constraints to price",
        [k.key for k in knobs],
        default=[k.key for k in knobs],
        format_func=lambda key: next(
            f"{k.label} ({k.current(raw):g} {k.unit})" for k in knobs if k.key == key),
    )
    if not st.button(f"Price {len(pick)} relaxation"
                     f"{'s' if len(pick) != 1 else ''} "
                     f"({len(pick)} full re-run{'s' if len(pick) != 1 else ''})"):
        return

    chosen = [k for k in knobs if k.key in pick]
    with st.spinner("Re-running the study once per constraint…"):
        prices = price_relaxations(study, scored, chosen)

    if not prices:
        st.caption("Nothing could be stepped.")
        return
    st.dataframe(
        pd.DataFrame([
            {"Constraint": p.label,
             "One notch": f"{p.before:g} → {p.after:g} {p.unit}",
             "Red": f"{p.red_before} → {p.red_after}",
             "Green": f"{p.green_before} → {p.green_after}",
             "Verdict": p.error or p.describe()}
            for p in prices
        ]),
        width="stretch", hide_index=True,
    )


def _render_table(st, scored, df, cats) -> None:
    fam_opts = sorted({s.metrics.family for s in scored})
    verdict_opts = ["green", "orange", "red"]

    f1, f2 = st.columns(2)
    fam_sel = f1.multiselect("Family", fam_opts, default=fam_opts)
    ver_sel = f2.multiselect("Verdict", verdict_opts, default=verdict_opts)

    mask = df["Family"].isin(fam_sel) & df["Verdict"].isin(ver_sel)
    view = df[mask]
    view_cats = cats.loc[view.index]

    def _apply_style(frame: pd.DataFrame) -> pd.DataFrame:
        return view_cats.map(_style_cell)

    styler = view.style.apply(_apply_style, axis=None).format(
        {header: "{:.3g}" for _, header in _COLUMNS
         if pd.api.types.is_numeric_dtype(df[header])},
        na_rep="—",
    )
    st.dataframe(styler, width="stretch", hide_index=True,
                 height=min(70 + 35 * len(view), 620))
    st.caption("Verdict is **worst-category-wins** across every applicable gate; "
               "grey cells are N-A for that family. ★ marks the best rows all-round. "
               "**Margin %** is how far the weakest applicable metric sits from its red "
               "boundary, discounted by how far the model is trusted for that number. "
               "**Valid** is orange outside the envelope the model has been checked in.")

    # ── drill-down ──────────────────────────────────────────────────────────
    st.markdown("#### Drill into a point")
    labels = [f"#{i + 1} — {s.metrics.label}  ({s.overall})"
              for i, s in enumerate(scored)]
    pick = st.selectbox("Point", labels, index=0)
    idx = labels.index(pick)
    _render_drilldown(st, scored[idx])


def _render_drilldown(st, sr: ScoredRow) -> None:
    m = sr.metrics
    left, mid, right = st.columns(3)
    with left:
        st.markdown("**Swept params**")
        st.json(m.params, expanded=True)
    with mid:
        st.markdown("**Score reasons**")
        if sr.chips:
            for c in sr.chips:
                st.write(f"- {c}")
        else:
            st.success("all green")
        st.markdown("**Notes**")
        for n in (m.notes or ["—"]):
            st.write(f"- {n}")
        st.markdown("**Margin & trust**")
        graded = sr.graded_cells
        if graded:
            st.dataframe(
                pd.DataFrame([
                    {"Metric": c.key,
                     "Margin %": round((c.margin or 0) * 100, 1),
                     "Trust": c.confidence}
                    for c in sorted(graded, key=lambda c: c.margin or 0)
                ]),
                width="stretch", hide_index=True,
            )
            st.caption(f"Weakest link: **{sr.weakest_metric or '—'}** · "
                       f"discounted margin "
                       f"{(sr.min_margin_discounted or 0) * 100:.0f}%")
        else:
            st.caption("No graded metric carries a margin for this row.")
    with right:
        st.markdown("**Raw metrics**")
        raw = {k: v for k, v in (m.raw or {}).items() if not k.startswith("_")}
        st.json(raw or {"(no raw metrics)": None}, expanded=False)


def _render_plots(st, plots: list[dict[str, Any]]) -> None:
    if not plots:
        st.info("No plots for this study.")
        return
    cols = st.columns(2)
    for j, p in enumerate(plots):
        with cols[j % 2]:
            best = ref = False
            toggles = st.columns(2)
            if p["has_best"]:
                best = toggles[0].checkbox("best-3", key=f"best_{j}")
            if p["has_ref"]:
                ref = toggles[1].checkbox("references", key=f"ref_{j}")
            key = variant_key(best, ref)
            img = p["images"].get(key, p["images"]["base"])
            st.image(img, caption=p["title"], width="stretch")
            st.caption(p["caption"])


def _render_provenance(st, result: StudyResult, study: Study) -> None:
    prov = result.provenance
    st.markdown(
        f"**Model commit:** `{prov.git_hash}`  ·  **Run:** {prov.timestamp}  ·  "
        f"**Points:** {prov.n_points}  ·  **Source:** `{prov.source_path or '(live edit)'}`"
    )

    with st.expander("Resolved constants (every value used)"):
        st.json(resolved_constants(study))
    with st.expander("Verbatim study config"):
        st.code(prov.source_text or "(config text unavailable)", language="yaml")

    st.markdown("#### Export")
    stem = Path(prov.source_path).stem if prov.source_path else "study"
    if st.button("Build self-contained HTML workbook"):
        book_dir = _REPO_ROOT / "book"
        out = write_workbook(result, book_dir / f"{stem}.html")
        html_bytes = out.read_bytes()
        st.success(f"Wrote {out.relative_to(_REPO_ROOT)}")
        st.download_button("⬇ Download HTML chapter", data=html_bytes,
                           file_name=out.name, mime="text/html")


# ---------------------------------------------------------------------------
# Small helpers for the sidebar
# ---------------------------------------------------------------------------

def _rel_to_repo(path: str | Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(_REPO_ROOT))
    except Exception:
        return str(path)


def _initial_text(chosen: str, uploaded, initial_path: str | None) -> str:
    if uploaded is not None:
        return uploaded.getvalue().decode("utf-8")
    if chosen and not chosen.startswith("("):
        p = _REPO_ROOT / chosen
        if p.is_file():
            return p.read_text(encoding="utf-8")
    if initial_path and Path(initial_path).is_file():
        return Path(initial_path).read_text(encoding="utf-8")
    return _TEMPLATE_HINT


def _families_hint(st) -> None:
    st.markdown(f"**Registered families:** {', '.join(list_families()) or '(none)'}")


_TEMPLATE_HINT = """\
title: "My study"

# ── Path A: say what you want, and let the families derive the geometry ──────
# Uncomment this block and delete everything below it. The junction exit is
# derived from the droplet target, the sweep is bounded by the constraints, and
# each family lays itself out. The Diagnosis tab then shows what was generated,
# what is standing in the way, and what relaxing a constraint would buy.
#
# intent:
#   droplet_um: 140
#   throughput_mlhr: 5
# constraints:
#   max_Po_mbar: 300
#   fab: current            # or: relaxed_300um / relaxed_500um
# explore: [serpentine, radial, manifold]

# ── Path B: write the grid yourself ─────────────────────────────────────────
family: serpentine        # or a list, e.g. [serpentine, radial, manifold]

# What "best" means. Several axes, not one goal — the Decision tab reports a
# winner per axis, the Pareto set, an all-round pick and the safest pick.
decide:
  axes: [flatness, throughput, drive_pressure, margin]
  weights: { flatness: 0.4, throughput: 0.3, drive_pressure: 0.2, margin: 0.1 }

# `goal: throughput` still works as a one-axis shorthand.
# See configs/study_template.yaml for the full annotated schema, and
# configs/study_intent_deep_dfu.yaml for a worked intent study.
"""


def main() -> None:
    """``streamlit run`` entry point."""
    initial = None
    # streamlit passes script args after `--`; also honour an env fallback
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        initial = sys.argv[1]
    initial = initial or os.environ.get("STEPGEN_STUDIO_STUDY")
    render(initial)


if __name__ == "__main__":
    main()
