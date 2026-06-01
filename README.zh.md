# execute-python-mcp

一個極度寬鬆的 MCP Server，提供 `execute_python` 工具，讓支援 MCP 的 Agent（特別是 **OpenClaw**）能以結構化方式執行 Python 程式碼。

**設計目標**：讓小模型（small models）大幅減少直接使用 `python -c "..."` 或 `bash -c "python ..."` 的情況，改用乾淨的工具呼叫。

## 核心特色

- **極度寬鬆**：直接使用你當前 Python 環境執行，**完全不做 sandbox、不做權限控管**。
- **原生套件可用**：你 `pip install` / `uv pip install` 的所有套件，在 Agent 裡都能直接 `import`。
- **對小模型友善的錯誤回饋**：
  - 發生 `ModuleNotFoundError` 時，自動附上 **Python 執行檔路徑 + Python 版本**，告訴你該用哪個環境裝套件。
  - 發生路徑相關錯誤（`FileNotFoundError`、`PermissionError`、`OSError` 等）時，明確告訴你**實際執行時的工作目錄（cwd）**。
- 參數極簡，只有 3 個，認知負擔低。

## 安裝方式

```bash
pip install execute-python-mcp
```

或使用 uv（推薦）：

```bash
uv pip install execute-python-mcp
```

> **重要環境提醒**：請在你希望 Agent 使用的「那個 Python 環境」裡安裝。
> 如果你有多個 conda / venv / pyenv 環境，Agent 能使用的套件取決於 `execute-python-mcp` 這個指令解析到哪個 Python。

安裝後驗證指令是否可用：

```bash
execute-python-mcp --help    # 應該顯示 usage 或直接啟動（Ctrl-C 離開）
which execute-python-mcp     # 查看實際指向的路徑
```

## 啟動方式

直接執行即可（使用 stdio transport，符合 MCP 標準）：

```bash
execute-python-mcp
```

這個程序會一直跑，等待 MCP Client 透過 stdin/stdout 與它通訊。通常不需要手動啟動，註冊到 OpenClaw / Claude Desktop 後會由 Client 自動管理生命週期。

## 在 OpenClaw 中註冊此 MCP Server

OpenClaw 提供 `/mcp` 指令來管理 MCP servers（寫入 `mcp.servers` 配置）。

### 最簡單註冊方式（推薦）

在 OpenClaw 聊天視窗中輸入：

```bash
/mcp set execute-python={"command":"execute-python-mcp"}
```

如果你的 `execute-python-mcp` 在特定路徑（例如使用 conda / mise / asdf）：

```bash
/mcp set execute-python={"command":"/home/alex/.local/bin/execute-python-mcp"}
```

或使用完整 python -m 方式（較穩）：

```bash
/mcp set execute-python={"command":"python","args":["-m","execute_python_mcp"]}
```

### 一次設定多個環境變數（進階）

```json
/mcp set execute-python={"command":"execute-python-mcp","env":{"PYTHONPATH":"/home/alex/myproject","MY_API_KEY":"..."}}
```

### 查看 / 移除

```bash
/mcp show execute-python
/mcp unset execute-python
```

設定完成後，**重啟 OpenClaw** 或該 Agent 的會話，即可讓工具生效。

工具在 Agent 中會以 `execute_python` 這個名字出現（不是 `mcp_execute-python_execute_python`）。

## 簡單驗證方式（讓 Agent 測試）

註冊完成後，在 OpenClaw 對話中直接對 Agent 說：

> 請使用 `execute_python` 工具執行以下程式碼，並把結果告訴我：
> ```python
> print("Hello from execute-python-mcp!")
> import sys
> print("Python version:", sys.version)
> print("Success!")
> ```

正常情況下，Agent 應該會呼叫工具，並回傳類似：

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

### 測試套件可用性（重要）

```python
import numpy as np
import pandas as pd
print("numpy:", np.__version__)
print("pandas:", pd.__version__)
print("All good!")
```

如果回報 `ModuleNotFoundError`，錯誤訊息裡會明確告訴你「請用這個 Python 執行檔去 pip install」。

## 工具參數說明

| 參數      | 類型     | 必填 | 預設值   | 說明 |
|-----------|----------|------|----------|------|
| `code`    | string   | 是   | -        | 要執行的完整 Python 原始碼（可多行、含 import、def、for 迴圈等） |
| `cwd`     | string   | 否   | 當前目錄 | 執行時的工作目錄。你的程式裡如果用相對路徑開檔，會以此為基準 |
| `timeout` | integer  | 否   | 300      | 超時秒數（5 分鐘）。長時間訓練/推論請調大，快速小程式可調小（例如 30） |

回傳永遠包含以下欄位（JSON）：

- `stdout`：標準輸出
- `stderr`：標準錯誤（已自動加入環境診斷資訊）
- `exit_code`：結束碼（0 = 成功）
- `duration`：執行耗時（秒，浮點數）
- `success`：布林值
- `error_type`：失敗時的錯誤類型字串（`ModuleNotFoundError`、`SyntaxError`、`FileNotFoundError`...），成功時為 null

## 常見問題與注意事項

### 1. ModuleNotFoundError 怎麼辦？

錯誤訊息會直接告訴你：

```
[Environment Info for ModuleNotFoundError]
  Python executable: /home/alex/.pyenv/versions/3.11.9/bin/python
  Python version: 3.11.9
```

請**切換到該環境**執行 `pip install <套件>`，而不是用另一個 shell 的 python。

### 2. 相對路徑找不到檔案？

錯誤訊息會附上「實際執行時的 cwd」。請確認：
- 你傳給 `cwd` 的路徑是否存在
- 該目錄下真的有你要開的檔案

### 3. 為什麼不做 sandbox / 權限控管？

本專案的定位就是「讓 Agent 能真正使用你本機的完整環境」。如果你需要受控執行，請搭配其他 sandbox MCP server 或 Docker 方案。

### 4. 長時間執行會被殺掉？

預設 300 秒（5 分鐘）。如需更長，請在呼叫時傳 `timeout: 1800`（30 分鐘）或更大值（上限 3600）。

### 5. 與 OpenClaw / Claude / Cursor 相容性

本 server 只使用 stdio transport，與所有主流 MCP Client 相容（包含 OpenClaw、Claude Desktop、Claude Code、Cursor、Cline、Windsurf 等）。

## 開發與貢獻

```bash
git clone https://github.com/alex-ht/execute-python-mcp.git
cd execute-python-mcp
pip install -e ".[dev]"   # 如果有 dev 依賴
pytest -v
```

## License

MIT License

Copyright (c) 2026 AlexHT Hung
