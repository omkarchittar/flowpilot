import pytest
from cryptography.fernet import Fernet

from flowpilot.security import SecretBox, hash_password, redact, session_digest, verify_password


def test_passwords_are_salted_and_verified():
    first = hash_password("long-secret-password")
    assert first != hash_password("long-secret-password")
    assert verify_password("long-secret-password", first)
    assert not verify_password("wrong", first)
    assert not verify_password("anything", "broken")


def test_secret_box_encrypts_and_uses_stable_keyed_fingerprints():
    box = SecretBox(Fernet.generate_key().decode())
    encrypted = box.encrypt("12-3456789")
    assert "12-3456789" not in encrypted
    assert box.decrypt(encrypted) == "12-3456789"
    assert box.fingerprint("12-3456789") == box.fingerprint("123456789")
    other = SecretBox(Fernet.generate_key().decode())
    assert other.fingerprint("123456789") != box.fingerprint("123456789")


def test_recursive_redaction_handles_nested_arrays_and_case():
    payload = {
        "Tax_ID": "123456789",
        "details": [{"bank_account": "1234567", "status": "ok"}],
        "authorization": "Bearer SECRET",
        "contact_email": "jane@example.com",
    }
    clean = redact(payload)
    assert clean["Tax_ID"] == "[REDACTED]"
    assert clean["details"][0] == {"bank_account": "[REDACTED]", "status": "ok"}
    assert clean["authorization"] == "[REDACTED]"
    assert clean["contact_email"] == "[REDACTED]"
    assert payload["Tax_ID"] == "123456789"


def test_session_digest_does_not_store_bearer_token():
    token = "high-entropy-bearer-token"
    assert session_digest(token) != token
    assert session_digest(token) == session_digest(token)


@pytest.mark.parametrize("password", ["", "short", "a" * 1025])
def test_password_bounds(password):
    with pytest.raises(ValueError):
        hash_password(password)
