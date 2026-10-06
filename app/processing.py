from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry
from pyproj import CRS

from .config import MAX_ZIP_FILES

ALLOWED_KML = {".kml"}
ALLOWED_ARCHIVE = {".zip"}
REQUIRED_SHP_PARTS = {".shp", ".shx", ".dbf"}


def _safe_extract_zip(zip_path: Path, destination: Path) -> Path:
    with zipfile.ZipFile(zip_path) as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        if len(members) > MAX_ZIP_FILES:
            raise ValueError(f"ZIP contains too many files; maximum is {MAX_ZIP_FILES}.")

        for member in members:
            name = Path(member.filename)
            if name.is_absolute() or ".." in name.parts:
                raise ValueError("ZIP contains an unsafe path.")
            if member.file_size > 50 * 1024 * 1024:
                raise ValueError("A file inside the ZIP is too large.")

        zf.extractall(destination)

    shp_files = list(destination.rglob("*.shp")) + list(destination.rglob("*.SHP"))
    if not shp_files:
        raise ValueError("ZIP does not contain a .shp file.")

    shp = shp_files[0]
    sibling_exts = {p.suffix.lower() for p in shp.parent.iterdir() if p.is_file() and p.stem.lower() == shp.stem.lower()}
    missing = REQUIRED_SHP_PARTS - sibling_exts
    if missing:
        raise ValueError(f"Shapefile is incomplete; missing: {', '.join(sorted(missing))}.")
    return shp


def load_geodata(upload_path: Path, original_filename: str) -> gpd.GeoDataFrame:
    suffix = Path(original_filename).suffix.lower()
    if suffix in ALLOWED_KML:
        gdf = gpd.read_file(upload_path, driver="KML")
    elif suffix in ALLOWED_ARCHIVE:
        with tempfile.TemporaryDirectory() as tmp:
            shp = _safe_extract_zip(upload_path, Path(tmp))
            gdf = gpd.read_file(shp)
    else:
        raise ValueError("Unsupported file type. Upload a .kml or a .zip containing a Shapefile.")

    if "geometry" not in gdf.columns:
        raise ValueError("The uploaded dataset has no geometry column.")
    return gdf


def crs_label(crs: Any) -> str | None:
    if crs is None:
        return None
    try:
        return CRS.from_user_input(crs).to_string()
    except Exception:
        return str(crs)


def choose_measurement_crs(gdf: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, str | None]:
    if gdf.crs is None:
        raise ValueError("Input CRS is missing. A valid CRS is required for reliable measurements.")

    source = CRS.from_user_input(gdf.crs)
    if source.is_geographic:
        wgs84 = gdf.to_crs("EPSG:4326")
    else:
        wgs84 = gdf.to_crs("EPSG:4326")

    non_empty = wgs84.geometry[wgs84.geometry.notna() & ~wgs84.geometry.is_empty]
    if non_empty.empty:
        raise ValueError("Dataset contains no non-empty geometries.")

    # A local UTM CRS gives metric units and is appropriate for typical survey-sized datasets.
    measurement_crs = wgs84.estimate_utm_crs()
    if measurement_crs is None:
        raise ValueError("Could not determine a suitable projected CRS for measurement.")

    return gdf.to_crs(measurement_crs), measurement_crs.to_string()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return value
    if hasattr(value, "item"):
        return _json_safe(value.item())
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    return str(value)


def process_file(upload_path: Path, original_filename: str) -> dict[str, Any]:
    gdf = load_geodata(upload_path, original_filename)
    source_crs = crs_label(gdf.crs)
    measured_gdf, measurement_crs = choose_measurement_crs(gdf)

    results: list[dict[str, Any]] = []
    for idx, row in gdf.iterrows():
        geom = row.geometry
        measured_geom: BaseGeometry | None = measured_gdf.loc[idx].geometry
        geometry_type = geom.geom_type if geom is not None else None
        properties = {str(k): _json_safe(v) for k, v in row.drop(labels=["geometry"]).to_dict().items()}
        result: dict[str, Any] = {
            "feature_id": int(idx) if isinstance(idx, (int, float)) and float(idx).is_integer() else str(idx),
            "geometry_type": geometry_type,
            "geometry": mapping(geom) if geom is not None and not geom.is_empty else None,
            "crs": source_crs,
            "properties": properties,
            "measurement": None,
            "warning": None,
        }

        if geom is None or geom.is_empty:
            result["warning"] = "Empty geometry; no measurement calculated."
        elif geometry_type == "Polygon" or geometry_type == "MultiPolygon":
            result["measurement"] = {"area_m2": float(measured_geom.area)}
        elif geometry_type == "LineString" or geometry_type == "MultiLineString":
            result["measurement"] = {"length_m": float(measured_geom.length)}
        elif geometry_type == "Point" or geometry_type == "MultiPoint":
            result["warning"] = "Point geometry has no measurement requirement."
        else:
            result["warning"] = f"Measurement not supported for geometry type: {geometry_type}."

        results.append(result)

    return {
        "feature_count": len(gdf),
        "crs": source_crs,
        "measurement_crs": measurement_crs,
        "measurements": results,
    }
