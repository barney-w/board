"""Key Vault operations — creation, recovery, secrets, and RBAC.

Implements the state machine from scripts/lib/keyvault.sh:
1. If vault exists and is accessible -> return it
2. If vault is soft-deleted -> recover it
3. If fresh creation fails with conflict -> retry with purge
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.keyvault.secrets import SecretClient
from azure.mgmt.authorization import AuthorizationManagementClient
from azure.mgmt.authorization.models import RoleAssignmentCreateParameters
from azure.mgmt.keyvault import KeyVaultManagementClient
from azure.mgmt.keyvault.models import (
    Sku,
    SkuFamily,
    SkuName,
    VaultCreateOrUpdateParameters,
    VaultProperties,
)

from board.core.errors import BoardError

logger = logging.getLogger(__name__)

# Key Vault Secrets Officer built-in role ID
_SECRETS_OFFICER_ROLE_ID = "b86a8fe4-44ce-4948-aee5-eccb2c155cd7"

# Retry delay for soft-delete conflict resolution (seconds)
_KV_RETRY_DELAY = 10.0

# Maximum number of retries for conflict resolution
_KV_MAX_RETRIES = 3


async def create_or_recover_vault(
    credential: Any,
    subscription_id: str,
    resource_group: str,
    vault_name: str,
    location: str,
    tenant_id: str,
) -> str:
    """Create or recover a Key Vault, handling the soft-delete state machine.

    State machine mirrors scripts/lib/keyvault.sh:create_keyvault:
    1. Vault already exists -> return its URL
    2. Vault is soft-deleted -> recover it
    3. Fresh creation -> attempt create
    4. Create fails (conflict) -> poll for soft-deleted, purge, recreate

    Args:
        credential: Azure credential.
        subscription_id: Target subscription.
        resource_group: Resource group name.
        vault_name: Desired vault name.
        location: Azure region.
        tenant_id: AAD tenant ID for vault access policies.

    Returns:
        The vault URL (e.g. https://myvault.vault.azure.net/).

    Raises:
        BoardError: If creation fails after all retries.
    """
    client = KeyVaultManagementClient(credential, subscription_id)

    # 1. Check if vault already exists
    try:
        vault = await asyncio.to_thread(
            client.vaults.get,
            resource_group,
            vault_name,
        )
        logger.info("Key Vault '%s' already exists", vault_name)
        return vault.properties.vault_uri  # type: ignore[return-value]
    except HttpResponseError:
        pass  # Vault doesn't exist in this RG, continue

    # 2. Check for soft-deleted vault and recover
    try:
        deleted = await asyncio.to_thread(
            client.vaults.get_deleted,
            vault_name,
            location,
        )
        if deleted:
            logger.info("Recovering soft-deleted Key Vault '%s'", vault_name)
            poller = await asyncio.to_thread(
                lambda: client.vaults.begin_recover_deleted(  # type: ignore[attr-defined]
                    vault_name,
                    location,
                ),
            )
            vault = await asyncio.to_thread(poller.result)
            return vault.properties.vault_uri  # type: ignore[return-value]
    except HttpResponseError:
        pass  # No soft-deleted vault, continue with fresh creation

    # 3. Attempt fresh creation
    params = VaultCreateOrUpdateParameters(
        location=location,
        properties=VaultProperties(
            tenant_id=tenant_id,
            sku=Sku(family=SkuFamily.A, name=SkuName.STANDARD),
            access_policies=[],
            enable_rbac_authorization=True,
            enable_soft_delete=True,
            soft_delete_retention_in_days=7,
        ),
        tags={
            "project": "devvm",
            "managed-by": "board-cli",
        },
    )

    try:
        poller = await asyncio.to_thread(
            client.vaults.begin_create_or_update,
            resource_group,
            vault_name,
            params,
        )
        vault = await asyncio.to_thread(poller.result)
        logger.info("Key Vault '%s' created", vault_name)
        return vault.properties.vault_uri  # type: ignore[return-value]
    except HttpResponseError as exc:
        # 4. Creation conflict — vault may be in limbo (recently deleted,
        # not yet queryable as soft-deleted). Retry with purge.
        logger.warning(
            "Key Vault create failed — checking for soft-delete conflict: %s",
            exc,
        )

    for attempt in range(1, _KV_MAX_RETRIES + 1):
        await asyncio.sleep(_KV_RETRY_DELAY)
        try:
            deleted = await asyncio.to_thread(
                client.vaults.get_deleted,
                vault_name,
                location,
            )
            if deleted:
                logger.info(
                    "Found soft-deleted vault (attempt %d), purging...",
                    attempt,
                )
                poller = await asyncio.to_thread(
                    client.vaults.begin_purge_deleted,
                    vault_name,
                    location,
                )
                await asyncio.to_thread(poller.result)
                await asyncio.sleep(_KV_RETRY_DELAY)

                poller = await asyncio.to_thread(
                    client.vaults.begin_create_or_update,
                    resource_group,
                    vault_name,
                    params,
                )
                vault = await asyncio.to_thread(poller.result)
                logger.info(
                    "Key Vault '%s' created after purge (attempt %d)",
                    vault_name,
                    attempt,
                )
                return vault.properties.vault_uri  # type: ignore[return-value]
        except HttpResponseError:
            logger.info(
                "Retry %d/%d — waiting for soft-delete state to settle...",
                attempt,
                _KV_MAX_RETRIES,
            )
            continue

    msg = (
        f"Failed to create Key Vault '{vault_name}' after {_KV_MAX_RETRIES} retries. "
        f"Manual fix: az keyvault purge --name {vault_name}"
    )
    raise BoardError(msg)


async def get_secret(
    vault_url: str,
    credential: Any,
    secret_name: str,
) -> str | None:
    """Get a secret value from Key Vault.

    Returns:
        The secret value, or None if the secret doesn't exist.
    """
    client = SecretClient(vault_url=vault_url, credential=credential)
    try:
        secret = await asyncio.to_thread(client.get_secret, secret_name)
        return secret.value
    except ResourceNotFoundError:
        return None


async def set_secret(
    vault_url: str,
    credential: Any,
    secret_name: str,
    value: str,
) -> None:
    """Set a secret in Key Vault."""
    client = SecretClient(vault_url=vault_url, credential=credential)
    await asyncio.to_thread(client.set_secret, secret_name, value)


async def list_secrets(
    vault_url: str,
    credential: Any,
) -> list[str]:
    """List secret names in a Key Vault.

    Returns:
        List of secret names (not values).
    """
    client = SecretClient(vault_url=vault_url, credential=credential)
    props = await asyncio.to_thread(
        lambda: [p.name for p in client.list_properties_of_secrets() if p.name],
    )
    return props


async def ensure_secrets_officer_role(
    credential: Any,
    subscription_id: str,
    vault_id: str,
    principal_id: str,
) -> None:
    """Ensure a principal has the Key Vault Secrets Officer role on a vault.

    Idempotent — skips assignment if the role is already granted.

    Args:
        credential: Azure credential.
        subscription_id: Target subscription.
        vault_id: Full resource ID of the Key Vault.
        principal_id: Object ID of the user or service principal.
    """
    auth_client = AuthorizationManagementClient(credential, subscription_id)
    role_definition_id = (
        f"/subscriptions/{subscription_id}"
        f"/providers/Microsoft.Authorization"
        f"/roleDefinitions/{_SECRETS_OFFICER_ROLE_ID}"
    )

    # Check if assignment already exists
    existing = await asyncio.to_thread(
        lambda: list(
            auth_client.role_assignments.list_for_scope(
                scope=vault_id,
                filter=f"principalId eq '{principal_id}'",
            ),
        ),
    )
    for assignment in existing:
        if assignment.role_definition_id and assignment.role_definition_id.endswith(
            _SECRETS_OFFICER_ROLE_ID,
        ):
            logger.info("Secrets Officer role already assigned")
            return

    # Create the assignment
    import uuid

    assignment_name = str(uuid.uuid4())
    params = RoleAssignmentCreateParameters(
        role_definition_id=role_definition_id,
        principal_id=principal_id,
        principal_type="User",
    )  # type: ignore[call-arg]
    try:
        await asyncio.to_thread(
            auth_client.role_assignments.create,
            scope=vault_id,
            role_assignment_name=assignment_name,
            parameters=params,
        )
        logger.info("Secrets Officer role assigned to %s", principal_id)
    except HttpResponseError as exc:
        logger.warning("Could not assign Secrets Officer role: %s", exc)
