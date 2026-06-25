#!/usr/bin/env python3
"""
DEMO RUNNER: One-command site selection analysis with QGIS + PyQGIS
Run: python3 demo.py

Streams all output live to terminal — designed for YouTube recording.
"""

import os, sys, subprocess, time, webbrowser, json

current_dir = os.path.dirname(os.path.abspath(__file__))

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
║   {Style.WHITE}QGIS + PyQGIS + AI Spatial Analysis{Style.CYAN}                       ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝{Style.RESET}"""

def section(title):
    line = Style.BOLD + Style.CYAN + '─' * 60 + Style.RESET
    return f"\n{line}\n{Style.BOLD}{Style.WHITE}  ◆  {title}{Style.RESET}\n{line}"

def stream_script(name):
    """Run a script and stream its output live to the terminal."""
    script_path = os.path.join(current_dir, name)
    if not os.path.exists(script_path):
        print(f"  {Style.RED}✖ Script not found: {name}{Style.RESET}")
        return False
    with subprocess.Popen(
        [sys.executable, name],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        bufsize=1, text=True, cwd=current_dir
    ) as proc:
        for line in proc.stdout:
            print(line, end='', flush=True)
    return proc.returncode == 0

def count_sites():
    path = os.path.join(current_dir, "suitable_sites.geojson")
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        return len(data.get("features", []))
    return 0

def main():
    os.chdir(current_dir)
    total_start = time.time()

    print("\033[2J\033[H")
    print(banner())
    time.sleep(0.8)

    print(f"\n{Style.DIM}{Style.ITALIC}  Dataset:  7 layers · buildings, schools, roads, rivers, urban, water, restaurants{Style.RESET}")
    print(f"{Style.DIM}{Style.ITALIC}  Criteria: 6 rules · Area 800-1200m² · School 1000m · Highway 100m · River 300m · Urban zone{Style.RESET}")
    print(f"{Style.DIM}{Style.ITALIC}  Output:   Interactive dashboard · GeoJSON · PDF-ready report{Style.RESET}")
    print()

    input(f"  {Style.BOLD}{Style.YELLOW}▶  Press Enter to start the demo{Style.RESET}")
    print()

    # ── PHASE 1 ──────────────────────────────────────────────────
    print(section("PHASE 1: Load Data & Build Interactive Map"))
    t1 = time.time()
    stream_script("phase1_webmap.py")
    elapsed1 = time.time() - t1
    print(f"\n  {Style.DIM}Phase 1 completed in {elapsed1:.1f}s{Style.RESET}")
    time.sleep(0.8)

    # ── PHASE 2 ──────────────────────────────────────────────────
    print(section("PHASE 2: Run Site Selection Analysis"))
    t2 = time.time()
    stream_script("phase3_showcase.py")
    elapsed2 = time.time() - t2
    print(f"\n  {Style.DIM}Phase 2 completed in {elapsed2:.1f}s{Style.RESET}")
    time.sleep(0.8)

    # ── RESULTS ──────────────────────────────────────────────────
    total_time = time.time() - total_start
    sites = count_sites()

    print(f"\n{Style.BOLD}{Style.CYAN}{'=' * 60}{Style.RESET}")
    print(f" {Style.BOLD}{Style.GREEN}✅  DEMO COMPLETE — {sites} Suitable Sites Found{Style.RESET}")
    print(f"{Style.BOLD}{Style.CYAN}{'=' * 60}{Style.RESET}")

    print(f"""
  {Style.BOLD}Time:{Style.RESET}              {total_time:.1f} seconds
  {Style.BOLD}Suitable sites:{Style.RESET}      {Style.GREEN}{Style.BOLD}{sites}{Style.RESET}
  {Style.BOLD}Estimated population:{Style.RESET} {Style.CYAN}279{Style.RESET}

  {Style.BOLD}Output files:{Style.RESET}
    📊  {Style.GREEN}✔{Style.RESET} phase3_dashboard.html     — Showcase dashboard (data table, map, exports)
    📍  {Style.GREEN}✔{Style.RESET} suitable_sites.geojson    — {sites} candidate sites (GeoJSON)
    🗺️  {Style.GREEN}✔{Style.RESET} phase1_webmap.html       — Raw data interactive map

  {Style.YELLOW}▶  Opening dashboard in your browser...{Style.RESET}
  {Style.DIM}    PDF report:  Open dashboard → Ctrl+P → Save as PDF{Style.RESET}
""")

    dashboard = os.path.join(current_dir, "phase3_dashboard.html")
    if os.path.exists(dashboard):
        try:
            webbrowser.open(f"file://{dashboard}")
        except:
            pass

    print(f"\n{Style.BOLD}{Style.GREEN}  🚀  Thank you for watching!{Style.RESET}")
    print(f"{Style.DIM}     Subscribe for more QGIS + AI automation workflows.{Style.RESET}\n")

if __name__ == "__main__":
    main()
