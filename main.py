# main.py — FaaS Platform Gateway (v2)
# This file serves as the main entry point for the FastAPI web server.
# It serves the web UI, exposes API endpoints for function management (deploy/list/delete), 
# and handles incoming function invocation requests by routing them to the runner.

# Import standard library modules for OS operations, UUIDs, time tracking, etc.
import os
import uuid
import time
import shutil
import logging
import json
from pathlib import Path

# Import FastAPI components for web routing, file uploads, and background tasks
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

# Import internal modules for function registry and execution
from function_registry import FunctionRegistry
from runner import run_function

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
# Configure logging to output timestamped, formatted messages for observability
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-20s  %(levelname)-5s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("faas.gateway")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
# Initialize the FastAPI application instance with metadata
app = FastAPI(
    title="FaaS Platform",
    description="Self-hosted Function-as-a-Service with Docker isolation",
    version="2.0.0",
)

BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

registry = FunctionRegistry()

_stats = {
    "total_invocations":    0,
    "successful_invocations": 0,
    "failed_invocations":   0,
    "total_deployments":    0,
    "started_at":           time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
@app.middleware("http")
async def request_middleware(request: Request, call_next):
    rid   = str(uuid.uuid4())[:8]
    request.state.rid = rid
    t0    = time.time()
    logger.info("[%s] → %s %s", rid, request.method, request.url.path)
    resp  = await call_next(request)
    logger.info("[%s] ← %s  %.2fs", rid, resp.status_code, time.time() - t0)
    resp.headers["X-Request-ID"] = rid
    return resp

# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_ui():
    html_path = BASE_DIR / "static" / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))

# ---------------------------------------------------------------------------
# Health & Stats
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "running", "version": "2.0.0", "uptime_since": _stats["started_at"]}

@app.get("/api/stats")
def stats():
    fns = registry.list_functions()
    return {
        **_stats,
        "total_functions":  len(fns),
        "builtin_functions": sum(1 for f in fns if f.get("builtin")),
        "user_functions":   sum(1 for f in fns if not f.get("builtin")),
    }

# ---------------------------------------------------------------------------
# Function Management
# ---------------------------------------------------------------------------
@app.get("/api/functions")
def list_functions():
    return registry.list_functions()

@app.get("/api/functions/{name}")
def get_function(name: str):
    fn = registry.get_function(name)
    if not fn:
        raise HTTPException(404, f"Function '{name}' not found")
    return fn

@app.post("/api/functions/deploy", status_code=201)
async def deploy_function(
    name:          str       = Form(...),
    description:   str       = Form(""),
    input_formats: str       = Form("jpg,jpeg,png"),   # comma-separated
    output_format: str       = Form("png"),
    script:        UploadFile = File(...),
    requirements:  UploadFile = File(None),
):
    """Deploy a new Python function and build its Docker image automatically."""
    # Sanitise name by stripping whitespace, making lowercase, and replacing spaces with hyphens
    name = name.strip().lower().replace(" ", "-")
    # Ensure the name is a valid identifier (alphanumeric and hyphens only) to avoid injection or errors
    if not name.isidentifier() and not all(c.isalnum() or c == "-" for c in name):
        raise HTTPException(400, "Name must contain only letters, numbers, and hyphens")

    script_bytes = await script.read()
    req_bytes    = b""
    if requirements and requirements.filename:
        req_bytes = await requirements.read()

    formats = [f.strip().lower() for f in input_formats.split(",") if f.strip()]

    try:
        # Call the registry to register the metadata and build the Docker image
        fn = registry.deploy_function(
            name=name,
            description=description,
            script_bytes=script_bytes,
            requirements_bytes=req_bytes,
            input_formats=formats,
            output_format=output_format.strip().lower(),
        )
        # Increment global stats for successful deployment
        _stats["total_deployments"] += 1
        return fn
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.exception("Deploy failed")
        raise HTTPException(500, str(e))

@app.delete("/api/functions/{name}", status_code=204)
def delete_function(name: str):
    try:
        registry.delete_function(name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))

# ---------------------------------------------------------------------------
# Function Invocation
# ---------------------------------------------------------------------------
@app.post("/api/functions/{name}/invoke")
async def invoke_function(
    request: Request,
    name:    str,
    file:    UploadFile = File(...),
    params:  str        = Form("{}"),   # JSON string of extra params
):
    """Invoke a deployed function with an uploaded file."""
    rid = getattr(request.state, "rid", "?")

    fn = registry.get_function(name)
    if not fn:
        raise HTTPException(404, f"Function '{name}' not found")

    if not file.filename:
        raise HTTPException(400, "No file provided")

    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in fn["input_formats"]:
        raise HTTPException(
            400,
            f"Function '{name}' does not accept .{ext} files. "
            f"Supported: {fn['input_formats']}"
        )

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(413, f"File too large. Max: {MAX_FILE_SIZE // (1024*1024)} MB")

    try:
        extra = json.loads(params)
    except Exception:
        extra = {}

    # Build env vars from extra params (for resize etc.) to be passed to the Docker container
    env_vars = {}
    for k, v in extra.items():
        env_vars[k.upper()] = str(v)
    # Map width/height to the vars the resize function expects specifically
    if "width" in extra:
        env_vars["RESIZE_WIDTH"] = str(extra["width"])
    if "height" in extra:
        env_vars["RESIZE_HEIGHT"] = str(extra["height"])

    # Increment global stats for total invocation attempts
    _stats["total_invocations"] += 1

    try:
        # Execute the function by spinning up a Docker container via the runner
        output_path = run_function(
            image=fn["image"],
            input_bytes=contents,
            filename=file.filename,
            output_format=fn["output_format"],
            env_vars=env_vars,
            request_id=rid,
        )
        # Record the successful invocation in the registry for statistics
        registry.record_invocation(name)
        _stats["successful_invocations"] += 1
    except Exception as e:
        _stats["failed_invocations"] += 1
        logger.error("[%s] Invocation failed: %s", rid, e)
        raise HTTPException(500, str(e))

    tmp_dir = os.path.dirname(output_path)
    out_ext = fn["output_format"]

    # Define a background task to cleanup the temporary directory after the file is sent to the client
    def cleanup():
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Return the file response, attaching the cleanup task to execute after the response finishes
    return FileResponse(
        path=output_path,
        filename=f"{name}_output.{out_ext}",
        media_type="application/octet-stream",
        background=BackgroundTask(cleanup),
    )