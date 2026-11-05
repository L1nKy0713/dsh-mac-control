#!/usr/bin/env python3
"""doctor.py — 体检：引擎、权限、录屏、代理依赖，一次说清能不能干活。"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import maclib as M  # noqa: E402


def check_engine() -> dict:
    try:
        pb = M.peekaboo()
    except SystemExit as exc:
        return {"ok": False, "error": str(exc)}
    ver = subprocess.run([pb, "--version"], capture_output=True, text=True).stdout.strip()
    return {"ok": True, "path": pb, "version": ver}


def check_permissions() -> dict:
    try:
        data = M.run_json(["permissions", "status"], timeout=60)
    except SystemExit as exc:
        return {"ok": False, "error": str(exc)}
    perms = {p.get("name"): p.get("isGranted") for p in data.get("permissions", [])}
    return {"ok": all(perms.values()) if perms else False,
            "source": data.get("source"), "permissions": perms}


WINDOW_NOISE = (
    "shareable window",
    "not found",
    "application selector",
    "inconsistent response evidence",
)


def _ax_probe(args: list[str]) -> dict:
    data = M.run_json(args, timeout=180)
    return {"ok": bool(data.get("element_count")),
            "front_app": data.get("application_name"),
            "elements": data.get("element_count"),
            "interactable": data.get("interactable_count")}


def check_ax() -> dict:
    """AX 可用性。前台 App 窗口最小化 / 名字解析不到时，换一个活窗口再试；
    这类错不是权限问题，不该让 ready 变 false。"""
    try:
        return _ax_probe(["see"])
    except SystemExit as exc:
        err = str(exc)
    # 换目标：挑一个不在列表尾、有窗口的 App 试 --pid
    try:
        d = M.run_json(["app", "list"], timeout=120)
        apps = d.get("apps") or []
    except SystemExit:
        apps = []
    for app in apps:
        pid = app.get("pid")
        if not pid or app.get("name", "").lower().startswith("deepseek"):
            continue
        try:
            out = _ax_probe(["see", "--pid", str(pid)])
            out["fallback_for"] = err[:120]
            return out
        except SystemExit:
            continue
    soft = any(w in err for w in WINDOW_NOISE)
    return {"ok": soft, "error": err[:300],
            "note": ("前台无可用窗口（多半最小化）或 App 名未解析；AX 权限本身可用"
                     if soft else "AX 观测失败")}


def check_recording() -> dict:
    ok = shutil.which("screencapture") is not None
    ff = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    return {"ok": ok, "screencapture": ok,
            "ffmpeg": bool(ff), "ffprobe": bool(ffprobe),
            "note": "视频用 screencapture -v；无 ffmpeg 时抽帧不可用"}


def main() -> None:
    M.main_guard()
    report = {
        "engine": check_engine(),
        "permissions": check_permissions(),
        "ax": check_ax(),
        "recording": check_recording(),
        "allow_list": M.allowed_apps(),
        "state_dir": str(M.STATE_DIR),
    }
    report["ready"] = bool(report["engine"].get("ok")
                           and report["permissions"].get("ok")
                           and report["ax"].get("ok")
                           and report["recording"].get("ok"))
    M.emit(report)


if __name__ == "__main__":
    main()