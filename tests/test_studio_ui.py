"""
Tests for the Phase 4 interactive Design Studio (stepgen.studio.ui).

These cover the *pure* (non-Streamlit) surface only — importing the module,
the text-based study loader, and the dataframe / plot / variant helpers — so
they run headless with no browser or Streamlit runtime.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from stepgen.studio import load_study, load_study_text
from stepgen.studio.run import run_study
from stepgen.studio.scoring import score_result
from stepgen.studio.workbook import _best_indices
from stepgen.studio import ui

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "configs" / "study_template.yaml"

# a fast, sweep-of-one serpentine study
_MINIMAL = """\
title: "UI test study"
goal: throughput
family: serpentine
fluids: { mu_dispersed: 0.06, mu_continuous: 0.00089, gamma: 0.015,
          emulsion_ratio: 0.10, phase_system: o/w }
footprint: { square_side_mm: 63.5 }
manufacturing: { max_main_depth_um: 200.0, max_main_width_um: 1000.0, min_wall_um: 5.0 }
operating: { Po_mbar: 500.0, Qw_mlhr: 5.0 }
serpentine:
  main: { depth_um: 200, width_um: 1000 }
  rung: { length_mm: 2, upstream_width_um: 15, N: 500 }
  junction: { exit_width_um: 60, exit_depth_um: 20, pitch_um: 120 }
scoring:
  throughput_mlhr:   { green: 5, orange: 1, higher_better: true }
  uniformity_pct:    { green: 20, orange: 100 }
  operating_Po_mbar: { green: 100, orange: 500 }
  build:             { from: manufacturing, fits_square: required }
"""


@pytest.fixture(scope="module")
def scored():
    study = load_study_text(_MINIMAL, source_path=None)
    result = run_study(study)
    rows = score_result(result, study.scoring)
    return study, result, rows


# ---------------------------------------------------------------------------
# text loader parity
# ---------------------------------------------------------------------------

def test_load_study_text_parity_with_file():
    from_file = load_study(TEMPLATE)
    from_text = load_study_text(TEMPLATE.read_text(encoding="utf-8"),
                                source_path=TEMPLATE)
    assert from_text.title == from_file.title
    assert from_text.families == from_file.families
    assert len(from_text.points) == len(from_file.points)
    assert from_text.scoring == from_file.scoring


def test_load_study_text_no_source_path():
    study = load_study_text(_MINIMAL)
    assert study.source_path is None
    assert study.source_text == _MINIMAL
    assert len(study.points) == 1


# ---------------------------------------------------------------------------
# pure UI helpers
# ---------------------------------------------------------------------------

def test_scored_dataframe_shape_and_columns(scored):
    _study, _result, rows = scored
    best = set(_best_indices(rows, "throughput"))
    df = ui.scored_dataframe(rows, best)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == len(rows)
    for col in ("#", "★", "Config", "Family", "Verdict", "Build", "Reasons"):
        assert col in df.columns
    assert df["Verdict"].iloc[0] in ("green", "orange", "red")


def test_category_frame_matches_dataframe_shape(scored):
    _study, _result, rows = scored
    df = ui.scored_dataframe(rows, set())
    cats = ui.category_frame(rows, df)
    assert cats.shape == df.shape
    assert list(cats.columns) == list(df.columns)
    # verdict cell carries a real traffic-light category
    assert cats["Verdict"].iloc[0] in ("green", "orange", "red", "grey")


def test_plot_pngs_returns_png_bytes(scored):
    _study, _result, rows = scored
    plots = ui.plot_pngs(rows, "throughput", refs=[])
    assert len(plots) >= 1
    for p in plots:
        assert "base" in p["images"]
        # PNG magic number
        assert p["images"]["base"][:8] == b"\x89PNG\r\n\x1a\n"
        assert isinstance(p["title"], str) and p["caption"]


def test_variant_key():
    assert ui.variant_key(False, False) == "base"
    assert ui.variant_key(True, False) == "best"
    assert ui.variant_key(False, True) == "ref"
    assert ui.variant_key(True, True) == "bestref"


def test_discover_studies_finds_configs():
    found = ui.discover_studies()
    names = {p.name for p in found}
    assert "study_template.yaml" in names


def test_module_exposes_entrypoints():
    # importing the module must not require a Streamlit runtime
    assert callable(ui.render)
    assert callable(ui.main)
    assert callable(ui._compute)
