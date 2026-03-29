---
title: For Shapers (Admins)
description: Guide for team leads and DevOps engineers who provision and manage cloud dev environments.
---

A **shaper** is someone who provisions and manages cloud dev environments for their team. This is typically a tech lead, DevOps engineer, or senior developer.

## Board up a developer

```bash
just board
```

The wizard handles everything: Azure login, VM provisioning, cloud-init, project setup, and health verification.

## Managing boards

```bash
just shape
```

The admin menu shows your fleet status with colored dots (green = running, grey = stopped) and provides options to:

- Start/stop boards
- Wax a board (re-provision projects)
- Create board passes
- Manage secrets
- Run health checks

## Creating board passes

```bash
just export-pass alice
```

The board pass is an AES-256-GCM encrypted file containing SSH keys and connection details. Send it to the developer along with the passphrase (always via a separate channel — in person, phone call, or different messaging app).

## Project manifests

Each project has a `.project.yaml` manifest that declares everything needed:

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

See [Manifest Schema](/board/reference/manifest-schema/) for the full specification.

## Fleet operations

```bash
just fleet-status
```

Shows all boards across your environment with their status, TTFC, and health scores.
