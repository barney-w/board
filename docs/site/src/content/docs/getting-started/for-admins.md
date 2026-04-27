---
title: For Admins
description: Provision and manage cloud dev environments for your team.
---

An **admin** provisions and manages cloud dev environments. Typically a tech lead, DevOps engineer, or senior developer.

## Provision a board

```bash
just board
```

The wizard handles Azure login, VM creation, cloud-init, project provisioning, and health verification. By default, boards use **Entra ID** authentication — developers sign in with their Azure AD identity and no SSH keys are needed.

## Authentication methods

Board supports two auth methods, chosen during provisioning:

- **Entra ID** (default) — developers authenticate via `az login`. Short-lived certificates are generated automatically. No SSH keys in the board pass. Requires Azure CLI on the developer's machine.
- **SSH key** — a per-developer ed25519 key pair is generated and bundled into the board pass. No Azure CLI needed on the developer's machine.

### Granting access (Entra ID)

For Entra ID boards, grant developers access with a role:

```bash
just grant-access jbloggs jane@contoso.com           # developer role (default)
just grant-access jbloggs jane@contoso.com role=admin # full admin access
```

Roles: `admin` (VM admin + Key Vault), `developer` (SSH + reader), `viewer` (reader only).

## Manage boards

```bash
just admin
```

The admin menu shows fleet status with coloured dots (green = running, grey = stopped) and provides options to start/stop boards, re-provision projects, create board passes, manage secrets, and run health checks.

## Create a board pass

```bash
just export-pass jbloggs
```

Creates a starter kit zip with connection details, the VS Code extension, and a setup script. For Entra ID boards, the pass is unencrypted (no passphrase needed) and contains connection metadata only (no keys). For SSH key boards, the pass is encrypted and bundles the SSH private key — share the passphrase via a separate channel (in person, phone, different messaging app).

To force SSH key auth regardless of VM tag:

```bash
just export-ssh-pass jbloggs
```

## Governance

View enforced policies (VM limits, allowed SKUs, required auth):

```bash
just policies
```

View cost breakdown by developer:

```bash
just costs
just costs-dev jbloggs
```

## Project manifests

Each project has a `.project.yaml` manifest in `projects/`:

```yaml
name: "my-api"
repo: "git@github.com:org/my-api.git"
requires:
  tools: [python3, uv]
install:
  - label: "Install dependencies"
    run: "uv sync"
docker:
  compose_file: docker-compose.yml
  containers:
    - name: my-api-postgres
      health_cmd: "pg_isready -U myapi"
services:
  - name: my-api
    exec: "uvicorn main:app --port 8000"
    health_url: "http://localhost:8000/health"
health:
  - label: "API"
    check: "curl -sf http://localhost:8000/health"
    port: 8000
```

See [Manifest Schema](/board/reference/manifest-schema/) for the full spec.

## Fleet operations

```bash
just fleet-status
```

Shows all boards across your environment with status, uptime, and health.
