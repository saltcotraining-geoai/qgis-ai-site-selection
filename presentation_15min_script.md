# YouTube Presentation — QGIS AI Site Selection (15 min)

---

## Part 1: Intro (0:00 – 3:00)

### 0:00 — Hook (15 sec)

**[Camera: you, relaxed, confident]**

"Most GIS analysts spend hours running the same filters over and over. Buffer this. Clip that. Export. Repeat.

I automated the whole thing — and today I'll show you how."

### 0:15 — Who I am (60 sec)

**[Camera: you]**

"I'm Saltibin — Senior Survey Analyst and GIS instructor.

A bit about me: I have over 25 years in surveying, geospatial analytics, and teaching. I spent 15-plus years as a GIS Analyst in Houston, Texas. Before the war in Sudan, I volunteered teaching QGIS, Python, and ESL at universities there — which taught me that the best tool is the one people can actually access.

Today I run Saltco GeoTraining, focused on open-source GIS automation for universities, NGOs, and professionals in limited-resource regions."

### 1:15 — How AI fits in (60 sec)

**[Camera: you]**

"Now, you might be wondering — where does AI come into this?

Recently I completed Google's AI Essentials certification and started running open-source LLMs locally — models like Llama and Gemma. Here's what I learned:

You don't need ChatGPT Pro to build powerful GIS workflows. Open-source LLMs can help you write PyQGIS scripts, debug spatial queries, and design processing pipelines — all on your own machine, with your own data, no API costs, no privacy concerns.

This whole demo was built with the help of AI — but the final script was tested, refined, and verified by a human who understands GIS."

### 2:15 — What we'll cover (45 sec)

**[Camera: you, maybe show a slide or README]**

"Here's what we'll do in the next 12 minutes:

1. The problem — manual site selection is slow
2. The dataset — 7 layers, 6 criteria, one area in South Africa
3. One command — we run the script live
4. The dashboard — automated results
5. How it works — the PyQGIS pipeline explained
6. Production roadmap — from QGIS to PostGIS to GeoServer to the web

Let's start."

---

## Part 2: The Problem (3:00 – 4:30)

### 3:00 — The manual way (45 sec)

**[Camera: README on GitHub or a simple diagram]**

"Imagine you're a GIS analyst tasked with finding suitable building sites. You need buildings that are:

- Between 800 and 1200 square meters
- Within one kilometer of a school
- Not within 100 meters of a highway
- Not within 300 meters of a river
- Inside a residential urban zone
- And you need a population estimate

Manually? That's six rounds of selection, export, re-import. Easily an hour of clicking."

### 3:45 — The automated way (45 sec)

**[Camera: you]**

"With PyQGIS — the Python API for QGIS — I wrote a script that chains all six filters into one pipeline. You run a single command and get a full interactive dashboard at the end.

From 4,708 buildings to 9 suitable sites. In 25 seconds."

---

## Part 3: Run the Demo (4:30 – 6:30)

### 4:30 — Before we run it (30 sec)

**[Camera: you, then terminal]**

"Let's look at what we're working with. Seven GeoPackage layers from OpenStreetMap — buildings, schools, roads, rivers, urban zones, water bodies, restaurants. Study area: Cape Agulhas, South Africa."

### 5:00 — The magic command (90 sec)

**[Camera: terminal, full screen, font size 18+]**

```bash
python3 demo.py
```

**[Let it run. Stay quiet for 15 seconds while colored output scrolls. Then narrate softly:]**

"Step one — reproject everything to UTM 33 South."

**[pause]**

"Step two — filter buildings by area."

**[pause]**

"Step three — buffer schools at one kilometer, select buildings within."

**[pause]**

"Step four — exclude buildings near highways."

**[pause]**

"Step five — exclude buildings near rivers."

**[pause]**

"Step six — clip to urban zones."

**[pause]**

"And done. Nine suitable sites."

### 6:30 — Open the dashboard

**[Open phase3_dashboard.html in browser]**

"And here's the result — a complete interactive dashboard, generated automatically."

---

## Part 4: Dashboard Tour (6:30 – 9:30)

### 6:30 — Stats cards (30 sec)

**[Cursor hovers over top stats]**

"At the top: 4,708 buildings → 9 suitable sites. The numbers tell the whole story."

### 7:00 — Filter funnel (45 sec)

**[Scroll to filter funnel chart]**

"This bar chart is my favorite part. It shows the cascade — each bar shrinking as we apply more criteria. Area filter cuts it by half. School proximity narrows it further. Highway and river exclusion zones remove the rest. By the time we clip to urban zones, we're down to single digits."

### 7:45 — Interactive map (60 sec)

**[Interact with the map]**

"Green dots are the suitable sites. Click any one — you can see its area, its distance to the nearest school, its population estimate.

The shaded areas show what was excluded: orange buffers around highways, blue buffers around rivers. This gives stakeholders visual confidence that nothing was missed."

### 8:45 — Data table & exports (45 sec)

**[Scroll to data table]**

"Every site in a searchable, sortable table. Click a row — the map zooms to it.

Need to share the results? One click downloads CSV. One click downloads GeoJSON. And Ctrl+P gives a clean, print-friendly report ready for PDF."

---

## Part 5: How It Works (9:30 – 12:00)

### 9:30 — The pipeline (90 sec)

**[Camera: README mermaid diagram or draw on screen]**

"Here's the pipeline under the hood — and this is where the AI piece comes in.

I described this workflow to an open-source LLM running locally on my laptop. It suggested the PyQGIS algorithms I should use, and I refined them based on 25 years of knowing what actually works in the field.

The key algorithms:

- `native:reprojectlayer` — transform all data to UTM 33 South
- `native:fieldcalculator` — calculate building area
- `native:extractbyexpression` — filter by area range
- `native:buffer` — create proximity zones
- `native:extractbylocation` — spatial joins
- `native:fixgeometries` — clean up before calculations

Each one is a QGIS Processing algorithm, chained together in Python."

### 11:00 — Why this matters (60 sec)

**[Camera: you]**

"The beauty of this approach: it's reproducible, it's auditable, and it's completely open-source.

You can tweak any parameter — change the building size range, adjust the buffer distances, swap the study area — and re-run in seconds. No clicking through menus. No manually exporting intermediate results.

This is what I teach. This is what I do. And this is the future of GIS."

---

## Part 6: Production Roadmap & Wrap (12:00 – 15:00)

### 12:00 — Taking it to production (60 sec)

**[Camera: you]**

"What we just ran is a desktop prototype. Here's how you take it to production:

- Load the results into PostgreSQL with PostGIS
- Publish as a WMS layer through GeoServer
- Consume it in a Leaflet web map

Full architecture: PyQGIS → PostgreSQL/PostGIS → GeoServer → Leaflet. All open-source."

### 13:00 — Learn more (60 sec)

**[Camera: you]**

"Everything is on GitHub — saltcotraining-geoai/qgis-ai-site-selection. Full code, dataset, documentation, MIT license. Use it, modify it, teach with it.

I post automated GIS workflows on this channel every week. If you want to move from clicking to coding — hit subscribe."

### 14:00 — Q&A / Engagement (60 sec)

**[Camera: you]**

"Five questions for you in the comments — pick any to answer:

1. What's the most repetitive GIS task you wish you could automate?
2. Have you tried using AI to write GIS scripts — and did it work?
3. What study area or dataset should I cover in the next tutorial?
4. Which would help you more — more PyQGIS pipelines or more dashboard tutorials?
5. What's the biggest barrier stopping you from automating your GIS workflow?

Drop your answers below — I read every comment."

### 14:45 — Outro (15 sec)

**[Camera: you, smile]**

"Thanks for watching. The best GIS analyst is the one who automates their workflow. See you in the next one."

**[End]**
