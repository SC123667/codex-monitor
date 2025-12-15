#!/usr/bin/env python3
"""
Codex Code Monitor - 核心解析与统计模块

数据来源：~/.codex/sessions/**.jsonl（Codex CLI 本地会话日志）

统计口径：
- 以 token_count.info.total_token_usage 的“累积计数”做差得到“单次模型调用增量”，避免重复 token_count 事件双计数。
- total_tokens 通常等于 input_tokens + output_tokens；cached_input_tokens / reasoning_output_tokens 为子集信息。
- 费用为“估算值”，按配置的每百万 token 单价计算（input / cached_input / output）。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8081


BUILTIN_PRICING_PER_MILLION: Dict[str, "PricingRatesPerMillion"] = {}
BUILTIN_MODEL_ALIASES: Dict[str, str] = {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def parse_timestamp_local(timestamp_str: str) -> datetime:
    """
    解析日志里的 timestamp（通常为 ISO8601 + Z），转换为本地时间（naive）。
    """
    if not timestamp_str:
        return datetime.now()

    try:
        if timestamp_str.endswith("Z"):
            utc_dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            return utc_dt.astimezone(tz=None).replace(tzinfo=None)

        # 兼容不带时区的 ISO 字符串
        return datetime.fromisoformat(timestamp_str.replace("Z", ""))
    except Exception:
        return datetime.now()


def default_codex_sessions_dir() -> Path:
    return Path.home() / ".codex" / "sessions"


def default_config_path() -> Path:
    return Path.home() / ".codex" / "monitor_config.json"


@dataclass(frozen=True)
class PricingRatesPerMillion:
    input: float
    cached_input: float
    output: float

    @staticmethod
    def from_mapping(mapping: Dict[str, Any]) -> "PricingRatesPerMillion":
        return PricingRatesPerMillion(
            input=_safe_float(mapping.get("input", 0.0)),
            cached_input=_safe_float(mapping.get("cached_input", 0.0)),
            output=_safe_float(mapping.get("output", 0.0)),
        )


# 内置 OpenAI 官方定价（来源：openai.com/api/pricing）
# 说明：默认内置为 Text tokens 的 Standard tier（USD / 1M tokens）。
# Codex CLI 的 model id 可能为别名，会通过 alias/规则映射到这些定价键。
BUILTIN_PRICING_PER_MILLION = {
    # GPT-5.x
    "gpt-5.2": PricingRatesPerMillion(input=1.75, cached_input=0.175, output=14.0),
    "gpt-5.1": PricingRatesPerMillion(input=1.25, cached_input=0.125, output=10.0),
    "gpt-5": PricingRatesPerMillion(input=1.25, cached_input=0.125, output=10.0),
    "gpt-5-mini": PricingRatesPerMillion(input=0.25, cached_input=0.025, output=2.0),
    "gpt-5-nano": PricingRatesPerMillion(input=0.05, cached_input=0.005, output=0.4),
    "gpt-5.2-chat-latest": PricingRatesPerMillion(input=1.75, cached_input=0.175, output=14.0),
    "gpt-5.1-chat-latest": PricingRatesPerMillion(input=1.25, cached_input=0.125, output=10.0),
    "gpt-5-chat-latest": PricingRatesPerMillion(input=1.25, cached_input=0.125, output=10.0),
    "gpt-5.1-codex-max": PricingRatesPerMillion(input=1.25, cached_input=0.125, output=10.0),
    "gpt-5.1-codex": PricingRatesPerMillion(input=1.25, cached_input=0.125, output=10.0),
    "gpt-5-codex": PricingRatesPerMillion(input=1.25, cached_input=0.125, output=10.0),
    "gpt-5.1-codex-mini": PricingRatesPerMillion(input=0.25, cached_input=0.025, output=2.0),
    "codex-mini-latest": PricingRatesPerMillion(input=1.5, cached_input=0.375, output=6.0),
    # cached input 为 '-'：按“无缓存折扣”处理（cached_input = input）
    "gpt-5.2-pro": PricingRatesPerMillion(input=21.0, cached_input=21.0, output=168.0),
    "gpt-5-pro": PricingRatesPerMillion(input=15.0, cached_input=15.0, output=120.0),
    # GPT-4.x / 4o
    "gpt-4.1": PricingRatesPerMillion(input=2.0, cached_input=0.5, output=8.0),
    "gpt-4.1-mini": PricingRatesPerMillion(input=0.4, cached_input=0.1, output=1.6),
    "gpt-4.1-nano": PricingRatesPerMillion(input=0.1, cached_input=0.025, output=0.4),
    "gpt-4o": PricingRatesPerMillion(input=2.5, cached_input=1.25, output=10.0),
    "gpt-4o-2024-05-13": PricingRatesPerMillion(input=5.0, cached_input=5.0, output=15.0),
    "gpt-4o-mini": PricingRatesPerMillion(input=0.15, cached_input=0.075, output=0.6),
    # Realtime / Audio
    "gpt-realtime": PricingRatesPerMillion(input=4.0, cached_input=0.4, output=16.0),
    "gpt-realtime-mini": PricingRatesPerMillion(input=0.6, cached_input=0.06, output=2.4),
    "gpt-4o-realtime-preview": PricingRatesPerMillion(input=5.0, cached_input=2.5, output=20.0),
    "gpt-4o-mini-realtime-preview": PricingRatesPerMillion(input=0.6, cached_input=0.3, output=2.4),
    "gpt-audio": PricingRatesPerMillion(input=2.5, cached_input=2.5, output=10.0),
    "gpt-audio-mini": PricingRatesPerMillion(input=0.6, cached_input=0.6, output=2.4),
    "gpt-4o-audio-preview": PricingRatesPerMillion(input=2.5, cached_input=2.5, output=10.0),
    "gpt-4o-mini-audio-preview": PricingRatesPerMillion(input=0.15, cached_input=0.15, output=0.6),
    # o-series
    "o1": PricingRatesPerMillion(input=15.0, cached_input=7.5, output=60.0),
    "o1-pro": PricingRatesPerMillion(input=150.0, cached_input=150.0, output=600.0),
    "o1-mini": PricingRatesPerMillion(input=1.1, cached_input=0.55, output=4.4),
    "o3": PricingRatesPerMillion(input=2.0, cached_input=0.5, output=8.0),
    "o3-pro": PricingRatesPerMillion(input=20.0, cached_input=20.0, output=80.0),
    "o3-deep-research": PricingRatesPerMillion(input=10.0, cached_input=2.5, output=40.0),
    "o3-mini": PricingRatesPerMillion(input=1.1, cached_input=0.55, output=4.4),
    "o4-mini": PricingRatesPerMillion(input=1.1, cached_input=0.275, output=4.4),
    "o4-mini-deep-research": PricingRatesPerMillion(input=2.0, cached_input=0.5, output=8.0),
    # Search / Tools
    "gpt-5-search-api": PricingRatesPerMillion(input=1.25, cached_input=0.125, output=10.0),
    "gpt-4o-mini-search-preview": PricingRatesPerMillion(input=0.15, cached_input=0.15, output=0.6),
    "gpt-4o-search-preview": PricingRatesPerMillion(input=2.5, cached_input=2.5, output=10.0),
    "computer-use-preview": PricingRatesPerMillion(input=3.0, cached_input=3.0, output=12.0),
    # Image (text tokens only; output 为 '-' 表示不按 text output token 计费)
    "gpt-image-1": PricingRatesPerMillion(input=5.0, cached_input=1.25, output=0.0),
    "gpt-image-1-mini": PricingRatesPerMillion(input=2.0, cached_input=0.2, output=0.0),
}

BUILTIN_MODEL_ALIASES = {
    # Codex CLI 常见别名
    "gpt-5.1-codex-max": "gpt-5.1",
    "gpt-5.1-codex": "gpt-5.1",
    "gpt-5.1-codex-mini": "gpt-5-mini",
    "gpt-5-codex": "gpt-5",
}


@dataclass(frozen=True)
class MonitorConfig:
    host: str
    port: int
    pricing_per_million: Dict[str, PricingRatesPerMillion]
    model_aliases: Dict[str, str]

    @staticmethod
    def load(path: Optional[Path] = None) -> "MonitorConfig":
        env_path = os.environ.get("CODEX_MONITOR_CONFIG")
        config_path = path or (Path(env_path) if env_path else default_config_path())

        host = DEFAULT_HOST
        port = DEFAULT_PORT
        # 先加载内置定价，再允许配置文件覆盖。
        pricing: Dict[str, PricingRatesPerMillion] = dict(BUILTIN_PRICING_PER_MILLION)
        # default 兜底（仍然允许你在配置里覆盖）
        pricing.setdefault("default", PricingRatesPerMillion(input=0.0, cached_input=0.0, output=0.0))

        aliases: Dict[str, str] = dict(BUILTIN_MODEL_ALIASES)

        try:
            if config_path and Path(config_path).exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    raw = json.load(f) or {}

                web = raw.get("web", {}) if isinstance(raw.get("web", {}), dict) else {}
                host = str(web.get("host", host))
                port = _safe_int(web.get("port", port), port)

                raw_pricing = raw.get("pricing_per_million", {})
                if isinstance(raw_pricing, dict):
                    for model_name, model_rates in raw_pricing.items():
                        if isinstance(model_rates, dict):
                            pricing[str(model_name)] = PricingRatesPerMillion.from_mapping(model_rates)

                raw_aliases = raw.get("model_aliases", {})
                if isinstance(raw_aliases, dict):
                    for k, v in raw_aliases.items():
                        if isinstance(k, str) and isinstance(v, str) and k and v:
                            aliases[k] = v
        except Exception:
            # 配置文件坏了也不影响使用：继续用默认值
            pass

        return MonitorConfig(host=host, port=port, pricing_per_million=pricing, model_aliases=aliases)

    def rates_for_model(self, model: str) -> Tuple[PricingRatesPerMillion, str]:
        """
        返回 (单价, 来源标识)。
        来源标识用于调试：direct / alias / heuristic / default / zero
        """
        if model in self.pricing_per_million:
            return self.pricing_per_million[model], "direct"

        alias = self.model_aliases.get(model)
        if alias and alias in self.pricing_per_million:
            return self.pricing_per_million[alias], f"alias:{alias}"

        canonical = canonicalize_model_id(model)
        if canonical and canonical in self.pricing_per_million:
            return self.pricing_per_million[canonical], f"heuristic:{canonical}"

        if "default" in self.pricing_per_million:
            return self.pricing_per_million["default"], "default"
        return PricingRatesPerMillion(input=0.0, cached_input=0.0, output=0.0), "zero"


def canonicalize_model_id(model: str) -> Optional[str]:
    """
    将 Codex CLI 里出现的模型 id 归一到 OpenAI 定价键（尽量保守）。
    """
    if not model:
        return None

    m = str(model).strip().lower()

    # GPT-5.x
    if m.startswith("gpt-5") and "mini" in m:
        return "gpt-5-mini"
    if m.startswith("gpt-5") and "nano" in m:
        return "gpt-5-nano"
    if m.startswith("gpt-5.2"):
        if "pro" in m:
            return "gpt-5.2-pro"
        return "gpt-5.2"
    if m.startswith("gpt-5.1"):
        return "gpt-5.1"
    if m == "gpt-5":
        return "gpt-5"

    # Codex / Max 等：尽量按版本归一（可在 model_aliases 覆盖）
    if m.startswith("gpt-5") and ("codex" in m or "max" in m):
        if "5.2" in m:
            return "gpt-5.2"
        if "5.1" in m:
            return "gpt-5.1"
        return "gpt-5"

    return None


@dataclass
class UsageDelta:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    total_tokens: int = 0

    @staticmethod
    def from_total_usage(total_usage: Dict[str, Any]) -> "UsageDelta":
        return UsageDelta(
            input_tokens=_safe_int(total_usage.get("input_tokens", 0)),
            cached_input_tokens=_safe_int(total_usage.get("cached_input_tokens", 0)),
            output_tokens=_safe_int(total_usage.get("output_tokens", 0)),
            reasoning_output_tokens=_safe_int(total_usage.get("reasoning_output_tokens", 0)),
            total_tokens=_safe_int(total_usage.get("total_tokens", 0)),
        )

    def diff(self, previous: "UsageDelta") -> "UsageDelta":
        return UsageDelta(
            input_tokens=self.input_tokens - previous.input_tokens,
            cached_input_tokens=self.cached_input_tokens - previous.cached_input_tokens,
            output_tokens=self.output_tokens - previous.output_tokens,
            reasoning_output_tokens=self.reasoning_output_tokens - previous.reasoning_output_tokens,
            total_tokens=self.total_tokens - previous.total_tokens,
        )


@dataclass
class RateLimitSnapshot:
    used_percent: Optional[float] = None
    window_minutes: Optional[int] = None
    resets_at: Optional[datetime] = None
    resets_in_seconds: Optional[int] = None

    @staticmethod
    def from_payload(timestamp_local: datetime, rate_limits: Dict[str, Any]) -> "RateLimitSnapshot":
        primary = rate_limits.get("primary", {}) if isinstance(rate_limits, dict) else {}
        used_percent = primary.get("used_percent")
        window_minutes = primary.get("window_minutes")

        resets_at_dt: Optional[datetime] = None
        resets_in_seconds: Optional[int] = None

        if isinstance(primary, dict):
            if "resets_at" in primary:
                resets_at_epoch = primary.get("resets_at")
                try:
                    resets_at_dt = datetime.fromtimestamp(float(resets_at_epoch), tz=timezone.utc).astimezone(tz=None).replace(tzinfo=None)
                except Exception:
                    resets_at_dt = None
            if "resets_in_seconds" in primary:
                resets_in_seconds = _safe_int(primary.get("resets_in_seconds", None), 0)

        # 如果只有 resets_in_seconds，可以估算 resets_at（以当前事件时间为基准）
        if resets_at_dt is None and resets_in_seconds is not None and resets_in_seconds > 0:
            resets_at_dt = timestamp_local + timedelta(seconds=resets_in_seconds)

        return RateLimitSnapshot(
            used_percent=_safe_float(used_percent, None) if used_percent is not None else None,
            window_minutes=_safe_int(window_minutes, None) if window_minutes is not None else None,
            resets_at=resets_at_dt,
            resets_in_seconds=resets_in_seconds if resets_in_seconds and resets_in_seconds > 0 else None,
        )


@dataclass
class UsageEvent:
    timestamp: datetime
    model: str
    cwd: Optional[str]
    delta: UsageDelta
    estimated_cost_usd: float
    pricing_source: str


def _path_matches_filter(candidate: Optional[str], cwd_filter: Optional[str]) -> bool:
    if not cwd_filter:
        return True
    if not candidate:
        return False
    try:
        candidate_path = Path(candidate).resolve()
        filter_path = Path(cwd_filter).resolve()
        return candidate_path == filter_path or filter_path in candidate_path.parents
    except Exception:
        return False


def estimate_cost_usd(model: str, delta: UsageDelta, config: MonitorConfig) -> Tuple[float, str]:
    rates, source = config.rates_for_model(model)

    # cached_input_tokens 是 input_tokens 的子集，按“未缓存输入 + 缓存输入”分别计价
    cached = max(0, delta.cached_input_tokens)
    input_total = max(0, delta.input_tokens)
    uncached = max(0, input_total - cached)
    output = max(0, delta.output_tokens)

    cost = 0.0
    cost += uncached * rates.input / 1_000_000
    cost += cached * rates.cached_input / 1_000_000
    cost += output * rates.output / 1_000_000
    return cost, source


def iter_session_files(sessions_dir: Path) -> List[Path]:
    if not sessions_dir.exists():
        return []
    files = [p for p in sessions_dir.glob("**/*.jsonl") if p.is_file()]
    # 按路径排序，便于稳定输出；后续会再按事件时间排序
    files.sort()
    return files


def parse_usage_events_from_session_file(
    file_path: Path,
    config: MonitorConfig,
    cwd_filter: Optional[str] = None,
) -> Tuple[List[UsageEvent], Optional[RateLimitSnapshot]]:
    events: List[UsageEvent] = []
    latest_rl: Optional[RateLimitSnapshot] = None

    current_model: str = "unknown"
    current_cwd: Optional[str] = None

    prev_total: Optional[UsageDelta] = None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line:
                    continue

                # 只解析关键信息，避免处理巨大 encrypted_content 行
                if '"type":"session_meta"' in line:
                    try:
                        obj = json.loads(line)
                        payload = obj.get("payload", {}) if isinstance(obj, dict) else {}
                        cwd = payload.get("cwd")
                        if isinstance(cwd, str) and cwd:
                            current_cwd = cwd
                    except Exception:
                        pass
                    continue

                if '"type":"turn_context"' in line:
                    try:
                        obj = json.loads(line)
                        payload = obj.get("payload", {}) if isinstance(obj, dict) else {}
                        model = payload.get("model")
                        cwd = payload.get("cwd")
                        if isinstance(model, str) and model:
                            current_model = model
                        if isinstance(cwd, str) and cwd:
                            current_cwd = cwd
                    except Exception:
                        pass
                    continue

                if '"type":"token_count"' not in line:
                    continue

                try:
                    obj = json.loads(line)
                except Exception:
                    continue

                if not isinstance(obj, dict):
                    continue

                ts_local = parse_timestamp_local(str(obj.get("timestamp", "")))
                payload = obj.get("payload", {}) if isinstance(obj.get("payload", {}), dict) else {}

                # rate_limits 也可能存在于 info 为 null 的 token_count 事件里
                rl = payload.get("rate_limits")
                if isinstance(rl, dict):
                    snapshot = RateLimitSnapshot.from_payload(ts_local, rl)
                    # 以时间为准保留最新的
                    if latest_rl is None or (snapshot.resets_at and latest_rl.resets_at and snapshot.resets_at >= latest_rl.resets_at) or ts_local >= (latest_rl.resets_at or datetime.min):
                        latest_rl = snapshot

                info = payload.get("info")
                if not isinstance(info, dict):
                    continue

                total_usage = info.get("total_token_usage")
                if not isinstance(total_usage, dict):
                    continue

                current_total = UsageDelta.from_total_usage(total_usage)
                if prev_total is None:
                    delta = current_total
                else:
                    delta = current_total.diff(prev_total)
                prev_total = current_total

                if delta.total_tokens <= 0:
                    continue

                if not _path_matches_filter(current_cwd, cwd_filter):
                    continue

                cost, pricing_source = estimate_cost_usd(current_model, delta, config)
                events.append(
                    UsageEvent(
                        timestamp=ts_local,
                        model=current_model,
                        cwd=current_cwd,
                        delta=delta,
                        estimated_cost_usd=cost,
                        pricing_source=pricing_source,
                    )
                )
    except FileNotFoundError:
        return [], None
    except Exception:
        # 单个文件坏了不影响整体
        return events, latest_rl

    return events, latest_rl


def build_usage_summary(
    sessions_dir: Optional[Path] = None,
    config: Optional[MonitorConfig] = None,
    cwd_filter: Optional[str] = None,
    now: Optional[datetime] = None,
    include_events: bool = False,
) -> Dict[str, Any]:
    """
    读取 ~/.codex/sessions 并汇总：
    - 总 token / 总调用次数 / 总费用（估算）
    - 最近 5 小时 token / 次数 / 费用
    - 按模型、按日期、按 cwd 统计
    - 最新 rate_limits(primary) 快照
    """

    cfg = config or MonitorConfig.load()
    sessions = sessions_dir or default_codex_sessions_dir()

    current_time = now or datetime.now()
    five_hours_ago = current_time - timedelta(hours=5)
    week_start = (current_time - timedelta(days=current_time.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)

    all_events: List[UsageEvent] = []
    latest_rl: Optional[RateLimitSnapshot] = None

    for file_path in iter_session_files(sessions):
        events, rl = parse_usage_events_from_session_file(file_path, cfg, cwd_filter=cwd_filter)
        all_events.extend(events)
        if rl is not None:
            if latest_rl is None:
                latest_rl = rl
            else:
                # 按 resets_at 优先，其次保留较新的
                if rl.resets_at and (not latest_rl.resets_at or rl.resets_at > latest_rl.resets_at):
                    latest_rl = rl

    all_events.sort(key=lambda e: e.timestamp)

    def empty_stats() -> Dict[str, Any]:
        return {
            "calls": 0,
            "total_tokens": 0,
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_output_tokens": 0,
            "estimated_cost_usd": 0.0,
        }

    total = empty_stats()
    by_model: Dict[str, Dict[str, Any]] = {}
    by_date: Dict[str, Dict[str, Any]] = {}
    by_hour: Dict[str, Dict[str, Any]] = {}
    by_cwd: Dict[str, Dict[str, Any]] = {}

    five_hour = empty_stats()
    five_hour_by_hour: Dict[str, Dict[str, Any]] = {}
    five_hour_by_model: Dict[str, Dict[str, Any]] = {}

    this_week = empty_stats()
    this_week_by_date: Dict[str, Dict[str, Any]] = {}
    this_week_by_model: Dict[str, Dict[str, Any]] = {}

    for event in all_events:
        delta = event.delta

        def apply(stats: Dict[str, Any]):
            stats["calls"] += 1
            stats["total_tokens"] += max(0, delta.total_tokens)
            stats["input_tokens"] += max(0, delta.input_tokens)
            stats["cached_input_tokens"] += max(0, delta.cached_input_tokens)
            stats["output_tokens"] += max(0, delta.output_tokens)
            stats["reasoning_output_tokens"] += max(0, delta.reasoning_output_tokens)
            stats["estimated_cost_usd"] += float(event.estimated_cost_usd)

        apply(total)

        model_key = event.model or "unknown"
        if model_key not in by_model:
            by_model[model_key] = empty_stats()
        apply(by_model[model_key])

        date_key = event.timestamp.strftime("%Y-%m-%d")
        if date_key not in by_date:
            by_date[date_key] = empty_stats()
        apply(by_date[date_key])

        hour_key = event.timestamp.strftime("%Y-%m-%d %H:00")
        if hour_key not in by_hour:
            by_hour[hour_key] = empty_stats()
        apply(by_hour[hour_key])

        cwd_key = event.cwd or "unknown"
        if cwd_key not in by_cwd:
            by_cwd[cwd_key] = empty_stats()
        apply(by_cwd[cwd_key])

        if event.timestamp >= five_hours_ago:
            apply(five_hour)
            if hour_key not in five_hour_by_hour:
                five_hour_by_hour[hour_key] = empty_stats()
            apply(five_hour_by_hour[hour_key])

            if model_key not in five_hour_by_model:
                five_hour_by_model[model_key] = empty_stats()
            apply(five_hour_by_model[model_key])

        if event.timestamp >= week_start:
            apply(this_week)
            if date_key not in this_week_by_date:
                this_week_by_date[date_key] = empty_stats()
            apply(this_week_by_date[date_key])

            if model_key not in this_week_by_model:
                this_week_by_model[model_key] = empty_stats()
            apply(this_week_by_model[model_key])

    # 补齐窗口明细里的空桶，便于前端稳定展示
    start_hour = (current_time - timedelta(hours=5)).replace(minute=0, second=0, microsecond=0)
    end_hour = current_time.replace(minute=0, second=0, microsecond=0)
    t = start_hour
    while t <= end_hour:
        k = t.strftime("%Y-%m-%d %H:00")
        if k not in five_hour_by_hour:
            five_hour_by_hour[k] = empty_stats()
        t += timedelta(hours=1)

    d = week_start.date()
    end_d = current_time.date()
    while d <= end_d:
        k = d.strftime("%Y-%m-%d")
        if k not in this_week_by_date:
            this_week_by_date[k] = empty_stats()
        d += timedelta(days=1)

    recent_events = sorted(all_events, key=lambda e: e.timestamp, reverse=True)[:50]
    recent_calls = [
        {
            "timestamp": e.timestamp.isoformat(sep=" ", timespec="seconds"),
            "model": e.model,
            "cwd": e.cwd,
            "total_tokens": e.delta.total_tokens,
            "input_tokens": e.delta.input_tokens,
            "cached_input_tokens": e.delta.cached_input_tokens,
            "output_tokens": e.delta.output_tokens,
            "estimated_cost_usd": round(e.estimated_cost_usd, 6),
            "pricing_source": e.pricing_source,
        }
        for e in recent_events
    ]

    def _series_rows(stats_by_key: Dict[str, Dict[str, Any]], key_name: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for k in sorted(stats_by_key.keys()):
            st = stats_by_key[k]
            rows.append(
                {
                    key_name: k,
                    "calls": int(st.get("calls", 0)),
                    "total_tokens": int(st.get("total_tokens", 0)),
                    "input_tokens": int(st.get("input_tokens", 0)),
                    "cached_input_tokens": int(st.get("cached_input_tokens", 0)),
                    "output_tokens": int(st.get("output_tokens", 0)),
                    "reasoning_output_tokens": int(st.get("reasoning_output_tokens", 0)),
                    "estimated_cost_usd": round(float(st.get("estimated_cost_usd", 0.0)), 6),
                }
            )
        return rows

    series = {
        "by_date": _series_rows(by_date, "date"),
        "by_hour": _series_rows(by_hour, "hour"),
    }

    def _top_rows(stats_by_key: Dict[str, Dict[str, Any]], key_name: str, limit: int = 15) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for k, st in stats_by_key.items():
            rows.append(
                {
                    key_name: k,
                    "calls": int(st.get("calls", 0)),
                    "total_tokens": int(st.get("total_tokens", 0)),
                    "input_tokens": int(st.get("input_tokens", 0)),
                    "cached_input_tokens": int(st.get("cached_input_tokens", 0)),
                    "output_tokens": int(st.get("output_tokens", 0)),
                    "reasoning_output_tokens": int(st.get("reasoning_output_tokens", 0)),
                    "estimated_cost_usd": round(float(st.get("estimated_cost_usd", 0.0)), 6),
                }
            )
        rows.sort(key=lambda r: (r.get("total_tokens", 0), r.get("estimated_cost_usd", 0.0)), reverse=True)
        return rows[: max(1, int(limit))]

    windows = {
        "last_5_hours": {
            "total": five_hour,
            "by_hour": _series_rows(five_hour_by_hour, "hour"),
            "by_model": _top_rows(five_hour_by_model, "model", 15),
        },
        "this_week": {
            "range": {
                "start": week_start.isoformat(sep=" ", timespec="seconds"),
                "end": current_time.isoformat(sep=" ", timespec="seconds"),
            },
            "total": this_week,
            "by_date": _series_rows(this_week_by_date, "date"),
            "by_model": _top_rows(this_week_by_model, "model", 15),
        },
    }

    rate_limits = None
    if latest_rl is not None:
        remaining_seconds = None
        if latest_rl.resets_at is not None:
            remaining_seconds = max(0, int((latest_rl.resets_at - current_time).total_seconds()))
        elif latest_rl.resets_in_seconds is not None:
            remaining_seconds = max(0, int(latest_rl.resets_in_seconds))

        rate_limits = {
            "primary": {
                "used_percent": latest_rl.used_percent,
                "window_minutes": latest_rl.window_minutes,
                "resets_at": latest_rl.resets_at.isoformat(sep=" ", timespec="seconds") if latest_rl.resets_at else None,
                "remaining_seconds": remaining_seconds,
            }
        }

    summary: Dict[str, Any] = {
        "source": {
            "sessions_dir": str(sessions),
            "cwd_filter": cwd_filter,
            "files": len(iter_session_files(sessions)),
        },
        "total": total,
        "five_hour": five_hour,
        "by_model": by_model,
        "by_date": by_date,
        "by_hour": by_hour,
        "by_cwd": by_cwd,
        "recent_calls": recent_calls,
        "series": series,
        "windows": windows,
        "rate_limits": rate_limits,
        "generated_at": current_time.isoformat(sep=" ", timespec="seconds"),
        "note": "费用为估算值：默认使用内置 OpenAI 官方定价（openai.com/api/pricing）；也可在 ~/.codex/monitor_config.json 覆盖 pricing_per_million / model_aliases。",
    }

    if include_events:
        events_payload: List[Dict[str, Any]] = []
        for e in reversed(all_events):
            delta = e.delta
            rates, _ = cfg.rates_for_model(e.model)

            cached = max(0, int(delta.cached_input_tokens))
            input_total = max(0, int(delta.input_tokens))
            uncached = max(0, input_total - cached)
            output = max(0, int(delta.output_tokens))

            cost_uncached = uncached * float(rates.input) / 1_000_000
            cost_cached = cached * float(rates.cached_input) / 1_000_000
            cost_output = output * float(rates.output) / 1_000_000
            cost_total = cost_uncached + cost_cached + cost_output

            events_payload.append(
                {
                    "timestamp": e.timestamp.isoformat(sep=" ", timespec="seconds"),
                    "model": e.model,
                    "cwd": e.cwd,
                    "pricing_source": e.pricing_source,
                    "tokens": {
                        "input": input_total,
                        "cached_input": cached,
                        "uncached_input": uncached,
                        "output": output,
                        "reasoning_output": max(0, int(delta.reasoning_output_tokens)),
                        "total": max(0, int(delta.total_tokens)),
                    },
                    "rates_per_million": {
                        "input": float(rates.input),
                        "cached_input": float(rates.cached_input),
                        "output": float(rates.output),
                    },
                    "cost_usd": {
                        "uncached_input": round(cost_uncached, 6),
                        "cached_input": round(cost_cached, 6),
                        "output": round(cost_output, 6),
                        "total": round(cost_total, 6),
                    },
                }
            )
        summary["events"] = events_payload
        summary["events_count"] = len(events_payload)

    return summary
