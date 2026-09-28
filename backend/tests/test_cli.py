import os
import subprocess
import sys


def test_invalid_bootstrap_password_is_never_printed():
    secret = "secret123"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "flowpilot.cli",
            "create-user",
            "--email",
            "admin@example.com",
            "--name",
            "Admin",
            "--password-env",
            "BOOTSTRAP_TEST_PASSWORD",
        ],
        env={**os.environ, "BOOTSTRAP_TEST_PASSWORD": secret},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert secret not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr
