"""
execute-python-mcp server implementation.

Provides the `execute_python` MCP tool for structured Python code execution.
Designed to be extremely permissive (uses current Python env, no sandbox)
and friendly to small models with clear error messages.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

# Lazy import to give nice error if mcp missing (though pip dep should prevent)
try:
    from mcp.server.fastmcp import FastMCP
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "The 'mcp' package is required. Install with: pip install 'mcp>=1.26.0,<2'"
    ) from e


# ---------------------------------------------------------------------------
# Core execution logic (extracted for testability)
# ---------------------------------------------------------------------------


def _detect_error_type(stderr: str, stdout: str) -> Optional[str]:
    """Heuristically detect common Python error types from combined output."""
    combined = (stderr or "") + "\n" + (stdout or "")
    # Order matters: more specific first
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
    effective_cwd: str,
) -> tuple[str, str]:
    """
    Enrich stderr/stdout for specific error types per requirements:
    - ModuleNotFoundError: include python executable path + version
    - Path-related errors: explicitly include the actual cwd used
    """
    if not error_type:
        return stderr, stdout

    extra = ""
    if error_type == "ModuleNotFoundError":
        py_exe = sys.executable
        py_ver = sys.version.split()[0]
        extra = (
            f"\n\n[Environment Info for ModuleNotFoundError]\n"
            f"  Python executable: {py_exe}\n"
            f"  Python version: {py_ver}\n"
            f"  This MCP server is running under the above Python. "
            f"Make sure the missing package is installed in THIS environment "
            f"(pip install <package> or uv pip install <package>)."
        )
    elif error_type in {
        "FileNotFoundError",
        "PermissionError",
        "OSError",
        "IsADirectoryError",
        "NotADirectoryError",
    }:
        extra = (
            f"\n\n[Environment Info for Path Error]\n"
            f"  Actual execution working directory (cwd): {effective_cwd}\n"
            f"  Please verify that the path exists and is accessible from this directory."
        )

    if extra:
        stderr = (stderr or "") + extra
    return stderr, stdout


def execute_python_code(
    code: str,
    cwd: str,
    timeout: int = 300,
) -> dict[str, Any]:
    """
    Execute arbitrary Python code using the current Python interpreter.

    This is intentionally permissive:
    - Runs in the exact same Python environment as the MCP server (all user packages available)
    - No sandbox, no permission restrictions
    - Full access to installed packages, filesystem (subject to OS user), network, etc.

    Args:
        code: The Python source code to execute. Can be multi-line.
        cwd: Working directory for the execution (required, no default).
             Relative paths in code (open('data.txt'), etc.) will resolve against this directory.
             Must be an existing directory.
        timeout: Maximum seconds to allow execution (default 300 = 5 minutes).
                 Use smaller values for quick one-liners; larger for long computations.

    Returns:
        dict with keys:
            stdout: captured standard output
            stderr: captured standard error (plus enriched info on certain errors)
            exit_code: process exit code (0 = success)
            duration: wall time in seconds (float, 3 decimals)
            success: bool (exit_code == 0)
            error_type: str | None  (e.g. "ModuleNotFoundError", "SyntaxError", ...)
    """
    start_time = time.time()

    # Resolve effective cwd (must be absolute for clarity in error messages)
    effective_cwd = os.path.abspath(os.path.expanduser(cwd))

    # Early validation of cwd (before spawning) so we can report it clearly
    if not os.path.isdir(effective_cwd):
        duration = time.time() - start_time
        err_msg = (
            f"[Path Error] Working directory does not exist or is not a directory: {effective_cwd}\n"
            f"Please create it first or use an existing directory."
        )
        return {
            "stdout": "",
            "stderr": err_msg,
            "exit_code": 1,
            "duration": round(duration, 3),
            "success": False,
            "error_type": "FileNotFoundError",
        }

    # Write code to a temp file (in system tempdir to avoid polluting cwd).
    # We still execute *with* cwd=effective_cwd so that relative paths inside
    # the user's code resolve correctly.
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
            # Ensure trailing newline (some Python edge cases)
            if not code.endswith("\n"):
                tmp.write("\n")
            script_path = tmp.name

        # Full environment inheritance (permissive design)
        env = os.environ.copy()

        # Use -u for unbuffered stdout/stderr (better for long-running prints)
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
        stderr, stdout = _enrich_error_message(error_type, stderr, stdout, effective_cwd)

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
        stderr += f"\n\n[TimeoutError] Execution exceeded the {timeout}s limit and was terminated."
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
        # This catches Popen-level failures (e.g. weird permission on python binary)
        err_type = type(exc).__name__
        if isinstance(exc, (PermissionError, FileNotFoundError, OSError)):
            err_type = "PathError"
        return {
            "stdout": "",
            "stderr": f"[Internal MCP Error] {err_type}: {exc}\nActual cwd attempted: {effective_cwd}",
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
                pass  # best effort cleanup


# ---------------------------------------------------------------------------
# FastMCP server factory
# ---------------------------------------------------------------------------


def create_mcp_server() -> FastMCP:
    """Create and configure the execute-python MCP server."""
    mcp = FastMCP(
        "execute-python",
        instructions=(
            "You are an MCP server that lets the agent execute Python code in the user's local "
            "Python environment. All packages the user has pip/uv-installed are directly available. "
            "No sandboxing is applied. Use this instead of shelling out to `python -c` or `bash -c`."
        ),
    )

    @mcp.tool(
        name="execute_python",
        description=(
            "Execute Python code in the current environment and return structured results. "
            "This is the preferred way for agents (especially small models) to run Python instead of "
            "using `python -c '...' ` or `bash -c 'python ...'`.\n\n"
            "Parameters:\n"
            "  code (string, REQUIRED): The complete Python source code to run. Supports multiple lines, "
            "imports, functions, loops, etc. Write normal .py code.\n"
            "  cwd (string, REQUIRED): Working directory for the script (no default). Use this when your code opens "
            "relative files (e.g. 'data.csv', './output/'). Must be an existing directory path.\n"
            "  timeout (integer, OPTIONAL): Max seconds before killing the execution. Default=300 (5 min). "
            "Use 30-60 for quick snippets; increase for long training/inference jobs.\n\n"
            "Returns (always):\n"
            "  stdout, stderr, exit_code, duration (seconds), success (bool), error_type (string or null).\n\n"
            "Error handling (model-friendly):\n"
            "  - ModuleNotFoundError: automatically appends the exact Python executable path and version "
            "so you know which environment to pip install into.\n"
            "  - Path errors (FileNotFoundError, PermissionError, ...): automatically appends the actual "
            "cwd that was used during execution.\n\n"
            "Tips for small models:\n"
            "  - Always import what you need at the top of `code`.\n"
            "  - Print final results with print().\n"
            "  - For long computations, consider a larger timeout.\n"
            "  - If a package is missing, the error message will tell you exactly which Python to use for pip."
        ),
    )
    def execute_python(
        code: str,
        cwd: str,
        timeout: int = 300,
    ) -> str:
        """
        Execute Python code.

        See the tool description for full parameter and return documentation.
        The return value is a JSON string containing stdout/stderr/exit_code/duration/success/error_type.
        """
        if not isinstance(code, str) or not code.strip():
            return json.dumps(
                {
                    "stdout": "",
                    "stderr": "Error: 'code' parameter must be a non-empty string containing Python source.",
                    "exit_code": 1,
                    "duration": 0.0,
                    "success": False,
                    "error_type": "ValueError",
                },
                ensure_ascii=False,
                indent=2,
            )

        # Coerce timeout to sane bounds (protect against model sending 999999 or negative)
        try:
            timeout = int(timeout)
        except (TypeError, ValueError):
            timeout = 300
        timeout = max(5, min(timeout, 3600))  # 5s min, 1h max

        if not isinstance(cwd, str):
            cwd = str(cwd)

        result = execute_python_code(code=code, cwd=cwd, timeout=timeout)
        return json.dumps(result, ensure_ascii=False, indent=2)

    return mcp


# Convenience for direct invocation
def run_server() -> None:
    """Run the MCP server using stdio transport (blocking)."""
    mcp = create_mcp_server()
    mcp.run(transport="stdio")
