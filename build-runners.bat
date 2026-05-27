@echo off
REM build-runners.bat — builds all required Docker runner images
REM Run this ONCE before starting the platform.

echo [1/3] Building faas-converter (convert-to-pdf)...
docker build -t faas-converter ./runners/converter
if %errorlevel% neq 0 ( echo ERROR: faas-converter build failed & exit /b 1 )

echo [2/3] Building faas-fn-image-grayscale...
docker build -t faas-fn-image-grayscale ./runners/image-grayscale
if %errorlevel% neq 0 ( echo ERROR: grayscale build failed & exit /b 1 )

echo [3/3] Building faas-fn-image-resize...
docker build -t faas-fn-image-resize ./runners/image-resize
if %errorlevel% neq 0 ( echo ERROR: resize build failed & exit /b 1 )

echo.
echo All runner images built successfully!
echo.
echo Next step: run the gateway
echo   Option A (direct):  uvicorn main:app --reload --port 8000
echo   Option B (Docker):  docker-compose up --build
