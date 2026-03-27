#!/usr/bin/env bash
# board init — auto-detect project stack and generate a .project.yaml manifest
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/ui.sh
source "${SCRIPT_DIR}/lib/ui.sh"

PROJECT_DIR="${1:-.}"
cd "$PROJECT_DIR"
PROJECT_NAME=$(basename "$(pwd)")

ui_header "Board Init"
ui_info "Scanning ${PROJECT_DIR}..."
echo ""

# ── Detection ──

LANG=""
FRAMEWORK=""
PACKAGE_MGR=""
declare -a DOCKER_SERVICES=()
declare -a DETECTED=()

# Language detection
if [[ -f "pyproject.toml" ]] || [[ -f "requirements.txt" ]] || [[ -f "setup.py" ]]; then
    LANG="python"
    if [[ -f "pyproject.toml" ]] && grep -q '\[tool\.uv\]' pyproject.toml 2>/dev/null; then
        PACKAGE_MGR="uv"
    elif [[ -f "Pipfile" ]]; then
        PACKAGE_MGR="pipenv"
    elif [[ -f "pyproject.toml" ]]; then
        PACKAGE_MGR="pip"
    else
        PACKAGE_MGR="pip"
    fi
    DETECTED+=("Python ($PACKAGE_MGR)")
elif [[ -f "package.json" ]]; then
    LANG="node"
    if [[ -f "pnpm-lock.yaml" ]]; then
        PACKAGE_MGR="pnpm"
    elif [[ -f "yarn.lock" ]]; then
        PACKAGE_MGR="yarn"
    else
        PACKAGE_MGR="npm"
    fi
    DETECTED+=("Node.js ($PACKAGE_MGR)")
elif [[ -f "go.mod" ]]; then
    LANG="go"
    PACKAGE_MGR="go"
    DETECTED+=("Go")
elif [[ -f "Gemfile" ]]; then
    LANG="ruby"
    PACKAGE_MGR="bundler"
    DETECTED+=("Ruby (bundler)")
elif [[ -f "build.gradle" ]] || [[ -f "build.gradle.kts" ]] || [[ -f "pom.xml" ]]; then
    LANG="java"
    if [[ -f "build.gradle" ]] || [[ -f "build.gradle.kts" ]]; then
        PACKAGE_MGR="gradle"
    else
        PACKAGE_MGR="maven"
    fi
    DETECTED+=("Java ($PACKAGE_MGR)")
fi

# Framework detection
if [[ "$LANG" == "python" ]]; then
    deps=""
    [[ -f "pyproject.toml" ]] && deps=$(cat pyproject.toml)
    [[ -f "requirements.txt" ]] && deps="$deps $(cat requirements.txt)"
    if echo "$deps" | grep -qi "django"; then
        FRAMEWORK="django"
        DETECTED+=("Django")
    elif echo "$deps" | grep -qi "fastapi"; then
        FRAMEWORK="fastapi"
        DETECTED+=("FastAPI")
    elif echo "$deps" | grep -qi "flask"; then
        FRAMEWORK="flask"
        DETECTED+=("Flask")
    fi
elif [[ "$LANG" == "node" ]]; then
    if grep -q '"next"' package.json 2>/dev/null; then
        FRAMEWORK="nextjs"
        DETECTED+=("Next.js")
    elif grep -q '"react"' package.json 2>/dev/null; then
        FRAMEWORK="react"
        DETECTED+=("React")
    elif grep -q '"vue"' package.json 2>/dev/null; then
        FRAMEWORK="vue"
        DETECTED+=("Vue")
    elif grep -q '"express"' package.json 2>/dev/null; then
        FRAMEWORK="express"
        DETECTED+=("Express")
    fi
elif [[ "$LANG" == "ruby" ]]; then
    if grep -q "rails" Gemfile 2>/dev/null; then
        FRAMEWORK="rails"
        DETECTED+=("Rails")
    fi
elif [[ "$LANG" == "java" ]]; then
    all_build=""
    [[ -f "build.gradle" ]] && all_build=$(cat build.gradle)
    [[ -f "build.gradle.kts" ]] && all_build=$(cat build.gradle.kts)
    [[ -f "pom.xml" ]] && all_build=$(cat pom.xml)
    if echo "$all_build" | grep -qi "spring-boot"; then
        FRAMEWORK="spring-boot"
        DETECTED+=("Spring Boot")
    fi
fi

# Docker service detection
if [[ -f "docker-compose.yml" ]] || [[ -f "docker-compose.yaml" ]] || [[ -f "compose.yml" ]] || [[ -f "compose.yaml" ]]; then
    compose_file=""
    for f in docker-compose.yml docker-compose.yaml compose.yml compose.yaml; do
        [[ -f "$f" ]] && compose_file="$f" && break
    done
    if [[ -n "$compose_file" ]]; then
        if grep -qi "postgres" "$compose_file"; then
            DOCKER_SERVICES+=("postgres")
            DETECTED+=("PostgreSQL")
        fi
        if grep -qi "redis" "$compose_file"; then
            DOCKER_SERVICES+=("redis")
            DETECTED+=("Redis")
        fi
        if grep -qi "mysql" "$compose_file"; then
            DOCKER_SERVICES+=("mysql")
            DETECTED+=("MySQL")
        fi
        if grep -qi "mongo" "$compose_file"; then
            DOCKER_SERVICES+=("mongodb")
            DETECTED+=("MongoDB")
        fi
    fi
fi

# ── Display detected ──
if [[ ${#DETECTED[@]} -eq 0 ]]; then
    ui_warn "Could not detect project stack"
    ui_info "Create a manifest manually using examples in projects/examples/"
    exit 1
fi

echo "  ${_bold}Detected:${_reset}"
for item in "${DETECTED[@]}"; do
    echo "    ${_green}✓${_reset} ${item}"
done
echo ""

# ── Generate manifest ──

# Determine default port
DEFAULT_PORT="8080"
case "$FRAMEWORK" in
    django) DEFAULT_PORT="8000" ;;
    nextjs|rails) DEFAULT_PORT="3000" ;;
    fastapi|flask) DEFAULT_PORT="8000" ;;
    express) DEFAULT_PORT="3000" ;;
    spring-boot) DEFAULT_PORT="8080" ;;
esac

# Determine install commands
INSTALL_CMD=""
case "$LANG" in
    python)
        case "$PACKAGE_MGR" in
            uv) INSTALL_CMD="uv sync" ;;
            pipenv) INSTALL_CMD="pipenv install" ;;
            *) INSTALL_CMD="pip install -r requirements.txt" ;;
        esac
        ;;
    node)
        case "$PACKAGE_MGR" in
            pnpm) INSTALL_CMD="pnpm install" ;;
            yarn) INSTALL_CMD="yarn install" ;;
            *) INSTALL_CMD="npm install" ;;
        esac
        ;;
    go) INSTALL_CMD="go mod download" ;;
    ruby) INSTALL_CMD="bundle install" ;;
    java)
        case "$PACKAGE_MGR" in
            gradle) INSTALL_CMD="./gradlew build -x test" ;;
            *) INSTALL_CMD="mvn package -DskipTests" ;;
        esac
        ;;
esac

# Determine run command
RUN_CMD=""
case "$FRAMEWORK" in
    django) RUN_CMD="python manage.py runserver 0.0.0.0:${DEFAULT_PORT}" ;;
    fastapi) RUN_CMD="uvicorn main:app --host 0.0.0.0 --port ${DEFAULT_PORT} --reload" ;;
    flask) RUN_CMD="flask run --host=0.0.0.0 --port=${DEFAULT_PORT}" ;;
    nextjs) RUN_CMD="$PACKAGE_MGR run dev" ;;
    rails) RUN_CMD="rails server -b 0.0.0.0 -p ${DEFAULT_PORT}" ;;
    express) RUN_CMD="$PACKAGE_MGR run dev" ;;
    spring-boot) RUN_CMD="./gradlew bootRun" ;;
    react|vue) RUN_CMD="$PACKAGE_MGR run dev" ;;
    *)
        case "$LANG" in
            go) RUN_CMD="go run ." ;;
            *) RUN_CMD="echo 'TODO: add run command'" ;;
        esac
        ;;
esac

# Generate YAML
cat << YAML
name: "${PROJECT_NAME}"
description: "TODO: describe your project"
repo: "https://github.com/your-org/${PROJECT_NAME}"

requires:
YAML

case "$LANG" in
    python) echo "  - python3"; [[ "$PACKAGE_MGR" == "uv" ]] && echo "  - uv" ;;
    node) echo "  - node"; [[ "$PACKAGE_MGR" == "pnpm" ]] && echo "  - pnpm" ;;
    go) echo "  - go" ;;
    ruby) echo "  - ruby"; echo "  - bundler" ;;
    java) echo "  - java"; [[ "$PACKAGE_MGR" == "gradle" ]] && echo "  - gradle" ;;
esac

cat << YAML

install:
  - "${INSTALL_CMD}"
YAML

# Docker section
if [[ ${#DOCKER_SERVICES[@]} -gt 0 ]]; then
    echo ""
    echo "docker:"
    echo "  compose: true"
    echo "  services:"
    for svc in "${DOCKER_SERVICES[@]}"; do
        case "$svc" in
            postgres)
                echo "    - name: postgres"
                echo "      image: postgres:16"
                echo "      ports: [\"5432:5432\"]"
                echo "      env:"
                echo "        POSTGRES_DB: ${PROJECT_NAME}"
                echo "        POSTGRES_USER: dev"
                echo "        POSTGRES_PASSWORD: dev"
                ;;
            redis)
                echo "    - name: redis"
                echo "      image: redis:7-alpine"
                echo "      ports: [\"6379:6379\"]"
                ;;
            mysql)
                echo "    - name: mysql"
                echo "      image: mysql:8"
                echo "      ports: [\"3306:3306\"]"
                echo "      env:"
                echo "        MYSQL_DATABASE: ${PROJECT_NAME}"
                echo "        MYSQL_ROOT_PASSWORD: dev"
                ;;
            mongodb)
                echo "    - name: mongodb"
                echo "      image: mongo:7"
                echo "      ports: [\"27017:27017\"]"
                ;;
        esac
    done
fi

# Services section
cat << YAML

services:
  - name: "${PROJECT_NAME}"
    command: "${RUN_CMD}"
    port: ${DEFAULT_PORT}
    health:
      endpoint: "http://localhost:${DEFAULT_PORT}/"
      interval: 10
YAML

# Env section
echo ""
echo "env:"
echo "  NODE_ENV: development"
case "$LANG" in
    python) echo "  PYTHONUNBUFFERED: \"1\"" ;;
esac
for svc in "${DOCKER_SERVICES[@]}"; do
    case "$svc" in
        postgres) echo "  DATABASE_URL: \"postgresql://dev:dev@localhost:5432/${PROJECT_NAME}\"" ;;
        redis) echo "  REDIS_URL: \"redis://localhost:6379\"" ;;
        mysql) echo "  DATABASE_URL: \"mysql://root:dev@localhost:3306/${PROJECT_NAME}\"" ;;
        mongodb) echo "  MONGO_URL: \"mongodb://localhost:27017/${PROJECT_NAME}\"" ;;
    esac
done

# Health section
cat << YAML

health:
  - label: "${PROJECT_NAME}"
    check: "curl -sf http://localhost:${DEFAULT_PORT}/ >/dev/null"
YAML

for svc in "${DOCKER_SERVICES[@]}"; do
    case "$svc" in
        postgres) echo "  - label: Postgres"; echo "    check: \"pg_isready -h localhost -p 5432\"" ;;
        redis) echo "  - label: Redis"; echo "    check: \"redis-cli ping | grep -q PONG\"" ;;
        mysql) echo "  - label: MySQL"; echo "    check: \"mysqladmin ping -h localhost --silent\"" ;;
        mongodb) echo "  - label: MongoDB"; echo "    check: \"mongosh --eval 'db.runCommand({ping:1})' --quiet\"" ;;
    esac
done

echo ""
ui_success "Manifest generated. Pipe to file: just init > ${PROJECT_NAME}.project.yaml" >&2
