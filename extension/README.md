# Board

One-click connection to your Board cloud dev environment.

## Quick Start

Your admin sent you a **`.board-pass`** file and a **passphrase**.

1. **Cmd+Shift+P** > `Board: Import Pass` > select the file > enter the passphrase
2. Click **Connect Now** on the board pass card
3. You're coding on your cloud VM

The extension handles SSH keys, config, and connection automatically.

## After Connecting

On first connect you'll be prompted to run **first-time setup** (Git identity + SSH keys).

Your VM has a sample project at `~/projects/hello-board` — try `docker compose up` and visit `http://localhost:8000`.

## Commands

| Command | What it does |
|---|---|
| `Board: Import Pass` | Decrypt and install a `.board-pass` file |
| `Board: Connect` | Open a remote VS Code window on your VM |
| `Board: Start` / `Stop` | Start or deallocate the VM (requires Azure CLI) |
| `Board: Run First-Time Setup` | Configure Git + SSH keys on the VM |
| `Board: Open in Browser` | Open code-server or VS Code Tunnel |

## Don't have a board pass?

Ask your admin. They'll create one with `just export-pass <yourname>`.
