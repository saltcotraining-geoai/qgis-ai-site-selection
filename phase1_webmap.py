import os
import sys
import json

from qgis.core import (
    QgsApplication, QgsVectorLayer, QgsVectorFileWriter,
    QgsCoordinateReferenceSystem, QgsProject, QgsRasterLayer
)
import folium
from folium import plugins

QgsApplication.setPrefixPath("/usr", True)
qgs_app = QgsApplication([], False)
qgs_app.initQgis()

current_folder = os.path.dirname(os.path.abspath(__file__))
dataset_dir = os.path.join(current_folder, "dataset")
crs_4326 = QgsCoordinateReferenceSystem("EPSG:4326")

# ─── Layer Configuration ──────────────────────────────────────────
# Each layer gets: visible fields for popup, tooltip fields, colors, styles
# Colors chosen to be maximally distinguishable across the palette.

layers_config = {
    "buildings": {
        "name": "🏘️ Buildings",
        "color": "#e74c3c", "weight": 0.8, "fillOpacity": 0.45,
        "show": True,
        "tooltip_fields": ["name", "building", "fid"],
        "tooltip_aliases": ["Name", "Type", "ID"],
        "popup_fields": ["name", "building", "building:levels", "amenity",
                         "addr:street", "addr:city", "full_id"],
        "popup_aliases": ["Name", "Building Type", "Levels", "Amenity",
                          "Street", "City", "OSM ID"]
    },
    "schools": {
        "name": "🏫 Schools",
        "color": "#2980b9", "weight": 2.5, "fillOpacity": 0.6,
        "show": True,
        "tooltip_fields": ["name", "amenity"],
        "tooltip_aliases": ["Name", "Type"],
        "popup_fields": ["name", "amenity", "building:levels",
                         "building:walls", "website", "full_id"],
        "popup_aliases": ["Name", "Amenity", "Levels",
                          "Walls", "Website", "OSM ID"]
    },
    "roads": {
        "name": "🛣️ Roads",
        "color": "#f39c12", "weight": 2.0, "fillOpacity": 0.0,
        "show": True,
        "tooltip_fields": ["name", "highway", "ref"],
        "tooltip_aliases": ["Name", "Type", "Ref"],
        "popup_fields": ["name", "highway", "ref", "maxspeed",
                         "lanes", "surface", "oneway", "full_id"],
        "popup_aliases": ["Name", "Road Type", "Route Ref", "Speed Limit",
                          "Lanes", "Surface", "One Way", "OSM ID"]
    },
    "rivers": {
        "name": "🌊 Rivers",
        "color": "#16a085", "weight": 2.5, "fillOpacity": 0.0,
        "show": True,
        "tooltip_fields": ["name", "waterway"],
        "tooltip_aliases": ["Name", "Type"],
        "popup_fields": ["name", "name_af", "waterway", "full_id"],
        "popup_aliases": ["Name", "Afrikaans", "Waterway Type", "OSM ID"]
    },
    "urban": {
        "name": "🏙️ Urban Zones",
        "color": "#8e44ad", "weight": 1.5, "fillOpacity": 0.12,
        "show": True,
        "tooltip_fields": ["ERF_NO", "MIN_REGION"],
        "tooltip_aliases": ["Erf No", "Region"],
        "popup_fields": ["ERF_NO", "SG_CODE", "MIN_REGION", "MAJ_REGION",
                         "AREA_TABLE", "X", "Y"],
        "popup_aliases": ["Erf Number", "SG Code", "Min Region", "Major Region",
                          "Area Table", "Longitude", "Latitude"]
    },
    "water": {
        "name": "💧 Water Bodies",
        "color": "#3498db", "weight": 1.0, "fillOpacity": 0.45,
        "show": False,
        "tooltip_fields": ["natural", "water"],
        "tooltip_aliases": ["Natural", "Water Type"],
        "popup_fields": ["natural", "water", "full_id"],
        "popup_aliases": ["Natural Feature", "Water Type", "OSM ID"]
    },
    "restaurants": {
        "name": "🍽️ Restaurants",
        "color": "#e84393", "weight": 1.5, "fillOpacity": 0.5,
        "show": False,
        "tooltip_fields": ["name", "amenity", "cuisine"],
        "tooltip_aliases": ["Name", "Type", "Cuisine"],
        "popup_fields": ["name", "amenity", "cuisine", "addr:street",
                         "addr:city", "addr:housenumber", "full_id"],
        "popup_aliases": ["Name", "Amenity", "Cuisine", "Street",
                          "City", "House No", "OSM ID"]
    }
}

def load_layer(name):
    path = os.path.join(dataset_dir, f"{name}.gpkg")
    uri = f"{path}|layername={name}"
    layer = QgsVectorLayer(uri, name, "ogr")
    if not layer.isValid():
        print(f"[WARN] Failed to load {name}")
        return None
    return layer

def layer_to_geojson(layer, output_path):
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GeoJSON"
    options.fileEncoding = "UTF-8"
    options.targetCrs = crs_4326
    transform_context = QgsProject.instance().transformContext()
    error = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, output_path, transform_context, options
    )
    return error[0] == QgsVectorFileWriter.NoError

def get_popup_html(fields, aliases, props):
    rows = ""
    for f, a in zip(fields, aliases):
        val = props.get(f)
        if val is None or val == "" or val == "NULL":
            val = "—"
        rows += f"<tr><td style='font-weight:500;color:#555;padding:2px 8px 2px 0;white-space:nowrap'>{a}</td><td style='color:#1a1a2e;padding:2px 0'>{val}</td></tr>"
    return f"<table style='font:12px/1.5 Inter,sans-serif;border-collapse:collapse'>{rows}</table>"


print("Loading dataset layers...")
geojson_files = {}
for name, cfg in layers_config.items():
    layer = load_layer(name)
    if not layer:
        continue
    geojson_path = os.path.join(current_folder, f"_temp_{name}.geojson")
    if layer_to_geojson(layer, geojson_path):
        geojson_files[name] = geojson_path
        print(f"  {cfg['name']}: {layer.featureCount():,} features converted")
    else:
        print(f"  {name}: FAILED to convert")

print("Loading satellite image...")
sat_path = os.path.join(dataset_dir, "satellite_image.tif")
sat_layer = QgsRasterLayer(sat_path, "satellite_image")
if sat_layer.isValid():
    print(f"  satellite_image.tif loaded: {sat_layer.width()}x{sat_layer.height()}")
    sat_extent = sat_layer.extent()
    sat_bounds = [
        [sat_extent.yMinimum(), sat_extent.xMinimum()],
        [sat_extent.yMaximum(), sat_extent.xMaximum()]
    ]
else:
    sat_layer = None
    sat_bounds = None
    print("  [WARN] Could not load satellite_image.tif")

all_extents = []
for name in layers_config:
    path = os.path.join(current_folder, f"_temp_{name}.geojson")
    if os.path.exists(path):
        layer = QgsVectorLayer(path, name, "ogr")
        if layer.isValid():
            ext = layer.extent()
            all_extents.append(ext)

if all_extents:
    min_x = min(e.xMinimum() for e in all_extents)
    max_x = max(e.xMaximum() for e in all_extents)
    min_y = min(e.yMinimum() for e in all_extents)
    max_y = max(e.yMaximum() for e in all_extents)
    center_lat = (min_y + max_y) / 2
    center_lon = (min_x + max_x) / 2
else:
    center_lat, center_lon = -34.02, 20.44

print(f"\nBuilding interactive map at ({center_lat:.4f}, {center_lon:.4f})...")

mymap = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=15,
    tiles="OpenStreetMap",
    control_scale=True
)

folium.TileLayer(
    tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
    attr="Google Satellite",
    name="🛰️ Google Satellite",
    overlay=False,
    control=True
).add_to(mymap)

if sat_bounds:
    folium.raster_layers.ImageOverlay(
        image=sat_path,
        bounds=sat_bounds,
        name="📡 Satellite Image (local)",
        overlay=True,
        opacity=0.65,
        interactive=True,
        cross_origin=False,
        zindex=1
    ).add_to(mymap)

# ─── Add each layer with tooltips + popups ────────────────────────
for name, cfg in layers_config.items():
    geojson_path = os.path.join(current_folder, f"_temp_{name}.geojson")
    if not os.path.exists(geojson_path):
        continue
    with open(geojson_path) as f:
        data = json.load(f)
    if not data.get("features"):
        os.remove(geojson_path)
        continue

    fc = data["features"]

    # Build a lookup of properties by feature id or index for popups
    # We use a GeoJsonPopup with all fields + a custom HTML renderer
    popup_fields = cfg["popup_fields"]
    popup_aliases = cfg["popup_aliases"]
    tooltip_fields = cfg["tooltip_fields"]
    tooltip_aliases = cfg["tooltip_aliases"]

    gj = folium.GeoJson(
        data,
        name=cfg["name"],
        style_function=lambda f, c=cfg["color"], w=cfg["weight"], o=cfg["fillOpacity"]: {
            "color": c,
            "weight": w,
            "fillColor": c,
            "fillOpacity": o if f["geometry"]["type"] != "LineString" else 0.0
        },
        highlight_function=lambda f, c=cfg["color"]: {
            "weight": max(cfg["weight"] + 2, 4),
            "color": "#ffff00",
            "fillOpacity": min(cfg["fillOpacity"] + 0.2, 0.8)
        },
        tooltip=folium.GeoJsonTooltip(
            fields=tooltip_fields,
            aliases=tooltip_aliases,
            localize=True,
            sticky=False,
            labels=True,
            style="""
                font-size: 12px;
                font-family: 'Inter', 'Segoe UI', sans-serif;
                font-weight: 500;
                background: rgba(255,255,255,0.95);
                border: 1px solid #ddd;
                border-radius: 6px;
                padding: 6px 10px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            """,
            max_width=300,
        ),
        popup=folium.GeoJsonPopup(
            fields=popup_fields,
            aliases=popup_aliases,
            localize=True,
            style="""
                font-family: 'Inter', 'Segoe UI', sans-serif;
                font-size: 13px;
                line-height: 1.5;
            """,
            max_width=350,
        ),
        zoom_on_click=True,
        show=cfg["show"]
    ).add_to(mymap)

plugins.Fullscreen().add_to(mymap)
plugins.MousePosition().add_to(mymap)

# ─── Legend / Layer Info Control ──────────────────────────────────
legend_html = """
<div style="
    position: fixed; bottom: 24px; right: 24px; z-index: 9999;
    background: rgba(255,255,255,0.92);
    backdrop-filter: blur(8px);
    border-radius: 10px;
    padding: 14px 16px;
    font: 12px 'Inter', 'Segoe UI', sans-serif;
    box-shadow: 0 4px 16px rgba(0,0,0,0.12);
    border: 1px solid rgba(0,0,0,0.06);
    max-width: 200px;
">
    <div style="font-weight:600;font-size:13px;margin-bottom:6px;color:#1a1a2e">
        🗺️ Legend
    </div>
    <div style="display:flex;align-items:center;margin:3px 0">
        <span style="display:inline-block;width:14px;height:14px;border-radius:3px;
            background:#e74c3c;margin-right:8px;opacity:0.8"></span>
        <span>Buildings</span>
    </div>
    <div style="display:flex;align-items:center;margin:3px 0">
        <span style="display:inline-block;width:14px;height:14px;border-radius:3px;
            background:#2980b9;margin-right:8px;opacity:0.8"></span>
        <span>Schools</span>
    </div>
    <div style="display:flex;align-items:center;margin:3px 0">
        <span style="display:inline-block;width:24px;height:3px;border-radius:2px;
            background:#f39c12;margin-right:8px"></span>
        <span>Roads</span>
    </div>
    <div style="display:flex;align-items:center;margin:3px 0">
        <span style="display:inline-block;width:24px;height:3px;border-radius:2px;
            background:#16a085;margin-right:8px"></span>
        <span>Rivers</span>
    </div>
    <div style="display:flex;align-items:center;margin:3px 0">
        <span style="display:inline-block;width:14px;height:14px;border-radius:3px;
            background:#8e44ad;margin-right:8px;opacity:0.5"></span>
        <span>Urban Zones</span>
    </div>
    <div style="display:flex;align-items:center;margin:3px 0">
        <span style="display:inline-block;width:14px;height:14px;border-radius:3px;
            background:#3498db;margin-right:8px;opacity:0.6"></span>
        <span>Water</span>
    </div>
    <div style="display:flex;align-items:center;margin:3px 0">
        <span style="display:inline-block;width:14px;height:14px;border-radius:3px;
            background:#e84393;margin-right:8px;opacity:0.7"></span>
        <span>Restaurants</span>
    </div>
    <div style="margin-top:6px;padding-top:6px;border-top:1px solid #eee;
        font-size:10px;color:#999">
        Hover for preview · Click for details
    </div>
    <div style="font-size:8px;color:#aaa;margin-top:4px">
        Dataset: QGIS Training Manual · &copy; OSM contributors (ODbL)
    </div>
</div>"""
mymap.get_root().html.add_child(folium.Element(legend_html))

folium.LayerControl(collapsed=True).add_to(mymap)

output_html = os.path.join(current_folder, "phase1_webmap.html")
mymap.save(output_html)

for fname in os.listdir(current_folder):
    if fname.startswith("_temp_") and fname.endswith(".geojson"):
        os.remove(os.path.join(current_folder, fname))

qgs_app.exitQgis()
print(f"\n✅ Phase 1 complete! View your interactive map:")
print(f"  → {output_html}")
print(f"\n  💡 Hover over features for tooltips")
print(f"  💡 Click features for detail popups")
print(f"  💡 Toggle layers with the layer control (top-right)")
