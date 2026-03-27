# Community Project Manifests

This directory contains community-contributed project manifests for Board.

## What is a manifest?

A Board project manifest (`.project.yaml`) declares everything a dev environment
needs to run a project: dependencies, Docker services, application services,
environment variables, VS Code configuration, and health checks. Board reads
these manifests and provisions a fully working environment automatically.

See `projects/examples/` for reference manifests covering Next.js, Django, Rails,
Go, and Spring Boot.

## Contributing a manifest

1. **Fork** the Board repository.

2. **Create your manifest** in `projects/community/` following the naming
   convention below.

3. **Test your manifest** by provisioning a Board VM with it. Every health check
   should pass.

4. **Submit a pull request** with:
   - The manifest file
   - A brief description of the stack in the PR body
   - Confirmation that you tested provisioning end-to-end

## Naming convention

Manifest files must follow this pattern:

```
<stack>-<variant>.project.yaml
```

Examples:
- `flask-api.project.yaml`
- `express-graphql.project.yaml`
- `rust-axum.project.yaml`
- `elixir-phoenix.project.yaml`
- `dotnet-webapi.project.yaml`

Use lowercase, hyphens for separators, no underscores. The name should make the
stack and purpose immediately clear.

## Quality requirements

Every community manifest must include:

- **name** -- Unique, matches the filename without `.project.yaml`
- **description** -- One-line summary of the stack
- **repo** -- A public repository URL (use a real, cloneable repo or a clearly
  marked placeholder like `https://github.com/your-org/project`)
- **requires** -- List of required tools
- **install** -- At least one labeled install step
- **docker** -- At least one container with a health check (if the project uses
  any data stores or infrastructure services)
- **services** -- At least one application service with a health URL
- **env** -- Environment section with `hardcoded` values for local dev and a
  `fallback` file
- **vscode** -- Port forwarding, at least two tasks, and a debug launch config
- **health** -- At least two health checks

Additional quality standards:

- All commands must be idempotent (safe to run multiple times)
- Health check commands must return exit code 0 on success, non-zero on failure
- Docker container names must be prefixed with the project name to avoid
  collisions
- Port numbers must not conflict with common defaults (check existing manifests)
- Secrets must use `keyvault_secrets` with descriptive key names, never hardcoded
  credentials for real services
- The `hardcoded` env section is only for local dev values (localhost URLs,
  default passwords for local databases, debug flags)

## Schema reference

Refer to the existing example manifests for the full schema:

- `projects/examples/django-api.project.yaml` -- Python/Django + Postgres (full example)
- `projects/examples/nextjs-app.project.yaml` -- Next.js/pnpm + Postgres (minimal example)
- `projects/examples/*.project.yaml` -- Various stacks (comprehensive examples)

## Questions?

Open an issue on the Board repository if you have questions about the manifest
schema or need help with your contribution.
