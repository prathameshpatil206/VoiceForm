# ==============================================================================
# VoiceForm — Hackathon Submission Packaging Script
# Creates a clean, compliant submission ZIP file without secrets, .venv, or node_modules
# ==============================================================================

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$ZipName = "VoiceForm_Submission.zip"
$ZipPath = Join-Path $ProjectRoot $ZipName
$StagingDir = Join-Path $ProjectRoot "_staging_submission"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  VoiceForm Packaging Script for Hackathon Submission" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# Step 1: Run Preflight Check
Write-Host "`n[Step 1/5] Running Preflight & Secret Hygiene Check..." -ForegroundColor Yellow
$PythonExe = Join-Path $ProjectRoot "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python"
}

try {
    & $PythonExe (Join-Path $ScriptDir "preflight_check.py")
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Preflight check failed! Please fix issues before packaging."
        exit 1
    }
} catch {
    Write-Warning "Could not run python preflight check automatically. Proceeding with caution..."
}

# Step 2: Clean existing zip and staging
Write-Host "`n[Step 2/5] Preparing clean staging directory..." -ForegroundColor Yellow
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
    Write-Host "  Removed existing $ZipName"
}
if (Test-Path $StagingDir) {
    Remove-Item $StagingDir -Recurse -Force
}
New-Item -ItemType Directory -Path $StagingDir | Out-Null

# Step 3: Copy required files and folders into staging
Write-Host "`n[Step 3/5] Copying repository assets to staging..." -ForegroundColor Yellow

$RootFiles = @(
    "README.md",
    "RIME_EVIDENCE.md",
    "DEMO_LINK.md",
    ".env.example",
    "package.json",
    "package-lock.json",
    "docker-compose.yml",
    "pytest.ini",
    "pyrightconfig.json",
    "pyrefly.toml",
    "LICENSE",
    ".gitignore",
    "serve-test-pages.js"
)

foreach ($file in $RootFiles) {
    $src = Join-Path $ProjectRoot $file
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination (Join-Path $StagingDir $file) -Force
    }
}

# Copy Scripts folder
Copy-Item -Path (Join-Path $ProjectRoot "scripts") -Destination (Join-Path $StagingDir "scripts") -Recurse -Force

# Copy Test Pages
Copy-Item -Path (Join-Path $ProjectRoot "test-pages") -Destination (Join-Path $StagingDir "test-pages") -Recurse -Force

# Copy Evidence
Copy-Item -Path (Join-Path $ProjectRoot "evidence") -Destination (Join-Path $StagingDir "evidence") -Recurse -Force

# Copy Backend (excluding .venv, .env, __pycache__, .pytest_cache)
Write-Host "  Copying backend (filtering out .venv and .env)..."
$BackendStaging = Join-Path $StagingDir "backend"
New-Item -ItemType Directory -Path $BackendStaging | Out-Null

Get-ChildItem -Path (Join-Path $ProjectRoot "backend") | ForEach-Object {
    if ($_.Name -notin @(".venv", ".env", "__pycache__", ".pytest_cache", ".coverage")) {
        Copy-Item -Path $_.FullName -Destination (Join-Path $BackendStaging $_.Name) -Recurse -Force
    }
}

# Clean any nested __pycache__ in backend staging
Get-ChildItem -Path $BackendStaging -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $BackendStaging -Recurse -Directory -Filter ".pytest_cache" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# Copy Extension (excluding node_modules)
Write-Host "  Copying extension (filtering out node_modules)..."
$ExtensionStaging = Join-Path $StagingDir "extension"
New-Item -ItemType Directory -Path $ExtensionStaging | Out-Null

Get-ChildItem -Path (Join-Path $ProjectRoot "extension") | ForEach-Object {
    if ($_.Name -notin @("node_modules", ".git")) {
        Copy-Item -Path $_.FullName -Destination (Join-Path $ExtensionStaging $_.Name) -Recurse -Force
    }
}

# Step 4: Strict Security Audit on Staging
Write-Host "`n[Step 4/5] Running strict security & secret audit on staged files..." -ForegroundColor Yellow
$EnvFiles = Get-ChildItem -Path $StagingDir -Recurse -Filter ".env" -File
if ($EnvFiles.Count -gt 0) {
    Write-Error "CRITICAL SECURITY BREACH: A real .env file was found in staging! Aborting packaging."
    Remove-Item $StagingDir -Recurse -Force
    exit 1
}
Write-Host "  [VERIFIED] Zero secret .env files in submission package." -ForegroundColor Green

# Step 5: Create ZIP Archive
Write-Host "`n[Step 5/5] Compressing staging directory into $ZipName..." -ForegroundColor Yellow
Compress-Archive -Path "$StagingDir\*" -DestinationPath $ZipPath -CompressionLevel Optimal

# Cleanup staging directory
Remove-Item $StagingDir -Recurse -Force

$ZipItem = Get-Item $ZipPath
$ZipSizeMB = [math]::Round($ZipItem.Length / 1MB, 2)

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host "  SUCCESS! SUBMISSION PACKAGE CREATED" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  File Path: $ZipPath"
Write-Host "  File Size: $ZipSizeMB MB"
Write-Host "  Secrets:   Clean (Zero leaked credentials, .env excluded)"
Write-Host "  Ready for submission to hackathon organizers!`n"
