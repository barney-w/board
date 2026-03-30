---
title: For Developers
description: Connect to your cloud dev environment and start coding.
---

Your admin gives you a zip file and a passphrase. Everything else is automatic.

## Connect

1. Unzip the folder and double-click **Setup Board** (`.command` on Mac, `.cmd` on Windows)
2. VS Code opens and asks for your passphrase — enter it
3. Your Board Pass card appears — click **Connect Now**

You're coding on a cloud VM. VS Code's file explorer, terminal, and extensions all run remotely.

## First-time setup

On first connect, you'll be prompted to run a short setup: your name for Git, an SSH key, and optionally GitHub authentication (for Copilot). After that, your projects are at `~/projects/` with everything already running.

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

## Auto-shutdown

Boards stop at 7 PM daily to save costs. Your files, Docker volumes, and git state all persist — just reconnect tomorrow.
