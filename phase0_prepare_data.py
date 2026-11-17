#!/usr/bin/env python3
"""Phase 0 - prepare the data: study area -> CRS -> reproject -> fix -> clip -> fix.

Run this FIRST. Every later phase reads the prepared layers automatically
(see site_common.project_path), so the analysis never touches features it does
not need and never mixes coordinate systems.

    STEP 1  Find the raw inputs (every GeoPackage in paths.dataset_dir; originals untouched)
    STEP 2  Build the study area (AOI)                       (Extract Layer Extent / Dissolve / your polygon)
    STEP 3  Choose ONE metric CRS from the study area        (local UTM zone, or analysis.analysis_crs)
    STEP 4  Reproject the AOI and every layer to that CRS    (Reproject Layer)
    STEP 5  Fix geometries                                   (Fix Geometries - Clip fails on invalid input)
    STEP 6  Reference zone = AOI + buffer >= largest rule     (Buffer - avoids the EDGE EFFECT)
    STEP 7  Candidates: SELECT whole footprints in the AOI   (Extract by Location - never cut a footprint)
            Reference layers: CLIP to the reference zone      (Clip)
    STEP 8  Fix again + drop empty geometries                 (Fix Geometries, Extract by Expression)
    STEP 9  Save prepared/<layer>.gpkg + study_area.gpkg + prepare_summary.json

Why the buffer (edge effect): a school or river just OUTSIDE the study area can
decide whether a building INSIDE it qualifies. Clipping reference layers to the
AOI alone would silently change results. With a buffer at least as large as the
largest distance in any rule, clipping cannot change any result: a feature
farther away than every threshold can never make a building pass or fail.

    python3 phase0_prepare_data.py            [--config my_town.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from site_common import load_config, prepared_fingerprint, raw_dataset_dir
from qgis_common import (
    ConsoleFeedback,
    count_vertices,
    init_qgis,
    load_vector,
    output_layer,
    qgis_version,
    run_alg,
    save_vector,
    shutdown_qgis,
)
from phase2_site_selection import choose_analysis_crs, count, extract_by_expression, extract_by_location, PRED_INTERSECT, PRED_WITHIN

DEFAULT_MARGIN_M = 100.0


def largest_rule_distance(cfg: dict) -> float:
    """Largest distance (m) used by ANY rule in Phase 2 or 2b - the minimum safe reference buffer."""
    values = [float(v) for k, v in cfg.get("criteria", {}).items()
              if k.endswith("_m") and isinstance(v, (int, float))]
    for section in (cfg.get("scoring", {}), cfg.get("mce", {}).get("factors", {})):
        for name, f in section.items():
            if isinstance(f, dict) and not name.startswith("_") and f.get("enabled", True):
                values += [float(f[k]) for k in ("zero_at_m", "one_at_m") if isinstance(f.get(k), (int, float))]
    for name, c in cfg.get("mce", {}).get("constraints", {}).items():
        if isinstance(c, dict) and not name.startswith("_") and c.get("enabled", True):
            if isinstance(c.get("distance_m"), (int, float)):
                values.append(float(c["distance_m"]))
    return max(values) if values else 0.0


def alg_layer(alg: str, params: dict, label: str, name: str, feedback):
    return output_layer(run_alg(alg, {**params, "OUTPUT": "TEMPORARY_OUTPUT"}, label, feedback), "OUTPUT", name)


def build_study_area(cfg: dict, raw: dict, feedback):
    """STEP 2 - the study area polygon (one dissolved feature) in its source CRS."""
    sa = cfg["study_area"]
    source = str(sa.get("source", "extent")).lower()
    if source == "file":
        path = (Path(cfg["_config_dir"]) / sa["file"]).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"study_area.file not found: {path}")
        from qgis.core import QgsVectorLayer
        aoi = QgsVectorLayer(str(path), "study_area_input", "ogr")
        if not aoi.isValid() or aoi.featureCount() == 0:
            raise RuntimeError(f"Could not read a polygon from {path}")
        note = f"polygon file {path.name}"
    elif source == "urban":
        aoi = raw["urban"]
        flt = str(sa.get("urban_filter") or "").strip()
        if flt:
            aoi = extract_by_expression(aoi, flt, "urban_filtered", feedback)
            if count(aoi) == 0:
                raise RuntimeError(f"study_area.urban_filter matched no urban polygon: {flt}")
        aoi = alg_layer("native:fixgeometries", {"INPUT": aoi}, "Fix urban geometries for the study area",
                        "urban_fixed", feedback)
        note = "urban polygons" + (f" where {flt}" if flt else "")
    elif source == "extent":
        key = sa.get("extent_layer", "buildings")
        aoi = alg_layer("native:polygonfromlayerextent", {"INPUT": raw[key], "ROUND_TO": 0},
                        f"Extract layer extent of {key}", "extent", feedback)
        note = f"bounding box of {key}"
    else:
        raise ValueError("study_area.source must be 'extent', 'urban' or 'file'.")
    aoi = alg_layer("native:dissolve", {"INPUT": aoi, "FIELD": []}, "Dissolve the study area into one polygon",
                    "study_area", feedback)
    return aoi, note


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 0 - data preparation (study area, CRS, clip, fix)")
    parser.add_argument("--config", help="path to a config JSON (default: config.json)")
    args = parser.parse_args()
    cfg = load_config(args.config)
    if not cfg.get("study_area", {}).get("enabled"):
        print("study_area.enabled is false - nothing to prepare; the phases will read the raw data.")
        return 0

    print("=" * 68 + "\nPHASE 0 - DATA PREPARATION (study area -> CRS -> reproject -> fix -> clip)\n" + "=" * 68)
    app = init_qgis(with_processing=True)
    try:
        summary = prepare(cfg)
    finally:
        shutdown_qgis(app)

    print("\n" + "=" * 68 + "\nPHASE 0 COMPLETE\n" + "=" * 68)
    print(f"  Study area:       {summary['study_area']['note']}  ({summary['study_area']['area_km2']:.1f} km²)")
    print(f"  Analysis CRS:     {summary['analysis_crs_note']}")
    print(f"  Reference buffer: {summary['reference_buffer_m']:g} m (largest rule {summary['largest_rule_m']:g} m + margin)")
    print(f"  {'Layer':12s} {'role':10s} {'features':>17s} {'vertices':>21s}")
    for name, r in summary["layers"].items():
        print(f"  {name:12s} {r['role']:10s} {r['features_raw']:>7,} -> {r['features']:<7,} "
              f"{r['vertices_raw']:>9,} -> {r['vertices']:<9,}")
    print(f"  Prepared data:    {summary['prepared_dir']}")
    print("\n  Next: python3 phase1_webmap.py / phase2_site_selection.py  (they read the prepared data automatically)")
    return 0


def prepare(cfg: dict) -> dict:
    feedback = ConsoleFeedback(verbose=bool(cfg["analysis"].get("verbose_processing")))
    sa = cfg["study_area"]
    root = Path(cfg["_config_dir"])
    raw_dir = raw_dataset_dir(cfg)
    out_dir = (root / cfg["paths"].get("prepared_dir", "prepared")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stale = out_dir / "prepare_summary.json"
    if stale.is_file():
        stale.unlink()  # if this run fails, the phases must not use half-prepared data

    # ------------------------------------------------------------ STEP 1
    print("\n[STEP 1] Raw inputs (originals are not modified)")
    aoi_file = (root / sa.get("file", "")).resolve() if sa.get("source") == "file" else None
    raw = {}
    for path in sorted(raw_dir.glob("*.gpkg")):
        if aoi_file and path.resolve() == aoi_file:
            continue
        layer = load_vector(raw_dir, path.stem, required=False)
        if layer is not None:
            raw[path.stem] = layer
            print(f"  {path.stem:12s} {count(layer):6,} features  {layer.crs().authid()}")
    candidate_key = sa.get("candidate_layer", "buildings")
    if candidate_key not in raw:
        raise FileNotFoundError(f"Candidate layer '{candidate_key}.gpkg' not found in {raw_dir}")

    # ------------------------------------------------------------ STEP 2
    print("\n[STEP 2] Study area")
    aoi, note = build_study_area(cfg, raw, feedback)

    # ------------------------------------------------------------ STEP 3
    analysis_crs, crs_note, lon, lat = choose_analysis_crs(cfg, aoi)
    print(f"\n[STEP 3] Analysis CRS for the study area: {crs_note} (centre {lon:.5f}, {lat:.5f})")

    # ------------------------------------------------------------ STEP 4-5
    print("\n[STEP 4-5] Reproject everything to that CRS and fix geometries")

    def to_crs_fixed(layer, name):
        rep = alg_layer("native:reprojectlayer", {"INPUT": layer, "TARGET_CRS": analysis_crs},
                        f"Reproject {name} to {analysis_crs.authid()}", f"{name}_rep", feedback)
        return alg_layer("native:fixgeometries", {"INPUT": rep}, f"Fix geometries of {name}", name, feedback)

    aoi = to_crs_fixed(aoi, "study_area")
    if float(sa.get("aoi_buffer_m") or 0) > 0:
        aoi = alg_layer("native:buffer", {"INPUT": aoi, "DISTANCE": float(sa["aoi_buffer_m"]), "SEGMENTS": 16,
                                          "DISSOLVE": True}, f"Expand study area by {sa['aoi_buffer_m']} m",
                        "study_area", feedback)
    area_km2 = sum(f.geometry().area() for f in aoi.getFeatures()) / 1e6
    prepared = {name: to_crs_fixed(layer, name) for name, layer in raw.items()}

    # ------------------------------------------------------------ STEP 6
    largest = largest_rule_distance(cfg)
    setting = sa.get("reference_buffer_m", "auto")
    ref_buffer = largest + DEFAULT_MARGIN_M if str(setting).lower() == "auto" else float(setting)
    if ref_buffer < largest:
        print(f"  [WARN] reference_buffer_m {ref_buffer:g} < largest rule distance {largest:g} m: "
              "results near the study-area edge can change (edge effect).")
    print(f"\n[STEP 6] Reference zone = study area + {ref_buffer:g} m (largest rule distance {largest:g} m)")
    reference_zone = alg_layer("native:buffer", {"INPUT": aoi, "DISTANCE": ref_buffer, "SEGMENTS": 16,
                                                 "DISSOLVE": True},
                               f"Buffer study area by {ref_buffer:g} m", "reference_zone", feedback)

    # ------------------------------------------------------------ STEP 7-8
    print("\n[STEP 7-8] Select candidates, clip reference layers, fix again")
    relation = str(sa.get("candidate_relation", "intersects")).lower()
    report = {}
    for name, layer in prepared.items():
        n_raw, v_raw = count(raw[name]), count_vertices(raw[name])
        if name == candidate_key:
            role = "candidate"
            pred = PRED_WITHIN if relation == "within" else PRED_INTERSECT
            done = extract_by_location(layer, aoi, pred, f"{name}_in_study_area", feedback)
        else:
            role = "reference"
            done = alg_layer("native:clip", {"INPUT": layer, "OVERLAY": reference_zone},
                             f"Clip {name} to the reference zone", f"{name}_clipped", feedback)
            done = alg_layer("native:fixgeometries", {"INPUT": done}, f"Fix geometries of clipped {name}",
                             f"{name}_fixed", feedback)
        done = extract_by_expression(done, "$geometry IS NOT NULL AND NOT is_empty($geometry)", name, feedback)
        save_vector(done, out_dir / f"{name}.gpkg", "GPKG")  # layer name = file stem, like the raw data
        report[name] = {"role": role, "features_raw": n_raw, "features": count(done),
                        "vertices_raw": v_raw, "vertices": count_vertices(done), "crs": analysis_crs.authid()}
        print(f"    {name:12s} {role:9s} {n_raw:,} -> {count(done):,} features")
        if role == "candidate" and count(done) == 0:
            raise RuntimeError("No candidate features inside the study area - check study_area settings.")

    # ------------------------------------------------------------ STEP 9
    save_vector(aoi, out_dir / "study_area.gpkg", "GPKG")
    save_vector(reference_zone, out_dir / "reference_zone.gpkg", "GPKG")
    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "qgis_version": qgis_version(),
        "fingerprint": prepared_fingerprint(cfg),
        "study_area": {"note": note, "area_km2": round(area_km2, 3)},
        "analysis_crs": analysis_crs.authid(),
        "analysis_crs_note": crs_note,
        "largest_rule_m": largest,
        "reference_buffer_m": ref_buffer,
        "candidate_layer": candidate_key,
        "candidate_relation": relation,
        "layers": report,
        "raw_dataset_dir": str(raw_dir),
        "prepared_dir": str(out_dir),
        "notes": [
            "Candidate footprints are selected whole (Extract by Location), never cut, so areas stay correct.",
            "Reference layers are clipped to the study area plus a buffer >= the largest rule distance, "
            "so features just outside the study area still count (no edge effect).",
            "Geometries are fixed before clipping (Clip needs valid input) and again after it.",
        ],
    }
    # Written LAST: the other phases switch to the prepared data only when this file exists.
    (out_dir / "prepare_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"\n[FATAL] Phase 0 failed: {error}", file=sys.stderr)
        sys.exit(1)
