#!/usr/bin/env python3
"""
Codex Code Monitor - 统一启动入口

功能：
- Web 仪表板（美化增强版）
- 增强版终端监控（Rich 库）
- 标准版终端监控
- 后台运行/停止（写入 ~/.codex/monitor.pid）

美化版本：v2.4.0 (2026-03-19)
- 指挥台级监控中心布局
- 5 小时配额快照匹配修正
- 路径脱敏与图表交互增强
- 启动链路补强，支持重新打开仪表板
- 大屏模式、hover drill-down 与关闭提示增强
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from codex_monitor_core import DEFAULT_HOST, DEFAULT_PORT, MonitorConfig


def _script_path(name: str) -> Path:
    return Path(__file__).parent / name


def _resolve_host_port(args) -> tuple[str, int]:
    try:
        config_path = Path(args.config).expanduser() if getattr(args, "config", None) else None
        cfg = MonitorConfig.load(config_path)
        host = args.host or cfg.host or DEFAULT_HOST
        port = args.port or cfg.port or DEFAULT_PORT
        return host, int(port)
    except Exception:
        host = getattr(args, "host", None) or DEFAULT_HOST
        port = getattr(args, "port", None) or DEFAULT_PORT
        return host, int(port)


def _local_dashboard_build() -> Optional[str]:
    try:
        web_script = _script_path("web_dashboard.py")
        return datetime.fromtimestamp(web_script.stat().st_mtime).isoformat(sep=" ", timespec="seconds")
    except Exception:
        return None


def _fetch_running_server_info(url: str) -> tuple[Optional[str], bool]:
    try:
        import json
        import urllib.request

        with urllib.request.urlopen(url + "/api/data", timeout=1) as resp:
            raw = resp.read()
        obj = json.loads(raw.decode("utf-8", errors="replace"))
        if isinstance(obj, dict) and isinstance(obj.get("data"), dict):
            obj = obj.get("data")  # type: ignore[assignment]
        if not isinstance(obj, dict):
            return None, False

        is_monitor = isinstance(obj.get("source"), dict) and isinstance(obj.get("total"), dict)
        server = obj.get("server") if isinstance(obj.get("server"), dict) else {}
        build = server.get("build") if isinstance(server, dict) else None
        build_str = build if isinstance(build, str) and build else None
        return build_str, bool(is_monitor)
    except Exception:
        return None, False


def _is_server_healthy(url: str) -> bool:
    try:
        import urllib.request

        with urllib.request.urlopen(url + "/healthz", timeout=1.5) as resp:
            raw = resp.read().decode("utf-8", errors="replace").strip().lower()
        return resp.status == 200 and raw == "ok"
    except Exception:
        return False


def _wait_for_server(url: str, timeout_seconds: float = 8.0) -> bool:
    deadline = time.time() + max(timeout_seconds, 0.5)
    while time.time() < deadline:
        if _is_server_healthy(url):
            return True
        time.sleep(0.4)
    return _is_server_healthy(url)


def _try_open_browser(url: str) -> bool:
    try:
        import webbrowser

        if webbrowser.open(url, new=2):
            return True
    except Exception:
        pass

    try:
        if sys.platform.startswith("darwin"):
            subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        if sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        if os.name == "nt":
            os.startfile(url)  # type: ignore[attr-defined]
            return True
    except Exception:
        pass

    return False


def run_web_dashboard(args) -> int:
    web_script = _script_path("web_dashboard.py")
    if not web_script.exists():
        print(f"❌ 找不到文件: {web_script}")
        return 1

    cmd = [sys.executable, str(web_script)]
    if args.port:
        cmd += ["--port", str(args.port)]
    if args.host:
        cmd += ["--host", str(args.host)]
    if args.no_browser:
        cmd.append("--no-browser")
    if args.sessions_dir:
        cmd += ["--sessions-dir", args.sessions_dir]
    if args.config:
        cmd += ["--config", args.config]
    if args.cwd:
        cmd += ["--cwd", args.cwd]

    host, port = _resolve_host_port(args)
    print(f"🚀 启动 Web 仪表板... (http://{host}:{port})")
    print("关闭方式: 当前终端按 Ctrl+C")
    return subprocess.run(cmd).returncode


def open_dashboard(args) -> int:
    host, port = _resolve_host_port(args)
    url = f"http://{host}:{port}"

    if not _wait_for_server(url, timeout_seconds=1.5):
        print("ℹ️  未检测到可访问的监控服务，正在后台启动...")
        rc = run_background(args)
        if rc != 0:
            return rc

    print(f"🌐 仪表板地址: {url}")
    print(f"关闭命令: python3 {Path(__file__).name} stop")
    if args.no_browser:
        return 0
    if _try_open_browser(url):
        print("✅ 已尝试在浏览器中打开仪表板")
        return 0

    print(f"⚠️  浏览器未自动打开，请手动访问：{url}")
    return 0


def run_background(args) -> int:
    web_script = _script_path("web_dashboard.py")
    if not web_script.exists():
        print(f"❌ 找不到文件: {web_script}")
        return 1

    pid_file = Path.home() / ".codex" / "monitor.pid"
    log_file = Path(args.log_file).expanduser() if args.log_file else (Path.home() / ".codex" / "monitor.log")

    # 检查是否已经运行
    if pid_file.exists():
        try:
            old_pid = int(pid_file.read_text(encoding="utf-8").strip())
            os.kill(old_pid, 0)
            host, port = _resolve_host_port(args)
            url = f"http://{host}:{port}"
            local_build = _local_dashboard_build()
            running_build, is_monitor = _fetch_running_server_info(url)
            healthy = _is_server_healthy(url)
            if not healthy or not is_monitor:
                print("♻️  检测到已有后台进程但服务不可用，正在自动重启...")
                stop_rc = stop_background()
                if stop_rc != 0:
                    print("⚠️  自动重启失败：请先运行 stop 再启动。")
                    print(f"停止命令: python3 {Path(__file__).name} stop")
                    print(f"地址: {url}")
                    return stop_rc
            elif local_build and running_build != local_build:
                print("♻️  检测到后台服务为旧版本，正在自动重启以应用更新…")
                stop_rc = stop_background()
                if stop_rc != 0:
                    print("⚠️  自动重启失败：请先运行 stop 再启动。")
                    print(f"停止命令: python3 {Path(__file__).name} stop")
                    print(f"地址: {url}")
                    return stop_rc
            else:
                print(f"⚠️  监控器已在运行中 (PID: {old_pid})")
                print(f"地址: {url}")
                print(f"关闭命令: python3 {Path(__file__).name} stop")
                print(f"重新打开: python3 {Path(__file__).name} open")
                if not args.no_browser:
                    if not _try_open_browser(url):
                        print(f"🌐 浏览器未自动打开，请手动访问：{url}")
                return 0
        except Exception:
            try:
                pid_file.unlink()
            except Exception:
                pass

    log_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.parent.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, str(web_script), "--no-browser"]
    if args.port:
        cmd += ["--port", str(args.port)]
    if args.host:
        cmd += ["--host", str(args.host)]
    if args.sessions_dir:
        cmd += ["--sessions-dir", args.sessions_dir]
    if args.config:
        cmd += ["--config", args.config]
    if args.cwd:
        cmd += ["--cwd", args.cwd]

    with open(log_file, "a", encoding="utf-8") as log:
        process = subprocess.Popen(cmd, stdout=log, stderr=log, start_new_session=True)

    pid_file.write_text(str(process.pid), encoding="utf-8")

    host, port = _resolve_host_port(args)
    url = f"http://{host}:{port}"

    print("🚀 已后台启动 Codex Code Monitor")
    print(f"PID: {process.pid}")
    print(f"地址: {url}")
    print(f"日志: {log_file}")
    print(f"关闭命令: python3 {Path(__file__).name} stop")
    print(f"重新打开: python3 {Path(__file__).name} open")

    if _wait_for_server(url, timeout_seconds=10):
        print("✅ 健康检查通过")
    else:
        print("⚠️  服务启动超时，请先查看日志后再重试。")
        print(f"日志: {log_file}")
        print(f"前台排查: python3 {Path(__file__).name} web")
        return 1

    if not args.no_browser:
        if not _try_open_browser(url):
            print(f"🌐 浏览器未自动打开，请手动访问：{url}")

    return 0


def stop_background() -> int:
    pid_file = Path.home() / ".codex" / "monitor.pid"
    if not pid_file.exists():
        print("❌ 没有找到运行中的服务")
        return 1

    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        os.kill(pid, signal.SIGTERM)
        print(f"✅ 已发送停止信号到进程 {pid}")
        for _ in range(10):
            try:
                os.kill(pid, 0)
                time.sleep(0.5)
            except ProcessLookupError:
                break
        try:
            pid_file.unlink()
        except FileNotFoundError:
            pass
        print("✅ 服务已停止")
        return 0
    except Exception as e:
        print(f"❌ 停止失败: {e}")
        try:
            pid_file.unlink()
        except Exception:
            pass
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Codex Code Monitor - 美化增强版 v2.0",
        epilog="""
使用示例：
  python3 monitor.py              # 后台启动 Web 仪表板（默认）
  python3 monitor.py web          # 前台启动 Web 仪表板
  python3 monitor.py open         # 重新打开已运行的仪表板
  python3 monitor.py stop         # 关闭后台服务
  python3 monitor.py close        # 关闭后台服务（别名）
  python3 monitor.py enhanced     # 启动增强版终端监控（需要 Rich）
  python3 monitor.py simple       # 启动标准版终端监控

美化特性：
  ✨ 全新深蓝紫色主题
  🎨 玻璃态效果和动画
  💫 丰富的交互体验
  📱 完整响应式设计
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default="background",
        choices=["web", "background", "open", "stop", "close", "enhanced", "simple"],
        help="运行模式：web(Web仪表板) | background(后台运行) | open(打开仪表板) | stop/close(停止服务) | enhanced(增强终端) | simple(标准终端)",
    )
    parser.add_argument("--port", type=int, default=None, help="Web 端口（默认 8081）")
    parser.add_argument("--host", default=None, help="Web 监听地址（默认 127.0.0.1）")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--log-file", default=None, help="后台模式日志文件（默认 ~/.codex/monitor.log）")
    parser.add_argument("--sessions-dir", default=None, help="会话日志目录（默认 ~/.codex/sessions）")
    parser.add_argument("--config", default=None, help="配置文件路径（默认 ~/.codex/monitor_config.json）")
    parser.add_argument("--cwd", default=None, help="仅统计该目录(含子目录)下的会话")
    parser.add_argument("--once", action="store_true", help="只显示一次后退出（仅用于 enhanced/simple 模式）")
    return parser


def run_enhanced_terminal(args) -> int:
    """启动增强版终端监控"""
    enhanced_script = _script_path("codex_monitor_enhanced.py")
    if not enhanced_script.exists():
        print("❌ 找不到增强版终端脚本: codex_monitor_enhanced.py")
        print("💡 提示：增强版终端需要 Rich 库支持")
        print("   安装命令: pip install rich")
        return 1

    cmd = [sys.executable, str(enhanced_script)]
    if args.sessions_dir:
        cmd += ["--sessions-dir", args.sessions_dir]
    if args.config:
        cmd += ["--config", args.config]
    if args.cwd:
        cmd += ["--cwd", args.cwd]
    if args.once:
        cmd.append("--once")

    print("🚀 启动增强版终端监控...")
    try:
        return subprocess.run(cmd).returncode
    except KeyboardInterrupt:
        print("\n✅ 已退出终端监控")
        return 0


def run_simple_terminal(args) -> int:
    """启动标准版终端监控"""
    simple_script = _script_path("codex_monitor_simple.py")
    if not simple_script.exists():
        print(f"❌ 找不到文件: {simple_script}")
        return 1

    cmd = [sys.executable, str(simple_script)]
    if args.sessions_dir:
        cmd += ["--sessions-dir", args.sessions_dir]
    if args.config:
        cmd += ["--config", args.config]
    if args.cwd:
        cmd += ["--cwd", args.cwd]

    print("🚀 启动标准版终端监控...")
    try:
        return subprocess.run(cmd).returncode
    except KeyboardInterrupt:
        print("\n✅ 已退出终端监控")
        return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.mode == "web":
        return run_web_dashboard(args)
    if args.mode == "background":
        return run_background(args)
    if args.mode == "open":
        return open_dashboard(args)
    if args.mode == "enhanced":
        return run_enhanced_terminal(args)
    if args.mode == "simple":
        return run_simple_terminal(args)
    if args.mode in {"stop", "close"}:
        return stop_background()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
