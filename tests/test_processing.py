import geopandas as gpd
from shapely.geometry import Polygon, LineString, Point
from app.processing import choose_measurement_crs


def test_geographic_crs_is_projected_for_measurement():
    gdf = gpd.GeoDataFrame(
        {"name": ["square"]},
        geometry=[Polygon([(73.0, 18.0), (73.01, 18.0), (73.01, 18.01), (73.0, 18.01)])],
        crs="EPSG:4326",
    )
    measured, crs = choose_measurement_crs(gdf)
    assert crs is not None
    assert measured.crs.is_projected
    assert measured.geometry.iloc[0].area > 0


def test_supported_geometry_types():
    gdf = gpd.GeoDataFrame(
        {"name": ["line", "point"]},
        geometry=[LineString([(73, 18), (73.01, 18)]), Point(73, 18)],
        crs="EPSG:4326",
    )
    measured, _ = choose_measurement_crs(gdf)
    assert measured.geometry.iloc[0].length > 0
