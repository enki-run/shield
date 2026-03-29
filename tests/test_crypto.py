import pytest
from cryptography.exceptions import InvalidTag
from app.core.crypto import encrypt_value, decrypt_value


def test_encrypt_decrypt_roundtrip():
    secret = "test-secret-key"
    plaintext = "John Doe"
    encrypted = encrypt_value(plaintext, secret)
    decrypted = decrypt_value(encrypted, secret)
    assert decrypted == plaintext


def test_encrypt_decrypt_empty_string():
    secret = "test-secret-key"
    plaintext = ""
    encrypted = encrypt_value(plaintext, secret)
    decrypted = decrypt_value(encrypted, secret)
    assert decrypted == plaintext


def test_encrypt_decrypt_special_characters():
    secret = "test-secret-key"
    plaintext = "Ääöö Üü ß — test@example.com <script>alert(1)</script>"
    encrypted = encrypt_value(plaintext, secret)
    decrypted = decrypt_value(encrypted, secret)
    assert decrypted == plaintext


def test_encrypt_decrypt_long_text():
    secret = "test-secret-key"
    plaintext = "A" * 10000
    encrypted = encrypt_value(plaintext, secret)
    decrypted = decrypt_value(encrypted, secret)
    assert decrypted == plaintext


def test_wrong_key_fails():
    plaintext = "sensitive data"
    encrypted = encrypt_value(plaintext, "correct-key")
    with pytest.raises(InvalidTag):
        decrypt_value(encrypted, "wrong-key")


def test_different_keys_produce_different_ciphertexts():
    plaintext = "same text"
    encrypted1 = encrypt_value(plaintext, "key-one")
    encrypted2 = encrypt_value(plaintext, "key-two")
    assert encrypted1 != encrypted2


def test_nonce_uniqueness():
    secret = "test-secret-key"
    plaintext = "same plaintext"
    encrypted1 = encrypt_value(plaintext, secret)
    encrypted2 = encrypt_value(plaintext, secret)
    # Same plaintext + same key → different ciphertext due to random nonce
    assert encrypted1 != encrypted2


def test_encrypted_is_base64_string():
    import base64
    secret = "test-secret-key"
    plaintext = "test"
    encrypted = encrypt_value(plaintext, secret)
    # Should not raise
    decoded = base64.b64decode(encrypted)
    # Nonce (12 bytes) + tag (16 bytes) + ciphertext (len(plaintext) bytes)
    assert len(decoded) >= 12 + 16


def test_tampered_ciphertext_fails():
    plaintext = "important data"
    secret = "my-secret"
    encrypted = encrypt_value(plaintext, secret)

    # Flip a byte in the middle of the ciphertext
    import base64
    raw = bytearray(base64.b64decode(encrypted))
    raw[20] ^= 0xFF
    tampered = base64.b64encode(bytes(raw)).decode("ascii")

    with pytest.raises(InvalidTag):
        decrypt_value(tampered, secret)
