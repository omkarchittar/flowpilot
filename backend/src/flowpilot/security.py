"""Sensitive data utilities. Do not serialize decrypted values into logs or audit events."""

import base64
import hashlib
import hmac
import os
import re
from typing import Any

from cryptography.fernet import Fernet


def hash_password(password: str) -> str:
    if not 12 <= len(password) <= 1024:
        raise ValueError("Password must contain 12–1024 characters")
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return "scrypt$" + salt.hex() + "$" + digest.hex()


def verify_password(password: str, encoded: str) -> bool:
    if len(password) > 1024:
        return False
    try:
        algorithm, salt, expected = encoded.split("$")
        if algorithm != "scrypt" or len(salt) != 32 or len(expected) != 64:
            return False
        actual = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32
        )
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def session_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class SecretBox:
    def __init__(self, key: str):
        self.fernet = Fernet(key.encode())
        self.fingerprint_key = hmac.digest(
            base64.urlsafe_b64decode(key), b"flowpilot-tax-fingerprint-v1", "sha256"
        )

    def encrypt(self, value: str) -> str:
        return self.fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        return self.fernet.decrypt(value.encode()).decode()

    def fingerprint(self, tax_id: str) -> str:
        normalized = re.sub(r"[\s-]", "", tax_id)
        return hmac.new(self.fingerprint_key, normalized.encode(), hashlib.sha256).hexdigest()


SENSITIVE_KEYS = {
    "taxid",
    "ein",
    "ssn",
    "bankaccount",
    "bankdetails",
    "accountnumber",
    "routingnumber",
    "password",
    "passwordhash",
    "token",
    "authorization",
    "apikey",
    "secret",
    "contactemail",
    "contactname",
    "requesttext",
    "content",
    "rawtext",
    "quote",
    "text",
    "encryptedtaxid",
}


def redact(value: Any) -> Any:
    """Defense in depth; audit producers must still use allowlisted payloads.

    Free text cannot be safely sanitized by key matching. Never send raw prompts or
    provider exception messages to this function and assume they are safe to log.
    """
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if re.sub("[^a-z0-9]", "", str(key).lower()) in SENSITIVE_KEYS
            else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return value
