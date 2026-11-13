#!/usr/bin/env python3
"""Phase 1 - explore the input data on an interactive web map.

Manual QGIS equivalent: add the layers, style them, set up identify pop-ups,
then export with qgis2web. This script does the same automatically.

    STEP 1  Start QGIS (no Processing needed)
    STEP 2  Convert each GeoPackage layer to WGS 84 GeoJSON   (Export > Save Features As...)
            lines/polygons simplified for display (Vector > Geometry Tools > Simplify)
    STEP 3  Prepare the local satellite image for the web     (Raster > Projections > Warp, Translate)
    STEP 4  Shut QGIS down cleanly
    STEP 5  Build the Folium map: basemaps, layers, tooltips, pop-ups, legend

Run:  python3 phase1_webmap.py   [--config my_town.json]
Output: phase1_webmap.html (+ web_assets/satellite_overlay.png)
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import tempfile
from pathlib import Path

from site_common import (
    existing_fields,
    normalize_for_leaflet,
    geojson_property_names,
    load_config,
    make_base_map,
    project_path,
    require_folium,
    web_simplify_m,
)
from qgis_common import (
    wgs84,
    ConsoleFeedback,
    extent_in_wgs84,
    init_qgis,
    load_vector,
    save_vector,
    set_geojson_precision,
    shutdown_qgis,
    simplify_layer,
)
from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject, QgsRectangle

# ---------------------------------------------------------------------------
# Layer styles and pop-up fields (presentation only - analysis settings live
# in config.json). Fields that are missing in your data are skipped
# automatically, so this list can be generous.
# ---------------------------------------------------------------------------
LAYER_STYLES = {
    "buildings": {
        "name": "🏘️ Buildings", "color": "#e74c3c", "weight": 0.8, "fillOpacity": 0.45, "show": True,
        "tooltip": [("name", "Name"), ("building", "Type"), ("fid", "ID")],
        "popup": [("name", "Name"), ("building", "Building Type"), ("building:levels", "Levels"),
                  ("amenity", "Amenity"), ("addr:street", "Street"), ("addr:city", "City"),
                  ("osm_id", "OSM ID"), ("full_id", "OSM full ID")],
    },
    "schools": {
        "name": "🏫 Schools", "color": "#2980b9", "weight": 2.5, "fillOpacity": 0.6, "show": True,
        "tooltip": [("name", "Name"), ("amenity", "Type")],
        "popup": [("name", "Name"), ("amenity", "Amenity"), ("building:levels", "Levels"),
                  ("building:walls", "Walls"), ("website", "Website"), ("osm_id", "OSM ID"), ("full_id", "OSM full ID")],
    },
    "roads": {
        "name": "🛣️ Roads", "color": "#f39c12", "weight": 2.0, "fillOpacity": 0.0, "show": True,
        "tooltip": [("name", "Name"), ("highway", "Type"), ("ref", "Ref")],
        "popup": [("name", "Name"), ("highway", "Road Type"), ("ref", "Route Ref"), ("maxspeed", "Speed Limit"),
                  ("lanes", "Lanes"), ("surface", "Surface"), ("oneway", "One Way"), ("osm_id", "OSM ID"),
                  ("full_id", "OSM full ID")],
    },
    "rivers": {
        "name": "🌊 Rivers", "color": "#16a085", "weight": 2.5, "fillOpacity": 0.0, "show": True,
        "tooltip": [("name", "Name"), ("waterway", "Type")],
        "popup": [("name", "Name"), ("name_af", "Afrikaans"), ("waterway", "Waterway Type"),
                  ("osm_id", "OSM ID"), ("full_id", "OSM full ID")],
    },
    "urban": {
        "name": "🏙️ Urban Zones", "color": "#8e44ad", "weight": 1.5, "fillOpacity": 0.12, "show": True,
        "tooltip": [("ERF_NO", "Erf No"), ("MIN_REGION", "Region")],
        "popup": [("ERF_NO", "Erf Number"), ("SG_CODE", "SG Code"), ("MIN_REGION", "Min Region"),
                  ("MAJ_REGION", "Major Region"), ("AREA_TABLE", "Area Table"), ("X", "Longitude"), ("Y", "Latitude")],
    },
    "water": {
        "name": "💧 Water Bodies", "color": "#3498db", "weight": 1.0, "fillOpacity": 0.45, "show": False,
        "tooltip": [("natural", "Natural"), ("water", "Water Type")],
        "popup": [("natural", "Natural Feature"), ("water", "Water Type"), ("osm_id", "OSM ID"), ("full_id", "OSM full ID")],
    },
    "restaurants": {
        "name": "🍽️ Restaurants", "color": "#e84393", "weight": 1.5, "fillOpacity": 0.5, "show": False,
        "tooltip": [("name", "Name"), ("amenity", "Type"), ("cuisine", "Cuisine")],
        "popup": [("name", "Name"), ("amenity", "Amenity"), ("cuisine", "Cuisine"), ("addr:street", "Street"),
                  ("addr:city", "City"), ("addr:housenumber", "House No"), ("osm_id", "OSM ID"), ("full_id", "OSM full ID")],
    },
}

DEFAULT_CENTER = [-34.02, 20.44]  # Swellendam (QGIS Training Manual data) - used only if nothing loads


# ===========================================================================
# STEP 2 - layers to GeoJSON
# ===========================================================================
def export_layers(cfg: dict) -> tuple[dict, list]:
    """Return ({layer_key: geojson_dict}, [extents in WGS 84])."""
    feedback = ConsoleFeedback(verbose=bool(cfg["analysis"].get("verbose_processing")))
    set_geojson_precision(cfg)
    dataset_dir = project_path(cfg, "dataset_dir")
    geojson_by_layer, extents = {}, []
    # FIX: temporary files go into a TemporaryDirectory that is always removed,
    # instead of _temp_*.geojson files in the project folder.
    with tempfile.TemporaryDirectory(prefix="phase1_") as tmp:
        for key, style in LAYER_STYLES.items():
            layer = load_vector(dataset_dir, key, required=False)
            if layer is None:
                continue
            out = Path(tmp) / f"{key}.geojson"
            # FIX: save_vector() now really reprojects to WGS 84 (options.ct).
            # PERFORMANCE: simplify lines/polygons for the web map only (not buildings by default);
            # fewer vertices = smaller HTML, faster loading on slow connections.
            layer = simplify_layer(layer, web_simplify_m(cfg, key), key, feedback, fix_first=True)
            save_vector(layer, out, "GeoJSON", wgs84())
            with out.open(encoding="utf-8") as handle:
                data = json.load(handle)
            if not data.get("features"):
                print(f"  {style['name']}: no features - skipped")
                continue
            fixed = normalize_for_leaflet(data)
            if fixed:
                print(f"  {style['name']}: {fixed} multi-part feature(s) made Leaflet-safe (GeometryCollection/MultiPoint)")
            geojson_by_layer[key] = data
            # FIX: extent is transformed directly - no need to re-open the GeoJSON.
            extents.append(extent_in_wgs84(layer))
            print(f"  {style['name']}: {layer.featureCount():,} features ({layer.crs().authid()} -> EPSG:4326)")
    return geojson_by_layer, extents


# ===========================================================================
# STEP 3 - satellite GeoTIFF -> web-ready PNG
# ===========================================================================
def prepare_satellite(cfg: dict) -> tuple[Path, list] | None:
    """Warp the GeoTIFF to Web Mercator and save a PNG for Leaflet's ImageOverlay.

    FIX: the original passed the .tif straight to folium. Folium embeds it as
    'image/tiff', which Chrome/Firefox cannot display, and the file can be huge.
    FIX: Leaflet draws in Web Mercator (EPSG:3857). Warping to 3857 first means
    the image pixels line up with the map; only stretching a bounding box (the
    original approach) misaligns rasters that are in a projected CRS.

    Manual QGIS equivalent: Raster > Projections > Warp (EPSG:3857, alpha band),
    then Raster > Conversion > Translate (PNG, Byte, scaled, reduced size).
    """
    sat_path = project_path(cfg, "satellite_image")
    if not sat_path.is_file():
        print(f"  [WARN] {sat_path} not found - no local image overlay")
        return None
    try:
        from osgeo import gdal  # GDAL ships with every QGIS install
    except ImportError:
        print("  [WARN] GDAL Python bindings not found - no local image overlay")
        return None
    gdal.UseExceptions()

    out_dir = project_path(cfg, "web_assets_dir")
    out_dir.mkdir(parents=True, exist_ok=True)
    png_path = out_dir / "satellite_overlay.png"
    warped_path = "/vsimem/satellite_3857.tif"  # in-memory file, nothing left on disk

    src = gdal.Open(str(sat_path))
    print(f"  {sat_path.name}: {src.RasterXSize}x{src.RasterYSize}, {src.RasterCount} band(s)")
    warped = gdal.Warp(warped_path, src, dstSRS="EPSG:3857", dstAlpha=True, resampleAlg="bilinear")

    alpha_band = warped.RasterCount            # dstAlpha adds the alpha band last
    data_bands = alpha_band - 1
    band_list = ([1, 2, 3] if data_bands >= 3 else [1]) + [alpha_band]
    options = {"format": "PNG", "bandList": band_list}
    if warped.GetRasterBand(1).DataType != gdal.GDT_Byte:
        # e.g. 16-bit imagery: stretch each band's min..max to 0..255
        options["outputType"] = gdal.GDT_Byte
        options["scaleParams"] = [[]]
    max_px = int(cfg["web"].get("satellite_max_px", 2048))
    if warped.RasterXSize > max_px:
        options["width"], options["height"] = max_px, 0  # 0 keeps the aspect ratio
    gdal.Translate(str(png_path), warped, **options)

    # Bounds of the warped image, converted from Web Mercator metres to lat/lon.
    gt = warped.GetGeoTransform()
    min_x, max_y = gt[0], gt[3]
    max_x, min_y = min_x + gt[1] * warped.RasterXSize, max_y + gt[5] * warped.RasterYSize
    warped = None  # close the dataset before unlinking
    src = None
    gdal.Unlink(warped_path)

    to_wgs84 = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:3857"), wgs84(), QgsProject.instance())
    ext = to_wgs84.transformBoundingBox(QgsRectangle(min_x, min_y, max_x, max_y))
    bounds = [[ext.yMinimum(), ext.xMinimum()], [ext.yMaximum(), ext.xMaximum()]]
    print(f"  -> {png_path.name} ({png_path.stat().st_size / 1e6:.1f} MB)")
    return png_path, bounds


# ===========================================================================
# STEP 5 - Folium map
# ===========================================================================
def build_map(cfg: dict, geojson_by_layer: dict, extents: list, satellite) -> Path:
    folium, plugins = require_folium()

    if extents:
        min_x = min(e.xMinimum() for e in extents)
        max_x = max(e.xMaximum() for e in extents)
        min_y = min(e.yMinimum() for e in extents)
        max_y = max(e.yMaximum() for e in extents)
        center = [(min_y + max_y) / 2, (min_x + max_x) / 2]
    else:
        center = DEFAULT_CENTER
    print(f"\n[STEP 5] Building the interactive map at ({center[0]:.4f}, {center[1]:.4f})")

    m = make_base_map(cfg, center)  # FIX: OSM + Esri imagery instead of direct Google tiles

    if satellite:
        png_path, bounds = satellite
        folium.raster_layers.ImageOverlay(
            image=str(png_path),  # PNG is embedded - the HTML stays a single portable file
            bounds=bounds,
            name="📡 Satellite Image (local)",
            opacity=float(cfg["web"].get("satellite_opacity", 0.65)),
            interactive=False,
            cross_origin=False,
            zindex=1,
        ).add_to(m)

    legend_rows = []
    for key, data in geojson_by_layer.items():
        style = LAYER_STYLES[key]
        props = geojson_property_names(data)
        # FIX: only ask folium for fields that exist (missing ones raise AssertionError).
        tip_f, tip_a = existing_fields([f for f, _ in style["tooltip"]], [a for _, a in style["tooltip"]], props)
        pop_f, pop_a = existing_fields([f for f, _ in style["popup"]], [a for _, a in style["popup"]], props)
        geom_types = {(f.get("geometry") or {}).get("type") for f in data["features"]}
        is_line = bool(geom_types) and geom_types <= {"LineString", "MultiLineString"}

        folium.GeoJson(
            data,
            name=style["name"],
            # FIX: every value is bound as a default argument. The original bound
            # only the colour in highlight_function, so weight/opacity came from
            # the LAST layer in the loop (late binding of `cfg`).
            style_function=lambda f, c=style["color"], w=style["weight"], o=style["fillOpacity"]: {
                "color": c, "weight": w, "fillColor": c, "fillOpacity": o,
            },
            highlight_function=lambda f, w=style["weight"], o=style["fillOpacity"]: {
                "weight": max(w + 2, 4), "color": "#ffff00", "fillOpacity": min(o + 0.2, 0.8),
            },
            tooltip=folium.GeoJsonTooltip(fields=tip_f, aliases=tip_a, localize=True, sticky=False,
                                          max_width=300) if tip_f else None,
            popup=folium.GeoJsonPopup(fields=pop_f, aliases=pop_a, localize=True, max_width=350) if pop_f else None,
            zoom_on_click=True,
            show=style["show"],
        ).add_to(m)

        swatch = ("width:24px;height:3px" if is_line else "width:14px;height:14px;opacity:0.7")
        label = html.escape(style["name"].split(" ", 1)[-1])
        legend_rows.append(
            f'<div style="display:flex;align-items:center;margin:3px 0">'
            f'<span style="display:inline-block;{swatch};border-radius:2px;background:{style["color"]};'
            f'margin-right:8px"></span><span>{label}</span></div>'
        )

    plugins.Fullscreen().add_to(m)
    plugins.MousePosition().add_to(m)

    # FIX: the legend is generated from the layers that were actually loaded.
    legend_html = f"""
    <div style="position:fixed;bottom:24px;right:24px;z-index:9999;background:rgba(255,255,255,0.92);
         border-radius:10px;padding:12px 14px;font:12px system-ui,'Segoe UI',sans-serif;
         box-shadow:0 4px 16px rgba(0,0,0,0.12);max-width:210px">
      <div style="font-weight:600;font-size:13px;margin-bottom:6px">Legend</div>
      {''.join(legend_rows)}
      <div style="margin-top:6px;padding-top:6px;border-top:1px solid #eee;font-size:10px;color:#777">
        Hover for preview · Click for details</div>
      <div style="font-size:9px;color:#999;margin-top:4px">
        Dataset: QGIS Training Manual · &copy; OpenStreetMap contributors (ODbL)</div>
    </div>"""
    m.get_root().html.add_child(folium.Element(legend_html))
    # Expanded list: always visible, and needs no icon image from the internet (offline-friendly).
    folium.LayerControl(collapsed=False, position="topright").add_to(m)

    output_html = Path(cfg["_config_dir"]) / "phase1_webmap.html"
    m.save(str(output_html))
    return output_html


def collect_inputs(cfg: dict):
    """STEPS 2-3, kept in one function so QGIS layers go out of scope on return."""
    print("\n[STEP 2] Converting dataset layers to WGS 84 GeoJSON")
    geojson_by_layer, extents = export_layers(cfg)
    # QgsRectangle -> plain tuples so no QGIS object outlives QGIS
    extents = [_PlainExtent(e.xMinimum(), e.yMinimum(), e.xMaximum(), e.yMaximum()) for e in extents]
    print("\n[STEP 3] Preparing the satellite image")
    satellite = prepare_satellite(cfg)
    return geojson_by_layer, extents, satellite


class _PlainExtent:
    """Tiny stand-in for QgsRectangle, safe to use after QGIS has exited."""

    def __init__(self, x0, y0, x1, y1):
        self._v = (x0, y0, x1, y1)

    def xMinimum(self): return self._v[0]
    def yMinimum(self): return self._v[1]
    def xMaximum(self): return self._v[2]
    def yMaximum(self): return self._v[3]


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 1 - interactive data web map")
    parser.add_argument("--config", help="path to a config JSON (default: config.json)")
    args = parser.parse_args()
    cfg = load_config(args.config)

    print("=" * 60)
    print("PHASE 1 - DATA EXPLORATION WEB MAP")
    print("=" * 60)
    print("\n[STEP 1] Starting QGIS (headless)")
    app = init_qgis(with_processing=True)  # Processing is used for web simplification
    try:
        geojson_by_layer, extents, satellite = collect_inputs(cfg)
    finally:
        print("\n[STEP 4] Shutting QGIS down")
        shutdown_qgis(app)

    output_html = build_map(cfg, geojson_by_layer, extents, satellite)
    print("\n✅ Phase 1 complete! Open the interactive map:")
    print(f"  → {output_html}")
    print("  💡 Hover for tooltips · click for pop-ups · toggle layers top-right")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"\n[FATAL] Phase 1 failed: {error}", file=sys.stderr)
        sys.exit(1)
