@echo off
setlocal
set AD_MCP_CONFIG=D:\python\localia-ops-dist\vendor\active-directory-mcp\ad-config\ad-config.json
set PYTHONPATH=D:\python\localia-ops-dist\vendor\active-directory-mcp\src
C:\ProgramData\miniconda3\envs\ad-mcp\python.exe -m active_directory_mcp.server_http --config "%AD_MCP_CONFIG%" --host 0.0.0.0 --port 8813 --path /activedirectory-mcp
