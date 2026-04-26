"""Policy configuration model — the board.policies.yaml schema."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AutoShutdownPolicy(BaseModel):
    """Auto-shutdown enforcement policy."""

    enabled: bool = True
    time: str = "1900"
    backstop_time: str = "2200"
    timezone: str = "AUS Eastern Standard Time"
    user_can_override: bool = False


class AutoStartPolicy(BaseModel):
    """Auto-start schedule policy."""

    enabled: bool = False
    time: str = "0800"
    timezone: str = "AUS Eastern Standard Time"


class ExpirationPolicy(BaseModel):
    """VM expiration policy."""

    enabled: bool = False
    max_days: int = 90


class PoliciesConfig(BaseModel):
    """Complete board.policies.yaml schema.

    Policies are checked by the CLI before provisioning. They enforce
    guardrails on VM count, allowed sizes, regions, and schedule settings.
    """

    model_config = ConfigDict(populate_by_name=True)

    max_vms_per_user: int = 1
    max_vms_total: int = 20
    allowed_vm_sizes: list[str] = [
        "Standard_D2s_v6",
        "Standard_D4s_v6",
        "Standard_D2s_v5",
    ]
    allowed_regions: list[str] = ["australiaeast"]
    auto_shutdown: AutoShutdownPolicy = AutoShutdownPolicy()
    auto_start: AutoStartPolicy = AutoStartPolicy()
    expiration: ExpirationPolicy = ExpirationPolicy()
    require_entra_auth: bool = True
    require_mfa: bool = True
