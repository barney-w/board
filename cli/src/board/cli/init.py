"""board init — auto-detect project stack and emit a .project.yaml manifest."""

from __future__ import annotations

from pathlib import Path

import typer

from board.ui import console as con

# ── Detection tables ──

FRAMEWORK_PORTS = {
    "django": "8000",
    "fastapi": "8000",
    "flask": "8000",
    "nextjs": "3000",
    "react": "3000",
    "vue": "3000",
    "express": "3000",
    "rails": "3000",
    "spring-boot": "8080",
}

FRAMEWORK_RUN_CMDS = {
    "django": "python manage.py runserver 0.0.0.0:{port}",
    "fastapi": "uvicorn main:app --host 0.0.0.0 --port {port} --reload",
    "flask": "flask run --host=0.0.0.0 --port={port}",
    "nextjs": "{pkg} run dev",
    "react": "{pkg} run dev",
    "vue": "{pkg} run dev",
    "express": "{pkg} run dev",
    "rails": "rails server -b 0.0.0.0 -p {port}",
    "spring-boot": "./gradlew bootRun",
}


def _detect_language(project_dir: Path) -> tuple[str, str]:
    """Detect language and package manager. Returns (language, package_manager)."""
    if (
        (project_dir / "pyproject.toml").exists()
        or (project_dir / "requirements.txt").exists()
        or (project_dir / "setup.py").exists()
    ):
        if (project_dir / "pyproject.toml").exists():
            content = (project_dir / "pyproject.toml").read_text()
            if "[tool.uv]" in content:
                return "python", "uv"
            return "python", "pip"
        if (project_dir / "Pipfile").exists():
            return "python", "pipenv"
        return "python", "pip"
    elif (project_dir / "package.json").exists():
        if (project_dir / "pnpm-lock.yaml").exists():
            return "node", "pnpm"
        if (project_dir / "yarn.lock").exists():
            return "node", "yarn"
        return "node", "npm"
    elif (project_dir / "go.mod").exists():
        return "go", "go"
    elif (project_dir / "Gemfile").exists():
        return "ruby", "bundler"
    elif (
        (project_dir / "build.gradle").exists()
        or (project_dir / "build.gradle.kts").exists()
        or (project_dir / "pom.xml").exists()
    ):
        if (project_dir / "build.gradle").exists() or (project_dir / "build.gradle.kts").exists():
            return "java", "gradle"
        return "java", "maven"
    return "", ""


def _detect_framework(project_dir: Path, language: str) -> str:
    """Detect framework from project files."""
    if language == "python":
        deps = ""
        if (project_dir / "pyproject.toml").exists():
            deps += (project_dir / "pyproject.toml").read_text()
        if (project_dir / "requirements.txt").exists():
            deps += " " + (project_dir / "requirements.txt").read_text()
        dl = deps.lower()
        if "django" in dl:
            return "django"
        if "fastapi" in dl:
            return "fastapi"
        if "flask" in dl:
            return "flask"
    elif language == "node":
        if (project_dir / "package.json").exists():
            pkg = (project_dir / "package.json").read_text()
            if '"next"' in pkg:
                return "nextjs"
            if '"react"' in pkg:
                return "react"
            if '"vue"' in pkg:
                return "vue"
            if '"express"' in pkg:
                return "express"
    elif language == "ruby":
        if (project_dir / "Gemfile").exists() and "rails" in (
            project_dir / "Gemfile"
        ).read_text().lower():
            return "rails"
    elif language == "java":
        for f in ("build.gradle", "build.gradle.kts", "pom.xml"):
            if (project_dir / f).exists():
                content = (project_dir / f).read_text().lower()
                if "spring-boot" in content or "springframework" in content:
                    return "spring-boot"
    return ""


def _detect_docker_services(project_dir: Path) -> list[str]:
    """Detect Docker Compose services."""
    services = []
    compose_file = None
    for name in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
        if (project_dir / name).exists():
            compose_file = project_dir / name
            break

    if compose_file is None:
        return services

    content = compose_file.read_text().lower()
    if "postgres" in content:
        services.append("postgres")
    if "redis" in content:
        services.append("redis")
    if "mysql" in content:
        services.append("mysql")
    if "mongo" in content:
        services.append("mongodb")

    return services


def _install_command(language: str, package_mgr: str) -> str:
    """Get the install command for the detected stack."""
    cmds = {
        ("python", "uv"): "uv sync",
        ("python", "pipenv"): "pipenv install",
        ("python", "pip"): "pip install -r requirements.txt",
        ("node", "pnpm"): "pnpm install",
        ("node", "yarn"): "yarn install",
        ("node", "npm"): "npm install",
        ("go", "go"): "go mod download",
        ("ruby", "bundler"): "bundle install",
        ("java", "gradle"): "./gradlew build -x test",
        ("java", "maven"): "mvn package -DskipTests",
    }
    return cmds.get((language, package_mgr), "")


def _run_command(framework: str, language: str, package_mgr: str, port: str) -> str:
    """Get the run command for the detected framework."""
    template = FRAMEWORK_RUN_CMDS.get(framework, "")
    if template:
        return template.format(pkg=package_mgr, port=port)
    if language == "go":
        return "go run ."
    return "echo 'TODO: add run command'"


def _generate_manifest(project_dir: Path) -> str:
    """Generate YAML manifest content."""
    project_name = project_dir.name
    language, package_mgr = _detect_language(project_dir)
    framework = _detect_framework(project_dir, language)
    docker_services = _detect_docker_services(project_dir)

    if not language:
        return ""

    port = FRAMEWORK_PORTS.get(framework, "8080")
    install_cmd = _install_command(language, package_mgr)
    run_cmd = _run_command(framework, language, package_mgr, port)

    lines: list[str] = []
    lines.append(f'name: "{project_name}"')
    lines.append('description: "TODO: describe your project"')
    lines.append(f'repo: "https://github.com/your-org/{project_name}"')
    lines.append("")
    lines.append("requires:")

    lang_requires = {
        "python": ["python3"] + (["uv"] if package_mgr == "uv" else []),
        "node": ["node"] + (["pnpm"] if package_mgr == "pnpm" else []),
        "go": ["go"],
        "ruby": ["ruby", "bundler"],
        "java": ["java"] + (["gradle"] if package_mgr == "gradle" else []),
    }
    for req in lang_requires.get(language, []):
        lines.append(f"  - {req}")

    lines.append("")
    lines.append("install:")
    lines.append(f'  - "{install_cmd}"')

    # Docker section
    if docker_services:
        lines.append("")
        lines.append("docker:")
        lines.append("  compose: true")
        lines.append("  services:")

        docker_templates = {
            "postgres": [
                "    - name: postgres",
                "      image: postgres:16",
                '      ports: ["5432:5432"]',
                "      env:",
                f"        POSTGRES_DB: {project_name}",
                "        POSTGRES_USER: dev",
                "        POSTGRES_PASSWORD: dev",
            ],
            "redis": [
                "    - name: redis",
                "      image: redis:7-alpine",
                '      ports: ["6379:6379"]',
            ],
            "mysql": [
                "    - name: mysql",
                "      image: mysql:8",
                '      ports: ["3306:3306"]',
                "      env:",
                f"        MYSQL_DATABASE: {project_name}",
                "        MYSQL_ROOT_PASSWORD: dev",
            ],
            "mongodb": [
                "    - name: mongodb",
                "      image: mongo:7",
                '      ports: ["27017:27017"]',
            ],
        }
        for svc in docker_services:
            lines.extend(docker_templates.get(svc, []))

    # Services section
    lines.append("")
    lines.append("services:")
    lines.append(f'  - name: "{project_name}"')
    lines.append(f'    command: "{run_cmd}"')
    lines.append(f"    port: {port}")
    lines.append("    health:")
    lines.append(f'      endpoint: "http://localhost:{port}/"')
    lines.append("      interval: 10")

    # Env section
    lines.append("")
    lines.append("env:")
    lines.append("  NODE_ENV: development")
    if language == "python":
        lines.append('  PYTHONUNBUFFERED: "1"')

    env_urls = {
        "postgres": f'  DATABASE_URL: "postgresql://dev:dev@localhost:5432/{project_name}"',
        "redis": '  REDIS_URL: "redis://localhost:6379"',
        "mysql": f'  DATABASE_URL: "mysql://root:dev@localhost:3306/{project_name}"',
        "mongodb": f'  MONGO_URL: "mongodb://localhost:27017/{project_name}"',
    }
    for svc in docker_services:
        if svc in env_urls:
            lines.append(env_urls[svc])

    # Health section
    lines.append("")
    lines.append("health:")
    lines.append(f'  - label: "{project_name}"')
    lines.append(f'    check: "curl -sf http://localhost:{port}/ >/dev/null"')

    health_checks = {
        "postgres": ('  - label: Postgres\n    check: "pg_isready -h localhost -p 5432"'),
        "redis": ('  - label: Redis\n    check: "redis-cli ping | grep -q PONG"'),
        "mysql": ('  - label: MySQL\n    check: "mysqladmin ping -h localhost --silent"'),
        "mongodb": (
            "  - label: MongoDB\n    check: \"mongosh --eval 'db.runCommand({ping:1})' --quiet\""
        ),
    }
    for svc in docker_services:
        if svc in health_checks:
            lines.append(health_checks[svc])

    lines.append("")
    return "\n".join(lines)


def init_command(
    path: str = typer.Argument(".", help="Project directory to scan."),
) -> None:
    """Detect project stack and generate a .project.yaml manifest."""
    project_dir = Path(path).resolve()

    if not project_dir.is_dir():
        con.error(f"Not a directory: {project_dir}")
        raise typer.Exit(1)

    con.header("Board Init")
    con.info(f"Scanning {project_dir}...")

    language, package_mgr = _detect_language(project_dir)
    framework = _detect_framework(project_dir, language)
    docker_services = _detect_docker_services(project_dir)

    # Collect detections for display
    detected: list[str] = []

    lang_labels = {
        "python": f"Python ({package_mgr})",
        "node": f"Node.js ({package_mgr})",
        "go": "Go",
        "ruby": f"Ruby ({package_mgr})",
        "java": f"Java ({package_mgr})",
    }
    if language in lang_labels:
        detected.append(lang_labels[language])

    framework_labels = {
        "django": "Django",
        "fastapi": "FastAPI",
        "flask": "Flask",
        "nextjs": "Next.js",
        "react": "React",
        "vue": "Vue",
        "express": "Express",
        "rails": "Rails",
        "spring-boot": "Spring Boot",
    }
    if framework in framework_labels:
        detected.append(framework_labels[framework])

    docker_labels = {
        "postgres": "PostgreSQL",
        "redis": "Redis",
        "mysql": "MySQL",
        "mongodb": "MongoDB",
    }
    for svc in docker_services:
        if svc in docker_labels:
            detected.append(docker_labels[svc])

    if not detected:
        con.warn("Could not detect project stack")
        con.info("Create a manifest manually using examples in projects/examples/")
        raise typer.Exit(1)

    con.console.print()
    con.console.print("  [bold]Detected:[/bold]")
    for item in detected:
        con.success(item)
    con.console.print()

    manifest = _generate_manifest(project_dir)
    # Print manifest to stdout
    typer.echo(manifest)

    project_name = project_dir.name
    con.success(f"Manifest generated. Pipe to file: board init > {project_name}.project.yaml")
