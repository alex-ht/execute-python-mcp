"""
Entry point for `execute-python-mcp` command and `python -m execute_python_mcp`.

Starts the MCP server over stdio (the only supported transport for this server).
"""

from __future__ import annotations

import logging
import sys


import os  # needed for env var check at import time for some runtimes


def main() -> None:
    """Main entry point. Configures minimal logging then runs the stdio MCP server."""
    # Keep logs quiet by default (MCP stdio must not emit to stdout).
    # Users can set EXECUTE_PYTHON_MCP_LOG=DEBUG for troubleshooting.
    log_level = logging.DEBUG if os.environ.get("EXECUTE_PYTHON_MCP_LOG") == "DEBUG" else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    from .server import run_server

    try:
        run_server()
    except KeyboardInterrupt:
        # Clean exit on Ctrl-C (common when testing from terminal)
        pass
    except Exception as exc:  # pragma: no cover
        print(f"Fatal error starting execute-python-mcp: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
