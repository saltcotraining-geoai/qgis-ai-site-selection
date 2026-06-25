# YouTube Demo Script — QGIS AI Site Selection (3 min)

---

## 0:00 — Intro (30 sec)

**[Camera: you]**

"Most GIS analysts spend hours running the same spatial filters over and over. Buffer this. Clip that. Export. Repeat.

I automated the whole thing with QGIS and PyQGIS. One command. Seven data layers. Six criteria. From 4,708 buildings to 9 suitable sites in about 25 seconds.

Let me show you."

---

## 0:30 — Run the demo (30 sec)

**[Camera: terminal window]**

"I'm inside the project folder. The only thing I need to do is run:"

```bash
python3 demo.py
```

**[Let the colored output scroll. Say nothing for 10 seconds. Then:]**

"You can see each step being logged in real time — reprojecting, filtering by area, buffering schools, excluding highways and rivers, clipping to urban zones."

---

## 1:00 — Dashboard reveal (30 sec)

**[Camera: browser showing phase3_dashboard.html]**

"And here's the result. A full interactive dashboard, generated automatically."

**[Stats cards at the top — zoom in with cursor]**

"4,708 buildings → filtered to 9 sites. That's what automation looks like."

---

## 1:30 — Dashboard tour (90 sec)

**[Camera: dashboard, moving slowly]**

"Let me walk through what this gives us."

**1:30 — Filter funnel:** "This bar chart shows the cascade — how each criterion narrows the pool."

**1:45 — Map:** "Green dots are the 9 suitable sites. The overlays show exclusion zones — rivers, highways, everything that was filtered out."

**2:00 — Data table:** "Every site is in a searchable, sortable table. Click any row to zoom to it."

**2:20 — Exports:** "One click to download CSV. One click for GeoJSON. And Ctrl+P gives you a clean PDF-ready report."

**2:45 — Wrap:**

"This whole workflow runs on free, open-source tools. QGIS. Python. Folium. No expensive licenses.

Full code and dataset are on GitHub — link below. Hit subscribe if you want more automated GIS workflows."

**[End]**
