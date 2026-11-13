#!/usr/bin/env python3
"""Phase 3 - build the showcase dashboard from Phase 2 outputs only.

No QGIS needed: this runs in any Python 3 with folium installed.

    STEP 1  Read suitable_sites.geojson + site_selection_summary.json
    STEP 2  Build the Folium map (sites coloured, zones as overlays)
    STEP 3  Build the table rows and the filter funnel (text is HTML-escaped)
    STEP 4  Write one HTML page: map (iframe) + funnel + criteria + table + exports
            Map <-> table selection is linked with one small script.

Run:  python3 phase3_showcase.py   [--config my_town.json]
Output: phase3_dashboard.html

Low-bandwidth design: apart from the Leaflet files folium loads for the map,
the page needs NO internet - no jQuery, DataTables, web fonts or icon fonts.
Search, sorting, CSV/GeoJSON export and printing are plain JavaScript.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

from site_common import existing_fields, normalize_for_leaflet, geojson_property_names, load_config, make_base_map, project_path, require_folium

DEFAULT_STYLE = {"color": "#006837", "weight": 2, "fillColor": "#31a354", "fillOpacity": 0.75}
SELECTED_STYLE = {"color": "#fdff00", "weight": 6, "fillColor": "#ffd700", "fillOpacity": 0.9}


def esc(value) -> str:
    """HTML-escape any value. FIX: OSM names like 'Smith & Sons <Pty>' broke the table."""
    if value is None or value == "":
        return "—"
    return html.escape(str(value), quote=True)


def script_json(obj) -> str:
    """JSON that is safe inside <script>: a '</script>' in the data cannot end the tag."""
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


AGREEMENT = {  # label, colour
    "both": ("Both methods", "#1a9850"),
    "mce_only": ("MCE only", "#7b3294"),
    "boolean_only": ("Boolean only", "#f1a340"),
    None: ("—", "#999999"),
}


def load_mce(root: Path) -> dict | None:
    """Phase 2b outputs, or None when Phase 2b has not been run."""
    selected_path, summary_path = root / "suitable_sites_mce.geojson", root / "mce_summary.json"
    if not selected_path.is_file() or not summary_path.is_file():
        return None
    comparison_path = root / "mce_vs_boolean.geojson"
    selected = json.loads(selected_path.read_text(encoding="utf-8"))
    normalize_for_leaflet(selected)
    comparison = json.loads(comparison_path.read_text(encoding="utf-8")) if comparison_path.is_file() else None
    if comparison:
        normalize_for_leaflet(comparison)
    return {"selected": selected, "summary": json.loads(summary_path.read_text(encoding="utf-8")),
            "comparison": comparison}


def build_mce_html(mce: dict | None) -> tuple[str, str]:
    """(sidebar card, table section) for the MCE results; empty strings if absent."""
    if not mce:
        return "", ""
    s = mce["summary"]
    w = s.get("weights", {})
    info = s.get("weights_info", {})
    comp = s.get("comparison")
    sens = s.get("sensitivity", {})

    lines = [f"<li>Weights: " + ", ".join(f"{esc(k)} {v:.2f}" for k, v in w.items()) +
             (f" (AHP, CR {info['cr']:.3f})" if info.get("method") == "ahp" else " (direct)") + "</li>",
             f"<li>Selection: {esc(s.get('selection', {}).get('note'))}</li>"]
    if sens:
        lines.append(f"<li>Mean stability (weights ±{float(sens.get('weight_change', 0)):.0%}): "
                     f"{esc(sens.get('mean_stability'))}</li>")
    comp_html = ""
    if comp:
        comp_html = "".join(
            f'<div class="agree"><span style="background:{AGREEMENT[key][1]}"></span>{AGREEMENT[key][0]}'
            f'<b>{comp[key]}</b></div>' for key in ("both", "mce_only", "boolean_only"))
        comp_html += f'<div class="agree-note">Agreement (Jaccard): {comp["jaccard"]:.2f}</div>'
    card = (f'<div class="card"><h3>Boolean vs MCE</h3>{comp_html}'
            f'<ul style="margin-top:.6rem">{"".join(lines)}</ul></div>')

    rows = []
    feats = sorted(mce["selected"].get("features", []), key=lambda f: f["properties"].get("mce_rank") or 0)
    for f in feats:
        p = f["properties"]
        label = p.get("name") or p.get("source_id") or ""
        agree_label, color = AGREEMENT.get(p.get("agreement"), AGREEMENT[None])
        cells = [
            (p.get("mce_rank"), p.get("mce_rank")), (num(p.get("mce_score"), 3), num(p.get("mce_score"), 3)),
            (num(p.get("stability"), 2), num(p.get("stability"), 2)), (agree_label, None),
            (label, None), (num(p.get("area_sqm")), num(p.get("area_sqm"))),
            (num(p.get("score_school"), 2), num(p.get("score_school"), 2)),
            (num(p.get("score_highway"), 2), num(p.get("score_highway"), 2)),
            (num(p.get("score_river"), 2), num(p.get("score_river"), 2)),
            (p.get("reason"), None),
        ]
        tds = "".join(f'<td data-sort="{esc(srt) if srt is not None else esc(v)}">{esc(v)}</td>' for v, srt in cells)
        tds = tds.replace(f">{esc(agree_label)}<", f'><span class="dot" style="background:{color}"></span>{esc(agree_label)}<', 1)
        rows.append(
            f'<tr data-lat="{esc(p.get("lat"))}" data-lon="{esc(p.get("lon"))}" '
            f'data-label="MCE rank {esc(p.get("mce_rank"))} · {esc(label)}">{tds}</tr>'
        )
    section = f"""
<div class="table-section">
  <div class="card">
    <div class="table-tools">
      <h3 style="margin:0">MCE ranked sites (weighted linear combination)</h3>
      <input id="mce-filter" type="search" placeholder="Search…">
      <small id="mce-count"></small>
    </div>
    <div class="table-wrap">
      <table id="mce-table">
        <thead><tr>
          <th data-type="num">MCE rank</th><th data-type="num">Score</th><th data-type="num">Stability</th>
          <th>Agreement</th><th>Name / ID</th><th data-type="num">Area m²</th>
          <th data-type="num">School f.</th><th data-type="num">Highway f.</th><th data-type="num">River f.</th><th>Why</th>
        </tr></thead>
        <tbody>
{chr(10).join(rows) or '<tr><td colspan="10">No MCE sites.</td></tr>'}
        </tbody>
      </table>
    </div>
  </div>
</div>"""
    return card, section


def num(value, digits=1):
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 3 - showcase dashboard")
    parser.add_argument("--config", help="path to a config JSON (default: config.json)")
    args = parser.parse_args()
    cfg = load_config(args.config)
    folium, plugins = require_folium()

    root = Path(cfg["_config_dir"])
    zones_dir = project_path(cfg, "zones_dir")
    sites_path = root / "suitable_sites.geojson"
    summary_path = root / "site_selection_summary.json"

    # ------------------------------------------------------------------ STEP 1
    if not sites_path.is_file() or not summary_path.is_file():
        raise SystemExit(
            "Phase 2 outputs were not found. Run phase2_site_selection.py first "
            f"(expected {sites_path.name} and {summary_path.name} in {root})."
        )
    sites_gj = json.loads(sites_path.read_text(encoding="utf-8"))
    normalize_for_leaflet(sites_gj)  # one Leaflet shape per feature (see site_common)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    features = sites_gj.get("features", [])
    if features and "site_id" not in (features[0].get("properties") or {}):
        raise SystemExit("suitable_sites.geojson has no 'site_id' - it comes from the old Phase 2. Re-run Phase 2.")

    counts = summary["counts"]
    crit = summary["criteria"]
    total = int(counts["total_buildings"])

    # One plain record per site, sorted by rank (1 = best).
    # FIX: lat/lon, rank and scores now come from Phase 2 (PyQGIS pointOnSurface),
    # so the ~70 lines of hand-written centroid maths are gone.
    sites = []
    for feature in features:
        p = feature.get("properties") or {}
        sites.append({
            "id": int(p["site_id"]),
            "rank": int(p.get("rank") or p["site_id"]),
            "name": p.get("name") or "",
            "source_id": p.get("source_id") or "",
            "type": p.get("building") or "",
            "levels": p.get("levels_used"),
            "area": num(p.get("area_sqm")),
            "pop": num(p.get("pop_estimate")),
            "pop_levels": num(p.get("pop_estimate_levels")),
            "score": num(p.get("suit_score"), 3),
            "d_school": num(p.get("dist_school_m"), 0),
            "d_highway": num(p.get("dist_highway_m"), 0),
            "d_river": num(p.get("dist_river_m"), 0),
            "street": p.get("addr:street") or "",
            "lat": num(p.get("lat"), 6),
            "lon": num(p.get("lon"), 6),
        })
    sites.sort(key=lambda s: s["rank"])

    print("=" * 60)
    print("PHASE 3: Build Dashboard from Phase 2 Results")
    print(f"Analysis CRS: {summary.get('analysis_crs', 'not recorded')}   QGIS {summary.get('qgis_version', '?')}")
    print(f"Candidates: {len(sites)}")
    print("=" * 60)

    # ------------------------------------------------------------------ STEP 2
    print("[STEP 2] Building the map")
    if sites:
        center = [sum(s["lat"] for s in sites) / len(sites), sum(s["lon"] for s in sites) / len(sites)]
    else:
        c = summary.get("study_area_center", {})
        center = [float(c.get("latitude", -34.0267)), float(c.get("longitude", 20.4504))]
    m = make_base_map(cfg, center)

    overlays = [
        ("school_zone.geojson", f"School zone ({crit['school_distance_m']:g} m)", "#1f78b4"),
        ("highway_exclusion.geojson", f"Highway exclusion ({crit['highway_exclusion_m']:g} m)", "#e31a1c"),
        ("river_exclusion.geojson", f"River exclusion ({crit['river_exclusion_m']:g} m)", "#33a02c"),
        ("urban_area_polygons.geojson", "Mapped urban areas", "#6a3d9a"),
    ]
    for filename, label, color in overlays:
        path = zones_dir / filename
        if path.is_file():
            overlay = json.loads(path.read_text(encoding="utf-8"))
            normalize_for_leaflet(overlay)  # one Leaflet shape per feature (see site_common)
            folium.GeoJson(
                overlay,
                name=label,
                style_function=lambda f, c=color: {"color": c, "weight": 2, "fillColor": c, "fillOpacity": 0.15},
            ).add_to(m)

    sites_layer = None
    if features:
        props = geojson_property_names(sites_gj)
        tip_f, tip_a = existing_fields(
            ["rank", "source_id", "area_sqm", "pop_estimate", "suit_score"],
            ["Rank:", "Source ID:", "Footprint area (m²):", "Population proxy:", "Suitability (0-1):"],
            props,
        )
        pop_f, pop_a = existing_fields(
            ["rank", "source_id", "name", "area_sqm", "levels_used", "pop_estimate", "pop_estimate_levels",
             "dist_school_m", "dist_highway_m", "dist_river_m", "suit_score"],
            ["Rank:", "Source ID:", "Name:", "Area (m²):", "Levels used:", "Population proxy:",
             "Population (× levels):", "To school (m):", "To main highway (m):", "To river (m):", "Suitability:"],
            props,
        )
        # Sites are added LAST so they sit on top of the zones.
        # No highlight_function: folium's hover reset would wipe the "selected" style.
        sites_layer = folium.GeoJson(
            sites_gj,
            name="Suitable building candidates",
            style_function=lambda f: dict(DEFAULT_STYLE),
            tooltip=folium.GeoJsonTooltip(fields=tip_f, aliases=tip_a, localize=True) if tip_f else None,
            popup=folium.GeoJsonPopup(fields=pop_f, aliases=pop_a, localize=True) if pop_f else None,
            show=True,
        )
        sites_layer.add_to(m)

    # NEW: Phase 2b (MCE) results, shown next to the Boolean result when present.
    mce = load_mce(root)
    if mce:
        print("[STEP 2b] Adding the MCE results and the Boolean-vs-MCE comparison")
        if mce["comparison"] and mce["comparison"].get("features"):
            folium.GeoJson(
                mce["comparison"],
                name="Boolean vs MCE agreement",
                show=False,
                style_function=lambda f: {
                    "color": AGREEMENT[f["properties"].get("agreement")][1], "weight": 3,
                    "fillColor": AGREEMENT[f["properties"].get("agreement")][1], "fillOpacity": 0.55,
                },
                tooltip=folium.GeoJsonTooltip(fields=["agreement", "reason"], aliases=["Agreement:", "Why:"]),
            ).add_to(m)
        if mce["selected"].get("features"):
            # outline only, no fill: clicks inside still reach the Boolean sites below
            folium.GeoJson(
                mce["selected"],
                name="MCE selected sites (outline)",
                style_function=lambda f: {"color": "#7b3294", "weight": 3, "fill": False, "dashArray": "6 4"},
            ).add_to(m)

    plugins.Fullscreen().add_to(m)
    plugins.MousePosition().add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)

    # FIX: the map is placed in an <iframe srcdoc> that we build ourselves.
    # The browser treats srcdoc as the same origin as the page, so the page
    # script can reach the Leaflet objects directly by their folium names
    # (m.get_name(), sites_layer.get_name()) - no window-key scanning and no
    # renumbering by layer order. (_repr_html_ also added a Jupyter "Trust
    # Notebook" message and a fixed aspect ratio, which we do not want.)
    map_document = m.get_root().render()
    # FIX: make the map fill the whole frame. Without this, folium's page inside
    # the iframe can end up shorter than the frame, and the map (and its tiles)
    # only covers the upper part of the canvas.
    map_document = map_document.replace(
        "</head>",
        "<style>html,body{width:100%;height:100%;margin:0;padding:0;overflow:hidden}"
        ".folium-map{position:absolute!important;top:0;bottom:0;left:0;right:0;"
        "width:100%!important;height:100%!important}</style></head>",
        1,
    )
    map_name = m.get_name()
    sites_layer_name = sites_layer.get_name() if sites_layer is not None else ""

    # ------------------------------------------------------------------ STEP 3
    print("[STEP 3] Building the table and the funnel")
    row_html = []
    for s in sites:
        # data-sort holds the raw value so sorting works on numbers, not text
        cells = [
            (s["rank"], s["rank"]), (s["score"], s["score"]), (s["name"] or s["source_id"], None),
            (s["type"], None), (s["area"], s["area"]), (s["pop"], s["pop"]), (s["pop_levels"], s["pop_levels"]),
            (s["d_school"], s["d_school"]), (s["d_highway"], s["d_highway"]), (s["d_river"], s["d_river"]),
            (s["street"], None), (f"{s['lat']}, {s['lon']}", None),
        ]
        tds = "".join(
            f'<td data-sort="{esc(sort) if sort is not None else esc(val)}">{esc(val)}</td>' for val, sort in cells
        )
        row_html.append(f'<tr data-site-id="{s["id"]}">{tds}</tr>')
    table_rows = "\n".join(row_html) or '<tr><td colspan="12">No candidates passed all criteria.</td></tr>'

    # Funnel = CUMULATIVE counts: each row is "previous rows AND this rule".
    relation = crit.get("urban_relation", "intersects")
    funnel = [
        ("All buildings", total),
        (f"A · area {crit['min_area_sqm']:g}–{crit['max_area_sqm']:g} m²", counts["step_a_area"]),
        (f"B · + within {crit['school_distance_m']:g} m of a school", counts["step_b_school"]),
        (f"C · + outside {crit['highway_exclusion_m']:g} m highway zone", counts["step_c_highway"]),
        (f"D · + outside {crit['river_exclusion_m']:g} m river zone", counts["step_d_river"]),
        (f"E · + urban area ({relation})", counts["final"]),
    ]
    colors = ["#0f3460", "#1f78b4", "#e31a1c", "#33a02c", "#6a3d9a", "#31a354"]
    funnel_html = []
    for (label, n), color in zip(funnel, colors):
        pct = (n / total * 100) if total else 0
        width = max(pct, 2)
        funnel_html.append(
            f'<div class="funnel-step"><div class="funnel-label">{esc(label)}</div>'
            f'<div class="funnel-bar-wrap"><div class="funnel-bar" style="width:{width:.1f}%;background:{color}">'
            f'<span>{n:,}</span></div></div><div class="funnel-pct">{pct:.1f}%</div></div>'
        )

    w = summary.get("scoring", {})
    criteria_items = [
        f"Footprint area {crit['min_area_sqm']:g}–{crit['max_area_sqm']:g} m² (planar, {summary.get('analysis_crs')})",
        f"Within {crit['school_distance_m']:g} m of a school",
        f"Outside {crit['highway_exclusion_m']:g} m of: {', '.join(crit.get('main_highway_classes', []))}",
        f"Outside {crit['river_exclusion_m']:g} m of rivers",
        f"Urban area relation: {relation} "
        f"(intersects {counts['step_e_urban_intersects']} / within {counts['step_e_urban_within']})",
    ]
    if w:
        criteria_items.append(
            "Ranking weights: school {s}, highway {h}, river {r}".format(
                s=w.get("school", {}).get("weight"), h=w.get("highway", {}).get("weight"), r=w.get("river", {}).get("weight")
            )
        )
    criteria_html = "".join(f"<li>{esc(item)}</li>" for item in criteria_items)
    notes_html = "".join(f"<li>{esc(n)}</li>" for n in summary.get("interpretation_notes", []))

    # ------------------------------------------------------------------ STEP 4
    mce_card, mce_section = build_mce_html(mce)
    n_mce = len(mce["selected"].get("features", [])) if mce else None
    badge_mce = f" · {n_mce} by MCE" if n_mce is not None else ""

    print("[STEP 4] Writing the dashboard HTML")
    page = PAGE_TEMPLATE.format(
        mce_card=mce_card,
        mce_section=mce_section,
        badge_mce=badge_mce,
        n_final=f"{counts['final']:,}",
        total=f"{total:,}",
        a=f"{counts['step_a_area']:,}",
        b=f"{counts['step_b_school']:,}",
        c=f"{counts['step_c_highway']:,}",
        d=f"{counts['step_d_river']:,}",
        pop=f"{summary.get('population_proxy_total', 0):,.0f}",
        crs=esc(summary.get("analysis_crs", "?")),
        qgis=esc(summary.get("qgis_version", "?")),
        generated=esc(summary.get("generated_utc", "")),
        funnel="".join(funnel_html),
        criteria=criteria_html,
        notes=notes_html,
        rows=table_rows,
        srcdoc=html.escape(map_document, quote=True),
        sites_json=script_json(sites),
        geojson_json=script_json(sites_gj),
        map_name=script_json(map_name),
        layer_name=script_json(sites_layer_name),
        default_style=script_json(DEFAULT_STYLE),
        selected_style=script_json(SELECTED_STYLE),
    )
    output_html = root / "phase3_dashboard.html"
    output_html.write_text(page, encoding="utf-8")  # FIX: explicit UTF-8 (Windows default is cp1252)

    print(f"\n{'=' * 60}\n  PHASE 3 COMPLETE — Dashboard Ready!\n{'=' * 60}")
    print(f"  Suitable sites:          {counts['final']}")
    print(f"  Population proxy total:  {summary.get('population_proxy_total', 0):.0f}")
    print(f"  Dashboard:               {output_html}")
    print("  Use the Print button → 'Save as PDF' for a PDF report.")
    return 0


# ---------------------------------------------------------------------------
# HTML template. Doubled braces {{ }} are literal braces for CSS/JS;
# single braces {name} are filled in by .format() above.
# ---------------------------------------------------------------------------
PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Site Selection Analysis Dashboard</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; color: #1a1a2e; }}
.header {{ background: linear-gradient(135deg, #1a1a2e, #0f3460); color: #fff; padding: 1.6rem 2.5rem;
  display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; }}
.header h1 {{ font-size: 1.6rem; font-weight: 800; }}
.header p {{ font-size: .88rem; color: rgba(255,255,255,.75); margin-top: 4px; }}
.badge {{ background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.2); padding: .45rem 1.1rem; border-radius: 50px; font-size: .82rem; }}
.stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem; padding: 1.4rem 2.5rem; background: #fff; border-bottom: 1px solid #e8e8e8; }}
.stat {{ padding: .9rem 1.1rem; border-radius: 12px; background: #f8f9fc; border-left: 4px solid #0f3460; }}
.stat:nth-child(2) {{ border-left-color: #1f78b4; }} .stat:nth-child(3) {{ border-left-color: #e31a1c; }}
.stat:nth-child(4) {{ border-left-color: #33a02c; }} .stat:nth-child(5) {{ border-left-color: #6a3d9a; }}
.stat:nth-child(6) {{ border-left-color: #31a354; }}
.stat .v {{ font-size: 1.6rem; font-weight: 800; }} .stat .l {{ font-size: .72rem; color: #666; text-transform: uppercase; letter-spacing: .4px; margin-top: 2px; }}
.disclaimer {{ margin: 1rem 2.5rem 0; padding: .75rem 1rem; background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; color: #555; font-size: .82rem; line-height: 1.5; }}
.main {{ display: grid; grid-template-columns: 1fr 380px; gap: 1.5rem; padding: 1.5rem 2.5rem; max-width: 1600px; margin: 0 auto; }}
@media (max-width: 1100px) {{ .main {{ grid-template-columns: 1fr; }} }}
.card {{ background: #fff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,.06); padding: 1.3rem; }}
.card h3 {{ font-size: .85rem; font-weight: 700; margin-bottom: .9rem; text-transform: uppercase; letter-spacing: .5px; color: #555; }}
/* FIX: the map card stretches to the height of the sidebar (grid row);
   the map frame now grows with it instead of staying 520 px tall. */
.map-card {{ padding: 0; overflow: hidden; display: flex; flex-direction: column; }}
.map-card .map-head {{ padding: .9rem 1.3rem; border-bottom: 1px solid #eee; font-weight: 600; display: flex; justify-content: space-between; }}
.map-card .map-head small {{ font-weight: 400; color: #888; }}
#site-map {{ width: 100%; flex: 1 1 auto; min-height: 520px; height: auto; border: 0; display: block; }}
.side {{ display: flex; flex-direction: column; gap: 1.5rem; }}
/* each funnel step: label on top, bar + percentage below */
.funnel-step {{ display: grid; grid-template-columns: 1fr 48px; grid-template-areas: "label label" "bar pct"; gap: 3px; margin-bottom: 10px; }}
.funnel-label {{ grid-area: label; font-size: .78rem; color: #444; }}
.funnel-bar-wrap {{ grid-area: bar; }} .funnel-pct {{ grid-area: pct; }}
.funnel-bar-wrap {{ height: 24px; background: #f0f2f5; border-radius: 6px; overflow: hidden; }}
.funnel-bar {{ height: 100%; border-radius: 6px; display: flex; align-items: center; justify-content: flex-end; padding-right: 6px; min-width: 28px; }}
.funnel-bar span {{ font-size: .7rem; font-weight: 700; color: #fff; text-shadow: 0 1px 2px rgba(0,0,0,.3); }}
.funnel-pct {{ text-align: right; font-size: .74rem; font-weight: 600; color: #888; align-self: center; }}
.card ul {{ padding-left: 1.1rem; font-size: .8rem; line-height: 1.55; color: #444; }}
.buttons {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }}
.btn {{ padding: .65rem .8rem; border: 0; border-radius: 8px; font-size: .8rem; font-weight: 600; cursor: pointer; color: #fff; }}
.btn.csv {{ background: #1f78b4; }} .btn.geojson {{ background: #33a02c; }} .btn.print {{ background: #6a3d9a; }}
.table-section {{ padding: 0 2.5rem 2rem; max-width: 1600px; margin: 0 auto; }}
.table-tools {{ display: flex; justify-content: space-between; align-items: center; gap: 1rem; margin-bottom: .8rem; flex-wrap: wrap; }}
.table-tools input {{ border: 1px solid #ccc; border-radius: 6px; padding: 6px 10px; font-size: .85rem; min-width: 240px; }}
.table-tools small {{ color: #888; }}
.table-wrap {{ max-height: 480px; overflow: auto; border: 1px solid #eee; border-radius: 8px; }}
table {{ width: 100%; border-collapse: collapse; font-size: .8rem; }}
thead th {{ position: sticky; top: 0; background: #f8f9fc; font-size: .72rem; text-transform: uppercase; letter-spacing: .3px; color: #555;
  padding: 9px 8px; border-bottom: 2px solid #e0e0e0; text-align: left; cursor: pointer; white-space: nowrap; }}
thead th.asc::after {{ content: " ▲"; }} thead th.desc::after {{ content: " ▼"; }}
tbody td {{ padding: 7px 8px; border-bottom: 1px solid #f0f0f0; }}
tbody tr {{ cursor: pointer; }} tbody tr:hover {{ background: #f0f7ff; }}
tbody tr.selected {{ background: #fff3cd !important; outline: 2px solid #ffc107; }}
.agree {{ display: flex; align-items: center; gap: 8px; font-size: .82rem; margin-bottom: 6px; }}
.agree span {{ width: 12px; height: 12px; border-radius: 3px; display: inline-block; }}
.agree b {{ margin-left: auto; font-size: 1rem; }}
.agree-note {{ font-size: .75rem; color: #888; margin-top: 4px; }}
.dot {{ width: 9px; height: 9px; border-radius: 50%; display: inline-block; margin-right: 6px; }}
.footer {{ text-align: center; padding: 1.4rem; font-size: .74rem; color: #888; border-top: 1px solid #eee; }}
.footer a {{ color: #888; }}
@media print {{
  body {{ background: #fff; }} .header, .stat, .funnel-bar {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  .buttons, .table-tools input {{ display: none; }} .table-wrap {{ max-height: none; overflow: visible; }}
  .side {{ break-inside: avoid; }}
}}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>Site Selection Analysis</h1>
    <p>Automated spatial screening and ranking · QGIS {qgis} · PyQGIS · CRS {crs}</p>
  </div>
  <div class="badge">✔ {n_final} candidate footprints (Boolean){badge_mce}</div>
</div>

<div class="stats">
  <div class="stat"><div class="v">{total}</div><div class="l">Total buildings</div></div>
  <div class="stat"><div class="v">{a}</div><div class="l">A · Size OK</div></div>
  <div class="stat"><div class="v">{b}</div><div class="l">B · + Near school</div></div>
  <div class="stat"><div class="v">{c}</div><div class="l">C · + Not near highway</div></div>
  <div class="stat"><div class="v">{d}</div><div class="l">D · + Not near river</div></div>
  <div class="stat"><div class="v" style="color:#31a354">{n_final}</div><div class="l">E · Final (urban)</div></div>
</div>

<div class="disclaimer">
  Results are mapped building-footprint candidates, not verified vacant parcels. The urban/erf layer is not a
  zoning map. Population ({pop}) is an indicative area-based proxy, not census data. The suitability score only
  ranks candidates that already passed every screening rule.
</div>

<div class="main">
  <div class="card map-card">
    <div class="map-head">Spatial analysis map <small>Click a site or a table row · toggle layers top-right</small></div>
    <iframe id="site-map" title="Site selection map" srcdoc="{srcdoc}"></iframe>
  </div>
  <div class="side">
    <div class="card"><h3>Filter cascade (cumulative)</h3>{funnel}</div>
    <div class="card"><h3>Criteria (Boolean)</h3><ul>{criteria}</ul></div>
    {mce_card}
    <div class="card">
      <h3>Export</h3>
      <div class="buttons">
        <button class="btn csv" onclick="exportCSV()">CSV</button>
        <button class="btn geojson" onclick="exportGeoJSON()">GeoJSON</button>
        <button class="btn print" onclick="window.print()">Print / PDF</button>
      </div>
    </div>
  </div>
</div>

<div class="table-section">
  <div class="card">
    <div class="table-tools">
      <h3 style="margin:0">Suitable sites register (ranked)</h3>
      <input id="table-filter" type="search" placeholder="Search name, street, type…">
      <small id="table-count"></small>
    </div>
    <div class="table-wrap">
      <table id="sites-table">
        <thead><tr>
          <th data-type="num">Rank</th><th data-type="num">Score</th><th>Name / ID</th><th>Type</th>
          <th data-type="num">Area m²</th><th data-type="num">Pop.</th><th data-type="num">Pop. × levels</th>
          <th data-type="num">To school m</th><th data-type="num">To highway m</th><th data-type="num">To river m</th>
          <th>Street</th><th>Lat, Lon</th>
        </tr></thead>
        <tbody>
{rows}
        </tbody>
      </table>
    </div>
  </div>
</div>

{mce_section}

<div class="card" style="margin:0 2.5rem 1.5rem"><h3>Interpretation notes</h3><ul>{notes}</ul></div>

<div class="footer">
  Generated {generated} from Phase 2 PyQGIS results · Folium/Leaflet<br>
  Dataset: <a href="https://docs.qgis.org/latest/en/docs/training_manual/" target="_blank" rel="noopener">QGIS Training Manual</a>
  exercise data · &copy; <a href="https://openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a> (ODbL)
</div>

<script>
// ---------------------------------------------------------------- data from Python
var SITES = {sites_json};
var SITES_GEOJSON = {geojson_json};
var MAP_NAME = {map_name};          // folium variable name of the L.Map inside the iframe
var LAYER_NAME = {layer_name};      // folium variable name of the sites L.GeoJSON layer
var DEFAULT_STYLE = {default_style};
var SELECTED_STYLE = {selected_style};

var siteById = {{}};
SITES.forEach(function (s) {{ siteById[s.id] = s; }});
var siteLayers = {{}};   // site id -> Leaflet polygon
var leafletMap = null, leafletL = null, selectedId = null;

function escapeHtml(v) {{
  return String(v === null || v === undefined ? '' : v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}}

// ---------------------------------------------------------------- map <-> table link
// FIX: ONE mechanism. We look up the map and the sites layer by name, register
// our own click handler NEXT TO folium's (popups keep working), and use the
// site_id stored on each feature - never the drawing order.
function connectMap(attempt) {{
  attempt = attempt || 0;
  var frame = document.getElementById('site-map');
  var win;
  try {{ win = frame.contentWindow; void win.document; }}
  catch (e) {{ console.warn('Map frame not reachable; table-map linking disabled.', e); return; }}
  if (!win || !win[MAP_NAME] || (LAYER_NAME && !win[LAYER_NAME])) {{
    if (attempt < 50) setTimeout(function () {{ connectMap(attempt + 1); }}, 200);
    return;
  }}
  leafletMap = win[MAP_NAME];
  leafletL = win.L;
  // FIX: Leaflet measured its container before the dashboard finished its
  // layout, so tiles covered only part of the canvas. Re-measure now, after a
  // short delay, and whenever the window size changes.
  fitMapToFrame();
  setTimeout(fitMapToFrame, 300);
  if (!LAYER_NAME) return;
  win[LAYER_NAME].eachLayer(function (layer) {{
    var p = layer.feature && layer.feature.properties;
    if (!p || p.site_id === undefined || p.site_id === null) return;
    var id = Number(p.site_id);
    siteLayers[id] = layer;
    layer.on('click', function () {{ selectSite(id, 'map'); }});
  }});
}}

function fitMapToFrame() {{
  if (leafletMap) leafletMap.invalidateSize({{ pan: false }});
}}
window.addEventListener('resize', fitMapToFrame);

function selectSite(id, source) {{
  if (selectedId !== null && siteLayers[selectedId]) siteLayers[selectedId].setStyle(DEFAULT_STYLE);
  Array.prototype.forEach.call(document.querySelectorAll('#sites-table tbody tr.selected'),
    function (r) {{ r.classList.remove('selected'); }});
  selectedId = id;

  var row = document.querySelector('#sites-table tbody tr[data-site-id="' + id + '"]');
  if (row) {{
    row.classList.add('selected');
    if (source === 'map') row.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
  }}
  var layer = siteLayers[id];
  if (!layer) return;
  layer.setStyle(SELECTED_STYLE);
  layer.bringToFront();
  if (source === 'table' && leafletMap) {{
    leafletMap.fitBounds(layer.getBounds(), {{ maxZoom: 18, padding: [40, 40] }});
    var s = siteById[id];
    if (s && leafletL) {{
      leafletL.popup()
        .setLatLng([s.lat, s.lon])
        .setContent('<b>Rank ' + s.rank + '</b> · score ' + s.score + '<br>' +
                    escapeHtml(s.name || s.source_id) + '<br>' + s.area + ' m² · pop. ' + s.pop)
        .openOn(leafletMap);
    }}
  }}
}}

document.getElementById('site-map').addEventListener('load', function () {{ connectMap(0); }});
connectMap(0);

document.querySelector('#sites-table tbody').addEventListener('click', function (e) {{
  var tr = e.target.closest('tr[data-site-id]');
  if (tr) selectSite(Number(tr.getAttribute('data-site-id')), 'table');
}});

// MCE table: a row click zooms to the site and opens a small popup
var mceBody = document.querySelector('#mce-table tbody');
if (mceBody) {{
  mceBody.addEventListener('click', function (e) {{
    var tr = e.target.closest('tr[data-lat]');
    if (!tr) return;
    Array.prototype.forEach.call(mceBody.querySelectorAll('tr.selected'), function (r) {{ r.classList.remove('selected'); }});
    tr.classList.add('selected');
    var lat = parseFloat(tr.getAttribute('data-lat')), lon = parseFloat(tr.getAttribute('data-lon'));
    if (leafletMap && leafletL && !isNaN(lat) && !isNaN(lon)) {{
      leafletMap.setView([lat, lon], 18);
      leafletL.popup().setLatLng([lat, lon]).setContent(escapeHtml(tr.getAttribute('data-label'))).openOn(leafletMap);
    }}
  }});
}}

// ---------------------------------------------------------------- search + sort (no jQuery)
// One function, used for both tables (Boolean and MCE).
function setupTable(tableId, filterId, countId) {{
  var table = document.getElementById(tableId);
  if (!table) return;
  var tbody = table.querySelector('tbody');
  function dataRows() {{ return Array.prototype.slice.call(tbody.querySelectorAll('tr')).filter(function (r) {{ return r.children.length > 1; }}); }}
  function visibleCount() {{
    var rows = dataRows(), n = rows.filter(function (r) {{ return r.style.display !== 'none'; }}).length;
    document.getElementById(countId).textContent = n + ' of ' + rows.length + ' sites shown';
  }}
  document.getElementById(filterId).addEventListener('input', function () {{
    var q = this.value.toLowerCase();
    dataRows().forEach(function (r) {{ r.style.display = r.textContent.toLowerCase().indexOf(q) >= 0 ? '' : 'none'; }});
    visibleCount();
  }});
  Array.prototype.forEach.call(table.querySelectorAll('thead th'), function (th, col) {{
    th.addEventListener('click', function () {{
      var asc = !th.classList.contains('asc');
      Array.prototype.forEach.call(th.parentNode.children, function (h) {{ h.classList.remove('asc', 'desc'); }});
      th.classList.add(asc ? 'asc' : 'desc');
      var numeric = th.getAttribute('data-type') === 'num';
      var rows = dataRows();
      rows.sort(function (a, b) {{
        var x = a.children[col].getAttribute('data-sort'), y = b.children[col].getAttribute('data-sort');
        if (numeric) {{
          x = parseFloat(x); y = parseFloat(y);
          if (isNaN(x)) x = -Infinity; if (isNaN(y)) y = -Infinity;
          return asc ? x - y : y - x;
        }}
        return asc ? x.localeCompare(y) : y.localeCompare(x);
      }});
      rows.forEach(function (r) {{ tbody.appendChild(r); }});
    }});
  }});
  visibleCount();
}}
setupTable('sites-table', 'table-filter', 'table-count');
setupTable('mce-table', 'mce-filter', 'mce-count');

// ---------------------------------------------------------------- exports
function download(text, filename, type) {{
  var blob = new Blob([text], {{ type: type }});
  var link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.appendChild(link); link.click(); link.remove();
}}
// FIX: every CSV field is quoted/escaped (not only the name); the BOM makes Excel read UTF-8 (m², accents).
function csvCell(v) {{
  v = (v === null || v === undefined) ? '' : String(v);
  return /[",\\r\\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
}}
function exportCSV() {{
  var cols = ['rank', 'id', 'score', 'name', 'source_id', 'type', 'levels', 'area', 'pop', 'pop_levels',
              'd_school', 'd_highway', 'd_river', 'street', 'lat', 'lon'];
  var lines = [cols.join(',')];
  SITES.forEach(function (s) {{ lines.push(cols.map(function (c) {{ return csvCell(s[c]); }}).join(',')); }});
  download('\\ufeff' + lines.join('\\r\\n'), 'suitable_sites.csv', 'text/csv;charset=utf-8');
}}
function exportGeoJSON() {{
  download(JSON.stringify(SITES_GEOJSON, null, 2), 'suitable_sites.geojson', 'application/geo+json;charset=utf-8');
}}
</script>
</body>
</html>
"""


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as error:
        print(f"\n[FATAL] Phase 3 failed: {error}", file=sys.stderr)
        sys.exit(1)
