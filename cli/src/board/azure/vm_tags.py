"""Read VM tags via the Azure CLI.

Sync helpers used by Typer commands. The async :mod:`board.azure.az` module
covers the long-running provisioning paths; this one is just for fast tag
reads inside command handlers.
"""

from __future__ import annotations

import subprocess

from board.core.errors import BoardError

VALID_AUTH_METHODS = ("entra-id", "ssh-key")


def resolve_auth_method(rg: str, vm: str) -> str:
    """Read the ``auth-method`` tag from *vm* in *rg* and return it.

    Raises :class:`BoardError` if the ``az`` call fails or the tag is missing
    or unrecognised. Never silently falls back — callers that want to override
    the tag should accept an ``--auth`` flag and short-circuit before calling
    this helper.
    """
    result = subprocess.run(  # noqa: S603, S607
        [
            "az",
            "vm",
            "show",
            "--resource-group",
            rg,
            "--name",
            vm,
            "--query",
            'tags."auth-method"',
            "-o",
            "tsv",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip() or "(no stderr output)"
        msg = (
            f"Could not read VM tags for '{vm}' in resource group '{rg}'.\n"
            f"  az vm show exited with code {result.returncode}: {stderr}\n"
            f"  Check that the VM exists and you are signed in to the right subscription."
        )
        raise BoardError(msg)

    tag = result.stdout.strip()

    if not tag:
        msg = (
            f"VM '{vm}' has no 'auth-method' tag. Board cannot tell whether to use "
            f"Entra ID or an SSH key.\n"
            f"  Fix the VM:  az vm update -g {rg} -n {vm} --set tags.auth-method=entra-id\n"
            f"  Or override: pass --auth entra-id (or --auth ssh-key) on this command."
        )
        raise BoardError(msg)

    if tag not in VALID_AUTH_METHODS:
        msg = (
            f"VM '{vm}' has an unrecognised 'auth-method' tag: {tag!r}.\n"
            f"  Expected one of {VALID_AUTH_METHODS}.\n"
            f"  Fix the VM:  az vm update -g {rg} -n {vm} --set tags.auth-method=entra-id\n"
            f"  Or override: pass --auth entra-id (or --auth ssh-key) on this command."
        )
        raise BoardError(msg)

    return tag
