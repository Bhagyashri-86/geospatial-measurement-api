import json
from pathlib import Path
import tempfile

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from .config import MAX_UPLOAD_SIZE
from .db import Base, engine, get_db
from .models import GeoFile
from .processing import process_file
from .schemas import FeatureMeasurement, FileInfoResponse, UploadResponse

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Geospatial File Measurement API",
    version="1.0.0",
    description="Upload KML or zipped Shapefiles and calculate geometry measurements in metric units.",
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/files/", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".kml", ".zip"}:
        raise HTTPException(status_code=400, detail="Only .kml and .zip files are supported.")

    data = await file.read()
    if len(data) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail=f"File is too large. Maximum is {MAX_UPLOAD_SIZE} bytes.")

    record = GeoFile(filename=filename, status="PROCESSING")
    db.add(record)
    db.commit()
    db.refresh(record)

    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / filename
            path.write_bytes(data)
            result = process_file(path, filename)

        record.feature_count = result["feature_count"]
        record.crs = result["crs"]
        record.measurement_crs = result["measurement_crs"]
        record.measurements_json = json.dumps(result["measurements"], default=str)
        record.status = "COMPLETED"
        db.commit()
        db.refresh(record)
    except Exception as exc:
        record.status = "FAILED"
        record.error = str(exc)
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return record

@app.get("/api/files/{file_id}/", response_model=FileInfoResponse)
def file_info(file_id: str, db: Session = Depends(get_db)):
    record = db.get(GeoFile, file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found.")
    return record

@app.get("/api/files/{file_id}/measurements/", response_model=list[FeatureMeasurement])
def measurements(file_id: str, db: Session = Depends(get_db)):
    record = db.get(GeoFile, file_id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found.")
    if record.status != "COMPLETED":
        raise HTTPException(status_code=409, detail=f"File status is {record.status}.")
    return json.loads(record.measurements_json)
