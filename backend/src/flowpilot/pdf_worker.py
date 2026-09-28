"""Resource-isolated PDF extraction entry point, invoked by documents.extract_pages.

The production target is Linux (Docker), where RLIMIT_AS bounds total process address
space. A parent RSS monitor also caps child memory on macOS, where RLIMIT_AS
is not supported. Incremental budgets, CPU limits and wall timeout apply on both. The API process never imports or expands untrusted PDF objects.
"""

import json
import resource
import sys
from io import BytesIO


class PdfLimit(ValueError):
    pass


def parse_pdf(
    data: bytes, *, max_pages: int, max_characters: int, max_decoded_bytes: int = 10_000_000
) -> list[tuple[int, str]]:
    from pypdf import PdfReader, apply_configuration
    from pypdf.generic import ArrayObject, DictionaryObject, StreamObject

    with apply_configuration(
        maximum_declared_stream_length=max_decoded_bytes,
        array_based_stream_maximum_output_length=max_decoded_bytes,
        zlib_maximum_output_length=max_decoded_bytes,
        lzw_maximum_output_length=max_decoded_bytes,
        run_length_maximum_output_length=max_decoded_bytes,
        jbig2_maximum_output_length=max_decoded_bytes,
    ):
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise PdfLimit("Encrypted PDFs are not supported")
        if len(reader.pages) > max_pages:
            raise PdfLimit("PDF exceeds the page limit")
        decoded_bytes = 0
        object_visits = 0

        def check_streams(obj, active: set[int], depth: int = 0):
            nonlocal decoded_bytes, object_visits
            if obj is None:
                return
            obj = obj.get_object()
            object_visits += 1
            if depth > 32 or object_visits > 10000 or id(obj) in active:
                raise PdfLimit("PDF exceeds the decompressed content limit")
            path = active | {id(obj)}
            if isinstance(obj, StreamObject):
                decoded_bytes += len(obj.get_data())
                if decoded_bytes > max_decoded_bytes:
                    raise PdfLimit("PDF exceeds the decompressed content limit")
                # Form XObjects can have nested resource graphs.
                check_streams(obj.get("/Resources"), path, depth + 1)
            elif isinstance(obj, ArrayObject):
                for item in obj:
                    check_streams(item, path, depth + 1)
            elif isinstance(obj, DictionaryObject):
                for item in obj.values():
                    check_streams(item, path, depth + 1)

        pages = []
        text_length = 0
        for number, page in enumerate(reader.pages, start=1):
            # Traverse streams one at a time BEFORE page.get_contents()/extract_text
            # concatenate /Contents arrays. Repeated references count each time.
            check_streams(page.get("/Contents"), set())
            check_streams(page.get("/Resources"), set())
            text = page.extract_text() or ""
            text_length += len(text)
            if text_length > max_characters:
                raise PdfLimit("Document exceeds the extracted text limit")
            pages.append((number, text))
        return pages


def main():
    # OS limits cover parser work not expressible as incremental stream budgets,
    # including pathological references and text operator expansion.
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    if sys.platform.startswith("linux"):
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        max_bytes = min(int(sys.argv[3]), 50_000_000)
        data = sys.stdin.buffer.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise PdfLimit("PDF exceeds the file size limit")
        pages = parse_pdf(data, max_pages=int(sys.argv[1]), max_characters=int(sys.argv[2]))
        output = {"pages": pages}
    except PdfLimit as exc:
        output = {"error": str(exc)}
    except Exception:
        output = {"error": "PDF could not be parsed within resource limits"}
    sys.stdout.write(json.dumps(output))


if __name__ == "__main__":
    main()
