# Changelog

## v2.0.0 (16 Nov 2026): Multi-Criteria Evaluation

- **New:** `phase2b_mce.py` and `mce_core.py`, plus an `mce` section in `config.json`. Same data and the same prepared layers as the Boolean screening; only the decision rule differs.
- **Constraints vs factors:** true limits stay yes/no (area, urban, 100 m river setback, 25 m highway setback); preferences become 0–1 scores (school, highway, river), weighted by **AHP** (default 0.60 / 0.20 / 0.20, CR 0.000).
- **Sensitivity analysis:** each weight ±20 %; every selected site gets a `stability` score (default run: 0.981).
- **Comparison with Boolean:** each site is labelled `both`, `mce_only` or `boolean_only`, with the reason (default run: 6 / 3 / 3).
- **Dashboard:** Phase 3 shows the MCE layer, a Boolean-vs-MCE card and a ranked MCE table. `demo.py` runs Phase 2b between Phase 2 and Phase 3 (`--skip-mce` for Boolean only).
- **Dashboard selection:** the Boolean table, the MCE table and the map share one selection, keyed by building ID: click a row or a site and it is highlighted on the map and marked in **both** tables. Ctrl/⌘-click adds more sites; **Reset selection** (or Esc) clears everything and returns to the starting view.
- **Credit:** the dashboard footer and the map's attribution line show who prepared it (`web.credit` in `config.json`).
- **Optional criteria, off by default:** a water-body setback (C5) and a restaurant-proximity factor, as class exercises in the README section *Try it: add a criterion*. The results above don't change unless you switch them on.
- **Unchanged:** the Boolean result is still 9 sites, and the 1,600 m edge buffer from v1.0.1 already covers the MCE distances.

## v1.0.1 (16 Nov 2026): one edge buffer for every release

- `study_area.reference_buffer_m` is fixed at **1,600 m** (it was `auto`, which gave 1,100 m). From now on every release reads the same prepared data: 1,600 m covers the largest distance any rule measures in this repository (the MCE school factor in v2.0, 1,500 m) plus a 100 m margin. **The Boolean result is unchanged: 9 sites.**
- Fixed: the video link in this changelog (the video ID ends in a capital U).
- Wording: notes in this changelog, `config.json` and two code comments cleaned up. No code behaviour changes.

## v1.0.0 (13 Nov 2026): Boolean screening, fixed and automated

This is the workflow from the January 2025 site-selection class, fixed and extended. **The method and the result are the same as in the video: 9 suitable buildings.**

- **Fixed:** GeoJSON exports really are lon/lat (`options.ct` + RFC 7946); before, they could silently stay in UTM metres.
- **Fixed:**
  - the web maps no longer crash on GeometryCollection or MultiPoint features (this also restores the layer control)
  - the satellite image overlay displays again
  - the Phase 3 map–table link works
  - missing popup fields are skipped instead of crashing folium
  - HTML is escaped and the files are written as UTF-8
  - QGIS starts and shuts down without warnings
- **New:** Phase 0 data preparation (study area → one metric CRS → reproject → fix → clip, with an edge buffer).
- **New:** attribute-class filters for roads (`main_highway_classes`) and rivers (`river_classes`) before any geometry step.
- **New:** STEP M criteria matrix: pass/fail and the measured values for every building, checked against the Boolean result.
- **New:** `config.json` holds every criterion; `demo.py` runs Phase 0 → 3 in one command.
- **Performance:** fix geometries everywhere; simplify the reference layers (1 m for analysis, 2 m for the web); round GeoJSON coordinates to 6 decimals.
- **Tested on** QGIS 3.40.6 LTR, Debian/Ubuntu, Python 3.13.

Earlier: the version shown in the video, https://youtu.be/khPESqTPLMU (tag `video-2026`).
