# ⚡ FaaS Platform — Function-as-a-Service

A self-hosted **Function-as-a-Service** platform where users upload Python scripts and the platform automatically builds a Docker image and runs each function in an isolated container.

---

## Architecture

```
Browser / API Client
       │  HTTP
       ▼
┌─────────────────────┐
│   FastAPI Gateway   │  ← main.py
│  (function_registry │
│   + runner)         │
└──────────┬──────────┘
           │  Docker SDK
    ┌──────┴──────────────────┐
    │                         │
    ▼                         ▼
faas-converter        faas-fn-<name>
(convert-to-pdf)      (user functions)
    ▼                         ▼
faas-fn-image-grayscale   faas-fn-image-resize
```

**Key properties (true FaaS):**
- Each function runs in its own **isolated Docker container**
- Containers are **ephemeral** — created per request, destroyed after
- User scripts get their own **auto-built Docker image** with dependencies
- **Concurrency control** via semaphore (max 4 parallel containers)
- **Resource limits** per container (memory capped at 256 MB)
- **No network access** inside containers (security)

---

## Built-in Functions

| Function | Input | Output | Description |
|---|---|---|---|
| `convert-to-pdf` | txt, md, jpg, png | pdf | Pandoc + ImageMagick |
| `image-grayscale` | jpg, png, bmp, webp | png | Pillow grayscale |
| `image-resize` | jpg, png, bmp, webp | png | Pillow resize (params: width, height) |

---

## Quick Start

### Step 1 — Build runner images (once)
```bat
build-runners.bat
```

### Step 2 — Install gateway dependencies
```bash
pip install -r requirements.txt
```

### Step 3 — Start the gateway
```bash
# Option A: direct
uvicorn main:app --reload --port 8000

# Option B: Docker Compose
docker-compose up --build
```

### Step 4 — Open the UI
```
http://localhost:8000
```

---

## Deploying a Custom Function

Your script must follow this contract:

```python
# function.py
import sys

def process(input_path, output_path):
    # Read from input_path, write result to output_path
    ...

if __name__ == "__main__":
    process(sys.argv[1], sys.argv[2])
```

Upload via UI → **Deploy** tab, or via API:

```bash
curl -X POST http://localhost:8000/api/functions/deploy \
  -F "name=my-function" \
  -F "description=Does something cool" \
  -F "input_formats=jpg,png" \
  -F "output_format=png" \
  -F "script=@function.py" \
  -F "requirements=@requirements.txt"
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/functions` | List all functions |
| GET | `/api/functions/{name}` | Get function details |
| POST | `/api/functions/deploy` | Deploy a new function |
| DELETE | `/api/functions/{name}` | Remove a function |
| POST | `/api/functions/{name}/invoke` | Invoke with a file |
| GET | `/api/health` | Health check |
| GET | `/api/stats` | Platform statistics |

---

## Project Structure

```
faas-fileconverter/
├── main.py                  # FastAPI gateway
├── function_registry.py     # Function management + image building
├── runner.py                # Docker container execution engine
├── requirements.txt
├── Dockerfile               # Gateway image
├── docker-compose.yml
├── build-runners.bat        # Build all runner images
├── static/
│   └── index.html           # Web UI
└── runners/
    ├── converter/           # convert-to-pdf runner
    │   ├── Dockerfile
    │   └── convert.sh
    ├── image-grayscale/     # grayscale runner
    │   ├── Dockerfile
    │   ├── requirements.txt
    │   └── function.py
    └── image-resize/        # resize runner
        ├── Dockerfile
        ├── requirements.txt
        └── function.py
```
