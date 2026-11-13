#!/usr/bin/env python3
"""
DEMO RUNNER: One-command site selection analysis with QGIS + PyQGIS
Run: python3 demo.py

Streams all output live to the terminal - designed for YouTube recording.

    python3 demo.py                   # full demo, waits for Enter, opens the dashboard
    python3 demo.py --skip-phase1     # analysis + dashboard only
    python3 demo.py --no-pause        # no "Press Enter" (for scripted/automatic runs)
    python3 demo.py --no-browser      # do not open the dashboard at the end
    python3 demo.py --config my_town.json

Why each phase runs as its own process
--------------------------------------
QGIS can only be started and stopped cleanly once per process, so Phase 1 and
Phase 2 must not run inside the same Python process. Every phase is started
with the same interpreter as this demo (sys.executable), so run the demo with
the QGIS Python:
    Linux:   python3 demo.py
    Windows: python-qgis-ltr.bat demo.py      (in the OSGeo4W Shell)
    macOS:   /Applications/QGIS.app/Contents/MacOS/bin/python3 demo.py
"""

from __future__ import annotations  # allows "str | None" hints on Python 3.8/3.9 (older QGIS)

import argparse
import json
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

current_dir = Path(__file__).resolve().parent

# FIX (Windows): make this console print UTF-8 box characters/emoji and turn on
# ANSI colours. Without this, the banner and the ✅/✔ symbols can crash or
# show as garbage in the Windows console.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (ValueError, OSError):
        pass
if os.name == "nt":
    os.system("")  # enables ANSI escape codes in Windows 10+ consoles


class Style:
    BOLD = '\033[1m'
    DIM = '\033[2m'
    ITALIC = '\033[3m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'


def banner():
    return f"""
{Style.BOLD}{Style.CYAN}╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ╔═╗╔═╗╔═╗╔═══╗╔══╗╔═╗╔═╗╔══╗╔══╗╔═══╗╔══╗╔═╗╔═╗╔═══╗   ║
║   ║ ╚╝ ║║ ║║╔══╝║╔╗║║ ║║ ║║╔╗║║╔╗║║╔══╝║╔╗║║ ║║ ║║╔══╝   ║
║   ║ ╔╗ ║║ ║║╚══╗║╚╝║║ ╚╝ ║║╚╝║║╚╝║║╚══╗║╚╝║║ ╚╝ ║║╚══╗   ║
║   ║ ║║ ║║ ║║╔══╝║╔╗║║ ╔╗ ║║╔╗║║╔╗║║╔══╝║╔╗║║ ╔╗ ║║╔══╝   ║
║   ║ ║║ ║║ ║║╚══╗║║║║║ ║║ ║║║║║║║║║║╚══╗║║║║║ ║║ ║║╚══╗   ║
║   ╚═╝╚═╝╚═╝╚═══╝╚╝╚╝╚═╝╚═╝╚╝╚╝╚╝╚╝╚═══╝╚╝╚╝╚═╝╚═╝╚═══╝   ║
║                                                              ║
║   {Style.WHITE}Automated Site Selection{Style.CYAN}                                  ║
║   {Style.WHITE}QGIS + PyQGIS Automated GIS Baseline{Style.CYAN}                       ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝{Style.RESET}"""


def section(title):
    line = Style.BOLD + Style.CYAN + '─' * 60 + Style.RESET
    return f"\n{line}\n{Style.BOLD}{Style.WHITE}  ◆  {title}{Style.RESET}\n{line}"


def load_json(path: Path):
    """Read a JSON file as UTF-8, or return None if it is missing."""
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_settings(config: str | None) -> dict:
    """Read config.json (or --config) so the intro text always matches the real criteria."""
    path = Path(config).resolve() if config else current_dir / "config.json"
    return load_json(path) or {}


def stream_script(name, config=None):
    """Run a script in its own process and stream its output live to the terminal."""
    script_path = current_dir / name
    if not script_path.is_file():
        print(f"  {Style.RED}✖ Script not found: {name}{Style.RESET}")
        return False
    cmd = [sys.executable, str(script_path)]
    if config:
        cmd += ["--config", config]
    # FIX: when output goes through a pipe, Python buffers it, so the phase
    # output arrived in big bursts instead of live. PYTHONUNBUFFERED makes it
    # stream line by line (important for recording).
    # FIX (Windows): PYTHONIOENCODING=utf-8 stops the child scripts crashing
    # with UnicodeEncodeError when they print ✅, m², arrows or emoji.
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    with subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        bufsize=1, text=True, encoding="utf-8", errors="replace",
        cwd=current_dir, env=env,
    ) as proc:
        for line in proc.stdout:
            print(line, end='', flush=True)
    return proc.returncode == 0  # returncode is set once the 'with' block has waited


def check_sites_are_lonlat(path: Path) -> bool:
    """NEW: every coordinate in suitable_sites.geojson must be valid lon/lat.

    Catches the bug fixed in this version (GeoJSON written in UTM metres),
    which would otherwise show an empty or broken map in the dashboard.
    """
    data = load_json(path) or {}

    def coords(c):
        if c and isinstance(c[0], (int, float)):
            yield c
        else:
            for item in c or []:
                yield from coords(item)

    for feature in data.get("features", []):
        for x, y, *_ in coords((feature.get("geometry") or {}).get("coordinates")):
            if not (-180 <= x <= 180 and -90 <= y <= 90):
                print(f"\n  {Style.RED}✖ {path.name} has coordinate ({x}, {y}) - not longitude/latitude.{Style.RESET}")
                print(f"  {Style.RED}  Make sure the fixed qgis_common.py is next to the scripts.{Style.RESET}")
                return False
    print(f"  {Style.GREEN}✔{Style.RESET} {path.name}: coordinates are longitude/latitude")
    return True


def run_phase(number, title, script, config):
    """Print the section header, run the script, return elapsed seconds or None on failure."""
    print(section(f"PHASE {number}: {title}"))
    start = time.time()
    if not stream_script(script, config):
        return None
    elapsed = time.time() - start
    print(f"\n  {Style.DIM}Phase {number} completed in {elapsed:.1f}s{Style.RESET}")
    time.sleep(0.8)
    return elapsed


def main():
    parser = argparse.ArgumentParser(description="One-command site selection demo")
    parser.add_argument("--config", help="config JSON passed to every phase (default: config.json)")
    parser.add_argument("--skip-phase1", action="store_true", help="skip the data exploration map")
    parser.add_argument("--skip-mce", action="store_true", help="skip Phase 2b (multi-criteria evaluation)")
    parser.add_argument("--no-pause", action="store_true", help="do not wait for Enter")
    parser.add_argument("--no-browser", action="store_true", help="do not open the dashboard")
    args = parser.parse_args()
    config = str(Path(args.config).resolve()) if args.config else None

    os.chdir(current_dir)
    # Outputs are written next to the config file (default: this folder).
    out_dir = Path(config).parent if config else current_dir
    settings = load_settings(config)
    crit = settings.get("criteria", {})
    total_start = time.time()
    # Phase 2b (MCE) is part of v2.0. In v1.0 (Boolean screening) the script is not
    # there, so the demo simply skips it - the same demo.py works for both versions.
    has_mce = (current_dir / "phase2b_mce.py").is_file()

    print("\033[2J\033[H")
    print(banner())
    time.sleep(0.8)

    # FIX: criteria text is read from config.json instead of being hard-coded,
    # so the video intro never disagrees with what the analysis really did.
    rules = (
        f"Area {crit.get('min_area_sqm', 800):g}-{crit.get('max_area_sqm', 1200):g}m² · "
        f"School {crit.get('school_distance_m', 1000):g}m · "
        f"Highway {crit.get('highway_exclusion_m', 100):g}m · "
        f"River {crit.get('river_exclusion_m', 300):g}m · "
        f"Urban ({crit.get('urban_relation', 'intersects')})"
    )
    print(f"\n{Style.DIM}{Style.ITALIC}  Phase 0:  study area -> one metric CRS -> fix -> clip (reference layers + edge buffer){Style.RESET}")
    print(f"{Style.DIM}{Style.ITALIC}  Dataset:  buildings, schools, roads, rivers, urban (+ water, restaurants on the Phase 1 map){Style.RESET}")
    print(f"{Style.DIM}{Style.ITALIC}  Criteria: {rules}{Style.RESET}")
    print(f"{Style.DIM}{Style.ITALIC}  Then:     population proxy + suitability score to rank the candidates{Style.RESET}")
    if has_mce:
        print(f"{Style.DIM}{Style.ITALIC}  Phase 2b: multi-criteria evaluation (constraints + weighted factors, AHP) vs the Boolean result{Style.RESET}")
    print(f"{Style.DIM}{Style.ITALIC}  Output:   Interactive dashboard · GeoJSON · PDF-ready report{Style.RESET}")
    print()

    if not args.no_pause:
        input(f"  {Style.BOLD}{Style.YELLOW}▶  Press Enter to start the demo{Style.RESET}")
        print()

    timings = {}

    # ── PHASE 0 (data preparation) ──────────────────────────────
    if settings.get("study_area", {}).get("enabled", True):
        t = run_phase(0, "Prepare Data: Study Area, CRS, Fix, Clip", "phase0_prepare_data.py", config)
        if t is None:
            print(f"\n  {Style.RED}Phase 0 failed. Check the study_area settings in config.json.{Style.RESET}")
            return 1
        timings[0] = t

    # ── PHASE 1 ──────────────────────────────────────────────────
    if args.skip_phase1:
        print(f"\n  {Style.DIM}(Phase 1 skipped){Style.RESET}")
    else:
        t = run_phase(1, "Load Data & Build Interactive Map", "phase1_webmap.py", config)
        if t is None:
            print(f"\n  {Style.RED}Phase 1 failed. Correct the QGIS/Python setup before continuing.{Style.RESET}")
            return 1
        timings[1] = t

    # ── PHASE 2 ──────────────────────────────────────────────────
    t = run_phase(2, "Run Site Selection Analysis", "phase2_site_selection.py", config)
    if t is None:
        print(f"\n  {Style.RED}Phase 2 failed. Dashboard generation stopped.{Style.RESET}")
        return 1
    timings[2] = t
    if not check_sites_are_lonlat(out_dir / "suitable_sites.geojson"):
        print(f"\n  {Style.RED}Dashboard generation stopped.{Style.RESET}")
        return 1

    # ── PHASE 2b (MCE) ───────────────────────────────────────────
    if not has_mce:
        pass  # v1.0: Boolean screening only
    elif args.skip_mce:
        print(f"\n  {Style.DIM}(Phase 2b MCE skipped){Style.RESET}")
    else:
        t = run_phase("2b", "Multi-Criteria Evaluation (weighted overlay)", "phase2b_mce.py", config)
        if t is None:
            print(f"\n  {Style.RED}Phase 2b failed. Continuing with the Boolean result only.{Style.RESET}")
        else:
            timings["2b"] = t

    # ── PHASE 3 ──────────────────────────────────────────────────
    t = run_phase(3, "Build Dashboard from Analysis Outputs", "phase3_showcase.py", config)
    if t is None:
        print(f"\n  {Style.RED}Phase 3 failed. Check the messages above.{Style.RESET}")
        return 1
    timings[3] = t

    # ── RESULTS ──────────────────────────────────────────────────
    total_time = time.time() - total_start
    sites_data = load_json(out_dir / "suitable_sites.geojson") or {}
    features = sites_data.get("features", [])
    summary = load_json(out_dir / "site_selection_summary.json") or {}
    population = float(summary.get("population_proxy_total", 0.0))
    counts = summary.get("counts", {})

    print(f"\n{Style.BOLD}{Style.CYAN}{'=' * 60}{Style.RESET}")
    print(f" {Style.BOLD}{Style.GREEN}✅  DEMO COMPLETE — {len(features)} Suitable Sites Found{Style.RESET}")
    print(f"{Style.BOLD}{Style.CYAN}{'=' * 60}{Style.RESET}")

    # NEW: the filter cascade, read from the Phase 2 summary - nice on screen.
    if counts:
        print(f"\n  {Style.BOLD}Filter cascade:{Style.RESET}")
        cascade = [
            ("All buildings", counts.get("total_buildings")),
            ("A  area", counts.get("step_a_area")),
            ("B  + near school", counts.get("step_b_school")),
            ("C  + not near highway", counts.get("step_c_highway")),
            ("D  + not near river", counts.get("step_d_river")),
            ("E  + urban area", counts.get("final")),
        ]
        top = max((n for _, n in cascade if n), default=1)
        for label, n in cascade:
            if n is None:
                continue
            bar = "█" * max(1, round(30 * n / top)) if n else ""
            print(f"    {label:24s} {Style.CYAN}{bar}{Style.RESET} {n:,}")

    # NEW: top-ranked sites (rank / suit_score are added by the fixed Phase 2).
    ranked = sorted(
        (f.get("properties") or {} for f in features),
        key=lambda p: p.get("rank") if p.get("rank") is not None else 10**9,
    )[:3]
    if ranked and ranked[0].get("rank") is not None:
        print(f"\n  {Style.BOLD}Top-ranked sites:{Style.RESET}")
        for p in ranked:
            label = p.get("name") or p.get("source_id") or f"Site {p.get('site_id')}"
            print(f"    #{p['rank']}  score {p.get('suit_score', 0):.2f}  ·  {float(p.get('area_sqm') or 0):,.0f} m²  ·  {label}")

    # NEW: Boolean vs MCE, read from the Phase 2b summary.
    mce_summary = load_json(out_dir / "mce_summary.json") if "2b" in timings else None
    if mce_summary:
        weights = ", ".join(f"{k} {v:.2f}" for k, v in mce_summary.get("weights", {}).items())
        print(f"\n  {Style.BOLD}Multi-criteria evaluation:{Style.RESET}")
        print(f"    Weights {weights}" + (f"  ·  AHP CR {mce_summary['weights_info']['cr']:.3f}"
                                         if "cr" in mce_summary.get("weights_info", {}) else ""))
        print(f"    {mce_summary['counts']['selected']} sites selected ({mce_summary['selection']['note']})")
        comp = mce_summary.get("comparison")
        if comp:
            print(f"    {Style.GREEN}■{Style.RESET} both methods {comp['both']}   "
                  f"{Style.MAGENTA}■{Style.RESET} MCE only {comp['mce_only']}   "
                  f"{Style.YELLOW}■{Style.RESET} Boolean only {comp['boolean_only']}   "
                  f"(agreement {comp['jaccard']:.2f})")

    phase_times = "  ·  ".join(f"P{n} {s:.1f}s" for n, s in timings.items())
    print(f"""
  {Style.BOLD}Time:{Style.RESET}              {total_time:.1f} seconds   {Style.DIM}({phase_times}){Style.RESET}
  {Style.BOLD}Suitable sites:{Style.RESET}      {Style.GREEN}{Style.BOLD}{len(features)}{Style.RESET}
  {Style.BOLD}Population proxy total:{Style.RESET} {Style.CYAN}{population:.0f}{Style.RESET}

  {Style.BOLD}Output files:{Style.RESET}""")

    # FIX: each file gets ✔ only if it really exists (was always ✔ before).
    outputs = [
        ("📊", "phase3_dashboard.html", "Showcase dashboard (map, ranked table, exports)"),
        ("📍", "suitable_sites.geojson", f"{len(features)} candidate sites (GeoJSON, WGS 84)"),
        ("📄", "site_selection_summary.json", "Criteria, counts, QGIS version"),
        ("🎯", "suitable_sites_mce.geojson", "MCE selected sites (scores, stability, agreement)"),
        ("⚖️", "mce_vs_boolean.geojson", "Boolean vs MCE: both / mce_only / boolean_only"),
        ("🗺️", "phase2b_mce.html", "MCE score map"),
        ("🗺️", "phase2_site_selection.html", "Analysis quick-look map"),
        ("🗺️", "phase1_webmap.html", "Raw data interactive map"),
    ]
    for icon, filename, description in outputs:
        if (args.skip_mce or not has_mce) and "mce" in filename:
            continue
        exists = (out_dir / filename).is_file()
        mark = f"{Style.GREEN}✔{Style.RESET}" if exists else f"{Style.RED}✖{Style.RESET}"
        print(f"    {icon}  {mark} {filename:28s} — {description}")

    dashboard = out_dir / "phase3_dashboard.html"
    if not args.no_browser and dashboard.is_file():
        print(f"\n  {Style.YELLOW}▶  Opening dashboard in your browser...{Style.RESET}")
        print(f"  {Style.DIM}    PDF report:  Open dashboard → Print / PDF → Save as PDF{Style.RESET}")
        try:
            # FIX: as_uri() builds a correct file:/// URL on Windows too
            # (f"file://{path}" breaks with C:\ backslashes and spaces).
            webbrowser.open(dashboard.as_uri())
        except Exception:
            pass

    print(f"\n{Style.BOLD}{Style.GREEN}  🚀  Thank you for watching!{Style.RESET}")
    print(f"{Style.DIM}     Subscribe for more QGIS + AI automation workflows.{Style.RESET}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
