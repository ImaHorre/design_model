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
        build = sr.cells.get("build")
        row["Build"] = build.category if build else "grey"
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
        for key, header in _COLUMNS:
            cell = sr.cells.get(key)
            if cell is not None:
                cats.at[i, header] = cell.category
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
    best = set(_best_indices(scored, study.goal))

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

    st.subheader(study.title or "Untitled study")
    st.caption(f"Goal: **{study.goal or '—'}**  ·  Families: "
               f"{', '.join(study.families)}  ·  {len(scored)} configs")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Configs", len(scored))
    c2.metric("🟢 Green", n_green)
    c3.metric("🟠 Orange", n_orange)
    c4.metric("🔴 Red", n_red)

    tab_table, tab_plots, tab_prov = st.tabs(
        ["Scored comparison", "Plots", "Provenance & export"])

    with tab_table:
        _render_table(st, scored, df, cats)

    with tab_plots:
        _render_plots(st, data["plots"])

    with tab_prov:
        _render_provenance(st, result, study)


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
               "grey cells are N-A for that family. ★ marks the best rows for the goal.")

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
goal: throughput          # 'flatness' or 'throughput'
family: serpentine        # or a list, e.g. [serpentine, radial, manifold]

# See configs/study_template.yaml for the full annotated schema.
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
