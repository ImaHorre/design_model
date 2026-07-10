"""
stepgen.studio.workbook
======================
Render a scored :class:`StudyResult` into one **self-contained HTML chapter**
(the "book" is a directory of such chapters).

A chapter has:
  * an overview scored table — traffic-light cells (worst-category-wins) with
    reason chips, sortable, click a row to drill into its params + raw metrics;
  * standard plots (base64 PNG), each with a plain-English "what this means IRL"
    caption, and a best-3 toggle on the tradeoff scatter;
  * a constants / provenance panel (git hash, verbatim config, resolved values).

It also emits ``<chapter>.json`` (the scored rows) so other chapters and the
book index can cross-reference this study's devices.

Everything is inlined (CSS, a little vanilla JS, base64 images) — no external
requests, no build step.
"""

from __future__ import annotations

import base64
import html
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from stepgen.studio.run import StudyResult, resolved_constants
from stepgen.studio.scoring import ScoredRow, score_result

_CAT_COLOR = {"green": "#1a7f37", "orange": "#bf8700", "red": "#cf222e", "grey": "#8b949e"}

# columns shown in the overview table: (scoring/attr key, header, formatter)
_COLUMNS: list[tuple[str, str]] = [
    ("throughput_mlhr", "Throughput (mL/hr)"),
    ("N_dfu", "N DFU"),
    ("droplet_um", "Droplet (µm)"),
    ("frequency_hz", "Freq (Hz)"),
    ("uniformity_pct", "ΔP flatness (%)"),
    ("operating_Po_mbar", "Po (mbar)"),
    ("regime_Ca", "Exit Ca"),
    ("hub_budget_pct", "Hub ΔP (%)"),
    ("area_used_cm2", "Area (cm²)"),
]


# ---------------------------------------------------------------------------
# Ranking / best-3
# ---------------------------------------------------------------------------

def _rank_key(sr: ScoredRow, goal: str):
    cat_rank = {"green": 0, "orange": 1, "red": 2}.get(sr.overall, 3)
    m = sr.metrics
    if goal == "flatness":
        second = m.uniformity_pct if m.uniformity_pct is not None else float("inf")
    else:  # default: prefer throughput
        second = -(m.throughput_mlhr or 0.0)
    return (cat_rank, second)


def _best_indices(scored: list[ScoredRow], goal: str, n: int = 3) -> list[int]:
    order = sorted(range(len(scored)), key=lambda i: _rank_key(scored[i], goal))
    return order[:n]


# ---------------------------------------------------------------------------
# Plots -> base64 data URIs
# ---------------------------------------------------------------------------

def _fig_to_uri(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    import matplotlib.pyplot as plt
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


# reference-series marker styling by kind
_REF_STYLE = {
    "modelled":     dict(marker="X", s=130, c="#0d1117", edgecolors="white", linewidths=1.2),
    "experimental": dict(marker="D", s=60,  c="none",    edgecolors="#8250df", linewidths=1.6),
    "chapter":      dict(marker="s", s=70,  c="none",    edgecolors="#0969da", linewidths=1.6),
}


def _draw_refs(ax, refs, xattr, yattr) -> bool:
    """Overlay each reference series' points where both x and y are known."""
    drew = False
    seen: set[str] = set()
    for rs in refs or []:
        if rs.error:
            continue
        style = dict(_REF_STYLE.get(rs.kind, _REF_STYLE["chapter"]))
        for p in rs.points:
            x = getattr(p, xattr, None)
            y = getattr(p, yattr, None)
            if x is None or y is None:
                continue
            lbl = rs.label if rs.label not in seen else None
            seen.add(rs.label)
            ax.scatter(x, y, zorder=5, label=lbl, **style)
            drew = True
    return drew


def _scatter(scored, xattr, yattr, xlabel, ylabel, title, highlight=None, refs=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    highlight = set(highlight or [])
    fig, ax = plt.subplots(figsize=(6.2, 4.2))
    plotted = False
    for i, sr in enumerate(scored):
        x = getattr(sr.metrics, xattr, None)
        y = getattr(sr.metrics, yattr, None)
        if x is None or y is None:
            continue
        plotted = True
        ax.scatter(x, y, s=90 if i in highlight else 45,
                   c=_CAT_COLOR.get(sr.overall, "#8b949e"),
                   edgecolors="#0d1117" if i in highlight else "none",
                   linewidths=1.6 if i in highlight else 0, zorder=3 if i in highlight else 2)
        if i in highlight:
            ax.annotate(sr.metrics.label, (x, y), fontsize=7,
                        xytext=(4, 4), textcoords="offset points")
    drew_refs = _draw_refs(ax, refs, xattr, yattr)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=11)
    ax.grid(True, alpha=0.25)
    if drew_refs:
        ax.legend(fontsize=7.5, framealpha=0.85, loc="best")
    if not plotted and not drew_refs:
        ax.text(0.5, 0.5, "no data", ha="center", va="center", transform=ax.transAxes)
    return _fig_to_uri(fig)


def _variant_plot(scored, goal, refs, *, xattr, yattr, xlabel, ylabel, title,
                  caption, with_best=False):
    """
    Build one plot with (best-3, references) toggle variants.

    Returns {title, caption, has_best, has_ref, variants:{key->uri}} where key is
    one of base / best / ref / bestref (only the reachable ones are rendered).
    """
    best = _best_indices(scored, goal) if with_best else []
    has_ref = any((not rs.error) and _series_hits(rs, xattr, yattr) for rs in (refs or []))

    variants: dict[str, str] = {
        "base": _scatter(scored, xattr, yattr, xlabel, ylabel, title),
    }
    if with_best:
        variants["best"] = _scatter(scored, xattr, yattr, xlabel, ylabel,
                                     title + " — best 3", highlight=best)
    if has_ref:
        variants["ref"] = _scatter(scored, xattr, yattr, xlabel, ylabel,
                                    title, refs=refs)
        if with_best:
            variants["bestref"] = _scatter(scored, xattr, yattr, xlabel, ylabel,
                                           title + " — best 3", highlight=best, refs=refs)
    return {"title": title, "caption": caption, "variants": variants,
            "has_best": with_best, "has_ref": has_ref}


def _series_hits(rs, xattr, yattr) -> bool:
    return any(getattr(p, xattr, None) is not None and getattr(p, yattr, None) is not None
               for p in rs.points)


def _build_plots(scored: list[ScoredRow], goal: str, refs=None) -> list[dict[str, Any]]:
    """Return the standard plot set, each with toggle variants + references."""
    refs = refs or []
    return [
        _variant_plot(
            scored, goal, refs,
            xattr="throughput_mlhr", yattr="uniformity_pct",
            xlabel="Throughput (mL/hr)", ylabel="ΔP flatness (%) — lower is flatter",
            title="Throughput vs flatness tradeoff",
            caption=("IRL: down-left is a flat, gentle device (every DFU works, but "
                     "modest output); up-right pushes more oil but starves the far rungs. "
                     "The green points pass every gate. Radial rows have automatic flatness "
                     "(N-A) so they do not appear on this axis."),
            with_best=True,
        ),
        _variant_plot(
            scored, goal, refs,
            xattr="operating_Po_mbar", yattr="throughput_mlhr",
            xlabel="Drive pressure Po (mbar)", ylabel="Throughput (mL/hr)",
            title="Throughput vs drive pressure",
            caption=("IRL: how hard you have to push to get the flow you want. "
                     "Cheaper, more robust devices sit to the left."),
            with_best=True,
        ),
        _variant_plot(
            scored, goal, refs,
            xattr="N_dfu", yattr="throughput_mlhr",
            xlabel="N DFU", ylabel="Throughput (mL/hr)",
            title="Throughput vs DFU count",
            caption=("IRL: more parallel DFUs generally means more oil — until the far "
                     "ones starve or reverse and extra DFUs stop paying their way."),
            with_best=True,
        ),
        _variant_plot(
            scored, goal, refs,
            xattr="operating_Po_mbar", yattr="droplet_um",
            xlabel="Drive pressure Po (mbar)", ylabel="Droplet diameter (µm)",
            title="Droplet size vs drive pressure",
            caption=("IRL: the size you actually make vs how hard you drive. Click-in "
                     "experimental / modelled references overlay here — the model line is "
                     "regime-blind, so treat wide gaps to experiment as a size-model caveat."),
            with_best=False,
        ),
    ]


# ---------------------------------------------------------------------------
# HTML assembly
# ---------------------------------------------------------------------------

def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        if value != value:  # NaN
            return "—"
        return f"{value:.3g}"
    return html.escape(str(value))


def _light(cat: str) -> str:
    return (f'<span class="dot" style="background:{_CAT_COLOR.get(cat, "#8b949e")}" '
            f'title="{cat}"></span>')


def _table_html(scored: list[ScoredRow], best: set[int]) -> str:
    head = ["#", "Config", "Family", "Verdict"] + [c[1] for c in _COLUMNS] + ["Build", "Reasons"]
    thead = "".join(
        f'<th onclick="sortTable({i})">{html.escape(h)}</th>'
        for i, h in enumerate(head)
    )

    rows_html: list[str] = []
    for i, sr in enumerate(scored):
        m = sr.metrics
        star = "★ " if i in best else ""
        cells = [
            f'<td data-v="{i}">{i + 1}</td>',
            f'<td data-v="{html.escape(m.label)}"><b>{star}{html.escape(m.label)}</b></td>',
            f'<td data-v="{html.escape(m.family)}">{html.escape(m.family)}</td>',
            f'<td data-v="{ {"green":0,"orange":1,"red":2}.get(sr.overall,3) }">'
            f'{_light(sr.overall)}{sr.overall}</td>',
        ]
        for key, _ in _COLUMNS:
            value = getattr(m, key, None)
            cell = sr.cells.get(key)
            color = _CAT_COLOR.get(cell.category, "") if cell else ""
            sort_v = value if isinstance(value, (int, float)) and value == value else -1e18
            style = f' style="color:{color};font-weight:600"' if cell and cell.category in ("orange", "red") else ""
            cells.append(f'<td data-v="{sort_v}"{style}>{_fmt(value)}</td>')
        build_cell = sr.cells.get("build")
        bcat = build_cell.category if build_cell else "grey"
        cells.append(f'<td data-v="{ {"green":0,"orange":1,"red":2}.get(bcat,3) }">{_light(bcat)}</td>')
        chips = " ".join(f'<span class="chip">{html.escape(c)}</span>' for c in sr.chips)
        cells.append(f'<td data-v="0">{chips}</td>')

        rows_html.append(
            f'<tr class="mainrow" onclick="toggleDrill({i})">' + "".join(cells) + "</tr>"
        )
        rows_html.append(_drilldown_row(i, sr, len(head)))

    return (f'<table id="scoretable"><thead><tr>{thead}</tr></thead>'
            f'<tbody>{"".join(rows_html)}</tbody></table>')


def _drilldown_row(i: int, sr: ScoredRow, ncols: int) -> str:
    m = sr.metrics
    params = json.dumps(m.params, indent=2, default=str)
    raw = {k: v for k, v in (m.raw or {}).items() if not k.startswith("_")}
    raw_txt = json.dumps(raw, indent=2, default=str)
    notes = "".join(f"<li>{html.escape(n)}</li>" for n in m.notes) or "<li>—</li>"
    reasons = "".join(f"<li>{html.escape(c)}</li>" for c in sr.chips) or "<li>all green</li>"
    body = (
        f'<div class="drillgrid">'
        f'<div><h4>Swept params</h4><pre>{html.escape(params)}</pre></div>'
        f'<div><h4>Score reasons</h4><ul>{reasons}</ul>'
        f'<h4>Notes</h4><ul>{notes}</ul></div>'
        f'<div><h4>Raw metrics</h4><pre>{html.escape(raw_txt)}</pre></div>'
        f'</div>'
    )
    return (f'<tr id="drill{i}" class="drill" style="display:none">'
            f'<td colspan="{ncols}">{body}</td></tr>')


def _plots_html(plots: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for j, p in enumerate(plots):
        variants = p["variants"]
        # data-* attributes carry every rendered variant for JS composition
        data_attrs = " ".join(f'data-{k}="{uri}"' for k, uri in variants.items())
        img = (f'<img id="plotimg{j}" src="{variants["base"]}" {data_attrs} '
               f'alt="{html.escape(p["title"])}">')
        toggles: list[str] = []
        if p.get("has_best"):
            toggles.append(f'<label class="toggle"><input type="checkbox" '
                           f'onchange="composePlot({j})" data-role="best"> best-3</label>')
        if p.get("has_ref"):
            toggles.append(f'<label class="toggle"><input type="checkbox" '
                           f'onchange="composePlot({j})" data-role="ref"> references</label>')
        toggle_html = " ".join(toggles)
        blocks.append(
            f'<figure class="plot" id="plotfig{j}">{img}'
            f'<figcaption><b>{html.escape(p["title"])}</b> {toggle_html}'
            f'<br>{html.escape(p["caption"])}</figcaption></figure>'
        )
    return '<div class="plots">' + "".join(blocks) + "</div>"


def _provenance_html(result: StudyResult, refs=None) -> str:
    prov = result.provenance
    consts = resolved_constants(result.study)
    consts_txt = json.dumps(consts, indent=2, default=str)
    cfg = html.escape(prov.source_text or "(config text unavailable)")
    refs = refs or []
    items = []
    for rs in refs:
        if rs.error:
            status = f'<span style="color:#cf222e">could not resolve — {html.escape(rs.error)}</span>'
        else:
            status = f'{len(rs.points)} overlay point(s)'
        items.append(f"<li>{html.escape(rs.label)} <code>{html.escape(rs.kind)}</code> — {status}</li>")
    refs_html = "".join(items) or "<li>none declared</li>"
    return (
        f'<h2>Constants &amp; provenance</h2>'
        f'<p><b>Model commit:</b> <code>{html.escape(prov.git_hash)}</code> · '
        f'<b>Run:</b> {html.escape(prov.timestamp)} · '
        f'<b>Points:</b> {prov.n_points} · '
        f'<b>Source:</b> <code>{html.escape(prov.source_path or "")}</code></p>'
        f'<h4>Declared references</h4><ul>{refs_html}</ul>'
        f'<details><summary>Resolved constants (every value used)</summary>'
        f'<pre>{html.escape(consts_txt)}</pre></details>'
        f'<details><summary>Verbatim study config</summary><pre>{cfg}</pre></details>'
    )


_JS = """
function sortTable(col){
  var t=document.getElementById('scoretable');
  var tb=t.tBodies[0];
  // group main+drill rows
  var groups=[];
  for(var i=0;i<tb.rows.length;i+=2){groups.push([tb.rows[i],tb.rows[i+1]]);}
  var dir=t.getAttribute('data-dir')==='asc'?-1:1;
  t.setAttribute('data-dir',dir===1?'asc':'desc');
  groups.sort(function(a,b){
    var x=a[0].cells[col].getAttribute('data-v');
    var y=b[0].cells[col].getAttribute('data-v');
    var nx=parseFloat(x),ny=parseFloat(y);
    if(!isNaN(nx)&&!isNaN(ny))return (nx-ny)*dir;
    return (''+x).localeCompare(''+y)*dir;
  });
  groups.forEach(function(g){tb.appendChild(g[0]);tb.appendChild(g[1]);});
}
function toggleDrill(i){
  var r=document.getElementById('drill'+i);
  r.style.display = r.style.display==='none' ? 'table-row' : 'none';
}
function composePlot(j){
  var fig=document.getElementById('plotfig'+j);
  var img=document.getElementById('plotimg'+j);
  var best=false, ref=false;
  fig.querySelectorAll('input[type=checkbox]').forEach(function(cb){
    if(cb.getAttribute('data-role')==='best') best=cb.checked;
    if(cb.getAttribute('data-role')==='ref')  ref=cb.checked;
  });
  var key = best && ref ? 'bestref' : best ? 'best' : ref ? 'ref' : 'base';
  var uri = img.getAttribute('data-'+key) || img.getAttribute('data-base');
  img.src = uri;
}
"""


def _css() -> str:
    return """
:root{color-scheme:light dark;}
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
     margin:0;padding:2rem;max-width:1200px;margin:auto;line-height:1.5;}
h1{margin-bottom:.2rem;} .goal{color:#8b949e;margin-top:0;}
table{border-collapse:collapse;width:100%;font-size:13px;margin:1rem 0;}
th,td{border:1px solid #d0d7de;padding:5px 8px;text-align:right;white-space:nowrap;}
th:nth-child(2),td:nth-child(2){text-align:left;}
th{background:#f6f8fa;cursor:pointer;position:sticky;top:0;user-select:none;}
tr.mainrow{cursor:pointer;} tr.mainrow:hover td{background:rgba(127,127,127,.08);}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:middle;}
.chip{display:inline-block;background:rgba(207,34,46,.12);border:1px solid rgba(207,34,46,.3);
      border-radius:10px;padding:0 7px;margin:1px;font-size:11px;white-space:nowrap;}
.drill td{background:rgba(127,127,127,.06);text-align:left;white-space:normal;}
.drillgrid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1rem;}
.drillgrid pre{background:rgba(127,127,127,.1);padding:.5rem;border-radius:6px;overflow:auto;font-size:11px;max-height:320px;}
.plots{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:1.5rem;}
figure.plot{margin:0;} figure.plot img{max-width:100%;border:1px solid #d0d7de;border-radius:6px;}
figcaption{font-size:12px;color:#57606a;margin-top:.4rem;}
.toggle{font-size:12px;margin-left:.5rem;}
.legend span{margin-right:1rem;font-size:12px;}
pre{white-space:pre-wrap;}
@media (prefers-color-scheme:dark){
  th{background:#161b22;} th,td{border-color:#30363d;} .goal,figcaption{color:#8b949e;}
}
"""


def write_workbook(result: StudyResult, out_path: str | Path) -> Path:
    """Render *result* to a self-contained HTML chapter and emit its JSON sidecar."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    scored = score_result(result, result.study.scoring)
    goal = result.study.goal
    best = set(_best_indices(scored, goal))

    # resolve click-in reference overlays (modelled / experimental / chapter)
    from stepgen.studio.references import resolve_references
    refs = resolve_references(result.study)

    plots = _build_plots(scored, goal, refs)
    plots_html = _plots_html(plots)

    n_green = sum(1 for s in scored if s.overall == "green")
    n_orange = sum(1 for s in scored if s.overall == "orange")
    n_red = sum(1 for s in scored if s.overall == "red")

    doc = f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(result.study.title)}</title>
<style>{_css()}</style></head>
<body>
<h1>{html.escape(result.study.title)}</h1>
<p class="goal">Goal: <b>{html.escape(goal or "—")}</b> ·
  Families: {html.escape(", ".join(result.study.families))} ·
  {len(scored)} configs</p>
<p class="legend">
  <span>{_light("green")}green {n_green}</span>
  <span>{_light("orange")}orange {n_orange}</span>
  <span>{_light("red")}red {n_red}</span>
  <span>★ = best {len(best)} for the goal</span>
</p>

<h2>Overview — scored comparison</h2>
<p style="font-size:12px;color:#57606a">Click a header to sort; click a row to drill in.
Verdict is <b>worst-category-wins</b> across every applicable gate; grey = N-A for that family.</p>
{_table_html(scored, best)}

<h2>Standard plots</h2>
{plots_html}

{_provenance_html(result, refs)}

<script>{_JS}</script>
</body></html>
"""
    out_path.write_text(doc, encoding="utf-8")

    # JSON sidecar for cross-chapter reference
    sidecar = out_path.with_suffix(".json")
    sidecar.write_text(json.dumps(_chapter_json(result, scored), indent=2, default=str),
                       encoding="utf-8")
    return out_path


def _chapter_json(result: StudyResult, scored: list[ScoredRow]) -> dict[str, Any]:
    return {
        "title": result.study.title,
        "goal": result.study.goal,
        "families": result.study.families,
        "git_hash": result.provenance.git_hash,
        "timestamp": result.provenance.timestamp,
        "rows": [
            {
                "label": sr.metrics.label,
                "family": sr.metrics.family,
                "overall": sr.overall,
                "chips": sr.chips,
                "params": sr.metrics.params,
                "metrics": {
                    "throughput_mlhr": sr.metrics.throughput_mlhr,
                    "N_dfu": sr.metrics.N_dfu,
                    "droplet_um": sr.metrics.droplet_um,
                    "frequency_hz": sr.metrics.frequency_hz,
                    "uniformity_pct": sr.metrics.uniformity_pct,
                    "operating_Po_mbar": sr.metrics.operating_Po_mbar,
                    "regime_Ca": sr.metrics.regime_Ca,
                    "hub_budget_pct": sr.metrics.hub_budget_pct,
                    "area_used_cm2": sr.metrics.area_used_cm2,
                    "fits_square": sr.metrics.fits_square,
                    "manufacturable": sr.metrics.manufacturable,
                },
            }
            for sr in scored
        ],
    }


def write_book_index(book_dir: str | Path) -> Path:
    """Write ``book/index.html`` linking every ``*.json`` chapter in *book_dir*."""
    book_dir = Path(book_dir)
    book_dir.mkdir(parents=True, exist_ok=True)
    chapters = []
    for jf in sorted(book_dir.glob("*.json")):
        if jf.name == "index.json":
            continue
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        chapters.append((jf.with_suffix(".html").name, data))

    items = []
    for html_name, data in chapters:
        rows = data.get("rows", [])
        greens = sum(1 for r in rows if r.get("overall") == "green")
        fams = ", ".join(data.get("families", []) or [])
        items.append(
            f'<li><a href="{html.escape(html_name)}">{html.escape(data.get("title","(untitled)"))}</a>'
            f' — goal <b>{html.escape(str(data.get("goal","")))}</b>, '
            f'families <i>{html.escape(fams)}</i>, '
            f'{len(rows)} configs, {greens} green '
            f'<span style="color:#8b949e">[{html.escape(str(data.get("git_hash",""))[:8])}]</span></li>'
        )
    body = "".join(items) or "<li>no chapters yet</li>"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>StepGen Design Studio — book</title><style>{_css()}</style></head>
<body><h1>StepGen Design Studio — book</h1>
<p class="goal">Chapters tie together here; each is a self-contained scored study. Generated {ts}.</p>
<ul>{body}</ul></body></html>"""
    index = book_dir / "index.html"
    index.write_text(doc, encoding="utf-8")
    return index
