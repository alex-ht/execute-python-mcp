"""
execute-python-mcp

A standalone MCP server that exposes a single powerful tool: `execute_python`.
Lets MCP clients (OpenClaw, Claude Code, Cursor, etc.) run Python code in the
user's real environment with zero friction and excellent error feedback for small models.

Usage (after pip install):
    execute-python-mcp
"""

__version__ = "0.1.0"

from .server import create_mcp_server, execute_python_code, run_server

__all__ = [
    "create_mcp_server",
    "execute_python_code",
    "run_server",
    "__version__",
]
