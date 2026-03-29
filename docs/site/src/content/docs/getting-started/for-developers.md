---
title: For Developers
description: Guide for developers using a cloud dev environment.
---

Your cloud dev environment is managed by your team — you just need to connect.

## Getting started

1. Install the **Board** VS Code extension
2. You'll receive a `.board-pass` file and a passphrase from your team lead
3. Open VS Code — the welcome page appears automatically
4. Click **Import Pass** and select your `.board-pass` file
5. Enter the passphrase when prompted
6. Click **Connect** — you're in

## What's in your environment

Your cloud environment comes with everything pre-configured:

- **Your projects** cloned and ready at `~/projects/`
- **Docker services** running (databases, caches, etc.)
- **Application services** managed by systemd
- **VS Code workspace** with tasks, launch configs, and settings
- **Health checks** to verify everything works

## Daily workflow

**Start your board** (if stopped):
- Click the Board status bar item in VS Code, or
- Your admin can start it with `just start yourname`

**Check health:**
```bash
check
```

This runs all health checks and shows which services are healthy.

**Get help:**
```bash
board-help
```

Shows available commands and how to manage services.

## Your board auto-stops

Boards auto-shutdown at 7 PM to save costs. Your work is saved — just start it again tomorrow. All your files, Docker volumes, and git state persist.
