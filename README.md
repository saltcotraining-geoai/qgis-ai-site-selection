# Automated Site Selection with QGIS and PyQGIS: Boolean Screening

**Version 1.0.0.** A site-selection workflow in QGIS, automated with PyQGIS. By [SALTCO Training](https://saltco.org) · [YouTube @saltcoTraining](https://www.youtube.com/@saltcoTraining).

The question: *which existing buildings could host a new community facility?* A building is suitable only if it passes **every** rule (Boolean screening):

1. footprint area between 800 and 1,200 m²
2. within 1,000 m of a school
3. more than 100 m from a main highway
4. more than 300 m from a river
5. in the mapped urban area

The same steps you do by hand in QGIS run here in one command, and every intermediate layer is saved so you can compare it with your own.

🎬 **Video walkthrough:** [QGIS + AI: Automated Site Selection (Full Demo)](https://youtu.be/khPESqTPLMU) (recorded with the earlier scripts; see *Changes since the video*).

Dataset: QGIS Training Manual exercise data (Swellendam, South Africa) · © OpenStreetMap contributors (ODbL).

**Tested on:** QGIS 3.40.6 LTR, Debian/Ubuntu Linux, Python 3.13. Windows (OSGeo4W) and macOS commands are listed below but haven't been tested yet.

---

## Changes since the video

The scripts shown in the video ([▶ watch on YouTube](https://youtu.be/khPESqTPLMU)) have been fixed and extended. **The method and the result are the same: 9 suitable buildings.** If you want exactly the files from the video, download the release **"Version shown in the video"** (tag `video-2026`).

| In the video | Now (v1.0) |
|---|---|
| Criteria written inside the scripts | All criteria in **`config.json`**; edit that file, not the code |
| Starts with Phase 1 | **Phase 0** prepares the data first: study area → one metric CRS → reproject → fix → clip |
| "WGS 84" GeoJSON exports could really be in UTM metres (a silent PyQGIS bug) | Exports are real lon/lat (EPSG:4326) |
| Only the urban layer was fixed | **Every** layer is fixed, and roads and rivers are filtered by attribute class first |
| Three scripts, run one by one | The same three scripts, plus `phase0_prepare_data.py` and `demo.py` to run everything at once |
| Shows who passed | Also explains who failed and why: a **criteria matrix** for all 4,708 buildings |
| Result: 9 buildings | **Result: the same 9 buildings** ✔ |

The full list of fixes is at the end of this file.

---

## Files

| File | Needs QGIS? | Purpose |
|---|---|---|
| `config.json` | – | **All criteria and settings.** Edit this file, not the code. |
| `site_common.py` | no | Shared helpers: config loading, basemaps, field checks |
| `qgis_common.py` | yes | Shared PyQGIS helpers: start/stop QGIS, Processing, saving layers |
| `phase0_prepare_data.py` | yes | **Run first.** Study area → one metric CRS → reproject → fix → clip, written to `prepared/` |
| `phase1_webmap.py` | yes | Explore the input data on an interactive web map |
| `phase2_site_selection.py` | yes | **The analysis:** Boolean screening (Steps 1–3, A–F), criteria matrix (M), export (G) |
| `phase3_showcase.py` | no | Dashboard: map + sortable, filterable table + CSV/GeoJSON export |
| `compare_outputs.py` | no | Compare your manual QGIS result with the script's result |
| `demo.py` | yes | Runs Phase 0 → 1 → 2 → 3 in one command, stops on errors, checks the output |

Expected input layout:

```
site_selection/
├── config.json  *.py
└── dataset/
    ├── buildings.gpkg  schools.gpkg  roads.gpkg  rivers.gpkg  urban.gpkg
    ├── water.gpkg  restaurants.gpkg          (Phase 1 map only)
    └── satellite_image.tif                   (Phase 1 only, optional)
```

---

## Running

Install folium once into the same Python that QGIS uses:

```bash
python3 -m pip install folium
```

| System | Command |
|---|---|
| **Linux** (Debian/Ubuntu QGIS packages) | `/usr/bin/python3 phase2_site_selection.py` |
| **Windows** (OSGeo4W) | Open the *OSGeo4W Shell* and run `python-qgis-ltr.bat phase2_site_selection.py` (or `python-qgis.bat`) |
| **macOS** | `/Applications/QGIS.app/Contents/MacOS/bin/python3 phase2_site_selection.py` |

> **Linux tip:** use the system Python (`/usr/bin/python3`). A conda or virtual-environment Python can't see the QGIS libraries and fails with `No module named 'qgis'`.

If QGIS is installed somewhere else, set `QGIS_PREFIX_PATH` (for example `export QGIS_PREFIX_PATH=/opt/qgis`).

Run the phases in order:

```bash
python3 phase0_prepare_data.py      # 0. data preparation: study area, CRS, fix, clip
python3 phase1_webmap.py            # 1. optional: data exploration map
python3 phase2_site_selection.py    # 2. analysis: Boolean screening + criteria matrix
python3 phase3_showcase.py          # 3. dashboard
```

Or run everything at once:

```bash
python3 demo.py                 # Phase 0 -> 1 -> 2 -> 3 (press Enter to start)
python3 demo.py --no-pause      # start immediately
python3 demo.py --skip-phase1   # analysis + dashboard only
python3 demo.py --no-browser    # don't open the dashboard at the end
```

`demo.py` runs each phase in its own process. QGIS can only be started and stopped cleanly once per process, so the phases aren't imported into one process. If a phase fails, the demo stops and names it. After Phase 2 it also checks that `suitable_sites.geojson` is really in lon/lat.

To run another town or another set of criteria, copy `config.json`, edit it, then run, for example, `python3 demo.py --config my_town.json`.

---

## The workflow: GUI tool ↔ script step

Each row is one manual action in QGIS and the matching code in `phase2_site_selection.py`.

| Step | Rule | Manual QGIS (GUI) | Script (Processing ID) |
|---|---|---|---|
| 1 | Load data | Layer ▸ Add Layer ▸ Add Vector Layer | `load_vector()` |
| 2 | Metric CRS | Choose UTM zone (EPSG:32734 for Swellendam) | `choose_analysis_crs()`: `auto` or fixed in config |
| 3 | Reproject | Vector ▸ Data Management ▸ Reproject Layer | `native:reprojectlayer` |
| 3 | Fix geometries | Processing ▸ Vector geometry ▸ Fix Geometries | `native:fixgeometries` |
| A | Area 800–1,200 m² | Field Calculator `area($geometry)` → Extract by Expression | `native:fieldcalculator`, `native:extractbyexpression` |
| B | ≤ 1,000 m to school | Buffer (✔ Dissolve) → Extract by Location: *intersect* | `native:buffer`, `native:extractbylocation` (0) |
| C | > 100 m from main highway | Check the attribute table → Extract by Expression `"highway" IN (...)` → Buffer → Extract by Location: *disjoint* | `main_highways_layer()`, `native:buffer`, `native:extractbylocation` (2) |
| D | > 300 m from river | (optional) Extract by Expression on `waterway` → Buffer → Extract by Location: *disjoint* | `river_layer()`, `native:buffer`, `native:extractbylocation` (2) |
| E | In urban area | Extract by Location: *intersect* (or *are within*) | `native:extractbylocation` (0 / 6) |
| F | Population proxy | Field Calculator `"area_sqm" / 30` | `enrich_candidates()` |
| F | Rank candidates | Field Calculator (distances, weighted sum) | `enrich_candidates()` |
| M | Criteria matrix | Field Calculator: distance + pass/fail per criterion for every building | `build_criteria_matrix()` → `criteria_matrix.csv` |
| G | Export | Export ▸ Save Features As… GeoJSON, EPSG:4326 | `save_vector(..., "GeoJSON", wgs84())` |

Every intermediate layer is saved in `analysis_data/steps/`, so you can open each one next to your own GUI layer and compare them step by step.

### Phase 0: data preparation (run first)

All later phases analyse the **prepared** layers. They switch to `prepared/` automatically once Phase 0 has run, and warn if the study-area settings have changed since then.

| Step | What | GUI equivalent | Why |
|---|---|---|---|
| 1 | Find every GeoPackage in `dataset/` | – | Originals are never modified |
| 2 | Build the study area: building extent, urban polygons (optionally filtered) or your own polygon | Extract Layer Extent / Dissolve | `config.json > study_area.source` |
| 3 | Choose **one** metric CRS from the study area | – | Local UTM zone. Data that's already projected (e.g. UTM 36N) keeps its CRS. |
| 4 | Reproject the study area and every layer to it | Reproject Layer | No mixed coordinate systems |
| 5 | Fix geometries | Fix Geometries | Clip fails on invalid input |
| 6 | Reference zone = study area + buffer | Buffer | Prevents the **edge effect**: a school just outside the study area still counts. Auto = largest rule distance (1,000 m) + 100 m. |
| 7 | Buildings: **select** whole footprints in the study area. Other layers: **clip** to the reference zone. | Extract by Location / Clip | Cutting a footprint would change its area, which is a selection rule |
| 8 | Fix again, drop empty geometries | Fix Geometries | Clipping can leave GeometryCollections or slivers |
| 9 | Save `prepared/*.gpkg`, `study_area.gpkg`, `reference_zone.gpkg`, `prepare_summary.json` | – | Before/after counts of features and vertices |

The default study area (`source: extent`, the bounding box of all buildings) keeps the **same 9 sites** while removing far-away roads, rivers and urban polygons. For your own data, use `source: file` with a digitised study-area polygon, or `source: urban` with a filter such as `"MIN_REGION" = 'SWELLENDAM'`.

### Attribute filters before geometry

Roads and rivers are filtered on their **attribute tables** before any buffer or overlay, so the geometry steps only handle the features a rule is about. Each run prints the classes it finds, like *Show unique values* in the GUI:

```
main_highways classes in the attribute table: residential (268), track (132), … trunk (57), primary (12) …
main_highways: kept 74 of 716 features where "highway" IN ('motorway', …)
rivers_filtered classes in the attribute table: river (6)
```

- `criteria.main_highway_classes`: which `highway` values count as "main".
- `criteria.river_classes`: which `waterway` values count as a river. An empty list `[]` means every waterway. This matters for QuickOSM downloads that mix `river`, `stream`, `canal` and `drain`.

### Screening vs. ranking

- **Steps A–E are screening.** A building has to pass every rule, or it is excluded.
- **Step F ranks the survivors.** Each candidate gets a 0–1 score per factor by straight-line interpolation (settings under `scoring` in `config.json`):
  - school: 1 at 0 m, 0 at 1,000 m
  - highway: 0 at 100 m, 1 at 500 m
  - river: 0 at 300 m, 1 at 1,000 m

  `suit_score` is the weighted sum (weights 0.50 / 0.25 / 0.25 by default). It orders the candidates but never excludes one.

### Criteria matrix (STEP M)

The Extract steps only tell you who *survived*. STEP M measures every rule for **every** building and records pass/fail:

- `criteria_matrix.csv`: one row per building, with the area, the distances, `pass_area` … `pass_urban`, `pass_all` and `fail_reasons`
- `all_buildings_evaluated.geojson`: the same on the map, so you can click any building to see why it was rejected

Phase 2 checks that `pass_all` reproduces the Boolean result exactly (`identical ✔`). If your manual result differs, the matrix shows which rule decided each building.

### Performance: fix, simplify, round

| Setting (`config.json > performance`) | Default | Effect | Trade-off |
|---|---|---|---|
| Fix geometries | always on | Repairs invalid polygons before any step | None: always do it |
| `simplify_analysis` | 1 m on roads, rivers and urban | Fewer vertices make buffers, overlays and distance checks faster | Distances to these layers can shift by up to 1 m. A building almost exactly at 100, 300 or 1,000 m could change result. |
| `simplify_web` | 2 m on all map layers except buildings | Smaller GeoJSON and HTML, faster on slow connections | Display only. The analysis and the result footprints are not affected. |
| `geojson_precision` | 6 decimals (about 11 cm) | Smaller GeoJSON files | Positions are rounded to about 11 cm |

**Building footprints are never simplified**: that would change their areas, and area is a selection rule. Each run prints the vertex counts before and after and records them in `site_selection_summary.json`.

GUI equivalent: *Vector ▸ Geometry Tools ▸ Simplify* (Douglas-Peucker, tolerance in metres on a UTM layer), then *Fix Geometries* again.

### Population

- `pop_estimate` = footprint area ÷ 30, a simple rule of thumb (30 m² per person).
- `pop_estimate_levels` also multiplies by `building:levels` (1 when the value is missing).

Both are rough proxies, not census figures.

---

## Comparing your manual QGIS result with the script

1. Export your final GUI layer as **GeoJSON in EPSG:4326**, keeping the `osm_id` (or `full_id`) field.
2. Run:

```bash
python3 compare_outputs.py manual=results/manual_qgis.geojson pyqgis=suitable_sites.geojson
```

3. Open `comparison_report.md`. It shows the counts, the agreement (Jaccard), every building that only one method selected, and a checklist of likely causes. If the files share no ID field, add `--match centroid`.

### Legitimate reasons the results may differ

| Cause | How to make them match |
|---|---|
| GUI `$area` is **ellipsoidal**; the script uses planar `area($geometry)` | Use `area($geometry)` in the GUI too |
| Different CRS | Set `analysis.analysis_crs` to the CRS you used in the GUI |
| Buffer segments / dissolve | 36 segments, ✔ Dissolve result |
| Predicate (intersects vs. within) | `criteria.urban_relation` |
| Which road classes count as "main" | `criteria.main_highway_classes` |
| Invalid geometries skipped in the GUI | Run Fix Geometries first in the GUI too |
| "Select within current selection" forgotten | Use Extract by…, not Select by…, in the GUI |

The comparison is itself a lesson: each difference points to a decision that was left implicit somewhere.

---

## What was fixed since the video (full list)

**Critical**

- **Reprojection on export.** `options.targetCrs` doesn't exist on `SaveVectorOptions`, so PyQGIS ignored it silently, and the "WGS 84" GeoJSON outputs could be in UTM metres. Exports now use `options.ct` (a `QgsCoordinateTransform`) plus `RFC7946=YES`. See `qgis_common.save_vector()`.

**Bugs**

- **Map crash.** Leaflet 1.9 crashed on GeometryCollection and MultiPoint features, which also hid the layer control. Every map layer now goes through `normalize_for_leaflet()` first.
- **Dashboard map** now fills the full height of its card.
- **Phase 1 satellite image.** A GeoTIFF embedded as `image/tiff` doesn't display in Chrome or Firefox. It's now warped to EPSG:3857 and saved as a size-limited PNG (`web_assets/`).
- **Phase 1 highlight style.** Every layer highlighted with the last layer's style, because of late binding. Values are now bound per layer.
- **Invalid geometries.** Previously only the urban layer was fixed. All inputs are now fixed.
- **Phase 3 map–table link.** Three conflicting mechanisms disabled the popups. There's now one mechanism, keyed on `site_id`.
- **Missing fields.** Popup and tooltip fields that don't exist crashed folium. They're now filtered against the data.
- **Unescaped text.** OSM text is now HTML-escaped in the table, and the CSV export has a UTF-8 BOM, so Excel reads it correctly.
- **Windows encoding.** The HTML is written as UTF-8 explicitly.
- **QGIS start and shutdown.** The "Application path not initialized" warning is gone (no QGIS objects are created before QGIS starts), and layers are released before `exitQgis()`, which avoids exit crashes.
- **Empty highway or river selections** are now skipped with a warning instead of being buffered.

**Method and portability**

- All criteria are in `config.json`. The summary records the QGIS version, a timestamp, the config file and the input paths.
- Phase 0 data preparation, with an edge buffer so features just outside the study area still count.
- Attribute-class filters for roads and rivers before any geometry step.
- Criteria matrix (STEP M) for every building.
- Ranking score (`suit_score`, `rank`), distance fields and `pop_estimate_levels`.
- Lat/lon calculated in PyQGIS with `pointOnSurface()`.
- Both urban results are saved (`intersects` and `within`); `config.json` chooses the primary one.
- Basemaps: OpenStreetMap plus Esri World Imagery, with attribution. Direct Google tile URLs aren't permitted by Google's terms.
- **Low-bandwidth dashboard:** no jQuery, DataTables, Font Awesome or Google Fonts. Search, sorting and exports are plain JavaScript.

---

## Coming next: v2.0

**Multi-criteria evaluation (MCE):** constraints plus weighted factors (AHP), sensitivity analysis, and a side-by-side comparison with this Boolean result. A blog post and a recording will follow on [saltco.org](https://saltco.org/blog.html).

## Data and licence

- Code: see `LICENSE`.
- Data: QGIS Training Manual exercise data, derived from **© OpenStreetMap contributors**, available under the [Open Database License (ODbL)](https://www.openstreetmap.org/copyright). Keep this attribution when you share maps or data made from it.
