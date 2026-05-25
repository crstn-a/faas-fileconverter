# faas-converter

This repository runs a local file conversion service using FastAPI and Docker.
The service accepts uploaded files and converts them to PDF using a Docker container.

## What this does
- `main.py` starts a FastAPI web server
- `converter.py` writes uploads to a temporary folder, launches a Docker container, and returns the converted file
- `runners/converter/convert.sh` performs the actual conversion inside the container
- supported input types: `txt`, `md`, `jpg`, `jpeg`, `png`
- output format: `pdf`

## Prerequisites
1. Install Python 3.x
2. Install project Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Install Docker Desktop on your local device and make sure it is running
   - Docker is required because the conversion happens inside the `faas-converter` container
4. (Optional) If you want native Windows TeX support outside Docker, install MiKTeX from:
   https://miktex.org/download?utm_source=copilot.com
   - Note: the Docker container already includes `texlive-xetex`, so MiKTeX is not required for the Docker-based service.

## Build the Docker image
From the repository root, run:

```bash
cd runners/converter
docker build -t faas-converter .
```

## Run the service locally
From the repository root, run:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Then open or call:

- Health check: `http://127.0.0.1:8000/`
- Conversion endpoint: `http://127.0.0.1:8000/convert`

## Example request
Use `curl` to upload a file and request PDF conversion:

```bash
curl -X POST "http://127.0.0.1:8000/convert" \
  -F "file=@path/to/input.md" \
  -F "target_format=pdf" \
  --output converted.pdf
```

## Notes
- The converter uses a temporary host directory mounted into Docker so the container can read the input file and write the output file.
- If Docker is not running or the image is not built, the conversion will fail.
- Supported input formats are limited to `txt`, `md`, `jpg`, `jpeg`, and `png`.
- The returned download file is named `converted.pdf` by default.

## Troubleshooting
- If you see Docker volume or permission errors on Windows, confirm Docker Desktop is running and file sharing is enabled.
- If conversion fails for text files, the container chooses `pdflatex` or `xelatex` automatically based on file content.
- If you installed MiKTeX for local Windows use, keep in mind the current project flow still uses Docker for conversion.
