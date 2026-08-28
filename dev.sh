#!/usr/bin/env bash
#
# Sajilo local development helper — the bash twin of dev.ps1.
#
#   ./dev.sh up        build and start everything, migrate and seed
#   ./dev.sh logs      follow all logs (OTP codes appear here)
#   ./dev.sh test      run the test suite
#   ./dev.sh lint      ruff + tsc
#   ./dev.sh rebuild   rebuild after adding a dependency
#   ./dev.sh seed      admin + catalog + demo accounts
#   ./dev.sh migrate   apply migrations
#   ./dev.sh psql      open a database shell
#   ./dev.sh shell     bash inside the api container
#   ./dev.sh down      stop everything
#   ./dev.sh reset     destroy volumes and rebuild from scratch
#
set -euo pipefail
cd "$(dirname "$0")"

# Tests use a separate database and Redis DB 15 so they never touch dev data.
TEST_ENV=(-e POSTGRES_DB=sajilo_test -e REDIS_URL=redis://redis:6379/15 -e ENVIRONMENT=test)

green() { printf '\033[32m%s\033[0m\n' "$1"; }
cyan()  { printf '\033[36m%s\033[0m\n' "$1"; }

seed_all() {
    docker compose exec -T api python -m app.cli seed-admin
    docker compose exec -T api python -m app.cli seed-catalog
    docker compose exec -T api python -m app.cli seed-demo
}

show_urls() {
    echo
    green "  Web:   http://localhost:3000"
    green "  API:   http://localhost:8000"
    green "  Docs:  http://localhost:8000/docs"
    echo
    cyan  "  Customer login  9841000100        (code is prefilled in dev)"
    cyan  "  Worker login    9841000001-4"
    cyan  "  Admin login     admin@sajilo.com.np / ChangeMeNow123!"
}

case "${1:-up}" in
    up)
        if [ ! -f .env ]; then
            cp .env.example .env
            key=$(python -c "import secrets; print(secrets.token_urlsafe(64))")
            # In-place sed differs between GNU and BSD, so write a new file.
            sed "s|^SECRET_KEY=.*|SECRET_KEY=$key|" .env > .env.tmp && mv .env.tmp .env
            green "Created .env with a generated SECRET_KEY."
        fi
        docker compose up -d --build
        docker compose exec -T api alembic upgrade head
        seed_all
        show_urls
        ;;
    down)    docker compose down ;;
    migrate) docker compose exec -T api alembic upgrade head ;;
    seed)    seed_all ;;
    test)
        # Idempotent: this fails harmlessly when the database already exists.
        docker compose exec -T postgres psql -U sajilo -d postgres \
            -c "CREATE DATABASE sajilo_test" >/dev/null 2>&1 || true
        docker compose exec -T "${TEST_ENV[@]}" api pytest -q
        docker compose exec -T web npx vitest run
        ;;
    lint)
        docker compose exec -T api ruff check .
        docker compose exec -T api ruff format --check .
        docker compose exec -T web npx tsc --noEmit
        ;;
    rebuild)
        # node_modules is a named volume, so it shadows whatever the image
        # ships. After adding a dependency the container keeps serving the old
        # tree and every import of the new package 500s. Dropping the volume
        # is the only thing that fixes it.
        docker compose stop web
        docker compose rm -f web
        docker volume rm sajilo_web_node_modules 2>/dev/null || true
        docker compose up -d --build web
        green "Web rebuilt with a fresh node_modules."
        ;;
    logs)  docker compose logs -f ;;
    psql)  docker compose exec postgres psql -U sajilo -d sajilo ;;
    shell) docker compose exec api bash ;;
    reset)
        docker compose down -v
        docker compose up -d --build
        docker compose exec -T api alembic upgrade head
        seed_all
        show_urls
        ;;
    *)
        sed -n '2,18p' "$0" | sed 's|^# \?||'
        exit 1
        ;;
esac
