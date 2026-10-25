<#
.SYNOPSIS
    Installs the Active Directory MCP server as a Windows service.

.DESCRIPTION
    This script installs the ActiveDirectoryMCP HTTP server as a Windows
    service configured to start automatically with the system.

    The service runs the MCP server on port 8813 and logs
    to ad-config/mcp_service.log.

.PARAMETER ConfigPath
    Path to the Active Directory configuration file (relative to project root).
    Default: ad-config\ad-config.json

.PARAMETER Host
    Host address for the MCP server.
    Default: 0.0.0.0

.PARAMETER Port
    Port for the MCP server.
    Default: 8813

.PARAMETER Path
    HTTP path for the MCP endpoint.
    Default: /activedirectory-mcp

.PARAMETER StartType
    Service start type: Automatic, Manual, or Disabled.
    Default: Automatic

.PARAMETER CondaEnv
    Conda environment to use.
    Default: ad-mcp

.EXAMPLE
    .\install_service.ps1
    Installs with defaults.

.EXAMPLE
    .\install_service.ps1 -Port 9000
    Installs with custom port.

.NOTES
    Requires Administrator privileges.
    Run PowerShell as Administrator before executing.
#>

param(
    [string]$ConfigPath = "ad-config\ad-config.json",
    [string]$ServerHost = "0.0.0.0",
    [int]$Port = 8813,
    [string]$Path = "/activedirectory-mcp",
    [ValidateSet("Automatic", "Manual", "Disabled")]
    [string]$StartType = "Automatic",
    [string]$CondaEnv = "ad-mcp"
)

$ErrorActionPreference = "Stop"

# Resolve script directory as base path
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$baseDir = (Get-Item $scriptDir).FullName

Write-Host "=== Active Directory MCP Windows Service Installer ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Base directory:      $baseDir" -ForegroundColor White
Write-Host "Conda environment:   $CondaEnv" -ForegroundColor White
Write-Host "Config path:         $ConfigPath" -ForegroundColor White
Write-Host "Host:                $ServerHost" -ForegroundColor White
Write-Host "Port:                $Port" -ForegroundColor White
Write-Host "Path:                $Path" -ForegroundColor White
Write-Host "Start type:          $StartType" -ForegroundColor White
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

# Get the environment prefix
Write-Host "Checking conda environment '$CondaEnv'..." -ForegroundColor Yellow
$envPrefix = & conda info --envs | Where-Object { $_ -match "^$CondaEnv\s" } | ForEach-Object { $_.Split()[-1] }

if (-not $envPrefix) {
    Write-Host "ERROR: Conda environment '$CondaEnv' not found." -ForegroundColor Red
    Write-Host "Available environments:" -ForegroundColor Yellow
    conda info --envs
    exit 1
}

$pythonExePath = Join-Path $envPrefix "python.exe"
if (-not (Test-Path $pythonExePath)) {
    Write-Host "ERROR: Python not found at $pythonExePath" -ForegroundColor Red
    exit 1
}

Write-Host "Conda env prefix:    $envPrefix" -ForegroundColor Green
Write-Host "Python executable:   $pythonExePath" -ForegroundColor Green

# Verify the environment has the required packages
Write-Host "Verifying packages in '$CondaEnv' environment..." -ForegroundColor Yellow
$verifyResult = & $pythonExePath -c "import win32service, active_directory_mcp; print('All packages OK')" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Required packages not found in '$CondaEnv' environment." -ForegroundColor Red
    Write-Host $verifyResult -ForegroundColor Red
    Write-Host "Install with: conda activate $CondaEnv && pip install -e ." -ForegroundColor Yellow
    exit 1
}
Write-Host "Packages verified:   OK" -ForegroundColor Green

# Check if the service already exists
$serviceName = "ActiveDirectoryMCP"
$existingService = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($existingService) {
    Write-Host ""
    Write-Host "WARNING: Service '$serviceName' already exists." -ForegroundColor Yellow
    Write-Host "Status:            $($existingService.Status)" -ForegroundColor White
    $overwrite = Read-Host "Reinstall? (y/n)"
    if ($overwrite -ne "y") {
        Write-Host "Installation cancelled." -ForegroundColor Yellow
        exit 0
    }
    Write-Host "Stopping existing service..." -ForegroundColor Yellow
    Stop-Service -Name $serviceName -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

Write-Host ""
Write-Host "Installing service '$serviceName'..." -ForegroundColor Cyan

# Install the service using New-Service
Write-Host "Creating service with New-Service..." -ForegroundColor Cyan

# Transport for settings: --env flags appended to ImagePath (below).
# LocalSystem does not inherit this shell's environment, so setting $env:*
# here would have no effect on the service - the ImagePath is the only
# channel the service process actually reads (besides the defaults).
$binPath = "`"$pythonExePath`" -m active_directory_mcp.windows_service"

try {
    New-Service -Name $serviceName `
        -BinaryPathName $binPath `
        -StartupType $StartType `
        -DisplayName "Active Directory MCP Server" `
        -Description "Active Directory MCP HTTP server providing LDAP-based Active Directory management tools via Model Context Protocol." `
        -ErrorAction Stop
    Write-Host "Service installed successfully." -ForegroundColor Green
} catch {
    Write-Host "ERROR: Service creation failed: $_" -ForegroundColor Red
    exit 1
}

# Set environment variables in the service registry key
$serviceKey = "HKLM:\SYSTEM\CurrentControlSet\Services\$serviceName"
if (Test-Path $serviceKey) {
    $envBlock = @{
        "AD_MCP_CONFIG" = Join-Path $baseDir $ConfigPath
        "AD_MCP_HOST" = $ServerHost
        "AD_MCP_PORT" = $Port
        "AD_MCP_PATH" = $Path
    }
    
    # Write environment variables to the service's ImagePath with --env flags
    $envArgs = ($envBlock.GetEnumerator() | ForEach-Object { 
        "--env $($_.Name)=`"$($_.Value)`"" 
    }) -join " "
    
    $newImagePath = "$binPath $envArgs"
    Set-ItemProperty -Path $serviceKey -Name "ImagePath" -Value $newImagePath
    Write-Host "Environment variables configured for service." -ForegroundColor Green
}

Write-Host ""
Write-Host "Starting service..." -ForegroundColor Cyan
try {
    Start-Service -Name $serviceName
    Write-Host "Service started successfully." -ForegroundColor Green
} catch {
    Write-Host "WARNING: Could not start service automatically." -ForegroundColor Yellow
    Write-Host "Start manually with: net start $serviceName" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Installation Complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Service name:        $serviceName" -ForegroundColor White
Write-Host "Display name:        Active Directory MCP Server" -ForegroundColor White
Write-Host "Start type:          $StartType" -ForegroundColor White
Write-Host "Conda environment:   $CondaEnv ($envPrefix)" -ForegroundColor White
Write-Host "Python executable:   $pythonExePath" -ForegroundColor White
Write-Host "Endpoint:            http://$ServerHost`:$Port$Path" -ForegroundColor White
Write-Host "Config file:         $(Join-Path $baseDir $ConfigPath)" -ForegroundColor White
Write-Host ""
Write-Host "Useful commands:" -ForegroundColor Cyan
Write-Host "  Stop:              net stop $serviceName" -ForegroundColor White
Write-Host "  Start:             net start $serviceName" -ForegroundColor White
Write-Host "  Logs:              Get-Content ad-config\mcp_service.log -Tail 50 -Wait" -ForegroundColor White
Write-Host "  Uninstall:         .\uninstall_service.ps1" -ForegroundColor White
Write-Host ""
