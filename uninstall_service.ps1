<#
.SYNOPSIS
    Uninstalls the Active Directory MCP server Windows service.

.DESCRIPTION
    This script stops and removes the ActiveDirectoryMCP Windows service.

.PARAMETER CondaEnv
    Conda environment to use for removal.
    Default: ad-mcp

.EXAMPLE
    .\uninstall_service.ps1
    Uninstalls the service.

.NOTES
    Requires Administrator privileges.
#>

param(
    [string]$CondaEnv = "ad-mcp"
)

$ErrorActionPreference = "Stop"

$serviceName = "ActiveDirectoryMCP"

Write-Host "=== Active Directory MCP Windows Service Uninstaller ===" -ForegroundColor Cyan
Write-Host "Conda environment:   $CondaEnv" -ForegroundColor White
Write-Host ""

# Check for Administrator privileges
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "ERROR: This script must be run as Administrator." -ForegroundColor Red
    Write-Host "Right-click PowerShell and select 'Run as Administrator'." -ForegroundColor Yellow
    exit 1
}

# Find the Python executable in the specified conda environment
$condaExe = Get-Command conda -ErrorAction SilentlyContinue
if (-not $condaExe) {
    Write-Host "ERROR: conda not found in PATH." -ForegroundColor Red
    exit 1
}

$envPrefix = & conda info --envs | Where-Object { $_ -match "^$CondaEnv\s" } | ForEach-Object { $_.Split()[-1] }

if (-not $envPrefix) {
    Write-Host "ERROR: Conda environment '$CondaEnv' not found." -ForegroundColor Red
    exit 1
}

$pythonExePath = Join-Path $envPrefix "python.exe"
if (-not (Test-Path $pythonExePath)) {
    Write-Host "ERROR: Python not found at $pythonExePath" -ForegroundColor Red
    exit 1
}

Write-Host "Python executable:   $pythonExePath" -ForegroundColor Green
Write-Host ""

# Check if service exists
$service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if (-not $service) {
    Write-Host "Service '$serviceName' is not installed." -ForegroundColor Yellow
    exit 0
}

Write-Host "Service found: $serviceName" -ForegroundColor White
Write-Host "Status:        $($service.Status)" -ForegroundColor White
Write-Host ""

# Stop the service if running
if ($service.Status -ne "Stopped") {
    Write-Host "Stopping service..." -ForegroundColor Yellow
    try {
        Stop-Service -Name $serviceName -Force
        Start-Sleep -Seconds 2
        Write-Host "Service stopped." -ForegroundColor Green
    } catch {
        Write-Host "WARNING: Could not stop service. It may be in a stuck state." -ForegroundColor Yellow
    }
}

# Remove the service
Write-Host "Removing service..." -ForegroundColor Cyan
try {
    $uninstallScript = @"
from active_directory_mcp.windows_service import unregister
unregister()
print('Service removed successfully.')
"@
    & $pythonExePath -c "$uninstallScript" 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed"
    }
} catch {
    Write-Host "Trying native removal..." -ForegroundColor Yellow
    & sc.exe delete $serviceName 2>&1
}

Write-Host ""
Write-Host "=== Uninstallation Complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Service '$serviceName' has been removed." -ForegroundColor Green
Write-Host ""
