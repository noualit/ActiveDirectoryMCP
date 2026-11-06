"""Entry point for `python -m active_directory_mcp`."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server_http import main as http_main
from server import main as stdio_main

if __name__ == "__main__":
    # Si hay argumentos, asumir que es el servidor HTTP
    if len(sys.argv) > 1:
        http_main()
    else:
        stdio_main()
