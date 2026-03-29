---
title: Quickstart
description: Get a cloud dev environment running in 5 minutes.
---

## Prerequisites

- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) with an active subscription
- [just](https://github.com/casey/just) command runner
- [Node.js 20+](https://nodejs.org/) (for the VS Code extension)

## Board up

```bash
git clone https://github.com/barney-w/board.git
cd board
just board
```

The interactive wizard walks you through:

1. **Azure login** — authenticates with your subscription
2. **Environment name** — label for this cloud environment
3. **Environment type** — personal or work-sandbox
4. **Projects** — which project manifests to provision
5. **Deploy** — creates the VM, installs tools, provisions projects

When it finishes, you'll see a completion card with the environment details and next steps.

## Send a board pass

```bash
just export-pass alice
```

This creates an encrypted `.board-pass` file. Send it to the developer along with the passphrase (via a separate channel).

## Connect

The developer installs the [Board VS Code extension](https://marketplace.visualstudio.com/items?itemName=board), imports the board pass, and clicks **Connect**. That's it — they're coding.
