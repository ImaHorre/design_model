"""
stepgen.studio.server
=====================
The Studio front door: a small FastAPI app that turns a study YAML into a scored
HTML chapter without a terminal.

Scope (plan section C1) is deliberately the **door only**.  The chapter already
filters, sorts and explains itself, so nothing here re-implements any of that —
``POST /run`` calls exactly the pipeline ``stepgen study`` calls, and then hands
back a link to the chapter that pipeline wrote.

Routes
------
    GET  /              the form page
    POST /preview       expand only — point count, no solve (~1-4 ms)
    POST /run           solve -> score -> diagnose -> write_workbook -> chapter
    GET  /book          the book index
    GET  /book/{name}   one chapter (or its JSON sidecar)
    GET  /configs       study YAMLs discoverable on disk

The form here is the minimal one: paste or load a study YAML.  The structured
three-region builder (designs / fluids / axes, with the fluid-swap button) is
C2, and is blocked on the reverse-flow guard — see the plan's *Explicitly
deferred* section for why a one-click W/O swap needs that guard first.
"""

from __future__ import annotations

import io
import traceback
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

# The study pipeline renders figures; without a non-interactive backend a
# request thread tries to open a window and the server hangs.  Same reason
# `_cmd_study` does this before importing the studio package.
import matplotlib

matplotlib.use("Agg")

# FastAPI resolves route annotations with ``eval_str=True`` against the
# *module* globals, so the request models and response classes must live here
# and not inside ``create_app`` — as locals they raise NameError at decoration
# time under `from __future__ import annotations`.
#
# This makes fastapi a hard import for this module.  That is fine and
# deliberate: nothing in ``stepgen.studio.__init__`` imports it, and
# ``_cmd_studio_serve`` checks for the extra and prints the install line before
# reaching here, so a lean install never sees the ImportError.
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel


class StudyText(BaseModel):
    """Body of ``POST /preview`` — a study YAML, nothing else."""
    yaml: str


class RunRequest(BaseModel):
    """Body of ``POST /run`` — the study plus the knobs `stepgen study` exposes."""
    yaml: str
    name: str = "study"
    diagnose: str = "auto"
    production_threshold: bool = False
    extends: str | None = None

#: Legacy flat rate — 1,368 points in ~26 s (plan, "Solve cost").  Kept only as
#: the last-resort fallback if ``configs/studio_defaults.yaml`` cannot be read.
#: It is a single geometry's average: measurement on 2026-08-06 put serpentine
#: at 3.5 ms (83 rungs) to 106 ms (2666 rungs) and radial at 0.017 ms, so one
#: number across all families is wrong by more than it is right.  Per-family
#: rates live in the defaults file — see ``studio.defaults``.
MS_PER_POINT: float = 19.0


def estimate_seconds(n_points: int) -> float:
    """Flat fallback estimate, in seconds.  Prefer ``StudioDefaults.estimate_seconds``."""
    return n_points * MS_PER_POINT / 1000.0


def _study_configs(configs_dir: Path) -> list[dict[str, Any]]:
    """Every ``study_*.yaml`` under *configs_dir*, newest first."""
    if not configs_dir.is_dir():
        return []
    found = sorted(
        configs_dir.glob("study_*.yaml"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return [{"name": p.name, "path": str(p)} for p in found]


def _expand(text: str) -> dict[str, Any]:
    """
    Parse and expand *text* without solving anything.

    Returns the same shape whether it worked or not, so the form can render one
    result panel: ``ok`` decides which half is populated.
    """
    from stepgen.families import list_families
    from stepgen.studio import load_study_text

    try:
        study = load_study_text(text)
    except Exception as exc:
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }

    # An unknown family parses and expands fine — it only fails later, per
    # point, inside run_study, which records the error and carries on.  That is
    # right for a run (one bad family must not lose the other 300 points) but
    # wrong for a preview, whose whole job is to say what will happen before
    # the solve is paid for.  So check the registry here.
    known = set(list_families())
    unknown = sorted({p.family for p in study.points} - known)
    if unknown:
        return {
            "ok": False,
            "error": f"unknown family: {', '.join(unknown)} "
                     f"(known: {', '.join(sorted(known))})",
        }

    per_family: dict[str, int] = {}
    for point in study.points:
        per_family[point.family] = per_family.get(point.family, 0) + 1

    n = len(study.points)

    # Per-family rates from the checked-in defaults; the flat legacy rate only
    # if that file is unreadable, so a broken defaults file degrades the
    # estimate rather than the preview.
    try:
        from stepgen.studio.defaults import load_defaults
        est = load_defaults().estimate_seconds(per_family)
        est_basis = "per-family measured rates"
    except Exception:
        est = estimate_seconds(n)
        est_basis = f"flat {MS_PER_POINT:g} ms/point (defaults file unreadable)"

    return {
        "ok": True,
        "title": study.title,
        "families": list(study.families),
        "n_points": n,
        "per_family": per_family,
        "est_seconds": round(est, 1),
        "est_basis": est_basis,
        "from_intent": study.from_intent,
    }


def create_app(
    book_dir: str | Path = "book",
    configs_dir: str | Path = "configs",
):
    """
    Build the FastAPI application.

    Parameters
    ----------
    book_dir    : directory the chapter and book index are written to
    configs_dir : directory scanned for selectable ``study_*.yaml`` files
    """
    book_path = Path(book_dir)
    configs_path = Path(configs_dir)

    app = FastAPI(title="StepGen Design Studio", version="1.0.0")

    # ── the form ───────────────────────────────────────────────────────────
    @app.get("/", response_class=HTMLResponse)
    def form() -> str:
        return _FORM_HTML

    @app.get("/configs")
    def configs() -> JSONResponse:
        return JSONResponse({"configs": _study_configs(configs_path)})

    @app.get("/defaults")
    def defaults() -> JSONResponse:
        """
        The house defaults, read-only (plan C3).

        Served as the parsed values *and* the verbatim file text, so the form
        can show what it starts from and the reader can see the comments that
        explain why — the reasoning is most of the value of that file.
        """
        from stepgen.studio.defaults import load_defaults

        try:
            d = load_defaults()
        except Exception as exc:
            return JSONResponse(
                {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
                status_code=500,
            )
        return JSONResponse({
            "ok": True,
            "sweep_defaults": d.sweep_defaults,
            "solve_cost": {
                k: {"us_per_element": v.us_per_element,
                    "ms_per_point": v.ms_per_point,
                    "reference_elements": v.reference_elements}
                for k, v in d.solve_cost.items()
            },
            "extras": d.extras,
            "source_path": d.source_path,
            "source_text": d.source_text,
        })

    @app.get("/configs/{name}", response_class=PlainTextResponse)
    def config_text(name: str) -> str:
        # Resolve inside configs_dir only — a study name is not a path.
        target = (configs_path / Path(name).name).resolve()
        if not str(target).startswith(str(configs_path.resolve())):
            raise HTTPException(status_code=400, detail="name escapes configs dir")
        if not target.is_file():
            raise HTTPException(status_code=404, detail=f"no such study: {name}")
        return target.read_text(encoding="utf-8")

    # ── expand only, no solve ──────────────────────────────────────────────
    @app.post("/preview")
    def preview(body: StudyText) -> JSONResponse:
        return JSONResponse(_expand(body.yaml))

    # ── the real thing ─────────────────────────────────────────────────────
    @app.post("/run")
    def run(body: RunRequest) -> JSONResponse:
        from stepgen.studio import (
            diagnose as diagnose_fn,
            load_study_text,
            run_study,
            score_result,
            write_book_index,
            write_workbook,
        )

        try:
            study = load_study_text(body.yaml)
        except Exception as exc:
            return JSONResponse(
                {"ok": False, "stage": "parse",
                 "error": f"{type(exc).__name__}: {exc}"},
                status_code=400,
            )

        stem = Path(body.name).stem or "study"
        book_path.mkdir(parents=True, exist_ok=True)
        chapter = book_path / f"{stem}.html"

        # run_study prints progress; keep it out of the server's stdout and
        # hand it back with the response instead, so a failed run is
        # diagnosable from the browser.
        log = io.StringIO()
        try:
            with redirect_stdout(log):
                result = run_study(study, progress=False)
                if body.production_threshold:
                    from stepgen.studio.run import fill_production_thresholds
                    fill_production_thresholds(result)
                scored = score_result(result, study.scoring)
                diag = diagnose_fn(study, scored, price=body.diagnose,
                                   progress=False)
                write_workbook(result, chapter, diagnosis=diag,
                               parent=body.extends)
                write_book_index(book_path)
        except Exception as exc:
            return JSONResponse(
                {"ok": False, "stage": "solve",
                 "error": f"{type(exc).__name__}: {exc}",
                 "traceback": traceback.format_exc(),
                 "log": log.getvalue()},
                status_code=500,
            )

        n_err = sum(1 for m in result.metrics if m.error)
        return JSONResponse({
            "ok": True,
            "title": study.title,
            "n_points": len(result.metrics),
            "n_errors": n_err,
            "n_green": diag.n_green,
            "n_orange": diag.n_orange,
            "n_red": diag.n_red,
            "headline": diag.headline(),
            "model_commit": result.provenance.git_hash,
            "chapter_url": f"/book/{chapter.name}",
            "chapter_path": str(chapter),
        })

    # ── serving what was written ───────────────────────────────────────────
    @app.get("/book", response_class=HTMLResponse)
    def book_index() -> str:
        index = book_path / "index.html"
        if not index.is_file():
            return "<p>No chapters yet — run a study.</p>"
        return index.read_text(encoding="utf-8")

    @app.get("/book/{name}")
    def chapter_file(name: str):
        target = (book_path / Path(name).name).resolve()
        if not str(target).startswith(str(book_path.resolve())):
            raise HTTPException(status_code=400, detail="name escapes book dir")
        if not target.is_file():
            raise HTTPException(status_code=404, detail=f"no such chapter: {name}")
        text = target.read_text(encoding="utf-8")
        if target.suffix == ".json":
            return PlainTextResponse(text, media_type="application/json")
        return HTMLResponse(text)

    return app


def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    book_dir: str | Path = "book",
    configs_dir: str | Path = "configs",
) -> int:
    """Run the front door under uvicorn.  Blocks until interrupted."""
    import uvicorn

    app = create_app(book_dir=book_dir, configs_dir=configs_dir)
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


# ── the page ───────────────────────────────────────────────────────────────
# Inline rather than a template file, for the same reason the chapter is one
# self-contained HTML: nothing to install, nothing to find at runtime.
_FORM_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>StepGen Design Studio</title>
<style>
  :root { color-scheme: light dark; --bg:#fff; --fg:#111; --mut:#666;
          --line:#d8d8d8; --accent:#1a5fb4; --bad:#a51d2d; --ok:#26734d;
          --panel:#f7f7f7; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#16181c; --fg:#e8e8e8; --mut:#9aa0a6; --line:#33363b;
            --accent:#78aeed; --bad:#f08b96; --ok:#7bd0a2; --panel:#1e2126; }
  }
  * { box-sizing: border-box; }
  body { margin:0; padding:2rem 1.25rem; background:var(--bg); color:var(--fg);
         font:15px/1.55 ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif; }
  main { max-width: 60rem; margin: 0 auto; }
  h1 { font-size:1.35rem; margin:0 0 .2rem; }
  p.sub { color:var(--mut); margin:0 0 1.5rem; }
  label { display:block; font-weight:600; margin:1rem 0 .35rem; }
  select, textarea, input { width:100%; padding:.5rem .6rem; font-size:.9rem;
    background:var(--bg); color:var(--fg); border:1px solid var(--line);
    border-radius:6px; font-family:inherit; }
  textarea { min-height:22rem; font:13px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;
             white-space:pre; overflow-wrap:normal; overflow-x:auto; }
  .row { display:flex; gap:.75rem; flex-wrap:wrap; align-items:center; margin-top:1rem; }
  button { padding:.55rem 1.1rem; font-size:.9rem; font-weight:600; cursor:pointer;
    border-radius:6px; border:1px solid var(--line); background:var(--panel); color:var(--fg); }
  button.primary { background:var(--accent); border-color:var(--accent); color:#fff; }
  button:disabled { opacity:.5; cursor:progress; }
  .opts { display:flex; gap:1rem; flex-wrap:wrap; align-items:center;
          color:var(--mut); font-size:.85rem; }
  .opts input[type=checkbox] { width:auto; }
  .opts input[type=text] { width:9rem; display:inline-block; }
  #out { margin-top:1.25rem; padding:.9rem 1rem; border:1px solid var(--line);
         border-radius:8px; background:var(--panel); display:none; }
  #out.show { display:block; }
  #out .err { color:var(--bad); white-space:pre-wrap;
              font:12.5px/1.5 ui-monospace,Consolas,monospace; }
  #out .big { font-size:1.1rem; font-weight:600; }
  .pill { display:inline-block; padding:.1rem .5rem; border-radius:999px;
          font-size:.8rem; font-weight:600; margin-right:.35rem; }
  .g { background:#26734d22; color:var(--ok); }
  .o { background:#c6801022; color:#c68010; }
  .r { background:#a51d2d22; color:var(--bad); }
  a { color:var(--accent); }
  .note { color:var(--mut); font-size:.82rem; margin-top:.5rem; }
  .mut { color:var(--mut); font-weight:400; font-size:.8rem; }
  details { margin-top:1.5rem; border-top:1px solid var(--line); padding-top:.9rem; }
  summary { cursor:pointer; font-weight:600; }
  pre { overflow-x:auto; background:var(--panel); border:1px solid var(--line);
        border-radius:8px; padding:.8rem 1rem; max-height:26rem;
        font:12.5px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace; }
</style>
</head>
<body>
<main>
  <h1>StepGen Design Studio</h1>
  <p class="sub">Solve a study &rarr; scored HTML chapter. Preview costs nothing;
     runtime scales with point count.</p>

  <label for="pick">Load a study</label>
  <select id="pick"><option value="">— paste your own below —</option></select>

  <label for="yaml">Study YAML</label>
  <textarea id="yaml" spellcheck="false"
    placeholder="Paste a study YAML, or pick one above."></textarea>

  <div class="row">
    <button id="btn-preview">Preview</button>
    <button id="btn-run" class="primary">Run study</button>
    <a href="/book" target="_blank">book index &rarr;</a>
  </div>
  <div class="row opts">
    <label style="margin:0;font-weight:400">
      <input type="checkbox" id="pt"> production threshold (~40 extra solves per design)
    </label>
    <label style="margin:0;font-weight:400">
      diagnose
      <select id="dx" style="width:7rem;display:inline-block">
        <option>auto</option><option>always</option><option>never</option>
      </select>
    </label>
    <label style="margin:0;font-weight:400">
      name <input type="text" id="name" value="study">
    </label>
  </div>

  <div id="out"></div>
  <p class="note">Adding an axis with k levels multiplies runtime by k.
     Solve cost is linear in rung count for serpentine and node count for
     manifold; radial is closed-form and effectively free.</p>

  <details id="dwrap">
    <summary>House defaults <span class="mut" id="dpath"></span></summary>
    <p class="note">Read-only. A study config overrides any of it; edit the file
       to change what a new study starts from.</p>
    <pre id="dtext"></pre>
  </details>
</main>
<script>
const $ = (id) => document.getElementById(id);
const out = $("out");

function show(html) { out.innerHTML = html; out.classList.add("show"); }
function esc(s) { return String(s).replace(/[&<>]/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c])); }

fetch("/configs").then(r => r.json()).then(d => {
  for (const c of d.configs) {
    const o = document.createElement("option");
    o.value = c.name; o.textContent = c.name;
    $("pick").appendChild(o);
  }
});

$("pick").addEventListener("change", async (e) => {
  const name = e.target.value;
  if (!name) return;
  const r = await fetch("/configs/" + encodeURIComponent(name));
  if (r.ok) {
    $("yaml").value = await r.text();
    $("name").value = name.replace(/\\.ya?ml$/, "");
    preview();
  }
});

async function preview() {
  const r = await fetch("/preview", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({yaml: $("yaml").value}),
  });
  const d = await r.json();
  if (!d.ok) { show('<div class="err">' + esc(d.error) + "</div>"); return; }
  const fam = Object.entries(d.per_family)
    .map(([k, v]) => esc(k) + " " + v).join(" &middot; ");
  show('<div class="big">' + d.n_points + " points</div>" +
       "<div>" + esc(d.title) + "</div>" +
       '<div class="note">' + fam + " &mdash; about " + d.est_seconds +
       " s to solve (" + esc(d.est_basis) + ")" +
       (d.from_intent ? " &middot; generated from intent" : "") +
       "</div>");
}

async function run() {
  $("btn-run").disabled = true;
  show("<div>Solving&hellip; this holds the connection until the chapter is written.</div>");
  try {
    const r = await fetch("/run", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        yaml: $("yaml").value, name: $("name").value,
        diagnose: $("dx").value, production_threshold: $("pt").checked,
      }),
    });
    const d = await r.json();
    if (!d.ok) {
      show('<div class="err">' + esc(d.error) +
           (d.traceback ? "\\n\\n" + esc(d.traceback) : "") + "</div>");
      return;
    }
    show('<div class="big"><a href="' + d.chapter_url +
         '" target="_blank">open chapter &rarr;</a></div>' +
         "<div>" +
         '<span class="pill g">' + d.n_green + " green</span>" +
         '<span class="pill o">' + d.n_orange + " orange</span>" +
         '<span class="pill r">' + d.n_red + " red</span>" +
         "</div><div style='margin-top:.5rem'>" + esc(d.headline) + "</div>" +
         '<div class="note">' + d.n_points + " points, " + d.n_errors +
         " errors &middot; model " + esc(d.model_commit).slice(0, 10) + "</div>");
  } catch (err) {
    show('<div class="err">' + esc(err) + "</div>");
  } finally {
    $("btn-run").disabled = false;
  }
}

$("btn-preview").addEventListener("click", preview);
$("btn-run").addEventListener("click", run);

fetch("/defaults").then(r => r.json()).then(d => {
  if (!d.ok) { $("dtext").textContent = d.error; return; }
  $("dpath").textContent = d.source_path || "";
  $("dtext").textContent = d.source_text || "";
});
</script>
</body>
</html>
"""
