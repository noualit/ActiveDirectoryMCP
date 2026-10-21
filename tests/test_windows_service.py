"""Tests for Windows service module."""

import json
import os
import tempfile
from pathlib import Path

import pytest


def test_windows_service_module_exists():
    """Test that the windows_service module can be imported."""
    from active_directory_mcp import windows_service
    assert windows_service is not None


def test_ad_windows_service_class_exists():
    """Test that ADWindowsService class exists."""
    from active_directory_mcp.windows_service import ADWindowsService
    assert ADWindowsService is not None


def test_ad_windows_service_has_required_methods():
    """Test that ADWindowsService has all required Windows service methods."""
    from active_directory_mcp.windows_service import ADWindowsService

    required_methods = [
        "SvcDoRun",
        "SvcStop",
        "SvcPause",
        "SvcContinue",
        "SvcGetStatus",
    ]

    for method_name in required_methods:
        assert hasattr(ADWindowsService, method_name), \
            f"ADWindowsService missing required method: {method_name}"


def test_ad_windows_service_service_name():
    """Test that ADWindowsService has correct service name."""
    from active_directory_mcp.windows_service import ADWindowsService
    assert ADWindowsService.serviceName == "ActiveDirectoryMCP"
    assert ADWindowsService.DisplayName == "Active Directory MCP Server"


def test_windows_service_init_with_config(tmp_path):
    """Test ADWindowsService initialization with config file path."""
    config_data = {
        "active_directory": {
            "server": "ldap://test.local:389",
            "domain": "test.local",
            "base_dn": "DC=test,DC=local",
            "bind_dn": "CN=admin,DC=test,DC=local",
            "password": "password123"
        },
        "organizational_units": {
            "users_ou": "OU=Users,DC=test,DC=local",
            "groups_ou": "OU=Groups,DC=test,DC=local",
            "computers_ou": "OU=Computers,DC=test,DC=local",
            "service_accounts_ou": "OU=Service Accounts,DC=test,DC=local"
        }
    }

    config_file = tmp_path / "test_config.json"
    config_file.write_text(json.dumps(config_data))

    from active_directory_mcp.windows_service import ADWindowsService

    service = ADWindowsService(
        args=["test"],
        config_path=str(config_file)
    )
    assert service.config_path == str(config_file)


def test_windows_service_default_config_path():
    """Default config is the live ad-config.json, always absolute.

    A Windows service starts in System32, so relative paths (the old
    'ad-config/config.json' fallback) resolve against the wrong CWD and
    crash with FileNotFoundError.
    """
    from active_directory_mcp import windows_service

    service = windows_service.ADWindowsService(args=["test"])
    path = Path(service.config_path)
    assert path.is_absolute()
    assert path == windows_service.PROJECT_ROOT / "ad-config" / "ad-config.json"


def test_windows_service_config_relative_env_resolves_against_project_root(monkeypatch, tmp_path):
    """Relative AD_MCP_CONFIG resolves against PROJECT_ROOT, not the process CWD."""
    monkeypatch.setenv("AD_MCP_CONFIG", "ad-config/ad-config.json")
    monkeypatch.chdir(tmp_path)  # simulate service CWD (System32)

    from active_directory_mcp import windows_service

    service = windows_service.ADWindowsService(args=["test"])
    path = Path(service.config_path)
    assert path.is_absolute()
    assert path == windows_service.PROJECT_ROOT / "ad-config" / "ad-config.json"
    assert path.exists()


def test_windows_service_config_default_without_env(monkeypatch):
    """With AD_MCP_CONFIG unset, the absolute live default is used."""
    monkeypatch.delenv("AD_MCP_CONFIG", raising=False)

    from active_directory_mcp import windows_service

    service = windows_service.ADWindowsService(args=["test"])
    assert Path(service.config_path) == windows_service.PROJECT_ROOT / "ad-config" / "ad-config.json"


def test_windows_service_default_host_port():
    """Test ADWindowsService uses correct default host and port."""
    from active_directory_mcp.windows_service import ADWindowsService

    service = ADWindowsService(args=["test"])
    assert service.host == "0.0.0.0"
    assert service.port == 8813
    assert service.path == "/activedirectory-mcp"


def test_windows_service_custom_host_port():
    """Test ADWindowsService accepts custom host and port."""
    from active_directory_mcp.windows_service import ADWindowsService

    service = ADWindowsService(
        args=["test"],
        host="192.168.1.100",
        port=9000,
        path="/mcp/ad"
    )
    assert service.host == "192.168.1.100"
    assert service.port == 9000
    assert service.path == "/mcp/ad"


def test_windows_service_log_file_default():
    """Default log file lives inside the project ad-config directory.

    The old '..'*3 chain resolved one level too high (D:\\github\\ad-config)
    when the module lives at <root>\\src\\active_directory_mcp.
    """
    from active_directory_mcp import windows_service

    service = windows_service.ADWindowsService(args=["test"])
    assert Path(service.log_file) == windows_service.PROJECT_ROOT / "ad-config" / "mcp_service.log"


def test_windows_service_log_file_custom():
    """Test ADWindowsService accepts custom log file path."""
    from active_directory_mcp.windows_service import ADWindowsService

    service = ADWindowsService(
        args=["test"],
        log_file="C:\\logs\\mcp.log"
    )
    assert service.log_file == "C:\\logs\\mcp.log"


def test_windows_service_unregister_function():
    """Test that unregister function exists and is callable."""
    from active_directory_mcp.windows_service import unregister
    assert callable(unregister)


# --- Environment argument parsing (installer writes `--env KEY=VALUE`, space form) ---

def test_parse_env_args_accepts_installer_space_form():
    """install_service.ps1 writes `--env KEY=VALUE`; the parser must accept it.

    The old parser only understood `--env=KEY=VALUE`, so every installer
    override (AD_MCP_CONFIG, host, port...) was silently discarded.
    """
    from active_directory_mcp.windows_service import parse_env_args

    args = ["--env", "AD_MCP_CONFIG=D:/x/config.json", "--env", "AD_MCP_PORT=9000"]
    assert parse_env_args(args) == {
        "AD_MCP_CONFIG": "D:/x/config.json",
        "AD_MCP_PORT": "9000",
    }


def test_parse_env_args_accepts_equals_form():
    from active_directory_mcp.windows_service import parse_env_args

    assert parse_env_args(["--env=AD_MCP_PORT=9000"]) == {"AD_MCP_PORT": "9000"}


def test_parse_env_args_mixed_and_unrelated_tokens():
    from active_directory_mcp.windows_service import parse_env_args

    args = ["--debug", "--env", "A=1", "--env=B=2", "orphan"]
    assert parse_env_args(args) == {"A": "1", "B": "2"}


# --- Config path resolution ---

def test_resolve_config_path_passthrough_absolute(tmp_path):
    from active_directory_mcp.windows_service import resolve_config_path

    cfg = tmp_path / "cfg.json"
    assert resolve_config_path(str(cfg)) == str(cfg)


def test_resolve_config_path_default_is_absolute_live_config():
    from active_directory_mcp import windows_service

    path = Path(windows_service.resolve_config_path(None))
    assert path.is_absolute()
    assert path == windows_service.PROJECT_ROOT / "ad-config" / "ad-config.json"


def test_resolve_config_path_relative_against_project_root(tmp_path, monkeypatch):
    from active_directory_mcp import windows_service

    monkeypatch.chdir(tmp_path)
    path = Path(windows_service.resolve_config_path("ad-config/other.json"))
    assert path == windows_service.PROJECT_ROOT / "ad-config" / "other.json"


# --- Service mode detection (SCM launch vs CLI verb) ---

def test_is_service_mode_true_for_scm_launches():
    from active_directory_mcp.windows_service import is_service_mode

    assert is_service_mode(["windows_service.py"]) is True
    assert is_service_mode(["windows_service.py", "--env", "AD_MCP_PORT=9000"]) is True


def test_is_service_mode_false_for_cli_verbs():
    from active_directory_mcp.windows_service import is_service_mode

    for verb in ("--debug", "--remove", "--start", "--stop", "install", "Debug"):
        assert is_service_mode(["windows_service.py", verb]) is False, verb


# --- main(): SCM entry point (root-cause regression: 16x event 7009) ---

def test_main_service_mode_connects_to_scm_dispatcher(monkeypatch):
    """Without Initialize/PrepareToHostSingle/StartServiceCtrlDispatcher the
    process never registers with the SCM and every start fails (event 7009).
    """
    from active_directory_mcp import windows_service as ws

    calls = []
    monkeypatch.setattr(ws.servicemanager, "Initialize", lambda: calls.append("init"))
    monkeypatch.setattr(
        ws.servicemanager, "PrepareToHostSingle",
        lambda cls: calls.append(("host", cls)),
    )
    monkeypatch.setattr(
        ws.servicemanager, "StartServiceCtrlDispatcher", lambda: calls.append("dispatch")
    )

    rc = ws.main(["windows_service.py"])
    assert rc == 0
    assert calls == ["init", ("host", ws.ADWindowsService), "dispatch"]


def test_main_install_redirects_to_install_script(capsys):
    from active_directory_mcp import windows_service as ws

    assert ws.main(["windows_service.py", "--install"]) == 1
    assert "install_service.ps1" in capsys.readouterr().out


def test_main_remove_invokes_win32serviceutil(monkeypatch):
    from active_directory_mcp import windows_service as ws

    removed = []
    monkeypatch.setattr(ws.win32serviceutil, "RemoveService", lambda name: removed.append(name))

    assert ws.main(["windows_service.py", "--remove"]) == 0
    assert removed == ["ActiveDirectoryMCP"]


def test_main_debug_runs_service_locally(monkeypatch):
    from active_directory_mcp import windows_service as ws

    runs = []

    class FakeService:
        def SvcDoRun(self):
            runs.append("run")

    monkeypatch.setattr(ws, "ADWindowsService", FakeService)
    assert ws.main(["windows_service.py", "--debug"]) == 0
    assert runs == ["run"]


def test_main_service_mode_redirects_stdio_to_file():
    """Service mode must redirect stdout/stderr to a log file.

    The SCM gives services no usable console: server_http/FastMCP/uvicorn
    write to stdio and an invalid handle raises OSError, killing the server
    thread while the service stays 'Running' with no listener.
    """
    import sys as _sys

    from active_directory_mcp import windows_service as ws

    old_out, old_err = _sys.stdout, _sys.stderr
    try:
        # Replace the dispatcher so main() returns instead of blocking.
        import unittest.mock as mock

        with mock.patch.object(ws.servicemanager, "Initialize"), \
                mock.patch.object(ws.servicemanager, "PrepareToHostSingle"), \
                mock.patch.object(ws.servicemanager, "StartServiceCtrlDispatcher"):
            rc = ws.main(["windows_service.py"])

        assert rc == 0
        assert _sys.stdout is not old_out
        assert _sys.stderr is not old_err
        assert _sys.stderr.name == str(ws.PROJECT_ROOT / "ad-config" / "service_console.log")
        assert not _sys.stderr.closed
    finally:
        _sys.stdout, _sys.stderr = old_out, old_err


def test_run_http_server_survives_system_exit_and_retries(monkeypatch, caplog):
    """server_http.run() calls sys.exit(1) on failure; a bare `except
    Exception` lets SystemExit kill the thread silently (service 'Running'
    with no listener). The loop must catch it, log it, and not propagate.
    """
    import logging as _logging

    from active_directory_mcp import server_http
    from active_directory_mcp import windows_service as ws

    calls = {"run": 0, "constructed": 0}

    class FakeServer:
        def __init__(self, **kwargs):
            calls["constructed"] += 1
            self.kwargs = kwargs

        def run(self, setup_signals=True):
            calls["run"] += 1
            svc.stop_event.set()  # shutdown requested during the failure
            raise SystemExit(1)   # what server_http.run() does on error

    monkeypatch.setattr(server_http, "ActiveDirectoryMCPHTTPServer", FakeServer)

    svc = ws.ADWindowsService(args=["test"])
    with caplog.at_level(_logging.ERROR, logger="ActiveDirectoryMCP-Service"):
        svc._run_http_server()  # must return, not raise SystemExit

    assert calls["constructed"] == 1
    assert calls["run"] == 1
    assert svc.server_instance is not None
    assert "HTTP server error" in caplog.text


def test_run_http_server_retries_after_transient_failure(monkeypatch):
    """A failed run() must be retried (transient bind errors), not kill the thread."""
    from active_directory_mcp import server_http
    from active_directory_mcp import windows_service as ws

    calls = {"run": 0}

    class FlakyServer:
        def __init__(self, **kwargs):
            pass

        def run(self, setup_signals=True):
            calls["run"] += 1
            if calls["run"] == 1:
                raise OSError(10048, "address already in use")  # transient
            svc.stop_event.set()

    monkeypatch.setattr(server_http, "ActiveDirectoryMCPHTTPServer", FlakyServer)
    monkeypatch.setattr(ws.time, "sleep", lambda _s: None)  # keep the test fast

    svc = ws.ADWindowsService(args=["test"])
    svc._run_http_server()

    assert calls["run"] == 2  # first failure, then successful retry


def test_windows_service_get_description():
    """Test ADWindowsService has description attribute."""
    from active_directory_mcp.windows_service import ADWindowsService

    assert hasattr(ADWindowsService, 'description')
    assert isinstance(ADWindowsService.description, str)
    assert len(ADWindowsService.description) > 0
