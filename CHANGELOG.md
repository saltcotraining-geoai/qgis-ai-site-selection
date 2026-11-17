# Changelog

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
