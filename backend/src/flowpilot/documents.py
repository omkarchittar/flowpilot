"""Bounded parsers for the supported upload formats."""

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import PurePath
from time import monotonic

import psutil


class DocumentError(ValueError):
    pass


MEDIA_TYPES = {".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown"}


def extract_pages(
    filename: str,
    data: bytes,
    *,
    max_bytes: int = 10_000_000,
    max_pages: int = 200,
    max_characters: int = 1_000_000,
) -> list[tuple[int, str]]:
    suffix = PurePath(filename).suffix.lower()
    if suffix not in MEDIA_TYPES:
        raise DocumentError("Supported formats are PDF, TXT and Markdown")
    if not data or len(data) > max_bytes:
        raise DocumentError("File size must be between 1 byte and the configured limit")
    if suffix == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise DocumentError("File does not contain a valid PDF header")
        try:
            with (
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "flowpilot.pdf_worker",
                        str(max_pages),
                        str(max_characters),
                        str(max_bytes),
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                ) as process,
                ThreadPoolExecutor(max_workers=1) as executor,
            ):
                output_future = executor.submit(process.communicate, data)
                deadline = monotonic() + 10
                monitor = psutil.Process(process.pid)
                try:
                    while True:
                        try:
                            stdout, _ = output_future.result(timeout=0.02)
                            break
                        except TimeoutError:
                            if monotonic() >= deadline:
                                raise DocumentError(
                                    "PDF could not be parsed within resource limits"
                                ) from None
                            try:
                                if monitor.memory_info().rss > 512 * 1024 * 1024:
                                    raise DocumentError(
                                        "PDF could not be parsed within resource limits"
                                    ) from None
                            except psutil.NoSuchProcess:
                                continue
                finally:
                    if process.poll() is None:
                        process.kill()
                    output_future.result(timeout=2)
            if process.returncode != 0:
                raise DocumentError("PDF could not be parsed within resource limits") from None
            output = json.loads(stdout)
            if "error" in output:
                raise DocumentError(output["error"])
            pages = [(page, text) for page, text in output["pages"]]
        except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError) as exc:
            raise DocumentError("PDF could not be parsed within resource limits") from exc
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DocumentError("Text documents must use UTF-8 encoding") from exc
        if "\x00" in text or any(ord(char) < 32 and char not in "\r\n\t\f" for char in text):
            raise DocumentError("Binary content is not a text document")
        if len(text) > max_characters:
            raise DocumentError("Document exceeds the extracted text limit")
        pages = [(1, text)]
    if not any(text.strip() for _, text in pages):
        raise DocumentError("No extractable text; scanned PDFs require OCR before upload")
    return pages
