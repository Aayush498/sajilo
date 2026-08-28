<#
.SYNOPSIS
    Sajilo local development helper.

.EXAMPLE
    .\dev.ps1 up          # build and start the whole stack, migrate and seed
    .\dev.ps1 migrate     # apply migrations
    .\dev.ps1 seed        # admin + catalog + demo workers
    .\dev.ps1 test        # run the test suite
    .\dev.ps1 lint        # ruff check + format, and tsc on the web app
    .\dev.ps1 rebuild     # rebuild the web app after adding a dependency
    .\dev.ps1 logs        # follow all logs (OTP codes appear here)
    .\dev.ps1 psql        # open a psql shell
    .\dev.ps1 down        # stop everything
    .\dev.ps1 reset       # destroy volumes and rebuild from scratch
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet("up", "down", "migrate", "seed", "test", "lint", "logs", "psql", "reset", "shell", "rebuild")]
    [string]$Command = "up"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Tests run against a separate database and Redis DB 15 so they never touch dev data.
$testEnv = @(
    "-e", "POSTGRES_DB=sajilo_test",
    "-e", "REDIS_URL=redis://redis:6379/15",
    "-e", "ENVIRONMENT=test"
)

function Invoke-Seed {
    docker compose exec -T api python -m app.cli seed-admin
    docker compose exec -T api python -m app.cli seed-catalog
    docker compose exec -T api python -m app.cli seed-demo
}

function Show-Urls {
    Write-Host ""
    Write-Host "  Web:   http://localhost:3000" -ForegroundColor Green
    Write-Host "  API:   http://localhost:8000" -ForegroundColor Green
    Write-Host "  Docs:  http://localhost:8000/docs" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Customer login  9841000100        (code is prefilled in dev)" -ForegroundColor Cyan
    Write-Host "  Worker login    9841000001-4" -ForegroundColor Cyan
    Write-Host "  Admin login     admin@sajilo.com.np / ChangeMeNow123!" -ForegroundColor Cyan
}

switch ($Command) {
    "up" {
        if (-not (Test-Path .env)) {
            Copy-Item .env.example .env
            $key = python -c "import secrets; print(secrets.token_urlsafe(64))"
            (Get-Content .env) -replace '^SECRET_KEY=.*', "SECRET_KEY=$key" | Set-Content .env
            Write-Host "Created .env with a generated SECRET_KEY." -ForegroundColor Green
        }
        docker compose up -d --build
        docker compose exec -T api alembic upgrade head
        Invoke-Seed
        Show-Urls
    }
    "down" { docker compose down }
    "migrate" { docker compose exec -T api alembic upgrade head }
    "seed" { Invoke-Seed }
    "test" {
        # Idempotent: CREATE DATABASE fails harmlessly if it already exists.
        docker compose exec -T postgres psql -U sajilo -d postgres -c "CREATE DATABASE sajilo_test" 2>&1 | Out-Null
        docker compose exec -T @testEnv api pytest -q
        docker compose exec -T web npx vitest run
    }
    "rebuild" {
        # node_modules is a named volume, so it shadows whatever the image
        # ships. After adding a dependency the container keeps serving the old
        # tree and every import of the new package 500s. Dropping the volume
        # is the only thing that fixes it.
        docker compose stop web
        docker compose rm -f web
        docker volume rm sajilo_web_node_modules 2>&1 | Out-Null
        docker compose up -d --build web
        Write-Host "Web rebuilt with a fresh node_modules." -ForegroundColor Green
    }
    "lint" {
        docker compose exec -T api ruff check .
        docker compose exec -T api ruff format --check .
        docker compose exec -T web npx tsc --noEmit
    }
    "logs" { docker compose logs -f }
    "psql" { docker compose exec postgres psql -U sajilo -d sajilo }
    "shell" { docker compose exec api bash }
    "reset" {
        docker compose down -v
        docker compose up -d --build
        docker compose exec -T api alembic upgrade head
        Invoke-Seed
        Show-Urls
    }
}
