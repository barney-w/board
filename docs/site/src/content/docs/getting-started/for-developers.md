---
title: For Developers
description: Connect to your cloud dev environment and start coding.
---

Your admin gives you a zip file and a passphrase. Everything else is automatic.

## Connect

1. Unzip the folder and double-click **Setup Board** (`.command` on Mac, `.cmd` on Windows)
2. VS Code opens and asks for your passphrase — enter it
3. If your board uses **Entra ID** auth, ensure you have [Azure CLI](https://aka.ms/installazurecli) installed and run `az login` in your terminal first
4. Your Board Pass card appears — click **Connect Now**

You're coding on a cloud VM. VS Code's file explorer, terminal, and extensions all run remotely.

## First-time setup

On first connect, you'll be prompted to run a short setup: your name for Git and optionally GitHub authentication (for Copilot). After that, your projects are at `~/projects/` with everything already running.

## Daily workflow

**Start your board** (if stopped): click the Board status bar item in VS Code, or ask your admin.

**Check health:**
```bash
check
```

**See available commands:**
```bash
board-help
```

## Port forwarding

VS Code automatically forwards every listening port from your VM to localhost. When a service starts (API, database, Langfuse, etc.), it appears in the **Ports** panel — open it with `Ctrl+Shift+P` → *Ports: Focus on Ports View*. Click the globe icon to open any port in your browser.

Not using VS Code? Run `forward-ports` on the VM to get an SSH command that tunnels all listening ports at once.

## Browser tools

Your board includes two browser-based admin tools (VS Code forwards the ports automatically when connected):

- **Cockpit** (`http://localhost:9091`) — system monitoring, logs, file browser, and terminal. Log in with `devuser` / `board`.
- **Portainer** (`https://localhost:9444`) — Docker container management, logs, and restart services. The admin password is unique per VM — run `cat ~/.portainer-password` to see it. Portainer uses a self-signed certificate, so accept the browser warning on first visit.

Open them from the command palette: **Board: Open Cockpit** or **Board: Open Portainer**.

## Auto-shutdown

Boards stop at 7 PM daily to save costs. Your files, Docker volumes, and git state all persist — just reconnect tomorrow.
