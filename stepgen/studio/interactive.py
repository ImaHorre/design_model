"""
stepgen.studio.interactive
==========================
The client-side half of a chapter: one JSON payload and the code that reads it.

A chapter used to be a static render — the decision was computed once over every
row, and the plots were PNGs baked at write time.  That makes the two questions a
designer actually asks unanswerable:

    "I only care about o/w — don't show me anything about switching to w/o."
    "Show me flatness against device length for this design, with the Ca ceiling
     drawn, and let me pin the three points I like."

Both need the *filter* to reach the decision layer and the plots, not just the
table.  So every row travels into the page as data, and the winner cards, the
counts, the plots and the table are all recomputed in the browser from whatever
subset is currently visible.  Nothing about the physics moves — the solve, the
scoring and the thresholds are still Python's, done once — but which rows those
verdicts are being read over is now the reader's to choose.

What lives here
---------------
:func:`chapter_payload`   every scored row, axis and threshold, as plain JSON
:data:`INTERACTIVE_JS`    filter → visible set → cards, table, SVG plots, pins
:data:`INTERACTIVE_CSS`   styling for the above

The plots are hand-drawn SVG rather than a charting library: a chapter has to be
one self-contained file with no external requests, and the four things needed
here — log axes, a shaded regime ceiling, click-to-pin and colour-by-design —
are less code than a bundled library would be.
"""

from __future__ import annotations

import json
from typing import Any, Sequence

from stepgen.families.base import CA_MEASURED_MAX, SE_CEILING_CA
from stepgen.studio.grouping import Axis, Grouping
from stepgen.studio.ranking import Decision, ValueAxis
from stepgen.studio.scoring import BUILD_GATES, ScoredRow, build_gate_state

#: Metrics offered as plot axes, in menu order: key -> (label, format, log-by-default).
#: Anything a family cannot compute is dropped from the menu at build time, so a
#: serpentine-only chapter never offers hub ΔP.
PLOT_METRICS: list[tuple[str, str, str, bool]] = [
    ("throughput_mlhr", "Throughput", "f1", False),
    ("uniformity_pct", "ΔP flatness (%)", "f1", False),
    ("regime_Ca", "Exit Ca", "ca", True),
    ("v_vs_demonstrated", "x vs demonstrated", "f1", True),
    ("operating_Po_mbar", "Drive pressure (mbar)", "int", False),
    ("N_dfu", "N DFU", "int", False),
    ("frequency_hz", "Frequency (Hz)", "freq", False),
    ("dP_rung_mbar", "ΔP across rung (mbar)", "f1", False),
    ("t_cycle_s", "Cycle time (s)", "g3", True),
    ("droplet_um", "Droplet (µm)", "f1", False),
    ("area_used_cm2", "Area (cm²)", "f1", False),
    ("emulsion_pct", "Emulsion (%)", "f1", False),
    ("margin", "Margin from failure", "pct0", False),
]

#: Metrics offered as numeric limits in the filter bar — the "show me only
#: flatness under 25%" control.  Kept short on purpose: a filter bar with twelve
#: range boxes is not a filter bar.
LIMIT_METRICS = ["uniformity_pct", "v_vs_demonstrated", "regime_Ca",
                 "throughput_mlhr", "operating_Po_mbar"]

#: Preset views, chosen because each answers a question the study exists to ask.
#: A preset whose axis is not present in this study is dropped rather than shown
#: broken.  Deliberately absent: anything against droplet size (geometry-set and
#: Ca-independent in SE, so it is a flat line by construction) and throughput
#: against DFU count (they are the same quantity twice).
PRESETS: list[dict[str, Any]] = [
    {
        "name": "Output vs blow-out risk",
        "x": "throughput_mlhr", "y": "regime_Ca", "logy": True,
        "note": "Every mL/hr is bought with exit velocity. The shaded band is where "
                "step-emulsification is no longer believed to hold.",
    },
    {
        "name": "Flatness vs device length",
        "x": "main.length_mm", "y": "uniformity_pct",
        "note": "Droop accumulates along the main: the cost of a longer ladder.",
    },
    {
        "name": "The trade — flatness vs throughput",
        "x": "throughput_mlhr", "y": "uniformity_pct",
        "note": "Down-left is gentle and uniform; up-right pushes oil and starves "
                "the far rungs.",
    },
    {
        "name": "Regime vs drive pressure",
        "x": "operating_Po_mbar", "y": "regime_Ca", "logy": True,
        "note": "Where each design leaves the regime its droplet size is predicted in.",
    },
    {
        "name": "Flatness vs N DFU",
        "x": "N_dfu", "y": "uniformity_pct",
        "note": "How many DFUs one main can feed before the far end stops matching "
                "the near end.",
    },
]


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def verdict_reason(row: ScoredRow) -> tuple[str, str]:
    """
    ``(category, one-line why)`` — the gate that decided this row's verdict.

    Reading a table of 350 traffic lights is only useful if each one says what
    it is about.  The binding cell is the worst category, and within that the
    tightest margin, so the sentence names the gate that would have to move for
    the verdict to change — not merely the first one that failed.

    Green rows get the same treatment in reverse: the gate with the least
    headroom, because "green with 4% margin" and "green with 3 spans of margin"
    are different designs.
    """
    if row.metrics.error:
        return "red", f"solve failed: {row.metrics.error}"

    order = {"red": 0, "orange": 1, "green": 2}
    graded = [c for c in row.cells.values() if c.category in order]
    if not graded:
        return row.overall, "no applicable gate"

    worst = min(graded, key=lambda c: order[c.category]).category
    candidates = [c for c in graded if c.category == worst]
    # tightest first; cells with no margin (gates) sort last so a numeric reason
    # is preferred over "gate failed" when both are red
    candidates.sort(key=lambda c: (c.margin is None, c.margin if c.margin is not None else 0))
    cell = candidates[0]

    if worst == "green":
        pct = f" ({cell.margin * 100:.0f}% margin)" if cell.margin is not None else ""
        return "green", f"all gates pass · tightest {cell.key}{pct}"
    reason = cell.reason or cell.key
    if cell.detail and not cell.reason:
        reason = cell.detail[0]
    return worst, reason


def build_gate_json(sr: ScoredRow, scoring: dict[str, Any]) -> dict[str, Any]:
    """
    One row's build sub-gates, as the browser's three-state control needs them.

    ``g``  which applicable sub-gates passed (``True``) or failed (``False``)
    ``s``  the state the *study* resolved each to — gate / report / off (W2-4)
    ``why`` Python's sentence for a failure, so an override that turns a gate
           back on can say why the row went red without composing English in JS

    **This is not scoring in the browser.**  The categories the page combines are
    all Python's: what moves under the control is *which* of them apply, exactly
    as the verdict filter already chooses which rows apply.  See the invariant
    note at the top of :data:`INTERACTIVE_JS`.
    """
    build_spec = (scoring or {}).get("build", {}) or {}
    gates, states, why = {}, {}, []
    for key, (attr, human) in BUILD_GATES.items():
        val = getattr(sr.metrics, attr, None)
        if val is None:
            continue                       # not applicable to this family
        gates[key] = bool(val)
        states[key] = build_gate_state(build_spec, key, pinned=sr.pinned)
        if val is False:
            why.append(f"{human} — no")
    return {"g": gates, "s": states, "why": "; ".join(why)}


def _schema_version() -> int:
    """The chapter schema version, from its one definition in ``workbook``."""
    from stepgen.studio.workbook import SCHEMA_VERSION

    return SCHEMA_VERSION


def chapter_payload(
    scored: Sequence[ScoredRow],
    grouping: Grouping,
    leaves: dict[int, dict[str, Any]],
    dec_axes: Sequence[ValueAxis],
    decisions: dict[str, Decision],
    scoring: dict[str, Any],
    refs: Sequence[Any] = (),
) -> dict[str, Any]:
    """Everything the browser needs to recompute the chapter over a subset."""
    axes = list(grouping.design_axes) + list(grouping.condition_axes)

    def axis_json(a: Axis, kind: str) -> dict[str, Any]:
        return {
            "path": a.path, "label": a.label, "unit": a.unit, "spec": a.spec,
            "kind": kind, "numeric": a.is_numeric,
            "values": [{"v": v, "t": a.show(v)} for v in a.values],
        }

    rows: list[dict[str, Any]] = []
    for i, sr in enumerate(scored):
        cat, why = verdict_reason(sr)
        metrics = {key: _num(getattr(sr.metrics, key, None))
                   for key, _, _, _ in PLOT_METRICS if key != "margin"}
        metrics["margin"] = sr.min_margin_discounted
        rows.append({
            "i": i,
            "gid": grouping.group_of.get(i, ""),
            "label": sr.metrics.label,
            "verdict": sr.overall,
            "why": why,
            "v": {a.path: leaves.get(i, {}).get(a.path) for a in axes},
            "m": metrics,
            # the γ this row's exit Ca was computed at [N/m].  Per row, not per
            # study: a study may carry several fluid systems, and Ca ∝ 1/γ
            # exactly — so the filter bar can only state the constant behind a
            # Ca verdict if each row brings its own.  Kept out of "m" so it
            # never becomes a plot axis; it is provenance, not a result.
            "gamma": _num(sr.metrics.gamma_Nm),
            # per-metric distance from the ceiling (uncapped), for the
            # Ca-distance column.  min_margin cannot answer "how far is the Ca".
            "margins": {k: c.margin for k, c in sr.cells.items()
                        if c.category != "grey" and c.margin is not None},
            # ── D2: the three-state gate control ────────────────────────────
            # `vnb` is the verdict with `build` left out, so the browser can
            # recombine it with a build category the reader has re-stated
            # without re-deriving a single threshold.  `pin` is decision 10's
            # provenance: did the USER choose this geometry?
            "b": build_gate_json(sr, scoring),
            "vnb": sr.verdict_without_build,
            "pin": bool(sr.pinned),
        })

    # only offer plot axes some row can actually place
    metrics_menu = [
        {"key": k, "label": lbl, "fmt": f, "log": lg}
        for k, lbl, f, lg in PLOT_METRICS
        if any(r["m"].get(k) is not None for r in rows)
    ]
    have = {m["key"] for m in metrics_menu} | {a.path for a in axes if a.is_numeric}
    presets = [p for p in PRESETS if p["x"] in have and p["y"] in have]

    ref_series = []
    for rs in refs or []:
        if getattr(rs, "error", None):
            continue
        pts = []
        for p in rs.points:
            pts.append({k: _num(getattr(p, k, None))
                        for k, _, _, _ in PLOT_METRICS if k != "margin"})
        if pts:
            ref_series.append({"label": rs.label, "kind": rs.kind, "points": pts})

    return {
        # The payload is a SECOND row serialiser beside `_chapter_json`, and it is
        # the one a reader filters in the browser — so it carries the schema
        # version too. A chapter whose page lets you narrow to a subset must be
        # able to say which vintage of the model produced that subset.
        # Imported here rather than at module scope: workbook imports interactive.
        "schemaVersion": _schema_version(),
        "axes": ([axis_json(a, "design") for a in grouping.design_axes]
                 + [axis_json(a, "condition") for a in grouping.condition_axes]),
        "groups": [
            {"gid": g.gid, "label": g.label(grouping.design_axes),
             "values": {a.path: a.show(g.values.get(a.path))
                        for a in grouping.design_axes},
             "idx": list(g.indices)}
            for g in grouping.groups
        ],
        "decideAxes": [
            {"key": a.key, "label": a.label, "source": a.source,
             "higher": a.higher_better, "unit": a.unit, "onRow": a.on_row}
            for a in dec_axes
        ],
        "weights": dict(next(iter(decisions.values())).weights) if decisions else {},
        "metrics": metrics_menu,
        "limits": [m for m in LIMIT_METRICS if m in {x["key"] for x in metrics_menu}],
        "presets": presets,
        "rows": rows,
        "refs": ref_series,
        "thresholds": {k: v for k, v in (scoring or {}).items()
                       if isinstance(v, dict) and "green" in v},
        # sub-gates some row can actually answer, in BUILD_GATES order.  A radial
        # chapter offers no `no_crossing` control rather than a dead one.
        "buildGates": [{"key": k, "label": human}
                       for k, (_, human) in BUILD_GATES.items()
                       if any(k in r["b"]["g"] for r in rows)],
        "caCeiling": SE_CEILING_CA,
        "caMeasured": CA_MEASURED_MAX,
    }


def payload_script(payload: dict[str, Any]) -> str:
    """The payload as an inline ``<script>`` body."""
    blob = json.dumps(payload, default=str, separators=(",", ":"))
    # </script> can never appear inside the blob or it closes the tag early
    blob = blob.replace("</", "<\\/")
    return f"const CHAPTER={blob};"


INTERACTIVE_CSS = """
/* ── control rail ────────────────────────────────────────────────────────── */
.rail{position:sticky;top:0;z-index:20;background:#fff;
  border-bottom:1px solid #d0d7de;padding:.5rem 0 .55rem;margin-bottom:1rem;}
.line{display:flex;flex-wrap:wrap;gap:.4rem .8rem;align-items:flex-end;}
.line label{display:flex;flex-direction:column;font-size:10.5px;color:#57606a;gap:1px;}
.line select,.line input{font-size:12px;padding:2px 5px;border-radius:5px;
  border:1px solid #d0d7de;background:transparent;color:inherit;max-width:210px;}
.line input[type=number]{width:74px;}
.line input[type=checkbox]{width:auto;}
.count{font-size:12px;font-weight:600;margin-left:auto;align-self:center;}
/* the γ behind the Ca column — never quiet, because a Ca verdict read without
   its interfacial tension is a physics claim with an invisible constant */
.gnote{font-size:11.5px;color:#57606a;align-self:center;flex-basis:100%;}
.gnote.mixed{color:#9a6700;font-weight:600;}
/* the three-state gate control (D2 / decision 10) */
.glabel{font-size:11px;font-weight:600;color:#57606a;align-self:center;
  text-transform:uppercase;letter-spacing:.03em;}
.tabbar{display:flex;gap:.3rem;margin-top:.5rem;border-bottom:1px solid #d0d7de;}
.tabbtn{font-size:12.5px;padding:.35rem .9rem;border:1px solid transparent;
  border-bottom:none;border-radius:7px 7px 0 0;background:transparent;color:inherit;
  cursor:pointer;margin-bottom:-1px;}
.tabbtn:hover{background:rgba(127,127,127,.1);}
.tabbtn.on{border-color:#d0d7de;background:rgba(9,105,218,.1);font-weight:600;
  border-bottom:1px solid transparent;}
.chipbar{display:flex;flex-wrap:wrap;gap:.3rem;margin-top:.4rem;font-size:11px;
  align-items:center;}
table.pintbl td.why{max-width:280px;white-space:normal;font-size:11.5px;}
.pinchip{border:1px solid #0969da;border-radius:10px;padding:0 7px;cursor:pointer;
  background:rgba(9,105,218,.12);}
.pinchip::after{content:" ✕";opacity:.55;}

/* ── plots ───────────────────────────────────────────────────────────────── */
.plotwrap{border:1px solid #d0d7de;border-radius:10px;padding:.6rem .8rem;margin:1rem 0;}
.plotwrap svg{width:100%;height:auto;display:block;}
.plotnote{font-size:11.5px;color:#57606a;margin:.3rem 0 0;}
.pt{cursor:pointer;}
.pt:hover{stroke:#0969da;stroke-width:2;}

/* ── design panels ───────────────────────────────────────────────────────── */
.dhead{display:flex;flex-wrap:wrap;gap:.5rem 1rem;align-items:baseline;}
.dparams{display:flex;flex-wrap:wrap;gap:.15rem 1.1rem;list-style:none;
  padding:0;margin:.3rem 0 .6rem;font-size:12.5px;}
.dparams li{white-space:nowrap;}
.dparams li b{font-size:13.5px;}
.dparams li span{color:#57606a;font-size:11px;}
.pick{cursor:pointer;}
.pick:hover{border-color:#0969da;}
tr.pinned td{outline:2px solid #0969da;outline-offset:-2px;}
tr.hit td{background:rgba(9,105,218,.18)!important;}
@media (prefers-color-scheme:dark){
  .rail{background:#0d1117;border-color:#30363d;}
  .line select,.line input,.plotwrap,.tabbar,.tabbtn.on{border-color:#30363d;}
  .line label,.plotnote,.dparams li span,.glabel{color:#8b949e;}
}
"""


INTERACTIVE_JS = r"""
// ── THE INVARIANT THIS FILE EXISTS UNDER (D7) ──────────────────────────────
// No threshold comparison happens in JavaScript. Every category on this page —
// green / orange / red / grey, per metric and per row — was computed in Python
// against the study's scoring block, once, and travels here as data. The browser
// chooses which rows and which gates apply; it never decides what a number means.
//
// The three-state gate control (D2) is the one place that looks like an
// exception and is not: it recombines `row.vnb` (Python's verdict with `build`
// left out) with a build category that is a lookup over Python's own pass/fail
// booleans. Nothing is compared against a bound. If you ever find yourself
// comparing a row value against one of the payload's thresholds here, stop —
// that is scoring, it belongs in scoring.py, and there is a test in
// tests/test_studio.py that greps this string and fails.
//
// (The thresholds ARE read here — the plot draws the ceiling as a band. Reading
// one is fine; deciding a colour with one is not.)
//
// ── formatting ─────────────────────────────────────────────────────────────
// Never toLocaleString() with the default locale: the reader's browser decides
// the decimal separator, and a chapter that prints 144,3 mL/hr next to a
// server-rendered 144.3 in the same table is reporting two different numbers as
// far as anyone scanning it is concerned. Grouping is done by hand for the same
// reason — one formatter, one output, wherever it is opened.
function group(intStr){ return intStr.replace(/\B(?=(\d{3})+(?!\d))/g, ','); }
function fixed(v, dp){
  var s = Math.abs(v).toFixed(dp), parts = s.split('.');
  return (v<0?'-':'') + group(parts[0]) + (parts[1] ? '.'+parts[1] : '');
}
function fmtN(v, spec){
  if(v===null||v===undefined||isNaN(v)) return '—';
  v = Number(v);
  if(spec==='f1')   return fixed(v,1);
  if(spec==='int')  return fixed(v,0);
  if(spec==='freq') return Math.abs(v)>=100 ? fixed(v,0) : fixed(v,1);
  if(spec==='ca')   return Math.abs(v)<1 ? v.toFixed(4) : fixed(v,2);
  if(spec==='pct0') return Math.round(v*100)+'%';
  return String(Number(v.toPrecision(3)));
}
const CAT={green:'#1a7f37',orange:'#bf8700',red:'#cf222e',grey:'#8b949e'};
const SERIES=['#0969da','#8250df','#bf8700','#1a7f37','#cf222e','#0a7c86'];
function esc(s){return String(s).replace(/[&<>"]/g,function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}

// ── state ──────────────────────────────────────────────────────────────────
// S.gate maps a build sub-gate to '' (as the study scored it, per row) or one of
// 'gate' / 'report' / 'off'. Empty is the default and MUST reproduce Python's
// verdict exactly — that equivalence is what makes the control safe.
const S = {f:{}, lim:[{k:'',min:null,max:null},{k:'',min:null,max:null}],
           pin:[], plot:0, x:null, y:null, logx:false, logy:false, colour:'verdict',
           pinOnly:false, showBest:true, tab:'explore', gate:{}};

// ── the three-state gate control (D2 / decision 10) ────────────────────────
// Decision 10: a gate exists to stop the TOOL proposing something you would not
// want; it does not exist to overrule a choice you have already made. So a
// failing sub-gate on geometry YOU pinned is reported, not gated. That is a
// judgement about provenance, and provenance is exactly the thing a reader may
// legitimately disagree with — hence a control rather than a fixed policy.
const ORDER={green:0,orange:1,red:2,grey:0};
function gateState(r, k){ return S.gate[k] || r.b.s[k]; }
function buildCatOf(r){
  var g=(r.b&&r.b.g)||{};
  for(var k in g){
    if(g[k]!==false) continue;
    if(gateState(r,k)==='gate') return 'red';
  }
  return 'green';
}
function verdictOf(r){
  if(!r.b||!r.b.s) return r.verdict;
  var a=r.vnb||'green', b=buildCatOf(r);
  return (ORDER[b]>ORDER[a]) ? b : a;
}
// The row's one-line reason, respecting an override. Python wrote both strings;
// this only picks which of them the current gate states make true.
function whyOf(r){
  if(verdictOf(r)==='red' && buildCatOf(r)==='red' && r.vnb!=='red')
    return r.b.why || 'build gate failed';
  return r.why;
}
function gateOverridden(){
  for(var k in S.gate){ if(S.gate[k]) return true; }
  return false;
}
// How many rows the reader's override actually moved. A control that silently
// changes 200 verdicts is worse than no control: this says so, in the rail.
function gateDelta(rows){
  var n=0;
  rows.forEach(function(r){ if(verdictOf(r)!==r.verdict) n++; });
  return n;
}

// ── tabs ───────────────────────────────────────────────────────────────────
// One page, four views. A 4 MB chapter where the plot sits below three screens
// of decision panels is a chapter nobody plays with: the filters and the plot
// have to be the thing you land on.
function showTab(name){
  S.tab=name;
  document.querySelectorAll('.tabpane').forEach(function(p){
    p.style.display = (p.getAttribute('data-tab')===name) ? '' : 'none';
  });
  document.querySelectorAll('.tabbtn').forEach(function(b){
    b.classList.toggle('on', b.getAttribute('data-tab')===name);
  });
  if(name==='explore') paintPlot(shown());
}

function metricOf(key){return CHAPTER.metrics.find(function(m){return m.key===key;});}
function axisOf(path){return CHAPTER.axes.find(function(a){return a.path===path;});}
function valueOf(row, key){
  if(key in row.m) return row.m[key];
  var v = row.v[key];
  return (typeof v === 'number') ? v : null;
}
function labelOf(key){
  var m = metricOf(key); if(m) return m.label;
  var a = axisOf(key);   return a ? (a.unit ? a.label+' ('+a.unit+')' : a.label) : key;
}
function fmtOf(key){
  var m = metricOf(key); if(m) return m.fmt;
  var a = axisOf(key);   return a ? (a.spec==='int'?'int':'f1') : 'g3';
}
// axis ticks drop the decimal once the numbers are big: "1,000" reads, "1,000.0"
// just makes the axis wider
function tickOf(key, v){
  var f=fmtOf(key);
  if((f==='f1'||f==='freq') && Math.abs(v)>=100) return fixed(v,0);
  return fmtN(v,f);
}

// ── the control rail ───────────────────────────────────────────────────────
function buildRail(){
  var h=[];
  h.push('<div class="line">');
  h.push('<label>Design<select data-f="__gid"><option value="">All designs</option>'
    + CHAPTER.groups.map(function(g){return '<option value="'+g.gid+'">'+esc(g.gid+' — '+g.label)+'</option>';}).join('')
    + '</select></label>');
  CHAPTER.axes.forEach(function(a){
    h.push('<label>'+esc(a.label)+(a.unit?' ('+esc(a.unit)+')':'')
      +'<select data-f="'+esc(a.path)+'"><option value="">Any</option>'
      + a.values.map(function(o){return '<option value="'+esc(o.v)+'">'+esc(o.t)+'</option>';}).join('')
      + '</select></label>');
  });
  h.push('<label>Verdict<select data-f="__verdict"><option value="">Any</option>'
    +'<option value="green">green</option><option value="orange">orange</option>'
    +'<option value="red">red</option></select></label>');
  h.push('<span class="count" id="railcount"></span>');
  h.push('</div><div class="line" style="margin-top:.35rem">');
  for(var i=0;i<2;i++){
    h.push('<label>Limit '+(i+1)+'<select data-lim="'+i+'" data-part="k">'
      +'<option value="">none</option>'
      + CHAPTER.limits.map(function(k){return '<option value="'+k+'">'+esc(labelOf(k))+'</option>';}).join('')
      + '</select></label>');
    h.push('<label>min<input type="number" step="any" data-lim="'+i+'" data-part="min"></label>');
    h.push('<label>max<input type="number" step="any" data-lim="'+i+'" data-part="max"></label>');
  }
  h.push('<button class="btn" onclick="resetAll()">Reset filters</button>');
  h.push('<button class="btn" onclick="clearPins()">Clear pins</button>');
  h.push('<span class="gnote" id="gammanote"></span>');
  h.push('</div>');
  if((CHAPTER.buildGates||[]).length){
    h.push('<div class="line" style="margin-top:.35rem">');
    h.push('<span class="glabel">Build gates</span>');
    CHAPTER.buildGates.forEach(function(bg){
      h.push('<label>'+esc(bg.label)+'<select data-gate="'+esc(bg.key)+'">'
        +'<option value="">as scored</option>'
        +'<option value="gate">gate — fail the row</option>'
        +'<option value="report">report — chip only</option>'
        +'<option value="off">off — silent</option>'
        +'</select></label>');
    });
    h.push('<span class="gnote" id="gatenote"></span>');
    h.push('</div>');
  }
  h.push('<div class="chipbar" id="pinbar"></div>');
  h.push('<div class="tabbar">'
    + [['explore','Explore'],['designs','Designs'],['runs','All runs'],['notes','Notes']]
      .map(function(t){return '<button class="tabbtn" data-tab="'+t[0]+'" onclick="showTab(\''+t[0]+'\')">'+t[1]+'</button>';}).join('')
    + '</div>');
  document.getElementById('rail').innerHTML = h.join('');

  document.querySelectorAll('#rail select[data-f]').forEach(function(sel){
    sel.addEventListener('change', function(){
      var key=sel.getAttribute('data-f');
      if(key==='__gid'||key==='__verdict') S[key]=sel.value; else S.f[key]=sel.value;
      paint();
    });
  });
  document.querySelectorAll('#rail [data-lim]').forEach(function(el){
    el.addEventListener('change', function(){
      var i=+el.getAttribute('data-lim'), part=el.getAttribute('data-part');
      if(part==='k') S.lim[i].k=el.value;
      else S.lim[i][part] = el.value===''?null:parseFloat(el.value);
      paint();
    });
  });
  document.querySelectorAll('#rail select[data-gate]').forEach(function(sel){
    sel.addEventListener('change', function(){
      S.gate[sel.getAttribute('data-gate')] = sel.value;
      paint();
    });
  });
}

// ── "you set this" ─────────────────────────────────────────────────────────
// The marker decision 10 needs on the page: which of the visible rows carry
// geometry the USER pinned, and therefore have their build sub-gates demoted to
// reports by default. Without it "why is this green when it does not fit the
// die?" has no answer anywhere on the page.
function paintGateNote(rows){
  var el=document.getElementById('gatenote');
  if(!el) return;
  var pinned=0, demoted=0, moved=gateDelta(rows);
  rows.forEach(function(r){
    if(!r.b||!r.b.s) return;
    if(r.pin) pinned++;
    var g=r.b.g;
    for(var k in g){
      if(g[k]===false && gateState(r,k)==='report'){ demoted++; break; }
    }
  });
  var bits=[];
  if(pinned===rows.length && rows.length)
    bits.push('⚪ you set this geometry — build failures are reported, not gated');
  else if(pinned)
    bits.push('⚪ '+pinned+' of '+rows.length+' rows carry geometry you set');
  if(demoted) bits.push(demoted+' row'+(demoted===1?'':'s')+' fail a gate that is only reporting');
  if(gateOverridden()) bits.push('override active — '+moved+' verdict'+(moved===1?'':'s')+' differ from the chapter as scored');
  el.textContent = bits.join(' · ');
  el.className = 'gnote' + (gateOverridden() ? ' mixed' : '');
}

function passes(r){
  if(S.__gid && r.gid!==S.__gid) return false;
  if(S.__verdict && verdictOf(r)!==S.__verdict) return false;
  for(var p in S.f){
    if(S.f[p]==='') continue;
    if(String(r.v[p]) !== S.f[p]) return false;
  }
  for(var i=0;i<S.lim.length;i++){
    var L=S.lim[i]; if(!L.k) continue;
    var v=valueOf(r,L.k);
    if(v===null||v===undefined) return false;
    if(L.min!==null && v<L.min) return false;
    if(L.max!==null && v>L.max) return false;
  }
  return true;
}
function shown(){ return CHAPTER.rows.filter(passes); }

function resetAll(){
  S.f={}; S.__gid=''; S.__verdict=''; S.gate={};
  S.lim=[{k:'',min:null,max:null},{k:'',min:null,max:null}];
  document.querySelectorAll('#rail select,#rail input').forEach(function(e){e.value='';});
  paint();
}

// ── pins ───────────────────────────────────────────────────────────────────
function togglePin(i){
  var at=S.pin.indexOf(i);
  if(at>=0) S.pin.splice(at,1); else S.pin.push(i);
  paint();
}
function clearPins(){ S.pin=[]; paint(); }
function gotoRow(i){
  if(S.pin.indexOf(i)<0) S.pin.push(i);
  showTab('runs');
  paint();
  var tr=document.getElementById('r'+i);
  if(tr){
    tr.scrollIntoView({behavior:'smooth',block:'center'});
    tr.classList.add('hit');
    setTimeout(function(){tr.classList.remove('hit');},2200);
  }
}
function paintPins(){
  document.getElementById('pinbar').innerHTML = S.pin.length
    ? ('<span class="muted">pinned:</span> ' + S.pin.map(function(i){
        var r=CHAPTER.rows[i];
        return '<span class="pinchip" onclick="togglePin('+i+')">'+esc(r.gid+' #'+(i+1))+'</span>';
      }).join(''))
    : '';
}

// ── the pinned devices, spelled out ────────────────────────────────────────
// Pinning a point on a plot is only half an answer: the other half is what that
// device actually is. Same shape as the design-vs-design table, one row per pin.
function paintPinTable(){
  var host=document.getElementById('pintable');
  if(!host) return;
  if(!S.pin.length){
    host.innerHTML='<p class="muted">No pins yet — click a point on the plot, a '
      +'winner card, or a cell of the design table to pin a run. Pinned runs are '
      +'drawn large on every plot and listed here with their full spec.</p>';
    return;
  }
  var cols = CHAPTER.axes;
  var mets = ['throughput_mlhr','uniformity_pct','regime_Ca','N_dfu'];
  var h = ['<table class="pareto pintbl"><thead><tr><th>Run</th><th>Verdict</th>'];
  cols.forEach(function(a){h.push('<th class="tight">'+esc(a.label)+(a.unit?' ('+esc(a.unit)+')':'')+'</th>');});
  mets.forEach(function(k){h.push('<th class="tight">'+esc(labelOf(k))+'</th>');});
  h.push('<th>Why</th><th></th></tr></thead><tbody>');
  S.pin.forEach(function(i){
    var r=CHAPTER.rows[i];
    h.push('<tr><td><b>'+esc(r.gid)+' #'+(i+1)+'</b></td>');
    h.push('<td><span class="dot" style="background:'+CAT[verdictOf(r)]+'"></span>'+verdictOf(r)+'</td>');
    cols.forEach(function(a){
      var opt=a.values.find(function(o){return String(o.v)===String(r.v[a.path]);});
      h.push('<td class="tight num">'+esc(opt?opt.t:r.v[a.path])+'</td>');
    });
    mets.forEach(function(k){h.push('<td class="tight num">'+fmtN(r.m[k],fmtOf(k))+'</td>');});
    h.push('<td class="why">'+esc(whyOf(r))+'</td>');
    h.push('<td><button class="btn" onclick="event.stopPropagation();gotoRow('+i+')">open</button> '
      +'<button class="btn" onclick="event.stopPropagation();togglePin('+i+')">unpin</button></td></tr>');
  });
  h.push('</tbody></table>');
  host.innerHTML=h.join('');
}

// ── the program's own picks, over the visible rows ─────────────────────────
function bestPicks(rows){
  var out={};
  CHAPTER.decideAxes.forEach(function(ax){
    var r=bestIn(rows,ax);
    // the axis KEY, not its label: "Margin from failure (confidence-discounted)"
    // written beside a data point is wider than the plot
    if(r) (out[r.i]=out[r.i]||[]).push(ax.key.replace('_',' '));
  });
  return out;
}

// ── per-design decision cards, recomputed over the visible rows ────────────
function bestIn(rows, ax){
  var pool = rows.filter(function(r){return verdictOf(r)!=='red';});
  if(!pool.length) pool = rows;
  var best=null, bv=null;
  pool.forEach(function(r){
    var v = (ax.key==='margin') ? r.m.margin : r.m[ax.source];
    if(v===null||v===undefined) return;
    var o = ax.higher ? v : -v;
    if(bv===null||o>bv){bv=o;best=r;}
  });
  return best;
}
function condText(r){
  var bits = CHAPTER.axes.filter(function(a){return a.kind==='condition';}).map(function(a){
    var opt = a.values.find(function(o){return String(o.v)===String(r.v[a.path]);});
    return a.label+' '+(opt?opt.t:r.v[a.path]);
  });
  if(r.m.N_dfu!==null&&r.m.N_dfu!==undefined) bits.push('N '+fixed(r.m.N_dfu,0)+' DFUs');
  return bits.join(' · ');
}
function paintDesigns(rows){
  CHAPTER.groups.forEach(function(g){
    var mine = rows.filter(function(r){return r.gid===g.gid;});
    var host = document.getElementById('picks-'+g.gid);
    var sec  = document.getElementById('grp-'+g.gid);
    if(sec) sec.style.display = mine.length ? '' : 'none';
    var cnt = document.getElementById('cnt-'+g.gid);
    if(cnt){
      var c={green:0,orange:0,red:0};
      mine.forEach(function(r){var v=verdictOf(r);c[v]=(c[v]||0)+1;});
      cnt.innerHTML = mine.length+' shown &middot; '
        +'<span style="color:'+CAT.green+'">'+c.green+'</span> / '
        +'<span style="color:'+CAT.orange+'">'+c.orange+'</span> / '
        +'<span style="color:'+CAT.red+'">'+c.red+'</span>';
    }
    if(!host) return;
    if(!mine.length){ host.innerHTML='<p class="muted">no rows match the filters</p>'; return; }
    host.innerHTML = CHAPTER.decideAxes.map(function(ax){
      var r = bestIn(mine, ax);
      if(!r) return '<div class="pick"><h4>Best '+esc(ax.label)+'</h4><div class="pickval">—</div></div>';
      var v = (ax.key==='margin') ? r.m.margin : r.m[ax.source];
      var txt = (ax.key==='margin') ? Math.round(v*100)+'%'
                                    : fmtN(v, fmtOf(ax.source))+ax.unit;
      return '<div class="pick" onclick="gotoRow('+r.i+')" title="click to pin and jump to row '+(r.i+1)+'">'
        +'<h4>Best '+esc(ax.label)+'</h4>'
        +'<div class="pickval"><span class="dot" style="background:'+CAT[verdictOf(r)]+'"></span>'+esc(txt)+'</div>'
        +'<div class="pickwhy">'+esc(condText(r))+'</div>'
        +'<div class="picksub">row #'+(r.i+1)+' · '+esc(whyOf(r))+'</div></div>';
    }).join('');
  });
}

// ── table ──────────────────────────────────────────────────────────────────
function paintTable(rows){
  var on={}; rows.forEach(function(r){on[r.i]=1;});
  var override=gateOverridden();
  CHAPTER.rows.forEach(function(r){
    var tr=document.getElementById('r'+r.i);
    if(!tr) return;
    tr.style.display = on[r.i] ? '' : 'none';
    tr.classList.toggle('pinned', S.pin.indexOf(r.i)>=0);
    var dr=document.getElementById('drill'+r.i);
    if(dr && !on[r.i]) dr.style.display='none';
    // the verdict, build light and reason are server-rendered; when the reader
    // re-states a gate they have to follow, or the table argues with the plot
    if(!override && !r._painted) return;
    r._painted = override;
    var v=verdictOf(r), b=buildCatOf(r);
    var vc=document.getElementById('v'+r.i);
    if(vc){
      vc.innerHTML='<span class="dot" style="background:'+CAT[v]+'" title="'+v+'"></span>'+v;
      vc.setAttribute('data-v', String(ORDER[v]));
    }
    var gc=document.getElementById('g'+r.i);
    if(gc && r.b && Object.keys(r.b.g).length){
      gc.innerHTML='<span class="dot" style="background:'+CAT[b]+'" title="'+b+'"></span>';
      gc.setAttribute('data-v', String(ORDER[b]));
    }
    var wc=document.getElementById('w'+r.i);
    if(wc){ wc.textContent=whyOf(r); wc.setAttribute('data-v', whyOf(r)); }
  });
}

// ── SVG scatter ────────────────────────────────────────────────────────────
function niceTicks(lo, hi, log){
  var out=[];
  if(log){
    var a=Math.floor(Math.log10(lo)), b=Math.ceil(Math.log10(hi));
    for(var e=a;e<=b;e++) out.push(Math.pow(10,e));
    return out.filter(function(v){return v>=lo*0.999&&v<=hi*1.001;});
  }
  var span=hi-lo; if(span<=0) return [lo];
  var step=Math.pow(10,Math.floor(Math.log10(span/4)));
  [1,2,2.5,5,10].some(function(m){ if(span/(step*m)<=6){step*=m;return true;} return false;});
  for(var v=Math.ceil(lo/step)*step; v<=hi+1e-12; v+=step) out.push(+v.toFixed(10));
  return out;
}
function paintPlot(rows){
  var W=880,H=430,L=74,R=18,T=14,B=46;
  var xk=S.x, yk=S.y, logx=S.logx, logy=S.logy;
  // picks are chosen over everything the filters allow, then drawn on whatever
  // subset is plotted — so "best" does not silently change meaning when the
  // pinned-only view narrows the picture
  var picks = S.showBest ? bestPicks(rows) : {};
  var plotRows = S.pinOnly
    ? rows.filter(function(r){return S.pin.indexOf(r.i)>=0;})
    : rows;
  var pts=[];
  plotRows.forEach(function(r){
    var x=valueOf(r,xk), y=valueOf(r,yk);
    if(x===null||y===null||x===undefined||y===undefined) return;
    if(logx&&x<=0) return; if(logy&&y<=0) return;
    pts.push({r:r,x:x,y:y});
  });
  var refPts=[];
  (CHAPTER.refs||[]).forEach(function(s,si){
    s.points.forEach(function(p){
      var x=p[xk], y=p[yk];
      if(x===null||y===null||x===undefined||y===undefined) return;
      if(logx&&x<=0) return; if(logy&&y<=0) return;
      refPts.push({s:s,si:si,x:x,y:y});
    });
  });
  var all=pts.concat(refPts);
  var host=document.getElementById('plot');
  if(!all.length){ host.innerHTML='<p class="muted">nothing to plot at these filters.</p>'; return; }

  // the bands come from THIS study's scoring block, not from a constant: a
  // chapter that draws one ceiling while its own table scores against another
  // is arguing with itself
  var th=(CHAPTER.thresholds||{})[yk]||null;
  var bands=[];
  if(yk==='regime_Ca'){
    var gb = th ? th.green : CHAPTER.caCeiling;
    var rb = th ? th.orange : CHAPTER.caCeiling;
    bands.push({v:rb, c:CAT.red,    t:'red past '+rb+' — outside step-emulsification', fill:true});
    if(gb!==rb) bands.push({v:gb, c:CAT.orange, t:'green bound '+gb+' — SE→jetting (@montessori2020)'});
    bands.push({v:CHAPTER.caMeasured, c:CAT.green,
                t:'highest exit Ca Peak has measured — '+CHAPTER.caMeasured});
  }

  var xs=all.map(function(p){return p.x;}), ys=all.map(function(p){return p.y;});
  var x0=Math.min.apply(null,xs), x1=Math.max.apply(null,xs);
  var y0=Math.min.apply(null,ys), y1=Math.max.apply(null,ys);
  // the ceiling has to be on screen or the plot argues with itself
  if(bands.length){
    bands.forEach(function(b){ y1=Math.max(y1,b.v*1.1); y0=Math.min(y0,b.v*0.9); });
  }
  if(x0===x1){x0-=Math.abs(x0)*0.05+1e-9;x1+=Math.abs(x1)*0.05+1e-9;}
  if(y0===y1){y0-=Math.abs(y0)*0.05+1e-9;y1+=Math.abs(y1)*0.05+1e-9;}
  if(!logx){var px=(x1-x0)*0.05;x0-=px;x1+=px;}
  if(!logy){var py=(y1-y0)*0.07;y0-=py;y1+=py;}
  if(logx){x0*=0.8;x1*=1.25;} if(logy){y0*=0.8;y1*=1.25;}

  function sx(v){ return logx ? L+(Math.log10(v)-Math.log10(x0))/(Math.log10(x1)-Math.log10(x0))*(W-L-R)
                              : L+(v-x0)/(x1-x0)*(W-L-R); }
  function sy(v){ return logy ? H-B-(Math.log10(v)-Math.log10(y0))/(Math.log10(y1)-Math.log10(y0))*(H-T-B)
                              : H-B-(v-y0)/(y1-y0)*(H-T-B); }

  var g=['<svg viewBox="0 0 '+W+' '+H+'" role="img">'];
  bands.forEach(function(b){
    var Y=sy(b.v);
    if(Y<T-40||Y>H-B+40) return;
    if(b.fill) g.push('<rect x="'+L+'" y="'+T+'" width="'+(W-L-R)+'" height="'
      +Math.max(0,Math.min(Y,H-B)-T)+'" fill="rgba(207,34,46,.08)"/>');
    g.push('<line x1="'+L+'" x2="'+(W-R)+'" y1="'+Y+'" y2="'+Y+'" stroke="'+b.c+'" stroke-dasharray="5 3"/>');
    g.push('<text x="'+(W-R-4)+'" y="'+(Y-4)+'" text-anchor="end" font-size="10" fill="'+b.c+'">'+esc(b.t)+'</text>');
  });
  // axes + ticks
  g.push('<line x1="'+L+'" x2="'+(W-R)+'" y1="'+(H-B)+'" y2="'+(H-B)+'" stroke="#8b949e"/>');
  g.push('<line x1="'+L+'" x2="'+L+'" y1="'+T+'" y2="'+(H-B)+'" stroke="#8b949e"/>');
  niceTicks(x0,x1,logx).forEach(function(v){
    var X=sx(v); if(X<L-1||X>W-R+1) return;
    g.push('<line x1="'+X+'" x2="'+X+'" y1="'+(H-B)+'" y2="'+T+'" stroke="rgba(139,148,158,.18)"/>');
    g.push('<text x="'+X+'" y="'+(H-B+15)+'" text-anchor="middle" font-size="10" fill="#8b949e">'+tickOf(xk,v)+'</text>');
  });
  niceTicks(y0,y1,logy).forEach(function(v){
    var Y=sy(v); if(Y<T-1||Y>H-B+1) return;
    g.push('<line x1="'+L+'" x2="'+(W-R)+'" y1="'+Y+'" y2="'+Y+'" stroke="rgba(139,148,158,.18)"/>');
    g.push('<text x="'+(L-6)+'" y="'+(Y+3)+'" text-anchor="end" font-size="10" fill="#8b949e">'+tickOf(yk,v)+'</text>');
  });
  g.push('<text x="'+((L+W-R)/2)+'" y="'+(H-6)+'" text-anchor="middle" font-size="11.5" fill="currentColor">'+esc(labelOf(xk))+(logx?' (log)':'')+'</text>');
  g.push('<text transform="translate(14,'+((T+H-B)/2)+') rotate(-90)" text-anchor="middle" font-size="11.5" fill="currentColor">'+esc(labelOf(yk))+(logy?' (log)':'')+'</text>');

  // points
  var gidIndex={}; CHAPTER.groups.forEach(function(gr,n){gidIndex[gr.gid]=n;});
  pts.forEach(function(p){
    var pinned = S.pin.indexOf(p.r.i)>=0;
    var col = S.colour==='design' ? SERIES[gidIndex[p.r.gid]%SERIES.length] : CAT[verdictOf(p.r)];
    g.push('<circle class="pt" cx="'+sx(p.x).toFixed(1)+'" cy="'+sy(p.y).toFixed(1)+'" r="'+(pinned?6:3.4)+'"'
      +' fill="'+col+'" fill-opacity="'+(pinned?1:.72)+'"'
      +(pinned?' stroke="#0969da" stroke-width="2"':'')
      +' onclick="togglePin('+p.r.i+')"><title>'+esc(p.r.gid+' #'+(p.r.i+1)+'\n'
      +labelOf(xk)+' '+fmtN(p.x,fmtOf(xk))+'\n'+labelOf(yk)+' '+fmtN(p.y,fmtOf(yk))
      +'\n'+whyOf(p.r))+'</title></circle>');
  });
  // the program's picks: a ring and what it won, so "what does the tool think"
  // and "what have I picked" are both readable at once
  pts.forEach(function(p){
    if(!picks[p.r.i]) return;
    var cx=sx(p.x), cy=sy(p.y);
    g.push('<circle cx="'+cx.toFixed(1)+'" cy="'+cy.toFixed(1)+'" r="9"'
      +' fill="none" stroke="#0969da" stroke-width="1.4" stroke-dasharray="3 2"/>');
    var txt='★ '+picks[p.r.i].join(' + ');
    var tx=Math.min(Math.max(cx, L+txt.length*2.6), W-R-txt.length*2.6);
    g.push('<text x="'+tx.toFixed(1)+'" y="'+(cy-13).toFixed(1)+'"'
      +' text-anchor="middle" font-size="9.5" fill="#0969da">'+esc(txt)+'</text>');
  });
  pts.filter(function(p){return S.pin.indexOf(p.r.i)>=0;}).forEach(function(p){
    g.push('<text x="'+(sx(p.x)+8).toFixed(1)+'" y="'+(sy(p.y)+13).toFixed(1)+'" font-size="10" fill="currentColor">#'+(p.r.i+1)+' '+esc(p.r.gid)+'</text>');
  });
  refPts.forEach(function(p){
    g.push('<rect class="pt" x="'+(sx(p.x)-5).toFixed(1)+'" y="'+(sy(p.y)-5).toFixed(1)+'" width="10" height="10"'
      +' transform="rotate(45 '+sx(p.x).toFixed(1)+' '+sy(p.y).toFixed(1)+')"'
      +' fill="none" stroke="#8250df" stroke-width="1.6"><title>'+esc(p.s.label)+'</title></rect>');
  });
  g.push('</svg>');
  host.innerHTML=g.join('');

  var legend=[];
  if(S.colour==='design') CHAPTER.groups.forEach(function(gr,n){
    legend.push('<span style="color:'+SERIES[n%SERIES.length]+'">■</span> '+esc(gr.gid));
  });
  else ['green','orange','red'].forEach(function(c){
    legend.push('<span style="color:'+CAT[c]+'">●</span> '+c);
  });
  if(refPts.length) legend.push('<span style="color:#8250df">◇</span> reference');
  if(S.showBest) legend.push('<span style="color:#0969da">◯</span> tool\'s pick');
  document.getElementById('plotlegend').innerHTML =
    legend.join(' &nbsp; ') + ' &nbsp; · &nbsp; ' + pts.length + ' points'
    + (S.pinOnly ? ' (pinned only)' : '') + ' · click one to pin it';
}

function buildPlotControls(){
  var opts = CHAPTER.metrics.map(function(m){return {k:m.key,l:m.label};})
    .concat(CHAPTER.axes.filter(function(a){return a.numeric;})
      .map(function(a){return {k:a.path,l:a.label+(a.unit?' ('+a.unit+')':'')};}));
  function sel(id,cur){
    return '<select id="'+id+'">'+opts.map(function(o){
      return '<option value="'+esc(o.k)+'"'+(o.k===cur?' selected':'')+'>'+esc(o.l)+'</option>';}).join('')+'</select>';
  }
  var pre = CHAPTER.presets.map(function(p,i){
    return '<option value="'+i+'">'+esc(p.name)+'</option>';}).join('');
  document.getElementById('plotctl').innerHTML =
     '<label>View<select id="p-pre"><option value="">custom</option>'+pre+'</select></label>'
    +'<label>X'+sel('p-x',S.x)+'</label>'
    +'<label>Y'+sel('p-y',S.y)+'</label>'
    +'<label>log X<input type="checkbox" id="p-lx"></label>'
    +'<label>log Y<input type="checkbox" id="p-ly"></label>'
    +'<label>colour<select id="p-c"><option value="verdict">verdict</option>'
    +'<option value="design">design</option></select></label>'
    +'<label title="hide everything except the runs you have pinned">'
    +'pinned only<input type="checkbox" id="p-po"></label>'
    +'<label title="ring the run that wins each decide axis, over the visible rows">'
    +'mark best<input type="checkbox" id="p-pb" checked></label>';
  document.getElementById('p-pre').addEventListener('change',function(e){
    if(e.target.value==='') return;
    usePreset(+e.target.value);
  });
  ['p-x','p-y'].forEach(function(id){
    document.getElementById(id).addEventListener('change',function(){
      S.x=document.getElementById('p-x').value;
      S.y=document.getElementById('p-y').value;
      document.getElementById('p-pre').value='';
      document.getElementById('plotnote').textContent='';
      paint();
    });
  });
  document.getElementById('p-lx').addEventListener('change',function(e){S.logx=e.target.checked;paint();});
  document.getElementById('p-ly').addEventListener('change',function(e){S.logy=e.target.checked;paint();});
  document.getElementById('p-c').addEventListener('change',function(e){S.colour=e.target.value;paint();});
  document.getElementById('p-po').addEventListener('change',function(e){S.pinOnly=e.target.checked;paint();});
  document.getElementById('p-pb').addEventListener('change',function(e){S.showBest=e.target.checked;paint();});
}
function usePreset(i){
  var p=CHAPTER.presets[i]; if(!p) return;
  S.x=p.x; S.y=p.y; S.logx=!!p.logx; S.logy=!!p.logy;
  document.getElementById('p-x').value=p.x;
  document.getElementById('p-y').value=p.y;
  document.getElementById('p-lx').checked=S.logx;
  document.getElementById('p-ly').checked=S.logy;
  document.getElementById('p-pre').value=String(i);
  document.getElementById('plotnote').textContent=p.note||'';
  paint();
}

// ── levers that the filter has made moot ───────────────────────────────────
// Pinning the fluid to o/w should silence "switch to w/o": it is no longer a
// lever, it is a different study.
function paintLevers(){
  document.querySelectorAll('tr[data-leveraxis]').forEach(function(tr){
    var path=tr.getAttribute('data-leveraxis');
    tr.style.display = (S.f[path] && S.f[path]!=='') ? 'none' : '';
  });
}

// ── the constant behind the Ca column ──────────────────────────────────────
// Ca = mu*v/gamma, so Ca is exactly proportional to 1/gamma — and gamma is not
// measured on Peak's fluids (it varies 3x across this repo's configs). A Ca
// limit control with no gamma on the page is a physics claim resting on an
// invisible constant.
//
// This recomputes over the VISIBLE rows on purpose. The diagnosis panel states
// gamma over every row; narrow to a subset that mixes fluid systems and that
// statement quietly stops applying. Here the note follows the filter, so a
// mixed subset says it is mixed rather than implying one gamma.
function paintGamma(rows){
  var el=document.getElementById('gammanote');
  if(!el) return;
  var seen=[], missing=0;
  rows.forEach(function(r){
    if(r.gamma===null||r.gamma===undefined){ missing++; return; }
    var g=Math.round(r.gamma*1e6)/1e3;          // N/m -> mN/m
    if(seen.indexOf(g)<0) seen.push(g);
  });
  seen.sort(function(a,b){return a-b;});
  var txt='', mixed=false;
  if(!rows.length){ txt=''; }
  else if(!seen.length){
    txt='exit Ca: γ not recorded on these rows — Ca cannot be re-checked';
    mixed=true;
  } else if(seen.length===1){
    txt='exit Ca computed at γ = '+seen[0]+' mN/m (unmeasured; Ca ∝ 1/γ)';
  } else {
    txt='exit Ca spans γ = '+seen.join(', ')+' mN/m — Ca ∝ 1/γ, so these rows '
       +'are not comparable on Ca. Filter to one fluid system.';
    mixed=true;
  }
  if(missing && seen.length){
    txt += ' · '+missing+' row'+(missing===1?'':'s')+' carry no γ';
    mixed=true;
  }
  el.textContent=txt;
  el.className='gnote'+(mixed?' mixed':'');
}

function paint(){
  var rows=shown();
  document.getElementById('railcount').textContent =
    rows.length+' of '+CHAPTER.rows.length+' rows';
  paintGamma(rows); paintGateNote(rows);
  paintPins(); paintPinTable(); paintDesigns(rows); paintTable(rows);
  paintLevers(); paintPlot(rows);
}

function initChapter(){
  S.__gid=''; S.__verdict='';
  var first = CHAPTER.presets.length ? CHAPTER.presets[0]
            : {x:CHAPTER.metrics[0].key, y:CHAPTER.metrics[1].key};
  S.x=first.x; S.y=first.y; S.logx=!!first.logx; S.logy=!!first.logy;
  buildRail(); buildPlotControls();
  showTab('explore');
  if(CHAPTER.presets.length) usePreset(0); else paint();
}
document.addEventListener('DOMContentLoaded', initChapter);
"""
