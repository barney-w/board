---
title: Quickstart
description: Provision a cloud dev environment and hand it to a developer.
---

## Prerequisites

- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) with an active subscription
- [just](https://github.com/casey/just) command runner
- [shellcheck](https://github.com/koalaman/shellcheck) and [yq](https://github.com/mikefarah/yq) (for `just check`)

## Provision

```bash
git clone https://github.com/barney-w/board.git
cd board
just board
```

The interactive wizard walks you through Azure login, naming the environment, selecting project manifests, and deploying. It creates the VM, runs cloud-init, provisions projects, and verifies health.

## Send a board pass

```bash
just export-pass jbloggs
```

This creates a starter kit zip containing a `.board-pass` file, the VS Code extension VSIX, a setup script, and a quick-start guide. For Entra ID boards, just send the zip — no passphrase needed. For SSH-key boards, share the passphrase via a separate channel.

## Developer connects

The developer unzips, double-clicks **Setup Board**, and clicks **Connect**. For SSH-key boards, they'll be prompted for the passphrase. See [For Developers](/board/getting-started/for-developers/) for their full guide.
