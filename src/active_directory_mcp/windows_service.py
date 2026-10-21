"""
Windows service wrapper for the Active Directory MCP HTTP server.

Native pywin32 hosting (python.exe + servicemanager), following the official
win32/Demos/service/nativePipeTestService.py pattern:

* SCM launch (no CLI verbs in argv) -> servicemanager.Initialize() +
  PrepareToHostSingle() + StartServiceCtrlDispatcher(). Without this call the
  process never registers with the SCM and every start fails (event 7009).
* CLI verbs (--debug/--start/...) -> local tooling, never SCM.

Install/uninstall with install_service.ps1 / uninstall_service.ps1.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional, Sequence

import servicemanager
import win32service
import win32serviceutil

# <root>/src/active_directory_mcp/windows_service.py -> parents[2] == <root>
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "ad-config" / "ad-config.json"
DEFAULT_LOG_FILE = PROJECT_ROOT / "ad-config" / "mcp_service.log"

# If argv[1:] contains one of these tokens the process was launched by a
# human, not by the SCM (which only passes the service start arguments).
_CLI_VERBS = frozenset(
    {
        "--install", "--remove", "--start", "--stop", "--debug", "--help", "-h",
        "install", "remove", "start", "stop", "restart", "debug", "help",
    }
)

_USAGE = """Usage:
  python -m active_directory_mcp.windows_service            (started by the SCM)
  python -m active_directory_mcp.windows_service --debug    (run locally)
  python -m active_directory_mcp.windows_service --start|--stop|--remove
Install or uninstall with install_service.ps1 (run PowerShell as Administrator).
"""


def parse_env_args(args: Sequence[str]) -> dict[str, str]:
    """Parse ``--env KEY=VALUE`` (installer form) and ``--env=KEY=VALUE``.

    install_service.ps1 writes the space form; the historical parser only
    accepted the equals form, so every installer override was silently lost.
    """
    env: dict[str, str] = {}
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--env" and i + 1 < len(args):
            kv, i = args[i + 1], i + 2
        elif arg.startswith("--env="):
            kv, i = arg[6:], i + 1
        else:
            i += 1
            continue
        if "=" in kv:
            key, value = kv.split("=", 1)
            env[key] = value
    return env


def _flag(args: Sequence[str], flag: str) -> Optional[str]:
    """Return the value following ``flag`` in ``args``, if present."""
    for i, arg in enumerate(args):
        if arg == flag and i + 1 < len(args):
            return args[i + 1]
    return None


def resolve_config_path(config_path: Optional[str] = None) -> str:
    """Resolve the config path to an absolute file path.

    Relative paths anchor at PROJECT_ROOT because a Windows service starts in
    System32, where ``ad-config/...`` raises FileNotFoundError.
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return str(path)


def is_service_mode(argv: Sequence[str]) -> bool:
    """True when the SCM launched the process (no CLI verb in argv[1:])."""
    return not any(arg.lower() in _CLI_VERBS for arg in argv[1:])


def _redirect_stdio_to_service_log() -> None:
    """Service processes have no usable console: send stdout/stderr to a file.

    server_http/FastMCP/uvicorn all write to stdio; the SCM gives services
    invalid handles, so those writes raise OSError and kill the server thread
    while the service stays 'Running' with no listener. The redirect happens
    before any server code loads, so every third-party log and traceback ends
    up in ad-config/service_console.log.
    """
    log_path = PROJECT_ROOT / "ad-config" / "service_console.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stream = open(log_path, "a", encoding="utf-8", errors="replace")
    sys.stdout = stream
    sys.stderr = stream


class ADWindowsService(win32serviceutil.ServiceFramework):
    """
    Windows service for Active Directory MCP HTTP server.

    Runs the MCP HTTP server as a Windows service so it starts
    automatically with the system and doesn't require manual console launch.
    """

    _svc_name_ = "ActiveDirectoryMCP"
    _svc_display_name_ = "Active Directory MCP Server"
    _svc_description_ = (
        "Active Directory MCP HTTP server providing LDAP-based "
        "Active Directory management tools via Model Context Protocol."
    )

    serviceName = _svc_name_
    DisplayName = _svc_display_name_
    description = _svc_description_

    def __init__(self, args=None, config_path=None, host=None, port=None,
                 path=None, log_file=None):
        """Initialize the Windows service.

        Sources for every setting (highest precedence first): explicit
        keyword > --flag in ServiceMain args/process argv > --env KEY=VALUE >
        process environment > default.
        """
        argv = list(sys.argv[1:])
        extra = list(args) if args else []
        env_kv = parse_env_args(argv)
        env_kv.update(parse_env_args(extra))

        if config_path is None:
            config_path = (
                _flag(extra, "--config") or _flag(argv, "--config")
                or env_kv.get("AD_MCP_CONFIG") or os.getenv("AD_MCP_CONFIG")
            )
        if host is None:
            host = (
                _flag(extra, "--host") or _flag(argv, "--host")
                or env_kv.get("AD_MCP_HOST") or os.getenv("AD_MCP_HOST")
                or "0.0.0.0"
            )
        if port is None:
            port_str = (
                _flag(extra, "--port") or _flag(argv, "--port")
                or env_kv.get("AD_MCP_PORT") or os.getenv("AD_MCP_PORT")
            )
            port = int(port_str) if port_str else 8813
        if path is None:
            path = (
                _flag(extra, "--path") or _flag(argv, "--path")
                or env_kv.get("AD_MCP_PATH") or os.getenv("AD_MCP_PATH")
                or "/activedirectory-mcp"
            )

        self.config_path = resolve_config_path(config_path)
        self.host = str(host)
        self.port = int(port)
        self.path = str(path)
        self.log_file = str(log_file) if log_file else str(DEFAULT_LOG_FILE)

        self.stop_event = threading.Event()
        self.server_thread = None
        self.server_instance = None

        # Parent __init__ registers the SCM control handler; outside the SCM
        # (tests, --debug) that registration can fail -> run without handler.
        try:
            win32serviceutil.ServiceFramework.__init__(
                self, extra if extra else [self._svc_name_]
            )
        except ValueError:
            self.ssh = None

        self._setup_logging()
        self.logger.info("Service initialized with config_path=%s", self.config_path)

    def _setup_logging(self) -> None:
        """Configure logging to file (idempotent: one handler per target file)."""
        log_path = Path(self.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger("ActiveDirectoryMCP-Service")
        self.logger.setLevel(logging.INFO)

        expected = str(log_path)
        has_handler = any(
            isinstance(handler, logging.FileHandler)
            and getattr(handler, "baseFilename", None) == expected
            for handler in self.logger.handlers
        )
        if not has_handler:
            file_handler = logging.FileHandler(expected)
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
            )
            self.logger.addHandler(file_handler)

    def SvcDoRun(self):
        """Called by the framework's SvcRun (which already reported RUNNING)."""
        self.logger.info("Service starting...")
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )

        self.server_thread = threading.Thread(
            target=self._run_http_server,
            name="MCP-HTTP-Server",
            daemon=True,
        )
        self.server_thread.start()

        self.stop_event.wait()
        self.logger.info("Service stopping...")

    def SvcStop(self):
        """Called when service is stopped."""
        self.logger.info("SvcStop called, signaling shutdown...")
        # Safe outside the SCM too: framework no-ops when ssh is None.
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)

        self.stop_event.set()

        if self.server_instance:
            self.server_instance._shutdown()

        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=10)

        self.logger.info("Service stopped.")

    def SvcPause(self):
        """Called when service is paused."""
        self.logger.info("SvcPause called (not implemented, service continues).")

    def SvcContinue(self):
        """Called when service is resumed from pause."""
        self.logger.info("SvcContinue called (not implemented, service was running).")

    def SvcGetStatus(self):
        """Called to get service status."""
        return win32service.SERVICE_RUNNING

    def _run_http_server(self):
        """Run the HTTP MCP server in a thread (self-healing: never dies silently).

        A Windows service shows no console: any exception escaping here (or a
        sys.exit inside server code) would kill the thread and leave the
        service 'Running' with no listener. Everything is logged to the
        service log and transient failures are retried.
        """
        while not self.stop_event.is_set():
            try:
                # Absolute import: works both as `-m` and as a direct script run
                # (relative imports require package context a direct run lacks).
                from active_directory_mcp.server_http import ActiveDirectoryMCPHTTPServer

                if self.server_instance is None:
                    self.server_instance = ActiveDirectoryMCPHTTPServer(
                        config_path=self.config_path,
                        host=self.host,
                        port=self.port,
                        path=self.path,
                    )
                    self.logger.info(
                        "HTTP server starting on %s:%s%s",
                        self.host, self.port, self.path,
                    )

                self.server_instance.run(setup_signals=False)

                if not self.stop_event.is_set():
                    self.logger.warning(
                        "HTTP server exited unexpectedly; restarting in 2s"
                    )
            except BaseException as exc:
                # BaseException on purpose: server_http.run() calls sys.exit(1)
                # on failure, which would otherwise kill this thread silently.
                self.logger.error("HTTP server error: %s", exc, exc_info=True)
                if self.stop_event.is_set():
                    break
            if not self.stop_event.is_set():
                time.sleep(2)


def unregister():
    """Unregister the service from Windows SCM (used by uninstall_service.ps1)."""
    win32serviceutil.RemoveService(ADWindowsService.serviceName)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point for both the SCM and human CLI invocations."""
    argv = list(sys.argv if argv is None else argv)

    if is_service_mode(argv):
        # Must be first: gives the server code a working stdio under the SCM.
        _redirect_stdio_to_service_log()
        # SCM launch: connect to the service dispatcher. Without this call the
        # process never registers with the SCM (event 7009 failed starts).
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(ADWindowsService)
        servicemanager.StartServiceCtrlDispatcher()
        return 0

    match argv[1].lower():
        case "--debug" | "debug":
            ADWindowsService().SvcDoRun()
            return 0
        case "--install" | "install":
            print(
                "Use install_service.ps1 (run PowerShell as Administrator) "
                "to install the service."
            )
            return 1
        case "--remove" | "remove":
            win32serviceutil.RemoveService(ADWindowsService.serviceName)
            print("Service removed successfully.")
            return 0
        case "--start" | "start":
            win32serviceutil.StartService(ADWindowsService.serviceName)
            print("Service started successfully.")
            return 0
        case "--stop" | "stop":
            win32serviceutil.StopService(ADWindowsService.serviceName)
            print("Service stopped successfully.")
            return 0
        case "--help" | "-h" | "help":
            print(_USAGE)
            return 0
        case _:
            print(_USAGE)
            return 1


if __name__ == "__main__":
    sys.exit(main())
