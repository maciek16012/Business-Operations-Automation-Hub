$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example"
} else {
    Write-Host ".env already exists"
}

if (-not (Test-Path ".git")) {
    git init
    Write-Host "Initialized Git repository"
}

Write-Host "Starter prepared. Run: docker compose up -d --build"
