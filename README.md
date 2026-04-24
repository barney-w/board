<!-- Animated hero banner with dark/light mode -->
<p align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme-hero-dark.svg">
  <img src="docs/assets/readme-hero.svg" alt="Board — dev environments that just work" width="680">
</picture>
</p>

<table align="center"><tr><td width="680" align="center">

<h2><em>Get on Board. Get to work.</em></h2>

<a href="https://github.com/barney-w/board/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/barney-w/board/ci.yml?label=CI&style=flat-square" alt="CI"></a>
<a href="https://github.com/barney-w/board/releases/latest"><img src="https://img.shields.io/github/v/release/barney-w/board?include_prereleases&style=flat-square" alt="Release"></a>
<a href="LICENSE"><img src="https://img.shields.io/github/license/barney-w/board?style=flat-square" alt="License"></a>

</td></tr></table>

<p align="center">
  <a href="#get-connected">Get Connected</a> &middot;
  <a href="#what-you-get">What you get</a> &middot;
  <a href="#for-admins">For Admins</a> &middot;
  <a href="#demos">Demos</a> &middot;
  <a href="https://barney-w.github.io/board/">Docs</a> &middot;
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

---

## Get Connected

You've been given a zip file and a passphrase. Here's what happens next.

<table>
<tr><td width="40" align="center"><strong>1</strong></td>
<td><strong>Double-click "Setup Board"</strong> — Unzip the folder. Double-click <code>Setup Board</code> (<code>.command</code> on Mac, <code>.cmd</code> on Windows). It installs the VS Code extension and opens your board pass. That's it — no terminal, no commands.</td></tr>
<tr><td width="40" align="center"><strong>2</strong></td>
<td><strong>Enter your passphrase</strong> — VS Code asks for the passphrase your admin gave you. This decrypts your connection details and configures everything automatically. (For Entra ID boards, ensure <a href="https://aka.ms/installazurecli">Azure CLI</a> is installed and run <code>az login</code> first.)</td></tr>
<tr><td width="40" align="center"><strong>3</strong></td>
<td><strong>Click Connect</strong> — Your Board Pass card appears. Click <strong>Connect Now</strong> and you're coding on your cloud VM. VS Code opens a remote window — the file explorer, terminal, and extensions all run on the VM.</td></tr>
</table>

On first connect you'll be prompted to run a short first-time setup (your name for Git + an SSH key). After that, your projects are at `~/projects/` with everything already running — databases, APIs, the lot.

<p align="center"><sub><strong>YOUR BOARD PASS</strong></sub></p>
<p align="center">
  <img src="docs/assets/board-pass-card.svg" alt="Board Pass card — access credential with holographic design, showing developer identity, region, clearance, and connect button" width="680">
</p>

### The starter kit

Your admin gives you a single zip file containing everything you need:

<p align="center">
  <img src="docs/assets/starter-kit.svg" alt="Starter kit contents — board.vsix, .board-pass, Setup Board script, Quick Start PDF" width="680">
</p>

The passphrase comes separately (in person, by text, however your team shares secrets). Two-channel delivery means the zip file is useless without the passphrase and vice versa.

---

## What you get

Once connected, VS Code is running on a full Linux VM in the cloud. Everything is already configured:

|                             |                                                                         |
| --------------------------- | ----------------------------------------------------------------------- |
| **Everything running**      | Databases, APIs, services — started on boot, healthy before you arrive. |
| **Full VM power**           | Systemd, native Docker, persistent disk. Real Linux, not a container.   |
| **Health checks**           | Type `check` in the terminal — green lights for every service.          |
| **VS Code integration**     | Tasks, launch configs, port forwarding, status bar — all generated.     |
| **Consistent environments** | Same manifest, same VM, same tools. No drift between developers.        |
| **Auto-shutdown**           | VMs stop at 7 PM to save costs. Your work persists.                     |

<p align="center"><sub><strong>VS CODE EXTENSION</strong></sub></p>
<p align="center">
  <img src="docs/assets/vscode-extension.svg" alt="Board VS Code Extension — Import Pass, Connect, Health Check" width="680">
</p>

### Access methods

| Method                | Client                    | Extensions                 | Auth              |
| --------------------- | ------------------------- | -------------------------- | ----------------- |
| VS Code Desktop + SSH | VS Code + Board Extension | Full Microsoft Marketplace | Entra ID or SSH key |
| code-server           | Any modern browser        | Open VSX                   | Password          |

### Commands you'll use

```
check                    Verify all services are healthy
Board: Connect           Open a remote VS Code window (Cmd+Shift+P)
Board: Start / Stop      Power-manage your VM from VS Code
Board: Show Pass         View your Board Pass card
Board: Open Cockpit      System monitoring dashboard (localhost:9091)
Board: Open Portainer    Docker management UI (localhost:9444)
Board: Open code-server  Open code-server in your browser
```

---

## For Admins

This is the other side of the story — what happens before the developer receives their zip file.

<p align="center"><sub><strong>WHAT YOU RUN</strong></sub></p>
<p align="center">
  <img src="docs/assets/typing-demo.svg" alt="Board workflow — board, export-pass, check" width="680">
</p>

### Create a board

```bash
git clone https://github.com/barney-w/board.git && cd board
just board                # interactive wizard — provisions a VM in ~11 min
```

The wizard walks you through developer name, environment, project selection, VM size, and SSH key generation. Behind the scenes it deploys Azure infrastructure (Bicep + cloud-init), clones project repos, starts Docker services, and runs database migrations.

### Export a board pass

```bash
just export-pass jbloggs   # encrypted credential bundle + starter kit zip
```

This creates the zip file containing the VS Code extension, encrypted board pass, setup scripts, and Quick Start PDF. Share the zip by email or file transfer; share the passphrase by a separate channel.

### Manage the fleet

```bash
just admin              # Admin menu (fleet status, manage boards, secrets)
just fleet-status       # Fleet overview with metrics
just list               # List all VMs
just smoke-test NAME    # Run health checks on a deployed board
```

See the [Admin Guide](https://barney-w.github.io/board/getting-started/for-admins/) for the full admin workflow.

<details>
<summary>📋 <strong>Project manifests</strong> — define a project in one YAML file</summary>

Each project on a board is defined by a single `.project.yaml` manifest. It declares everything the provisioning engine needs — tools, Docker services, environment variables, health checks, and VS Code config.

```yaml
name: nextjs-app
repo: https://github.com/your-org/nextjs-app
requires:
  tools: [node, pnpm, docker]

docker:
  compose_file: docker-compose.yml
  containers:
    - name: nextjs-postgres
      health_cmd: pg_isready -U nextjs

services:
  - name: nextjs-dev
    exec: next dev --port 3000
    health_url: http://localhost:3000/api/health

env:
  keyvault_secrets:
    NEXTAUTH_SECRET: nextauth-secret
  hardcoded:
    DATABASE_URL: postgresql://nextjs:localdev@localhost:5432/nextjs

health:
  - label: Postgres
    check: docker exec nextjs-postgres pg_isready
    port: 5432
  - label: Next.js App
    check: curl -sf http://localhost:3000/api/health
    port: 3000
```

**More examples:** [Django](projects/examples/django-api.project.yaml) · [Go](projects/examples/go-api.project.yaml) · [Next.js](projects/examples/nextjs-app.project.yaml) · [Rails](projects/examples/rails-app.project.yaml) · [Spring Boot](projects/examples/spring-boot.project.yaml)

</details>

---

## Demos

<p align="center">
  <img src="docs/vhs/output/board.gif" alt="just board — interactive setup wizard provisioning a cloud dev environment" width="680">
</p>

<details>
<summary><code>just export-pass jbloggs</code> — create starter kit</summary>

```
╔════════════════════════════════════════════════════════════════╗
║                                                                ║
║  ◆  B O A R D   P A S S                                       ║
║  ACCESS CREDENTIAL                                             ║
║                                                                ║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║  [JB]  jbloggs                                                 ║
║        personal environment                                    ║
║                                                                ║
║  REGION              AUTH METHOD           ZONE                ║
║  australiaeast       ssh-key               AUE                 ║
║                                                                ║
║  HOST                                                          ║
║  devvm-jbloggs.australiaeast.cloudapp.az...                    ║
║                                                                ║
║  · · · · · · · · · · · · · · · · · · · · · · · · · ·           ║
║                                                                ║
║  ISSUED              EXPIRES               FILE                ║
║  2026-03-29          2026-04-28            jbloggs-board.zip   ║
║                                                                ║
║  ┃│║│┃│┃┃│║│┃│┃┃│║│┃│┃┃│║│┃│┃┃│║│┃│┃┃│║│┃│┃                    ║
║  jbloggs-board.zip                                             ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
```

</details>

<details>
<summary><code>check</code> — verify environment health</summary>

```
  Board Check — board-jbloggs-dev
  ============================

  System
  +-- Docker daemon           ok
  +-- cloud-init              ok
  +-- Disk usage (38%)        ok
  +-- SSH agent               ok

  django-api
  +-- Postgres                ok   :5432
  +-- Django API              ok   :8000
  +-- Migrations              ok
  +-- Service: django-api     active (running)

  nextjs-app
  +-- Dependencies            ok
  +-- Build                   ok

  ----------------------------------------
  All checks passed (9/9)
```

</details>

<details>
<summary><code>just admin</code> — admin fleet management</summary>

```
  Board Admin
  ============

  Fleet Status
  ------------
  * jbloggs-dev    running   3h 12m   django-api, nextjs-app
  * asingh-dev   running   1h 45m   django-api
  o cjones-staging stopped   2d ago   django-api

  2 running  /  1 stopped  /  3 total

  Actions
  -------
  [1] Connect to VM         ssh into a running VM
  [2] Start / Stop VM       power on or deallocate
  [3] Reprovision VM        re-run provisioning scripts
  [4] Export pass            create shareable credentials
  [5] Rotate secrets         refresh Key Vault secrets
  [6] Destroy VM             permanently delete a VM
  [7] View logs              tail provisioning logs
  [q] Quit
```

</details>

---

## How it works

```mermaid
flowchart LR
    subgraph Admin
        A[just board] -->|Bicep + cloud-init| B[Azure VM]
        B -->|just export-pass| C[Starter Kit .zip]
    end
    subgraph Developer
        C -->|double-click Setup Board| D[VS Code Extension]
        D -->|click Connect| E[Coding on the VM]
    end

    style A fill:#e2e8f0,stroke:#64748b,color:#1e293b
    style B fill:#e2e8f0,stroke:#64748b,color:#1e293b
    style C fill:#e2e8f0,stroke:#64748b,color:#1e293b
    style D fill:#e2e8f0,stroke:#64748b,color:#1e293b
    style E fill:#e2e8f0,stroke:#64748b,color:#1e293b
```

The Board CLI (`cli/`) is a Python package that orchestrates provisioning. It reads `.project.yaml` manifests, deploys infrastructure via Bicep, provisions projects over SSH, and generates encrypted board passes. The VS Code extension handles the developer side — importing passes, connecting, and monitoring.

| Component               | Role                                                                 |
| ----------------------- | -------------------------------------------------------------------- |
| **Board CLI** (Python)  | Provisioning, fleet management, board pass creation, stack detection |
| **Bicep**               | Azure infrastructure — VM, networking, Key Vault, auto-shutdown      |
| **cloud-init**          | OS-level setup — packages, Docker, dev tools, user accounts          |
| **Provisioning engine** | Project-level setup — git clone, dependencies, Docker, services, env |
| **Board Pass**          | Encrypted credential bundle with connection config (+ SSH keys for key auth) |
| **VS Code extension**   | Import pass, connect, health check, start/stop, status bar           |

Your cloud, your control. Runs in your Azure subscription. No vendor lock-in. Apache 2.0 licensed.

See the [Architecture docs](https://barney-w.github.io/board/reference/architecture/) for the full deep-dive.

---

## Contributing

The easiest way to contribute is writing a [project manifest](projects/examples/). See [CONTRIBUTING.md](CONTRIBUTING.md).
