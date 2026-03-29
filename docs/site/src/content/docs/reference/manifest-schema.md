---
title: Manifest Schema
description: Complete reference for .project.yaml manifest files.
---

Project manifests define everything Board needs to provision a project on a developer's board. They live in the `projects/` directory and use the `.project.yaml` extension.

## Quick example

```yaml
name: "surf"
description: "Surf API — the core backend service"
repo: "git@github.com:org/surf.git"

requires:
  - python3
  - uv
  - docker

install:
  - "uv sync"
  - "uv run alembic upgrade head"

docker:
  compose: true
  services:
    - name: postgres
      image: postgres:16
      ports: ["5432:5432"]
      env:
        POSTGRES_DB: surf
        POSTGRES_USER: dev
        POSTGRES_PASSWORD: dev

services:
  - name: surf-api
    command: "uv run uvicorn surf.main:app --host 0.0.0.0 --port 8090"
    port: 8090
    health:
      endpoint: "http://localhost:8090/api/v1/health"
      interval: 10

env:
  DATABASE_URL: "postgresql://dev:dev@localhost:5432/surf"
  ANTHROPIC_API_KEY: "keyvault:anthropic-api-key"

vscode:
  tasks:
    - label: "Run API"
      type: "shell"
      command: "uv run uvicorn surf.main:app --reload --port 8090"

health:
  - label: "Postgres"
    check: "pg_isready -h localhost -p 5432"
  - label: "Surf API"
    check: "curl -sf http://localhost:8090/api/v1/health"
  - label: "Alembic"
    check: "uv run alembic check"
```

## Top-level fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Project identifier (used in directory names, service names) |
| `description` | string | No | Human-readable description |
| `repo` | string | Yes | Git clone URL |
| `requires` | string[] | No | System tools that must be available |
| `install` | string[] | No | Commands to run after cloning (in order) |
| `docker` | object | No | Docker Compose configuration |
| `services` | object[] | No | Application services (systemd units) |
| `env` | map | No | Environment variables |
| `vscode` | object | No | VS Code workspace configuration |
| `health` | object[] | No | Health check definitions |

## `docker` section

```yaml
docker:
  compose: true              # Generate docker-compose.yml
  services:
    - name: postgres         # Service name
      image: postgres:16     # Docker image
      ports: ["5432:5432"]   # Port mappings
      env:                   # Environment variables
        POSTGRES_DB: mydb
      volumes:               # Volume mounts (optional)
        - "pgdata:/var/lib/postgresql/data"
```

## `services` section

Each service becomes a systemd user unit:

```yaml
services:
  - name: my-api             # Unit name (board-<name>.service)
    command: "uvicorn ..."   # ExecStart command
    port: 8090               # Primary port (for health checks)
    working_directory: "."   # Relative to project root
    health:
      endpoint: "http://localhost:8090/health"
      interval: 10           # Seconds between checks
```

## `env` section

Environment variables are injected into the service environment files and the project's `.env`:

```yaml
env:
  DATABASE_URL: "postgresql://dev:dev@localhost:5432/mydb"
  REDIS_URL: "redis://localhost:6379"
  API_KEY: "keyvault:my-api-key"     # Fetched from Azure Key Vault
  DEBUG: "true"
```

Values prefixed with `keyvault:` are fetched from Azure Key Vault during provisioning. The secret name after the colon is looked up in the configured Key Vault.

## `health` section

Health checks are compiled into the board's `check` script:

```yaml
health:
  - label: "Postgres"
    check: "pg_isready -h localhost -p 5432"
  - label: "API"
    check: "curl -sf http://localhost:8090/health"
  - label: "Migrations"
    check: "uv run alembic check"
    hint: "Run: uv run alembic upgrade head"
```

The optional `hint` field shows a fix suggestion when the check fails.

## Auto-generating manifests

Run `just init` in any project directory to auto-detect the stack and generate a manifest:

```bash
cd ~/my-project
just init > my-project.project.yaml
```
