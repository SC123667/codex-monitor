# Codex Code Monitor (Local)

本工具用于**解析 Codex CLI 的本地日志**（`~/.codex/sessions/**.jsonl`），提供一个本地 Web 仪表板来统计：
- Token 使用量（输入/缓存输入/输出）
- 调用模型次数（按 token_count 增量去重）
- 最近 5 小时用量（本机日志口径）
- 5 小时窗口用量百分比与重置时间（来自 `rate_limits.primary`）
- 估算费用（默认按 OpenAI 官方定价计算，可覆盖）
- 趋势折线图（Tokens / Cost）
- 历史调用明细（分页、过滤、单价与费用拆分展示）
- 最近 5 小时 / 本周明细（分桶 + Top 模型）

> 说明：Codex CLI 日志里不一定包含真实账单金额，本工具的“费用”为**估算值**。默认内置 OpenAI 官方定价（来源：`openai.com/api/pricing`）；你也可以在配置里覆盖单价或调整模型别名映射。

## 快速开始

进入本目录后运行：

```bash
# 推荐：直接后台启动 Web 仪表板（默认 http://127.0.0.1:8081）
python3 monitor.py

# 前台启动（Ctrl+C 停止）
python3 monitor.py web

# 停止后台服务
python3 monitor.py stop
```

## 安全与隐私

- 默认只监听 `127.0.0.1`（不要轻易改成 `0.0.0.0`）
- 会展示本机路径（`cwd`）等信息，分享截图/导出的 JSON 前请注意脱敏

更多说明见：`SECURITY.md`、`PRIVACY.md`。

## Web 后台运行

```bash
# 后台启动（等价于 python3 monitor.py）
python3 monitor.py background

# 停止后台服务
python3 monitor.py stop
```

后台模式默认：
- PID 文件：`~/.codex/monitor.pid`
- 日志文件：`~/.codex/monitor.log`
- 如果浏览器未自动打开，请手动访问终端输出的地址（默认 `http://127.0.0.1:8081`）

## 费用单价配置（可选）

在 `~/.codex/monitor_config.json` 写入（示例）：

```json
{
  "web": { "host": "127.0.0.1", "port": 8081 },
  "model_aliases": {
    "gpt-5-codex": "gpt-5",
    "gpt-5.1-codex-max": "gpt-5.1"
  },
  "pricing_per_million": {
    "default": { "input": 0, "cached_input": 0, "output": 0 },
    "gpt-5.2": { "input": 1.75, "cached_input": 0.175, "output": 14.0 },
    "gpt-5.1": { "input": 1.25, "cached_input": 0.125, "output": 10.0 },
    "gpt-5": { "input": 1.25, "cached_input": 0.125, "output": 10.0 },
    "gpt-5-mini": { "input": 0.25, "cached_input": 0.025, "output": 2.0 },
    "gpt-5.2-pro": { "input": 21.0, "cached_input": 21.0, "output": 168.0 }
  }
}
```

计费口径：
- `uncached_input = input_tokens - cached_input_tokens`
- `cost = uncached_input*input + cached_input_tokens*cached_input + output_tokens*output`（单位：USD / 1M tokens）

你也可以通过环境变量指定配置文件路径：

```bash
export CODEX_MONITOR_CONFIG=/path/to/monitor_config.json
```

## 常用参数

```bash
# 只统计某个工程目录（含子目录）下的会话
python3 monitor.py --cwd "/path/to/project"

# 指定会话日志目录（默认 ~/.codex/sessions）
python3 monitor.py --sessions-dir "/path/to/sessions"

# 指定 Web 端口
python3 monitor.py --port 8888
```

## 文件结构

```
codex-code-monitor/
├── monitor.py
├── codex_monitor_core.py
├── codex_monitor_simple.py
├── codex_monitor_realtime.py
└── web_dashboard.py
```
