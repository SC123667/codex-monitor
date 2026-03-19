# Codex Code Monitor

[![License: MIT](https://img.shields.io/badge/license-MIT-2ea44f.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](requirements.txt)
[![Local only](https://img.shields.io/badge/network-localhost%20only-8a63d2.svg)](#开源友好说明)

Codex Code Monitor 是一个**本地优先**的 Codex CLI 使用监控器，读取 `~/.codex/sessions/**.jsonl` 里的日志，生成更适合长期挂屏查看的 NOC 风格仪表板。

它更像一个“Codex 监控中心”，而不是单纯的统计页：
- 统计 Token 使用量、模型调用次数、最近 5 小时窗口和估算费用
- 强调 5 分钟细粒度槽位、告警层级、实时速率和悬停 drill-down
- 默认只读本地日志，不需要接入远程服务

> 说明：Codex CLI 日志里不一定包含真实账单金额，本工具展示的是**估算值**。默认定价参考 OpenAI 官方文档 `https://developers.openai.com/api/docs/pricing`，并支持本地覆盖模型别名和单价。

## 项目定位

- 适合想观察 Codex 使用习惯、成本趋势和高峰窗口的人
- 适合需要把本机日志做成可读 Dashboard 的用户
- 适合偏开源展示、但又不想暴露个人路径或本地细节的场景

## 核心亮点

- 5 小时滚动窗口主视图，和 `rate_limits.primary` 分开展示，口径更清楚
- 5 分钟粒度 `by_slot` 热区条带，比整点聚合更细
- Web 界面偏监控中心风格，支持 hover drill-down 和大屏模式
- 路径和工作区已做匿名化，便于公开展示
- 终端模式、增强终端模式和 Web 仪表板都保留

## 安装

```bash
python3 -m pip install -r requirements.txt
```

说明：
- Web 仪表板和标准终端模式只依赖 Python 标准库
- 增强终端模式 `python3 monitor.py enhanced` 需要 `rich`

## 启动

```bash
# 推荐：后台启动 Web 仪表板（默认 http://127.0.0.1:8081）
python3 monitor.py

# 前台启动，直接在当前终端看输出，按 Ctrl+C 关闭
python3 monitor.py web

# 已在后台运行时，重新打开页面
python3 monitor.py open

# 停止后台服务
python3 monitor.py stop

# 停止后台服务（别名）
python3 monitor.py close
```

后台模式默认：
- PID 文件：`~/.codex/monitor.pid`
- 日志文件：`~/.codex/monitor.log`
- 如果浏览器没有自动打开，可以直接访问终端输出地址
- `python3 monitor.py open` 会优先复用已有服务，失败时自动尝试重启

## 截图占位

仓库公开前建议补 2-3 张图，最少覆盖这三种状态：
- `docs/screenshots/overview.png` - 首页总览
- `docs/screenshots/drilldown.png` - 图表悬停和 drill-down
- `docs/screenshots/wall-mode.png` - 大屏模式

当前仓库没有附带真实截图，方便你后续按自己的机器重新录制，不暴露本机路径或用户名。

## 配置

推荐把本地配置放到 `~/.codex/monitor_config.json`，也可以通过环境变量指定：

```bash
export CODEX_MONITOR_CONFIG=/path/to/monitor_config.json
```

仓库里提供了可直接复制的示例文件 [monitor_config.example.json](./monitor_config.example.json)。

示例内容会包含：
- `web`：本地绑定地址和端口
- `model_aliases`：模型别名映射
- `pricing_per_million`：按每百万 tokens 计价的本地覆盖值

计费口径：
- `uncached_input = input_tokens - cached_input_tokens`
- `cost = uncached_input*input + cached_input_tokens*cached_input + output_tokens*output`
- 对 `gpt-5.4` / `gpt-5.4-pro`，单次输入超过 `272K` tokens 时会自动套用 long context 规则

## FAQ

- 为什么费用看起来不是“真实账单”？因为 Codex 日志本身通常只有使用数据，没有最终账单。
- 为什么不显示本机路径？因为仓库默认按开源发布标准做了脱敏，避免暴露个人环境信息。
- 为什么 `5 小时` 和 `rate_limits.primary` 两个数不一样？它们本来就是两个信号：一个是本机滚动使用，一个是窗口快照。
- 可以把 Dashboard 暴露到公网吗？不建议，默认只绑定 `127.0.0.1`。
- 想改价格怎么办？直接改本地配置的 `pricing_per_million` 和 `model_aliases` 即可。

## 开源友好说明

- 不要提交 `~/.codex/sessions/**`
- 不要提交 `~/.codex/monitor_config.json`
- 不要提交 `~/.codex/monitor.log` 或 `~/.codex/monitor.pid`
- 默认只监听 localhost，适合本机私用和截图演示
- 如果你 fork 后想让更多人关注，建议补上截图、release notes 和简短的使用场景说明
- 欢迎 `Star`、`Issue` 和 `PR`

## 贡献

如果你想改进它，建议优先做这几类改动：
- 更清晰的图表和更强的 hover 交互
- 更好的配置导入/导出
- 更多模型别名或定价覆盖
- 更完整的截图和演示文案

## 文件结构

```
codex-code-monitor/
├── monitor.py
├── codex_monitor_core.py
├── codex_monitor_simple.py
├── codex_monitor_realtime.py
├── web_dashboard.py
├── monitor_config.example.json
├── LICENSE
└── .gitignore
```
