# runner.py — Generic FaaS container runner
# Spins up an ephemeral Docker container for any registered function image.

import docker
import os
import uuid
import tempfile
import shutil
import time
import logging
import threading
import tarfile
import io

logger = logging.getLogger("faas.runner")


class RunJob:
    """Encapsulates a single function invocation: temp files, unique IDs, tar I/O."""

    def __init__(self, input_bytes: bytes, filename: str, output_format: str, request_id: str = ""):
        self.input_bytes   = input_bytes
        self.filename      = filename
        self.output_format = output_format
        self.request_id    = request_id

        self.extension       = filename.rsplit(".", 1)[-1].lower()
        self.temp_dir        = tempfile.mkdtemp()
        self.unique_id       = str(uuid.uuid4())
        self.input_filename  = f"{self.unique_id}_input.{self.extension}"
        self.output_filename = f"{self.unique_id}_output.{self.output_format}"
        self.output_path     = os.path.join(self.temp_dir, self.output_filename)

    def build_input_archive(self) -> io.BytesIO:
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            info = tarfile.TarInfo(name=self.input_filename)
            info.size = len(self.input_bytes)
            tar.addfile(info, io.BytesIO(self.input_bytes))
        tar_stream.seek(0)
        return tar_stream

    def extract_output_archive(self, archive_stream) -> str:
        tar_bytes  = b"".join(archive_stream)
        tar_stream = io.BytesIO(tar_bytes)
        with tarfile.open(fileobj=tar_stream, mode="r") as tar:
            extracted = tar.extractfile(self.output_filename)
            if not extracted:
                raise RuntimeError("Output file not found in container archive")
            data = extracted.read()
        with open(self.output_path, "wb") as f:
            f.write(data)
        return self.output_path

    def cleanup(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)


class FunctionRunner:
    """
    Manages ephemeral Docker containers for function invocations.
    Enforces concurrency limits, resource isolation, and guaranteed cleanup.
    """

    def __init__(self, max_concurrent: int = 4, timeout: int = 120, mem_limit: str = "256m"):
        self.timeout       = timeout
        self.mem_limit     = mem_limit
        self.semaphore     = threading.Semaphore(max_concurrent)
        self._client       = None

    @property
    def client(self):
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def run(
        self,
        image: str,
        input_bytes: bytes,
        filename: str,
        output_format: str,
        env_vars: dict = None,
        request_id: str = "",
    ) -> str:
        """
        Run a function in an isolated container.
        Returns the local path of the output file.
        """
        acquired = self.semaphore.acquire(timeout=self.timeout)
        if not acquired:
            raise RuntimeError("Concurrency limit reached. Try again later.")

        job       = RunJob(input_bytes, filename, output_format, request_id)
        container = None
        start     = time.time()

        try:
            logger.info("[%s] Invoking image=%s  %s -> %s", request_id, image, filename, output_format)

            # Package the input file into an in-memory tarball for Docker
            tar_stream = job.build_input_archive()

            # Merge any passed-in environment variables with the request ID
            env = {"FAAS_REQUEST_ID": request_id, **(env_vars or {})}

            # This is the line where the creation of the docker container is made:
            # Tell Docker to create a stopped container with restricted networking and memory
            container = self.client.containers.create(
                image,
                command=[
                    f"/files/{job.input_filename}",
                    f"/files/{job.output_filename}",
                ],
                network_disabled=True,
                mem_limit=self.mem_limit,
                environment=env,
            )

            # Upload the input file tarball into the container's /files directory
            container.put_archive("/files", tar_stream)
            # This is where the conversion actually happens: start the container
            container.start()

            result = container.wait(timeout=self.timeout)
            if result["StatusCode"] != 0:
                logs = container.logs().decode("utf-8", errors="ignore")
                raise RuntimeError(f"Container exited {result['StatusCode']}: {logs}")

            archive_stream, _ = container.get_archive(f"/files/{job.output_filename}")
            output_path = job.extract_output_archive(archive_stream)

            if not os.path.exists(output_path):
                raise RuntimeError("Container completed but output file was not found.")

            elapsed = time.time() - start
            logger.info("[%s] Done in %.2fs → %s (%d bytes)", request_id, elapsed, job.output_filename, os.path.getsize(output_path))
            return output_path

        except Exception as e:
            job.cleanup()
            logger.error("[%s] Run failed: %s", request_id, e)
            raise

        finally:
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
            self.semaphore.release()


# Global runner instance
_runner = FunctionRunner()


def run_function(image: str, input_bytes: bytes, filename: str, output_format: str,
                 env_vars: dict = None, request_id: str = "") -> str:
    return _runner.run(image, input_bytes, filename, output_format, env_vars, request_id)
