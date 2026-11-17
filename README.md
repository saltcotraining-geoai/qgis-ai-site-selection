# Automated Site Selection with QGIS and PyQGIS: Boolean Screening and Multi-Criteria Evaluation

**Version 2.0.0.** A site-selection workflow in QGIS, automated with PyQGIS. By [SALTCO Training](https://saltco.org) · [YouTube @saltcoTraining](https://www.youtube.com/@saltcoTraining).

The question: *which existing buildings could host a new community facility?* A building is suitable only if it passes **every** rule (Boolean screening):

1. footprint area between 800 and 1,200 m²
2. within 1,000 m of a school
3. more than 100 m from a main highway
4. more than 300 m from a river
5. in the mapped urban area

The same steps you do by hand in QGIS run here in one command, and every intermediate layer is saved so you can compare it with your own.

**New in v2.0: multi-criteria evaluation (MCE).** Same data, same rules, but a more nuanced decision: true limits stay yes/no **constraints**, preferences become weighted 0–1 **factors** (AHP weights), with a **sensitivity check** and a **side-by-side comparison** with the Boolean result. See *Phase 2b* below.

🎬 **Video walkthrough:** [QGIS + AI: Automated Site Selection (Full Demo)](https://youtu.be/khPESqTPLMU) (recorded with the earlier scripts; see *Changes since the video*).

Dataset: QGIS Training Manual exercise data (Swellendam, South Africa) · © OpenStreetMap contributors (ODbL).

**Tested on:** QGIS 3.40.6 LTR, Debian/Ubuntu Linux, Python 3.13. Windows (OSGeo4W) and macOS commands are listed below but haven't been tested yet.

---

## Changes since the video

The scripts shown in the video ([▶ watch on YouTube](https://youtu.be/khPESqTPLMU)) have been fixed and extended. **The method and the result are the same: 9 suitable buildings.** If you want exactly the files from the video, download the release **"Version shown in the video"** (tag `video-2026`).

| In the video | Now (v1.0 onwards) |
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
| `phase2b_mce.py` | yes | **Multi-criteria evaluation** on the same data: constraints + weighted factors (AHP), sensitivity, comparison with Boolean |
| `mce_core.py` | no | MCE maths: AHP weights + consistency ratio, sensitivity, Boolean-vs-MCE labels |
| `phase3_showcase.py` | no | Dashboard: Boolean and MCE results side by side: map + sortable, filterable tables + CSV/GeoJSON export |
| `compare_outputs.py` | no | Compare your manual QGIS result with the script's result |
| `demo.py` | yes | Runs Phase 0 → 1 → 2 → 2b → 3 in one command, stops on errors, checks the output |

Expected input layout:

```
site_selection/
├── config.json  *.py
└── dataset/
    ├── buildings.gpkg  schools.gpkg  roads.gpkg  rivers.gpkg  urban.gpkg
    ├── water.gpkg  restaurants.gpkg          (Phase 1 map; optional criteria in Phase 2b)
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
python3 phase2b_mce.py              # 2b. analysis: multi-criteria evaluation (after Phase 2, for the comparison)
python3 phase3_showcase.py          # 3. dashboard (shows both methods)
```

Or run everything at once:

```bash
python3 demo.py                 # Phase 0 -> 1 -> 2 -> 2b -> 3 (press Enter to start)
python3 demo.py --no-pause      # start immediately
python3 demo.py --skip-phase1   # analysis + dashboard only
python3 demo.py --skip-mce      # Boolean only, as in v1.0
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
| 3 | Choose **one** metric CRS from the study area | – | Local UTM zone. Data that's already in a projected CRS (e.g. a UTM zone) keeps it. |
| 4 | Reproject the study area and every layer to it | Reproject Layer | No mixed coordinate systems |
| 5 | Fix geometries | Fix Geometries | Clip fails on invalid input |
| 6 | Reference zone = study area + buffer | Buffer | Prevents the **edge effect**: a school just outside the study area still counts. Fixed at **1,600 m** in every release from v1.0.1 on, so later releases (MCE, v2.0) read the same prepared data: the largest distance any rule measures (the MCE school factor, 1,500 m) + 100 m. Boolean screening alone would need only 1,100 m; the result is the same 9 sites. `"auto"` = largest rule distance + 100 m. Phase 0 warns if the buffer is ever smaller than that. |
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

### Phase 2b: Multi-criteria evaluation (MCE)

Phase 2b uses the same inputs, the same loading, reprojection, geometry fixing and saving as Phase 2. It even imports Phase 2's functions, so the two methods differ **only** in the decision rule.

| | Phase 2: Boolean screening | Phase 2b: MCE (weighted linear combination) |
|---|---|---|
| Criteria | every rule is a yes/no veto | true limits = **constraints** (0/1); preferences = **factors** (0–1) |
| Importance | all rules equal | factors **weighted** (AHP or direct) |
| Trade-offs | none: one miss = excluded | a strong factor can **compensate** a weak one |
| Result | an unranked set | a **score and rank for every eligible building** |
| Robustness check | none | **sensitivity**: weights ±20 % |

```
suitability = (Σ weightᵢ × factorᵢ) × Π constraintⱼ
```

| Step | What | Manual QGIS (GUI) | Script |
|---|---|---|---|
| 1–3 | Load, reproject, fix, save | same as Phase 2 | same functions as Phase 2 |
| C1 | Constraint: area 800–1,200 m² | Field Calculator + Extract by Expression | `native:fieldcalculator`, `native:extractbyexpression` |
| C2 | Constraint: in urban area | Extract by Location (intersect) | `native:extractbylocation` |
| C3 | Constraint: river setback 100 m (flood safety) | Buffer + Extract by Location (disjoint) | `native:buffer`, `native:extractbylocation` |
| C4 | Constraint: highway setback 25 m | Buffer + Extract by Location (disjoint) | same |
| C5 | *Optional* constraint: water-body setback (`mce.constraints.water_setback.enabled`) | Buffer `water` + Extract by Location (disjoint) | same |
| S+ | *Optional* factor: near restaurants (`mce.factors.restaurant.enabled`) | Field Calculator distance → 0–1, added to the weighted sum | `add_optional_factor()` |
| W | Weights | AHP in a spreadsheet: pairwise matrix → eigenvector → CR | `mce_core.ahp_weights()` |
| S | Standardise + combine | Field Calculator: distance → 0–1 → weighted sum | `enrich_candidates()` (shared with Phase 2) |
| R | Rank + select | Sort by score, Extract by Expression `"mce_rank" <= N` | `native:extractbyexpression` |
| T | Sensitivity | Re-run with changed weights | `mce_core.sensitivity()` |
| V | Compare with Boolean | Join by `osm_id`, compare | `mce_core.compare_with_boolean()` |

Factor scales (`config.json > mce > factors`; linear membership, 0 at `zero_at_m`, 1 at `one_at_m`):

- school: 1 at 0 m, 0 at **1,500 m**. This is wider than the Boolean 1,000 m cut-off, so near-misses get a score instead of being dropped.
- highway: 0 at the 25 m setback, 1 at 500 m.
- river: 0 at the 100 m setback, 1 at 1,000 m.

Default AHP judgements: school is 3× as important as highway and 3× as important as river; highway and river are equal. This gives weights **0.60 / 0.20 / 0.20** with CR = 0.00. All of these values are **teaching defaults** to agree on with your class.

**Selection.** By default (`match_boolean`), MCE selects the same number of sites as the Boolean result, so the comparison is like for like. The alternatives are `top_n` and `min_score`.

**Outputs:**

- `mce_scored_buildings.geojson`: every eligible building with its factor scores, MCE score and rank.
- `suitable_sites_mce.geojson`: the selected sites, with `stability` (0–1), `agreement` and `reason`.
- `mce_vs_boolean.geojson`: both methods' sites in one layer, each labelled:
  - `both`: selected by both methods (**the strongest candidates**)
  - `mce_only`: the `reason` says which Boolean rule it narrowly failed (for example "school 1,060 m > 1000 m")
  - `boolean_only`: the `reason` gives its MCE rank and score
- `mce_summary.json`: weights, AHP matrix, CR, counts, sensitivity scenarios and agreement.
- `phase2b_mce.html`: buildings coloured by MCE score.

**Three ways students can use the results:**

1. **Boolean only**: simple and transparent; good when every rule is a real regulation.
2. **MCE only**: ranked, with trade-offs; good when the criteria are preferences.
3. **Combined**:
   - the **consensus set** (`agreement = both`)
   - Boolean screening with the MCE score as the ranking (that is the Phase 2 `suit_score`)
   - or MCE constraints = the Boolean rules that are true regulations, with everything else as factors

**Discussion questions:**

- Which Boolean rules are real limits and which are preferences?
- Why did a `mce_only` site fail the Boolean screen? Is 60 m too close to call a "fail"?
- Change one AHP judgement to 5 or 1/5. What happens to the CR and to the selected sites?
- Which sites have a stability below 1.0? Would you recommend them?

### Try it: add a criterion (optional exercises)

Two extra criteria are built in but **switched off** by default, so the standard results (22 eligible buildings, weights 0.60 / 0.20 / 0.20, 6 both / 3 MCE only / 3 Boolean only) don't change. Both layers are already in `dataset/` (`water.gpkg`, `restaurants.gpkg`). Use them after you have a baseline run to compare against.

**Before you start:** copy the baseline outputs (`mce_summary.json`, `suitable_sites_mce.geojson`, `mce_vs_boolean.geojson`) into a folder such as `baseline/`, so you can compare before and after. Change one setting at a time.

**Exercise 1: a new constraint (water-body setback, C5)**

1. In `config.json`, set `mce.constraints.water_setback.enabled` to `true` (default distance 50 m from any dam, reservoir or pond).
2. Re-run `python3 phase2b_mce.py`, then `python3 phase3_showcase.py`.
3. Questions:
   - How many buildings still pass the constraints? Did any previously selected site drop out?
   - Is a 50 m setback from standing water a **regulation** (a constraint) or a **preference** (a factor)? What would change if you modelled it as a factor instead?
   - The Boolean screen doesn't use water at all. Is the Boolean-vs-MCE comparison still like for like?

GUI equivalent: Buffer `water` by 50 m (✔ Dissolve) → Extract by Location: *disjoint*.

**Exercise 2: a new factor (closeness to restaurants and amenities)**

1. In `config.json`, set `mce.factors.restaurant.enabled` to `true` (score 1 at 0 m, 0 at 1,500 m).
2. It joins the weights automatically. With `method: "ahp"` the pairs `school/restaurant`, `highway/restaurant` and `river/restaurant` are used; with `method: "direct"`, the `restaurant` weight is used (then all weights are normalised).
3. Re-run `python3 phase2b_mce.py`, then `python3 phase3_showcase.py`.
4. Questions:
   - What are the new weights and the CR in `mce_summary.json`? Did adding a fourth factor keep the matrix consistent (CR < 0.10)?
   - Which sites changed rank? Did the agreement with Boolean (both / MCE only / Boolean only) change?
   - Which sites have a lower stability now? Is a site that wins only because of restaurants a good recommendation for this use?

GUI equivalent: Field Calculator `distance` to the nearest restaurant → 0–1 score → add it to the weighted sum.

**Good to know:**
- Each run writes over the previous outputs, which is why you save the baseline first. To go back, set `enabled` to `false` again and re-run.
- If you widen any factor beyond 1,500 m (for example the restaurant `zero_at_m`), the 1,600 m edge buffer is no longer large enough. Phase 0 will warn you. Raise `study_area.reference_buffer_m` to the new distance + 100 m and re-run Phase 0 first.

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

## Coming next: v2.1 (for experienced analysts)

**Can AI do the GIS?** The same analysis, done three ways with an AI model, each scored against this workflow's criteria matrix. A separate release, video and blog post on [saltco.org](https://saltco.org/blog.html).

## Data and licence

- Code: see `LICENSE`.
- Data: QGIS Training Manual exercise data, derived from **© OpenStreetMap contributors**, available under the [Open Database License (ODbL)](https://www.openstreetmap.org/copyright). Keep this attribution when you share maps or data made from it.
