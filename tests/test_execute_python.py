"""
Unit tests for the core execute_python_code logic (no MCP server required).
These tests run fast and exercise success, error paths, cwd, timeout, and enrichment.
"""

import os
import sys
from pathlib import Path

import pytest

from execute_python_mcp.server import execute_python_code


def test_simple_print():
    result = execute_python_code("print('hello from mcp')")
    assert result["success"] is True
    assert result["exit_code"] == 0
    assert "hello from mcp" in result["stdout"]
    assert result["error_type"] is None
    assert result["duration"] > 0


def test_syntax_error():
    result = execute_python_code("print('unclosed")
    assert result["success"] is False
    assert result["exit_code"] != 0
    assert result["error_type"] == "SyntaxError"
    assert "SyntaxError" in result["stderr"]


def test_module_not_found_enrichment():
    result = execute_python_code("import definitely_not_a_real_package_xyz_123")
    assert result["success"] is False
    assert result["error_type"] == "ModuleNotFoundError"
    # Must contain Python executable path and version info
    assert "Python executable:" in result["stderr"]
    assert "Python version:" in result["stderr"]
    assert sys.executable in result["stderr"] or "python" in result["stderr"].lower()


def test_name_error():
    result = execute_python_code("x = undefined_variable_zzz + 1")
    assert result["success"] is False
    assert result["error_type"] == "NameError"


def test_cwd_affects_relative_path(tmp_path: Path):
    # Create a marker file in a temp dir and read it via relative open()
    marker = tmp_path / "marker.txt"
    marker.write_text("MCP_CWD_TEST_42", encoding="utf-8")

    code = "with open('marker.txt') as f: print(f.read().strip())"
    result = execute_python_code(code, cwd=str(tmp_path))
    assert result["success"] is True
    assert "MCP_CWD_TEST_42" in result["stdout"]


def test_invalid_cwd_reported():
    result = execute_python_code("print(1)", cwd="/this/path/almost_certainly_does_not_exist_98765")
    assert result["success"] is False
    assert result["error_type"] == "FileNotFoundError"
    assert "/this/path/almost_certainly_does_not_exist_98765" in result["stderr"]


def test_timeout_kills_long_running():
    # Sleep 10s but timeout after 1s
    result = execute_python_code("import time; time.sleep(10)", timeout=1)
    assert result["success"] is False
    assert result["error_type"] == "TimeoutError"
    assert "exceeded the 1s limit" in result["stderr"]


def test_path_error_enrichment(tmp_path: Path):
    # Try to open a file that doesn't exist inside a specific cwd
    # This should trigger FileNotFoundError + cwd note
    code = "open('i_do_not_exist_at_all_999.txt')"
    result = execute_python_code(code, cwd=str(tmp_path))
    assert result["success"] is False
    assert result["error_type"] == "FileNotFoundError"
    assert "Actual execution working directory (cwd):" in result["stderr"]
    assert str(tmp_path) in result["stderr"]


def test_return_value_and_stderr():
    code = """
import sys
print('to stdout')
print('to stderr', file=sys.stderr)
"""
    result = execute_python_code(code)
    assert "to stdout" in result["stdout"]
    assert "to stderr" in result["stderr"]
    assert result["success"] is True


def test_nonzero_exit():
    result = execute_python_code("import sys; sys.exit(42)")
    assert result["success"] is False
    assert result["exit_code"] == 42



