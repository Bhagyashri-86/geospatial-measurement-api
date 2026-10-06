from typing import Any
from pydantic import BaseModel

class UploadResponse(BaseModel):
    id: str
    filename: str
    feature_count: int
    crs: str | None
    status: str

class FileInfoResponse(UploadResponse):
    measurement_crs: str | None = None
    error: str | None = None

class FeatureMeasurement(BaseModel):
    feature_id: int
    geometry_type: str | None
    geometry: dict[str, Any] | None
    crs: str | None
    properties: dict[str, Any]
    measurement: dict[str, Any] | None
    warning: str | None = None
