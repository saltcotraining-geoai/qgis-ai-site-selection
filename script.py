import os
import sys
import folium
from qgis.core import (
    QgsApplication, 
    QgsVectorLayer, 
    QgsVectorFileWriter, 
    QgsCoordinateReferenceSystem,
    QgsProject
)

# =====================================================================
# SUB-STEP 1A: Start QGIS and Load Your Shapefile
# =====================================================================
QgsApplication.setPrefixPath("/usr", True)
qgis_app = QgsApplication([], False)
qgis_app.initQgis()

current_folder = os.path.dirname(os.path.abspath(__file__))
shapefiles = [f for f in os.listdir(current_folder) if f.endswith('.shp')]

if not shapefiles:
    print("[ERROR] No .shp file found in this folder!")
    qgis_app.exitQgis()
    sys.exit()

target_file_name = shapefiles[0]
shapefile_path = os.path.join(current_folder, target_file_name)
raw_layer = QgsVectorLayer(shapefile_path, "My Shapefile", "ogr")

if not raw_layer.isValid():
    print("[ERROR] Failed to load the shapefile.")
    qgis_app.exitQgis()
    sys.exit()

print(f"Loaded Shapefile successfully: {raw_layer.name()}")


# =====================================================================
# SUB-STEP 1B: Convert Shapefile to Web-Friendly Format (SAFE METHOD)
# =====================================================================
output_geojson_path = os.path.join(current_folder, "web_ready_data.geojson")
print("Converting Shapefile coordinates for the web...")

# 1. Setup the export options profile
options = QgsVectorFileWriter.SaveVectorOptions()
options.driverName = "GeoJSON"
options.fileEncoding = "UTF-8"

# 2. Tell QGIS directly to transform it to EPSG:4326 using targetCrs
# This bypasses the strict 'ct' object mismatch completely!
options.targetCrs = QgsCoordinateReferenceSystem("EPSG:4326")

# 3. Get the native project transform context
transform_context = QgsProject.instance().transformContext()

# 4. Write the vector file using the modern V3 API
error_code, error_msg, new_filename, new_layer = QgsVectorFileWriter.writeAsVectorFormatV3(
    raw_layer,
    output_geojson_path,
    transform_context,
    options
)

if error_code == QgsVectorFileWriter.NoError:
    print("Successfully converted Shapefile to web-friendly format!")
else:
    print(f"Failed to convert data. QGIS Error: {error_msg}")
    qgis_app.exitQgis()
    sys.exit()

# Shut QGIS down safely since our desktop processing layer is done
qgis_app.exitQgis()


# =====================================================================
# SUB-STEP 1C: Build the Interactive Map
# =====================================================================
print("Building your interactive map...")

mymap = folium.Map(location=[0.0, 0.0], zoom_start=2, tiles="OpenStreetMap")

folium.GeoJson(
    output_geojson_path,
    name="Our Automated Shapefile Layer"
).add_to(mymap)

folium.LayerControl().add_to(mymap)

output_html_path = os.path.join(current_folder, "my_first_webmap.html")
mymap.save(output_html_path)

print(f"\n[SUCCESS] Phase 1 complete! View your map here:\n-> {output_html_path}")

