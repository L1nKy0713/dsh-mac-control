#!/usr/bin/env python3
"""rec.py — 录屏：定时录制 / 手动 start-stop / 抽帧。

依赖系统自带的 `screencapture`（无需额外安装，DSH 进程已有屏幕录制权限）；
抽帧用 ffmpeg（可选）。

用法：
  rec.py capture --seconds 3                 # 录 3 秒 → /tmp/mac-rec-<ts>.mov
  rec.py start --out ~/Movies/demo.mov       # 后台开始，直到 stop
  rec.py stop                                # 停止并返回文件信息
  rec.py frames --mov /tmp/x.mov --every 1 --out /tmp/frames
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import maclib as M  # noqa: E402

STATE_DIR = M.STATE_DIR
REC_PID = STATE_DIR / "rec.pid"
REC_META = STATE_DIR / "rec.json"


def _mov_info(path: Path) -> dict:
    info = {"path": str(path), "bytes": path.stat().st_size if path.exists() else 0}
    ffprobe = shutil.which("ffprobe")
    if ffprobe and path.exists():
        try:
            out = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=nw=1:nk=1", str(path)],
                capture_output=True, text=True, timeout=30,
            ).stdout.strip()
            info["duration"] = round(float(out), 2) if out else None
        except Exception:
            info["duration"] = None
    return info


def cmd_capture(a) -> None:
    out = Path(a.out or f"/tmp/mac-rec-{time.strftime('%H%M%S')}.mov").expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["screencapture", "-v", "-x", "-V", str(a.seconds), str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=a.seconds + 120)
    if not out.exists():
        raise SystemExit(f"录制失败：{proc.stderr[:300]}")
    info = _mov_info(out)
    M.audit("rec_capture", seconds=a.seconds, out=str(out), bytes=info["bytes"])
    M.emit(info)


def cmd_start(a) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if REC_PID.exists():
        raise SystemExit("已有录制在进行，先 rec.py stop")
    out = Path(a.out or f"/tmp/mac-rec-{time.strftime('%H%M%S')}.mov").expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        ["screencapture", "-v", "-x", str(out)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    REC_PID.write_text(str(proc.pid))
    REC_META.write_text(json.dumps({"pid": proc.pid, "out": str(out),
                                    "started": time.time()}))
    M.audit("rec_start", pid=proc.pid, out=str(out))
    M.emit({"pid": proc.pid, "out": str(out), "note": "rec.py stop 结束录制"})


def cmd_stop(_a) -> None:
    if not REC_PID.exists():
        raise SystemExit("没有进行中的录制")
    meta = json.loads(REC_META.read_text())
    pid = int(meta["pid"])
    out = Path(meta["out"])
    try:
        os.kill(pid, signal.SIGINT)
    except ProcessLookupError:
        pass
    for _ in range(40):
        if not out.exists() or out.stat().st_size > 0:
            break
        time.sleep(0.2)
    time.sleep(1.5)  # 等 screencapture 收尾封装 moov
    REC_PID.unlink(missing_ok=True)
    REC_META.unlink(missing_ok=True)
    info = _mov_info(out)
    info["recorded_seconds"] = round(time.time() - meta["started"], 2)
    M.audit("rec_stop", out=str(out), bytes=info["bytes"])
    M.emit(info)


def cmd_frames(a) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("需要 ffmpeg：brew install ffmpeg")
    src = Path(a.mov).expanduser()
    if not src.exists():
        raise SystemExit(f"找不到视频：{src}")
    dest = Path(a.out or (src.parent / (src.stem + "-frames"))).expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(src),
         "-vf", f"fps=1/{a.every}", "-frames:v", str(a.max), str(dest / "f%03d.png")],
        capture_output=True, text=True, timeout=600,
    )
    frames = sorted(dest.glob("f*.png"))
    M.audit("rec_frames", mov=str(src), count=len(frames), out=str(dest))
    M.emit({"dir": str(dest), "count": len(frames),
            "frames": [str(p) for p in frames]})


def main() -> None:
    M.main_guard()
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("capture", help="录固定秒数")
    c.add_argument("--seconds", type=int, default=3)
    c.add_argument("--out")
    c.set_defaults(fn=cmd_capture)

    s = sub.add_parser("start", help="开始后台录制")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_start)

    sub.add_parser("stop", help="停止后台录制").set_defaults(fn=cmd_stop)

    f = sub.add_parser("frames", help="从视频抽帧")
    f.add_argument("--mov", required=True)
    f.add_argument("--every", type=int, default=1, help="每 N 秒一帧")
    f.add_argument("--max", type=int, default=20, help="最多抽多少帧")
    f.add_argument("--out")
    f.set_defaults(fn=cmd_frames)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()