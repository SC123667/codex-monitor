# Codex Monitor

Local monitoring center for Codex CLI sessions, rolling 5-hour quota pressure, token throughput, and estimated cost.

[![Version](https://img.shields.io/badge/version-v2.4.1-61d6ff)](VERSION)
[![License: MIT](https://img.shields.io/badge/license-MIT-7fe08a.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](#install)
[![GitHub stars](https://img.shields.io/github/stars/SC123667/codex-monitor?style=social)](https://github.com/SC123667/codex-monitor)

`Codex Monitor` 会解析本机 `~/.codex/sessions/**.jsonl` 日志，把零散的使用记录整理成一个更像系统监控中心的本地仪表板。它适合重度 Codex CLI 用户快速看清：

- 最近 5 小时到底用了多少 token
- 官方窗口快照和本地 rolling 5h 是否匹配
- 哪个模型最重、哪个工作区最活跃
- 缓存命中率、输出占比、突增倍率和费用估算

> 费用是估算值，不是官方账单。默认内置 OpenAI 官方定价，并支持本地覆盖定价和模型别名映射。

## Highlights

- NOC 风格 Web 仪表板，强调 5 小时窗口、吞吐、告警态势和模型负载
- 5 分钟粒度的 `by_slot` 滚动窗口，比整点小时聚合更接近真实最近 5 小时
- 同时显示官方 `rate_limits` 快照和本地严格 rolling 5h，避免口径混淆
- 默认本地运行，仅监听 `127.0.0.1`
- 工作区展示默认匿名化，适合截图、演示和后续开源分享
- 支持 Web、标准终端、增强终端三种视图

## Install

要求：

- Python 3.10+
- 本机可访问 Codex CLI 会话日志目录

安装依赖：

```bash
python3 -m pip install -r requirements.txt
```

说明：

- Web 仪表板和标准终端模式只依赖 Python 标准库
- 增强终端模式 `python3 monitor.py enhanced` 需要 `rich`

## Quick Start

```bash
# 推荐：后台启动 Web 仪表板
python3 monitor.py

# 前台启动（当前终端 Ctrl+C 关闭）
python3 monitor.py web

# 后台服务已存在时重新打开
python3 monitor.py open

# 关闭后台服务
python3 monitor.py close
```

默认地址：

- `http://127.0.0.1:8081`

后台模式会在终端直接打印：

- 仪表板地址
- 当前 PID
- 如何关闭程序

## What You See

- `Quota Snapshot`: 最近观测到的官方 5 小时窗口快照
- `Throughput Pulse`: 严格 rolling 5h 的吞吐、事件数和 15 分钟突增比
- `Efficiency Surface`: 缓存命中率、输出占比、活跃模型 / 工作区
- `5H Slots`: 5 分钟粒度热区条带
- `History`: 最近事件、分页历史、模型排行、工作区排行

## Configuration

把配置写到 `~/.codex/monitor_config.json`，或者直接复制仓库里的 [monitor_config.example.json](monitor_config.example.json)。

常见能力：

- 覆盖端口和监听地址
- 自定义模型别名
- 覆盖每百万 tokens 单价

也可以通过环境变量指定配置路径：

```bash
export CODEX_MONITOR_CONFIG=/path/to/monitor_config.json
```

计费口径：

- `uncached_input = input_tokens - cached_input_tokens`
- `cost = uncached_input*input + cached_input_tokens*cached_input + output_tokens*output`
- 对 `gpt-5.4` / `gpt-5.4-pro`，单次输入超过 `272K` tokens 时会自动套用 long context 调整

## Useful Commands

```bash
# 只统计某个工程目录（含子目录）下的会话
python3 monitor.py --cwd "/path/to/project"

# 指定会话日志目录
python3 monitor.py --sessions-dir "/path/to/sessions"

# 指定 Web 端口
python3 monitor.py --port 8888

# 后台启动但不自动开浏览器
python3 monitor.py open --no-browser
```

## Privacy

- 默认只监听 `127.0.0.1`
- 默认界面会把工作区显示成匿名标签，降低截图泄露风险
- 本工具不会把你的日志发送到第三方服务
- 本地原始日志依然可能包含路径、模型名和使用数据，请不要提交 `~/.codex` 内容

更多信息见 [PRIVACY.md](PRIVACY.md) 和 [SECURITY.md](SECURITY.md)。

## Verify Locally

```bash
python3 -m pip install -r requirements.txt
python3 monitor.py open --no-browser
python3 -m compileall monitor.py web_dashboard.py codex_monitor_core.py
```

如果你改了解析逻辑，建议再用自己的 `~/.codex/sessions` 做一次本地验证。

## FAQ

### 为什么“总花费”不等于 OpenAI 账单？

因为这里的费用来自本地日志推算，不是官方结算单。它更适合做趋势监控、模型对比和大致成本感知。

### 为什么要同时显示“官方快照”和“rolling 5h”？

因为日志里的 `rate_limits` 是最近观测到的官方窗口快照，而本地 rolling 5h 是严格按最近 5 小时重新聚合，两者语义不同。

### 会不会暴露本机路径？

当前界面默认会把工作区匿名化为通用标签；但你的本地原始日志和自定义配置仍然属于私密文件，不应提交到仓库。

## Contributing

欢迎提 issue、PR、定价更新和 UI 改进建议。开始前可先看：

- [CONTRIBUTING.md](CONTRIBUTING.md)
- [SECURITY.md](SECURITY.md)
- [CHANGELOG.md](CHANGELOG.md)

## Roadmap

- 更细粒度的时间窗口切换
- 更多模型价格模板和导入方式
- 更完整的大屏 / wall mode
- 更方便的导出和共享摘要能力
