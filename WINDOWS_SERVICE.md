# Windows Service Guide

Run the ActiveDirectoryMCP HTTP server as a native Windows service
(pywin32, python.exe-hosted) so it starts automatically with the system.

Default endpoint: `http://localhost:8813/activedirectory-mcp`
Default config: `ad-config\ad-config.json` (resolved against the project
root, never the process CWD).

## Requirements

- Windows with Administrator privileges
- Conda environment `ad-mcp` with the package installed (`pip install -e .`)
- pywin32 (installed with the package dependencies)

## Install

```powershell
# PowerShell as Administrator
.\install_service.ps1
```

Options: `-ConfigPath`, `-ServerHost`, `-Port`, `-Path`, `-StartType`,
`-CondaEnv` (see the script's comment-based help). Settings are written to
the service's ImagePath as `--env KEY="VALUE"` pairs; the service merges
them with the process environment and defaults.

## Manage

```powershell
net start ActiveDirectoryMCP     # or: Start-Service ActiveDirectoryMCP
net stop ActiveDirectoryMCP      # or: Stop-Service ActiveDirectoryMCP
Get-Service ActiveDirectoryMCP   # status
.\uninstall_service.ps1          # remove the service
```

Local debugging without the SCM (foreground, console logs):

```powershell
python -m active_directory_mcp.windows_service --debug
```

Other CLI verbs: `--start`, `--stop`, `--remove`. Without a verb the process
assumes the SCM launched it and connects to the service dispatcher.

## Logs

| File | Content |
|------|---------|
| `ad-config\mcp_service.log` | Service lifecycle + server errors with tracebacks |
| `ad-config\service_console.log` | stdout/stderr of the process: FastMCP banner, uvicorn, LDAP |

The service has no console, so stdout/stderr are redirected to
`service_console.log` at process start. When reporting bugs, check both.

## Configuration resolution (highest precedence first)

1. Explicit `--config` flag (ServiceMain args or process argv)
2. `--env AD_MCP_CONFIG=...` (written by install_service.ps1)
3. `AD_MCP_CONFIG` environment variable (manual runs)
4. Default: `<project>\ad-config\ad-config.json`

Relative paths resolve against the project root (the service CWD is
System32). Same precedence for host/port/path (`AD_MCP_HOST`, `AD_MCP_PORT`,
`AD_MCP_PATH`).

## Troubleshooting

**Service fails to start (events 7009/7000 in the System log)**
The process never registered with the SCM. Verify ImagePath ends in
`-m active_directory_mcp.windows_service` and run
`python -m active_directory_mcp.windows_service` from an admin console to
see the error.

**Service shows "Running" but the endpoint does not answer**
The server thread died or never bound. Read
`ad-config\service_console.log` for the traceback. A stale manual process
may own port 8813:

```powershell
Get-NetTCPConnection -LocalPort 8813 -State Listen
Get-CimInstance Win32_Process -Filter "ProcessId=<pid>" | Select CommandLine
```

Kill processes matching `-m active_directory_mcp.windows_service --debug`
(they are orphans, not service-managed), then restart the service.

**Stop takes ~10 seconds**
Expected: the HTTP thread is blocked inside uvicorn and the service joins it
with a 10s timeout before the process exits. The port is always released.

**Reinstall after changing code**
Code changes are picked up on service restart; reinstall only when the
ImagePath or start options change:

```powershell
.\uninstall_service.ps1
.\install_service.ps1
```
