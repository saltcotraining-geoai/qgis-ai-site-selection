# QGIS + AI: Automated Site Selection Demo

[![QGIS](https://img.shields.io/badge/QGIS-3.44-%23339933)](https://qgis.org)
[![Python](https://img.shields.io/badge/Python-3.12-%233776AB)](https://python.org)
[![Folium](https://img.shields.io/badge/Folium-0.20-%2300BFFF)](https://python-visualization.github.io/folium/)
[![YouTube](https://img.shields.io/badge/YouTube-%23FF0000?logo=youtube)](https://youtube.com/@Saltco_GeoTraining)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)
[![Data](https://img.shields.io/badge/Data-QGIS_Training_Manual-339933)](https://docs.qgis.org/latest/en/docs/training_manual/)

> One command. 7 data layers. 6 criteria. 9 suitable sites. **25 seconds.**
> Dataset: QGIS Training Manual (exercise_data) · Data © OpenStreetMap contributors · ODbL

---

📺 **Watch the demo:** [youtube.com/@Saltco_GeoTraining](https://youtube.com/@Saltco_GeoTraining)
🌐 **Portfolio:** [saltcotraining-geoai.github.io](https://saltcotraining-geoai.github.io)
📦 **Company:** Saltco for Training & Capacity Building

---

##  What This Demo Shows

This is a complete automated site selection workflow using **QGIS in headless mode** + **PyQGIS Processing algorithms** + **Folium web maps**.

**The Problem:** Find buildings that meet all these criteria:
1. Area between **800 and 1200 m²**
2. Within **1000m of a school**
3. NOT within **100m of a main highway**
4. NOT within **300m of a river**
5. Inside a **residential urban zone**
6. Calculate **population estimate**

**The Result:** From **4,708 buildings** → **9 suitable sites** — automatically.

---

##  Quick Start

### Prerequisites

| Dependency | Check |
|-----------|-------|
| QGIS 3.x | `qgis --version` |
| Python 3 | `python3 --version` |
| Folium | `pip install folium --break-system-packages` |
| GDAL | Included with QGIS |

### Run the Demo

```bash
# One command — runs all 3 phases
python3 demo.py
```

Or run phases individually:

```bash
# Phase 1: Load data + build web map
python3 phase1_webmap.py

# Phase 2: Run spatial analysis
python3 phase2_site_selection.py

# Phase 3: Generate showcase dashboard
python3 phase3_showcase.py
```

After running, open `phase3_dashboard.html` in your browser.

---

##  Output Files

| File | Size | Description |
|------|------|-------------|
| `phase3_dashboard.html` | ~1.4 MB | **Showcase dashboard** — interactive map, data table, exports |
| `phase2_site_selection.html` | ~1.4 MB | Analysis result map with exclusion zones |
| `phase1_webmap.html` | ~66 MB | Raw data visualization (all 7 layers + satellite) |
| `suitable_sites.geojson` | ~16 KB | Final 9 candidate sites (GeoJSON) |

### Dashboard Features

- **Stats cards** — see the filtering cascade at a glance
- **Interactive map** — green = suitable sites, overlays for exclusion zones
- **Filter funnel** — visual bar chart of the selection process
- **Data table** — searchable, sortable, paginated site register
- **Export CSV** — one-click download
- **Export GeoJSON** — one-click download
- **Print / PDF** — Ctrl+P → "Save as PDF" for professional reports

---

##  Dataset

| Layer | Type | Features | Source |
|-------|------|----------|--------|
| `buildings.gpkg` | Polygon | 4,708 | OpenStreetMap |
| `schools.gpkg` | Polygon | 4 | OpenStreetMap |
| `roads.gpkg` | Line | 717 | OpenStreetMap |
| `rivers.gpkg` | Line | 19 | OpenStreetMap |
| `urban.gpkg` | Polygon | 6 | OpenStreetMap |
| `water.gpkg` | Polygon | 37 | OpenStreetMap |
| `restaurants.gpkg` | Polygon | 11 | OpenStreetMap |
| `satellite_image.tif` | Raster | 3714×3012 | Satellite/drone imagery |

Study area: **Cape Agulhas, South Africa** (approx 20.44°E, -34.02°S)
CRS: EPSG:4326 (WGS 84) / EPSG:32733 (UTM 33S)

**Dataset sourced from [QGIS Training Manual](https://docs.qgis.org/latest/en/docs/training_manual/) exercise_data.**
Original data © [OpenStreetMap contributors](https://openstreetmap.org/copyright) (ODbL).

---

##  How It Works

```mermaid
graph TD
    A[Load GeoPackage Layers] --> B[Reproject to UTM 33S]
    B --> C[Filter Buildings by Area 800-1200m²]
    C --> D[Buffer Schools 1000m → Select Within]
    D --> E[Buffer Highways 100m → Exclude]
    E --> F[Buffer Rivers 300m → Exclude]
    F --> G[Clip to Urban Zones]
    G --> H[Calculate Population Estimate]
    H --> I[Export GeoJSON + Folium Dashboard]
```

**Key PyQGIS algorithms used:**
- `native:reprojectlayer` — CRS transformation
- `native:fieldcalculator` — $area calculation
- `native:extractbyexpression` — attribute filter
- `native:buffer` — distance buffering
- `native:extractbylocation` — spatial selection (intersect/disjoint)
- `native:fixgeometries` — geometry validation

---

##  YouTube Demo

Watch the full walkthrough: **[youtube.com/@Saltco_GeoTraining](https://youtube.com/@Saltco_GeoTraining)**

### In the video:
- 00:00 — Intro: The problem with manual GIS
- 01:30 — The dataset and criteria
- 03:00 — Running `python3 demo.py` (the magic command)
- 05:00 — The filtering cascade (WOW moment)
- 07:00 — Dashboard reveal
- 09:00 — How it works under the hood
- 10:00 — PostgreSQL + GeoServer production roadmap

---

##  Production Roadmap (Phase 3)

```bash
# Step 1: Load into PostgreSQL/PostGIS
ogr2ogr -f "PostgreSQL" PG:"dbname=gis" suitable_sites.geojson \
  -nln analysis.suitable_sites

# Step 2: Publish via GeoServer WMS
# (Point GeoServer data store to your PostgreSQL database)

# Step 3: Build Leaflet web map consuming GeoServer WMS
```

Full architecture: `PyQGIS → PostgreSQL/PostGIS → GeoServer → Leaflet`

---

##  License & Attribution

**Code:** MIT — free to use, modify, and share.

**Dataset:** Sourced from the [QGIS Training Manual](https://docs.qgis.org/latest/en/docs/training_manual/) exercise_data.
Original data © [OpenStreetMap contributors](https://openstreetmap.org/copyright) — licensed under [ODbL](https://opendatacommons.org/licenses/odbl/).
Contains information from the QGIS project (CC-BY-SA).

---

##  Connect

**YouTube:** [youtube.com/@Saltco_GeoTraining](https://youtube.com/@Saltco_GeoTraining)
**GitHub:** [github.com/saltcotraining-geoai/qgis-ai-site-selection](https://github.com/saltcotraining-geoai/qgis-ai-site-selection)
**Portfolio:** [saltcotraining-geoai.github.io](https://saltcotraining-geoai.github.io)
**Company:** Saltco for Training & Capacity Building
**Email:** saltco.training@gmail.com

*"The best GIS analyst is the one who automates their workflow."*
