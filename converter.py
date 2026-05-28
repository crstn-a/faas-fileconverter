# converter.py — manages Docker container execution for file conversion
# Follows clean OOP principles: separated service management from job execution.

import docker       # Docker Python SDK — controls containers from Python
import os           # os module — for file path operations
import uuid         # uuid — generates unique IDs to avoid filename collisions
import tempfile     # tempfile — creates temporary folders for file storage
import shutil       # shutil — for recursive temp directory cleanup
import time         # time — for measuring execution duration
import logging      # logging — structured log output
import threading    # threading — for concurrency control via semaphore
import tarfile      # tarfile — for Docker API put_archive/get_archive
import io           # io — for in-memory byte streams

# ---------------------------------------------------------------------------
# Logging setup — structured output for observability
# ---------------------------------------------------------------------------
logger = logging.getLogger("faas.converter")


class ConversionJob:
    """
    [ANALOGY: The Guest Chef's Prep & Order]
    Represents a single file conversion request. Encapsulates all 
    request-specific files, file paths, unique IDs, and streaming operations.
    """
    def __init__(self, input_bytes: bytes, filename: str, target_format: str, request_id: str = ""):
        self.input_bytes = input_bytes
        self.filename = filename
        self.target_format = target_format
        self.request_id = request_id

        # Extract file extension (e.g., "txt", "jpg") from the filename
        self.extension = filename.rsplit(".", 1)[-1].lower()

        # Create a temporary directory on the Gateway filesystem
        self.temp_dir = tempfile.mkdtemp()

        # Generate a unique ID to prevent collisions under concurrent requests
        self.unique_id = str(uuid.uuid4())
        self.input_filename = f"{self.unique_id}_input.{self.extension}"
        self.output_filename = f"{self.unique_id}_output.{self.target_format}"

        # Full local path where the output PDF will be saved for main.py to read
        self.output_path = os.path.join(self.temp_dir, self.output_filename)

    def build_input_archive(self) -> io.BytesIO:
        """
        [ANALOGY: Packing the raw ingredients into a delivery basket]
        Packs the raw input file bytes into an in-memory tarball stream 
        so it can be uploaded directly to the worker container.
        """
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode='w') as tar:
            tarinfo = tarfile.TarInfo(name=self.input_filename)
            tarinfo.size = len(self.input_bytes)
            tar.addfile(tarinfo, io.BytesIO(self.input_bytes))
        tar_stream.seek(0)
        return tar_stream

    def extract_output_archive(self, archive_stream) -> str:
        """
        [ANALOGY: Receiving the cooked dish basket and serving it]
        Reads the tarball stream returned by the container, extracts the 
        converted output file, and writes it to our local temporary folder.
        """
        tar_bytes = b"".join(archive_stream)
        tar_stream = io.BytesIO(tar_bytes)
        
        with tarfile.open(fileobj=tar_stream, mode='r') as tar:
            extracted_file = tar.extractfile(self.output_filename)
            if not extracted_file:
                raise RuntimeError("Failed to extract output file from container archive")
            final_output_bytes = extracted_file.read()

        with open(self.output_path, "wb") as f:
            f.write(final_output_bytes)

        return self.output_path

    def cleanup(self):
        """
        [ANALOGY: Clearing the chef's prep station]
        Recursively deletes the local temporary folder and its contents.
        """
        shutil.rmtree(self.temp_dir, ignore_errors=True)


class FileConverter:
    """
    [ANALOGY: The Head Chef & Kitchen Manager]
    Manages the global conversion service, including:
      - Concurrency limits (limited prep stations via Semaphore)
      - Docker connection (managing the kitchen environment)
      - Invoking worker containers (hiring guest chefs on demand)
    """
    def __init__(self, max_concurrent: int = 4, timeout: int = 60, mem_limit: str = "256m"):
        self.timeout = timeout
        self.mem_limit = mem_limit
        # Guard limits how many containers run at the same time
        self.semaphore = threading.Semaphore(max_concurrent)
        self._client = None

    @property
    def client(self):
        """Connects to Docker Desktop lazily upon first request."""
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def convert(self, input_bytes: bytes, filename: str, target_format: str, request_id: str = "") -> str:
        """
        Spins up an ephemeral container to perform the file conversion.
        Guarantees cleanup, resource limits, and concurrency control.
        """
        # Concurrency gate — block if we already have max concurrent containers running
        acquired = self.semaphore.acquire(timeout=self.timeout)
        if not acquired:
            raise RuntimeError(
                f"[{request_id}] Concurrency limit reached "
                f"({self.semaphore._value} active). Try again later."
            )

        # Create a new job instance for this request
        job = ConversionJob(input_bytes, filename, target_format, request_id)
        container = None
        start_time = time.time()

        try:
            logger.info(
                "[%s] Starting conversion (OOP): %s -> %s (temp=%s)",
                request_id, filename, target_format, job.temp_dir
            )

            # 1. Build input archive (the ingredient delivery basket)
            tar_stream = job.build_input_archive()

            # 2. Create the container (The Guest Chef - no volume mounts!)
            # This is the line where the creation of the docker container is made:
            container = self.client.containers.create(
                "faas-converter",
                command=[
                    f"/files/{job.input_filename}",   # Input file inside container
                    f"/files/{job.output_filename}",  # Output file inside container
                    job.extension                      # File type (e.g., txt, md, png)
                ],
                network_disabled=True,  # No internet access (security)
                mem_limit=self.mem_limit,  # Limit memory use (resource isolation)
                environment={
                    "FAAS_REQUEST_ID": request_id,
                    "FAAS_TIMEOUT": str(self.timeout),
                }
            )

            # 3. Stream input file into container
            container.put_archive("/files", tar_stream)

            # 4. Run the conversion process
            # This is where the conversion actually happens: start the container
            container.start()
            
            # Wait for execution with explicit timeout
            result = container.wait(timeout=self.timeout)

            if result['StatusCode'] != 0:
                logs = container.logs().decode('utf-8', errors='ignore')
                raise RuntimeError(
                    f"Conversion command failed with status {result['StatusCode']}: {logs}"
                )

            # 5. Retrieve output file archive and extract it
            archive_stream, _ = container.get_archive(f"/files/{job.output_filename}")
            output_path = job.extract_output_archive(archive_stream)

            # 6. Double-check output creation
            if not os.path.exists(output_path):
                raise RuntimeError("Container completed but output file was not found.")

            elapsed = time.time() - start_time
            logger.info(
                "[%s] Conversion complete in %.2fs — output: %s (%d bytes)",
                request_id, elapsed, job.output_filename, os.path.getsize(output_path)
            )

            return output_path

        except Exception as e:
            # Clean up local temporary files on error — leave no trace
            job.cleanup()
            logger.error("[%s] Conversion failed: %s", request_id, e)
            raise

        finally:
            # Always remove the container to free up Docker engine memory
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
            # Always release the semaphore so other requests can enter
            self.semaphore.release()


# ---------------------------------------------------------------------------
# Global Service Instance & Backward-Compatible API
# ---------------------------------------------------------------------------
# Global instance of our FileConverter service (The Head Chef)
_global_converter = FileConverter()

def convert_file(input_bytes: bytes, filename: str, target_format: str, request_id: str = "") -> str:
    """
    Exposes a clean wrapper function that calls the global OOP service.
    This maintains 100% backward compatibility with main.py.
    """
    return _global_converter.convert(input_bytes, filename, target_format, request_id=request_id)