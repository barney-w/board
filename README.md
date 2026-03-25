# Board

Cloud dev environments that just work.

Board provisions fully-configured cloud development environments on Azure. Developers receive a single zip file and a passphrase — double-click the setup script, enter the passphrase, and start coding on a full Linux VM with all tools, services, and projects pre-installed.

## What it does

- **For admins:** One command (`just board`) runs an interactive wizard that provisions an Azure VM with Docker, dev tools, project repos, and services — all configured and running before the developer connects.
- **For developers:** Double-click a setup script, enter a passphrase, click Connect in VS Code. No terminal, no manual configuration.

## Getting started

```bash
git clone https://github.com/barney-w/board.git && cd board
just board                # interactive setup wizard
just export-pass jbloggs  # create starter kit for a developer
```

## Tech stack

- **Infrastructure:** Azure Bicep + cloud-init
- **Provisioning:** Bash scripts with project manifests (YAML)
- **Extension:** VS Code extension for one-click connection
- **Security:** Encrypted board passes, SSH key auth, Key Vault integration

## License

MIT — see [LICENSE](LICENSE).
