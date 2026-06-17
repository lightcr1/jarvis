import os
import pytest


def _fresh_key():
    from jarvis.secret_crypto import generate_master_key
    return generate_master_key()


def test_encrypt_decrypt_roundtrip(monkeypatch):
    key = _fresh_key()
    monkeypatch.setenv("JARVIS_SECRET_KEY", key)
    from jarvis.secret_crypto import encrypt_secret, decrypt_secret
    plaintext = "sk-anthropic-abc123xyz987"
    ciphertext = encrypt_secret(plaintext)
    assert decrypt_secret(ciphertext) == plaintext


def test_ciphertext_is_not_plaintext(monkeypatch):
    key = _fresh_key()
    monkeypatch.setenv("JARVIS_SECRET_KEY", key)
    from jarvis.secret_crypto import encrypt_secret
    plaintext = "sk-secret-key"
    ciphertext = encrypt_secret(plaintext)
    assert plaintext not in ciphertext
    assert "sk-secret-key" not in ciphertext


def test_scheme_tag_present(monkeypatch):
    key = _fresh_key()
    monkeypatch.setenv("JARVIS_SECRET_KEY", key)
    from jarvis.secret_crypto import encrypt_secret
    ciphertext = encrypt_secret("anything")
    assert ciphertext.startswith("fernet:v1:")


def test_tampered_token_raises(monkeypatch):
    key = _fresh_key()
    monkeypatch.setenv("JARVIS_SECRET_KEY", key)
    from jarvis.secret_crypto import encrypt_secret, decrypt_secret, SecretDecryptionError
    ciphertext = encrypt_secret("supersecret")
    tampered = ciphertext[:-4] + "XXXX"
    with pytest.raises(SecretDecryptionError):
        decrypt_secret(tampered)


def test_missing_scheme_tag_raises(monkeypatch):
    key = _fresh_key()
    monkeypatch.setenv("JARVIS_SECRET_KEY", key)
    from jarvis.secret_crypto import decrypt_secret, SecretDecryptionError
    with pytest.raises(SecretDecryptionError):
        decrypt_secret("no-tag-here")


def test_encrypt_without_key_raises(monkeypatch):
    monkeypatch.delenv("JARVIS_SECRET_KEY", raising=False)
    from jarvis.secret_crypto import encrypt_secret, SecretEncryptionUnavailable
    with pytest.raises(SecretEncryptionUnavailable):
        encrypt_secret("mykey")


def test_decrypt_without_key_raises(monkeypatch):
    key = _fresh_key()
    monkeypatch.setenv("JARVIS_SECRET_KEY", key)
    from jarvis.secret_crypto import encrypt_secret
    ciphertext = encrypt_secret("mykey")

    monkeypatch.delenv("JARVIS_SECRET_KEY", raising=False)
    from jarvis import secret_crypto
    # Reload the env-read
    from jarvis.secret_crypto import decrypt_secret, SecretEncryptionUnavailable
    with pytest.raises(SecretEncryptionUnavailable):
        decrypt_secret(ciphertext)


def test_wrong_key_raises(monkeypatch):
    key_a = _fresh_key()
    key_b = _fresh_key()
    monkeypatch.setenv("JARVIS_SECRET_KEY", key_a)
    from jarvis.secret_crypto import encrypt_secret
    ciphertext = encrypt_secret("secret")

    monkeypatch.setenv("JARVIS_SECRET_KEY", key_b)
    from jarvis.secret_crypto import decrypt_secret, SecretDecryptionError
    with pytest.raises(SecretDecryptionError):
        decrypt_secret(ciphertext)


def test_encryption_available_true(monkeypatch):
    key = _fresh_key()
    monkeypatch.setenv("JARVIS_SECRET_KEY", key)
    from jarvis.secret_crypto import encryption_available
    assert encryption_available() is True


def test_encryption_available_false(monkeypatch):
    monkeypatch.delenv("JARVIS_SECRET_KEY", raising=False)
    from jarvis.secret_crypto import encryption_available
    assert encryption_available() is False


def test_mask_short_string():
    from jarvis.secret_crypto import mask_secret
    assert mask_secret("") == "****"
    assert mask_secret("short") == "****"
    assert mask_secret("1234567") == "****"


def test_mask_long_string():
    from jarvis.secret_crypto import mask_secret
    masked = mask_secret("sk-proj-abcdefghijklmnopwxyz1234")
    assert masked.startswith("sk-")
    assert masked.endswith(masked[-4:])
    assert "..." in masked
    # The middle of the key must not appear
    assert "abcdefghij" not in masked


def test_mask_never_reveals_middle():
    from jarvis.secret_crypto import mask_secret
    key = "sk-" + "X" * 40 + "abcd"
    masked = mask_secret(key)
    assert "X" * 10 not in masked
    assert masked.endswith("abcd")
    assert masked.startswith("sk-")


def test_generate_master_key_is_valid_fernet():
    from jarvis.secret_crypto import generate_master_key, get_master_key
    import os
    key = generate_master_key()
    os.environ["JARVIS_SECRET_KEY"] = key
    result = get_master_key()
    del os.environ["JARVIS_SECRET_KEY"]
    assert result is not None
    assert len(result) > 0
