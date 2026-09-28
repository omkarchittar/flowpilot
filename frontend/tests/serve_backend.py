"""Disposable PostgreSQL/API/worker fixture. Never uses a real model or production data."""

import json
import os
import re
import signal
import subprocess
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import psycopg
from cryptography.fernet import Fernet
from flowpilot.models import User
from flowpilot.security import hash_password
from psycopg import sql
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
PASSWORD = "browser-fixture-password-2026"
stop = threading.Event()
for sig in [signal.SIGTERM, signal.SIGINT]:
    signal.signal(sig, lambda *_: stop.set())


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        payload = json.loads(body["messages"][1]["content"])
        if "request" in payload:
            text = payload["request"].lower()
            kind = (
                "invoice_review"
                if "invoice review" in text
                else "contract_request"
                if "contract review" in text
                else "vendor_onboarding"
            )
            value = {"request_type": kind, "confidence": 0.99}
        elif "assessment" in payload:
            if payload["workflow_type"] == "invoice_review":
                self.send_response(503)
                self.end_headers()
                return
            value = {
                "assessment": payload["assessment"],
                "summary": "The policy checks passed for this revision. An independent person must review the evidence before authorizing vendor creation."
                if payload["assessment"] == "ready_for_review"
                else "The request is blocked by the recorded findings. Resolve them before independent review.",
                "issue_refs": [issue["id"] for issue in payload["issues"]],
            }
        else:
            sources = payload["sources"]
            value = {}
            for field in [
                "company_name",
                "tax_id",
                "contact_name",
                "contact_email",
                "insurance_expiration",
            ]:
                matched = next(
                    (
                        (identifier, re.search(rf"{field}: ([^\n]+)", content))
                        for identifier, content in sources.items()
                        if re.search(rf"{field}: ([^\n]+)", content)
                    ),
                    None,
                )
                found = matched[1].group(1).strip() if matched else None
                value[field] = {
                    "value": found,
                    "source_id": matched[0] if matched else None,
                    "quote": found,
                    "confidence": 0.99,
                }
            value.update(confidence=0.99, documents=[])
            for identifier, content in sources.items():
                if identifier == "request":
                    continue
                for label, kind in [
                    ("Tax form", "tax_form"),
                    ("Insurance certificate", "insurance_certificate"),
                    ("Bank confirmation", "bank_confirmation"),
                ]:
                    if content.startswith(label):
                        value["documents"].append(
                            {
                                "source_id": identifier,
                                "kind": kind,
                                "quote": label,
                                "confidence": 0.99,
                            }
                        )
        data = json.dumps(
            {
                "model": "controlled-browser-fixture",
                "choices": [
                    {"finish_reason": "stop", "message": {"content": json.dumps(value)}}
                ],
                "usage": {"prompt_tokens": 80, "completion_tokens": 50},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    if not os.environ.get("TEST_DATABASE_URL"):
        raise SystemExit(
            "TEST_DATABASE_URL must name an isolated PostgreSQL test database; its user needs CREATEDB."
        )
    original = make_url(os.environ["TEST_DATABASE_URL"])
    name = "flowpilot_browser_" + uuid.uuid4().hex[:10]
    target = original.set(database=name)
    admin_url = original.set(drivername="postgresql").render_as_string(
        hide_password=False
    )
    target_url = target.render_as_string(hide_password=False)
    provider = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    env = {
        **os.environ,
        "TEST_DATABASE_URL": target_url,
        "FLOWPILOT_DATABASE_URL": target_url,
        "FLOWPILOT_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "FLOWPILOT_OPENAI_API_KEY": "controlled-fixture-key",
        "FLOWPILOT_OPENAI_BASE_URL": f"http://127.0.0.1:{provider.server_port}/v1",
        "FLOWPILOT_GENERATION_MODEL": "controlled-browser-fixture",
        "FLOWPILOT_UPLOAD_LIMIT_BYTES": "32000000",
        "FLOWPILOT_ALLOWED_ORIGINS": '["http://127.0.0.1:3101"]',
    }
    processes = []
    python = str(BACKEND / ".venv/bin/python")
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            subprocess.run(
                [str(BACKEND / ".venv/bin/alembic"), "upgrade", "head"],
                cwd=BACKEND,
                env=env,
                check=True,
                capture_output=True,
            )
            engine = create_engine(target_url)
            with Session(engine) as db, db.begin():
                for email, display, role in [
                    ("requester@example.com", "Taylor Morgan", "requester"),
                    ("approver@example.com", "Alex Chen", "approver"),
                    ("reviewer@example.com", "Jordan Lee", "reviewer"),
                    ("admin@example.com", "Casey Rivera", "admin"),
                    ("other@example.com", "Other Requester", "requester"),
                ]:
                    db.add(
                        User(
                            email=email,
                            name=display,
                            role=role,
                            password_hash=hash_password(PASSWORD),
                        )
                    )
            engine.dispose()
            for command in [
                [
                    python,
                    "-m",
                    "uvicorn",
                    "flowpilot.app:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "18081",
                    "--no-access-log",
                ],
                [python, "-m", "flowpilot.worker"],
            ]:
                processes.append(
                    subprocess.Popen(
                        command,
                        cwd=BACKEND,
                        env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                )
            print(
                "Disposable browser backend started with a controlled provider.",
                flush=True,
            )
            while not stop.wait(0.5):
                if any(process.poll() is not None for process in processes):
                    raise RuntimeError("Browser fixture process exited")
        finally:
            for process in processes:
                process.terminate()
            for process in processes:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            admin.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )
            provider.shutdown()
            provider.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    main()
