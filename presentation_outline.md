# Presentation Outline
## "QGIS + AI: Automated Site Selection Workflow"
### Target: 10-15 minute talk / workshop opener

---

## Slide 1: Title Slide
- **Title:** QGIS + AI: Automate Your GIS Workflow
- **Subtitle:** Site Selection Analysis with PyQGIS & Python
- **Your name / channel logo**
- **Tagline:** "From 4,708 buildings to 9 suitable sites — in one command"

---

## Slide 2: The Problem
- **Image:** GIS analyst buried in QGIS dialogs (buffer, clip, select, export)
- **Text:**
  - "Manual site selection takes hours of repetitive clicking"
  - "Error-prone — miss a step, wrong answer"
  - "Not reproducible — can you redo it exactly next month?"
- **Key stat:** "A 6-criteria filter that takes 4+ hours manually"

---

## Slide 3: The Solution
- **Image:** Terminal with one clean command
- **Text:**
  - "QGIS Headless + PyQGIS = Automation"
  - "Same algorithms you know — just scripted"
  - "Repeatable · Auditable · Shareable"
- **Key phrase:** "Don't click — code"

---

## Slide 4: The Dataset
- **Screenshot:** QGIS with layers loaded
- **Bullet list:**
  - 7 GeoPackage layers (OSM data)
  - buildings · schools · roads · rivers · urban · water · restaurants
  - satellite_image.tif (drone/satellite base)
  - CRS: EPSG:4326 / EPSG:32733
  - Study area: Cape Agulhas, South Africa

---

## Slide 5: The Criteria
- **Visual:** Checklist with checkmarks
  1. ✅ Area 800–1200 m²
  2. ✅ Within 1000m of school
  3. ✅ NOT within 100m of highway
  4. ✅ NOT within 300m of river
  5. ✅ Within urban zone
  6. ✅ Population estimate
- **Highlight:** "Translated from plain English to QGIS algorithms"

---

## Slide 6: The Pipeline
- **Flow diagram:**
  ```
  ┌─────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
  │  Load   │ → │ Reproject│ → │  Filter  │ → │  Buffer  │
  │  Layers │   │  to UTM  │   │ by Area  │   │  Schools │
  └─────────┘   └──────────┘   └──────────┘   └──────────┘
                                                    ↓
  ┌─────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
  │  Final  │ ← │  Urban   │ ← │   River  │ ← │ Highway  │
  │  Sites  │   │  Clip    │   │  Buffer  │   │ Buffer   │
  └─────────┘   └──────────┘   └──────────┘   └──────────┘
  ```

---

## Slide 7: The Cascade (WOW SLIDE)
- **Animated funnel (build progressively):**
  ```
  4,708  ┌──────────────────────────────────────┐
            ↓ Area filter (800-1200 m²)
     28   ┌──┐
            ↓ School buffer (1000m)
     22   ┌─┘
            ↓ Highway exclusion (100m)
     21   ┌─┘
            ↓ River exclusion (300m)
      9   ┌┘
            ↓ Urban zone clip
      9   ┌┘  ← FINAL SUITABLE SITES
  ```
- **Callout:** "95% reduction in candidate sites. In milliseconds."

---

## Slide 8: The Dashboard
- **Screenshot of phase3_dashboard.html** (full page)
- **Callout boxes:**
  1. Stats cards — at-a-glance summary
  2. Interactive map — green = suitable sites
  3. Filter funnel — visual cascade
  4. Data table — search, sort, export
  5. Export buttons — CSV, GeoJSON, PDF

---

## Slide 9: Live Demo
- **Switch to terminal**
- Run: `python3 demo.py`
- Narrate as it runs
- Open dashboard at the end

---

## Slide 10: How It Works (Code)
- **Code snippet (3-4 lines max):**
  ```python
  # The core — QGIS Processing in 3 lines
  buildings_utm = processing.run("native:reprojectlayer", ...)
  school_buffer = processing.run("native:buffer", ...)
  suitable = processing.run("native:extractbylocation", ...)
  ```
- **Key point:** "Same toolbox you already know — just automated"

---

## Slide 11: Production Architecture
- **Architecture diagram:**
  ```
  ┌──────────┐    ┌────────────┐    ┌──────────┐    ┌──────────┐
  │ PyQGIS   │───▶│ PostgreSQL │───▶│GeoServer │───▶│ Leaflet  │
  │ (Script) │    │  + PostGIS │    │ (WMS)    │    │ (Web Map)│
  └──────────┘    └────────────┘    └──────────┘    └──────────┘
       │                                                
  Scheduled (cron / GitHub Actions)
  ```
- **Key technologies:**
  - PostgreSQL + PostGIS for spatial storage
  - GeoServer for OGC web services (WMS/WFS)
  - Leaflet / MapLibre for frontend
  - Docker for deployment

---

## Slide 12: Use Cases
- **Grid of icons + text:**
  - 🏪 Retail site selection
  - 🏥 Healthcare facility placement
  - 🌳 Conservation reserve design
  - 🚒 Emergency response planning
  - 🏘️ Urban development zoning
  - 📡 Telecom tower placement

---

## Slide 13: Key Takeaways
1. **QGIS + Python replaces hours of clicking**
2. **PyQGIS gives you access to 800+ processing algorithms**
3. **Same workflow works for ANY site selection problem**
4. **From local script → PostgreSQL → GeoServer → public web map**
5. **Open source, free, reproducible**

---

## Slide 14: Resources & Next Steps
- **GitHub:** [github.com/saltcotraining-geoai/qgis-ai-site-selection](https://github.com/saltcotraining-geoai/qgis-ai-site-selection)
- **YouTube:** [youtube.com/@Saltco_GeoTraining](https://youtube.com/@Saltco_GeoTraining)
- **Portfolio:** [saltcotraining-geoai.github.io](https://saltcotraining-geoai.github.io)
- **Watch next:** "Deploying to PostgreSQL & GeoServer"
- **QGIS Documentation:** qgis.org/pyqgis
- **Connect:**
  - 👍 Like this video
  - 💬 Comment your use case
  - 🔔 Subscribe for more
  - 📧 training@saltibin.com

---

## Slide 15: Q&A / Thank You
- **Thank you slide**
- **Contact info**
- **Quote:** "The best GIS analyst is the one who automates their workflow."
