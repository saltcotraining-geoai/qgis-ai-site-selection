#!/usr/bin/env python3
"""Phase 2 - reproducible PyQGIS site-selection analysis.

What it does (each step matches one tool in the manual QGIS exercise):

    STEP 1  Load the input GeoPackages (originals are never modified)
    STEP 2  Choose a metric analysis CRS (local UTM zone, or the one in config)
    STEP 3  Reproject + Fix geometries          (Reproject Layer, Fix Geometries)
    STEP A  Footprint area 800-1,200 m2         (Field Calculator, Extract by Expression)
    STEP B  Within 1,000 m of a school          (Buffer + dissolve, Extract by Location: intersect)
    STEP C  Not within 100 m of a main highway  (Extract by Expression, Buffer, Extract by Location: disjoint)
    STEP D  Not within 300 m of a river         (Buffer, Extract by Location: disjoint)
    STEP E  In a mapped urban area              (Fix Geometries, Extract by Location: intersect / within)
    STEP F  Population proxy + ranking score    (Field Calculator / Python)
    STEP M  Criteria matrix: pass/fail + measured values for EVERY building (ground truth)
    STEP G  Export web layers + summary + quick-look map

Run from a terminal (see README.md for Windows/macOS):
    python3 phase2_site_selection.py
    python3 phase2_site_selection.py --config my_town.json

Outputs
    analysis_data/utm/*.gpkg        metric copies of the inputs (fixed geometries)
    analysis_data/steps/*.gpkg      the candidate layer after every step
    analysis_zones/*.geojson        buffers / urban polygons for the web maps
    suitable_sites.geojson          final candidates (WGS 84) - used by Phase 3
    site_selection_summary.json     counts, criteria, QGIS version, notes
    phase2_site_selection.html      quick-look map
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

# site_common has no QGIS dependency; qgis_common sets up the PyQGIS paths.
from site_common import class_filter_expression, analysis_simplify_m, web_simplify_m, existing_fields, normalize_for_leaflet, load_config, make_base_map, project_path, require_folium
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
    simplify_layer,
    SIMPLIFY_LOG,
)
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)

# Predicate codes for native:extractbylocation (same order as the GUI list):
# 0 intersect, 1 contain, 2 disjoint, 3 equal, 4 touch, 5 overlap, 6 are within, 7 cross
PRED_INTERSECT = 0
PRED_DISJOINT = 2
PRED_WITHIN = 6


# ===========================================================================
# Small building blocks
# ===========================================================================
def count(layer: QgsVectorLayer) -> int:
    return int(layer.featureCount())


def choose_analysis_crs(cfg: dict, layer: QgsVectorLayer):
    """STEP 2 - return (crs, description, center_lon, center_lat).

    'auto' = UTM zone of the buildings' centre. A fixed code (e.g. EPSG:32734)
    lets you match exactly the CRS used in the manual QGIS exercise.
    """
    extent = layer.extent()
    to_wgs84 = QgsCoordinateTransform(layer.crs(), wgs84(), QgsProject.instance())
    center = to_wgs84.transform(QgsPointXY(extent.center()))
    lon, lat = center.x(), center.y()

    setting = str(cfg["analysis"].get("analysis_crs", "auto")).strip()
    if setting.lower() == "auto" and not layer.crs().isGeographic() and layer.crs().authid() != "EPSG:3857":
        # Data already in a projected (metric) CRS - e.g. the Phase 0 output, or course
        # data already reprojected to UTM 36N in class: keep it, do not switch zones.
        crs = layer.crs()
        return crs, f"{crs.authid()} (auto: the data's own projected CRS)", lon, lat
    if setting.lower() != "auto":
        crs = QgsCoordinateReferenceSystem(setting)
        if not crs.isValid():
            raise ValueError(f"analysis_crs '{setting}' in config is not a valid CRS.")
        if crs.isGeographic():
            raise ValueError(f"analysis_crs '{setting}' is geographic (degrees); use a projected CRS in metres.")
        return crs, f"{crs.authid()} (from config)", lon, lat

    if not (-180.0 <= lon <= 180.0 and -80.0 <= lat <= 84.0):
        raise ValueError(f"Study-area centre ({lon:.5f}, {lat:.5f}) is outside UTM coverage.")
    zone = max(1, min(60, int(math.floor((lon + 180.0) / 6.0)) + 1))
    epsg = (32700 if lat < 0 else 32600) + zone
    crs = QgsCoordinateReferenceSystem(f"EPSG:{epsg}")
    if not crs.isValid():
        raise RuntimeError(f"Could not construct local UTM CRS EPSG:{epsg}.")
    return crs, f"{crs.authid()} (auto: UTM zone {zone}{'S' if lat < 0 else 'N'})", lon, lat


def prepare_layer(layer, name, crs, utm_dir: Path, feedback, simplify_m: float | None = None) -> QgsVectorLayer:
    """STEP 3 - reproject to the metric CRS, fix invalid geometries, optionally simplify.

    FIX: the original only repaired the urban layer. OSM buildings and schools
    often contain self-intersecting polygons, and standalone Processing usually
    STOPS an algorithm when it meets an invalid geometry. Fixing every input
    first makes the run reliable and matches good manual practice.

    PERFORMANCE: with simplify_m (metres, from config performance.simplify_analysis)
    lines/polygons are simplified (Douglas-Peucker) and fixed again - fewer
    vertices make buffers, overlays and distance checks faster. Edges move by at
    most simplify_m, so distances to this layer can change by up to that much.
    """
    reprojected = output_layer(
        run_alg(
            "native:reprojectlayer",
            {"INPUT": layer, "TARGET_CRS": crs, "OUTPUT": "TEMPORARY_OUTPUT"},
            f"Reproject {name} to {crs.authid()}",
            feedback,
        ),
        "OUTPUT",
        f"{name}_reprojected",
    )
    fixed = output_layer(
        run_alg(
            "native:fixgeometries",
            {"INPUT": reprojected, "OUTPUT": "TEMPORARY_OUTPUT"},
            f"Fix geometries of {name}",
            feedback,
        ),
        "OUTPUT",
        f"{name}_utm",
    )
    fixed = simplify_layer(fixed, simplify_m, f"{name}_utm", feedback)  # no-op when simplify_m is None
    save_vector(fixed, utm_dir / f"{name}_utm.gpkg", "GPKG")
    return fixed


def dissolved_buffer(layer, distance_m, label, segments, feedback) -> QgsVectorLayer:
    """Buffer with 'Dissolve result' ticked (one merged zone)."""
    return output_layer(
        run_alg(
            "native:buffer",
            {
                "INPUT": layer,
                "DISTANCE": distance_m,      # metres, because the layer is in UTM
                "SEGMENTS": segments,        # smoothness of the round ends
                "END_CAP_STYLE": 0,          # round
                "JOIN_STYLE": 0,             # round
                "MITER_LIMIT": 2,
                "DISSOLVE": True,
                "OUTPUT": "TEMPORARY_OUTPUT",
            },
            label,
            feedback,
        ),
        "OUTPUT",
        label,
    )


def extract_by_location(inp, other, predicate, label, feedback) -> QgsVectorLayer:
    return output_layer(
        run_alg(
            "native:extractbylocation",
            {"INPUT": inp, "PREDICATE": [predicate], "INTERSECT": other, "OUTPUT": "TEMPORARY_OUTPUT"},
            label,
            feedback,
        ),
        "OUTPUT",
        label,
    )


def extract_by_expression(inp, expression, label, feedback) -> QgsVectorLayer:
    return output_layer(
        run_alg(
            "native:extractbyexpression",
            {"INPUT": inp, "EXPRESSION": expression, "OUTPUT": "TEMPORARY_OUTPUT"},
            label,
            feedback,
        ),
        "OUTPUT",
        label,
    )


def class_counts(layer: QgsVectorLayer, field: str) -> dict:
    """Value counts of one attribute (like Layer Properties > Fields, or 'Show unique values')."""
    counts = {}
    for f in layer.getFeatures():
        value = f[field]
        key = "NULL" if value is None or str(value) in ("", "NULL") else str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def filter_by_class(layer, field: str, classes, label: str, feedback, extra: str | None = None) -> QgsVectorLayer:
    """ATTRIBUTE filter before any geometry work: keep only the classes a rule is about.

    Manual QGIS: open the attribute table, check the unique values, then
    Extract by Expression  "field" IN ('a','b').  Filtering first means the buffer
    and overlay steps handle far fewer features, so they run faster.
    """
    expression = class_filter_expression(field, classes)
    if expression is not None and field not in layer.fields().names():
        raise RuntimeError(f"{label}: no '{field}' field (fields: {layer.fields().names()}). "
                           f"Fix the field name under 'fields' in config.json.")
    if field in layer.fields().names():
        found = class_counts(layer, field)
        print(f"    {label} classes in the attribute table: "
              + ", ".join(f"{k} ({v})" for k, v in list(found.items())[:12]))
    parts = [e for e in (extra, expression) if e]
    if not parts:
        return layer
    result = extract_by_expression(layer, " AND ".join(f"({e})" for e in parts), label, feedback)
    if expression is not None:
        print(f"    {label}: kept {count(result):,} of {count(layer):,} features where {expression}")
    return result


def main_highways_layer(roads, cfg: dict, feedback) -> QgsVectorLayer:
    """Roads -> only the main-highway classes (criteria.main_highway_classes)."""
    field = cfg["fields"]["highway"]
    if field not in roads.fields().names():
        raise RuntimeError(f"Roads layer has no '{field}' field. Fields are: {roads.fields().names()}. "
                           "Set fields.highway in config.json.")
    return filter_by_class(roads, field, cfg["criteria"]["main_highway_classes"], "main_highways", feedback)


def river_layer(rivers, cfg: dict, feedback) -> QgsVectorLayer:
    """Rivers -> non-empty geometries, and only criteria.river_classes when that list is set."""
    return filter_by_class(rivers, cfg["fields"].get("waterway", "waterway"),
                           cfg["criteria"].get("river_classes"), "rivers_filtered", feedback,
                           extra="$geometry IS NOT NULL AND NOT is_empty($geometry)")


def union_geometry(layer: QgsVectorLayer | None) -> QgsGeometry | None:
    """All non-empty geometries of a layer merged into one (for distance checks)."""
    if layer is None:
        return None
    geoms = [f.geometry() for f in layer.getFeatures() if f.hasGeometry() and not f.geometry().isEmpty()]
    return QgsGeometry.unaryUnion(geoms) if geoms else None


def linear_score(distance: float | None, zero_at: float, one_at: float) -> float:
    """0-1 score by linear interpolation: `zero_at` metres -> 0, `one_at` metres -> 1.

    Works both ways: school (closer is better) uses zero_at=1000, one_at=0;
    highway (farther is better) uses zero_at=100, one_at=500.
    If the reference layer is empty (distance None) the factor is not limiting -> 1.
    """
    if distance is None or zero_at == one_at:
        return 1.0
    t = (distance - zero_at) / (one_at - zero_at)
    return max(0.0, min(1.0, t))


def parse_levels(value, default: float) -> float:
    """OSM 'building:levels' is text ('2', '2.5', '3;4', NULL). Return a number >= 1."""
    try:
        text = str(value).replace(",", ".").split(";")[0].strip()
        levels = float(text)
    except (TypeError, ValueError):
        return default
    return levels if levels >= 1 else default


def pick_id_field(layer: QgsVectorLayer, candidates: list[str]) -> str | None:
    names = layer.fields().names()
    for candidate in candidates:
        if candidate in names:
            return candidate
    return None


# ===========================================================================
# STEP F - population proxy, distances, scores, ranking (pure PyQGIS/Python)
# ===========================================================================
NEW_FIELDS = [
    ("site_id", "int"),          # 1 = best ranked candidate
    ("rank", "int"),
    ("source_id", "string"),     # stable ID from the input (osm_id/full_id/fid)
    ("levels_used", "double"),
    ("pop_estimate", "double"),         # area / 30   (baseline taught in class)
    ("pop_estimate_levels", "double"),  # area * levels / 30
    ("dist_school_m", "double"),
    ("dist_highway_m", "double"),
    ("dist_river_m", "double"),
    ("score_school", "double"),
    ("score_highway", "double"),
    ("score_river", "double"),
    ("suit_score", "double"),    # weighted sum, 0-1
    ("lat", "double"),           # point-on-surface, WGS 84
    ("lon", "double"),
]


def enrich_candidates(layer: QgsVectorLayer, refs: dict, cfg: dict) -> QgsVectorLayer:
    """Add population, distance, score, rank and lat/lon fields to `layer` (in place).

    Distances are planar metres in the analysis CRS, from the building footprint
    to the nearest schools / main highways / rivers geometry (0 if touching).
    """
    pr = layer.dataProvider()
    existing = layer.fields().names()
    pr.addAttributes([make_field(n, t) for n, t in NEW_FIELDS if n not in existing])
    layer.updateFields()
    idx = {n: layer.fields().indexOf(n) for n, _ in NEW_FIELDS}

    pop_cfg = cfg["population"]
    sqm_per_person = float(pop_cfg["sqm_per_person"])
    default_levels = float(pop_cfg.get("default_levels", 1))
    levels_field = cfg["fields"]["building_levels"]
    has_levels = levels_field in existing
    id_field = pick_id_field(layer, cfg["fields"]["id_candidates"])

    sc = cfg["scoring"]
    weights = {k: float(sc[k]["weight"]) for k in ("school", "highway", "river")}
    weight_sum = sum(weights.values()) or 1.0
    weights = {k: w / weight_sum for k, w in weights.items()}  # normalise to 1

    to_wgs84 = QgsCoordinateTransform(layer.crs(), wgs84(), QgsProject.instance())

    rows = []
    for feat in layer.getFeatures():
        geom = feat.geometry()
        area = float(feat["area_sqm"] or 0.0)
        levels = parse_levels(feat[levels_field], default_levels) if has_levels else default_levels

        def dist(ref):
            if ref is None:
                return None
            d = geom.distance(ref)  # QGIS returns -1 if the distance cannot be computed
            return round(d, 1) if d >= 0 else None

        d_school, d_hwy, d_river = dist(refs["school"]), dist(refs["highway"]), dist(refs["river"])
        s_school = linear_score(d_school, sc["school"]["zero_at_m"], sc["school"]["one_at_m"])
        s_hwy = linear_score(d_hwy, sc["highway"]["zero_at_m"], sc["highway"]["one_at_m"])
        s_river = linear_score(d_river, sc["river"]["zero_at_m"], sc["river"]["one_at_m"])
        total = weights["school"] * s_school + weights["highway"] * s_hwy + weights["river"] * s_river

        point = geom.pointOnSurface().asPoint()  # always inside the polygon (centroid may not be)
        ll = to_wgs84.transform(point)

        rows.append({
            "fid": feat.id(),
            "source_id": str(feat[id_field]) if id_field else str(feat.id()),
            "levels_used": levels,
            "pop_estimate": round(area / sqm_per_person, 2),
            "pop_estimate_levels": round(area * levels / sqm_per_person, 2),
            "dist_school_m": d_school,
            "dist_highway_m": d_hwy,
            "dist_river_m": d_river,
            "score_school": round(s_school, 3),
            "score_highway": round(s_hwy, 3),
            "score_river": round(s_river, 3),
            "suit_score": round(total, 3),
            "lat": round(ll.y(), 7),
            "lon": round(ll.x(), 7),
            "_area": area,
        })

    # Rank: highest score first; ties broken by larger footprint, then source_id.
    rows.sort(key=lambda r: (-r["suit_score"], -r["_area"], r["source_id"]))
    changes = {}
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
        row["site_id"] = rank
        changes[row["fid"]] = {idx[name]: row[name] for name, _ in NEW_FIELDS}
    if changes and not pr.changeAttributeValues(changes):
        raise RuntimeError("Could not write the new attribute values.")
    return layer


# ===========================================================================
# STEP M - criteria matrix: measured values + pass/fail for EVERY building
# ===========================================================================
MATRIX_FIELDS = [
    ("source_id", "string"),
    ("dist_school_m", "double"), ("dist_highway_m", "double"), ("dist_river_m", "double"),
    ("urban_intersects", "int"), ("urban_within", "int"),
    ("pass_area", "int"), ("pass_school", "int"), ("pass_highway", "int"),
    ("pass_river", "int"), ("pass_urban", "int"), ("pass_all", "int"),
    ("fail_reasons", "string"),
    ("lat", "double"), ("lon", "double"),
]
MATRIX_CSV_COLUMNS = ["source_id", "area_sqm"] + [n for n, _ in MATRIX_FIELDS if n != "source_id"]


def build_criteria_matrix(buildings: QgsVectorLayer, refs: dict, urban: QgsVectorLayer,
                          cfg: dict, relation: str) -> list[dict]:
    """Measure every criterion for every building and record pass/fail (fields added in place).

    Why: the sequential Extract steps only tell you who SURVIVED. This table
    answers "why was building X rejected?" for all buildings, and it is the
    GROUND TRUTH that the AI experiment (experiment/evaluate.py) checks every
    AI-selected site against.

    The rules mirror Steps A-E, but as distances instead of buffers:
        A  min <= area <= max          B  distance to school <= school_distance_m
        C  distance to highway > m     D  distance to river > m
        E  intersects (or within) one urban polygon
    pass_all should reproduce the Boolean result exactly; Phase 2 checks it.
    """
    crit = cfg["criteria"]
    pr = buildings.dataProvider()
    existing = buildings.fields().names()
    pr.addAttributes([make_field(n, t) for n, t in MATRIX_FIELDS if n not in existing])
    buildings.updateFields()
    idx = {n: buildings.fields().indexOf(n) for n, _ in MATRIX_FIELDS}
    id_field = pick_id_field(buildings, cfg["fields"]["id_candidates"])
    urban_polys = [f.geometry() for f in urban.getFeatures() if f.hasGeometry()]
    to_wgs84 = QgsCoordinateTransform(buildings.crs(), wgs84(), QgsProject.instance())

    lo, hi = float(crit["min_area_sqm"]), float(crit["max_area_sqm"])
    school_m, hwy_m, river_m = (float(crit["school_distance_m"]), float(crit["highway_exclusion_m"]),
                                float(crit["river_exclusion_m"]))
    rows, changes = [], {}
    for feat in buildings.getFeatures():
        geom = feat.geometry()

        def dist(ref):
            if ref is None:
                return None
            d = geom.distance(ref)
            return round(d, 1) if d >= 0 else None

        area = float(feat["area_sqm"] or 0.0)
        d_school, d_hwy, d_river = dist(refs["school"]), dist(refs["highway"]), dist(refs["river"])
        inter = any(geom.intersects(p) for p in urban_polys)
        within = any(geom.within(p) for p in urban_polys)

        checks = {
            "pass_area": lo <= area <= hi,
            "pass_school": d_school is not None and d_school <= school_m,
            "pass_highway": d_hwy is None or d_hwy > hwy_m,
            "pass_river": d_river is None or d_river > river_m,
            "pass_urban": within if relation == "within" else inter,
        }
        reasons = []
        if not checks["pass_area"]:
            reasons.append(f"area {area:,.0f} m² outside {lo:g}–{hi:g}")
        if not checks["pass_school"]:
            reasons.append(f"school {d_school:,.0f} m > {school_m:g} m" if d_school is not None else "no school")
        if not checks["pass_highway"]:
            reasons.append(f"highway {d_hwy:,.0f} m ≤ {hwy_m:g} m")
        if not checks["pass_river"]:
            reasons.append(f"river {d_river:,.0f} m ≤ {river_m:g} m")
        if not checks["pass_urban"]:
            reasons.append(f"not {relation} an urban polygon")

        point = to_wgs84.transform(geom.pointOnSurface().asPoint())
        row = {
            "source_id": str(feat[id_field]) if id_field else str(feat.id()),
            "area_sqm": round(area, 3),
            "dist_school_m": d_school, "dist_highway_m": d_hwy, "dist_river_m": d_river,
            "urban_intersects": int(inter), "urban_within": int(within),
            **{k: int(v) for k, v in checks.items()},
            "pass_all": int(all(checks.values())),
            "fail_reasons": "; ".join(reasons),
            "lat": round(point.y(), 7), "lon": round(point.x(), 7),
        }
        rows.append(row)
        changes[feat.id()] = {idx[n]: row[n] for n, _ in MATRIX_FIELDS}
    if changes and not pr.changeAttributeValues(changes):
        raise RuntimeError("Could not write the criteria-matrix values.")
    return rows


# ===========================================================================
# The analysis. Kept in one function so that all QgsVectorLayer objects go
# out of scope when it returns - required for a clean QGIS shutdown.
# ===========================================================================
def run_analysis(cfg: dict) -> dict:
    feedback = ConsoleFeedback(verbose=bool(cfg["analysis"].get("verbose_processing")))
    set_geojson_precision(cfg)
    crit = cfg["criteria"]
    segments = int(cfg["analysis"].get("buffer_segments", 36))

    dataset_dir = project_path(cfg, "dataset_dir")
    analysis_dir = project_path(cfg, "analysis_dir")
    utm_dir, steps_dir = analysis_dir / "utm", analysis_dir / "steps"
    zones_dir = project_path(cfg, "zones_dir")
    root = Path(cfg["_config_dir"])
    for folder in (utm_dir, steps_dir, zones_dir):
        folder.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------- STEP 1
    print("\n[STEP 1] Load source data (original GeoPackages are not modified)")
    names = cfg["layers"]
    src = {key: load_vector(dataset_dir, names[key]) for key in ("buildings", "schools", "roads", "rivers", "urban")}
    for key, layer in src.items():
        print(f"  {key:10s} {count(layer):6d} features  {layer.crs().authid()}")

    # -------------------------------------------------------------- STEP 2
    analysis_crs, crs_note, center_lon, center_lat = choose_analysis_crs(cfg, src["buildings"])
    print(f"\n[STEP 2] Analysis CRS: {crs_note}; study-area centre {center_lon:.5f}, {center_lat:.5f}")

    # -------------------------------------------------------------- STEP 3
    print("\n[STEP 3] Reproject to metres and fix geometries")
    utm = {key: prepare_layer(layer, key, analysis_crs, utm_dir, feedback, analysis_simplify_m(cfg, key))
           for key, layer in src.items()}
    total_buildings = count(utm["buildings"])

    # -------------------------------------------------------------- STEP A
    print(f"\n[STEP A] Footprint area between {crit['min_area_sqm']:g} and {crit['max_area_sqm']:g} m2")
    # area($geometry) is PLANAR in the layer's CRS (metres here).
    # NOTE for the manual comparison: in the QGIS Field Calculator, `$area`
    # is ELLIPSOIDAL (uses the project ellipsoid) and can differ slightly, so
    # buildings close to 800 or 1,200 m2 may switch sides. Use area($geometry)
    # in the GUI too if you want identical results.
    with_area = output_layer(
        run_alg(
            "native:fieldcalculator",
            {
                "INPUT": utm["buildings"],
                "FIELD_NAME": "area_sqm",
                "FIELD_TYPE": 0,  # 0 = Decimal (double)
                "FIELD_LENGTH": 20,
                "FIELD_PRECISION": 3,
                "FORMULA": "area($geometry)",
                "OUTPUT": "TEMPORARY_OUTPUT",
            },
            "Calculate planar footprint area (m2)",
            feedback,
        ),
        "OUTPUT",
        "buildings_with_area",
    )
    step_a = extract_by_expression(
        with_area,
        f'"area_sqm" >= {float(crit["min_area_sqm"])} AND "area_sqm" <= {float(crit["max_area_sqm"])}',
        "step_a_area",
        feedback,
    )
    save_vector(step_a, steps_dir / "step_a_area_candidates.gpkg", "GPKG")
    print(f"    {count(step_a):,} candidates")

    # -------------------------------------------------------------- STEP B
    print(f"\n[STEP B] Within {crit['school_distance_m']:g} m of a school")
    if count(utm["schools"]) == 0:
        raise RuntimeError("The schools layer is empty - Step B cannot be evaluated.")
    school_buffer = dissolved_buffer(
        utm["schools"], float(crit["school_distance_m"]), "school_buffer", segments, feedback
    )
    # 'intersect' = any part of the footprint lies inside the school zone.
    step_b = extract_by_location(step_a, school_buffer, PRED_INTERSECT, "step_b_school", feedback)
    save_vector(step_b, steps_dir / "step_b_within_school_distance.gpkg", "GPKG")
    print(f"    {count(step_b):,} candidates")

    # -------------------------------------------------------------- STEP C
    print(f"\n[STEP C] Exclude footprints within {crit['highway_exclusion_m']:g} m of main highways")
    main_highways = main_highways_layer(utm["roads"], cfg, feedback)
    highway_buffer = None
    if count(main_highways) == 0:
        # FIX: no matching roads -> nothing to exclude. Skip instead of buffering an empty layer.
        print("    [WARN] No main-highway features matched; Step C excludes nothing.")
        step_c = step_b
    else:
        highway_buffer = dissolved_buffer(
            main_highways, float(crit["highway_exclusion_m"]), "highway_buffer", segments, feedback
        )
        # 'disjoint' = keep only footprints that do NOT touch the exclusion zone.
        step_c = extract_by_location(step_b, highway_buffer, PRED_DISJOINT, "step_c_highway", feedback)
    save_vector(step_c, steps_dir / "step_c_outside_highway_buffer.gpkg", "GPKG")
    print(f"    {count(step_c):,} candidates remain; {count(main_highways)} road segments are main highways")

    # -------------------------------------------------------------- STEP D
    print(f"\n[STEP D] Exclude footprints within {crit['river_exclusion_m']:g} m of rivers")
    rivers = river_layer(utm["rivers"], cfg, feedback)
    river_buffer = None
    if count(rivers) == 0:
        print("    [WARN] No river geometries; Step D excludes nothing.")
        step_d = step_c
    else:
        river_buffer = dissolved_buffer(
            rivers, float(crit["river_exclusion_m"]), "river_buffer", segments, feedback
        )
        step_d = extract_by_location(step_c, river_buffer, PRED_DISJOINT, "step_d_river", feedback)
    save_vector(step_d, steps_dir / "step_d_outside_river_buffer.gpkg", "GPKG")
    print(f"    {count(step_d):,} candidates remain")

    # -------------------------------------------------------------- STEP E
    print("\n[STEP E] Mapped urban area (urban geometries were fixed in STEP 3)")
    urban_intersects = extract_by_location(step_d, utm["urban"], PRED_INTERSECT, "step_e_intersects", feedback)
    urban_within = extract_by_location(step_d, utm["urban"], PRED_WITHIN, "step_e_within", feedback)
    save_vector(urban_intersects, steps_dir / "step_e_urban_intersects.gpkg", "GPKG")
    save_vector(urban_within, steps_dir / "step_e_urban_within.gpkg", "GPKG")
    relation = str(crit.get("urban_relation", "intersects")).lower()
    if relation not in ("intersects", "within"):
        raise ValueError("criteria.urban_relation must be 'intersects' or 'within'.")
    final, alternative = (urban_within, urban_intersects) if relation == "within" else (urban_intersects, urban_within)
    alt_relation = "intersects" if relation == "within" else "within"
    print(f"    intersects: {count(urban_intersects):,}   within: {count(urban_within):,}   "
          f"-> primary result uses '{relation}'")

    # -------------------------------------------------------------- STEP F
    print("\n[STEP F] Population proxy, distances, suitability score and rank")
    refs = {
        "school": union_geometry(utm["schools"]),
        "highway": union_geometry(main_highways),
        "river": union_geometry(rivers),
    }
    enrich_candidates(final, refs, cfg)
    enrich_candidates(alternative, refs, cfg)
    pop_total = sum(float(f["pop_estimate"] or 0) for f in final.getFeatures())
    pop_levels_total = sum(float(f["pop_estimate_levels"] or 0) for f in final.getFeatures())
    print(f"    {count(final):,} final candidates; population proxy {pop_total:.1f} "
          f"(with levels {pop_levels_total:.1f})")

    # -------------------------------------------------------------- STEP M
    print(f"\n[STEP M] Criteria matrix: pass/fail for all {total_buildings:,} buildings")
    matrix = build_criteria_matrix(with_area, refs, utm["urban"], cfg, relation)
    matrix_ids = {r["source_id"] for r in matrix if r["pass_all"]}
    id_field = pick_id_field(final, cfg["fields"]["id_candidates"])
    final_ids = {str(f[id_field]) if id_field else str(f.id()) for f in final.getFeatures()}
    matrix_check = {
        "matrix_pass_all": len(matrix_ids),
        "boolean_final": len(final_ids),
        "only_in_matrix": sorted(matrix_ids - final_ids),
        "only_in_boolean": sorted(final_ids - matrix_ids),
    }
    agree = not matrix_check["only_in_matrix"] and not matrix_check["only_in_boolean"]
    print(f"    pass_all = {len(matrix_ids)}; Boolean Steps A-E = {len(final_ids)} -> "
          + ("identical ✔" if agree else
             f"differ: {matrix_check['only_in_matrix']} / {matrix_check['only_in_boolean']} "
             "(buffer-polygon edge cases: a buffer is a polygon approximation of a true distance)"))
    with (root / "criteria_matrix.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MATRIX_CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(matrix)
    save_vector(with_area, analysis_dir / "criteria_matrix_utm.gpkg", "GPKG")
    save_vector(with_area, root / "all_buildings_evaluated.geojson", "GeoJSON", wgs84())

    # -------------------------------------------------------------- STEP G
    print("\n[STEP G] Export web layers (WGS 84) and the summary")
    save_vector(final, analysis_dir / "final_suitable_sites_utm.gpkg", "GPKG")
    final_geojson = save_vector(final, root / "suitable_sites.geojson", "GeoJSON", wgs84())
    save_vector(alternative, root / f"suitable_sites_{alt_relation}.geojson", "GeoJSON", wgs84())

    # Web copies of the zones: simplified for display only (performance.simplify_web).
    # Buffers with 36 segments per curve carry many vertices that a web map does not need.
    def web(layer, key):
        return simplify_layer(layer, web_simplify_m(cfg, key), f"{key}_web", feedback)

    save_vector(web(school_buffer, "school_zone"), zones_dir / "school_zone.geojson", "GeoJSON", wgs84())
    for name, layer in (("highway_exclusion.geojson", highway_buffer), ("river_exclusion.geojson", river_buffer)):
        path = zones_dir / name
        if layer is not None:
            save_vector(web(layer, path.stem), path, "GeoJSON", wgs84())
        elif path.is_file():
            path.unlink()  # do not leave an old zone from a previous run
    save_vector(web(utm["urban"], "urban"), zones_dir / "urban_area_polygons.geojson", "GeoJSON", wgs84())

    counts = {
        "total_buildings": total_buildings,
        "step_a_area": count(step_a),
        "step_b_school": count(step_b),
        "step_c_highway": count(step_c),
        "step_d_river": count(step_d),
        "step_e_urban_intersects": count(urban_intersects),
        "step_e_urban_within": count(urban_within),
        "final": count(final),
    }
    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": "PyQGIS script (phase2_site_selection.py)",
        "qgis_version": qgis_version(),
        "config_file": cfg.get("_config_file"),
        "analysis_crs": analysis_crs.authid(),
        "analysis_crs_note": crs_note,
        "study_area_center": {"longitude": center_lon, "latitude": center_lat},
        "inputs": {key: src[key].source() for key in src},
        "counts": counts,
        "population_proxy_total": pop_total,
        "population_proxy_levels_total": pop_levels_total,
        "criteria": {k: v for k, v in crit.items() if not k.startswith("_")},
        "population": {k: v for k, v in cfg["population"].items() if not k.startswith("_")},
        "scoring": {k: v for k, v in cfg["scoring"].items() if not k.startswith("_")},
        "outputs": {
            "final": final_geojson.name,
            "alternative": f"suitable_sites_{alt_relation}.geojson",
            "criteria_matrix": "criteria_matrix.csv",
            "all_buildings": "all_buildings_evaluated.geojson",
        },
        "criteria_matrix_check": matrix_check,
        "performance": {
            **{k: v for k, v in cfg.get("performance", {}).items() if not k.startswith("_")},
            "simplified": dict(SIMPLIFY_LOG),
        },
        "interpretation_notes": [
            f"Primary output uses the '{relation}' urban relation; the '{alt_relation}' result is saved for comparison.",
            "Screening (Steps A-E) is pass/fail. suit_score (0-1) only RANKS the candidates that passed; it is not used to exclude any.",
            "The urban layer holds cadastral/erf-derived polygons; it is not a zoning map and does not prove residential use.",
            "The buildings layer holds footprints, not parcels or vacant lots.",
            "pop_estimate = footprint area / sqm_per_person; pop_estimate_levels also multiplies by building:levels. Both are crude proxies, not census population.",
            "Distances are planar metres in the analysis CRS, measured from the footprint edge.",
            "Reference layers listed in performance.simplify_analysis were simplified (see 'performance'); distances to them can differ from unsimplified data by up to the tolerance. Building footprints are not simplified.",
            "Area uses area($geometry) (planar). The GUI's $area is ellipsoidal and may differ slightly near the thresholds.",
        ],
    }
    summary_path = root / "site_selection_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    summary["_paths"] = {
        "final_geojson": str(final_geojson),
        "summary": str(summary_path),
        "zones_dir": str(zones_dir),
        "analysis_dir": str(analysis_dir),
    }
    return summary  # only plain Python data leaves this function


# ===========================================================================
# Quick-look map (folium only - runs after QGIS has been shut down)
# ===========================================================================
def create_map(cfg: dict, summary: dict, output_html: Path) -> None:
    folium, plugins = require_folium()
    zones_dir = Path(summary["_paths"]["zones_dir"])
    with open(summary["_paths"]["final_geojson"], encoding="utf-8") as handle:
        sites = json.load(handle)
    normalize_for_leaflet(sites)

    center = [summary["study_area_center"]["latitude"], summary["study_area_center"]["longitude"]]
    m = make_base_map(cfg, center)
    crit = summary["criteria"]
    overlays = [
        ("school_zone.geojson", f"School proximity ({crit['school_distance_m']:g} m)", "#1f78b4", 0.10),
        ("highway_exclusion.geojson", f"Highway exclusion ({crit['highway_exclusion_m']:g} m)", "#e31a1c", 0.15),
        ("river_exclusion.geojson", f"River exclusion ({crit['river_exclusion_m']:g} m)", "#33a02c", 0.15),
        ("urban_area_polygons.geojson", "Mapped urban/erf polygons", "#6a3d9a", 0.08),
    ]
    for filename, label, color, opacity in overlays:
        path = zones_dir / filename
        if not path.is_file():
            continue
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        normalize_for_leaflet(data)  # one Leaflet shape per feature, or tooltips crash the map script
        folium.GeoJson(
            data,
            name=label,
            style_function=lambda f, c=color, o=opacity: {"color": c, "weight": 1, "fillColor": c, "fillOpacity": o},
        ).add_to(m)

    if sites.get("features"):
        props = {k for f in sites["features"] for k in (f.get("properties") or {})}
        fields, aliases = existing_fields(
            ["rank", "source_id", "area_sqm", "pop_estimate", "suit_score"],
            ["Rank:", "Source ID:", "Footprint area (m²):", "Population proxy:", "Suitability (0-1):"],
            props,
        )
        folium.GeoJson(
            sites,
            name="Suitable building candidates",
            style_function=lambda f: {"color": "#006837", "weight": 2, "fillColor": "#31a354", "fillOpacity": 0.72},
            highlight_function=lambda f: {"weight": 4, "color": "#ffff00"},
            tooltip=folium.GeoJsonTooltip(fields=fields, aliases=aliases, localize=True) if fields else None,
        ).add_to(m)
    else:
        print("  [WARN] No candidates passed all criteria - the map shows only the zones.")

    plugins.Fullscreen().add_to(m)
    plugins.MousePosition().add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(str(output_html))


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 2 - PyQGIS site selection")
    parser.add_argument("--config", help="path to a config JSON (default: config.json next to this script)")
    args = parser.parse_args()
    cfg = load_config(args.config)

    print("=" * 68)
    print("PHASE 2 - AUTOMATED SITE SELECTION (PyQGIS)")
    print("=" * 68)

    app = init_qgis(with_processing=True)
    try:
        summary = run_analysis(cfg)
    finally:
        shutdown_qgis(app)  # layers are already out of scope here

    output_html = Path(cfg["_config_dir"]) / "phase2_site_selection.html"
    print("\n[MAP] Building the Folium quick-look map")
    create_map(cfg, summary, output_html)

    c = summary["counts"]
    print("\n" + "=" * 68)
    print("PHASE 2 COMPLETE")
    print("=" * 68)
    print(f"  QGIS version:            {summary['qgis_version']}")
    print(f"  Analysis CRS:            {summary['analysis_crs_note']}")
    print(f"  Buildings:               {c['total_buildings']:,}")
    print(f"  A  area:                 {c['step_a_area']:,}")
    print(f"  B  near school:          {c['step_b_school']:,}")
    print(f"  C  outside highway zone: {c['step_c_highway']:,}")
    print(f"  D  outside river zone:   {c['step_d_river']:,}")
    print(f"  E  urban intersects:     {c['step_e_urban_intersects']:,}")
    print(f"  E  urban within:         {c['step_e_urban_within']:,}")
    print(f"  FINAL candidates:        {c['final']:,}")
    print(f"  Population proxy:        {summary['population_proxy_total']:.1f} "
          f"(with levels {summary['population_proxy_levels_total']:.1f}; not census)")
    print(f"  Web output:              {summary['_paths']['final_geojson']}")
    print(f"  Summary:                 {summary['_paths']['summary']}")
    print(f"  Map:                     {output_html}")
    print("\n  Next: python3 phase3_showcase.py")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"\n[FATAL] Phase 2 failed: {error}", file=sys.stderr)
        sys.exit(1)
