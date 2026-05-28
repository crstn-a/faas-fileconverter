# function_registry.py — manages deployed function metadata and Docker image building

import json
import os
import docker
import tempfile
import shutil
import logging
from datetime import datetime, timezone

logger = logging.getLogger("faas.registry")

REGISTRY_FILE = "functions.json"

# Built-in functions pre-registered at startup
_BUILTINS = {
    "convert-to-pdf": {
        "name": "convert-to-pdf",
        "description": "Convert .txt, .md, or images to PDF using Pandoc & ImageMagick",
        "image": "faas-converter",
        "builtin": True,
        "input_formats": ["txt", "md", "jpg", "jpeg", "png"],
        "output_format": "pdf",
        "params": {},
        "created_at": "2024-01-01T00:00:00Z",
        "invocations": 0,
    },
    "image-grayscale": {
        "name": "image-grayscale",
        "description": "Convert any color image to grayscale using Pillow",
        "image": "faas-fn-image-grayscale",
        "builtin": True,
        "input_formats": ["jpg", "jpeg", "png", "bmp", "webp"],
        "output_format": "png",
        "params": {},
        "created_at": "2024-01-01T00:00:00Z",
        "invocations": 0,
    },
    "image-resize": {
        "name": "image-resize",
        "description": "Resize an image to custom dimensions (default 800×600)",
        "image": "faas-fn-image-resize",
        "builtin": True,
        "input_formats": ["jpg", "jpeg", "png", "bmp", "webp"],
        "output_format": "png",
        "params": {
            "width":  {"type": "int", "default": 800, "description": "Target width in pixels"},
            "height": {"type": "int", "default": 600, "description": "Target height in pixels"},
        },
        "created_at": "2024-01-01T00:00:00Z",
        "invocations": 0,
    },
}


class FunctionRegistry:
    def __init__(self):
        self._client    = None
        self._functions = {}
        self._load()

    # ------------------------------------------------------------------
    # Docker client (lazy)
    # ------------------------------------------------------------------
    @property
    def client(self):
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load(self):
        self._functions = {k: dict(v) for k, v in _BUILTINS.items()}
        if os.path.exists(REGISTRY_FILE):
            try:
                with open(REGISTRY_FILE) as f:
                    saved = json.load(f)
                for name, fn in saved.items():
                    if not fn.get("builtin"):
                        self._functions[name] = fn
            except Exception as e:
                logger.warning("Could not load registry: %s", e)

    def _save(self):
        to_save = {k: v for k, v in self._functions.items() if not v.get("builtin")}
        with open(REGISTRY_FILE, "w") as f:
            json.dump(to_save, f, indent=2)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def list_functions(self) -> list:
        return list(self._functions.values())

    def get_function(self, name: str) -> dict | None:
        return self._functions.get(name)

    def record_invocation(self, name: str):
        if name in self._functions:
            self._functions[name]["invocations"] = self._functions[name].get("invocations", 0) + 1
            if not self._functions[name].get("builtin"):
                self._save()

    def deploy_function(
        self,
        name: str,
        description: str,
        script_bytes: bytes,
        requirements_bytes: bytes,
        input_formats: list,
        output_format: str,
    ) -> dict:
        """Deploy a new function by building a dedicated Docker image."""
        # Check if the name conflicts with an existing built-in function to prevent overriding core functionality
        if name in self._functions and self._functions[name].get("builtin"):
            raise ValueError(f"Cannot override built-in function '{name}'")

        image_tag = f"faas-fn-{name}:latest"
        # Call internal method to build the Docker image using the provided scripts and requirements
        self._build_image(image_tag, script_bytes, requirements_bytes)

        meta = {
            "name":         name,
            "description":  description,
            "image":        image_tag,
            "builtin":      False,
            "input_formats":  input_formats,
            "output_format":  output_format,
            "params":       {},
            "created_at":   datetime.now(timezone.utc).isoformat(),
            "invocations":  0,
        }
        self._functions[name] = meta
        self._save()
        logger.info("Deployed function '%s' → image '%s'", name, image_tag)
        return meta

    def delete_function(self, name: str):
        fn = self._functions.get(name)
        if not fn:
            raise ValueError(f"Function '{name}' not found")
        if fn.get("builtin"):
            raise ValueError(f"Cannot delete built-in function '{name}'")
        try:
            self.client.images.remove(fn["image"], force=True)
            logger.info("Removed Docker image: %s", fn["image"])
        except Exception as e:
            logger.warning("Could not remove image %s: %s", fn["image"], e)
        del self._functions[name]
        self._save()

    # ------------------------------------------------------------------
    # Private: build Docker image for a user-deployed function
    # ------------------------------------------------------------------
    def _build_image(self, image_tag: str, script_bytes: bytes, requirements_bytes: bytes):
        """
        Builds a Docker image dynamically. It creates a temporary directory, writes the user scripts,
        generates a Dockerfile, and instructs the Docker engine to build the image.
        """
        # Create a temporary directory to serve as the Docker build context
        build_dir = tempfile.mkdtemp()
        try:
            # Write the user's Python script into the build directory
            with open(os.path.join(build_dir, "function.py"), "wb") as f:
                f.write(script_bytes)
            # Write the user's requirements.txt into the build directory
            with open(os.path.join(build_dir, "requirements.txt"), "wb") as f:
                f.write(requirements_bytes)

            # Generate the Dockerfile on the fly: uses python 3.10 slim, installs requirements, copies the script
            dockerfile = (
                "FROM python:3.10-slim\n"
                "WORKDIR /app\n"
                "COPY requirements.txt .\n"
                "RUN pip install --no-cache-dir -r requirements.txt\n"
                "COPY function.py .\n"
                "WORKDIR /files\n"
                'ENTRYPOINT ["python", "/app/function.py"]\n'
            )
            with open(os.path.join(build_dir, "Dockerfile"), "w") as f:
                f.write(dockerfile)

            logger.info("Building image: %s", image_tag)
            # This is the line where the creation of the docker container/image is made:
            # Tell Docker client to build the image from the temporary build context
            image, logs = self.client.images.build(
                path=build_dir, tag=image_tag, rm=True, forcerm=True
            )
            # Stream build logs for observability
            for chunk in logs:
                if "stream" in chunk:
                    logger.debug("BUILD | %s", chunk["stream"].strip())
            logger.info("Image built: %s", image_tag)
        finally:
            shutil.rmtree(build_dir, ignore_errors=True)
