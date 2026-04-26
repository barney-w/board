"""Board CLI — typer application and subcommand registration."""

import typer

app = typer.Typer(
    name="board",
    help="Provision and manage Azure developer VMs.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

# ── Subcommand groups ──
vm_app = typer.Typer(name="vm", help="Manage VMs (start, stop, ssh, ls, status, delete, keygen).")
app.add_typer(vm_app)

ssh_config_app = typer.Typer(name="ssh-config", help="Manage SSH config file entries.")
app.add_typer(ssh_config_app)

admin_app = typer.Typer(
    name="admin",
    help="Admin commands (control panel, MFA setup).",
    invoke_without_command=True,
)
app.add_typer(admin_app)

# ── Import and register CLI commands ──

from board.cli.costs import costs_command  # noqa: E402
from board.cli.export_pass import export_pass_command  # noqa: E402
from board.cli.fleet import fleet_command  # noqa: E402
from board.cli.infra import (  # noqa: E402
    create_rg_command,
    create_vm_command,
    destroy_command,
    preflight_command,
    validate_command,
    what_if_command,
)
from board.cli.init import init_command  # noqa: E402
from board.cli.policies_cmd import show_command as policies_show_command  # noqa: E402
from board.cli.projects import install_projects_command, project_status_command  # noqa: E402
from board.cli.setup import up_command  # noqa: E402
from board.cli.tools import rotate_key_command, wait_ready_command  # noqa: E402
from board.cli.validate import smoke_test_command  # noqa: E402

# Core commands
app.command(name="up")(up_command)
app.command(name="fleet")(fleet_command)
app.command(name="init")(init_command)
app.command(name="smoke-test")(smoke_test_command)
app.command(name="export-pass")(export_pass_command)
app.command(name="costs")(costs_command)
app.command(name="policies")(policies_show_command)

# Infrastructure commands
app.command(name="create-rg")(create_rg_command)
app.command(name="create-vm")(create_vm_command)
app.command(name="validate")(validate_command)
app.command(name="what-if")(what_if_command)
app.command(name="destroy")(destroy_command)
app.command(name="preflight")(preflight_command)

# Project commands
app.command(name="install-projects")(install_projects_command)
app.command(name="project-status")(project_status_command)

# Utility commands
app.command(name="wait-ready")(wait_ready_command)
app.command(name="rotate-key")(rotate_key_command)

# Import subcommands to trigger their @app.command() registrations
import board.cli.admin  # noqa: E402, F401
import board.cli.ssh_config_cmd  # noqa: E402, F401
import board.cli.vm  # noqa: E402, F401
