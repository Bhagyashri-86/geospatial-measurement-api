# Geospatial File Measurement API

A FastAPI backend that accepts either:

- `.kml`
- `.zip` containing an ESRI Shapefile (`.shp`, `.shx`, `.dbf`, with `.prj` recommended)

It extracts feature information and calculates:

- Polygon / MultiPolygon → area in square metres (`area_m2`)
- LineString / MultiLineString → length in metres (`length_m`)
- Point / MultiPoint → no measurement required
- Other geometry types → graceful warning instead of a crash

## Tech stack

- FastAPI
- GeoPandas
- Shapely
- PyProj
- Fiona/GDAL
- SQLAlchemy + SQLite
- Pytest

## Project structure

```text
geospatial_measurement_api/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── db.py
│   ├── main.py
│   ├── models.py
│   ├── processing.py
│   └── schemas.py
├── tests/
│   └── test_processing.py
├── .gitignore
├── README.md
└── requirements.txt
```

## Setup

### 1. Clone the repository

```bash
git clone <YOUR_GITHUB_REPO_URL>
cd geospatial_measurement_api
```

### 2. Create a virtual environment

Windows:

```bash
python -m venv venv
venv\Scripts\activate
```

macOS/Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

> GeoPandas depends on native geospatial libraries through Fiona/GDAL, so installation can be platform-dependent. If KML support is unavailable in the local GDAL build, install a GDAL/Fiona distribution that includes the KML driver.

### 4. Run the API

```bash
uvicorn app.main:app --reload
```

Open Swagger UI:

```text
http://127.0.0.1:8000/docs
```

## API

### POST `/api/files/`

Upload and process a KML or zipped Shapefile.

Example using curl:

```bash
curl -X POST "http://127.0.0.1:8000/api/files/" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@survey.kml"
```

Example response:

```json
{
  "id": "abc123",
  "filename": "survey.kml",
  "feature_count": 120,
  "crs": "EPSG:4326",
  "status": "COMPLETED"
}
```

### GET `/api/files/{id}/`

Returns metadata and processing status.

Example:

```json
{
  "id": "abc123",
  "filename": "survey.kml",
  "feature_count": 120,
  "crs": "EPSG:4326",
  "status": "COMPLETED",
  "measurement_crs": "EPSG:32643",
  "error": null
}
```

### GET `/api/files/{id}/measurements/`

Returns one object per feature.

Example:

```json
[
  {
    "feature_id": 0,
    "geometry_type": "Polygon",
    "geometry": {
      "type": "Polygon",
      "coordinates": [[[73.0, 18.0], [73.01, 18.0], [73.01, 18.01], [73.0, 18.0]]]
    },
    "crs": "EPSG:4326",
    "properties": {
      "name": "Site A"
    },
    "measurement": {
      "area_m2": 1160000.25
    },
    "warning": null
  }
]
```

## Architecture

### 1. Upload flow

`POST /api/files/` validates the extension and upload size, creates a database record, writes the upload to a temporary directory, and passes it to the processing layer.

### 2. File-processing flow

- KML is read directly with GeoPandas/Fiona.
- ZIP files are checked for unsafe paths and excessive member count.
- The archive must contain the core Shapefile files: `.shp`, `.shx`, and `.dbf`.
- The extracted Shapefile is read with GeoPandas.
- Temporary files are deleted automatically after processing.

### 3. Measurement flow

The original GeoDataFrame is retained for reporting source geometry and CRS. A second GeoDataFrame is transformed to a projected CRS for measurements.

- Polygon → `geometry.area`
- LineString → `geometry.length`
- Point → no measurement
- Unsupported geometry → warning

The API returns geometry in its source CRS and measurement values in metres/metres squared.

### 4. CRS handling

Latitude/longitude coordinates are angular units, so the service never directly uses EPSG:4326 for area or length.

For measurement:

1. The input is checked for a CRS.
2. It is transformed to EPSG:4326.
3. GeoPandas `estimate_utm_crs()` selects a local UTM CRS.
4. Measurements are calculated in that projected CRS.

This works well for typical local/regional survey datasets. A single UTM zone is not ideal for very large datasets crossing multiple UTM zones; that is a future improvement.

If the input has no CRS, the service fails with a clear error instead of silently guessing.

## Design decisions

### Why FastAPI?

FastAPI provides automatic OpenAPI/Swagger documentation, type validation through Pydantic, and a small structure suitable for a focused backend service.

### Why GeoPandas/Shapely/PyProj?

These libraries provide standard geospatial file reading, geometry operations, CRS transformations, and reliable measurement operations without manually implementing GIS algorithms.

### Why SQLite?

SQLite keeps the assignment self-contained and easy to run locally. In production, PostgreSQL/PostGIS would be a better choice for large datasets, spatial queries, concurrency, and persistent feature storage.

### Why store measurements as JSON?

The assignment requires file metadata and measurement retrieval, not a full spatial database. Storing processed feature results as JSON keeps the implementation small. For a production GIS platform, feature and geometry data should move to PostGIS.

### Error handling

Invalid extensions, oversized files, unsafe ZIP paths, incomplete Shapefiles, missing CRS, empty geometries, and unsupported geometry types are handled explicitly.

## Testing

Run:

```bash
pytest -q
```

## Learning

This project demonstrates practical backend and GIS concepts:

- FastAPI REST API design
- multipart file uploads
- GeoPandas/Shapely geometry processing
- CRS and projection handling
- area and length calculations
- ZIP validation
- SQLAlchemy persistence
- Pydantic response validation
- automated tests
- API documentation with OpenAPI

## Future scope

- PostgreSQL + PostGIS
- Background processing with Celery/RQ for very large files
- Authentication and API keys
- Object storage such as S3
- Per-file processing logs
- Pagination for very large measurement responses
- Multiple measurement CRS strategies for datasets spanning large regions
- Support for GeoJSON and GeoPackage
- Rate limiting and stronger upload/content validation
- Docker and CI/CD

## Production notes

This implementation is assignment-ready. For public production deployment, add authentication, rate limiting, persistent object storage, structured logging, monitoring, stricter resource limits, and a PostGIS-backed data model.
