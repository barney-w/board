---
title: Architecture
description: How Board works under the hood.
---

Board provisions cloud developer environments using a layered architecture:

```
justfile (CLI recipes)
  └─ scripts/ (setup, admin, provisioning)
       ├─ lib/ui.sh (terminal UI abstraction)
       ├─ lib/azure.sh (Azure provider)
       ├─ lib/manifest.sh (YAML manifest processing)
       └─ lib/keyvault.sh (secret management)
  └─ infra/ (Bicep templates + cloud-init)
  └─ extension/ (VS Code extension)
```

## Infrastructure layer

**Bicep templates** (`infra/main.bicep`) define the Azure resources:
- Virtual Machine (Ubuntu 24.04, configurable SKU)
- Network Security Group (SSH-only inbound)
- Public IP with DNS label
- OS disk with auto-delete

**Cloud-init** (`infra/cloud-init/cloud-init.yaml`) runs on first boot:
- Installs Docker, Python, Node.js, Go, Rust, and dev tools
- Configures SSH hardening
- Sets up systemd user services
- Installs the dynamic MOTD
- Creates the `board-help` command

## Provisioning engine

The provisioning engine (`scripts/provision-engine.sh`) runs after cloud-init and handles project-specific setup. It's a 9-phase pipeline:

1. **Connect** — establish SSH connection
2. **Clone** — clone project repositories
3. **Docker** — generate and start Docker Compose services
4. **Wait** — wait for Docker services to be healthy
5. **Install** — run project install commands
6. **Services** — create and start systemd user units
7. **Environment** — write `.env` files and fetch Key Vault secrets
8. **VS Code** — generate workspace file, tasks, and launch configs
9. **Health** — generate and upload the check script

## Manifest system

Project manifests (`.project.yaml`) are the core abstraction. A single YAML file generates:
- Docker Compose configuration
- Systemd service units
- Environment files with Key Vault secret injection
- VS Code workspace configuration
- Health check scripts with tree-drawn output

## VS Code extension

The extension provides:
- One-click connection via Remote-SSH
- Board pass import (AES-256-GCM encrypted bundles)
- Status bar with live VM state and health summary
- Welcome webview for first-time setup
- Automatic workspace detection and opening

## Security model

- VMs are SSH-only (no exposed service ports)
- Secrets stay in Azure Key Vault; fetched at provisioning time
- Board passes use AES-256-GCM encryption with password-derived keys
- SSH keys are ed25519
- Auto-shutdown at 7 PM reduces exposure window
