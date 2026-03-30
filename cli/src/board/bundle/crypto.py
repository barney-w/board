"""AES-256-GCM encryption compatible with extension/src/bundle.ts."""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from board.models.bundle import BundleEnvelope

_SALT_BYTES = 16
_IV_BYTES = 12
_KEY_BYTES = 32
_PBKDF2_ITERATIONS = 100_000
_TAG_BYTES = 16


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """Derive a 256-bit key from *passphrase* and *salt* via PBKDF2-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=SHA256(),
        length=_KEY_BYTES,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    return kdf.derive(passphrase.encode("utf-8"))


def encrypt(payload_json: str, passphrase: str) -> BundleEnvelope:
    """Encrypt *payload_json* with AES-256-GCM, returning a :class:`BundleEnvelope`.

    The output is byte-compatible with the Node.js ``decryptBundle()`` in
    ``extension/src/bundle.ts``.
    """
    salt = os.urandom(_SALT_BYTES)
    iv = os.urandom(_IV_BYTES)
    key = _derive_key(passphrase, salt)

    aesgcm = AESGCM(key)
    # AESGCM.encrypt() returns ciphertext || 16-byte auth tag
    combined = aesgcm.encrypt(iv, payload_json.encode("utf-8"), None)

    ciphertext = combined[:-_TAG_BYTES]
    tag = combined[-_TAG_BYTES:]

    return BundleEnvelope(
        version=2,
        format="board-pass",
        salt=base64.b64encode(salt).decode(),
        iv=base64.b64encode(iv).decode(),
        ciphertext=base64.b64encode(ciphertext).decode(),
        tag=base64.b64encode(tag).decode(),
    )


def decrypt(envelope: BundleEnvelope, passphrase: str) -> str:
    """Decrypt a :class:`BundleEnvelope`, returning the plaintext JSON string.

    Raises :class:`cryptography.exceptions.InvalidTag` on a wrong passphrase.
    """
    salt = base64.b64decode(envelope.salt)
    iv = base64.b64decode(envelope.iv)
    ciphertext = base64.b64decode(envelope.ciphertext)
    tag = base64.b64decode(envelope.tag)

    key = _derive_key(passphrase, salt)

    aesgcm = AESGCM(key)
    # Reassemble ciphertext || tag for AESGCM.decrypt()
    plaintext = aesgcm.decrypt(iv, ciphertext + tag, None)
    return plaintext.decode("utf-8")
