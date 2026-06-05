"""
execute-python-mcp server implementation.

Provides the `execute_python` MCP tool for structured Python code execution.
Uses low-level mcp.server.Server for full control over error messages
and to avoid redundant parameter echoing from FastMCP.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

# ---------------------------------------------------------------------------
# Core execution logic
# ---------------------------------------------------------------------------

def _detect_error_type(stderr: str, stdout: str) -> Optional[str]:
    """Heuristically detect common Python error types from combined output."""
    combined = (stderr or "") + "\n" + (stdout or "")
    patterns = [
        ("ModuleNotFoundError", "ModuleNotFoundError"),
        ("No module named", "ModuleNotFoundError"),
        ("ImportError", "ImportError"),
        ("SyntaxError", "SyntaxError"),
        ("IndentationError", "SyntaxError"),
        ("NameError", "NameError"),
        ("AttributeError", "AttributeError"),
        ("TypeError", "TypeError"),
        ("ValueError", "ValueError"),
        ("FileNotFoundError", "FileNotFoundError"),
        ("PermissionError", "PermissionError"),
        ("IsADirectoryError", "IsADirectoryError"),
        ("NotADirectoryError", "NotADirectoryError"),
        ("OSError", "OSError"),
        ("TimeoutError", "TimeoutError"),
        ("RecursionError", "RecursionError"),
        ("KeyboardInterrupt", "KeyboardInterrupt"),
        ("RuntimeError", "RuntimeError"),
    ]
    for needle, etype in patterns:
        if needle in combined:
            return etype
    if "Traceback (most recent call last)" in combined:
        return "ExecutionError"
    return None

def _enrich_error_message(
    error_type: Optional[str],
    stderr: str,
    stdout: str,
) -> tuple[str, str]:
    """
    Enrich stderr/stdout for specific error types.
    REVISED: Removed redundant parameter/path echoing to minimize noise.
    """
    if not error_type:
        return stderr, stdout

    extra = ""
    if error_type == "ModuleNotFoundError":
        py_exe = sys.executable
        py_ver = sys.version.split()[0]
        extra = (
            f"\n\n[Environment Info]\n"
            f"  Python executable: {py_exe}\n"
            f"  Python version: {py_ver}\n"
            f"  Please ensure the missing package is installed in THIS environment."
        )
    elif error_type in {
        "FileNotFoundError",
        "PermissionError",
        "OSError",
        "IsADirectoryError",
        "NotADirectoryError",
    }:
        extra = "\n\n[Error] The specified path is inaccessible or does not exist."

    if extra:
        stderr = (stderr or "") + extra
    return stderr, stdout

def execute_python_code(
    code: str,
    cwd: str,
    timeout: int = 300,
) -> dict[str, Any]:
    """Execute arbitrary Python code using the current Python interpreter."""
    start_time = time.time()
    effective_cwd = os.path.abspath(os.path.expanduser(cwd))

    if not os.path.isdir(effective_cwd):
        duration = time.time() - start_time
        return {
            "stdout": "",
            "stderr": f"Working directory does not exist: {effective_cwd}",
            "exit_code": 1,
            "duration": round(duration, 3),
            "success": False,
            "error_type": "FileNotFoundError",
        }

    script_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            prefix="mcp_exec_",
            dir=tempfile.gettempdir(),
            delete=False,
            encoding="utf-8",
        ) as tmp:
            tmp.write(code)
            if not code.endswith("\n"):
                tmp.write("\n")
            script_path = tmp.name

        env = os.environ.copy()
        cmd = [sys.executable, "-u", script_path]

        proc = subprocess.run(
            cmd,
            cwd=effective_cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )

        duration = time.time() - start_time
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        exit_code = proc.returncode
        success = exit_code == 0

        error_type = None if success else _detect_error_type(stderr, stdout)
        stderr, stdout = _enrich_error_message(error_type, stderr, stdout)

        return {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "duration": round(duration, 3),
            "success": success,
            "error_type": error_type,
        }

    except subprocess.TimeoutExpired as exc:
        duration = time.time() - start_time
        stdout = (exc.stdout or b"").decode("utf-8", errors="replace") if exc.stdout else ""
        stderr = (exc.stderr or b"").decode("utf-8", errors="replace") if exc.stderr else ""
        stderr += f"\n\n[TimeoutError] Execution exceeded the {timeout}s limit."
        return {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": -1,
            "duration": round(duration, 3),
            "success": False,
            "error_type": "TimeoutError",
        }

    except Exception as exc:
        duration = time.time() - start_time
        err_type = type(exc).__name__
        if isinstance(exc, (PermissionError, FileNotFoundError, OSError)):
            err_type = "PathError"
        return {
            "stdout": "",
            "stderr": f"[Internal MCP Error] {err_type}: {exc}",
            "exit_code": 1,
            "duration": round(duration, 3),
            "success": False,
            "error_type": err_type,
        }

    finally:
        if script_path:
            try:
                Path(script_path).unlink(missing_ok=True)
            except Exception:
                pass

# ---------------------------------------------------------------------------
# Low-level MCP Server implementation
# ---------------------------------------------------------------------------

async def run_server() -> None:
    """Run the MCP server using stdio transport."""
    server = Server("execute-python")

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="execute_python",
                description=(
                    "Execute Python code in the current environment and return structured results. "
                    "This is the preferred way for agents to run Python.\n\n"
                    "Parameters:\n"
                    "  code (string, REQUIRED): The complete Python source code to run.\n"
                    "  cwd (string, REQUIRED): Working directory for the script.\n"
                    "  timeout (integer, OPTIONAL): Max seconds before killing the execution. Default=300.\n"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "The complete Python source code to run."
                        },
                        "cwd": {
                            "type": "string",
                            "description": "Working directory for the script."
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Max seconds before killing the execution.",
                            "default": 300
                        }
                    },
                    "required": ["code", "cwd"]
                }
            )
        ]

    @server.call_tool()
    async def handle_call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> list[types.TextContent]:
        if name != "execute_python":
            raise ValueError(f"Unknown tool: {name}")

        if not arguments:
            return [types.TextContent(type="text", text="Error: Missing arguments.")]

        # 1. Manual Validation (To avoid FastMCP's verbose parameter echoing)
        code = arguments.get("code")
        cwd = arguments.get("cwd")
        timeout_raw = arguments.get("timeout", 300)

        # Minimal, non-verbose error messages
        if not isinstance(code, str) or not code.strip():
            return [types.TextContent(type="text", text="Error: 'code' must be a non-empty string.")]
        
        if not isinstance(cwd, str):
            return [types.TextContent(type="text", text="Error: 'cwd' must be a string.")]

        try:
            timeout = int(timeout_raw)
            timeout = max(5, min(timeout, 3600))
        except (TypeError, ValueError):
            timeout = 300

        # 2. Execution
        result = await asyncio.to_thread(
            execute_python_code, 
            code=code, 
            cwd=cwd, 
            timeout=timeout
        )

        # 3. Return
        return [
            types.TextContent(
                type="text",
                text=json.dumps(result, ensure_ascii=False, indent=2)
            )
        ]

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(run_server())
