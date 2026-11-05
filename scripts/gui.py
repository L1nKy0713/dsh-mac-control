#!/usr/bin/env python3
"""gui.py — 观察与操作 macOS 图形界面（Peekaboo 4.9.7 封装）。

子命令：
  apps                        列出运行中的 App
  wins --app NAME             列出该 App 的窗口（含 window-id）
  see [--app NAME] [--window-id ID] [--annotate]
                              观测：截图 + AX 元素表 → 返回可点击元素
  click --app NAME (--elem elem_3 | --at x,y) [--double]
  type --app NAME "文本"       输入文本
  keys --app NAME cmd+s        按键组合
  scroll --app NAME --dy -5    滚动
  drag --app NAME --from x,y --to x,y
  focus --app NAME            把 App 提到前台
  launch --app NAME           启动 App（已运行则直接 focus）

安全规则（脚本内置，不可绕过）：
  * 所有输入类动作必须给 --app 或 --window-id；
  * 默认拒绝操作 DSH 自身（除非 --allow-self）；
  * 支持 allow.json 白名单；
  * 每次动作写审计日志 ~/.local/state/mac-control/audit.jsonl
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import maclib as M  # noqa: E402


def _target_args(a) -> list[str]:
    """输入类命令的目标参数：必须带 App/窗口；默认前台投递（实测后台投递常被拒）。"""
    out: list[str] = []
    if getattr(a, "app", None):
        out += ["--app", a.app]
    if getattr(a, "window_id", None):
        out += ["--window-id", str(a.window_id)]
    if not getattr(a, "background", False):
        out += ["--foreground"]
    return out


def cmd_apps(_a) -> None:
    data = M.run_json(["app", "list"])
    apps = data.get("applications") or data.get("apps") or []
    M.emit({"count": len(apps), "apps": apps})


def cmd_wins(a) -> None:
    M.guard_target(a.app)
    data = M.run_json(["window", "list", "--app", a.app])
    M.emit(data)


def cmd_see(a) -> None:
    args = ["see", "--json"]
    if a.app:
        args += ["--app", a.app]
    if a.window_id:
        args += ["--window-id", str(a.window_id)]
    if a.annotate:
        args += ["--annotate"]
    try:
        data = M.run_json(args, timeout=180)
    except SystemExit as exc:
        msg = str(exc)
        # 实测 4.9.7：任何 --app 选择器都会报 "inconsistent response evidence"；
        # 退路 = 先把目标提到前台，再做无选择器的前台观测。
        if a.app and "application selector" in msg:
            M.run(["window", "focus", "--app", a.app], timeout=60)
            fb = ["see", "--json"] + (["--annotate"] if a.annotate else [])
            data = M.run_json(fb, timeout=180)
            data["_fallback"] = "app selector 有 bug，已 focus 后做前台观测"
        elif a.window_id and "application selector" in msg:
            data = M.run_json(["see", "--json"] + (["--annotate"] if a.annotate else []), timeout=180)
            data["_fallback"] = "window selector 有 bug，已退回前台观测"
        else:
            raise
    elements = data.get("ui_elements") or []
    compact = [
        {k: e.get(k) for k in ("id", "role", "label", "value", "description",
                               "role_description", "is_actionable", "is_enabled",
                               "bounds")}
        for e in elements
    ]
    M.audit("see", app=a.app, elements=len(compact),
            snapshot=data.get("snapshot_id"))
    M.emit({
        "app": data.get("application_name"),
        "window_title": data.get("window_title"),
        "snapshot_id": data.get("snapshot_id"),
        "element_count": data.get("element_count"),
        "interactable_count": data.get("interactable_count"),
        "screenshot_raw": data.get("screenshot_raw"),
        "elements": compact,
        "_fallback": data.get("_fallback"),
    })


def _do(a, args: list[str], action: str) -> None:
    M.guard_target(a.app, allow_self=getattr(a, "allow_self", False))
    proc = M.run([*args, *_target_args(a)], timeout=a.timeout)
    ok = proc.returncode == 0
    M.audit(action, app=a.app, window_id=getattr(a, "window_id", None),
            argv=args, rc=proc.returncode)
    M.emit({"ok": ok, "rc": proc.returncode,
            "stdout": proc.stdout.strip()[:1200],
            "stderr": proc.stderr.strip()[:600]})


def cmd_click(a) -> None:
    args = ["click"]
    if a.elem:
        args += ["--on", a.elem]
    elif a.at:
        x, y = a.at.split(",")
        args += ["--at", f"{x},{y}"]
    else:
        raise SystemExit("click 需要 --elem elem_3 或 --at x,y")
    args += ["--foreground"] if a.background is False else []
    _do(a, args, "click")


def _clipboard() -> str:
    r = subprocess.run(["pbpaste"], capture_output=True, text=True)
    return r.stdout


def _clipboard_set(text: str) -> None:
    M.run(["clipboard", "set", "--text", text], timeout=30)


def cmd_type(a) -> None:
    """默认用「写剪贴板 + cmd+v」：peekaboo type 实测会吞掉空格，粘贴才可靠。"""
    M.guard_target(a.app, allow_self=getattr(a, "allow_self", False))
    if a.raw:
        _do(a, ["type", a.text], "type_raw")
        return
    old = _clipboard()
    _clipboard_set(a.text)
    proc = M.run(["press", "cmd+v", *_target_args(a)], timeout=a.timeout)
    _clipboard_set(old)  # 还原用户剪贴板
    M.audit("type_paste", app=a.app, chars=len(a.text), rc=proc.returncode)
    M.emit({"ok": proc.returncode == 0, "rc": proc.returncode, "chars": len(a.text),
            "method": "clipboard+cmd+v",
            "stdout": proc.stdout.strip()[:400], "stderr": proc.stderr.strip()[:400]})


def cmd_keys(a) -> None:
    keys = a.keys.split()
    _do(a, ["press", *keys], "keys")


def cmd_scroll(a) -> None:
    _do(a, ["scroll", "--dy", str(a.dy), *(["--dx", str(a.dx)] if a.dx else [])], "scroll")


def cmd_drag(a) -> None:
    _do(a, ["drag", "--from", a.src, "--to", a.dst], "drag")


def cmd_dialog(a) -> None:
    """系统对话框：模态 sheet 无法用 click --elem 命中，必须走 dialog 子命令。"""
    M.guard_target(a.app, allow_self=getattr(a, "allow_self", False))
    args = ["dialog", a.action]
    if a.action == "click":
        if not a.button:
            raise SystemExit("dialog click 需要 --button")
        args += ["--button", a.button]
    elif a.action == "input":
        if not a.text:
            raise SystemExit("dialog input 需要 --text")
        args += ["--text", a.text]
        if a.field:
            args += ["--field", a.field]
    elif a.action == "file":
        if a.path:
            args += ["--path", a.path]
        if a.name:
            args += ["--name", a.name]
        if a.select:
            args += ["--select", a.select]
    elif a.action == "dismiss":
        if a.force:
            args += ["--force"]
    args += _target_args(a)
    _do(a, args, f"dialog_{a.action}")


def cmd_focus(a) -> None:
    args = ["window", "focus", "--app", a.app] if not a.window_id else \
           ["window", "focus", "--window-id", str(a.window_id)]
    M.guard_target(a.app, allow_self=a.allow_self)
    proc = M.run(args, timeout=60)
    M.audit("focus", app=a.app, rc=proc.returncode)
    M.emit({"ok": proc.returncode == 0, "stdout": proc.stdout.strip()[:600],
            "stderr": proc.stderr.strip()[:400]})


def cmd_launch(a) -> None:
    M.guard_target(a.app, allow_self=a.allow_self)
    args = ["app", "launch", a.app, "--wait-ready"]
    if a.foreground:
        args += ["--foreground"]
    proc = M.run(args, timeout=a.timeout)
    M.audit("launch", app=a.app, rc=proc.returncode)
    M.emit({"ok": proc.returncode == 0, "stdout": proc.stdout.strip()[:600],
            "stderr": proc.stderr.strip()[:400]})


def main() -> None:
    M.main_guard()
    ap = argparse.ArgumentParser(description="macOS 图形界面观察与操作")
    ap.add_argument("--timeout", type=int, default=120)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_target(p):
        p.add_argument("--app", help="目标 App 名，如 TextEdit / Safari")
        p.add_argument("--window-id", help="目标窗口 id（更精确）")
        p.add_argument("--allow-self", action="store_true", help="允许操作 DSH 本体")

    sub.add_parser("apps").set_defaults(fn=cmd_apps)

    p = sub.add_parser("wins"); add_target(p); p.set_defaults(fn=cmd_wins)

    p = sub.add_parser("see"); add_target(p)
    p.add_argument("--annotate", action="store_true")
    p.set_defaults(fn=cmd_see)

    p = sub.add_parser("click"); add_target(p)
    p.add_argument("--elem", help="元素 id，如 elem_3")
    p.add_argument("--at", help="坐标 x,y")
    p.add_argument("--background", action="store_true", help="后台投递（默认前台）")
    p.set_defaults(fn=cmd_click)

    p = sub.add_parser("type"); add_target(p)
    p.add_argument("text")
    p.add_argument("--raw", action="store_true", help="用 peekaboo type（会吞空格，慎用）")
    p.add_argument("--background", action="store_true", help="后台投递（需快照，常被拒）")
    p.set_defaults(fn=cmd_type)

    p = sub.add_parser("keys"); add_target(p)
    p.add_argument("keys", help='如 "cmd+s" 或 "cmd shift p"')
    p.set_defaults(fn=cmd_keys)

    p = sub.add_parser("scroll"); add_target(p)
    p.add_argument("--dy", type=int, default=-3)
    p.add_argument("--dx", type=int, default=0)
    p.set_defaults(fn=cmd_scroll)

    p = sub.add_parser("drag"); add_target(p)
    p.add_argument("--from", dest="src", required=True)
    p.add_argument("--to", dest="dst", required=True)
    p.set_defaults(fn=cmd_drag)

    p = sub.add_parser("dialog"); add_target(p)
    p.add_argument("action", choices=["click", "input", "file", "dismiss"])
    p.add_argument("--button"); p.add_argument("--text"); p.add_argument("--field")
    p.add_argument("--path"); p.add_argument("--name"); p.add_argument("--select")
    p.add_argument("--force", action="store_true")
    p.add_argument("--background", action="store_true")

    p = sub.add_parser("focus"); add_target(p); p.set_defaults(fn=cmd_focus)

    p = sub.add_parser("launch"); add_target(p)
    p.add_argument("--foreground", action="store_true")
    p.set_defaults(fn=cmd_launch)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()