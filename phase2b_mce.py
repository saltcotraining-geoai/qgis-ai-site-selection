#!/usr/bin/env python3
"""Phase 2b - Multi-Criteria Evaluation (MCE) site selection with PyQGIS.

Same data and the same first steps as Phase 2 (load, reproject, fix
geometries, save metric copies); then a different decision method:

    PHASE 2 (Boolean screening)           PHASE 2b (MCE - weighted linear combination)
    every rule is a yes/no veto           only true limits are yes/no CONSTRAINTS;
                                          preferences become 0-1 FACTORS that are
                                          WEIGHTED and can compensate each other

    STEP 1   Load the input GeoPackages                        (same as Phase 2)
    STEP 2   Choose the metric analysis CRS                    (same as Phase 2)
    STEP 3   Reproject + fix geometries, save metric copies    (same as Phase 2)
    STEP C1  Constraint: footprint area range                  (Field Calculator, Extract by Expression)
    STEP C2  Constraint: in a mapped urban area                (Extract by Location)
    STEP C3  Constraint: river setback (flood safety)          (Buffer, Extract by Location: disjoint)
    STEP C4  Constraint: highway setback (noise/safety)        (Buffer, Extract by Location: disjoint)
    STEP C5  OPTIONAL constraint: water-body setback           (water.gpkg; off unless enabled in config)
    STEP W   Weights: AHP pairwise comparison + consistency ratio, or direct weights
    STEP S   Standardise factors 0-1 and combine: score = sum(weight x factor)
             (+ OPTIONAL restaurant-proximity factor from restaurants.gpkg; off unless enabled)
    STEP R   Rank and select (top N / match the Boolean count / score threshold)
    STEP T   Sensitivity: change each weight +/-20 % - which sites stay selected?
    STEP V   Compare with the Boolean result: both / mce_only / boolean_only
    STEP G   Export + summary + quick-look map

Run Phase 2 first if you want the Boolean comparison (STEP V):
    python3 phase2_site_selection.py
    python3 phase2b_mce.py              [--config my_town.json]

Outputs
    analysis_data/mce/steps/*.gpkg      candidates after every constraint
    analysis_data/mce/*.gpkg            scored + selected layers (metric CRS)
    mce_scored_buildings.geojson        every building that passed the constraints, with its score
    suitable_sites_mce.geojson          the selected MCE sites (WGS 84)
    mce_vs_boolean.geojson              Boolean + MCE sites labelled both / mce_only / boolean_only
    mce_summary.json                    weights, consistency ratio, counts, sensitivity, comparison
    phase2b_mce.html                    quick-look map
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from site_common import analysis_simplify_m, existing_fields, load_config, normalize_for_leaflet, make_base_map, project_path, require_folium
from mce_core import FACTORS, active_factors, compare_with_boolean, resolve_weights, sensitivity
from qgis_common import (
    wgs84,
    ConsoleFeedback,
    init_qgis,
    load_vector,
    make_field,
    output_layer,
    qgis_version,
    run_alg,
    save_vector,
    set_geojson_precision,
    shutdown_qgis,
)
# The SAME building blocks as Phase 2 - one implementation, two methods.
from phase2_site_selection import (
    PRED_DISJOINT,
    PRED_INTERSECT,
    PRED_WITHIN,
    choose_analysis_crs,
    count,
    dissolved_buffer,
    enrich_candidates,
    extract_by_expression,
    extract_by_location,
    linear_score,
    main_highways_layer,
    pick_id_field,
    prepare_layer,
    river_layer,
    union_geometry,
)


def rename_fields(layer, mapping: dict) -> None:
    """Rename attribute fields in place, e.g. suit_score -> mce_score (clearer in QGIS)."""
    pr = layer.dataProvider()
    renames = {layer.fields().indexOf(old): new for old, new in mapping.items() if layer.fields().indexOf(old) >= 0}
    if renames and not pr.renameAttributes(renames):
        raise RuntimeError(f"Could not rename fields {mapping}")
    layer.updateFields()


def add_optional_factor(layer, name: str, ref, zero_at: float, one_at: float, weights: dict, cfg: dict) -> None:
    """Score one extra factor, then recompute suit_score and rank with ALL active weights (in place).

    enrich_candidates() (shared with Phase 2) scores only school / highway / river.
    This adds dist_<name>_m and score_<name>, and rebuilds the weighted sum from
    the stored 0-1 factor scores so that the ranking includes the new factor.
    Manual QGIS equivalent: Field Calculator with
        distance / linear membership for the new layer, then the weighted sum.
    """
    pr = layer.dataProvider()
    new = [(f"dist_{name}_m", "double"), (f"score_{name}", "double")]
    pr.addAttributes([make_field(n, t) for n, t in new if n not in layer.fields().names()])
    layer.updateFields()
    idx = {n: layer.fields().indexOf(n) for n in ("suit_score", "rank", "site_id", *(n for n, _ in new))}
    id_field = pick_id_field(layer, cfg["fields"]["id_candidates"])

    rows = []
    for feat in layer.getFeatures():
        d = None
        if ref is not None:
            d = feat.geometry().distance(ref)
            d = round(d, 1) if d >= 0 else None
        s = round(linear_score(d, zero_at, one_at), 3)
        scores = {f: float(feat[f"score_{f}"] or 0) for f in weights if f != name}
        scores[name] = s
        total = round(sum(weights[f] * scores[f] for f in weights), 3)
        rows.append({"fid": feat.id(), "dist": d, "score": s, "total": total,
                     "area": float(feat["area_sqm"] or 0),
                     "sid": str(feat[id_field]) if id_field else str(feat.id())})

    # Same ranking rule as Phase 2: score, then larger footprint, then source_id.
    rows.sort(key=lambda r: (-r["total"], -r["area"], r["sid"]))
    changes = {}
    for rank, r in enumerate(rows, start=1):
        changes[r["fid"]] = {idx[f"dist_{name}_m"]: r["dist"], idx[f"score_{name}"]: r["score"],
                             idx["suit_score"]: r["total"], idx["rank"]: rank, idx["site_id"]: rank}
    if changes and not pr.changeAttributeValues(changes):
        raise RuntimeError(f"Could not write the {name} factor values.")


def boolean_result_count(root: Path) -> int | None:
    """Number of sites the Boolean Phase 2 selected (for a like-for-like comparison)."""
    path = root / "site_selection_summary.json"
    if not path.is_file():
        return None
    counts = json.loads(path.read_text(encoding="utf-8")).get("counts", {})
    return counts.get("final")


# ===========================================================================
# The GIS part (needs QGIS). Returns plain data only, so QGIS can shut down.
# ===========================================================================
def run_mce(cfg: dict) -> dict:
    feedback = ConsoleFeedback(verbose=bool(cfg["analysis"].get("verbose_processing")))
    set_geojson_precision(cfg)
    mce = cfg["mce"]
    cons = mce["constraints"]
    segments = int(cfg["analysis"].get("buffer_segments", 36))

    root = Path(cfg["_config_dir"])
    dataset_dir = project_path(cfg, "dataset_dir")
    analysis_dir = project_path(cfg, "analysis_dir")
    utm_dir = analysis_dir / "utm"
    mce_dir = analysis_dir / "mce"
    steps_dir = mce_dir / "steps"
    for folder in (utm_dir, steps_dir):
        folder.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------- STEPS 1-3 (as Phase 2)
    print("\n[STEP 1] Load source data (same inputs as Phase 2)")
    names = cfg["layers"]
    src = {key: load_vector(dataset_dir, names[key]) for key in ("buildings", "schools", "roads", "rivers", "urban")}
    for key, layer in src.items():
        print(f"  {key:10s} {count(layer):6d} features  {layer.crs().authid()}")

    analysis_crs, crs_note, center_lon, center_lat = choose_analysis_crs(cfg, src["buildings"])
    print(f"\n[STEP 2] Analysis CRS: {crs_note}")

    print("\n[STEP 3] Reproject to metres and fix geometries (identical to Phase 2)")
    # Same simplification settings as Phase 2, so both methods use identical reference layers.
    utm = {key: prepare_layer(layer, key, analysis_crs, utm_dir, feedback, analysis_simplify_m(cfg, key))
           for key, layer in src.items()}
    total_buildings = count(utm["buildings"])

    # Optional layers: loaded only when the constraint/factor that uses them is switched on,
    # so the default run reads exactly the same five inputs as Phase 2.
    factor_names = active_factors(mce)
    optional = {
        "water": bool((cons.get("water_setback") or {}).get("enabled", False)),
        "restaurants": "restaurant" in factor_names,
    }
    for key, wanted in optional.items():
        if not wanted:
            continue
        layer = load_vector(dataset_dir, names.get(key, key), required=False)
        if layer is None or count(layer) == 0:
            print(f"  [WARN] optional layer '{key}' is switched on in config but missing/empty - it will be skipped")
            utm[key] = None
            continue
        print(f"  {key:10s} {count(layer):6d} features  {layer.crs().authid()}  (optional)")
        utm[key] = prepare_layer(layer, key, analysis_crs, utm_dir, feedback, analysis_simplify_m(cfg, key))

    # Reference layers used by both constraints and factors
    # Attribute filters first (same as Phase 2): only the road / river classes the rules are about.
    main_highways = main_highways_layer(utm["roads"], cfg, feedback)
    rivers = river_layer(utm["rivers"], cfg, feedback)
    if count(utm["schools"]) == 0:
        raise RuntimeError("The schools layer is empty - the school factor cannot be scored.")

    # Area is always calculated (it is also used for ranking ties and population)
    with_area = output_layer(
        run_alg(
            "native:fieldcalculator",
            {"INPUT": utm["buildings"], "FIELD_NAME": "area_sqm", "FIELD_TYPE": 0, "FIELD_LENGTH": 20,
             "FIELD_PRECISION": 3, "FORMULA": "area($geometry)", "OUTPUT": "TEMPORARY_OUTPUT"},
            "Calculate planar footprint area (m2)",
            feedback,
        ),
        "OUTPUT",
        "buildings_with_area",
    )

    step_counts = {"total_buildings": total_buildings}

    # ------------------------------------------------- CONSTRAINTS (0/1 masks)
    print("\n[STEP C1-C5] Constraints - hard 0/1 rules (is the building allowed at all?)")
    current = with_area

    c = cons["area"]
    if c.get("enabled", True):
        current = extract_by_expression(
            current, f'"area_sqm" >= {float(c["min_sqm"])} AND "area_sqm" <= {float(c["max_sqm"])}',
            "mce_c1_area", feedback,
        )
        print(f"    C1 area {c['min_sqm']:g}–{c['max_sqm']:g} m²: {count(current):,} remain")
    step_counts["c1_area"] = count(current)
    save_vector(current, steps_dir / "mce_c1_area.gpkg", "GPKG")

    c = cons["urban"]
    if c.get("enabled", True):
        relation = str(c.get("relation", "intersects")).lower()
        if relation not in ("intersects", "within"):
            raise ValueError("mce.constraints.urban.relation must be 'intersects' or 'within'.")
        predicate = PRED_WITHIN if relation == "within" else PRED_INTERSECT
        current = extract_by_location(current, utm["urban"], predicate, "mce_c2_urban", feedback)
        print(f"    C2 urban ({relation}): {count(current):,} remain")
    step_counts["c2_urban"] = count(current)
    save_vector(current, steps_dir / "mce_c2_urban.gpkg", "GPKG")

    c = cons["river_setback"]
    if c.get("enabled", True) and count(rivers) > 0:
        buf = dissolved_buffer(rivers, float(c["distance_m"]), "mce_river_setback", segments, feedback)
        current = extract_by_location(current, buf, PRED_DISJOINT, "mce_c3_river", feedback)
        print(f"    C3 river setback {c['distance_m']:g} m: {count(current):,} remain")
    step_counts["c3_river"] = count(current)
    save_vector(current, steps_dir / "mce_c3_river.gpkg", "GPKG")

    c = cons["highway_setback"]
    if c.get("enabled", True) and count(main_highways) > 0:
        buf = dissolved_buffer(main_highways, float(c["distance_m"]), "mce_highway_setback", segments, feedback)
        current = extract_by_location(current, buf, PRED_DISJOINT, "mce_c4_highway", feedback)
        print(f"    C4 highway setback {c['distance_m']:g} m: {count(current):,} remain")
    step_counts["c4_highway"] = count(current)
    save_vector(current, steps_dir / "mce_c4_highway.gpkg", "GPKG")

    c = cons.get("water_setback") or {}
    if c.get("enabled", False):
        if utm.get("water") is not None:
            buf = dissolved_buffer(utm["water"], float(c["distance_m"]), "mce_water_setback", segments, feedback)
            current = extract_by_location(current, buf, PRED_DISJOINT, "mce_c5_water", feedback)
            print(f"    C5 water setback {c['distance_m']:g} m: {count(current):,} remain")
        else:
            print("    C5 water setback: no water layer - excludes nothing")
        step_counts["c5_water"] = count(current)
        save_vector(current, steps_dir / "mce_c5_water.gpkg", "GPKG")

    eligible = current
    if count(eligible) == 0:
        raise RuntimeError("No building passes the MCE constraints - relax mce.constraints in config.json.")

    # ------------------------------------------------- WEIGHTS
    print("\n[STEP W] Factor weights")
    weights, weight_info = resolve_weights(mce)
    for f in weights:
        print(f"    {f:10s} {weights[f]:.3f}")
    if weight_info["method"] == "ahp":
        print(f"    AHP: lambda_max {weight_info['lambda_max']:.3f}, CI {weight_info['ci']:.3f}, "
              f"CR {weight_info['cr']:.3f} ({'OK' if weight_info['cr'] <= 0.10 else 'TOO HIGH'})")
    for w in weight_info.get("warnings", []):
        print(f"    [WARN] {w}")

    # ------------------------------------------------- STANDARDISE + COMBINE
    print("\n[STEP S] Standardise factors (0-1) and combine: score = Σ weight × factor")
    # enrich_candidates() is the Phase 2 function: it measures distances, scores
    # each factor by linear membership and sums them with the weights. We give it
    # the MCE factor ranges and weights instead of the Phase 2 ranking settings.
    mce_cfg = copy.deepcopy(cfg)
    mce_cfg["scoring"] = {
        f: {"weight": weights[f], "zero_at_m": float(mce["factors"][f]["zero_at_m"]),
            "one_at_m": float(mce["factors"][f]["one_at_m"])}
        for f in FACTORS
    }
    refs = {
        "school": union_geometry(utm["schools"]),
        "highway": union_geometry(main_highways),
        "river": union_geometry(rivers),
    }
    enrich_candidates(eligible, refs, mce_cfg)
    if "restaurant" in weights:
        f_cfg = mce["factors"]["restaurant"]
        add_optional_factor(eligible, "restaurant", union_geometry(utm.get("restaurants")),
                            float(f_cfg["zero_at_m"]), float(f_cfg["one_at_m"]), weights, cfg)
        print("    + restaurant proximity factor included in the score")
    rename_fields(eligible, {"suit_score": "mce_score", "rank": "mce_rank"})
    print(f"    {count(eligible):,} buildings scored")

    # ------------------------------------------------- RANK + SELECT
    print("\n[STEP R] Rank and select")
    sel = mce["selection"]
    method = str(sel.get("method", "match_boolean")).lower()
    n_boolean = boolean_result_count(root)
    if method == "match_boolean" and n_boolean is None:
        print("    [WARN] No Phase 2 summary found - falling back to top_n.")
        method = "top_n"
    if method == "match_boolean":
        n_select = max(1, int(n_boolean))
        expression = f'"mce_rank" <= {n_select}'
        note = f"top {n_select} (same number as the Boolean result)"
    elif method == "top_n":
        n_select = max(1, int(sel.get("top_n", 10)))
        expression = f'"mce_rank" <= {n_select}'
        note = f"top {n_select}"
    elif method == "min_score":
        threshold = float(sel.get("min_score", 0.6))
        expression = f'"mce_score" >= {threshold}'
        n_select = sum(1 for f in eligible.getFeatures() if float(f["mce_score"] or 0) >= threshold)
        note = f"score ≥ {threshold:g}"
    else:
        raise ValueError("mce.selection.method must be 'match_boolean', 'top_n' or 'min_score'.")
    selected = extract_by_expression(eligible, expression, "mce_selected", feedback)
    print(f"    {count(selected):,} sites selected: {note}")

    # ------------------------------------------------- EXPORT (GIS formats)
    save_vector(eligible, mce_dir / "mce_scored_utm.gpkg", "GPKG")
    save_vector(selected, mce_dir / "mce_selected_utm.gpkg", "GPKG")
    scored_geojson = save_vector(eligible, root / "mce_scored_buildings.geojson", "GeoJSON", wgs84())
    selected_geojson = save_vector(selected, root / "suitable_sites_mce.geojson", "GeoJSON", wgs84())

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": "Multi-criteria evaluation, weighted linear combination (phase2b_mce.py)",
        "qgis_version": qgis_version(),
        "config_file": cfg.get("_config_file"),
        "analysis_crs": analysis_crs.authid(),
        "analysis_crs_note": crs_note,
        "study_area_center": {"longitude": center_lon, "latitude": center_lat},
        "counts": {**step_counts, "scored": count(eligible), "selected": count(selected)},
        "constraints": {k: v for k, v in cons.items() if not k.startswith("_")},
        "factors": {k: v for k, v in mce["factors"].items() if not k.startswith("_")},
        "weights": weights,
        "weights_info": weight_info,
        "selection": {"method": method, "n_select": n_select, "expression": expression, "note": note},
        "_paths": {"scored": str(scored_geojson), "selected": str(selected_geojson)},
    }


# ===========================================================================
# Pure-Python part: sensitivity, Boolean comparison, summary, map
# ===========================================================================
def post_process(cfg: dict, summary: dict) -> dict:
    root = Path(cfg["_config_dir"])
    scored_path, selected_path = Path(summary["_paths"]["scored"]), Path(summary["_paths"]["selected"])
    scored = json.loads(scored_path.read_text(encoding="utf-8"))
    selected = json.loads(selected_path.read_text(encoding="utf-8"))

    # ------------------------------------------------- SENSITIVITY
    sens_cfg = cfg["mce"]["sensitivity"]
    stability = {}
    if sens_cfg.get("enabled", True) and selected["features"]:
        print("\n[STEP T] Sensitivity analysis: change each weight and re-select")
        rows = [{
            "id": str(f["properties"]["source_id"]),
            "factors": {k: float(f["properties"].get(f"score_{k}") or 0) for k in summary["weights"]},
            "area": float(f["properties"].get("area_sqm") or 0),
        } for f in scored["features"]]
        result = sensitivity(rows, summary["weights"], len(selected["features"]), float(sens_cfg.get("weight_change", 0.2)))
        stability = result["stability"]
        for s in result["scenarios"]:
            print(f"    {s['scenario']:14s} keeps {s['kept_of_base']}/{len(selected['features'])} sites, "
                  f"{s['new_sites']} new")
        values = list(stability.values())
        summary["sensitivity"] = {
            "weight_change": sens_cfg.get("weight_change", 0.2),
            "scenarios": result["scenarios"],
            "mean_stability": round(sum(values) / len(values), 3) if values else None,
            "fully_stable_sites": sum(1 for v in values if v >= 0.999),
        }
    for f in selected["features"]:
        f["properties"]["stability"] = round(stability.get(str(f["properties"]["source_id"]), 0.0), 3) \
            if stability else None

    # ------------------------------------------------- COMPARISON WITH BOOLEAN
    boolean_path = root / "suitable_sites.geojson"
    if boolean_path.is_file():
        print("\n[STEP V] Compare with the Boolean result (Phase 2)")
        boolean_fc = json.loads(boolean_path.read_text(encoding="utf-8"))
        if boolean_fc.get("features") and "source_id" not in boolean_fc["features"][0].get("properties", {}):
            print("    [WARN] suitable_sites.geojson has no source_id (old Phase 2). Re-run Phase 2 to compare.")
        else:
            comp = compare_with_boolean(selected, scored, boolean_fc, cfg["criteria"])
            path = root / "mce_vs_boolean.geojson"
            path.write_text(json.dumps(comp["collection"], ensure_ascii=False), encoding="utf-8")
            summary["comparison"] = {**comp["counts"], "boolean_count": len(boolean_fc.get("features", [])),
                                     "file": path.name}
            c = comp["counts"]
            print(f"    both {c['both']}  ·  MCE only {c['mce_only']}  ·  Boolean only {c['boolean_only']}  "
                  f"·  agreement (Jaccard) {c['jaccard']:.2f}")
    else:
        print("\n[STEP V] No suitable_sites.geojson - run Phase 2 to get the Boolean comparison.")

    # rewrite the selected GeoJSON with stability / agreement / reason
    selected_path.write_text(json.dumps(selected, ensure_ascii=False), encoding="utf-8")

    pop = sum(float(f["properties"].get("pop_estimate") or 0) for f in selected["features"])
    summary["population_proxy_total"] = pop
    summary["interpretation_notes"] = [
        "Constraints are pass/fail; factors are scored 0-1 and combined with weights, so a strong factor can compensate a weak one.",
        "Factor ranges and weights are teaching defaults (config.json > mce): agree on them with stakeholders.",
        "A low consistency ratio (CR ≤ 0.10) means the AHP judgements are coherent; it does not mean they are right.",
        "stability = share of weight-change scenarios in which the site stays selected (1.0 = robust).",
        "agreement 'both' = selected by Boolean screening AND MCE - the strongest candidates.",
        "Same caveats as Phase 2: footprints are not parcels, urban polygons are not zoning, population is a proxy.",
    ]
    out = {k: v for k, v in summary.items() if not k.startswith("_")}
    (root / "mce_summary.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


SCORE_CLASSES = [(0.8, "#1a9850"), (0.6, "#91cf60"), (0.4, "#fee08b"), (0.2, "#fc8d59"), (0.0, "#d73027")]
AGREEMENT_COLORS = {"both": "#1a9850", "mce_only": "#7b3294", "boolean_only": "#f1a340"}


def score_color(score) -> str:
    score = float(score or 0)
    return next(color for limit, color in SCORE_CLASSES if score >= limit)


def create_map(cfg: dict, summary: dict, output_html: Path) -> None:
    folium, plugins = require_folium()
    root = Path(cfg["_config_dir"])
    scored = json.loads(Path(summary["_paths"]["scored"]).read_text(encoding="utf-8"))
    selected = json.loads(Path(summary["_paths"]["selected"]).read_text(encoding="utf-8"))
    normalize_for_leaflet(scored)    # one Leaflet shape per feature, or tooltips crash the map script
    normalize_for_leaflet(selected)
    center = [summary["study_area_center"]["latitude"], summary["study_area_center"]["longitude"]]
    m = make_base_map(cfg, center)

    if scored["features"]:
        props = {k for f in scored["features"] for k in f["properties"]}
        tf, ta = existing_fields(
            ["mce_rank", "mce_score", "score_school", "score_highway", "score_river", "score_restaurant", "area_sqm"],
            ["MCE rank:", "MCE score:", "School factor:", "Highway factor:", "River factor:", "Restaurant factor:",
             "Area (m²):"], props)
        folium.GeoJson(
            scored, name="MCE score (all eligible buildings)",
            style_function=lambda f: {"color": "#555", "weight": 0.5, "fillColor": score_color(f["properties"].get("mce_score")),
                                      "fillOpacity": 0.8},
            tooltip=folium.GeoJsonTooltip(fields=tf, aliases=ta, localize=True) if tf else None,
        ).add_to(m)
    if selected["features"]:
        folium.GeoJson(
            selected, name="MCE selected sites",
            style_function=lambda f: {"color": "#000", "weight": 3, "fillOpacity": 0},
        ).add_to(m)
    comp_path = root / "mce_vs_boolean.geojson"
    if comp_path.is_file():
        comp = json.loads(comp_path.read_text(encoding="utf-8"))
        normalize_for_leaflet(comp)
        if comp["features"]:
            folium.GeoJson(
                comp, name="Boolean vs MCE agreement", show=False,
                style_function=lambda f: {"color": AGREEMENT_COLORS.get(f["properties"].get("agreement"), "#999"),
                                          "weight": 3, "fillColor": AGREEMENT_COLORS.get(f["properties"].get("agreement"), "#999"),
                                          "fillOpacity": 0.6},
                tooltip=folium.GeoJsonTooltip(fields=["agreement", "reason"], aliases=["Agreement:", "Why:"]),
            ).add_to(m)

    legend = "".join(
        f'<div><span style="display:inline-block;width:12px;height:12px;background:{c};margin-right:6px"></span>'
        f'score ≥ {lim:g}</div>' for lim, c in SCORE_CLASSES)
    m.get_root().html.add_child(folium.Element(
        '<div style="position:fixed;bottom:24px;right:24px;z-index:9999;background:#fff;padding:10px 12px;'
        'border-radius:8px;font:12px system-ui,sans-serif;box-shadow:0 2px 8px rgba(0,0,0,.2)">'
        f'<b>MCE score</b>{legend}<div style="margin-top:4px">▭ black outline = selected</div></div>'))
    plugins.Fullscreen().add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(str(output_html))


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 2b - multi-criteria evaluation (MCE)")
    parser.add_argument("--config", help="path to a config JSON (default: config.json)")
    args = parser.parse_args()
    cfg = load_config(args.config)

    print("=" * 68)
    print("PHASE 2b — MULTI-CRITERIA EVALUATION (weighted linear combination)")
    print("=" * 68)
    app = init_qgis(with_processing=True)
    try:
        summary = run_mce(cfg)
    finally:
        shutdown_qgis(app)

    summary = post_process(cfg, summary)
    output_html = Path(cfg["_config_dir"]) / "phase2b_mce.html"
    print("\n[STEP G] Building the quick-look map")
    create_map(cfg, summary, output_html)

    c = summary["counts"]
    print("\n" + "=" * 68)
    print("PHASE 2b COMPLETE")
    print("=" * 68)
    print(f"  Buildings:                {c['total_buildings']:,}")
    print(f"  After constraints:        {c['scored']:,} (all scored)")
    print(f"  Selected:                 {c['selected']:,}  [{summary['selection']['note']}]")
    print("  Weights:                  " + ", ".join(f"{k} {v:.2f}" for k, v in summary["weights"].items()))
    if "cr" in summary["weights_info"]:
        print(f"  AHP consistency ratio:    {summary['weights_info']['cr']:.3f}")
    if "sensitivity" in summary:
        print(f"  Mean stability:           {summary['sensitivity']['mean_stability']}")
    if "comparison" in summary:
        cp = summary["comparison"]
        print(f"  vs Boolean:               both {cp['both']}, MCE only {cp['mce_only']}, Boolean only {cp['boolean_only']}")
    print(f"  Map:                      {output_html}")
    print("\n  Next: python3 phase3_showcase.py   (shows Boolean and MCE side by side)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"\n[FATAL] Phase 2b failed: {error}", file=sys.stderr)
        sys.exit(1)
