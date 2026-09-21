<#
.SYNOPSIS
    Developer tasks for Windows PowerShell - mirrors the Makefile targets.

.EXAMPLE
    .\scripts\dev.ps1 compose-up
    .\scripts\dev.ps1 api-dev
    .\scripts\dev.ps1 help

.NOTES
    ASCII only on purpose: Windows PowerShell 5.1 misreads UTF-8 files without BOM.
    If scripts are blocked: powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 <target>
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('help', 'setup', 'api-dev', 'web-dev', 'worker-dev', 'test', 'test-api', 'test-web',
        'lint', 'lint-api', 'lint-web', 'lint-infra', 'fmt', 'migrate', 'seed',
        'compose-up', 'compose-up-all', 'compose-down', 'compose-logs', 'compose-ps', 'tf-validate')]
    [string]$Target = 'help'
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$ApiDir = Join-Path $Root 'apps\api'
$WebDir = Join-Path $Root 'apps\web'
$TfDir = Join-Path $Root 'infra\terraform'
$EnvFile = Join-Path $Root '.env'

function Invoke-Native {
    # Runs a native command and fails the script when it exits non-zero.
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory = $Root
    )
    Push-Location $WorkingDirectory
    try {
        Write-Host "> $Exe $($Arguments -join ' ')" -ForegroundColor DarkGray
        & $Exe @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "$Exe exited with code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

function Invoke-Uv {
    # uv run, with the root .env when it exists (same file docker compose uses).
    param([string[]]$Arguments)
    $uvArgs = @('run')
    if (Test-Path $EnvFile) {
        $uvArgs += @('--env-file', $EnvFile)
    }
    Invoke-Native -Exe 'uv' -Arguments ($uvArgs + $Arguments) -WorkingDirectory $ApiDir
}

function Invoke-Compose {
    param([string[]]$Arguments)
    Invoke-Native -Exe 'docker' -Arguments (@('compose') + $Arguments) -WorkingDirectory $Root
}

function Test-Command {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Invoke-Migrate {
    if (Test-Path (Join-Path $ApiDir 'alembic.ini')) {
        Invoke-Uv @('alembic', 'upgrade', 'head')
    }
    else {
        Invoke-Uv @('python', '-m', 'app.cli', 'db', 'init')
    }
}

function Invoke-LintApi {
    Invoke-Native -Exe 'uv' -Arguments @('run', 'ruff', 'check', '.') -WorkingDirectory $ApiDir
    Invoke-Native -Exe 'uv' -Arguments @('run', 'ruff', 'format', '--check', '.') -WorkingDirectory $ApiDir
    Invoke-Native -Exe 'uv' -Arguments @('run', 'mypy', 'app') -WorkingDirectory $ApiDir
}

function Invoke-LintWeb {
    Invoke-Native -Exe 'npm' -Arguments @('run', 'lint') -WorkingDirectory $WebDir
    Invoke-Native -Exe 'npm' -Arguments @('run', 'typecheck') -WorkingDirectory $WebDir
}

function Invoke-LintInfra {
    if (Test-Command 'terraform') {
        Invoke-Native -Exe 'terraform' -Arguments @('fmt', '-check', '-recursive', $TfDir)
    }
    else {
        Write-Host 'terraform not installed - skipped' -ForegroundColor Yellow
    }
}

function Invoke-TestApi {
    Invoke-Native -Exe 'uv' -Arguments @('run', '--with', 'pytest-cov', 'pytest', '--cov=app', '--cov-report=term-missing') -WorkingDirectory $ApiDir
}

function Invoke-TestWeb {
    Invoke-Native -Exe 'npm' -Arguments @('run', 'typecheck') -WorkingDirectory $WebDir
}

function Show-Help {
    @'
Usage: .\scripts\dev.ps1 <target>

  setup            Install api + web dependencies and create .env
  api-dev          FastAPI with auto reload on :8000 (needs compose-up)
  web-dev          Next.js dev server on :3000
  worker-dev       Celery worker on the host
  test             Run all tests (test-api + test-web)
  lint             Lint everything (lint-api + lint-web + lint-infra)
  fmt              Auto-format python and terraform
  migrate          Create / upgrade the local schema
  seed             Load scoring config + file-based seed places
  compose-up       Start postgres, redis, elasticsearch
  compose-up-all   Start everything incl. api, worker, beat, web (builds images)
  compose-down     Stop all containers (volumes are kept)
  compose-logs     Follow container logs
  compose-ps       Container status
  tf-validate      terraform validate for every stack (no backend, no credentials)
'@ | Write-Host
}

switch ($Target) {
    'help' { Show-Help }

    'setup' {
        if (-not (Test-Path $EnvFile)) {
            Copy-Item (Join-Path $Root '.env.example') $EnvFile
            Write-Host 'created .env from .env.example'
        }
        Invoke-Native -Exe 'uv' -Arguments @('sync') -WorkingDirectory $ApiDir
        Invoke-Native -Exe 'npm' -Arguments @('ci') -WorkingDirectory $WebDir
    }

    'api-dev' { Invoke-Uv @('uvicorn', 'app.main:app', '--reload', '--host', '0.0.0.0', '--port', '8000') }
    'web-dev' { Invoke-Native -Exe 'npm' -Arguments @('run', 'dev') -WorkingDirectory $WebDir }
    # Celery's prefork pool does not work on Windows -> solo pool.
    'worker-dev' { Invoke-Uv @('celery', '-A', 'app.workers.celery_app', 'worker', '--loglevel=INFO', '--pool=solo') }

    'test' { Invoke-TestApi; Invoke-TestWeb }
    'test-api' { Invoke-TestApi }
    'test-web' { Invoke-TestWeb }

    'lint' { Invoke-LintApi; Invoke-LintWeb; Invoke-LintInfra }
    'lint-api' { Invoke-LintApi }
    'lint-web' { Invoke-LintWeb }
    'lint-infra' { Invoke-LintInfra }

    'fmt' {
        Invoke-Native -Exe 'uv' -Arguments @('run', 'ruff', 'check', '--fix', '.') -WorkingDirectory $ApiDir
        Invoke-Native -Exe 'uv' -Arguments @('run', 'ruff', 'format', '.') -WorkingDirectory $ApiDir
        if (Test-Command 'terraform') {
            Invoke-Native -Exe 'terraform' -Arguments @('fmt', '-recursive', $TfDir)
        }
    }

    'migrate' { Invoke-Migrate }

    'seed' {
        Invoke-Migrate
        Invoke-Uv @('python', '-m', 'app.cli', 'seed-config')
        Invoke-Uv @('python', '-m', 'app.cli', 'ingest', '--provider', 'file', '--all')
    }

    'compose-up' { Invoke-Compose @('up', '-d', '--wait', 'postgres', 'redis', 'elasticsearch') }
    'compose-up-all' { Invoke-Compose @('--profile', 'app', 'up', '-d', '--build') }
    'compose-down' { Invoke-Compose @('--profile', 'app', 'down') }
    'compose-logs' { Invoke-Compose @('--profile', 'app', 'logs', '-f', '--tail=100') }
    'compose-ps' { Invoke-Compose @('--profile', 'app', 'ps') }

    'tf-validate' {
        foreach ($stack in @('bootstrap', 'envs\shared', 'envs\staging', 'envs\prod')) {
            $dir = Join-Path $TfDir $stack
            Write-Host "== $stack"
            Invoke-Native -Exe 'terraform' -Arguments @('init', '-backend=false', '-input=false') -WorkingDirectory $dir
            Invoke-Native -Exe 'terraform' -Arguments @('validate') -WorkingDirectory $dir
        }
    }
}
