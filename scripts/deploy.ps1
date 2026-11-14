<#
.SYNOPSIS
    Prepares the SACCO app for deployment: builds frontend, collects static,
    runs migrations, and optionally creates a superuser.

.DESCRIPTION
    Run this script before deploying to Railway, a VPS, or any platform.
    It assumes you are in the project root and have:
      - Python 3.11+ with the venv activated
      - Node.js 18+ installed
      - .env file configured with production values

.PARAMETER CreateSuperuser
    If provided, creates a superuser after deployment prep.
    Requires SUPERUSER_USERNAME, SUPERUSER_PASSWORD (and optionally SUPERUSER_EMAIL)
    environment variables to be set.

.EXAMPLE
    .\scripts\deploy.ps1
    .\scripts\deploy.ps1 -CreateSuperuser
#>

param(
    [switch]$CreateSuperuser
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  SACCO App — Deployment Preparation" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Step 1: Check prerequisites
Write-Host "`n[1/6] Checking prerequisites..." -ForegroundColor Yellow

if (-not (Test-Path ".env")) {
    Write-Host "  ERROR: .env file not found. Copy .env.example to .env and fill in your values." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path "venv\Scripts\Activate.ps1")) {
    Write-Host "  ERROR: venv not found. Run: python -m venv venv" -ForegroundColor Red
    exit 1
}

Write-Host "  .env found." -ForegroundColor Green
Write-Host "  venv found." -ForegroundColor Green

# Step 2: Install Python dependencies
Write-Host "`n[2/6] Installing Python dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) { Write-Host "  FAILED" -ForegroundColor Red; exit 1 }
Write-Host "  Done." -ForegroundColor Green

# Step 3: Build React frontend
Write-Host "`n[3/6] Building React frontend..." -ForegroundColor Yellow
Push-Location frontend
npm install --legacy-peer-deps --silent 2>$null
npm run build 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "  FAILED" -ForegroundColor Red; Pop-Location; exit 1 }
Write-Host "  Frontend built to frontend/build/" -ForegroundColor Green
Pop-Location

# Step 4: Collect static files
Write-Host "`n[4/6] Collecting static files..." -ForegroundColor Yellow
python manage.py collectstatic --noinput 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "  FAILED" -ForegroundColor Red; exit 1 }
Write-Host "  Done." -ForegroundColor Green

# Step 5: Run migrations
Write-Host "`n[5/6] Running database migrations..." -ForegroundColor Yellow
python manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { Write-Host "  FAILED" -ForegroundColor Red; exit 1 }
Write-Host "  Done." -ForegroundColor Green

# Step 6: Django system check
Write-Host "`n[6/6] Running Django system check..." -ForegroundColor Yellow
python manage.py check
if ($LASTEXITCODE -ne 0) { Write-Host "  WARNINGS DETECTED — review before deploying." -ForegroundColor Yellow }

# Optional: Create superuser
if ($CreateSuperuser) {
    Write-Host "`n[Optional] Creating superuser..." -ForegroundColor Yellow
    $suUser = $env:SUPERUSER_USERNAME
    $suPass = $env:SUPERUSER_PASSWORD
    $suEmail = $env:SUPERUSER_EMAIL

    if (-not $suUser) { Write-Host "  Set `$env:SUPERUSER_USERNAME first." -ForegroundColor Red; exit 1 }
    if (-not $suPass) { Write-Host "  Set `$env:SUPERUSER_PASSWORD first." -ForegroundColor Red; exit 1 }

    python manage.py shell -c "exec(open('scripts/create_superuser.py').read())"
    if ($LASTEXITCODE -ne 0) { Write-Host "  FAILED — check SUPERUSER_SECRET in .env" -ForegroundColor Red; exit 1 }
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Deployment prep complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "`nNext steps:" -ForegroundColor White
Write-Host "  1. Push to GitHub:  git add -A; git commit -m 'deploy prep'; git push" -ForegroundColor White
Write-Host "  2. On Railway:      Connect repo, add PostgreSQL, set env vars, deploy" -ForegroundColor White
Write-Host "  3. Or on VPS:       Run with gunicorn behind nginx" -ForegroundColor White
Write-Host "  4. Create superuser: $env:SUPERUSER_PASSWORD='...'; .\scripts\deploy.ps1 -CreateSuperuser" -ForegroundColor White
Write-Host ""
