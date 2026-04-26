"""Round-trip tests for AES-256-GCM encrypt/decrypt and plaintext wrapping."""

from __future__ import annotations

import json

import pytest
from cryptography.exceptions import InvalidTag

from board.bundle.crypto import decrypt, encrypt, wrap_plaintext

SAMPLE_PAYLOAD = json.dumps(
    {
        "developerName": "jbloggs",
        "environment": "personal",
        "region": "australiaeast",
        "regionShort": "aue",
        "hostname": "devvm-jbloggs.australiaeast.cloudapp.azure.com",
        "username": "devuser",
        "authMethod": "ssh-key",
        "sshPrivateKey": "-----BEGIN OPENSSH PRIVATE KEY-----\nfake\n-----END OPENSSH PRIVATE KEY-----\n",
        "sshPublicKey": "ssh-ed25519 AAAA fake@host",
        "resourceGroup": "rg-personal-aue-devvm",
        "vmName": "vm-personal-aue-devvm-jbloggs",
        "issuedAt": "2026-03-29T00:00:00Z",
        "validUntil": "2026-04-28T00:00:00Z",
    }
)

ENTRA_PAYLOAD = json.dumps(
    {
        "developerName": "jbloggs",
        "environment": "personal",
        "region": "australiaeast",
        "regionShort": "aue",
        "hostname": "devvm-jbloggs.australiaeast.cloudapp.azure.com",
        "username": "devuser",
        "authMethod": "entra-id",
        "sshPrivateKey": "",
        "sshPublicKey": "",
        "resourceGroup": "rg-personal-aue-devvm",
        "vmName": "vm-personal-aue-devvm-jbloggs",
        "issuedAt": "2026-03-29T00:00:00Z",
        "validUntil": "2026-04-28T00:00:00Z",
    }
)


class TestRoundTrip:
    """Encrypt then decrypt and verify plaintext is preserved."""

    def test_basic_round_trip(self) -> None:
        passphrase = "correct horse battery staple"
        envelope = encrypt(SAMPLE_PAYLOAD, passphrase)
        result = decrypt(envelope, passphrase)
        assert json.loads(result) == json.loads(SAMPLE_PAYLOAD)

    @pytest.mark.parametrize(
        "passphrase",
        [
            "short123",
            "a" * 128,
            "P@$$w0rd!#%^&*()_+-={}[]|;':\",./<>?",
            "unicode passphrase \u2603\u2764\ufe0f\U0001f680",
        ],
        ids=["8-char", "128-char", "special-chars", "unicode"],
    )
    def test_various_passphrases(self, passphrase: str) -> None:
        envelope = encrypt(SAMPLE_PAYLOAD, passphrase)
        result = decrypt(envelope, passphrase)
        assert json.loads(result) == json.loads(SAMPLE_PAYLOAD)

    def test_wrong_passphrase_raises(self) -> None:
        envelope = encrypt(SAMPLE_PAYLOAD, "right passphrase")
        with pytest.raises(InvalidTag):
            decrypt(envelope, "wrong passphrase")

    def test_envelope_fields(self) -> None:
        envelope = encrypt(SAMPLE_PAYLOAD, "test passphrase!")
        assert envelope.version == 2
        assert envelope.format == "board-pass"
        # All fields should be non-empty base64 strings
        for field in ("salt", "iv", "ciphertext", "tag"):
            value = getattr(envelope, field)
            assert isinstance(value, str)
            assert len(value) > 0

    def test_different_encryptions_differ(self) -> None:
        """Two encryptions of the same plaintext should produce different ciphertext."""
        passphrase = "same passphrase"
        env1 = encrypt(SAMPLE_PAYLOAD, passphrase)
        env2 = encrypt(SAMPLE_PAYLOAD, passphrase)
        # Different random salt and IV each time
        assert env1.salt != env2.salt or env1.iv != env2.iv
        assert env1.ciphertext != env2.ciphertext

    def test_empty_payload(self) -> None:
        passphrase = "test passphrase!"
        envelope = encrypt("{}", passphrase)
        result = decrypt(envelope, passphrase)
        assert json.loads(result) == {}

    def test_large_payload(self) -> None:
        """Ensure large payloads (simulating big SSH keys) work."""
        large = json.dumps({"key": "A" * 100_000})
        passphrase = "large payload passphrase"
        envelope = encrypt(large, passphrase)
        result = decrypt(envelope, passphrase)
        assert json.loads(result) == json.loads(large)


class TestPlaintextEnvelope:
    """Tests for Entra ID plaintext (unencrypted) envelopes."""

    def test_wrap_plaintext_preserves_payload(self) -> None:
        envelope = wrap_plaintext(ENTRA_PAYLOAD)
        assert envelope.payload == json.loads(ENTRA_PAYLOAD)

    def test_wrap_plaintext_sets_auth_method(self) -> None:
        envelope = wrap_plaintext(ENTRA_PAYLOAD)
        assert envelope.auth_method == "entra-id"

    def test_wrap_plaintext_envelope_fields(self) -> None:
        envelope = wrap_plaintext(ENTRA_PAYLOAD)
        assert envelope.version == 2
        assert envelope.format == "board-pass"
        # Encrypted fields should be empty
        assert envelope.salt == ""
        assert envelope.iv == ""
        assert envelope.ciphertext == ""
        assert envelope.tag == ""

    def test_wrap_plaintext_serialises_with_alias(self) -> None:
        """Ensure authMethod (not auth_method) appears in JSON output."""
        envelope = wrap_plaintext(ENTRA_PAYLOAD)
        dumped = envelope.model_dump(by_alias=True)
        assert "authMethod" in dumped
        assert dumped["authMethod"] == "entra-id"
        assert dumped["payload"]["developerName"] == "jbloggs"
