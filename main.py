# main.py — FastAPI server that acts as the FaaS Gateway
# Receives HTTP requests, validates sizes/formats, and invokes the conversion service.

import os
import uuid
import time
import shutil
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from converter import convert_file

# ---------------------------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-18s  %(levelname)-5s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("faas.gateway")

# ---------------------------------------------------------------------------
# FastAPI Application & Constants
# ---------------------------------------------------------------------------
app = FastAPI(
    title="FaaS File Converter",
    description="A self-hosted Function-as-a-Service for file conversion using Docker.",
    version="1.0.0",
)

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB limit
SUPPORTED_FORMATS = ["txt", "md", "jpg", "jpeg", "png"]

# ---------------------------------------------------------------------------
# HTTP Middleware (Request ID & Execution Timing)
# ---------------------------------------------------------------------------
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    # Generate unique 8-character ID for request tracing
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    
    start_time = time.time()
    logger.info("[%s] → %s %s", request_id, request.method, request.url.path)
    
    response = await call_next(request)
    
    elapsed = time.time() - start_time
    logger.info("[%s] ← %s (%.2fs)", request_id, response.status_code, elapsed)
    
    # Propagate ID to response header for debugging
    response.headers["X-Request-ID"] = request_id
    return response

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/")
def health_check():
    """Simple status endpoint reporting current configurations."""
    return {
        "status": "running",
        "service": "FaaS File Converter",
        "version": "1.0.0",
        "supported_formats": SUPPORTED_FORMATS,
        "max_file_size_mb": MAX_FILE_SIZE_BYTES // (1024 * 1024),
    }


@app.post("/convert")
async def convert(
    request: Request,
    file: UploadFile = File(...),
    target_format: str = "pdf"
):
    """
    Handles file upload and passes it to the Docker converter.
    Returns the converted file and schedules a clean-up of temporary files on disk.
    """
    request_id = getattr(request.state, "request_id", "unknown")

    # 1. Validation: Ensure file exists
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    # 2. Validation: Ensure format is supported
    extension = file.filename.rsplit(".", 1)[-1].lower()
    if extension not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: .{extension}. Supported: {SUPPORTED_FORMATS}"
        )

    # 3. Validation: Limit file upload size
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE_BYTES:
        size_mb = len(contents) / (1024 * 1024)
        limit_mb = MAX_FILE_SIZE_BYTES / (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {size_mb:.1f} MB. Maximum allowed: {limit_mb:.0f} MB."
        )

    logger.info(
        "[%s] File accepted: %s (%d bytes) -> %s",
        request_id, file.filename, len(contents), target_format
    )

    # 4. Invoke Docker conversion service
    try:
        output_path = convert_file(
            contents, 
            file.filename, 
            target_format, 
            request_id=request_id
        )
    except Exception as e:
        logger.error("[%s] Conversion failed: %s", request_id, e)
        raise HTTPException(status_code=500, detail=str(e))

    # 5. Build file response and schedule background deletion of local temp folder
    tmp_dir = os.path.dirname(output_path)
    
    def cleanup_temp_dir():
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.info("[%s] Temp directory cleaned up: %s", request_id, tmp_dir)

    return FileResponse(
        path=output_path,
        filename=f"converted.{target_format}",
        media_type="application/octet-stream",
        background=BackgroundTask(cleanup_temp_dir)
    )