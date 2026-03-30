---
title: For Shapers (Admins)
description: Provision and manage cloud dev environments for your team.
---

A **shaper** provisions and manages cloud dev environments. Typically a tech lead, DevOps engineer, or senior developer.

## Provision a board

```bash
just board
```

The wizard handles Azure login, VM creation, cloud-init, project provisioning, and health verification.

## Manage boards

```bash
just shape
```

The admin menu shows fleet status with coloured dots (green = running, grey = stopped) and provides options to start/stop boards, re-provision projects, create board passes, manage secrets, and run health checks.

## Create a board pass

```bash
just export-pass jbloggs
```

Creates an encrypted starter kit zip with SSH keys, connection details, the VS Code extension, and a setup script. Send it to the developer with the passphrase via a separate channel (in person, phone, different messaging app).

## Project manifests

Each project has a `.project.yaml` manifest in `projects/`:

```yaml
name: "my-api"
repo: "git@github.com:org/my-api.git"
requires: [python3, uv]
install: ["uv sync"]
docker:
  compose: true
services:
  - name: my-api
    command: "uvicorn main:app --port 8000"
    port: 8000
health:
  - label: "API"
    check: "curl -sf http://localhost:8000/health"
```

See [Manifest Schema](/board/reference/manifest-schema/) for the full spec.

## Fleet operations

```bash
just fleet-status
```

Shows all boards across your environment with status, uptime, and health.
