# Contributing to Board

Thanks for your interest in contributing to Board! This guide will help you get started.

## Quick Links

- [Example Project Manifests](projects/examples/)
- [Community Project Manifests](projects/community/)

## Easiest Contribution: Write a Project Manifest

The simplest way to contribute is to write a project manifest. A manifest describes how to provision a dev environment for a project. Check out the examples in `projects/examples/` for inspiration, then submit yours to `projects/community/`.

A manifest is a YAML file that declares the tools, runtimes, and infrastructure a project needs. See the examples in `projects/examples/` for details on the manifest schema.

## Dev Setup

To work on Board itself, you need:

1. **Azure CLI** -- Install via `brew install azure-cli` or see [Microsoft docs](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli). Log in with `az login`.
2. **just** -- A command runner. Install via `brew install just` or see [just docs](https://github.com/casey/just).
3. **uv** -- Python package manager. Install via `curl -LsSf https://astral.sh/uv/install.sh | sh` or `brew install uv`.
4. **Node.js 20+** -- Required for the VS Code extension. Install via `brew install node@20` or use [nvm](https://github.com/nvm-sh/nvm).

### Python CLI (cli/)

The Board CLI is a Python package using typer, Rich, and the Azure SDK.

```bash
cd cli
uv sync --all-extras    # Install all dependencies (including dev)
uv run board --help     # Verify CLI works
uv run pytest           # Run all tests
uv run ruff check       # Lint
uv run ruff format      # Format
uv run mypy src/        # Type check
```

Once installed, run `just` to see available recipes.

## Docs Site

The documentation site uses [Astro Starlight](https://starlight.astro.build/) and lives in `docs/site/`.

```bash
cd docs/site
npm install
npm run dev
```

This starts a local dev server (usually at `http://localhost:4321`). Content lives in `docs/site/src/content/`.

## Code Style

- **Python CLI**: Must pass `ruff check`, `ruff format --check`, and `mypy --strict src/`. Target Python 3.12+.
- **Shell scripts** (setup-me.sh, cloud-init.yaml): Must pass `shellcheck` with zero warnings. Use `#!/usr/bin/env bash` and `set -euo pipefail`.
- **TypeScript (VS Code extension)**: Follow Prettier formatting and ESLint rules. Run `npm run lint` and `npm run format` in the `extension/` directory.
- **Commit messages**: Use [Conventional Commits](https://www.conventionalcommits.org/) format:
  - `feat: add multi-project provisioning`
  - `fix: correct health check timeout`
  - `docs: update architecture overview`
  - `chore: bump dependencies`

## Submitting Changes

1. Fork the repository and create a feature branch from `main`.
2. Make your changes, ensuring all checks pass (`shellcheck`, extension builds, manifests parse).
3. Write clear commit messages using Conventional Commits.
4. Open a pull request against `main` and fill out the PR template.

## Reporting Issues

Use the GitHub issue templates for bug reports and feature requests. For questions, check the [documentation](docs/) first.

## License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).
