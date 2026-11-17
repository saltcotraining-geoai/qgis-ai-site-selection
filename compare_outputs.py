#!/usr/bin/env python3
"""Compare site-selection results from different methods.

Typical use:
    manual  = the result students produce by hand in QGIS (exported as GeoJSON, WGS 84)
    pyqgis  = suitable_sites.geojson from phase2_site_selection.py
    ai      = the result of the prompt-only AI run (exported as GeoJSON)

    python3 compare_outputs.py manual=results/manual_qgis.geojson \\
                               pyqgis=suitable_sites.geojson \\
                               ai=results/ai_prompt.geojson

No QGIS needed (standard-library Python only).

Matching
    --match id        (default) match buildings by an ID attribute. The field is
                      chosen with --id-field, or automatically: the first of
                      osm_id / full_id / source_id / fid present in ALL inputs.
    --match centroid  match by location when the files share no ID field:
                      two buildings are "the same" if their vertex-mean points
                      are within --tolerance-m metres (default 2 m).

Outputs (next to the first input, or --out-dir)
    comparison_report.md        counts, overlaps, differences, likely causes
    comparison_membership.csv   one row per building: which methods selected it
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from itertools import combinations
from pathlib import Path

AUTO_ID_FIELDS = ["osm_id", "full_id", "source_id", "fid"]

LIKELY_CAUSES = [
    "Area: GUI `$area` is ellipsoidal; the script uses planar `area($geometry)` - buildings near 800 / 1,200 m² can switch.",
    "CRS: a different projected CRS (e.g. another UTM zone or Lo19) changes areas and distances slightly.",
    "Buffers: number of segments, and whether 'Dissolve result' was ticked.",
    "Spatial predicate: intersects vs. within (urban step) and intersects vs. disjoint (exclusions).",
    "Highway classes: which `highway` values counted as 'main' roads (links included or not).",
    "Invalid geometries: skipped, fixed, or causing a step to fail silently in the GUI.",
    "Selection mode: 'create new selection' vs. 'select within current selection' in the GUI.",
    "Input versions: a different download/clip of the OSM data.",
]


def load_features(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("type") != "FeatureCollection":
        raise SystemExit(f"{path} is not a GeoJSON FeatureCollection.")
    return data.get("features", [])


def property_names(features: list[dict]) -> set[str]:
    names: set[str] = set()
    for f in features:
        names.update((f.get("properties") or {}).keys())
    return names


def vertex_mean(geometry: dict | None):
    """Mean of all vertices (lon, lat). Good enough to match the same footprint."""
    pts = []

    def walk(coords):
        if coords and isinstance(coords[0], (int, float)):
            pts.append(coords)
        else:
            for c in coords or []:
                walk(c)

    walk((geometry or {}).get("coordinates"))
    if not pts:
        return None
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def metres_between(a, b) -> float:
    """Haversine distance in metres between (lon, lat) points."""
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(h))


def keys_by_id(features, field) -> dict:
    out = {}
    for f in features:
        value = (f.get("properties") or {}).get(field)
        if value not in (None, ""):
            out[str(value)] = f
    return out


def keys_by_centroid(datasets: dict, tolerance_m: float) -> dict:
    """Give the same key to footprints whose centroids are within tolerance across datasets."""
    anchors: list[tuple[str, tuple]] = []  # (key, point)
    result = {}
    for name, features in datasets.items():
        mapping = {}
        for f in features:
            pt = vertex_mean(f.get("geometry"))
            if pt is None:
                continue
            key = next((k for k, a in anchors if metres_between(pt, a) <= tolerance_m), None)
            if key is None:
                key = f"pt_{pt[1]:.6f}_{pt[0]:.6f}"
                anchors.append((key, pt))
            mapping[key] = f
        result[name] = mapping
    return result


def area_of(feature) -> float | None:
    v = (feature.get("properties") or {}).get("area_sqm")
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare site-selection GeoJSON results")
    parser.add_argument("inputs", nargs="+", help="label=path.geojson (at least two)")
    parser.add_argument("--match", choices=["id", "centroid"], default="id")
    parser.add_argument("--id-field", help="attribute used to match buildings (default: auto)")
    parser.add_argument("--tolerance-m", type=float, default=2.0, help="centroid matching tolerance")
    parser.add_argument("--out-dir", help="folder for the report (default: folder of the first input)")
    args = parser.parse_args()

    datasets: dict[str, list] = {}
    paths: dict[str, Path] = {}
    for item in args.inputs:
        if "=" not in item:
            raise SystemExit(f"Use label=path, e.g. manual=manual.geojson (got '{item}')")
        label, path = item.split("=", 1)
        paths[label] = Path(path)
        datasets[label] = load_features(Path(path))
    if len(datasets) < 2:
        raise SystemExit("Give at least two inputs to compare.")

    # ---- build {label: {key: feature}}
    match_note = ""
    if args.match == "id":
        field = args.id_field
        if not field:
            common = set.intersection(*(property_names(f) for f in datasets.values()))
            field = next((c for c in AUTO_ID_FIELDS if c in common), None)
        if not field:
            raise SystemExit("No shared ID field found. Use --id-field NAME or --match centroid.")
        keyed = {label: keys_by_id(feats, field) for label, feats in datasets.items()}
        match_note = f"by attribute `{field}`"
    else:
        keyed = keys_by_centroid(datasets, args.tolerance_m)
        match_note = f"by footprint position (within {args.tolerance_m:g} m)"

    labels = list(keyed)
    sets = {label: set(keyed[label]) for label in labels}
    all_keys = sorted(set.union(*sets.values()))
    in_all = set.intersection(*sets.values())

    # ---- report
    lines = ["# Site-selection comparison", "", f"Matching {match_note}.", "", "## Counts", "",
             "| Method | File | Candidates | Total area m² |", "|---|---|---:|---:|"]
    for label in labels:
        areas = [a for a in (area_of(f) for f in keyed[label].values()) if a is not None]
        area_txt = f"{sum(areas):,.0f}" if areas else "—"
        lines.append(f"| {label} | `{paths[label].name}` | {len(sets[label])} | {area_txt} |")
    lines += ["", f"Selected by **all** methods: **{len(in_all)}** of {len(all_keys)} distinct buildings.", "",
              "## Pairwise agreement", "",
              "| A | B | Both | Only A | Only B | Jaccard |", "|---|---|---:|---:|---:|---:|"]
    for a, b in combinations(labels, 2):
        both, only_a, only_b = sets[a] & sets[b], sets[a] - sets[b], sets[b] - sets[a]
        union = sets[a] | sets[b]
        jac = len(both) / len(union) if union else 1.0
        lines.append(f"| {a} | {b} | {len(both)} | {len(only_a)} | {len(only_b)} | {jac:.2f} |")

    disagreements = [k for k in all_keys if k not in in_all]
    lines += ["", "## Buildings not selected by every method", ""]
    if disagreements:
        lines += ["| Building key | " + " | ".join(labels) + " | area m² |",
                  "|---|" + "---|" * len(labels) + "---:|"]
        for k in disagreements:
            area = next((area_of(keyed[l][k]) for l in labels if k in keyed[l] and area_of(keyed[l][k]) is not None), None)
            marks = " | ".join("✔" if k in sets[l] else "" for l in labels)
            lines.append(f"| {k} | {marks} | {area:,.1f} |" if area is not None else f"| {k} | {marks} | — |")
        lines += ["", "Tip: an area close to 800 or 1,200 m² usually points to the area-calculation difference."]
    else:
        lines.append("None - all methods selected exactly the same buildings. ✅")

    lines += ["", "## Usual causes of differences (check these first)", ""] + [f"- {c}" for c in LIKELY_CAUSES]

    out_dir = Path(args.out_dir) if args.out_dir else paths[labels[0]].resolve().parent
    out_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / "comparison_report.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    membership = out_dir / "comparison_membership.csv"
    with membership.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["key"] + labels + ["selected_by_all"])
        for k in all_keys:
            writer.writerow([k] + [int(k in sets[l]) for l in labels] + [int(k in in_all)])

    # Print the counts + pairwise tables; the full detail is in the report file.
    print("\n".join(lines[: lines.index("## Buildings not selected by every method")]))
    print(f"\nReport:     {report}\nMembership: {membership}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
