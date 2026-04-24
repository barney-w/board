# Board — Master Technical Reference

> **Version:** CLI 2.0.0 / Extension 0.1.0
> **License:** Apache 2.0
> **Repository:** github.com/barney-w/board
> **Generated:** 2026-03-30

---

## Table of Contents

- [1. Project Overview](#1-project-overview)
  - [1.1 What Board Is](#11-what-board-is)
  - [1.2 The Problem](#12-the-problem)
  - [1.3 The Vision](#13-the-vision)
  - [1.4 Design Principles](#14-design-principles)
- [2. Architecture](#2-architecture)
  - [2.1 Layered Stack](#21-layered-stack)
  - [2.2 Component Map](#22-component-map)
  - [2.3 Data Flow](#23-data-flow)
  - [2.4 Security Model](#24-security-model)
- [3. Repository Structure](#3-repository-structure)
- [4. Board CLI (Python)](#4-board-cli-python)
  - [4.1 Package Metadata](#41-package-metadata)
  - [4.2 Command Reference](#42-command-reference)
  - [4.3 Core Module — config.py](#43-core-module--configpy)
  - [4.4 Core Module — errors.py](#44-core-module--errorspy)
  - [4.5 Core Module — manifest.py](#45-core-module--manifestpy)
  - [4.6 Pydantic Models](#46-pydantic-models)
  - [4.7 Azure SDK Wrappers](#47-azure-sdk-wrappers)
  - [4.8 SSH Management](#48-ssh-management)
  - [4.9 Bundle (Encryption and Packaging)](#49-bundle-encryption-and-packaging)
  - [4.10 Provisioning Engine](#410-provisioning-engine)
  - [4.11 User Interface](#411-user-interface)
  - [4.12 CLI Commands In Depth](#412-cli-commands-in-depth)
- [5. VS Code Extension (TypeScript)](#5-vs-code-extension-typescript)
  - [5.1 Extension Manifest](#51-extension-manifest)
  - [5.2 Module Reference](#52-module-reference)
  - [5.3 Commands](#53-commands)
  - [5.4 Board Pass Card UI](#54-board-pass-card-ui)
  - [5.5 Connection Workflow](#55-connection-workflow)
  - [5.6 Polling and Status](#56-polling-and-status)
  - [5.7 Sidebar and Cheatsheet](#57-sidebar-and-cheatsheet)
- [6. Infrastructure (Bicep + Cloud-Init)](#6-infrastructure-bicep--cloud-init)
  - [6.1 Bicep Templates](#61-bicep-templates)
  - [6.2 Cloud-Init](#62-cloud-init)
  - [6.3 Auto-Shutdown](#63-auto-shutdown)
  - [6.4 Key Vault Integration](#64-key-vault-integration)
- [7. Project Manifest System](#7-project-manifest-system)
  - [7.1 Schema Reference](#71-schema-reference)
  - [7.2 Output Artefacts](#72-output-artefacts)
  - [7.3 Bundled Manifests](#73-bundled-manifests)
  - [7.4 Example Manifests](#74-example-manifests)
  - [7.5 Auto-Detection](#75-auto-detection)
- [8. Justfile Recipes](#8-justfile-recipes)
- [9. CI/CD and Release](#9-cicd-and-release)
  - [9.1 CI Pipeline](#91-ci-pipeline)
  - [9.2 Release Pipeline](#92-release-pipeline)
  - [9.3 Docs Deployment](#93-docs-deployment)
  - [9.4 VHS Recording](#94-vhs-recording)
- [10. Documentation Site](#10-documentation-site)
- [11. Testing](#11-testing)
  - [11.1 Python Test Suite](#111-python-test-suite)
  - [11.2 Extension Test Suite](#112-extension-test-suite)
  - [11.3 Cross-Language Crypto Compatibility](#113-cross-language-crypto-compatibility)
- [12. Cross-Component Contracts](#12-cross-component-contracts)
- [13. Developer Setup](#13-developer-setup)
- [14. Workflows](#14-workflows)
  - [14.1 Admin: Provision a Board](#141-admin-provision-a-board)
  - [14.2 Admin: Export a Board Pass](#142-admin-export-a-board-pass)
  - [14.3 Developer: Get Connected](#143-developer-get-connected)
  - [14.4 Admin: Fleet Management](#144-admin-fleet-management)
- [15. Technology Stack Summary](#15-technology-stack-summary)

---

## 1. Project Overview

### 1.1 What Board Is

Board is an open-source platform for provisioning consistent, reproducible cloud development environments on Azure. It combines infrastructure-as-code (Bicep), YAML-driven project manifests, encrypted credential handoff, and a VS Code extension to deliver zero-configuration developer onboarding.

An admin runs `just board` to provision a cloud VM, then `just export-pass jbloggs` to create an encrypted starter kit. The developer unzips, double-clicks "Setup Board", enters a passphrase, clicks "Connect Now", and is coding on a fully configured cloud VM with databases running, services healthy, and VS Code preconfigured — typically in under two minutes from first click.

### 1.2 The Problem

Local development environments are broken. Every developer's machine is a unique snowflake — different operating systems, hardware, stateful environments that drift over time. A team of ten losing thirty minutes per week to environment issues burns 260 hours per year. New hires spend days following stale READMEs before writing their first line of code. "Works on my machine" is a systemic failure, not a joke.

The industry largely ignores this friction because it is invisible — distributed across individuals, normalised as "just part of the job". The cost compounds: wasted onboarding time, inconsistent bug reproduction, broken CI caused by environment divergence, and knowledge silos around tribal setup procedures.

### 1.3 The Vision

Board treats developer environments as infrastructure. The same manifest that provisions a fresh VM also generates health checks, VS Code configurations, systemd services, and debug launchers. The `check` command gives a deterministic answer to "is my environment working?" in seconds. Every developer gets the same environment from day one — identical tools, identical services, identical configuration.

**Core tenets:**

- **Environment as code** — A single `.project.yaml` manifest is the source of truth
- **Zero-trust onboarding** — No README following, no tribal knowledge, no "ask Sarah"
- **Verifiable health** — Every environment can prove it works, programmatically
- **Your cloud, your control** — Runs in your Azure subscription, Apache 2.0 licensed, no vendor lock-in

### 1.4 Design Principles

| Principle | Implementation |
|---|---|
| **Manifest-driven** | Data, not scripts. YAML manifests are parseable, validatable, and generate multiple outputs from a single source |
| **Idempotent** | Every operation is safe to run repeatedly. Key Vault creation recovers soft-deleted vaults. SSH config blocks are marker-delimited. Systemd units are overwritten cleanly |
| **Async-first** | All network operations (Azure SDK, SSH, cloud-init polling) use asyncio |
| **Non-interactive mode** | Full support for CI/CD via `BOARD_*` environment variables and `--non-interactive` flag |
| **Graceful degradation** | Extension works without Azure CLI (no polling, but connect still works). Cloud-init can fail partially without blocking the entire provision |
| **Cross-component contracts** | Naming conventions, encryption formats, and SSH config markers are shared contracts tested across Python and TypeScript |
| **Security by default** | SSH-only VMs, no exposed service ports, AES-256-GCM encrypted credentials, ed25519 keys, Key Vault for secrets, auto-shutdown |

---

## 2. Architecture

### 2.1 Layered Stack

```
┌─────────────────────────────────────────────────┐
│  Layer 4: VS Code Extension (TypeScript)         │
│  Import pass, connect, health check, status bar  │
├─────────────────────────────────────────────────┤
│  Layer 3: Board CLI (Python)                     │
│  Provisioning wizard, fleet management, passes   │
├─────────────────────────────────────────────────┤
│  Layer 2: Cloud-Init (YAML)                      │
│  OS setup — Docker, languages, tools, hardening  │
├─────────────────────────────────────────────────┤
│  Layer 1: Bicep (Infrastructure-as-Code)         │
│  VM, VNet, NSG, Key Vault, auto-shutdown         │
└─────────────────────────────────────────────────┘
```

**Layer 1 — Bicep:** Declares Azure infrastructure. Parameterised templates deploy a VM with networking, security groups, managed identity, and optional Key Vault RBAC. Uses Azure Verified Modules (AVM) for composition.

**Layer 2 — Cloud-Init:** Runs on first VM boot (~8 minutes). Installs Docker, Python 3.12, Node.js 20, dev tools, configures SSH hardening, creates the `devuser` account, writes the dynamic MOTD, sets up systemd timers, and creates a sample `hello-board` project.

**Layer 3 — Board CLI:** Python package that orchestrates the entire lifecycle. Interactive 5-phase wizard for provisioning, 9-phase engine for project setup, fleet management, board pass encryption, and health verification.

**Layer 4 — VS Code Extension:** Developer-facing interface. Imports encrypted board passes, manages SSH configuration, connects to remote VMs, polls VM status, displays health in the status bar, and provides a guided onboarding walkthrough.

### 2.2 Component Map

```
board/
├── cli/              Board CLI (Python 3.12, typer, Rich, Azure SDK, asyncssh)
│   └── src/board/
│       ├── cli/          Command modules (setup, admin, fleet, vm, export_pass, init, etc.)
│       ├── core/         Config derivation, error hierarchy, manifest parsing + generation
│       ├── models/       Pydantic models (ProjectManifest, BundlePayload, DeploymentConfig)
│       ├── azure/        Azure SDK wrappers (auth, compute, deployment, keyvault)
│       ├── ssh/          asyncssh sessions, SSH config management, key generation
│       ├── provision/    9-phase provisioning engine, orchestrator, cloud-init wait
│       ├── bundle/       AES-256-GCM encryption, payload assembly, ZIP packaging, SVG rendering
│       └── ui/           Rich console, questionary prompts, boarding pass display
├── extension/        VS Code Extension (TypeScript 5.9, esbuild)
│   └── src/
│       ├── extension.ts       Entry point, command registration, event wiring
│       ├── azure.ts           Azure CLI wrapper (never-throws)
│       ├── bundle.ts          AES-256-GCM decryption, board pass import
│       ├── config.ts          Settings and naming derivation
│       ├── connection.ts      SSH connection orchestration (7-step workflow)
│       ├── ssh.ts             SSH config file management
│       ├── polling.ts         VM status polling service (event-driven)
│       ├── statusBar.ts       Status bar widget with health integration
│       ├── sidebar.ts         Three tree-view providers (status, actions, cheatsheet)
│       ├── boardPassCard.ts   Boarding pass webview (holographic card UI)
│       ├── boardPassEditor.ts Custom read-only editor for .board-pass files
│       ├── terminal.ts        Terminal profile and workspace terminals
│       ├── cheatsheet.ts      Quick-reference webview
│       ├── firstRun.ts        Post-connect setup detection
│       └── welcome.ts         First-time onboarding panel
├── infra/            Azure infrastructure
│   ├── main.bicep            VM + VNet + NSG + auto-shutdown
│   ├── modules/
│   │   ├── auto-shutdown.bicep   DevTestLab daily shutdown schedule
│   │   ├── keyvault-role.bicep   Key Vault Secrets User RBAC
│   │   ├── vm-login-roles.bicep  VM Administrator Login RBAC (Entra ID)
│   │   └── auto-start.bicep      Logic App weekday auto-start schedule
│   └── cloud-init/           First-boot provisioning
├── projects/         Project manifests
│   ├── surf.project.yaml         Production: FastAPI + Postgres
│   ├── surf-kit.project.yaml     Production: React component library
│   ├── examples/                 Reference manifests (Django, Go, Rails, Spring Boot)
│   └── community/                Community-contributed manifests
├── docs/             Astro Starlight documentation site
├── justfile          50+ recipes for every operation
└── .github/          CI, release, docs deployment, VHS recording workflows
```

### 2.3 Data Flow

```
Admin Machine                        Azure Cloud                     Developer Machine
─────────────                        ───────────                     ─────────────────
just board                           ┌──────────────┐
  │                                  │ Bicep Deploy │
  ├─ Bicep deploy ──────────────────>│ VM + VNet    │
  │                                  │ NSG + KV     │
  │                                  └──────┬───────┘
  │                                         │ cloud-init
  │                                         ▼
  │                                  ┌──────────────┐
  ├─ SSH (wait for ready) ──────────>│ Docker       │
  │                                  │ Python, Node │
  │                                  │ Dev tools    │
  ├─ SSH (provision projects) ──────>│ git clone    │
  │                                  │ docker up    │
  │                                  │ systemd svcs │
  │                                  └──────────────┘
  │
just export-pass jbloggs
  │
  ├─ Read SSH keys
  ├─ AES-256-GCM encrypt ──────────> {name}.board-pass
  ├─ Package ZIP ───────────────────> {name}-board.zip
  │                                       │
  │   (email/file share)                  │
  │   (passphrase via separate channel)   ▼
  │                                  ┌───────────────┐
  │                                  │ Unzip         │
  │                                  │ Setup Board   │
  │                                  │ Enter phrase  │
  │                                  │ Click Connect │
  │                                  └───────┬───────┘
  │                                          │ Remote-SSH
  │                                          ▼
  │                                  ┌───────────────┐
  │                                  │ Coding on VM  │
  │                                  │ ~/projects/   │
  │                                  └───────────────┘
```

### 2.4 Security Model

| Layer | Mechanism | Detail |
|---|---|---|
| **VM access** | SSH-only | NSG blocks all inbound except SSH (port 22). No service ports exposed |
| **SSH hardening** | sshd_config | `PermitRootLogin no`, `PasswordAuthentication no`, `X11Forwarding no`, `MaxAuthTries 6` (raised from 3 for Entra ID `az ssh` agent key negotiation) |
| **Entra ID SSH** | AADSSHLogin VM extension | Default auth method. Short-lived certificates (~1 hour), tenant-locked, RBAC-scoped. No persistent keys |
| **SSH keys** | ed25519 | Alternative auth. Generated per-developer, never reused. Stored at `~/.ssh/devvm-{name}` |
| **Credential transport** | AES-256-GCM | Board passes encrypted with PBKDF2-SHA256 (100,000 iterations), 16-byte salt, 12-byte IV |
| **Two-channel delivery** | Split knowledge | ZIP file delivered by one channel (email/file share), passphrase by another (in person/SMS) |
| **Secrets management** | Azure Key Vault | Secrets fetched at provisioning time via managed identity. RBAC-controlled (Key Vault Secrets User role) |
| **VM identity** | System-assigned managed identity | Used for Key Vault access. No shared keys or connection strings |
| **Trusted Launch** | Secure Boot + vTPM | Enabled by default on all VMs |
| **Auto-shutdown** | DevTestLab schedule | VMs stop at 7 PM daily. Reduces exposure window and cost |
| **Key rotation** | `board rotate-key` | Generates new keypair, pushes via old key, swaps atomically |

---

## 3. Repository Structure

```
board/
├── .claude/                    Claude Code settings and custom commands
│   ├── settings.json
│   ├── settings.local.json
│   └── commands/
│       └── debug.md            Custom debug skill (315-line diagnostic protocol)
├── .editorconfig               2-space default, 4-space for shell/justfile, LF endings
├── .gitignore                  Env files, SSH keys, build artefacts, Azure state
├── .github/
│   ├── FUNDING.yml             GitHub Sponsors: barney-w
│   ├── PULL_REQUEST_TEMPLATE.md  What/Why/How checklist
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug.yml             Board version, health output, repro steps
│   │   ├── feature.yml         Description, use case, alternatives
│   │   └── config.yml          Links to docs
│   └── workflows/
│       ├── ci.yml              6-job pipeline (manifests, Bicep, Python lint/test, crypto, extension)
│       ├── docs.yml            Astro build → GitHub Pages
│       ├── release.yml         Tag-triggered VSIX build → GitHub Release
│       └── vhs.yml             Terminal GIF recording
├── CHANGELOG.md                Keep a Changelog format, SemVer
├── CONTRIBUTING.md             Dev setup, code style, submission guide
├── LICENSE                     Apache License 2.0
├── README.md                   Project homepage with demos and quick start
├── justfile                    50+ recipes (board, admin, fleet, vm ops, testing, linting)
├── cli/                        Python CLI package
│   ├── pyproject.toml          Hatchling build, uv managed, Python 3.12+
│   ├── README.md               CLI-specific docs
│   ├── src/board/              Source (7 subpackages, ~7,065 lines)
│   ├── tests/                  Unit + integration tests
│   └── scripts/                PDF generation
├── extension/                  VS Code extension
│   ├── package.json            Extension manifest (commands, views, editors, config)
│   ├── tsconfig.json           ES2022 target, strict mode
│   ├── esbuild.config.js       Bundler (prod minified, dev sourcemaps)
│   ├── vitest.config.ts        Test runner config
│   ├── src/                    TypeScript source (15 modules)
│   ├── test/                   Unit tests + vscode mock
│   └── resources/              Icons, walkthrough markdown
├── infra/                      Azure infrastructure
│   ├── main.bicep              Main template (303 lines, AVM composition)
│   ├── main.json               Compiled ARM template
│   ├── bicepconfig.json        Linter rules (error on unused params, no hardcoded URLs)
│   ├── modules/
│   │   ├── auto-shutdown.bicep DevTestLab schedule
│   │   └── keyvault-role.bicep RBAC assignment (Secrets User)
│   └── cloud-init/
│       └── cloud-init.yaml     First-boot provisioning (725 lines)
├── projects/                   Project manifests
│   ├── surf.project.yaml       FastAPI + Postgres (production)
│   ├── surf-kit.project.yaml   React component library (production)
│   ├── examples/               Django, Go, Rails, Spring Boot reference manifests
│   └── community/              Community contributions (with README guidelines)
├── docs/
│   ├── assets/                 SVG logos, hero banners, diagrams
│   ├── plans/                  Internal planning documents (gitignored from dist)
│   └── site/                   Astro Starlight documentation site
│       ├── package.json        Astro 5.18 + Starlight 0.37
│       └── src/content/
│           ├── docs/           Getting started guides, reference docs
│           └── blog/           (planned)
└── barney-board/               Starter kit build output (gitignored)
```

---

## 4. Board CLI (Python)

### 4.1 Package Metadata

| Field | Value |
|---|---|
| **Name** | board |
| **Version** | 2.0.0 |
| **Python** | >= 3.12 |
| **Build system** | Hatchling |
| **Package manager** | uv |
| **Entry point** | `board = "board.cli:app"` |

**Core dependencies:**

| Package | Version | Purpose |
|---|---|---|
| `typer` | >= 0.15 | CLI framework with subcommands |
| `questionary` | >= 2.1 | Interactive prompts (input, select, checklist, confirm, password) |
| `rich` | >= 14.0 | Terminal UI (panels, tables, spinners, progress bars, theming) |
| `asyncssh` | >= 2.22 | SSH connections, key generation, SFTP |
| `ruamel.yaml` | >= 0.18 | YAML parsing (round-trip preserving) |
| `pydantic` | >= 2.10 | Data validation and serialisation |
| `cryptography` | >= 44.0 | AES-256-GCM encryption, PBKDF2 key derivation |
| `azure-identity` | >= 1.19 | DefaultAzureCredential |
| `azure-mgmt-resource` | >= 23.3 | ARM deployments, resource groups |
| `azure-mgmt-compute` | >= 34.0 | VM lifecycle (start, stop, delete, run-command) |
| `azure-mgmt-network` | >= 28.0 | NIC and public IP management |
| `azure-mgmt-keyvault` | >= 10.4 | Key Vault creation and recovery |
| `aiohttp` | >= 3.13.4 | Async HTTP (webhook notifications, REST API calls) |

**Dev dependencies:** pytest, pytest-asyncio, pytest-cov, mypy, ruff

### 4.2 Command Reference

```
board up                Interactive 5-phase wizard — provisions a VM in ~11 min
board admin             Admin control panel (fleet status, manage boards, secrets)
board fleet             Fleet dashboard with metrics for all boards
board init [PATH]       Detect project stack, generate .project.yaml manifest
board smoke-test NAME   Run health checks on a deployed board
board export-pass NAME  Create encrypted board pass for a developer

board vm start NAME     Start a VM
board vm stop NAME      Stop (deallocate) a VM
board vm ssh NAME       SSH into a VM
board vm ls             List all VMs in the environment
board vm status NAME    Show detailed VM status
board vm delete NAME    Delete a VM and associated resources
board vm keygen NAME    Generate SSH keypair for a VM

board ssh-config show NAME    Print SSH config block (auto-detects auth method)
board ssh-config write NAME   Write to ~/.ssh/config (idempotent, auto-detects)
board ssh-config remove NAME  Remove managed block

board create-rg               Create resource group
board create-vm NAME          Direct Bicep deploy (no wizard)
board validate                Validate Bicep template
board what-if NAME            ARM what-if preview
board destroy                 Delete entire environment
board preflight NAME          Check prerequisites

board install-projects NAME   Provision projects on a board
board project-status NAME     Check project service health
board wait-ready NAME         Wait for cloud-init to complete
board rotate-key NAME         Rotate SSH key atomically

board vm grant-access EMAIL NAME  Grant Entra ID access (--role admin/developer/viewer)
board costs                       Show cost breakdown by developer
board policies show               Show policy enforcement rules
```

**Global flags:**

| Flag | Env var | Description |
|---|---|---|
| `--dry-run` | `BOARD_DRY_RUN` | Validate inputs without deploying |
| `--non-interactive` | `BOARD_NON_INTERACTIVE` | Use env vars/defaults, skip prompts |
| `--env` | `BOARD_ENVIRONMENT` | Environment name (e.g. `personal`) |
| `--location` | `BOARD_LOCATION` | Azure region (e.g. `australiaeast`) |
| `--region-short` | `BOARD_REGION_SHORT` | Short region code (e.g. `aue`) |

### 4.3 Core Module — config.py

Centralises all naming conventions. These derivations **must match** `extension/src/config.ts` exactly — this is a shared contract enforced by cross-language tests.

```python
DEV_NAME_PATTERN = "^[a-z][a-z0-9]{0,11}$"

ssh_host_alias(name)          → "devvm-{name}"
hostname(name, region)        → "devvm-{name}.{region}.cloudapp.azure.com"
resource_group(env, region)   → "rg-{env}-{region}-devvm"
vm_name(env, region, name)    → "vm-{env}-{region}-devvm-{name}"
ssh_key_path(name)            → "~/.ssh/devvm-{name}"
tunnel_url(name)              → "https://vscode.dev/tunnel/devvm-{name}"
```

**Environment resolution:**
- `get_env(key, default)` — checks env vars with `BOARD_` prefix fallback
- `is_non_interactive()` — checks `BOARD_NON_INTERACTIVE` (1/true/yes)
- `is_dry_run()` — checks `BOARD_DRY_RUN`
- `discover_bicepparams(infra_dir)` — scans `infra/config/*.bicepparam`, returns `(env_name, Path)` tuples

### 4.4 Core Module — errors.py

Exception hierarchy for domain-specific failure handling:

```
BoardError (base)
├── PreflightError      — Missing prerequisites
├── DeploymentError     — Azure deployment failures
├── SSHError            — SSH connection/command failures
├── ManifestError       — Invalid manifest parsing
├── CryptoError         — Encryption/decryption failures
└── ProvisionError      — Project provisioning failures
```

Also provides `retry[T]()` — generic async retry with exponential backoff (configurable max_attempts, delay, backoff multiplier, optional on_retry callback).

### 4.5 Core Module — manifest.py

Loads `.project.yaml` files and generates artefacts from them.

**Loading:**
- `load(path) → ProjectManifest` — parse single manifest
- `load_all(directory, filter_names) → [ProjectManifest]` — parse all manifests in directory
- `list_projects(directory) → [(name, description)]` — lightweight listing

**Generation (single project):**
- `generate_systemd_unit(service, project_path) → str` — systemd user unit file
- `generate_vscode_tasks(manifest) → str` — tasks.json
- `generate_vscode_launch(manifest) → str` — launch.json
- `generate_vscode_settings(manifest) → str` — settings.json

**Generation (multi-project):**
- `generate_workspace(manifests) → str` — `board.code-workspace` with remote port forwarding for all projects
- `generate_check_script(manifests) → str` — consolidated bash health-check script with system checks (Docker, disk, memory, code-server), per-project service health, systemd timer status, and TTFC metrics

### 4.6 Pydantic Models

#### ProjectManifest (`models/manifest.py`)

The core schema for `.project.yaml` files:

```python
class ProjectManifest:
    name: str                           # Project identifier
    description: str | None             # Human-readable description
    repo: str                           # Git clone URL
    path: str                           # Default: ~/projects/{name}
    requires: Requires                  # tools[], cloud_init flag
    install: list[InstallStep]          # label + run command
    docker: DockerConfig | None         # compose_file, containers[]
    post_docker: list[InstallStep]      # Run after containers healthy
    services: list[Service]             # Systemd user units
    env: EnvConfig | None               # file, fallback, keyvault_secrets, hardcoded, required
    vscode: VscodeConfig | None         # ports, tasks, launch, settings
    workspace: WorkspaceConfig | None   # Terminal panes for workspace layout
    health: list[HealthCheck]           # label, check command, port
```

**Supporting types:**
- `Requires` — tools (list[str]), cloud_init (bool)
- `InstallStep` — label, run
- `DockerContainer` — name, restart_policy, health_cmd, health_interval, health_timeout
- `DockerConfig` — compose_file, containers[]
- `Service` — name, description, exec_ (aliased "exec"), working_dir, env_file, extra_path, health_url, health_timeout
- `EnvConfig` — file, fallback, keyvault_secrets{}, hardcoded{}, required[]
- `VscodeConfig` — ports{}, tasks[], launch[], settings{}
- `HealthCheck` — label, check, port

#### DeploymentConfig (`models/deployment.py`)

Internal dataclass mirroring `config.py` derivations:

```python
class DeploymentConfig:
    developer_name: str
    environment: str
    region: str
    region_short: str
    # Properties: ssh_host_alias, hostname, resource_group, vm_name,
    #             ssh_key_path, ssh_key_path_expanded, tunnel_url
```

**PhaseResult** — phase number, name, success flag, elapsed_seconds, warnings[], errors[]

**DeploymentResult** — config + phases[] + total_elapsed_seconds, with computed success/all_warnings/all_errors properties

#### BundlePayload (`models/bundle.py`)

Byte-compatible with `extension/src/bundle.ts` (camelCase JSON serialisation):

```python
class BundlePayload:
    developer_name: str       # → "developerName"
    environment: str
    region: str
    region_short: str         # → "regionShort"
    hostname: str
    username: str
    auth_method: str          # → "authMethod"
    ssh_private_key: str      # → "sshPrivateKey"
    ssh_public_key: str       # → "sshPublicKey"
    resource_group: str       # → "resourceGroup"
    vm_name: str              # → "vmName"
    issued_at: str | None     # → "issuedAt" (ISO-8601)
    valid_until: str | None   # → "validUntil" (ISO-8601)
    browser_ide: BrowserIdeConfig | None  # → "browserIde"
```

**BundleEnvelope** — version (2), format ("board-pass"), salt, iv, ciphertext, tag (all base64-encoded)

### 4.7 Azure SDK Wrappers

#### auth.py — Authentication
- `get_credential()` — `DefaultAzureCredential` (excludes `SharedTokenCacheCredential` and `PowerShellCredential`)
- `get_subscription_id()` — env vars (`AZURE_SUBSCRIPTION_ID`, `BOARD_SUBSCRIPTION_ID`) then `az account show`
- `get_tenant_id()` — from `az account show`
- `list_subscriptions()` — returns `[{name, id, is_default}]`

#### az.py — Safe Azure CLI Runner
- `az_json(*args, timeout=30) → dict|list` — async subprocess, parses JSON output
- `az_text(*args, timeout=30) → str` — async subprocess, returns stripped text
- Raises `BoardError` on timeout or non-zero exit

#### compute.py — VM Operations
- `list_vms(credential, sub_id, rg)` — returns `[{name, vm_size, os, power_state, location}]`
- `get_vm_status(credential, sub_id, rg, vm_name)` — returns power/provisioning state, size, location
- `start_vm()`, `stop_vm()`, `deallocate_vm()` — VM power management
- `delete_vm()` — deletes VM + attached public IPs (reads NIC references, cleans up orphaned PIPs)
- `list_skus(credential, sub_id, location, filter)` — **uses REST API** (not `az vm list-skus` which takes 73+ seconds in `australiaeast`)
- `run_command(credential, sub_id, rg, vm_name, script)` — execute shell script via Azure Run Command API

#### deployment.py — Bicep and ARM Deployment
- `bicep_build(bicep_path)` — compile via `az bicep build --stdout`, returns JSON template
- `deploy(credential, sub_id, rg, template, parameters, deployment_name, on_progress, timeout)` — ARM deployment with progress callback for per-resource status updates
- `ensure_resource_group(credential, sub_id, rg, location, tags)` — create if not exists

#### keyvault.py — Key Vault Operations

State machine handling vault lifecycle:

1. Check if vault exists → return
2. Check for soft-deleted vault → recover it
3. Attempt fresh creation
4. If create fails (conflict) → retry with purge

**Functions:**
- `create_or_recover_vault(credential, sub_id, rg, vault_name, location, tenant_id) → vault_url`
- `get_secret()`, `set_secret()`, `list_secrets()` — CRUD operations
- `ensure_secrets_officer_role()` — assign RBAC role (idempotent)

**Constants:** `_SECRETS_OFFICER_ROLE_ID = "b86a8fe4-44ce-4948-aee5-eccb2c155cd7"`, retry delay 10s, max retries 3

### 4.8 SSH Management

#### keys.py — SSH Key Generation
- `generate_keypair(key_path) → (private_key_str, public_key_str)` — ed25519 keys
  - Primary: asyncssh native crypto
  - Fallback: `ssh-keygen -t ed25519` subprocess
  - Permissions: directory 0o700, private key 0o600, public key 0o644

#### session.py — SSH Session Wrapper

`SSHSession` — async context manager around asyncssh:
- No host-key checking, 10s connect timeout, 60s keepalive
- `connect()`, `run()`, `upload()`, `download()`, `close()`
- Used by provisioning engine, smoke tests, and fleet metrics collection

#### config_file.py — SSH Config Management

Manages marker-delimited blocks in `~/.ssh/config`:

```
# BEGIN board: devvm-jbloggs
Host devvm-jbloggs
    HostName devvm-jbloggs.australiaeast.cloudapp.azure.com
    User devuser
    IdentityFile ~/.ssh/devvm-jbloggs
    ForwardAgent yes
    ServerAliveInterval 60
    ServerAliveCountMax 3
    StrictHostKeyChecking accept-new
# END board: devvm-jbloggs
```

**Functions:**
- `read_managed_block(config_path, alias)` — read existing block
- `write_managed_block(config_path, alias, block)` — insert/replace (idempotent)
- `remove_managed_block(config_path, alias)` — delete block
- `build_ssh_key_config_block(alias, hostname, key_path, username)` — generate Host stanza for SSH key auth
- `build_entra_id_config_block(alias, hostname)` — generate Host stanza for Entra ID auth (certificate-based, with LocalForward for code-server, Cockpit, Portainer)
- `refresh_entra_certs(alias, resource_group, vm_name) → (success, entra_user)` — generate/refresh short-lived Entra ID certificates via `az ssh config`; returns the Entra UPN from the generated config

### 4.9 Bundle (Encryption and Packaging)

#### crypto.py — AES-256-GCM Encryption

| Parameter | Value |
|---|---|
| Algorithm | AES-256-GCM |
| Key derivation | PBKDF2-SHA256 |
| Iterations | 100,000 |
| Salt | 16 bytes (random) |
| IV | 12 bytes (random) |
| Key | 32 bytes (derived) |
| Auth tag | 16 bytes (GCM) |

- `encrypt(payload_json, passphrase) → BundleEnvelope` — encrypt plaintext, return envelope with base64 fields
- `decrypt(envelope, passphrase) → str` — reverse process, raises `InvalidTag` on wrong passphrase

**Cross-language compatibility:** byte-identical output with `extension/src/bundle.ts`. Tested in CI.

#### payload.py — Bundle Payload Assembly
- `build_payload(developer_name, environment, region, ..., ttl_days=730) → BundlePayload`
- Sets `issued_at` (UTC now) and `valid_until` (now + ttl_days) as ISO-8601

#### package.py — ZIP Assembly
- `build_zip(board_pass_path, vsix_path, output_dir, name, ...) → Path`

ZIP structure:
```
{name}-board/
├── {name}.board-pass          # Encrypted JSON (AES-256-GCM)
├── board.vsix                 # VS Code extension (optionally patched with personalised PNG)
├── Setup Board.command        # macOS launcher script
├── Setup Board.cmd            # Windows launcher script
└── Board Quick Start.pdf      # (optional) Quick start guide
```

#### svg.py — Board Pass SVG Rendering
- `render_board_pass_svg(developer_name, environment, region, ...) → str`
- Produces an SVG card with deterministic barcode, initials avatar, region/auth/zone fields, host, issued/expiry dates

### 4.10 Provisioning Engine

#### engine.py — ProvisionEngine (9-Phase System)

Accepts a manifest and SSH runner (protocol for dependency injection), executes project provisioning in nine sequential phases:

| Phase | Name | Action |
|---|---|---|
| 1 | **Validate** | Verify prerequisites (tools exist, repos accessible, cloud-init marker present) |
| 2 | **Clone** | `git clone` repository to `~/projects/{name}` |
| 3 | **Env** | Write `.env` file from keyvault_secrets + hardcoded + fallback |
| 4 | **Install** | Run `install[]` commands (e.g. `uv sync`, `npm install`) |
| 5 | **Docker** | `docker compose up -d`, wait for container health checks |
| 6 | **Post-Docker** | Run `post_docker[]` commands (e.g. database migrations) |
| 7 | **Services** | Generate and install systemd user units, start services |
| 8 | **Workspace** | Generate `.vscode/{tasks,launch,settings}.json` |
| 9 | **Health** | Run health checks, install TTFC (time-to-first-commit) hook |

**TTFC Hook:** A one-time `pre-push` git hook that measures elapsed time from provisioning (`created_at`) to first push (`first_push_at`). Stores `metrics.json` with `time_to_first_commit_minutes`. Self-removes after first execution.

Each phase returns a `PhaseResult` with timing, warnings, and errors. The engine is testable via protocol-based SSH injection (fake SSH runners in tests).

#### orchestrator.py — Multi-Project Provisioning

Runs `ProvisionEngine` for each selected manifest, then generates cross-project artefacts:
1. Discover manifests (`load_all` with optional filter)
2. Provision each project (run `engine.run_all()`)
3. Generate `board.code-workspace` (multi-root workspace with port forwarding)
4. Generate `check` script (consolidated health checks)
5. Copy manifests to `~/projects/.manifests`
6. Print summary (N succeeded, M failed)

#### cloud_init.py — Cloud-Init Wait Logic

Two-phase polling:

**Phase 1 — SSH Connectivity** (10s polling, max 30 min):
- Try hostname first, fallback to IP
- Clear stale `known_hosts` entries before connecting
- Detect DNS propagation delays

**Phase 2 — Cloud-Init Completion** (60s polling):
- Poll `cloud-init status` (done/running/error)
- Check marker file: `/home/{user}/.cloud-init-complete`
- Verify tool availability: `which docker node python3`
- Handle edge cases: stale marker from prior boot, status done but no marker, status error

Returns SSH target (hostname or IP) on success. Raises `SSHError` on timeout or failure.

### 4.11 User Interface

#### console.py — Rich Console Wrapper

**Theme:** ACCENT = `#0ea5e9` (Sky-500)

**Display functions:**
- `header()`, `banner()`, `ascii_banner()` — titles and headers
- `step(current, total, text)` — phase counter `[1/5]`
- `success()`, `error()`, `warn()`, `info()` — status messages with icons
- `summary_box()`, `completion_box()`, `warn_summary()` — bordered panels
- `phase_timing()` — elapsed time display

**Context managers:**
- `spin(message)` — synchronous spinner
- `spin_timed(message)` — async spinner with elapsed timer

**Utilities:**
- `play_sound()` — macOS `afplay` bell notification on completion
- `webhook(url, message)` — POST to webhook URL (e.g. Slack)

#### prompts.py — Questionary Wrappers

All prompts support non-interactive mode (`BOARD_NON_INTERACTIVE=1`):
- `input_text()`, `input_validated()` — text input with optional regex validation
- `choose()` — single-select list
- `checklist()` — multi-select with defaults
- `confirm()` — yes/no
- `secret()` — password input (no echo)

Non-interactive fallback: checks `BOARD_{KEY}` env vars (derived from prompt text), then defaults.

#### boarding_pass.py — Boarding Pass Console Rendering
- `render_boarding_pass()` — Rich panel with initials avatar, deterministic barcode, region/auth/zone fields, host, dates, filename

### 4.12 CLI Commands In Depth

#### `board up` — 5-Phase Provisioning Wizard (`setup.py`)

The main entry point for creating a new board.

**Phase 1 — Configure:**
- Persona selection (setting up for self or another developer)
- Developer name input (validated against `DEV_NAME_PATTERN`)
- Environment discovery (`discover_bicepparams`) or default "personal"
- Project selection (interactive checklist from `projects/` directory)
- Key Vault setup (existing vault, create new, or skip)
- SSH key handling (generate new, use existing, or custom path)
- VM size selection from catalogue:
  - `Standard_D2s_v6`: 2 vCPU, 8 GB RAM (~$55/mo)
  - `Standard_D4s_v6`: 4 vCPU, 16 GB RAM (~$110/mo)
  - `Standard_D8s_v6`: 8 vCPU, 32 GB RAM (~$220/mo)
  - Custom SKU

**Phase 2 — Authenticate:**
- Resolve subscription ID (env var or `az account show`)

**Phase 3 — Review:**
- Summary box: resource group, VM name, projects, Key Vault, estimated cost

**Phase 4 — Provision (Deployment):**
- Create resource group
- Create Key Vault (if selected)
- Compile Bicep template
- Deploy ARM template (with per-resource progress callback)
- Wait for cloud-init (two-phase polling)
- Provision projects (9-phase engine for each manifest)

**Phase 5 — Handoff:**
- Write SSH config block to `~/.ssh/config`
- Display completion box with connection instructions
- Send webhook notification (if `BOARD_WEBHOOK_URL` set)
- Display warning summary (if any issues)
- Offer to create board pass

**Flags:** `--dry-run` (validate only), `--demo` (mock Azure calls), `--non-interactive` (env var driven)

#### `board admin` — Admin Control Panel (`admin.py`)

Interactive menu for day-2 operations:

1. **Manage boards** — Select environment → Select VM → Start/Stop/SSH/Delete
2. **Set up projects** — Select environment → Select VM → Checklist projects → Provision
3. **Create board pass** — Select environment → Select VM → Export encrypted bundle
4. **Manage Key Vault secrets** — Input vault name → List/Set secrets
5. **Run health checks** — Select environment → Select VM → Smoke test

#### `board fleet` — Fleet Dashboard (`fleet.py`)

Concurrent metrics collection from all VMs via SSH:
- TTFC (time-to-first-commit from `~/.board/metrics.json`)
- Health (passed/total from `~/.board/last-check`)
- Issues list
- Rendered as Rich table

#### `board init` — Stack Detection (`init.py`)

Auto-detects language, framework, Docker services, and ports in a project directory:

| Detected | Examples |
|---|---|
| Languages | Python (uv/pipenv/pip), Node (pnpm/yarn/npm), Go, Ruby, Java |
| Frameworks | Django, FastAPI, Flask, Next.js, React, Vue, Express, Rails, Spring Boot |
| Docker | PostgreSQL, Redis, MySQL, MongoDB |
| Ports | Django→8000, Node→3000, Spring Boot→8080 |

Generates a complete `.project.yaml` manifest to stdout.

#### `board export-pass` — Board Pass Creation (`export_pass.py`)

1. Resolve developer name, environment, region
2. Read SSH keys (private + public)
3. Prompt passphrase (min 8 chars, confirmed)
4. Build payload (with issued_at/valid_until timestamps)
5. Encrypt (AES-256-GCM) → BundleEnvelope
6. Write `.board-pass` JSON file
7. Offer to render boarding pass SVG
8. Build ZIP with optional patched VSIX (personalised board pass card PNG)
9. Render boarding pass to console with barcode

#### `board smoke-test` — Deployment Validation (`validate.py`)

SSH-based health verification:

**Tool checks:** git, python3, uv, node, npm, docker, docker compose, az, just, nvim, gh, jq, pnpm, yq

**SSHD settings verified:** `PermitRootLogin=no`, `PasswordAuthentication=no`, `X11Forwarding=no`, `MaxAuthTries=6`

**Cloud-init artefacts:** setup-me.sh, .board/config, /home/devuser ownership, systemd timer

---

## 5. VS Code Extension (TypeScript)

### 5.1 Extension Manifest

| Field | Value |
|---|---|
| **Name** | board |
| **Display Name** | Board |
| **Version** | 0.1.0 |
| **Publisher** | barney-w |
| **VS Code** | ^1.96.0 |
| **License** | Apache-2.0 |
| **Categories** | Other, SCM Providers |
| **Activation** | `onStartupFinished`, `onLanguage:board-pass`, `onCommand:board.importPass`, `onCommand:board.configure` |
| **Extension Kind** | workspace + ui |
| **Bundle** | esbuild → `dist/extension.js` |

### 5.2 Module Reference

| Module | Lines | Purpose |
|---|---|---|
| `extension.ts` | 580 | Entry point, command registration, event wiring |
| `boardPassCard.ts` | 668 | Holographic boarding pass webview (HTML/CSS/JS) |
| `connection.ts` | 281 | 7-step SSH connection orchestration |
| `bundle.ts` | 244 | AES-256-GCM decryption, board pass import workflow |
| `cheatsheet.ts` | 211 | Quick-reference webview (8 sections) |
| `ssh.ts` | 200 | SSH config file management (marker blocks) |
| `boardPassEditor.ts` | 196 | Custom read-only editor for .board-pass files |
| `azure.ts` | 192 | Azure CLI wrapper (never-throws pattern) |
| `welcome.ts` | 185 | First-time onboarding panel |
| `polling.ts` | 184 | VM status monitoring (event-driven) |
| `sidebar.ts` | 267 | Three tree-view providers (status, actions, cheatsheet) |
| `statusBar.ts` | 108 | Status bar widget with health integration |
| `firstRun.ts` | 84 | Post-connect setup detection |
| `config.ts` | 78 | Settings and naming derivation (pure functions) |
| `terminal.ts` | 47 | Terminal profile and workspace terminals |

### 5.3 Commands

| Command | Title | Description |
|---|---|---|
| `board.configure` | Configure Connection (Advanced) | Manual setup for admins |
| `board.connect` | Connect | Open remote VS Code window on VM |
| `board.start` | Start | Start the VM (requires Azure CLI) |
| `board.stop` | Stop | Deallocate the VM |
| `board.importPass` | Import Pass | Decrypt and install a `.board-pass` file |
| `board.runSetup` | Run First-Time Setup | Configure Git + SSH on the VM |
| `board.openPortal` | Open in Azure Portal | Jump to VM in Azure portal |
| `board.openTerminal` | Open Terminal | SSH terminal to VM |
| `board.openCodeServer` | Open code-server | SSH tunnel to code-server |
| `board.openWorkspace` | Open Workspace Terminals | Terminal + Copilot split layout |
| `board.showPass` | Show Pass | Display the Board Pass card for the current configuration |
| `board.openCockpit` | Open Cockpit | SSH tunnel to Cockpit system admin UI (localhost:9091) |
| `board.openPortainer` | Open Portainer | SSH tunnel to Portainer Docker management (localhost:9444) |
| `board.cheatsheet` | Cheatsheet | Full quick-reference webview |

### 5.4 Board Pass Card UI

`boardPassCard.ts` generates a rich webview mimicking a physical boarding pass:

- **Header** — gradient blue bar with shield icon, "BOARD PASS", "ACCESS CREDENTIAL"
- **Identity** — initials avatar SVG, developer name, environment
- **Stamp** — animated "AUTHORIZED" or "REVOKED" stamp (rotated, bounces in)
- **Fields** — 2-column grid: host, zone, auth method, issued date, expiration
- **Clearance chips** — available access methods (SSH Terminal, code-server)
- **Barcode** — deterministic hash-based SVG (60 bars from name)
- **Perforation** — dashed tear line with circular cutout holes
- **Stub** — tear-off section with dev name, region, expiry, zone code
- **Connect Now** button — closes panel, executes `board.connect`

**Visual effects:** 0.6s fade-in, 6s infinite shimmer overlay, stamp bounce at 0.5s offset. Responsive at <460px.

### 5.5 Connection Workflow

`connection.ts` implements a multi-step connection sequence that branches on auth method:

1. **Configuration check** — ensure developer name is set
2. **SSH config** — write/update `~/.ssh/config` (idempotent)
3. **Auth-specific verification:**
   - **SSH key path** (ssh-key auth) — check file exists, restore from SecretStorage if missing, prompt import if not found
   - **Entra ID path** (entra-id auth) — verify Azure CLI installed, check/install `az ssh` extension, refresh short-lived certificates via `az ssh config`, re-write SSH config with Entra username from cert
4. **VM state check** (if Azure CLI available) — check power state, auto-start if stopped, wait up to 2 minutes for "running"
5. **Remote-SSH extension** — check installed, install if missing
6. **Open remote window** — `vscode.openFolder()` with `vscode-remote://ssh-remote+devvm-{name}/home/devuser/projects`

**VM state handling:**
- `running` → proceed immediately
- `stopped/deallocated` → auto-start (if `autoStartVm=true`), wait for running
- `starting` → wait up to 2 minutes
- `deallocating` → suggest retry later
- `unknown` → warn but proceed (SSH may still work)

### 5.6 Polling and Status

#### PollingService (`polling.ts`)

Event-driven VM status monitoring:
- Default interval: 60 seconds (configurable 10–600s via `board.pollIntervalSeconds`)
- Emits `onDidChangeStatus` when power state changes
- Emits `onDidChangeHealth` when health check results change
- Health checks run every 5 minutes (SSH to VM, run `check.sh`, parse results)
- Pauses when window loses focus (battery/bandwidth optimisation)
- Immediate poll on resume

#### StatusBar (`statusBar.ts`)

| State | Display | Click action |
|---|---|---|
| not-configured | `$(remote) Board — Import Pass` | `board.importPass` |
| running | `$(remote) Board ✓` | `board.connect` |
| running + issues | `$(remote) Board ⚠ N issue(s)` | `board.connect` |
| starting | `$(remote) Board ↑ starting...` | (none) |
| stopped/deallocated | `$(remote) Board ↓` | `board.start` |
| deallocating | `$(remote) Board ↓ stopping...` | (none) |
| unknown | `$(remote) Board ?` | `board.connect` |

Tooltip shows developer name, region, power state, and service health lines.

### 5.7 Sidebar and Cheatsheet

Three sidebar tree-view providers under the Board activity bar icon:

**VmStatusProvider** — Live VM state (status, IP, FQDN, size) with dynamic icons (pulse for running, loading-spin for starting, debug-stop for stopped)

**QuickActionsProvider** — Action buttons: Connect, Open Workspace, Open Terminal, Run Setup, Open code-server, Open Portal, Start/Stop (contextual)

**CheatsheetProvider** — Nested tree with collapsible groups: VS Code Commands, Terminal Commands, Key Paths, Tips. Links to full webview cheatsheet.

**Cheatsheet webview** (`cheatsheet.ts`) — 8-section reference: VS Code commands, health/status, git aliases, Docker aliases, systemd services, key paths, access methods, daily workflow, troubleshooting.

---

## 6. Infrastructure (Bicep + Cloud-Init)

### 6.1 Bicep Templates

**`infra/main.bicep`** (303 lines) — orchestrates Azure Verified Modules (AVM):

**Parameters:**
| Parameter | Type | Default | Description |
|---|---|---|---|
| `location` | string | `australiaeast` | Azure region |
| `environment` | string | `personal` | Environment name |
| `regionShort` | string | `aue` | Short region code |
| `developerName` | string | (required) | Developer identifier |
| `vmSku` | string | `Standard_D2s_v6` | VM size |
| `osDiskSizeGb` | int | 128 | OS disk size |
| `sshPublicKey` | string | (required) | SSH public key |
| `adminUsername` | string | `devuser` | VM admin username |
| `enablePublicIp` | bool | true | Attach public IP with DNS |
| `allowedSshSource` | string | `*` | NSG source for SSH rule |
| `enableHttps` | bool | false | Open port 443 |
| `shutdownTime` | string | `1900` | Auto-shutdown (local time) |
| `shutdownEmail` | string | `""` | Notification email |
| `keyVaultName` | string | `""` | Optional Key Vault name |
| `useEntraIdLogin` | bool | `true` | Enable Entra ID (AAD) SSH authentication |
| `entraLoginTenantId` | string | `""` | Tenant ID for AADSSHLogin extension |
| `entraLoginPrincipalId` | string | `""` | Principal ID for VM Login RBAC role |
| `enableAutoStart` | bool | `false` | Enable weekday auto-start schedule |
| `autoStartTime` | string | `"0800"` | Auto-start time (24h format) |
| `autoStartTimezone` | string | `"AUS Eastern Standard Time"` | Timezone for auto-start |

**Resources created:**
- **NSG** — deny-all inbound baseline, allow SSH from `allowedSshSource`, conditional HTTPS
- **VNet** — 10.0.0.0/16 with 10.0.1.0/24 subnet
- **Public IP** — static allocation with DNS label (`devvm-{name}`)
- **VM** — Ubuntu 24.04 LTS, Trusted Launch (Secure Boot + vTPM), system-assigned managed identity, no password auth, custom data = cloud-init YAML
- **Auto-shutdown** — DevTestLab schedule (via module)
- **Key Vault RBAC** — conditional "Key Vault Secrets User" role for VM managed identity (via module)

**Outputs:** `vmName`, `publicIpAddress`, `fqdn`, `sshCommand`

**`infra/modules/auto-shutdown.bicep`** — creates `Microsoft.DevTestLab/schedules` resource for daily VM shutdown with optional email notification.

**`infra/modules/keyvault-role.bicep`** — assigns "Key Vault Secrets User" role (GUID: `4633458b-17de-408a-b874-0445c86b69e6`) to the VM's system-assigned managed identity.

**`infra/modules/vm-login-roles.bicep`** — assigns "Virtual Machine Administrator Login" role (GUID: `1c0163c0-47e6-4577-8991-ea5c82e286e4`) to a specified Entra ID principal, scoped to the VM. Used for Entra ID SSH authentication.

**`infra/modules/auto-start.bicep`** — Logic App-based weekday auto-start schedule. Creates a weekly recurrence trigger, grants "Virtual Machine Contributor" to the Logic App's managed identity, and calls the VM start API.

**`infra/bicepconfig.json`** — analyser rules: error on unused params/vars, no hardcoded URLs, no secrets in outputs; warning on literal admin usernames, old API versions.

### 6.2 Cloud-Init

**`infra/cloud-init/cloud-init.yaml`** (725 lines) — runs on first VM boot, takes ~8 minutes.

**1. System packages** (22 packages):
`build-essential`, `curl`, `wget`, `git`, `unzip`, `neovim`, `nano`, `jq`, `htop`, `tree`, `tmux`, `ca-certificates`, `gpg`, `lsb-release`, `apt-transport-https`, and more.

**2. Docker:**
- Official Docker repo with signed GPG key
- `devuser` added to docker group
- BuildKit enabled by default

**3. Language runtimes:**
- **Node.js 20** via nodesource repository
- **pnpm 10.33.0** via corepack
- **Python 3.12** from deadsnakes PPA + venv + dev headers
- **uv** (astral.sh) installed globally

**4. Developer tools:**
- Azure CLI (`aka.ms/InstallAzureCLIDeb`)
- GitHub CLI (with GPG verification)
- GitHub Copilot CLI (`gh extension install github/gh-copilot`)
- `just` (task runner)
- `yq` (YAML parser)
- code-server v4.96.4 (browser IDE on localhost:8080)
- VS Code CLI (tunnel support)

**5. SSH hardening:**
```
PermitRootLogin no
PasswordAuthentication no
X11Forwarding no
MaxAuthTries 6
ClientAliveInterval 300
ClientAliveCountMax 2
```

**6. Files written to disk:**

**`setup-me.sh`** (~230 lines) — interactive first-run script:
- Git identity configuration (name, email)
- SSH key generation (ed25519)
- GitHub authentication (for Copilot)
- Tool verification (14 tools)
- Docker sudo-free verification
- Workspace orientation
- Signals completion: `~/.setup-me-complete`

**Dynamic MOTD** (`/etc/update-motd.d/50-board`):
- Renders on SSH login in <500ms
- Shows Board name, region, VM size, health summary, disk usage, uptime, command hints

**Health check components:**
- `~/.board/is-idle.sh` — idle detection (SSH sessions, code-server, tunnels)
- `~/.board/config` — board metadata (name, region, size)
- `board-check.service` + `board-check.timer` — periodic health check (every 10 minutes)

**7. Bash profile** (`~/.bashrc`):
- Custom prompt with git branch: `user@host:path (branch)$`
- Aliases: `gs`=git status, `gd`=git diff, `gl`=git log, `dc`=docker compose, `k`=kubectl
- Windows-familiar aliases: `cls`, `dir`, `copy`, `move`
- `board-help` function — quick reference for common commands
- `check` alias → runs `~/projects/.board/check.sh`
- Auto-cd to `~/projects` on login

**8. Sample project** — `hello-board` Python/FastAPI project:
- `main.py` — FastAPI app with `/` and `/health` endpoints
- `docker-compose.yml` with live reload
- Dockerfile (python:3.12-slim)
- VS Code devcontainer config

**9. Systemd services:**
- `code-server@devuser` — auto-started on localhost:8080
- Linger enabled (services persist after logout)

**10. Completion signal:**
- `touch ~/.cloud-init-complete` — marker for provisioning engine to detect readiness

### 6.3 Auto-Shutdown

VMs auto-shutdown at 7 PM daily via DevTestLab schedule. Configurable via `shutdownTime` parameter. Optional email notification. Developer work persists — files, Docker volumes, and git state survive shutdown.

### 6.4 Key Vault Integration

When a Key Vault name is provided to the deployment:
1. VM's system-assigned managed identity gets "Key Vault Secrets User" role
2. During project provisioning, secrets are fetched from Key Vault via `keyvault_secrets` in manifests
3. Secrets are written to `.env` files on the VM
4. Secrets never appear in manifests, logs, or git

---

## 7. Project Manifest System

### 7.1 Schema Reference

A `.project.yaml` manifest declares everything needed to provision a project on a board:

```yaml
# ── Identity ──
name: string                    # Required. Project identifier
description: string             # Optional. Human-readable description
repo: string                    # Required. Git clone URL
path: string                    # Default: ~/projects/{name}

# ── Prerequisites ──
requires:
  tools: [string]               # System tools that must exist
  cloud_init: bool              # Wait for cloud-init before provisioning

# ── Dependency installation ──
install:                        # Idempotent commands, run in order
  - label: string
    run: string

# ── Docker services ──
docker:
  compose_file: string          # Relative to project path
  containers:
    - name: string
      restart_policy: string    # Default: unless-stopped
      health_cmd: string        # Docker health check command
      health_interval: int      # Seconds between health checks
      health_timeout: int       # Max seconds to wait for healthy

# ── Post-Docker setup ──
post_docker:                    # Run after containers are healthy
  - label: string
    run: string

# ── Application services (systemd) ──
services:
  - name: string                # Unit name: board-{name}.service
    description: string
    exec: string                # ExecStart command
    working_dir: string         # Relative to project path
    env_file: string            # Relative to project path
    extra_path: string          # Prepended to PATH
    health_url: string          # HTTP endpoint to verify
    health_timeout: int         # Max seconds to wait

# ── Environment variables ──
env:
  file: string                  # Target .env file
  fallback: string              # Copy if no Key Vault available
  keyvault_secrets:             # {ENV_VAR: secret-name}
    ANTHROPIC_API_KEY: anthropic-api-key
  hardcoded:                    # Always the same for local dev
    DATABASE_URL: postgresql://...
  required: [string]            # Warn loudly if missing

# ── VS Code integration ──
vscode:
  ports:                        # Port forwarding config
    "8090": { label: string, auto_forward: notify|silent|ignore }
  tasks:                        # tasks.json entries
    - label: string
      command: string
      group: string
      background: bool
  launch:                       # launch.json entries
    - name: string
      type: string              # debugpy, delve, ruby-debug, etc.
      request: string           # launch|attach
      module: string
      args: [string]
      cwd: string
      env_file: string
      pre_launch_task: string
  settings: {}                  # settings.json overrides

# ── Workspace panes ──
workspace:
  services:
    - name: string
      command: string           # Terminal command for pane

# ── Health checks ──
health:
  - label: string               # Display name
    check: string               # Shell command (exit 0 = healthy)
    port: int                   # Optional, for display
    hint: string                # Optional fix suggestion
```

### 7.2 Output Artefacts

A single manifest generates:

| Artefact | Location | Purpose |
|---|---|---|
| Systemd user unit | `~/.config/systemd/user/board-{name}.service` | Long-running application service |
| tasks.json | `~/projects/{name}/.vscode/tasks.json` | VS Code task definitions |
| launch.json | `~/projects/{name}/.vscode/launch.json` | VS Code debug configurations |
| settings.json | `~/projects/{name}/.vscode/settings.json` | VS Code workspace settings |
| .env | `~/projects/{name}/.env` | Environment variables (with Key Vault secrets) |
| check.sh | `~/projects/.board/check.sh` | Consolidated health check script |
| board.code-workspace | `~/projects/board.code-workspace` | Multi-root workspace with port forwarding |

### 7.3 Bundled Manifests

**`surf.project.yaml`** — AI platform (Python/FastAPI + Postgres):
- Repo: github.com/barney-w/surf
- Tools: python3, uv, docker
- Docker: surf-postgres (pg_isready health check)
- Service: surf-api on port 8090 (uvicorn)
- Post-Docker: Alembic migrations
- Key Vault secrets: ANTHROPIC_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_SEARCH_ENDPOINT, AZURE_STORAGE_ACCOUNT_URL
- VS Code: 6 tasks, debugpy launch config, port forwarding (8090, 5432)
- Health: Postgres, API, Alembic

**`surf-kit.project.yaml`** — React component library:
- Repo: github.com/barney-w/surf-kit
- Tools: node, pnpm
- Install: pnpm install, pnpm build
- No Docker
- VS Code: 4 tasks, port 5173
- Health: Dependencies installed, build artefacts exist

### 7.4 Example Manifests

| Manifest | Stack | Docker | Services | Health Checks |
|---|---|---|---|---|
| `django-api.project.yaml` | Python/Django | Postgres + Redis | django-api, celery worker, celery-beat | 5 (Postgres, Redis, API, Celery, Migrations) |
| `go-api.project.yaml` | Go 1.22 | Postgres | go-api-http (8080 + gRPC 50051) | 4 (HTTP, gRPC, Postgres, Migrations) |
| `rails-app.project.yaml` | Ruby/Rails | Postgres + Redis | rails-server, rails-sidekiq | 5 (Postgres, Redis, Rails, Sidekiq, Migrations) |
| `spring-boot.project.yaml` | Java 21/Spring Boot | Postgres | spring-boot-api (8080) | 3 (Postgres, Actuator, Flyway) |

### 7.5 Auto-Detection

`board init` scans a project directory and generates a manifest:

**Detection targets:**
- **Languages:** Python (pyproject.toml/Pipfile/requirements.txt → uv/pipenv/pip), Node (pnpm-lock/yarn.lock/package-lock → pnpm/yarn/npm), Go (go.mod), Ruby (Gemfile), Java (build.gradle/pom.xml → gradle/maven)
- **Frameworks:** Django, FastAPI, Flask, Next.js, React, Vue, Express, Rails, Spring Boot
- **Docker services:** PostgreSQL, Redis, MySQL, MongoDB (from docker-compose.yml)
- **Port inference:** Django/FastAPI/Flask→8000, Node frameworks→3000, Spring Boot→8080, Go→8080, Rails→3000

---

## 8. Justfile Recipes

The `justfile` contains 50+ recipes organised into categories. All invoke the Python CLI via `uv run --project cli board`.

**Defaults:**
```
default_env      = "personal"
default_sku      = "Standard_D2s_v6"
default_location = "australiaeast"
default_region   = "aue"
```

| Category | Recipes |
|---|---|
| **Interactive Setup** | `board`, `demo`, `admin` |
| **Deployment** | `create-vm`, `create-rg`, `validate`, `what-if` |
| **VM Operations** | `start`, `stop`, `ssh`, `status`, `list` |
| **Access Control** | `grant-access` (admin/developer/viewer roles) |
| **Teardown** | `delete-vm`, `destroy-all` |
| **SSH Config** | `ssh-config`, `ssh-config-write`, `ssh-config-remove` (all auto-detect auth method) |
| **Board Passes** | `export-pass`, `export-ssh-pass` |
| **Utilities** | `generate-key`, `smoke-test`, `cloud-init-status` |
| **Browser Tools** | `cockpit`, `portainer`, `code-server` (auth-aware SSH tunnels) |
| **VS Code Tunnel** | `tunnel-setup`, `tunnel-web`, `browser-ide` |
| **Governance** | `policies`, `costs`, `costs-dev` |
| **Project Operations** | `install-projects`, `project-status`, `fleet-status`, `init` |
| **Automation** | `wait-ready`, `preflight`, `provision`, `rotate-key`, `build-extension` |
| **Static Analysis** | `lint-python`, `format-python`, `lint-bicep`, `lint-cloud-init`, `lint-manifests`, `check` |
| **Testing** | `test`, `test-cov`, `dry-run`, `test-cloud-init` |

**Notable recipes:**

- `just board` — runs the full interactive wizard
- `just admin` — admin control panel
- `just export-pass jbloggs` — creates encrypted starter kit
- `just grant-access jbloggs jane@contoso.com role=admin` — grant Entra ID access with role
- `just costs` — cost breakdown by developer
- `just policies` — show policy enforcement rules
- `just provision name` — non-interactive full provision (`BOARD_NON_INTERACTIVE=1`)
- `just test-cloud-init` — launches Ubuntu 24.04 in Multipass, applies cloud-init, verifies tools
- `just dry-run testuser` — validates setup inputs without Azure calls

---

## 9. CI/CD and Release

### 9.1 CI Pipeline

**Trigger:** Push/PR to `main`

**6 parallel jobs:**

| Job | Runner | Steps |
|---|---|---|
| **static-analysis** | ubuntu-latest | Install yq, validate all `.project.yaml` manifests |
| **validate-bicep** | ubuntu-latest | Install Bicep CLI, `bicep build` + `bicep lint` |
| **python-lint** | ubuntu-latest | `uv sync`, `ruff check`, `ruff format --check`, `mypy src/` |
| **python-test** | ubuntu-latest | `uv sync`, `pytest tests/unit/ --cov=board --cov-report=term-missing` |
| **crypto-compat** | ubuntu-latest | Build extension (npm ci + build:prod), install Python deps, run `test_crypto_compat.py` |
| **build-extension** | ubuntu-latest | `npm ci`, `npm run build:prod`, `npm test` |

### 9.2 Release Pipeline

**Trigger:** Git tag `v*`

Steps:
1. Checkout code
2. Setup Node.js 20
3. `npm ci` + `npm run build` in extension/
4. Package VSIX (`npx @vscode/vsce package --out board.vsix`)
5. Create GitHub Release (auto-generated notes + VSIX artefact)

### 9.3 Docs Deployment

**Trigger:** Changes to `docs/site/**`

Steps:
1. Check if GitHub Pages enabled
2. Build Astro site
3. Upload to GitHub Pages

### 9.4 VHS Recording

Records terminal GIFs from `.tape` files using VHS (charm.sh). Creates PR if GIFs changed. Used for animated documentation in README.

---

## 10. Documentation Site

Built with **Astro 5.18 + Starlight 0.37** (static site generator for technical documentation).

**Dependencies:** sharp (image optimisation), asciinema-player (terminal recordings)

**Content structure:**
```
docs/site/src/content/
├── docs/
│   ├── getting-started/
│   │   ├── quickstart.md        Prerequisites, provision, export pass, developer connects
│   │   ├── for-developers.md    Connect, first-time setup, daily workflow, auto-shutdown
│   │   └── for-admins.md        Provision boards, admin menu, fleet operations, manifests
│   └── reference/
│       ├── architecture.md      4-layer stack, 9-phase pipeline, security model
│       └── manifest-schema.md   Complete YAML schema with examples
└── (blog posts planned)
```

**Hosted at:** `https://barney-w.github.io/board/`

---

## 11. Testing

### 11.1 Python Test Suite

**Location:** `cli/tests/`
**Runner:** pytest + pytest-asyncio
**Coverage:** pytest-cov

| Test File | Focus | Key Tests |
|---|---|---|
| `test_az.py` | Azure CLI runner | Async subprocess, JSON parsing, timeout handling |
| `test_azure.py` | Azure SDK wrappers | Auth, compute, deployment, Key Vault (mocked SDK clients) |
| `test_cli.py` | CLI command parsing | Command registration, argument parsing, subcommands |
| `test_config.py` | Naming conventions | All derivation functions, env var resolution |
| `test_crypto.py` | AES-256-GCM | Round-trip encrypt/decrypt, wrong passphrase rejection |
| `test_manifest.py` | YAML loading + generation | Manifest parsing, systemd units, VS Code configs, workspace, check script |
| `test_models.py` | Pydantic validation | Model instantiation, serialisation, field aliases |
| `test_provision.py` | 9-phase engine | Fake SSH runner, phase results, error handling |
| `test_ssh_config.py` | SSH config management | Read/write/remove blocks, idempotency, marker preservation |
| `test_ui.py` | Console + prompts | Rich output, non-interactive mode, prompt fallbacks |

**Integration tests:**
- `test_shape_e2e.py` — end-to-end provisioning flow (file retains legacy name)
- `test_crypto_compat.py` — cross-language crypto compatibility (Python ↔ TypeScript)

**Fixtures:** `conftest.py` with mocked Azure credentials, SDK clients, SSH sessions.

### 11.2 Extension Test Suite

**Location:** `extension/test/`
**Runner:** Vitest
**Mock:** `test/__mocks__/vscode.ts` (minimal VS Code API stubs)

| Test File | Tests | Focus |
|---|---|---|
| `bundle.test.ts` | 4 | Round-trip encrypt/decrypt, wrong passphrase, envelope structure, payload equality |
| `config.test.ts` | 8 | All derivation functions (host alias, hostname, RG, VM name, SSH key path, portal URL) |
| `ssh.test.ts` | 7 | SSH key block, Entra ID block, managed block append/replace/preservation |

### 11.3 Cross-Language Crypto Compatibility

The `crypto-compat` CI job verifies that:
1. Python can decrypt what TypeScript encrypts
2. TypeScript can decrypt what Python encrypts
3. Envelope format (base64 fields, JSON structure) is identical
4. Key derivation (PBKDF2-SHA256, 100K iterations) produces identical keys from identical input

This is critical because the CLI creates board passes (Python) and the extension imports them (TypeScript).

---

## 12. Cross-Component Contracts

Board spans Python (CLI) and TypeScript (extension). These shared contracts are enforced by tests:

| Contract | Python | TypeScript | Test |
|---|---|---|---|
| **Naming conventions** | `core/config.py` | `src/config.ts` | `test_config.py`, `config.test.ts` |
| **Encryption format** | `bundle/crypto.py` | `src/bundle.ts` | `test_crypto_compat.py` (CI) |
| **Bundle payload fields** | `models/bundle.py` (camelCase aliases) | `src/bundle.ts` (native camelCase) | `test_crypto_compat.py` |
| **SSH config markers** | `ssh/config_file.py` (`# BEGIN/END board:`) | `src/ssh.ts` (same markers) | `test_ssh_config.py`, `ssh.test.ts` |
| **Developer name pattern** | `DEV_NAME_PATTERN = "^[a-z][a-z0-9]{0,11}$"` | `validateDeveloperName()` | Both test suites |

**Key naming derivations (must be identical):**
```
devvm-{name}                                         SSH host alias
devvm-{name}.{region}.cloudapp.azure.com             FQDN
rg-{env}-{regionShort}-devvm                         Resource group
vm-{env}-{regionShort}-devvm-{name}                  VM name
~/.ssh/devvm-{name}                                  SSH key path
https://vscode.dev/tunnel/devvm-{name}               Tunnel URL
```

---

## 13. Developer Setup

**Prerequisites:**
1. **Azure CLI** — `brew install azure-cli`, then `az login`
2. **just** — `brew install just`
3. **uv** — `curl -LsSf https://astral.sh/uv/install.sh | sh` or `brew install uv`
4. **Node.js 20+** — `brew install node@20` or nvm

**Python CLI:**
```bash
cd cli
uv sync --all-extras     # Install with dev dependencies
uv run board --help      # Verify CLI
uv run pytest            # Run tests
uv run ruff check        # Lint
uv run ruff format       # Format
uv run mypy src/         # Type check
```

**VS Code Extension:**
```bash
cd extension
npm ci                   # Install dependencies
npm run build            # Build (esbuild)
npm test                 # Run tests (Vitest)
npm run lint             # ESLint
```

**Documentation site:**
```bash
cd docs/site
npm install
npm run dev              # Dev server at localhost:4321
```

**Code style:**
- Python: `ruff check`, `ruff format --check`, `mypy --strict`. Target Python 3.12+.
- Shell: `shellcheck` with zero warnings. `#!/usr/bin/env bash` and `set -euo pipefail`.
- TypeScript: Prettier + ESLint. `npm run lint && npm run format`.
- Commits: Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`)

---

## 14. Workflows

### 14.1 Admin: Provision a Board

```bash
git clone https://github.com/barney-w/board.git && cd board
just board
```

The 5-phase interactive wizard:
1. **Configure** — developer name, environment, projects, Key Vault, SSH key, VM size
2. **Authenticate** — resolve Azure subscription
3. **Review** — summary with estimated cost
4. **Provision** — Bicep deploy, cloud-init wait (~8 min), project provisioning
5. **Handoff** — SSH config, connection instructions, optional board pass

Total time: ~11 minutes for a fresh board.

### 14.2 Admin: Export a Board Pass

```bash
just export-pass jbloggs
```

Creates an encrypted starter kit ZIP containing:
- `.board-pass` file (AES-256-GCM encrypted JSON with SSH keys, connection details)
- `board.vsix` (VS Code extension, optionally with personalised board pass card PNG)
- `Setup Board.command` (macOS) / `Setup Board.cmd` (Windows)
- Quick Start PDF (optional)

Share the ZIP by email/file transfer. Share the passphrase by a separate channel (in person, SMS, different messaging app). Two-channel delivery means the ZIP is useless without the passphrase and vice versa.

### 14.3 Developer: Get Connected

1. Unzip the folder
2. Double-click "Setup Board" (.command on Mac, .cmd on Windows)
3. VS Code opens → extension installs → asks for passphrase
4. Board Pass card appears → click "Connect Now"
5. VS Code opens a remote window on the cloud VM
6. First connect: prompted to run `setup-me.sh` (Git identity + SSH key)
7. Projects at `~/projects/` with everything running

**Daily workflow:**
- Morning: Click "Board: Connect" (or status bar item). VM auto-starts if stopped.
- During day: Code normally. Run `check` if something feels off.
- Evening: VMs auto-shutdown at 7 PM. Files persist.

### 14.4 Admin: Fleet Management

```bash
just admin                # Interactive admin menu
just fleet-status         # Fleet dashboard with metrics
just list                 # List all VMs
just smoke-test jbloggs   # Health checks on a specific board
```

The admin menu (`board admin`) provides:
- Fleet overview with running/stopped status
- Start/stop/SSH/delete individual VMs
- Project provisioning on existing VMs
- Board pass creation
- Key Vault secret management
- Remote health checks

---

## 15. Technology Stack Summary

| Layer | Technology | Version | Purpose |
|---|---|---|---|
| **Language (CLI)** | Python | 3.12+ | CLI, provisioning, encryption |
| **Language (Extension)** | TypeScript | 5.9 | VS Code extension |
| **CLI Framework** | typer | 0.15+ | Command-line interface |
| **Terminal UI** | Rich | 14.0+ | Panels, tables, spinners, theming |
| **Interactive Prompts** | questionary | 2.1+ | Input, select, checklist, confirm |
| **Data Validation** | Pydantic | 2.10+ | Manifest and payload models |
| **YAML Parsing** | ruamel.yaml | 0.18+ | Round-trip YAML processing |
| **SSH** | asyncssh | 2.22+ | Async SSH sessions, key generation |
| **Encryption** | cryptography | 44.0+ | AES-256-GCM, PBKDF2-SHA256 |
| **Azure SDK** | azure-identity, azure-mgmt-* | Latest | Authentication, compute, deployment, Key Vault |
| **HTTP** | aiohttp | 3.13+ | Webhooks, REST API calls |
| **Bundler** | esbuild | 0.27+ | Extension bundling |
| **Test (Python)** | pytest + pytest-asyncio | Latest | Unit and integration tests |
| **Test (TS)** | Vitest | 4.0+ | Extension unit tests |
| **Lint (Python)** | ruff | Latest | Linting and formatting |
| **Type Check** | mypy | Latest | Static type analysis |
| **Build (Python)** | Hatchling | Latest | Package build system |
| **Package Manager** | uv | Latest | Fast Python dependency management |
| **Infrastructure** | Bicep / ARM | Latest | Azure resource deployment |
| **VM Image** | Ubuntu 24.04 LTS | Latest | Base OS |
| **First-Boot** | cloud-init | Latest | OS-level provisioning |
| **Container Runtime** | Docker + Compose | Latest | Infrastructure services |
| **Service Manager** | systemd (user units) | Latest | Application service lifecycle |
| **Task Runner** | just | Latest | Project-level command orchestration |
| **IDE** | VS Code + Remote-SSH | 1.96+ | Developer interface |
| **Docs** | Astro + Starlight | 5.18 / 0.37 | Documentation site |
| **CI/CD** | GitHub Actions | Latest | Validation, testing, release |
| **Secrets** | Azure Key Vault | Latest | Credential management |
| **Hosting** | GitHub Pages | Latest | Documentation hosting |

---

*This document was generated from a complete analysis of the Board repository as of 2026-03-30. It covers every component, module, configuration file, and workflow in the project.*
