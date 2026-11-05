"""mac-control 公共层：定位 peekaboo、跑命令、审计日志、应用允许列表。

设计原则（来自实测事故）：
1. 任何键盘/鼠标输入都必须显式给出目标（--app / --window-id / --snapshot），
   绝不裸用 --foreground，否则输入会落到最前台 App（通常是 DSH 自己）。
2. 每次动作写一行审计日志，便于事后追溯"谁点了什么"。
3. 默认禁止把输入打进 DSH 本体，除非显式 --allow-self。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
STATE_DIR = HOME / ".local" / "state" / "mac-control"
AUDIT = STATE_DIR / "audit.jsonl"
SKILL_DIR = Path(__file__).resolve().parent.parent
ALLOW_FILE = SKILL_DIR / "allow.json"

SELF_APP_MARKERS = ("deepseek harness", "dsh")


def peekaboo() -> str:
    """返回 peekaboo 可执行文件路径；找不到就抛错并给出安装命令。"""
    for cand in (
        shutil.which("peekaboo"),
        HOME / ".local/bin/peekaboo",
        HOME / ".local/share/mac-control/current/peekaboo",
    ):
        if cand and Path(cand).exists():
            return str(cand)
    raise SystemExit(
        "peekaboo 未安装。装法：bash "
        f"{SKILL_DIR}/scripts/setup.sh"
    )


def run(args: list[str], *, timeout: int = 120, check: bool = False) -> subprocess.CompletedProcess:
    """跑 peekaboo 子命令。统一 --json 由调用方决定。"""
    cmd = [peekaboo(), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and proc.returncode != 0:
        raise SystemExit(f"命令失败({proc.returncode}): {' '.join(cmd)}\n{proc.stderr[:800]}")
    return proc


def run_json(args: list[str], *, timeout: int = 120) -> dict:
    """跑并解析 peekaboo 的 JSON 输出（失败时把 error.message 抛出来）。"""
    proc = run([*args, "--json"], timeout=timeout)
    raw = proc.stdout.strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise SystemExit(f"非 JSON 输出：{raw[:400]}\n{proc.stderr[:400]}")
    if not payload.get("success"):
        err = (payload.get("error") or {}).get("message") or raw[:400]
        raise SystemExit(f"peekaboo 报错：{err}")
    return payload.get("data") or {}


def audit(action: str, **fields) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "action": action, **fields}
    with AUDIT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def allowed_apps() -> list[str] | None:
    """allow.json 存在且 allow 非空时作为白名单；否则 None = 不限制。"""
    if not ALLOW_FILE.exists():
        return None
    try:
        data = json.loads(ALLOW_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    allow = [a for a in (data.get("allow") or []) if a]
    return allow or None


def guard_target(app: str | None, *, allow_self: bool = False) -> None:
    """拒绝把输入打进 DSH 本体；再校验白名单。"""
    if not app:
        raise SystemExit(
            "必须指定 --app 或 --window-id：装配一次 --foreground 输入曾误写进 DSH 输入框。"
        )
    low = app.lower()
    if not allow_self and any(m in low for m in SELF_APP_MARKERS):
        raise SystemExit(
            f"拒绝操作 {app}：这是运行 Agent 的宿主 App。确实要动它就加 --allow-self。"
        )
    allow = allowed_apps()
    if allow and not any(a.lower() in low or low in a.lower() for a in allow):
        raise SystemExit(f"{app} 不在 allow.json 白名单里：{allow}")


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main_guard() -> None:
    if sys.version_info < (3, 9):
        raise SystemExit("需要 Python 3.9+")