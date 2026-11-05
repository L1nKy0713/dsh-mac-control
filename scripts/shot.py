#!/usr/bin/env python3
"""shot.py — 截屏（整屏 / 指定窗口 / 指定 App），输出路径 + 尺寸 + 指纹。

用法：
  shot.py                          # 整屏，存 /tmp/mac-<ts>.png
  shot.py --out ~/Desktop/a.png    # 指定输出
  shot.py --scale 1400             # 缩到宽 1400，省 token
  shot.py --elements               # 同时返回 AX 元素表（用于点击定位）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import maclib as M  # noqa: E402


def dims(path: Path) -> tuple[int, int]:
    try:
        out = subprocess.run(
            ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
            capture_output=True, text=True, timeout=20,
        ).stdout
        w = h = 0
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("pixelWidth:"):
                w = int(line.split(":")[1])
            if line.startswith("pixelHeight:"):
                h = int(line.split(":")[1])
        return w, h
    except Exception:
        return 0, 0


def main() -> None:
    M.main_guard()
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="screen",
                    choices=["screen", "window", "frontmost", "area", "front_app"])
    ap.add_argument("--app", help="目标 App 名（window 模式）")
    ap.add_argument("--window-id", help="目标窗口 id")
    ap.add_argument("--region", help="area 模式：x,y,w,h")
    ap.add_argument("--out", help="输出 png 路径")
    ap.add_argument("--scale", type=int, default=0, help="最大宽度像素，0=不缩")
    ap.add_argument("--annotate", action="store_true", help="要求带标注的截图")
    ap.add_argument("--elements", action="store_true", help="附带 AX 元素表")
    a = ap.parse_args()

    out = Path(a.out or f"/tmp/mac-{time.strftime('%H%M%S')}.png").expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    args = ["see", "--path", str(out)]
    mode = "frontmost" if a.mode == "front_app" else a.mode
    args += ["--mode", mode]
    if a.app:
        args += ["--app", a.app]
    if a.window_id:
        args += ["--window-id", str(a.window_id)]
    if a.region:
        args += ["--region", a.region]
    if a.annotate:
        args += ["--annotate"]

    data = M.run_json(args, timeout=180)
    if not out.exists():
        raise SystemExit("截图未生成，peekaboo 返回：" + json.dumps(data)[:300])

    if a.scale > 0:
        w, _ = dims(out)
        if w > a.scale:
            subprocess.run(["sips", "-Z", str(a.scale), str(out)],
                           capture_output=True, timeout=60)

    w, h = dims(out)
    blob = out.read_bytes()
    payload = {
        "path": str(out),
        "bytes": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest()[:16],
        "width": w,
        "height": h,
        "app": data.get("application_name"),
        "window_title": data.get("window_title"),
        "snapshot_id": data.get("snapshot_id"),
        "element_count": data.get("element_count"),
    }
    if a.elements:
        payload["elements"] = [
            {k: e.get(k) for k in ("id", "role", "label", "is_actionable", "bounds")}
            for e in (data.get("ui_elements") or [])
        ]
    M.audit("shot", mode=mode, app=a.app, out=str(out), sha=payload["sha256"])
    M.emit(payload)


if __name__ == "__main__":
    main()