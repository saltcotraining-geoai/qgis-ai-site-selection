"""Shared PyQGIS helpers for Phase 1 and Phase 2.

Import this module BEFORE anything from `qgis` - it sets up the Python path so
that `qgis.core` and the Processing plugin can be found in a standalone script.

Contents
--------
- init_qgis()        start a headless QGIS (optionally with Processing)
- shutdown_qgis()    release layers and stop QGIS cleanly (avoids exit crashes)
- ConsoleFeedback    print Processing messages to the terminal
- run_alg()          processing.run() with a clear error message
- output_layer()     get a QgsVectorLayer from a Processing result
- load_vector()      open dataset/<name>.gpkg|layername=<name>
- save_vector()      write a layer to GPKG/GeoJSON, reprojecting correctly
- qgis_version()     QGIS version string, recorded in the summary for reproducibility
- simplify_layer()   Douglas-Peucker + Fix Geometries, with a vertex count before/after
- set_geojson_precision()  coordinate decimals for GeoJSON output (from config)
"""

from __future__ import annotations

import gc
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# STEP 0 - Make PyQGIS importable from a plain terminal.
# ---------------------------------------------------------------------------
# Headless Qt: lets the script run on servers / over SSH without a display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _default_prefix() -> str:
    """Typical QGIS install prefix per platform. Override with QGIS_PREFIX_PATH."""
    if sys.platform.startswith("win"):
        # OSGeo4W default. The QGIS LTR package uses ...\apps\qgis-ltr instead.
        return r"C:\OSGeo4W\apps\qgis"
    if sys.platform == "darwin":
        return "/Applications/QGIS.app/Contents/MacOS"
    return "/usr"  # Debian / Ubuntu / Fedora packages


QGIS_PREFIX = os.environ.get("QGIS_PREFIX_PATH", _default_prefix())

_python_dir_candidates = [
    os.environ.get("QGIS_PYTHON_DIR"),
    os.path.join(QGIS_PREFIX, "share", "qgis", "python"),            # Linux
    os.path.join(QGIS_PREFIX, "python"),                             # Windows OSGeo4W
    os.path.join(os.path.dirname(QGIS_PREFIX), "Resources", "python"),  # macOS bundle
]
for _dir in _python_dir_candidates:
    if _dir and os.path.isdir(_dir):
        for _p in (_dir, os.path.join(_dir, "plugins")):  # plugins/ holds `processing`
            if _p not in sys.path and os.path.isdir(_p):
                sys.path.insert(0, _p)
        break

try:
    from qgis.core import (
        Qgis,
        QgsApplication,
        QgsCoordinateReferenceSystem,
        QgsCoordinateTransform,
        QgsProcessingFeedback,
        QgsProject,
        QgsVectorFileWriter,
        QgsVectorLayer,
        QgsWkbTypes,
    )
except ImportError as exc:  # pragma: no cover - depends on the environment
    _venv = os.environ.get("VIRTUAL_ENV") or os.environ.get("CONDA_PREFIX")
    raise SystemExit(
        "PyQGIS could not be imported.\n"
        f"  This script is running with: {sys.executable} (Python {sys.version.split()[0]})\n"
        + (f"  A virtual/conda environment is active: {_venv}\n"
           "  -> it cannot see QGIS. Run 'deactivate' (or 'conda deactivate'), or create the venv with\n"
           "     python3 -m venv --system-site-packages <folder>\n" if _venv else "")
        + "  Test the QGIS Python with:  python3 -c \"import qgis.core; print(qgis.core.Qgis.version())\"\n"
        "  Linux:   run with the system python3 that QGIS uses (e.g. /usr/bin/python3)\n"
        "  Windows: run from the 'OSGeo4W Shell' (python-qgis.bat / python-qgis-ltr.bat)\n"
        "  macOS:   /Applications/QGIS.app/Contents/MacOS/bin/python3\n"
        "Set QGIS_PREFIX_PATH if QGIS is installed somewhere else.\n"
        f"Original import error: {exc}"
    ) from exc

def wgs84() -> QgsCoordinateReferenceSystem:
    """EPSG:4326. A function, not a module constant: FIX - creating a CRS before
    QgsApplication.initQgis() prints "Application path not initialized"."""
    return QgsCoordinateReferenceSystem("EPSG:4326")


# ---------------------------------------------------------------------------
# Start / stop QGIS
# ---------------------------------------------------------------------------
def init_qgis(with_processing: bool = True) -> QgsApplication:
    """Start QGIS without a GUI. With Processing, the native algorithms are registered."""
    QgsApplication.setPrefixPath(QGIS_PREFIX, True)
    app = QgsApplication([], False)  # False = no GUI
    app.initQgis()

    if with_processing:
        from processing.core.Processing import Processing
        from qgis.analysis import QgsNativeAlgorithms

        Processing.initialize()
        registry = QgsApplication.processingRegistry()
        if registry.providerById("native") is None:
            if not registry.addProvider(QgsNativeAlgorithms()):
                raise RuntimeError("Could not register the QGIS native Processing provider.")
    return app


def shutdown_qgis(app: QgsApplication) -> None:
    """Stop QGIS safely.

    FIX: exitQgis() while Python still holds QgsVectorLayer objects can crash
    (segfault) on some builds. Callers should let their layers go out of scope
    first (e.g. keep them inside a function that has returned); we then clear
    the project and force garbage collection before exiting.
    """
    QgsProject.instance().clear()
    gc.collect()
    app.exitQgis()


def qgis_version() -> str:
    return Qgis.version()


# ---------------------------------------------------------------------------
# Processing helpers
# ---------------------------------------------------------------------------
class ConsoleFeedback(QgsProcessingFeedback):
    """Print Processing messages to the terminal.

    verbose=False shows only warnings and errors (cleaner for students);
    verbose=True also shows every INFO/CMD line, like the Processing log panel.
    """

    def __init__(self, verbose: bool = False):
        super().__init__()
        self.verbose = verbose

    def pushInfo(self, info: str) -> None:
        if self.verbose and info:
            print(f"      [INFO] {info}")

    def pushCommandInfo(self, info: str) -> None:
        if self.verbose and info:
            print(f"      [CMD] {info}")

    def pushDebugInfo(self, info: str) -> None:
        if self.verbose and info:
            print(f"      [DEBUG] {info}")

    def pushWarning(self, warning: str) -> None:
        if warning:
            print(f"      [WARNING] {warning}")

    def reportError(self, error: str, fatalError: bool = False) -> None:
        if error:
            print(f"      [PROCESSING ERROR] {error}")


def run_alg(algorithm_id: str, parameters: dict, label: str, feedback: QgsProcessingFeedback) -> dict:
    """processing.run() with a printed label and a readable error if it fails."""
    import processing  # available after init_qgis(with_processing=True)

    print(f"  -> {label}   [{algorithm_id}]")
    try:
        result = processing.run(algorithm_id, parameters, feedback=feedback)
    except Exception as exc:
        raise RuntimeError(f"Processing step failed: {label} ({algorithm_id})\n{exc}") from exc
    if not isinstance(result, dict):
        raise RuntimeError(f"Processing step '{label}' returned no result dictionary.")
    return result


def output_layer(result: dict, key: str, name: str) -> QgsVectorLayer:
    """Return result[key] as a valid QgsVectorLayer (memory layer or file path)."""
    output = result.get(key)
    layer = output if isinstance(output, QgsVectorLayer) else QgsVectorLayer(str(output), name, "ogr")
    if not layer.isValid():
        raise RuntimeError(f"Processing output '{name}' is not a valid vector layer: {output}")
    layer.setName(name)
    # FIX: memory layers from Processing have no spatial index, which caused the
    # "No spatial index exists for input layer" warnings in Extract by Location.
    # (GUI equivalent: Processing > Vector general > Create spatial index.)
    if layer.providerType() == "memory":
        layer.dataProvider().createSpatialIndex()
    return layer


# ---------------------------------------------------------------------------
# Reading / writing
# ---------------------------------------------------------------------------
def make_field(name: str, kind: str):
    """QgsField of kind 'int' | 'double' | 'string' for any QGIS 3.x.

    FIX: QGIS 3.38+ deprecates QgsField(name, QVariant.Type) in favour of
    QMetaType, which older versions do not accept - so pick by version.
    """
    from qgis.core import QgsField
    if Qgis.QGIS_VERSION_INT >= 33800:
        from qgis.PyQt.QtCore import QMetaType
        types = {"int": QMetaType.Type.Int, "double": QMetaType.Type.Double, "string": QMetaType.Type.QString}
    else:
        from qgis.PyQt.QtCore import QVariant
        types = {"int": QVariant.Int, "double": QVariant.Double, "string": QVariant.String}
    return QgsField(name, types[kind])


def load_vector(dataset_dir: Path, name: str, required: bool = True) -> QgsVectorLayer | None:
    """Open dataset/<name>.gpkg|layername=<name> and check it has a valid CRS."""
    path = Path(dataset_dir) / f"{name}.gpkg"
    if not path.is_file():
        if required:
            raise FileNotFoundError(f"Required input layer is missing: {path}")
        print(f"  [WARN] {path.name} not found - skipped")
        return None
    layer = QgsVectorLayer(f"{path}|layername={name}", name, "ogr")
    if not layer.isValid():
        if required:
            raise RuntimeError(f"Could not load GeoPackage layer '{name}' from {path}")
        print(f"  [WARN] could not load {path.name} - skipped")
        return None
    if not layer.crs().isValid():
        raise RuntimeError(f"Layer '{name}' has no valid coordinate reference system.")
    return layer


def _remove_owned_output(path: Path) -> None:
    """Delete an output file this script owns (plus GeoPackage -wal/-shm side files)."""
    for candidate in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        if candidate.is_file():
            candidate.unlink()


def save_vector(
    layer: QgsVectorLayer,
    path: Path,
    driver_name: str,
    target_crs: QgsCoordinateReferenceSystem | None = None,
) -> Path:
    """Write `layer` to `path` (driver 'GPKG' or 'GeoJSON'), optionally reprojected.

    FIX (critical): the original code set `options.targetCrs`. SaveVectorOptions
    has no such attribute; PyQGIS accepted the assignment silently and ignored
    it, so "WGS 84" GeoJSON files were actually written in UTM metres.
    Reprojection on export is done through `options.ct` (a QgsCoordinateTransform).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _remove_owned_output(path)

    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = driver_name
    options.fileEncoding = "UTF-8"
    if driver_name == "GPKG":
        options.layerName = path.stem
    if driver_name == "GeoJSON":
        # RFC 7946 = the modern GeoJSON standard: WGS 84 lon/lat, 7 decimals.
        # GDAL also reprojects to WGS 84 when this is on - a second safety net.
        options.layerOptions = ["RFC7946=YES", "WRITE_NAME=NO", f"COORDINATE_PRECISION={GEOJSON_PRECISION}"]
        if target_crs is None:
            target_crs = wgs84()
    if target_crs is not None and target_crs != layer.crs():
        options.ct = QgsCoordinateTransform(layer.crs(), target_crs, QgsProject.instance())

    result = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, str(path), QgsProject.instance().transformContext(), options
    )
    error_code = result[0]
    error_message = result[1] if len(result) > 1 else ""
    if error_code != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"Could not write {path}: {error_message}")
    return path


# ---------------------------------------------------------------------------
# Performance: fewer vertices, smaller files
# ---------------------------------------------------------------------------
GEOJSON_PRECISION = 7          # decimals in GeoJSON coordinates (7 = ~1 cm); set from config
SIMPLIFY_LOG: dict = {}        # layer name -> {"tolerance_m", "vertices_before", "vertices_after"}


def set_geojson_precision(cfg: dict) -> None:
    """Use performance.geojson_precision from config (6 decimals = ~11 cm, smaller files)."""
    global GEOJSON_PRECISION
    GEOJSON_PRECISION = int(cfg.get("performance", {}).get("geojson_precision", 7))


def count_vertices(layer: QgsVectorLayer) -> int:
    return sum(f.geometry().constGet().nCoordinates() for f in layer.getFeatures()
               if f.hasGeometry() and not f.geometry().isEmpty())


def is_point_layer(layer: QgsVectorLayer) -> bool:
    return "Point" in QgsWkbTypes.displayString(layer.wkbType())


def simplify_layer(layer: QgsVectorLayer, tolerance_m: float | None, name: str, feedback,
                   fix_first: bool = False) -> QgsVectorLayer:
    """Douglas-Peucker simplification, then Fix Geometries again. Returns a new memory layer.

    Why: fewer vertices = faster buffers / overlays / distance checks and smaller
    web files. Simplifying can create self-intersections, so geometries are fixed
    AFTER simplifying (and before too with fix_first=True, for raw input layers).
    Point layers and tolerance None/0 are returned unchanged.
    tolerance_m is in metres; for a layer in degrees (EPSG:4326, web copies in
    Phase 1) it is converted with 1 degree = 111,320 m - close enough for display.
    GUI equivalent: Vector > Geometry Tools > Simplify (Distance / Douglas-Peucker),
    then Fix Geometries.
    """
    if not tolerance_m or is_point_layer(layer):
        return layer
    tolerance = tolerance_m / 111320.0 if layer.crs().isGeographic() else tolerance_m
    if fix_first:  # raw input (e.g. Phase 1): Processing stops on invalid geometries, so fix before simplifying
        layer = output_layer(
            run_alg("native:fixgeometries", {"INPUT": layer, "OUTPUT": "TEMPORARY_OUTPUT"},
                    f"Fix geometries of {name}", feedback),
            "OUTPUT", f"{name}_fixed")
    before = count_vertices(layer)
    simplified = output_layer(
        run_alg("native:simplifygeometries",
                {"INPUT": layer, "METHOD": 0, "TOLERANCE": tolerance, "OUTPUT": "TEMPORARY_OUTPUT"},
                f"Simplify {name} (Douglas-Peucker, {tolerance_m:g} m)", feedback),
        "OUTPUT", f"{name}_simplified")
    fixed = output_layer(
        run_alg("native:fixgeometries", {"INPUT": simplified, "OUTPUT": "TEMPORARY_OUTPUT"},
                f"Fix geometries of simplified {name}", feedback),
        "OUTPUT", name)
    after = count_vertices(fixed)
    SIMPLIFY_LOG[name] = {"tolerance_m": tolerance_m, "vertices_before": before, "vertices_after": after}
    pct = (1 - after / before) * 100 if before else 0
    print(f"      vertices {before:,} -> {after:,} ({pct:.0f}% fewer)")
    return fixed


def extent_in_wgs84(layer: QgsVectorLayer):
    """Layer extent as a QgsRectangle in EPSG:4326."""
    extent = layer.extent()
    target = wgs84()
    if layer.crs() != target:
        extent = QgsCoordinateTransform(layer.crs(), target, QgsProject.instance()).transformBoundingBox(extent)
    return extent
