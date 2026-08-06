"""
tests.test_studio_server
========================
The Studio front door (plan C1).

These exercise the routes through FastAPI's TestClient — no live port, no
uvicorn — so they run in the normal suite.  The point of the server is that it
reuses the `stepgen study` pipeline rather than reimplementing it, so the tests
that matter here are: does the door parse the same YAML, does it refuse bad
input without a traceback in the user's face, and does /run actually leave a
chapter on disk.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "configs" / "study_template.yaml"

fastapi = pytest.importorskip("fastapi", reason="needs the .[serve] extra")
from fastapi.testclient import TestClient  # noqa: E402

from stepgen.studio.server import MS_PER_POINT, create_app, estimate_seconds  # noqa: E402


@pytest.fixture
def client(tmp_path):
    app = create_app(book_dir=tmp_path / "book", configs_dir=REPO / "configs")
    return TestClient(app)


# ---------------------------------------------------------------------------
# The door itself
# ---------------------------------------------------------------------------

def test_form_page_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "StepGen Design Studio" in r.text
    assert "Run study" in r.text


def test_configs_lists_study_yamls(client):
    r = client.get("/configs")
    assert r.status_code == 200
    names = [c["name"] for c in r.json()["configs"]]
    assert "study_template.yaml" in names
    assert all(n.startswith("study_") and n.endswith(".yaml") for n in names)


def test_config_text_round_trips(client):
    r = client.get("/configs/study_template.yaml")
    assert r.status_code == 200
    assert r.text == TEMPLATE.read_text(encoding="utf-8")


def test_config_name_cannot_escape_configs_dir(client):
    """A study name is a name, not a path — `..` must not reach outside."""
    r = client.get("/configs/..%2F..%2Fpyproject.toml")
    assert r.status_code in (400, 404)
    assert "build-system" not in r.text


# ---------------------------------------------------------------------------
# Preview — expand only, never solve
# ---------------------------------------------------------------------------

def test_preview_counts_template_points_without_solving(client):
    """27 points is the same number test_template_study_runs_end_to_end asserts."""
    r = client.post("/preview", json={"yaml": TEMPLATE.read_text(encoding="utf-8")})
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["n_points"] == 27
    assert d["per_family"] == {"serpentine": 27}
    # estimate now comes from the per-family measured rates (C3), not the flat
    # legacy MS_PER_POINT — 27 serpentine points at the reference size.
    from stepgen.studio.defaults import load_defaults
    expected = load_defaults().estimate_seconds({"serpentine": 27})
    assert d["est_seconds"] == round(expected, 1)
    assert d["est_basis"] == "per-family measured rates"


def test_preview_reports_bad_yaml_as_a_message_not_a_500(client):
    r = client.post("/preview", json={"yaml": "family: [unclosed\n"})
    assert r.status_code == 200            # a broken study is a result, not a crash
    d = r.json()
    assert d["ok"] is False
    assert d["error"]


def test_preview_rejects_unknown_family_gracefully(client):
    """
    An unknown family parses and expands cleanly — it only fails later, per
    point, inside run_study.  That is correct for a run and useless for a
    preview, so the preview checks the registry itself.
    """
    r = client.post("/preview", json={"yaml": "family: hexagonal\ntitle: nope\n"})
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is False
    assert "hexagonal" in d["error"]
    assert "serpentine" in d["error"]      # names what it would have accepted


def test_estimate_is_linear_in_points():
    assert estimate_seconds(0) == 0.0
    assert estimate_seconds(2000) == pytest.approx(2 * estimate_seconds(1000))


# ---------------------------------------------------------------------------
# Run — the whole pipeline, on disk
# ---------------------------------------------------------------------------

def test_run_writes_a_chapter_and_serves_it(client, tmp_path):
    r = client.post("/run", json={
        "yaml": TEMPLATE.read_text(encoding="utf-8"),
        "name": "from_server",
        "diagnose": "never",          # keep the test cheap; pricing re-runs
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    assert d["n_points"] == 27
    assert d["n_errors"] == 0
    assert d["chapter_url"] == "/book/from_server.html"

    chapter = tmp_path / "book" / "from_server.html"
    assert chapter.exists()
    assert chapter.with_suffix(".json").exists()   # sidecar, as `stepgen study` writes

    served = client.get(d["chapter_url"])
    assert served.status_code == 200
    assert served.text == chapter.read_text(encoding="utf-8")

    assert client.get("/book").status_code == 200


def test_run_reports_parse_failure_as_400(client):
    r = client.post("/run", json={"yaml": "family: [unclosed\n", "name": "bad"})
    assert r.status_code == 400
    d = r.json()
    assert d["ok"] is False
    assert d["stage"] == "parse"


def test_run_name_cannot_escape_book_dir(client, tmp_path):
    """`name` becomes a filename; it must not steer the write out of the book."""
    r = client.post("/run", json={
        "yaml": TEMPLATE.read_text(encoding="utf-8"),
        "name": "../escaped",
        "diagnose": "never",
    })
    assert r.status_code == 200, r.text
    assert not (tmp_path / "escaped.html").exists()
    assert (tmp_path / "book" / "escaped.html").exists()


def test_missing_chapter_is_404(client):
    assert client.get("/book/nope.html").status_code == 404


# ---------------------------------------------------------------------------
# House defaults, served read-only (C3)
# ---------------------------------------------------------------------------

def test_defaults_route_serves_values_and_verbatim_text(client):
    r = client.get("/defaults")
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["sweep_defaults"]["footprint"]["square_side_mm"] == 100.0
    assert "serpentine" in d["solve_cost"]
    # the comments are most of the value of that file, so the raw text ships too
    assert "sweep_defaults" in d["source_text"]
    assert "#" in d["source_text"]


def test_form_shows_the_defaults_panel(client):
    body = client.get("/").text
    assert "House defaults" in body
    assert "/defaults" in body
