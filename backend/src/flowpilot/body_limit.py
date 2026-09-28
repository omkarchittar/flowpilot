"""Bound request bodies before JSON or multipart parsing allocates/spools them."""

import asyncio
import json
from time import monotonic
from uuid import uuid4


class BodyLimit:
    def __init__(self, app, max_bytes: int = 25_000_000, timeout: float = 30):
        self.app, self.max_bytes, self.timeout = app, max_bytes, timeout

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        chunks = []
        size = 0
        deadline = monotonic() + self.timeout
        status = None
        while True:
            if monotonic() >= deadline:
                status = 408
                break
            try:
                message = await asyncio.wait_for(
                    receive(), timeout=max(0.001, deadline - monotonic())
                )
            except TimeoutError:
                status = 408
                break
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.max_bytes:
                status = 413
                break
            if chunk:
                chunks.append(chunk)
            if not message.get("more_body", False):
                break
        if status:
            request_id = str(uuid4())
            payload = json.dumps(
                {
                    "error": {
                        "code": "request_too_large" if status == 413 else "request_timeout",
                        "message": "Request body exceeds the allowed limit."
                        if status == 413
                        else "Request body timed out.",
                        "request_id": request_id,
                    }
                }
            ).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": status,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"x-request-id", request_id.encode()),
                        (b"cache-control", b"no-store"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": payload})
            return
        buffered = b"".join(chunks)
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": buffered, "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)
