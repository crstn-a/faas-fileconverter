FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY function.py .
WORKDIR /files
ENTRYPOINT ["python", "/app/function.py"]
