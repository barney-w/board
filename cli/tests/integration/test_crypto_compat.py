"""Cross-language compatibility test: Python encrypt -> Node.js decrypt.

Verifies that envelopes produced by the Python crypto module can be
decrypted by the Node.js ``decryptBundle()`` in the VS Code extension.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from board.bundle.crypto import encrypt

# Path to the compiled extension JS
_EXTENSION_OUT = Path(__file__).resolve().parents[3] / "extension" / "out"
_BUNDLE_JS = _EXTENSION_OUT / "bundle.js"

_NODE = shutil.which("node")

_SKIP_REASON_NO_NODE = "Node.js not available"
_SKIP_REASON_NO_EXTENSION = (
    f"Compiled extension not found at {_BUNDLE_JS}; run 'npm run build' in extension/"
)

# Small Node.js helper that requires the compiled bundle.js and decrypts a file.
# It re-uses the exact decryptBundle() the extension ships.
_NODE_HELPER = """\
const path = require('path');
const fs = require('fs/promises');

// The compiled extension bundle.js expects 'vscode' — stub it out so require() works.
const Module = require('module');
const originalResolve = Module._resolveFilename;
Module._resolveFilename = function (request, parent, ...args) {
  if (request === 'vscode') {
    return request;                // pretend it resolves
  }
  return originalResolve.call(this, request, parent, ...args);
};
require.cache['vscode'] = {
  id: 'vscode', filename: 'vscode', loaded: true, exports: {},
};

const bundleMod = require(process.argv[2]);   // path to bundle.js
const bundlePath = process.argv[3];           // .board-pass file
const passphrase = process.argv[4];

(async () => {
  const payload = await bundleMod.decryptBundle(bundlePath, passphrase);
  process.stdout.write(JSON.stringify(payload));
})().catch(err => {
  process.stderr.write(err.message + '\\n');
  process.exit(1);
});
"""

SAMPLE_PAYLOAD = {
    "developerName": "jbloggs",
    "environment": "personal",
    "region": "australiaeast",
    "regionShort": "aue",
    "hostname": "devvm-jbloggs.australiaeast.cloudapp.azure.com",
    "username": "devuser",
    "authMethod": "ssh-key",
    "sshPrivateKey": "-----BEGIN OPENSSH PRIVATE KEY-----\nfake-key-data\n-----END OPENSSH PRIVATE KEY-----\n",
    "sshPublicKey": "ssh-ed25519 AAAA fake@host",
    "resourceGroup": "rg-personal-aue-devvm",
    "vmName": "vm-personal-aue-devvm-jbloggs",
    "issuedAt": "2026-03-29T00:00:00Z",
    "validUntil": "2026-04-28T00:00:00Z",
}


@pytest.mark.skipif(not _NODE, reason=_SKIP_REASON_NO_NODE)
@pytest.mark.skipif(not _BUNDLE_JS.exists(), reason=_SKIP_REASON_NO_EXTENSION)
class TestNodeCompat:
    """Encrypt in Python, decrypt in Node.js using the real extension code."""

    def test_python_to_node_round_trip(self) -> None:
        passphrase = "cross-language-test-passphrase"
        payload_json = json.dumps(SAMPLE_PAYLOAD)

        envelope = encrypt(payload_json, passphrase)
        envelope_json = envelope.model_dump_json()

        with tempfile.TemporaryDirectory() as tmpdir:
            board_pass = Path(tmpdir) / "test.board-pass"
            board_pass.write_text(envelope_json)

            helper_script = Path(tmpdir) / "decrypt_helper.js"
            helper_script.write_text(_NODE_HELPER)

            result = subprocess.run(
                [
                    _NODE or "node",
                    str(helper_script),
                    str(_BUNDLE_JS),
                    str(board_pass),
                    passphrase,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            assert result.returncode == 0, (
                f"Node.js decryption failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
            )

            decrypted = json.loads(result.stdout)

            # Compare all fields from the original payload
            for key, expected in SAMPLE_PAYLOAD.items():
                assert decrypted[key] == expected, f"Mismatch on field {key!r}"
