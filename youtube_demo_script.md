# ─────────────────────────────────────────────────────────────────
# YouTube Demo Script
# Title: "QGIS + AI: Automated Site Selection in 60 Seconds"
# Duration: ~10 minutes
# Audience: Beginners to mid-career GIS professionals, students
# ─────────────────────────────────────────────────────────────────

## ── INTRO (0:00 - 1:30) ──────────────────────────────────────

### VISUAL: You on camera (or voiceover) + terminal/screen share

"Welcome back! Today I'm going to show you something that usually takes
GIS analysts half a day — and do it in under 60 seconds.

This is the problem: You have a city dataset — buildings, schools, roads,
rivers, urban zones. Your task: find every building that is:

  → Between 800 and 1200 square meters
  → Within 1 kilometer of a school
  → NOT within 100 meters of a highway
  → NOT within 300 meters of a river
  → Inside a residential urban zone

Manually? You'd be buffering, clipping, selecting, exporting for hours.
With QGIS + PyQGIS + AI workflow automation? One command, done.

Let me show you."

### SCREEN: Open terminal at the project directory
"Here's what we're working with..."

### SCREEN: ls -la dataset/
"7 GeoPackage layers — buildings, schools, roads, rivers, urban,
water, restaurants — plus a satellite image. All ready to go."

### SCREEN: cat location_criteria
"These are the 6 selection criteria. Written in plain English.
Our Python script translates these into QGIS spatial algorithms."


## ── THE MAGIC COMMAND (1:30 - 3:00) ─────────────────────────

### VISUAL: Terminal, type the command slowly

"Watch this. One command."

### TYPE: python3 demo.py

### PAUSE for the banner animation to print
"The script prints a beautiful banner, tells you what it's about,
and asks you to press Enter."

### PRESS ENTER — Phase 1 starts immediately
"Phase 1 fires up QGIS in headless mode — no GUI needed.
It loads all 7 layers, converts them to web-friendly GeoJSON,
and builds an interactive Folium map."

### Let the layer loading output scroll
"Notice: 4,708 buildings loaded. 717 roads. 19 rivers.
Each layer converted to the web-friendly GeoJSON format.
All in about 15 seconds."

### SCREEN: Briefly show phase1_webmap.html (optional quick tab switch)
"This is the raw data map — every building in red, schools in blue,
roads in amber, rivers in teal. You can hover to see details,
click for full popups, toggle layers on and off. All interactive.
But this is just the starting point — the data explorer."


## ── THE ANALYSIS CASCADE (3:00 - 4:30) ─────────────────────

### VISUAL: Terminal output as Phase 2 begins automatically

"But Phase 2 is where the real magic happens."

### READ the cascade numbers as they appear live on screen:

"Watch the numbers cascade down:

  4,708 buildings total
  → 28 meet the size criteria (800-1200 sqm)
  → 22 are within 1km of a school
  → 21 pass the highway exclusion zone
  → 9 survive the river buffer
  → 9 are inside urban zones

From 4,708 to 9 suitable sites. In seconds."

### EMPHASIZE — lean in, slow down:
"This is the WOW moment. What takes a GIS analyst 4 hours
of clicking, buffering, selecting, exporting — QGIS does
in milliseconds. And it's 100% reproducible. Run it again
tomorrow with updated data and get the same correct answer."


## ── THE DASHBOARD REVEAL (4:30 - 6:30) ──────────────────────

### VISUAL: Browser auto-opens, show the dashboard

"And then the script opens this."

### WALK through the dashboard top to bottom:

  ★ Summary stats cards — see the filtering cascade
  ★ Interactive map — green polygons = your suitable sites
  ★ Exclusion zone overlays — school buffer, highway buffer,
     river buffer, urban zones — all color-coded
  ★ A searchable data table — click any site for details
  ★ One-click CSV export
  ★ One-click GeoJSON export
  ★ Print to PDF — perfect for reports

Let me open it."

### SCREEN: Show the dashboard, walk through each section

"Top: the summary. 9 sites found. 279 estimated population.

Left: the interactive map. Green = suitable. Red = highway exclusion.
Blue = school zone. You can toggle layers, click sites for popups.

Right: the filter funnel — a visual bar chart showing how each
criterion narrowed down the candidates. This is great for
stakeholder presentations.

Bottom: the full data table. Search by name, sort by area,
filter by type. Export to CSV for Excel, or GeoJSON for QGIS.

And if you need a PDF report? Just Ctrl+P → Save as PDF.
It's print-optimized — clean layout, no buttons, just the data."


## ── THE ARCHITECTURE (7:00 - 8:30) ──────────────────────────

### VISUAL: Diagram or code walkthrough — show script.py structure

"Let me show you how this works under the hood."

### SCREEN: Show parts of phase3_showcase.py

"There are three parts:

1. QGIS Initialization — we start QGIS in headless mode.
   No GUI. It runs entirely from the command line.
   Perfect for servers, automation, CI/CD pipelines.

2. Spatial Analysis — we use QGIS Processing algorithms.
   native:reprojectlayer, native:buffer, native:extractbylocation,
   native:extractbyexpression. These are the same tools you use
   in the QGIS toolbox — just automated via Python.

3. Web Publishing — Folium converts the results into an
   interactive Leaflet map. Embed it in a website, share it
   with stakeholders, export as PDF."

"This is the AI + GIS workflow I teach:

  → Define criteria (plain English)
  → Translate to spatial operations
  → Automate with PyQGIS
  → Publish as web dashboard
  
  You can apply this to ANY site selection problem.
  Retail, real estate, conservation, emergency services — same pipeline."


## ── WIDER AUDIENCE: POSTGRESQL + GEOSERVER (8:30 - 9:30) ──

### VISUAL: Architecture diagram or bullet points

"Now, this is Phase 1 — local analysis. Phase 2 is
publishing to the web for a wider audience.

Here's the production architecture:

  PyQGIS → PostgreSQL/PostGIS → GeoServer → Leaflet Web Map

Step 1: Load all layers into PostgreSQL with PostGIS extension.
   ogr2ogr imports the GeoPackages as spatial tables.

Step 2: Publish via GeoServer as WMS/WFS services.
   This gives you REST APIs, tile caching, user permissions.

Step 3: Replace the Folium map with Leaflet consuming
   GeoServer WMS. Now your analysis is live, scalable,
   and accessible from any device.

You can even automate the refresh — run the script daily,
auto-reload GeoServer, invalidate cache. Always up to date."


## ── CALL TO ACTION (9:30 - 10:00) ──────────────────────────

### VISUAL: You on camera

"If you found this useful:

  👍 Like this video — it tells the algorithm more people
     should see this
  💬 Comment below — what site selection problem would YOU
     automate? I'll help you build it.
  🔔 Subscribe — I post GIS + AI automation tutorials every week
  📥 Download the code — link in description. Run it yourself.
     All open source. QGIS. Python. Folium. Free.

Next video: I'll show you how to deploy this on a real server
with PostgreSQL and GeoServer — production-ready.

Thanks for watching. Go automate something. 🚀"


## ── RECORDING SETUP GUIDE ────────────────────────────────────

### Terminal setup (critical — this is on camera):
- **Emulator:** GNOME Terminal or Tilix (clean, no tabs visible)
- **Font:** Fira Code Nerd Font or JetBrains Mono **20pt** (must be readable in 1080p)
- **Theme:** One Dark or Dracula — dark background makes colors pop
- **Window size:** 1280×800, positioned top-left quarter of screen
- **Remove distractions:** no menu bar, no scrollbar if possible
- **Command:** `clear && python3 demo.py` — clean start

### Recording setup:
- **Software:** OBS Studio (free, open source)
- **Resolution:** 1080p at 30fps
- **Audio:** USB microphone (Blue Yeti, Rode NT-USB, or Samson Q2U)
  - Room tip: hang a blanket behind you to kill echo
- **Lighting:** window-facing or ring light — avoid being backlit
- **Recording approach:** 
  - Record terminal FULL SCREEN (no other windows visible)
  - Record your face as a separate source (picture-in-picture corner)
  - Dashboard reveal: switch to browser source or edit it in post

### Script execution notes:
- The entire demo runs in **~25 seconds** of processing time
- You have plenty of room to narrate over it
- **Key moments to pause:**
  1. After the banner prints (2s pause) — let viewers read "Automated Site Selection"
  2. When the cascade numbers appear (2s pause at 4708→28→22→21→9→9)
  3. After "DEMO COMPLETE" banner (3s pause) — let it sink in
  4. Dashboard opening — move mouse slowly, let each section breathe

### Editing workflow:
1. Record terminal session in one take (just let it run)
2. Record your face/narration separately or simultaneously in OBS
3. In editing (DaVinci Resolve / Shotcut — both free):
   - Trim the QGIS startup silence (first 2-3 seconds of output)
   - Add a zoom-in effect when the cascade numbers appear
   - Add text overlay that highlights: "4,708 → 9" during the cascade
   - When dashboard opens, switch to a browser recording
   - Add soft background music (YouTube Audio Library — search "ambient electronic")
4. Final check: watch without audio — visuals should tell the story

### Thumbnail:
- Split screen: left side shows the 4,708 buildings, right side shows 9 green markers
- Big bold text: "QGIS + AI = 25 SECONDS"
- Funnel graphic connecting the two sides
- Your face (excited expression) in the bottom corner
- Colors: dark background, bright green for the result

### Title options (A/B test these):
1. "From 4,708 to 9 Buildings: AI Automates QGIS in 25 Seconds"
2. "I Automated QGIS Site Selection with One Python Command"
3. "QGIS + AI: The End of Manual Site Selection"
4. "Stop Wasting Hours: Automate QGIS Analysis with PyQGIS"

### Description template:
```
Can QGIS + AI really find suitable building sites in 25 seconds?
Yes — and this video proves it. 🚀

In this demo I show you how to automate a 6-criteria site selection
analysis using PyQGIS processing algorithms — all in one command.

📂 Dataset: OpenStreetMap (buildings, schools, roads, rivers, urban)
📍 Location: Cape Agulhas, South Africa
⚙️ Tech: QGIS 3.44 · PyQGIS · Folium · Python

🔗 Code: https://github.com/saltcotraining-geoai/qgis-ai-site-selection

📅 Series: AI-Powered GIS for the Developing World
Next episode: Watershed delineation with open data

If you're a GIS professional, student, or someone who wants to use
open-source tools to solve real problems — hit subscribe and join
the journey.

📚 Dataset credit:
Dataset sourced from the QGIS Training Manual exercise_data (CC-BY-SA).
Original data © OpenStreetMap contributors — openstreetmap.org/copyright (ODbL)

#QGIS #PyQGIS #GIS #AI #OpenSource #Geospatial #Python #Automation
```
