import os
import sys
import json
import math

sys.path.insert(0, '/usr/share/qgis/python')
sys.path.insert(0, '/usr/share/qgis/python/plugins')

from qgis.core import (
    QgsApplication, QgsVectorLayer, QgsVectorFileWriter,
    QgsCoordinateReferenceSystem, QgsProject, QgsProcessingFeedback
)
from qgis.analysis import QgsNativeAlgorithms
import processing
from processing.core.Processing import Processing

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
    if label:
        print(f"  -> {label}")
    return processing.run(alg, params, feedback=fb)

def mem_layer(name):
    return f"memory:{name}"

def count_features(layer):
    return layer.featureCount() if layer else 0

print("=" * 60)
print("  PHASE 2: Automated Site Selection Analysis")
print("=" * 60)

print("\n[1] Loading dataset layers...")
buildings  = load_vector("buildings")
schools    = load_vector("schools")
rivers     = load_vector("rivers")
roads      = load_vector("roads")
urban      = load_vector("urban")
water      = load_vector("water")
print(f"  buildings:  {count_features(buildings)} features")
print(f"  schools:    {count_features(schools)} features")
print(f"  rivers:     {count_features(rivers)} features")
print(f"  roads:      {count_features(roads)} features")
print(f"  urban:      {count_features(urban)} features")

print("\n[2] Reprojecting all layers to UTM 33S (EPSG:32733) for meter-based analysis...")
buildings_utm = run("native:reprojectlayer", {
    'INPUT': buildings, 'TARGET_CRS': crs_utm, 'OUTPUT': mem_layer("buildings_utm")
}, "Reproject buildings")['OUTPUT']

schools_utm = run("native:reprojectlayer", {
    'INPUT': schools, 'TARGET_CRS': crs_utm, 'OUTPUT': mem_layer("schools_utm")
}, "Reproject schools")['OUTPUT']

rivers_utm = run("native:reprojectlayer", {
    'INPUT': rivers, 'TARGET_CRS': crs_utm, 'OUTPUT': mem_layer("rivers_utm")
}, "Reproject rivers")['OUTPUT']

roads_utm = run("native:reprojectlayer", {
    'INPUT': roads, 'TARGET_CRS': crs_utm, 'OUTPUT': mem_layer("roads_utm")
}, "Reproject roads")['OUTPUT']

urban_utm = run("native:reprojectlayer", {
    'INPUT': urban, 'TARGET_CRS': crs_utm, 'OUTPUT': mem_layer("urban_utm")
}, "Reproject urban")['OUTPUT']

print("\n[3] Step A: Filter buildings by area (800 - 1200 sq.m)...")
buildings_with_area = run("native:fieldcalculator", {
    'INPUT': buildings_utm,
    'FIELD_NAME': 'area_sqm',
    'FORMULA': '$area',
    'OUTPUT': mem_layer("buildings_with_area")
}, "Calculate area")['OUTPUT']

candidates = run("native:extractbyexpression", {
    'INPUT': buildings_with_area,
    'EXPRESSION': '"area_sqm" >= 800 AND "area_sqm" <= 1200',
    'OUTPUT': mem_layer("candidates")
}, f"Filter 800-1200 sq.m: {count_features(buildings_with_area)} -> ?")['OUTPUT']
print(f"    {count_features(candidates)} buildings meet size criteria")

print("\n[4] Step B: Within 1000m of schools...")
school_buffer = run("native:buffer", {
    'INPUT': schools_utm,
    'DISTANCE': 1000,
    'SEGMENTS': 36,
    'DISSOLVE': True,
    'OUTPUT': mem_layer("school_buffer")
}, "Create 1000m school buffer")['OUTPUT']

step_b = run("native:extractbylocation", {
    'INPUT': candidates,
    'PREDICATE': [0],
    'INTERSECT': school_buffer,
    'OUTPUT': mem_layer("step_b")
}, f"Select within school buffer: {count_features(candidates)} -> ?")['OUTPUT']
print(f"    {count_features(step_b)} buildings within 1000m of a school")

print("\n[5] Step C: Exclude buildings within 100m of main highways...")
main_highways = run("native:extractbyexpression", {
    'INPUT': roads_utm,
    'EXPRESSION': '"highway" IN (\'motorway\', \'trunk\', \'primary\')',
    'OUTPUT': mem_layer("main_highways")
}, "Filter main highways")['OUTPUT']
print(f"    {count_features(main_highways)} highway segments identified")

highway_buffer = run("native:buffer", {
    'INPUT': main_highways,
    'DISTANCE': 100,
    'SEGMENTS': 36,
    'DISSOLVE': True,
    'OUTPUT': mem_layer("highway_buffer")
}, "Create 100m highway buffer")['OUTPUT']

step_c = run("native:extractbylocation", {
    'INPUT': step_b,
    'PREDICATE': [2],
    'INTERSECT': highway_buffer,
    'OUTPUT': mem_layer("step_c")
}, f"Remove buildings near highways: {count_features(step_b)} -> ?")['OUTPUT']
print(f"    {count_features(step_c)} buildings remain after highway exclusion")

print("\n[6] Step D: Exclude buildings within 300m of rivers...")
river_buffer = run("native:buffer", {
    'INPUT': rivers_utm,
    'DISTANCE': 300,
    'SEGMENTS': 36,
    'DISSOLVE': True,
    'OUTPUT': mem_layer("river_buffer")
}, "Create 300m river buffer")['OUTPUT']

step_d = run("native:extractbylocation", {
    'INPUT': step_c,
    'PREDICATE': [2],
    'INTERSECT': river_buffer,
    'OUTPUT': mem_layer("step_d")
}, f"Remove buildings near rivers: {count_features(step_c)} -> ?")['OUTPUT']
print(f"    {count_features(step_d)} buildings remain after river exclusion")

print("\n[7] Fixing urban zone geometries and selecting within residential zones...")
urban_fixed = run("native:fixgeometries", {
    'INPUT': urban_utm,
    'OUTPUT': mem_layer("urban_fixed")
}, "Fix urban zone geometries")['OUTPUT']
print(f"    Urban zones fixed: {count_features(urban_fixed)} features")

step_e = run("native:extractbylocation", {
    'INPUT': step_d,
    'PREDICATE': [0],
    'INTERSECT': urban_fixed,
    'OUTPUT': mem_layer("step_e")
}, f"Select within urban zones: {count_features(step_d)} -> ?")['OUTPUT']
print(f"    {count_features(step_e)} suitable sites found in urban zones")

print("\n[8] Step F: Calculate population estimates...")
final_utm = run("native:fieldcalculator", {
    'INPUT': step_e,
    'FIELD_NAME': 'pop_estimate',
    'FORMULA': '"area_sqm" / 30',
    'FIELD_TYPE': 0,
    'FIELD_LENGTH': 10,
    'FIELD_PRECISION': 1,
    'OUTPUT': mem_layer("final_utm")
}, "Estimate population (area_sqm / 30)")['OUTPUT']

total_pop = 0
for feat in final_utm.getFeatures():
    total_pop += feat['pop_estimate']
print(f"    Estimated total population: {total_pop:.0f}")
print(f"    Number of suitable sites:   {count_features(final_utm)}")

print("\n[9] Reprojecting final result to EPSG:4326 for web display...")
final_4326 = run("native:reprojectlayer", {
    'INPUT': final_utm, 'TARGET_CRS': crs_4326, 'OUTPUT': mem_layer("final_4326")
})['OUTPUT']

print("[10] Saving results...")
sites_geojson = os.path.join(output_dir, "suitable_sites.geojson")
options = QgsVectorFileWriter.SaveVectorOptions()
options.driverName = "GeoJSON"
options.fileEncoding = "UTF-8"
options.targetCrs = crs_4326
tc = QgsProject.instance().transformContext()
err = QgsVectorFileWriter.writeAsVectorFormatV3(final_4326, sites_geojson, tc, options)
if err[0] == QgsVectorFileWriter.NoError:
    print(f"   -> suitable_sites.geojson saved")
else:
    print(f"   [ERROR] Failed to save GeoJSON: {err}")

print("\n[11] Generating exclusion zone GeoJSON for map visualization...")
excl_highway_4326 = run("native:reprojectlayer", {
    'INPUT': highway_buffer, 'TARGET_CRS': crs_4326, 'OUTPUT': mem_layer("excl_hw_4326")
})['OUTPUT']
excl_river_4326 = run("native:reprojectlayer", {
    'INPUT': river_buffer, 'TARGET_CRS': crs_4326, 'OUTPUT': mem_layer("excl_rv_4326")
})['OUTPUT']
school_zone_4326 = run("native:reprojectlayer", {
    'INPUT': school_buffer, 'TARGET_CRS': crs_4326, 'OUTPUT': mem_layer("sch_zn_4326")
})['OUTPUT']
urban_4326 = run("native:reprojectlayer", {
    'INPUT': urban_fixed, 'TARGET_CRS': crs_4326, 'OUTPUT': mem_layer("urban_4326")
})['OUTPUT']

for lyr, name in [(excl_highway_4326, "exclusion_highway_buffer"),
                    (excl_river_4326, "exclusion_river_buffer"),
                    (school_zone_4326, "school_zone"),
                    (urban_4326, "urban_zone")]:
    out_path = os.path.join(output_dir, f"_{name}.geojson")
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GeoJSON"
    opts.fileEncoding = "UTF-8"
    opts.targetCrs = crs_4326
    QgsVectorFileWriter.writeAsVectorFormatV3(lyr, out_path, tc, opts)

print("\n[12] Building interactive analysis map with Folium...")
try:
    import folium
    from folium import plugins
    import numpy as np
except ImportError:
    print("[ERROR] folium not installed. Run: pip install folium")
    qgs_app.exitQgis()
    sys.exit(1)

# Determine map center
ext = final_4326.extent()
if ext.xMinimum() < ext.xMaximum():
    center = [(ext.yMinimum() + ext.yMaximum()) / 2,
              (ext.xMinimum() + ext.xMaximum()) / 2]
else:
    center = [-34.0248, 20.4415]

m = folium.Map(location=center, zoom_start=15, tiles="OpenStreetMap", control_scale=True)

folium.TileLayer(
    "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
    attr="Google Satellite", name="Google Satellite", overlay=False
).add_to(m)

excl_highway_data = json.load(open(os.path.join(output_dir, "_exclusion_highway_buffer.geojson")))
excl_river_data = json.load(open(os.path.join(output_dir, "_exclusion_river_buffer.geojson")))
school_zone_data = json.load(open(os.path.join(output_dir, "_school_zone.geojson")))
urban_data = json.load(open(os.path.join(output_dir, "_urban_zone.geojson")))

folium.GeoJson(
    school_zone_data,
    name="School Zone (1000m buffer)",
    style_function=lambda f: {"color": "#1f78b4", "weight": 1, "fillColor": "#1f78b4", "fillOpacity": 0.1},
    show=True
).add_to(m)

folium.GeoJson(
    excl_highway_data,
    name="Highway Exclusion (100m buffer)",
    style_function=lambda f: {"color": "#e31a1c", "weight": 1, "fillColor": "#e31a1c", "fillOpacity": 0.15},
    show=True
).add_to(m)

folium.GeoJson(
    excl_river_data,
    name="River Exclusion (300m buffer)",
    style_function=lambda f: {"color": "#33a02c", "weight": 1, "fillColor": "#33a02c", "fillOpacity": 0.15},
    show=True
).add_to(m)

folium.GeoJson(
    urban_data,
    name="Urban Zone",
    style_function=lambda f: {"color": "#6a3d9a", "weight": 1, "fillColor": "#6a3d9a", "fillOpacity": 0.08},
    show=True
).add_to(m)

folium.GeoJson(
    sites_geojson,
    name=" Suitable Sites",
    style_function=lambda f: {
        "color": "#006837", "weight": 2, "fillColor": "#31a354", "fillOpacity": 0.7
    },
    highlight_function=lambda f: {"weight": 4, "color": "#ffff00"},
    tooltip=folium.GeoJsonTooltip(
        fields=["area_sqm", "pop_estimate"],
        aliases=["Area (sq.m):", "Est. Population:"],
        localize=True
    ),
    popup=folium.GeoJsonPopup(
        fields=["area_sqm", "pop_estimate"],
        aliases=["Area (sq.m):", "Est. Population:"]
    ),
    show=True
).add_to(m)

plugins.Fullscreen().add_to(m)
plugins.MousePosition().add_to(m)
folium.LayerControl(collapsed=False).add_to(m)

output_html = os.path.join(output_dir, "phase2_site_selection.html")
m.save(output_html)

for f in os.listdir(output_dir):
    if f.startswith("_") and f.endswith(".geojson"):
        os.remove(os.path.join(output_dir, f))

print(f"\n {'=' * 60}")
print(f"  PHASE 2 COMPLETE")
print(f" {'=' * 60}")
print(f"  Suitable sites found:   {count_features(final_utm)}")
print(f"  Estimated population:   {total_pop:.0f}")
print(f"  GeoJSON:                {sites_geojson}")
print(f"  Interactive web map:    {output_html}")

qgs_app.exitQgis()
