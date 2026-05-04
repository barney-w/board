# Board CLI

Python CLI for provisioning and managing Azure developer VMs.

## Install

```bash
cd cli
uv sync              # install dependencies
uv run board --help  # verify
```

Or install as a tool:

```bash
uv tool install .
board --help
```

## Commands

```
board up              Interactive wizard — provisions a VM in ~11 min
board admin           Admin control panel (fleet status, manage boards, secrets)
board fleet           Fleet dashboard with metrics for all boards
board init [PATH]     Detect project stack, generate .project.yaml manifest
board smoke-test NAME Run health checks on a deployed board
board export-pass NAME Create encrypted board pass for a developer

board vm start NAME   Start a VM
board vm stop NAME    Stop (deallocate) a VM
board vm ssh NAME     SSH into a VM (add --plain to skip 2-column tmux layout)
board vm ls           List all VMs in the environment
board vm status NAME  Show detailed VM status
board vm delete NAME  Delete a VM
board vm keygen NAME  Generate SSH keypair for a VM
```

### Global flags

| Flag | Env var | Description |
|------|---------|-------------|
| `--dry-run` | `BOARD_DRY_RUN` | Validate inputs without deploying |
| `--non-interactive` | `BOARD_NON_INTERACTIVE` | Use env vars/defaults, skip prompts |
| `--env` | `BOARD_ENVIRONMENT` | Environment name (e.g. `personal`) |
| `--location` | `BOARD_LOCATION` | Azure region (e.g. `australiaeast`) |
| `--region-short` | `BOARD_REGION_SHORT` | Short region code (e.g. `aue`) |

Resource group naming is fixed at `rg-{env}-{region-short}-devvm`. To scope a board to a different RG, pick a different `--env`.

## Locked-down tenants

If your Azure tenant enforces mandatory tags via Azure Policy, copy `board.tags.example.yaml` (at the repo root) to `board.tags.yaml` and fill in your values. The wizard prompts *"Include extra tags?"* — answer **yes** to apply the tags to the resource group and every Bicep-deployed resource. The file is gitignored.

## Development

```bash
uv sync --all-extras     # install with dev dependencies
uv run pytest            # run tests (194 tests)
uv run ruff check        # lint
uv run ruff format       # format
uv run mypy src/         # type check
```

## Architecture

```
src/board/
  cli/           Command modules (typer)
  core/          Config, naming, errors, manifest parsing + file generators
  models/        Pydantic models (manifest, bundle, deployment)
  azure/         Azure SDK wrappers (auth, deployment, compute, keyvault)
  ssh/           asyncssh session, SSH config manager, key generation
  provision/     9-phase provisioning engine, orchestrator, cloud-init wait
  bundle/        AES-256-GCM encryption, payload assembly, zip packaging
  ui/            Rich console, questionary prompts, boarding pass display
```

## Compatibility

The CLI produces artifacts consumed by the VS Code extension (`extension/`). These contracts are tested:

- **Naming conventions** match `extension/src/config.ts` (e.g. `devvm-{name}`, `rg-{env}-{region}-devvm`)
- **Board pass encryption** (AES-256-GCM + PBKDF2) is byte-compatible with `extension/src/bundle.ts`
- **SSH config markers** (`# BEGIN board:` / `# END board:`) match `extension/src/ssh.ts`
- **BundlePayload** JSON field names (camelCase) match the TypeScript interface exactly
