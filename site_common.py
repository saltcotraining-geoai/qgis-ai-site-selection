"""Shared helpers that do NOT need QGIS.

Used by all three phases. Phase 3 and compare_outputs.py only need these,
so they can run in any Python 3 that has folium (no QGIS install required).

Contents
--------
- load_config()       read config.json and fill in defaults for missing keys
- project_path()      turn a relative path from config into an absolute Path
- existing_fields()   keep only popup/tooltip fields that really exist
- add_basemaps()      add licence-friendly basemaps to a folium map
- require_folium()    import folium with a helpful error message
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Defaults. config.json overrides any of these; a missing key falls back here,
# so an old or partial config.json never crashes the scripts.
# ---------------------------------------------------------------------------
DEFAULT_CONFIG: dict = {
    "paths": {
        "dataset_dir": "dataset",
        "analysis_dir": "analysis_data",
        "zones_dir": "analysis_zones",
        "web_assets_dir": "web_assets",
        "satellite_image": "dataset/satellite_image.tif",
        "prepared_dir": "prepared",
    },
    "study_area": {
        "enabled": True,
        "source": "extent",
        "extent_layer": "buildings",
        "urban_filter": "",
        "file": "dataset/study_area.gpkg",
        "aoi_buffer_m": 0,
        "reference_buffer_m": "auto",
        "candidate_layer": "buildings",
        "candidate_relation": "intersects",
    },
    "layers": {
        "buildings": "buildings",
        "schools": "schools",
        "roads": "roads",
        "rivers": "rivers",
        "urban": "urban",
        "water": "water",              # Phase 1 map only
        "restaurants": "restaurants",  # Phase 1 map only
    },
    "fields": {
        "highway": "highway",
        "waterway": "waterway",
        "building_levels": "building:levels",
        "id_candidates": ["osm_id", "full_id", "fid"],
    },
    "analysis": {"analysis_crs": "auto", "buffer_segments": 36, "verbose_processing": False},
    "criteria": {
        "min_area_sqm": 800.0,
        "max_area_sqm": 1200.0,
        "school_distance_m": 1000.0,
        "highway_exclusion_m": 100.0,
        "main_highway_classes": [
            "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
        ],
        "river_exclusion_m": 300.0,
        "river_classes": [],       # empty = every waterway
        "urban_relation": "intersects",
    },
    "population": {"sqm_per_person": 30.0, "default_levels": 1.0},
    "performance": {
        "simplify_analysis": {"enabled": True, "tolerance_m": 1.0, "layers": ["roads", "rivers", "urban"]},
        "simplify_web": {"enabled": True, "tolerance_m": 2.0, "exclude": ["buildings"]},
        "geojson_precision": 6,
    },
    "scoring": {
        "school": {"weight": 0.50, "zero_at_m": 1000.0, "one_at_m": 0.0},
        "highway": {"weight": 0.25, "zero_at_m": 100.0, "one_at_m": 500.0},
        "river": {"weight": 0.25, "zero_at_m": 300.0, "one_at_m": 1000.0},
    },
    "web": {
        "basemaps": ["osm", "esri_imagery"],
        "satellite_max_px": 2048,
        "satellite_opacity": 0.65,
        "zoom_start": 15,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively copy `override` onto `base`. Keys starting with '_' are notes."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key.startswith("_"):
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def class_filter_expression(field: str, classes) -> str | None:
    """QGIS expression that keeps only these attribute classes, e.g. "highway" IN ('primary','trunk').

    None when no classes are given (= keep everything). Used for the roads and
    rivers layers, so the analysis buffers only the features a rule is about.
    """
    classes = [str(c) for c in (classes or [])]
    if not classes:
        return None
    quoted = ",".join("'" + c.replace("'", "''") + "'" for c in classes)
    return f'"{field}" IN ({quoted})'


def load_config(path: str | os.PathLike | None = None) -> dict:
    """Load config.json (or $SITESEL_CONFIG, or an explicit path) merged with defaults."""
    config_path = Path(path or os.environ.get("SITESEL_CONFIG") or PROJECT_DIR / "config.json")
    if not config_path.is_file():
        print(f"[WARN] {config_path} not found - using built-in defaults.")
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["_config_dir"] = str(PROJECT_DIR)
        return cfg
    with config_path.open("r", encoding="utf-8") as handle:
        user_cfg = json.load(handle)
    cfg = _deep_merge(DEFAULT_CONFIG, user_cfg)
    # Relative paths in the config are resolved against the config's own folder.
    cfg["_config_dir"] = str(config_path.resolve().parent)
    cfg["_config_file"] = str(config_path.resolve())
    return cfg


def analysis_simplify_m(cfg: dict, layer_key: str) -> float | None:
    """Simplification tolerance (m) for one analysis layer, or None when it is not simplified."""
    s = cfg.get("performance", {}).get("simplify_analysis", {})
    if s.get("enabled") and layer_key in s.get("layers", []) and float(s.get("tolerance_m", 0)) > 0:
        return float(s["tolerance_m"])
    return None


def web_simplify_m(cfg: dict, layer_key: str) -> float | None:
    """Simplification tolerance (m) for a web-map copy, or None (disabled / excluded layer)."""
    s = cfg.get("performance", {}).get("simplify_web", {})
    if s.get("enabled") and layer_key not in s.get("exclude", []) and float(s.get("tolerance_m", 0)) > 0:
        return float(s["tolerance_m"])
    return None


_WARNED: set = set()


def _warn_once(message: str) -> None:
    if message not in _WARNED:
        _WARNED.add(message)
        print(f"[WARN] {message}")


def raw_dataset_dir(cfg: dict) -> Path:
    """The original input folder (paths.dataset_dir). Only Phase 0 reads it directly."""
    base = Path(cfg.get("_config_dir", PROJECT_DIR))
    return (base / cfg["paths"]["dataset_dir"]).resolve()


def prepared_fingerprint(cfg: dict) -> dict:
    """The settings Phase 0 depends on; stored with the prepared data to detect stale data."""
    return {
        "study_area": {k: v for k, v in cfg.get("study_area", {}).items() if not k.startswith("_")},
        "analysis_crs": cfg.get("analysis", {}).get("analysis_crs", "auto"),
        "raw_dataset_dir": str(raw_dataset_dir(cfg)),
    }


def project_path(cfg: dict, key: str) -> Path:
    """Absolute Path for cfg['paths'][key], relative to the config file's folder.

    'dataset_dir' points to the PREPARED data (Phase 0 output) when the study
    area is enabled and Phase 0 has run - so every phase analyses the same
    reprojected, fixed and clipped layers without any change to its code.
    Falls back to the raw data with a warning if Phase 0 has not run yet.
    """
    base = Path(cfg.get("_config_dir", PROJECT_DIR))
    if key == "dataset_dir" and cfg.get("study_area", {}).get("enabled"):
        prepared = (base / cfg["paths"].get("prepared_dir", "prepared")).resolve()
        summary = prepared / "prepare_summary.json"
        if summary.is_file():
            stored = json.loads(summary.read_text(encoding="utf-8")).get("fingerprint")
            if stored != prepared_fingerprint(cfg):
                _warn_once("study_area / analysis_crs changed since Phase 0 ran - re-run phase0_prepare_data.py. "
                           "Using the existing prepared data for now.")
            return prepared
        _warn_once("study_area is enabled but Phase 0 has not run yet - using the RAW data. "
                   "Run: python3 phase0_prepare_data.py")
    return (base / cfg["paths"][key]).resolve()


def existing_fields(fields: list[str], aliases: list[str], available) -> tuple[list[str], list[str]]:
    """Keep only (field, alias) pairs whose field exists in `available`.

    folium.GeoJsonTooltip / GeoJsonPopup raise an AssertionError when asked for a
    field that the data does not contain, so we filter first. OSM-derived data
    often differs between downloads (e.g. 'name_af' or 'building:walls' missing).
    """
    available = set(available)
    kept = [(f, a) for f, a in zip(fields, aliases) if f in available]
    return [f for f, _ in kept], [a for _, a in kept]


def geojson_property_names(geojson: dict) -> set[str]:
    """Union of property names over all features of a GeoJSON FeatureCollection."""
    names: set[str] = set()
    for feature in geojson.get("features", []):
        names.update((feature.get("properties") or {}).keys())
    return names


def _flatten_parts(geom: dict) -> dict:
    """All simple parts of a geometry, grouped as {'polygons': [...], 'lines': [...], 'points': [...]}."""
    parts = {"polygons": [], "lines": [], "points": []}
    gtype = (geom or {}).get("type")
    coords = (geom or {}).get("coordinates")
    if gtype == "Polygon":
        parts["polygons"].append(coords)
    elif gtype == "MultiPolygon":
        parts["polygons"].extend(coords)
    elif gtype == "LineString":
        parts["lines"].append(coords)
    elif gtype == "MultiLineString":
        parts["lines"].extend(coords)
    elif gtype == "Point":
        parts["points"].append(coords)
    elif gtype == "MultiPoint":
        parts["points"].extend(coords)
    elif gtype == "GeometryCollection":
        for member in geom.get("geometries") or []:  # nested collections too
            sub = _flatten_parts(member)
            for key in parts:
                parts[key].extend(sub[key])
    return parts


def normalize_for_leaflet(geojson: dict) -> int:
    """Make every feature ONE Leaflet shape, in place. Returns how many features changed.

    FIX: Leaflet turns a GeometryCollection or a MultiPoint into a *group* of
    shapes. Leaflet 1.9's tooltip code expects a single shape, so the map's
    script crashed while adding the layer ("t.getElement is not a function") -
    and everything after it, including the layer control, never ran. Hovering the
    group's parts also failed ("layer.feature is undefined").
    Rules (no attribute is lost):
      GeometryCollection -> MultiPolygon if it has polygon parts (stray lines/points
                            from digitising or Fix Geometries are dropped),
                            else MultiLineString, else one Point feature per point
      MultiPoint         -> one Point feature per point (same attributes)
    GUI equivalent: Vector > Geometry Tools > Multipart to Singleparts, or
    'Collect geometries' after removing non-polygon parts.
    """
    changed = 0
    out = []
    for feature in geojson.get("features", []):
        geom = feature.get("geometry") or {}
        gtype = geom.get("type")
        if gtype not in ("GeometryCollection", "MultiPoint"):
            out.append(feature)
            continue
        changed += 1
        parts = _flatten_parts(geom)
        if parts["polygons"]:
            out.append({**feature, "geometry": {"type": "MultiPolygon", "coordinates": parts["polygons"]}})
        elif parts["lines"]:
            out.append({**feature, "geometry": {"type": "MultiLineString", "coordinates": parts["lines"]}})
        else:
            for point in parts["points"]:
                out.append({**feature, "geometry": {"type": "Point", "coordinates": point}})
    geojson["features"] = out
    return changed


# Old name kept so existing calls keep working.
explode_geometry_collections = normalize_for_leaflet


def require_folium():
    """Import folium + plugins, or stop with installation instructions."""
    try:
        import folium
        from folium import plugins
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise SystemExit(
            "Folium is required. Install it into the Python you run this script with:\n"
            "    python3 -m pip install folium\n"
            "(On Windows/OSGeo4W use the 'OSGeo4W Shell' and run: python -m pip install folium)"
        ) from exc
    return folium, plugins


# Basemaps that may be used in teaching material with attribution.
# NOTE: direct Google tile URLs (mt1.google.com) are NOT used - Google's terms
# do not allow that kind of direct tile access outside their own APIs.
BASEMAPS = {
    "osm": {
        "tiles": "OpenStreetMap",
        "attr": None,
        "name": "OpenStreetMap",
    },
    "esri_imagery": {
        "tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attr": "Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community",
        "name": "Esri World Imagery",
    },
}


def make_base_map(cfg: dict, center: list[float], **map_kwargs):
    """Create a folium.Map with the basemaps listed in cfg['web']['basemaps']."""
    folium, _ = require_folium()
    print(f"  folium {getattr(folium, '__version__', '?')}")  # recorded in the log: map behaviour differs between versions
    keys = [k for k in cfg["web"].get("basemaps", ["osm"]) if k in BASEMAPS] or ["osm"]
    first = BASEMAPS[keys[0]]
    # FIX: the same pattern as the original scripts, which works in every folium
    # version: the FIRST basemap is created by folium.Map itself, the others are
    # added as extra base layers. (An empty map plus a base layer flagged
    # show=False can raise a JavaScript error in some folium versions; folium
    # writes the layer control last, so the error made the control disappear.)
    m = folium.Map(
        location=center,
        zoom_start=cfg["web"].get("zoom_start", 15),
        tiles=first["tiles"],
        attr=first["attr"],
        control_scale=True,
        **map_kwargs,
    )
    for key in keys[1:]:
        spec = BASEMAPS[key]
        folium.TileLayer(
            tiles=spec["tiles"],
            attr=spec["attr"],
            name=spec["name"],
            overlay=False,
            control=True,
        ).add_to(m)
    return m
