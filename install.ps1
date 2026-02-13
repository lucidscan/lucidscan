#Requires -Version 5.1
<#
.SYNOPSIS
    LucidShark Installer for Windows

.DESCRIPTION
    Downloads and installs LucidShark binary for Windows.

.PARAMETER Global
    Install globally to %LOCALAPPDATA%\Programs\lucidshark

.PARAMETER Local
    Install locally to current directory

.PARAMETER Version
    Specific version to install (e.g., v0.5.17)

.EXAMPLE
    irm https://raw.githubusercontent.com/lucidshark-code/lucidshark/main/install.ps1 | iex

.EXAMPLE
    .\install.ps1 -Global

.EXAMPLE
    .\install.ps1 -Version v0.5.17
#>

param(
    [switch]$Global,
    [switch]$Local,
    [string]$Version
)

$ErrorActionPreference = "Stop"

# Configuration
$Repo = "lucidshark-code/lucidshark"
$BinaryName = "lucidshark"

function Write-Info { param($Message) Write-Host $Message -ForegroundColor Cyan }
function Write-Success { param($Message) Write-Host $Message -ForegroundColor Green }
function Write-Warn { param($Message) Write-Host $Message -ForegroundColor Yellow }
function Write-Error { param($Message) Write-Host "Error: $Message" -ForegroundColor Red; exit 1 }

function Get-Architecture {
    $arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
    switch ($arch) {
        "X64" { return "amd64" }
        "Arm64" { return "arm64" }
        default { Write-Error "Unsupported architecture: $arch" }
    }
}

function Get-LatestVersion {
    $url = "https://api.github.com/repos/$Repo/releases/latest"
    try {
        $response = Invoke-RestMethod -Uri $url -Method Get -UseBasicParsing
        return $response.tag_name
    }
    catch {
        Write-Error "Failed to fetch latest version: $_"
    }
}

function Main {
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Blue
    Write-Info "       LucidShark Installer"
    Write-Host "==========================================" -ForegroundColor Blue
    Write-Host ""

    # Detect platform
    $arch = Get-Architecture
    $platform = "windows-$arch"

    Write-Info "Detected platform: $platform"
    Write-Host ""

    # Get version
    if (-not $Version) {
        Write-Info "Fetching latest version..."
        $Version = Get-LatestVersion
        if (-not $Version) {
            Write-Error "Could not determine latest version. Please specify with -Version"
        }
    }
    Write-Info "Version: $Version"
    Write-Host ""

    # Determine install location
    $installMode = ""
    if ($Global) {
        $installMode = "global"
    }
    elseif ($Local) {
        $installMode = "local"
    }
    else {
        Write-Host "Where would you like to install LucidShark?"
        Write-Host ""
        Write-Host "  [1] Global ($env:LOCALAPPDATA\Programs\lucidshark)"
        Write-Host "      - Available system-wide"
        Write-Host "      - Added to user PATH"
        Write-Host ""
        Write-Host "  [2] This project (current directory)"
        Write-Host "      - Project-specific installation"
        Write-Host "      - Binary placed in project root"
        Write-Host ""

        Write-Host -NoNewline "Choice [1/2]: "
        $choice = [Console]::ReadLine()
        Write-Host ""

        switch ($choice) {
            "1" { $installMode = "global" }
            "2" { $installMode = "local" }
            default { Write-Error "Invalid choice: $choice" }
        }
    }

    if ($installMode -eq "global") {
        $installDir = Join-Path $env:LOCALAPPDATA "Programs\lucidshark"
    }
    else {
        $installDir = Get-Location
    }

    # Create install directory
    if (-not (Test-Path $installDir)) {
        New-Item -ItemType Directory -Path $installDir -Force | Out-Null
    }

    # Construct download URL
    $binaryName = "$BinaryName-$platform.exe"
    $downloadUrl = "https://github.com/$Repo/releases/download/$Version/$binaryName"
    $installPath = Join-Path $installDir "$BinaryName.exe"

    Write-Info "Downloading $binaryName..."

    # Download binary
    try {
        $tempFile = Join-Path $env:TEMP "$BinaryName-$([guid]::NewGuid()).exe"
        Invoke-WebRequest -Uri $downloadUrl -OutFile $tempFile -UseBasicParsing
    }
    catch {
        Write-Error "Failed to download binary from: $downloadUrl`n$_"
    }

    # Install binary
    Write-Info "Installing to $installPath..."
    Move-Item -Path $tempFile -Destination $installPath -Force

    Write-Host ""
    Write-Success "Installation complete!"
    Write-Host ""

    # Verify installation
    try {
        $installedVersion = & $installPath --version 2>&1
        Write-Success "Verified: $installedVersion"
    }
    catch {
        Write-Warn "Binary installed but could not verify version"
    }

    Write-Host ""

    # Get PowerShell profile path
    $profilePath = $PROFILE.CurrentUserAllHosts
    $profileDir = Split-Path $profilePath -Parent
    $globalPath = Join-Path $env:LOCALAPPDATA "Programs\lucidshark\lucidshark.exe"

    # Ensure profile directory exists
    if (-not (Test-Path $profileDir)) {
        New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
    }

    # Check if lucidshark function already configured
    $profileExists = Test-Path $profilePath
    $alreadyConfigured = $profileExists -and (Select-String -Path $profilePath -Pattern "# LucidShark" -Quiet)

    if ($alreadyConfigured) {
        Write-Info "Shell already configured in $profilePath"
    }
    else {
        # Add function that prefers local binary over global (like venv)
        $functionCode = @"

# LucidShark - prefers local binary over global (like venv)
function lucidshark {
    if (Test-Path ".\lucidshark.exe") {
        & ".\lucidshark.exe" @args
    } elseif (Test-Path "$globalPath") {
        & "$globalPath" @args
    } else {
        Write-Host "lucidshark not found. Install with: irm https://raw.githubusercontent.com/lucidshark-code/lucidshark/main/install.ps1 | iex" -ForegroundColor Red
        return
    }
}
"@
        Add-Content -Path $profilePath -Value $functionCode
        Write-Success "Added lucidshark to $profilePath"
    }

    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Yellow
    Write-Warn "⚠️  ACTION REQUIRED"
    Write-Host "==========================================" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To use 'lucidshark' command, you must either:"
    Write-Host ""
    Write-Host "  1. Restart your terminal"
    Write-Host ""
    Write-Host "  OR"
    Write-Host ""
    Write-Host "  2. Run this command now:"
    Write-Success "     . `$PROFILE"
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Yellow
    Write-Host ""
    if ($installMode -eq "local") {
        Write-Info "Local install: 'lucidshark' will use .\lucidshark.exe in this directory"
        Write-Info "Different projects can have different versions (like Python venv)"
    }
    Write-Host ""
    Write-Host "Then run: lucidshark --help"
    Write-Host ""
}

Main
