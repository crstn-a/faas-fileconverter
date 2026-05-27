# Dockerfile — FaaS Gateway (v2)

FROM python:3.10-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .
COPY converter.py .
COPY runner.py .
COPY function_registry.py .

# Copy web UI
COPY static/ ./static/

# Expose API port
EXPOSE 8000

# Start FastAPI gateway
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
