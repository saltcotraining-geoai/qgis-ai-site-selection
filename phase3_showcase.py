"""
PHASE 3: Professional Site Selection Showcase Dashboard
Generates a polished single-page HTML dashboard with:
  - Interactive map (Folium + Leaflet)
  - Summary statistics cards
  - Filter funnel visualization
  - Searchable/sortable data table of suitable sites
  - CSV, GeoJSON, and PDF export
  - Print-optimized stylesheet
"""

import os, sys, json, math, csv, io

sys.path.insert(0, '/usr/share/qgis/python')
sys.path.insert(0, '/usr/share/qgis/python/plugins')

from qgis.core import (
    QgsApplication, QgsVectorLayer, QgsVectorFileWriter,
    QgsCoordinateReferenceSystem, QgsProject, QgsProcessingFeedback
)
from qgis.analysis import QgsNativeAlgorithms
import processing
from processing.core.Processing import Processing

import folium
from folium import plugins
import numpy as np

QgsApplication.setPrefixPath("/usr", True)
qgs_app = QgsApplication([], False)
qgs_app.initQgis()
Processing.initialize()
QgsNativeAlgorithms().loadAlgorithms()

current_folder = os.path.dirname(os.path.abspath(__file__))
dataset_dir = os.path.join(current_folder, "dataset")
output_dir = current_folder

crs_4326 = QgsCoordinateReferenceSystem("EPSG:4326")
crs_utm = QgsCoordinateReferenceSystem("EPSG:32733")

class Feedback(QgsProcessingFeedback):
    def pushInfo(self, info): pass
    def pushCommandInfo(self, info): pass
    def pushDebugInfo(self, info): pass
    def reportError(self, error, fatalOnly=False): pass
fb = Feedback()

def load_vector(name):
    path = os.path.join(dataset_dir, f"{name}.gpkg")
    layer = QgsVectorLayer(f"{path}|layername={name}", name, "ogr")
    if not layer.isValid():
        print(f"[ERROR] Failed to load {name}")
        sys.exit(1)
    return layer

def run(alg, params, label=""):
    if label: print(f"  -> {label}")
    return processing.run(alg, params, feedback=fb)

def mem_layer(name):
    return f"memory:{name}"

def count_features(layer):
    return layer.featureCount() if layer else 0

# =====================================================================
# RUN FULL ANALYSIS
# =====================================================================
print("=" * 60)
print("  PHASE 3: Site Selection Showcase Dashboard")
print("=" * 60)

print("\n[1] Loading and reprojecting data...")
buildings  = load_vector("buildings")
schools    = load_vector("schools")
rivers     = load_vector("rivers")
roads      = load_vector("roads")
urban      = load_vector("urban")

buildings_utm = run("native:reprojectlayer", {'INPUT': buildings, 'TARGET_CRS': crs_utm, 'OUTPUT': mem_layer("b_utm")}, "Reproject")['OUTPUT']
schools_utm = run("native:reprojectlayer", {'INPUT': schools, 'TARGET_CRS': crs_utm, 'OUTPUT': mem_layer("s_utm")})['OUTPUT']
rivers_utm = run("native:reprojectlayer", {'INPUT': rivers, 'TARGET_CRS': crs_utm, 'OUTPUT': mem_layer("r_utm")})['OUTPUT']
roads_utm = run("native:reprojectlayer", {'INPUT': roads, 'TARGET_CRS': crs_utm, 'OUTPUT': mem_layer("rd_utm")})['OUTPUT']
urban_utm = run("native:reprojectlayer", {'INPUT': urban, 'TARGET_CRS': crs_utm, 'OUTPUT': mem_layer("u_utm")})['OUTPUT']

total_buildings = count_features(buildings_utm)

print("\n[2] Step A: Filter buildings by area (800-1200 sq.m)...")
buildings_area = run("native:fieldcalculator", {'INPUT': buildings_utm, 'FIELD_NAME': 'area_sqm', 'FORMULA': '$area', 'OUTPUT': mem_layer("b_area")})['OUTPUT']
step_a = run("native:extractbyexpression", {'INPUT': buildings_area, 'EXPRESSION': '"area_sqm" >= 800 AND "area_sqm" <= 1200', 'OUTPUT': mem_layer("step_a")})['OUTPUT']
count_a = count_features(step_a)
print(f"  {count_a} buildings meet size criteria")

print("[3] Step B: Within 1000m of schools...")
school_buf = run("native:buffer", {'INPUT': schools_utm, 'DISTANCE': 1000, 'SEGMENTS': 36, 'DISSOLVE': True, 'OUTPUT': mem_layer("s_buf")})['OUTPUT']
step_b = run("native:extractbylocation", {'INPUT': step_a, 'PREDICATE': [0], 'INTERSECT': school_buf, 'OUTPUT': mem_layer("step_b")})['OUTPUT']
count_b = count_features(step_b)
print(f"  {count_b} within school buffer")

print("[4] Step C: Exclude within 100m of main highways...")
main_hw = run("native:extractbyexpression", {'INPUT': roads_utm, 'EXPRESSION': '"highway" IN (\'motorway\',\'trunk\',\'primary\')', 'OUTPUT': mem_layer("mhw")})['OUTPUT']
hw_buf = run("native:buffer", {'INPUT': main_hw, 'DISTANCE': 100, 'SEGMENTS': 36, 'DISSOLVE': True, 'OUTPUT': mem_layer("hw_buf")})['OUTPUT']
step_c = run("native:extractbylocation", {'INPUT': step_b, 'PREDICATE': [2], 'INTERSECT': hw_buf, 'OUTPUT': mem_layer("step_c")})['OUTPUT']
count_c = count_features(step_c)
print(f"  {count_c} after highway exclusion")

print("[5] Step D: Exclude within 300m of rivers...")
riv_buf = run("native:buffer", {'INPUT': rivers_utm, 'DISTANCE': 300, 'SEGMENTS': 36, 'DISSOLVE': True, 'OUTPUT': mem_layer("riv_buf")})['OUTPUT']
step_d = run("native:extractbylocation", {'INPUT': step_c, 'PREDICATE': [2], 'INTERSECT': riv_buf, 'OUTPUT': mem_layer("step_d")})['OUTPUT']
count_d = count_features(step_d)
print(f"  {count_d} after river exclusion")

print("[6] Step E: Within urban zones...")
urban_fixed = run("native:fixgeometries", {'INPUT': urban_utm, 'OUTPUT': mem_layer("u_fixed")})['OUTPUT']
step_e = run("native:extractbylocation", {'INPUT': step_d, 'PREDICATE': [0], 'INTERSECT': urban_fixed, 'OUTPUT': mem_layer("step_e")})['OUTPUT']
count_e = count_features(step_e)
print(f"  {count_e} suitable sites in urban zones")

print("[7] Step F: Calculate population estimates...")
final_utm = run("native:fieldcalculator", {'INPUT': step_e, 'FIELD_NAME': 'pop_estimate', 'FORMULA': '"area_sqm" / 30', 'FIELD_TYPE': 0, 'FIELD_LENGTH': 10, 'FIELD_PRECISION': 1, 'OUTPUT': mem_layer("final_utm")})['OUTPUT']
total_pop = sum(f['pop_estimate'] for f in final_utm.getFeatures())
print(f"  Estimated total population: {total_pop:.0f}")

print("[8] Reprojecting to EPSG:4326...")
final_4326 = run("native:reprojectlayer", {'INPUT': final_utm, 'TARGET_CRS': crs_4326, 'OUTPUT': mem_layer("final_4326")})['OUTPUT']
school_buf_4326 = run("native:reprojectlayer", {'INPUT': school_buf, 'TARGET_CRS': crs_4326, 'OUTPUT': mem_layer("sb_4326")})['OUTPUT']
hw_buf_4326 = run("native:reprojectlayer", {'INPUT': hw_buf, 'TARGET_CRS': crs_4326, 'OUTPUT': mem_layer("hb_4326")})['OUTPUT']
riv_buf_4326 = run("native:reprojectlayer", {'INPUT': riv_buf, 'TARGET_CRS': crs_4326, 'OUTPUT': mem_layer("rb_4326")})['OUTPUT']
urban_4326 = run("native:reprojectlayer", {'INPUT': urban_fixed, 'TARGET_CRS': crs_4326, 'OUTPUT': mem_layer("u_4326")})['OUTPUT']

# =====================================================================
# SAVE GEOJSON FILES
# =====================================================================
def save_geojson(layer, path):
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GeoJSON"
    opts.fileEncoding = "UTF-8"
    opts.targetCrs = crs_4326
    tc = QgsProject.instance().transformContext()
    err = QgsVectorFileWriter.writeAsVectorFormatV3(layer, path, tc, opts)
    return err[0] == QgsVectorFileWriter.NoError

sites_json = os.path.join(output_dir, "suitable_sites.geojson")
save_geojson(final_4326, sites_json)

# =====================================================================
# BUILD SITES DATA TABLE (extract properties from final layer)
# =====================================================================
sites_data = []
for i, feat in enumerate(final_utm.getFeatures(), 1):
    props = feat.attributes()
    idx_name = final_utm.fields().indexFromName('name')
    idx_area = final_utm.fields().indexFromName('area_sqm')
    idx_pop = final_utm.fields().indexFromName('pop_estimate')
    idx_building = final_utm.fields().indexFromName('building')
    idx_levels = final_utm.fields().indexFromName('building:levels')
    idx_amenity = final_utm.fields().indexFromName('amenity')
    idx_street = final_utm.fields().indexFromName('addr:street')

    name = feat.attribute('name') or feat.attribute('full_id') or f"Site {i}"
    area = round(feat.attribute('area_sqm'), 1) if feat.attribute('area_sqm') else 0
    pop = round(feat.attribute('pop_estimate'), 1) if feat.attribute('pop_estimate') else 0
    btype = feat.attribute('building') or '—'
    levels = feat.attribute('building:levels') or '—'
    amenity = feat.attribute('amenity') or '—'
    street = feat.attribute('addr:street') or '—'

    centroid = feat.geometry().centroid().asPoint()
    lat = round(centroid.y(), 6)
    lon = round(centroid.x(), 6)

    sites_data.append({
        'id': i,
        'name': name,
        'area': area,
        'pop': pop,
        'type': btype,
        'levels': levels,
        'amenity': amenity,
        'street': street,
        'lat': lat,
        'lon': lon
    })

# =====================================================================
# GET MAP CENTER
# =====================================================================
ext = final_4326.extent()
center = [(ext.yMinimum() + ext.yMaximum()) / 2,
          (ext.xMinimum() + ext.xMaximum()) / 2]

# =====================================================================
# BUILD FOLIUM MAP
# =====================================================================
print("[9] Building interactive map...")
m = folium.Map(location=center, zoom_start=15, tiles="OpenStreetMap", control_scale=True, prefer_canvas=True)

folium.TileLayer("https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
                 attr="Google Satellite", name="Satellite", overlay=False).add_to(m)

# Exclusion/analysis zones
with open(sites_json) as f:
    sites_gj_data = json.load(f)

# Add sequential ID to each feature for map-table linking
for idx, feature in enumerate(sites_gj_data['features']):
    feature['properties']['site_id'] = idx + 1

folium.GeoJson(
    sites_gj_data,
    name="Suitable Sites",
    style_function=lambda f: {"color": "#006837", "weight": 2, "fillColor": "#31a354", "fillOpacity": 0.75},
    highlight_function=lambda f: {"weight": 4, "color": "#fdff00"},
    tooltip=folium.GeoJsonTooltip(fields=["site_id", "area_sqm", "pop_estimate"], aliases=["Site #:", "Area (m²):", "Population:"], localize=True),
    popup=folium.GeoJsonPopup(fields=["site_id", "name", "area_sqm", "pop_estimate"], aliases=["Site #:", "Name:", "Area (m²):", "Population:"]),
    on_each_feature="""function(feature, layer) {
        layer.on({
            click: function(e) {
                window.parent.postMessage({type: 'siteSelect', siteId: feature.properties.site_id || 0}, '*');
            }
        });
    }""",
    show=True
).add_to(m)

# Re-read the GeoJSON files for zone overlays
# Since these are memory layers, we need to save them temporarily
temp_dir = output_dir
temp_files = {}
for lyr, key in [(school_buf_4326, "school"), (hw_buf_4326, "highway"), (riv_buf_4326, "river"), (urban_4326, "urban")]:
    p = os.path.join(temp_dir, f"_z_{key}.geojson")
    save_geojson(lyr, p)
    temp_files[key] = p

for key, label, color in [
    ("school", "School Zone (1000m)", "#1f78b4"),
    ("highway", "Highway Exclusion (100m)", "#e31a1c"),
    ("river", "River Exclusion (300m)", "#33a02c"),
    ("urban", "Urban Zone", "#6a3d9a")
]:
    p = temp_files.get(key)
    if p and os.path.exists(p):
        with open(p) as fh:
            data = json.load(fh)
        folium.GeoJson(data, name=label,
            style_function=lambda f, c=color: {"color": c, "weight": 2, "fillColor": c, "fillOpacity": 0.2}
        ).add_to(m)

plugins.Fullscreen().add_to(m)
plugins.MousePosition().add_to(m)

# Layer control for toggling overlays
folium.LayerControl(collapsed=False).add_to(m)

# Custom JS: highlight site when parent sends message (table row click)
folium.Element("""
<script>
(function() {
    var siteMap = null;
    for (var k in window) {
        if (k.indexOf('map_') === 0 && window[k] instanceof L.Map) { siteMap = window[k]; break; }
    }
    if (!siteMap) return;
    window.addEventListener('message', function(e) {
        if (!e.data || e.data.type !== 'highlightSite' || !siteMap) return;
        var target = e.data.siteId;
        siteMap.eachLayer(function(layer) {
            if (layer.feature && layer.feature.properties && layer.feature.properties.site_id) {
                if (layer.feature.properties.site_id === target) {
                    layer.setStyle({weight: 6, color: '#fdff00', fillColor: '#ffd700', fillOpacity: 0.9});
                    layer.bringToFront();
                    layer.openPopup();
                } else {
                    layer.closePopup();
                    layer.setStyle({weight: 2, color: '#006837', fillColor: '#31a354', fillOpacity: 0.75});
                }
            }
        });
    });
})();
</script>
""").add_to(m)

# =====================================================================
# BUILD DASHBOARD HTML
# =====================================================================
print("[10] Building professional dashboard HTML...")

sites_json_str = json.dumps(sites_data)
# Build table rows
table_rows = ""
for s in sites_data:
    table_rows += f"""<tr>
        <td>{s['id']}</td>
        <td>{s['name']}</td>
        <td>{s['type']}</td>
        <td>{s['area']}</td>
        <td>{s['pop']}</td>
        <td>{s['levels']}</td>
        <td>{s['street']}</td>
        <td>{s['lat']}, {s['lon']}</td>
    </tr>\n"""

funnel_data = json.dumps([
    {"label": f"Total Buildings ({total_buildings})", "count": total_buildings, "pct": 100},
    {"label": f"Area 800-1200 m² ({count_a})", "count": count_a, "pct": round(count_a/total_buildings*100, 1) if total_buildings else 0},
    {"label": f"Within 1000m School ({count_b})", "count": count_b, "pct": round(count_b/total_buildings*100, 1) if total_buildings else 0},
    {"label": f"Not near Highway ({count_c})", "count": count_c, "pct": round(count_c/total_buildings*100, 1) if total_buildings else 0},
    {"label": f"Not near River ({count_d})", "count": count_d, "pct": round(count_d/total_buildings*100, 1) if total_buildings else 0},
    {"label": f"In Urban Zone ({count_e})", "count": count_e, "pct": round(count_e/total_buildings*100, 1) if total_buildings else 0}
])

# Get map HTML
map_html = m._repr_html_()

map_height = 500
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Site Selection Analysis Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.datatables.net/1.13.6/css/jquery.dataTables.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<script src="https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Inter', sans-serif; background: #f0f2f5; color: #1a1a2e; }}

.dashboard-header {{
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    color: white; padding: 2rem 2.5rem; position: relative; overflow: hidden;
}}
.dashboard-header::after {{
    content: ''; position: absolute; top: -50%; right: -20%;
    width: 500px; height: 500px; background: radial-gradient(circle, rgba(255,255,255,0.03) 0%, transparent 70%);
    border-radius: 50%;
}}
.header-content {{ position: relative; z-index: 1; display: flex; justify-content: space-between; align-items: center; }}
.header-title h1 {{ font-size: 1.8rem; font-weight: 800; letter-spacing: -0.5px; }}
.header-title h1 i {{ color: #4fc3f7; margin-right: 12px; }}
.header-title p {{ font-size: 0.9rem; color: rgba(255,255,255,0.7); margin-top: 4px; }}
.header-badge {{ background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.15); padding: 0.5rem 1.2rem; border-radius: 50px; font-size: 0.8rem; }}

.stats-row {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem;
    padding: 1.5rem 2.5rem; background: white; border-bottom: 1px solid #e8e8e8;
}}
.stat-card {{
    padding: 1rem 1.2rem; border-radius: 12px; background: #f8f9fc;
    border-left: 4px solid #0f3460; transition: transform 0.2s;
}}
.stat-card:hover {{ transform: translateY(-2px); }}
.stat-card .stat-value {{ font-size: 1.8rem; font-weight: 800; color: #1a1a2e; }}
.stat-card .stat-label {{ font-size: 0.75rem; color: #666; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 2px; }}
.stat-card:nth-child(1) {{ border-left-color: #0f3460; }}
.stat-card:nth-child(2) {{ border-left-color: #1f78b4; }}
.stat-card:nth-child(3) {{ border-left-color: #e31a1c; }}
.stat-card:nth-child(4) {{ border-left-color: #33a02c; }}
.stat-card:nth-child(5) {{ border-left-color: #6a3d9a; }}
.stat-card:nth-child(6) {{ border-left-color: #31a354; }}

.main-content {{
    display: grid; grid-template-columns: 1fr 380px; gap: 1.5rem;
    padding: 1.5rem 2.5rem; max-width: 1600px; margin: 0 auto;
}}
@media (max-width: 1100px) {{
    .main-content {{ grid-template-columns: 1fr; }}
}}

.map-panel {{ background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
.map-panel .map-header {{ padding: 1rem 1.5rem; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; }}
.map-panel .map-header h2 {{ font-size: 1rem; font-weight: 600; }}
.map-panel .map-header h2 i {{ color: #0f3460; margin-right: 8px; }}
.map-container {{ height: {map_height}px; }}

.sidebar {{ display: flex; flex-direction: column; gap: 1.5rem; }}

.funnel-card, .export-card {{
    background: white; border-radius: 12px; padding: 1.5rem; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}}
.funnel-card h3, .export-card h3 {{
    font-size: 0.9rem; font-weight: 600; margin-bottom: 1rem; text-transform: uppercase; letter-spacing: 0.5px; color: #555;
}}
.funnel-step {{
    display: flex; align-items: center; margin-bottom: 10px; gap: 10px;
}}
.funnel-bar-wrap {{ flex: 1; height: 28px; background: #f0f2f5; border-radius: 6px; overflow: hidden; position: relative; }}
.funnel-bar {{ height: 100%; border-radius: 6px; transition: width 0.8s ease; display: flex; align-items: center; justify-content: flex-end; padding-right: 8px; }}
.funnel-bar span {{ font-size: 0.7rem; font-weight: 700; color: white; text-shadow: 0 1px 2px rgba(0,0,0,0.3); }}
.funnel-label {{ min-width: 200px; font-size: 0.78rem; color: #444; }}
.funnel-pct {{ min-width: 40px; text-align: right; font-size: 0.75rem; font-weight: 600; color: #888; }}

.export-buttons {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
.export-btn {{
    padding: 0.7rem 1rem; border: none; border-radius: 8px; font-size: 0.8rem; font-weight: 600;
    cursor: pointer; transition: all 0.2s; display: flex; align-items: center; justify-content: center; gap: 8px;
}}
.export-btn:hover {{ transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }}
.export-btn.csv {{ background: #1f78b4; color: white; }}
.export-btn.geojson {{ background: #33a02c; color: white; }}
.export-btn.pdf {{ background: #e31a1c; color: white; }}
.export-btn.print {{ background: #6a3d9a; color: white; }}

.table-section {{
    padding: 0 2.5rem 2rem; max-width: 1600px; margin: 0 auto;
}}
.table-card {{
    background: white; border-radius: 12px; padding: 1.5rem; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}}
.table-card h3 {{ font-size: 1rem; font-weight: 600; margin-bottom: 1rem; }}
.table-card h3 i {{ color: #0f3460; margin-right: 8px; }}
.table-card .table-info {{ font-size: 0.8rem; color: #888; margin-bottom: 1rem; }}

#sites-table {{ width: 100% !important; font-size: 0.82rem; }}
#sites-table thead th {{ background: #f8f9fc; font-weight: 600; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.3px; color: #555; padding: 10px 8px; border-bottom: 2px solid #e0e0e0; }}
#sites-table tbody td {{ padding: 8px; border-bottom: 1px solid #f0f0f0; vertical-align: middle; }}
#sites-table tbody tr:hover {{ background: #f0f7ff; }}
#sites-table tbody tr.selected {{ background-color: #fff3cd !important; outline: 2px solid #ffc107; }}
#sites-table tbody tr.selected:hover {{ background-color: #ffe8a1 !important; }}

.dataTables_wrapper .dataTables_filter input {{
    border: 1px solid #ddd; border-radius: 6px; padding: 6px 12px; font-size: 0.8rem;
    outline: none; margin-left: 8px;
}}
.dataTables_wrapper .dataTables_filter input:focus {{ border-color: #0f3460; box-shadow: 0 0 0 2px rgba(15,52,96,0.1); }}
.dataTables_wrapper .dataTables_length select {{
    border: 1px solid #ddd; border-radius: 6px; padding: 4px 8px; font-size: 0.8rem;
}}
.dataTables_info {{ font-size: 0.78rem; color: #888; }}
.paginate_button {{ padding: 4px 10px !important; font-size: 0.78rem !important; }}

.footer {{
    text-align: center; padding: 1.5rem; font-size: 0.75rem; color: #999;
    border-top: 1px solid #eee; margin-top: 1rem;
}}

@media print {{
    body {{ background: white; }}
    .dashboard-header {{ background: #1a1a2e !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    .stat-card {{ background: #f8f9fc !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    .funnel-bar {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    .export-buttons {{ display: none; }}
    .dataTables_filter, .dataTables_length, .dataTables_info, .paginate_button {{ display: none !important; }}
    .sidebar {{ break-inside: avoid; }}
}}
</style>
</head>
<body>

<div class="dashboard-header">
    <div class="header-content">
        <div class="header-title">
            <h1><i class="fas fa-map-marked-alt"></i> Site Selection Analysis</h1>
            <p>Automated spatial analysis using QGIS · PyQGIS · Multi-criteria evaluation</p>
        </div>
        <div class="header-badge">
            <i class="fas fa-check-circle" style="color: #4fc3f7;"></i> {count_e} suitable sites identified
        </div>
    </div>
</div>

<div class="stats-row">
    <div class="stat-card"><div class="stat-value">{total_buildings:,}</div><div class="stat-label">Total Buildings</div></div>
    <div class="stat-card"><div class="stat-value">{count_a}</div><div class="stat-label">Size 800-1200 m²</div></div>
    <div class="stat-card"><div class="stat-value">{count_b}</div><div class="stat-label">Within School Zone</div></div>
    <div class="stat-card"><div class="stat-value">{count_c}</div><div class="stat-label">Not Near Highway</div></div>
    <div class="stat-card"><div class="stat-value">{count_d}</div><div class="stat-label">Not Near River</div></div>
    <div class="stat-card"><div class="stat-value" style="color: #31a354;">{count_e}</div><div class="stat-label"> In Urban Zone</div></div>
</div>

<div class="main-content">
    <div class="map-panel">
        <div class="map-header">
            <h2><i class="fas fa-globe"></i> Spatial Analysis Map</h2>
            <span style="font-size:0.75rem;color:#888;"><i class="fas fa-info-circle"></i> Click sites for details · Toggle layers </span>
        </div>
        <div class="map-container">
            {map_html}
        </div>
    </div>

    <div class="sidebar">
        <div class="funnel-card">
            <h3><i class="fas fa-filter"></i> Filter Cascade</h3>
            <div id="funnel-viz"></div>
        </div>

        <div class="export-card">
            <h3><i class="fas fa-download"></i> Export Results</h3>
            <div class="export-buttons">
                <button class="export-btn csv" onclick="exportCSV()"><i class="fas fa-file-csv"></i> CSV</button>
                <button class="export-btn geojson" onclick="exportGeoJSON()"><i class="fas fa-globe"></i> GeoJSON</button>
                <button class="export-btn pdf" onclick="window.print()"><i class="fas fa-file-pdf"></i> PDF</button>
                <button class="export-btn print" onclick="window.print()"><i class="fas fa-print"></i> Print</button>
            </div>
            <div style="margin-top:12px;font-size:0.75rem;color:#999;">
                <i class="fas fa-info-circle"></i> PDF: Use browser Print (Ctrl+P) → "Save as PDF"
            </div>
        </div>
    </div>
</div>

<div class="table-section">
    <div class="table-card">
        <h3><i class="fas fa-list"></i> Suitable Sites Register</h3>
        <div class="table-info">{count_e} sites found · Search, sort, and export below</div>
        <table id="sites-table" class="display">
            <thead>
                <tr>
                    <th>#</th>
                    <th>Name / ID</th>
                    <th>Type</th>
                    <th>Area (m²)</th>
                    <th>Est. Pop.</th>
                    <th>Levels</th>
                    <th>Street</th>
                    <th>Coordinates</th>
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>
    </div>
</div>

<div class="footer">
    <i class="fas fa-tools"></i> Generated with PyQGIS · QGIS 3.44 · Folium
    <br>Dataset: <a href="https://docs.qgis.org/latest/en/docs/training_manual/" target="_blank" style="color:#999;">QGIS Training Manual</a> exercise_data &middot; Data &copy; <a href="https://openstreetmap.org/copyright" target="_blank" style="color:#999;">OpenStreetMap contributors</a> (ODbL)
</div>

<script>
var sitesData = {sites_json_str};

$('#sites-table').DataTable({{
    pageLength: 10,
    lengthMenu: [[5, 10, 25, 50, -1], [5, 10, 25, 50, "All"]],
    order: [[0, 'asc']],
    language: {{ search: "<i class='fas fa-search'></i> Search:", searchPlaceholder: "name, street, type..." }}
}});

var funnelData = {funnel_data};
var funnelColors = ['#0f3460','#1f78b4','#e31a1c','#33a02c','#6a3d9a','#31a354'];
var funnelHtml = '';
funnelData.forEach(function(d, i) {{
    funnelHtml += '<div class="funnel-step">' +
        '<div class="funnel-label">' + d.label + '</div>' +
        '<div class="funnel-bar-wrap"><div class="funnel-bar" style="width:' + d.pct + '%;background:' + funnelColors[i] + '"><span>' + d.count + '</span></div></div>' +
        '<div class="funnel-pct">' + d.pct + '%</div>' +
        '</div>';
}});
document.getElementById('funnel-viz').innerHTML = funnelHtml;

function exportCSV() {{
    var csv = "ID,Name,Type,Area (m²),Est.Population,Levels,Street,Latitude,Longitude\\n";
    sitesData.forEach(function(s) {{
        csv += s.id + ',"' + s.name.replace(/"/g,'""') + '","' + s.type + '",' + s.area + ',' + s.pop + ',"' + s.levels + '","' + s.street + '",' + s.lat + ',' + s.lon + '\\n';
    }});
    var blob = new Blob([csv], {{ type: 'text/csv;charset=utf-8;' }});
    var link = document.createElement('a'); link.href = URL.createObjectURL(blob);
    link.download = 'suitable_sites.csv'; link.click();
}}

// ===== Map-Table Bidirectional Selection =====
var selectedSiteId = null;

// Map feature click → highlight table row
window.addEventListener('message', function(e) {{
    if (e.data && e.data.type === 'siteSelect') {{
        highlightSite(parseInt(e.data.siteId));
    }}
}});

// Table row click → highlight map feature
$('#sites-table tbody').on('click', 'tr', function() {{
    var table = $('#sites-table').DataTable();
    var data = table.row(this).data();
    if (data && data[0]) {{
        highlightSite(parseInt(data[0]));
    }}
}});

function highlightSite(siteId) {{
    if (selectedSiteId) $('#sites-table tbody tr').removeClass('selected');
    selectedSiteId = siteId;
    var table = $('#sites-table').DataTable();
    table.rows().every(function() {{
        if (parseInt(this.data()[0]) === siteId) {{
            $(this.node()).addClass('selected');
            if (this.node()) this.node().scrollIntoView({{behavior: 'smooth', block: 'center'}});
        }}
    }});
    var iframe = document.querySelector('.map-container iframe');
    if (!iframe || !iframe.contentWindow) return;
    var win = iframe.contentWindow;
    var siteMap = win._siteMap;
    if (!siteMap) return;
    siteMap.eachLayer(function(layer) {{
        if (!layer.siteIdx) return;
        if (layer.siteIdx === siteId) {{
            layer.setStyle({{weight: 6, color: '#fdff00', fillColor: '#ffd700', fillOpacity: 0.9}});
            layer.bringToFront();
            layer.openPopup();
        }} else {{
            layer.closePopup();
            layer.setStyle(layer.origStyle || {{weight: 2, color: '#006837', fillColor: '#31a354', fillOpacity: 0.75}});
        }}
    }});
}}

// Assign indices and click handlers to map features
(function trySetup() {{
    var iframe = document.querySelector('.map-container iframe');
    if (!iframe || !iframe.contentWindow) {{ setTimeout(trySetup, 300); return; }}
    var win = iframe.contentWindow;
    if (!win.L || !win.L.Map) {{ setTimeout(trySetup, 500); return; }}
    var siteMap = null;
    for (var k in win) {{
        if (k.indexOf('map_') === 0 && win[k] instanceof win.L.Map) {{ siteMap = win[k]; break; }}
    }}
    if (!siteMap) {{ setTimeout(trySetup, 500); return; }}
    var counter = 0;
    siteMap.eachLayer(function(layer) {{
        if (layer.feature && layer.feature.properties && layer.feature.properties.area_sqm) {{
            counter++;
            layer.siteIdx = counter;
            layer.origStyle = {{weight: 2, color: '#006837', fillColor: '#31a354', fillOpacity: 0.75}};
            layer.off('click');
            layer.on('click', function() {{
                window.postMessage({{type: 'siteSelect', siteId: this.siteIdx}}, '*');
            );
        }}
    }});
    win._siteMap = siteMap;
}})();

function exportGeoJSON() {{
    var features = sitesData.map(function(s) {{
        return {{ "type": "Feature", "properties": {{
            "site_id": s.id, "name": s.name, "type": s.type, "area_sqm": s.area,
            "pop_estimate": s.pop, "levels": s.levels, "street": s.street
        }}, "geometry": {{ "type": "Point", "coordinates": [s.lon, s.lat] }} }};
    }});
    var gj = {{ "type": "FeatureCollection", "features": features }};
    var blob = new Blob([JSON.stringify(gj, null, 2)], {{ type: 'application/geo+json;charset=utf-8;' }});
    var link = document.createElement('a'); link.href = URL.createObjectURL(blob);
    link.download = 'suitable_sites_points.geojson'; link.click();
}}
</script>
</body>
</html>"""

output_html = os.path.join(output_dir, "phase3_dashboard.html")
with open(output_html, 'w') as f:
    f.write(html)

# Clean up temp files
for key in ["school", "highway", "river", "urban"]:
    p = os.path.join(temp_dir, f"_z_{key}.geojson")
    if os.path.exists(p):
        os.remove(p)

qgs_app.exitQgis()

print(f"\n {'=' * 60}")
print(f"  PHASE 3 COMPLETE — Dashboard Ready!")
print(f" {'=' * 60}")
print(f"  Suitable sites:           {count_e}")
print(f"  Estimated population:     {total_pop:.0f}")
print(f"  Dashboard:                phase3_dashboard.html")
print(f"  GeoJSON:                  suitable_sites.geojson")
print(f"\n  Open phase3_dashboard.html in a browser to view the showcase.")
print(f"  Use Ctrl+P → 'Save as PDF' to generate a professional PDF report.")
