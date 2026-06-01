# execute-python-mcp

A minimal and extremely permissive MCP Server that provides the `execute_python` tool. It allows MCP-compatible agents (especially **OpenClaw**) to execute Python code in a clean, structured way.

**Design Goal**: Significantly reduce the need for small models to use raw `python -c "..."` or `bash -c "python ..."` commands by providing a proper tool interface.

## Key Features

- **Extremely Permissive**: Executes code directly in your current Python environment. **No sandboxing, no permission restrictions**.
- **Native Package Access**: All packages you installed via `pip install` or `uv pip install` are immediately available for the agent to `import`.
- **Small-Model-Friendly Error Feedback**:
  - On `ModuleNotFoundError`, automatically appends the **Python executable path + Python version** so you know exactly which environment to install the package in.
  - On path-related errors (`FileNotFoundError`, `PermissionError`, `OSError`, etc.), clearly reports the **actual working directory (cwd)** used during execution.
- Minimal parameters (only 3), keeping cognitive load low for agents.

## Installation

```bash
pip install execute-python-mcp
```

Or using uv (recommended):

```bash
uv pip install execute-python-mcp
```

> **Important Environment Note**: Install this package in the exact Python environment you want the agent to use.
> If you have multiple conda / venv / pyenv environments, the packages available to the agent depend on which Python the `execute-python-mcp` command resolves to.

After installation, verify the command is available:

```bash
execute-python-mcp --help    # Should show usage or start the server (Ctrl-C to exit)
which execute-python-mcp     # Check which Python environment it points to
```

## Running the Server

Simply run the command (uses stdio transport, fully MCP compliant):

```bash
execute-python-mcp
```

This process runs continuously and communicates with MCP clients via stdin/stdout. You usually do not need to start it manually — once registered with OpenClaw, Claude Desktop, or similar clients, the client will manage its lifecycle automatically.

## Registering in OpenClaw

OpenClaw provides the `/mcp` command to manage MCP servers (writes to `mcp.servers` configuration).

### Recommended Registration

In the OpenClaw chat, run:

```bash
/mcp set execute-python={"command":"execute-python-mcp"}
```

If `execute-python-mcp` is in a specific location (e.g., conda / mise / asdf):

```bash
/mcp set execute-python={"command":"/home/alex/.local/bin/execute-python-mcp"}
```

Or using the more robust `python -m` approach:

```bash
/mcp set execute-python={"command":"python","args":["-m","execute_python_mcp"]}
```

### Advanced: Setting Environment Variables

```json
/mcp set execute-python={"command":"execute-python-mcp","env":{"PYTHONPATH":"/home/alex/myproject","MY_API_KEY":"..."}}
```

### View / Remove

```bash
/mcp show execute-python
/mcp unset execute-python
```

After setting, **restart OpenClaw** or the relevant agent session for the tool to take effect.

The tool will appear in the agent as `execute_python` (not `mcp_execute-python_execute_python`).

## Quick Verification (Let the Agent Test It)

After registration, ask your agent in OpenClaw:

> Please use the `execute_python` tool to run the following code and report the result back to me:
> ```python
> print("Hello from execute-python-mcp!")
> import sys
> print("Python version:", sys.version)
> print("Success!")
> ```

The agent should call the tool and return something like:

```json
{
  "stdout": "Hello from execute-python-mcp!\nPython version: 3.11.9 ...\nSuccess!\n",
  "stderr": "",
  "exit_code": 0,
  "duration": 0.123,
  "success": true,
  "error_type": null
}
```

### Test Package Availability (Recommended)

```python
import numpy as np
import pandas as pd
print("numpy:", np.__version__)
print("pandas:", pd.__version__)
print("All good!")
```

If a `ModuleNotFoundError` occurs, the error message will clearly indicate which Python executable should be used to install the package.

## Tool Parameters

| Parameter | Type    | Required | Default     | Description |
|-----------|---------|----------|-------------|-------------|
| `code`    | string  | Yes      | -           | The complete Python source code to execute (supports multiline, imports, functions, loops, etc.) |
| `cwd`     | string  | No       | Current dir | Working directory during execution. Relative paths in your code are resolved against this directory. |
| `timeout` | integer | No       | 300         | Timeout in seconds (5 minutes). Increase for long-running training/inference; decrease for quick scripts (e.g., 30). |

The tool always returns the following fields (JSON):

- `stdout`: Standard output
- `stderr`: Standard error (environment diagnostic information is automatically appended on errors)
- `exit_code`: Exit code (0 = success)
- `duration`: Execution time in seconds (float)
- `success`: Boolean
- `error_type`: Error type string on failure (`ModuleNotFoundError`, `SyntaxError`, `FileNotFoundError`, ...), or `null` on success

## Troubleshooting

### 1. ModuleNotFoundError

The error message will include:

```
[Environment Info for ModuleNotFoundError]
  Python executable: /home/alex/.pyenv/versions/3.11.9/bin/python
  Python version: 3.11.9
```

**Solution**: Switch to that exact environment and run `pip install <package>`. Do not install from a different shell.

### 2. Relative paths cannot find files

The error message includes the **actual cwd** used at runtime. Please verify:
- The `cwd` you passed actually exists
- The target files exist in that directory

### 3. Why no sandbox / permission control?

This project is intentionally designed to give agents full access to your local environment. If you need controlled execution, consider using other sandboxed MCP servers or Docker-based solutions.

### 4. Long-running tasks get killed?

Default timeout is 300 seconds (5 minutes). For longer execution, pass `timeout: 1800` (30 minutes) or higher (maximum 3600).

### 5. Compatibility

This server uses only stdio transport and is compatible with all major MCP clients, including OpenClaw, Claude Desktop, Claude Code, Cursor, Cline, Windsurf, etc.

## Development

```bash
git clone https://github.com/alex-ht/execute-python-mcp.git
cd execute-python-mcp
pip install -e ".[dev]"
pytest -v
```

## License

MIT License

Copyright (c) 2026 AlexHT Hung
