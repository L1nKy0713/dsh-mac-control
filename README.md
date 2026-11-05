# dsh-mac-control

一个给 **DeepSeek Harness（DSH）** 用的 macOS 本机操作技能（skill）：让 agent 能**看屏幕、点鼠标、敲键盘、录屏**，替你在指定的 App 里把流程跑完。

> 观察用 macOS 辅助功能（AX）元素表 + 截图，动作一律锁定目标 App 并留审计日志 —— 不做"盲打坐标"。

- 引擎：[Peekaboo](https://github.com/openclaw/Peekaboo) 4.9.7（Swift CLI，自带屏幕录制 / 辅助功能 / 事件合成三项授权）
- 形态：DSH skill（`SKILL.md` + 6 个 Python 脚本，零第三方 Python 依赖）
- 平台：macOS（本机实测 macOS 26 / Apple Silicon；Intel 路径同理，引擎换 x86_64 包即可）

## 它能做什么

| 能力 | 命令 | 说明 |
|---|---|---|
| 截屏 | `shot.py [--mode screen\|window\|area\|frontmost] [--scale 1400]` | 返回 PNG 路径 + sha256 + 尺寸 + AX 元素数 |
| 看元素 | `gui.py see --app "文本编辑" --json` | 返回 `elem_N / role / label / value / bounds / is_actionable` |
| 点击 | `gui.py click --app X --elem elem_12` 或 `--at 400,300` | 按元素 ID 或坐标 |
| 输入 | `gui.py type --app X "中文 空格 标点"` | 走剪贴板 + `cmd+v`，空格不会被吞 |
| 快捷键 | `gui.py keys --app X "cmd+s"` | 支持组合键 |
| 滚动 / 拖拽 | `gui.py scroll --dy -5` / `drag --from 100,200 --to 400,200` | |
| 模态对话框 | `gui.py dialog click --button "删除" --app X` | 存盘面板、权限弹窗这类 sheet 必须用它 |
| 录屏 | `rec.py capture --seconds 3` / `start`+`stop` / `frames` | 视频走 `screencapture -v`，抽帧走 ffmpeg |
| 自检 | `doctor.py` | `ready: true` 才能干活 |

## 安装

```bash
git clone https://github.com/<you>/dsh-mac-control.git ~/.dsh/skills/mac-control
bash ~/.dsh/skills/mac-control/scripts/setup.sh    # 走 npmmirror 装 Peekaboo 4.9.7
python3 ~/.dsh/skills/mac-control/scripts/doctor.py
```

`doctor.py` 报三项权限缺一，就到「系统设置 → 隐私与安全性」给 **Peekaboo** 勾上**屏幕录制**与**辅助功能**。

权限由 Peekaboo 的守护进程持有（`source: bridge`），所以之后移动二进制不会重置授权。

## 三条实测验收（本机真跑过）

| 用例 | 结果 |
|---|---|
| 计算器里 `全部清除 6 × 7 =` | 读回 `编辑字段 value = 42` |
| 文本编辑写入 35 字符中英混排 | `cmd+a/c` 后 `pbpaste` 回读**完全一致** |
| 录 3 秒屏 + 抽帧 | `3.04s / 4.8MB` mov，抽出 2816×1762 PNG |

## 四个必须知道的坑（血泪）

1. **App 名必须是系统本地化名。** 中文 macOS 上写 `--app "Calculator"` / `--app "TextEdit"` / `com.apple.calculator` 都会报 `Application '…' not found`（Peekaboo 4.9.7 还会把它包装成 `application selector` / `inconsistent response evidence`，措辞极具误导性）。正确写法是 `计算器` / `文本编辑` / `访达`，或直接用 `--pid`。
2. **元素 ID 每次观测都会变。** `elem_26` 下一次 `see` 可能就是 `elem_28`。每个动作前都要重新 `see`，不能缓存。
3. **`peekaboo type` 会吞空格。** `"hello mac-control"` → `hellomac-control`，中文与空格的丢失更随机。本仓库的 `gui.py type` 已改成「存剪贴板 → `clipboard set` → `press cmd+v` → 还原剪贴板」，实测中文、空格、标点全保留。
4. **模态 sheet 不能 `click --elem`。** 会恒报 `Window focus did not complete with a verified exact target … focusVerificationTimeout(1056)`。必须用 `dialog click --button "删除"` 这类子命令。

更多记录见 [`docs/PITFALLS.md`](docs/PITFALLS.md)。

## 安全设计

- **默认拒绝操作 DSH 本体**：`allow.json` 里 `deny_always: ["DeepSeek Harness"]`；裸 `--foreground` 输入会打到最前台 App，不锁目标就可能把 `cmd+n` 送进 agent 自己的宿主（本项目开发时真踩过）。
- **白名单机制**：`allow.json` 的 `allow` 为空 = 除 DSH 外都允许；填入 App 名后只允许这些 App。
- **审计日志**：每次动作写 `~/.local/state/mac-control/audit.jsonl`（时间、动作、目标 App、argv、rc），出问题先读它还原时序。
- **破坏性操作先确认**：删除、发送、支付、提交表单、丢弃未保存内容 —— 技能里写明必须先问用户。

## 英文速览 / English

A macOS GUI-automation skill for DeepSeek Harness. Observe via Accessibility tree + screenshots, act via Peekaboo with the target app always pinned and every action logged. Verified end-to-end: click a button and read the result back (`6 × 7 = 42`), type mixed CJK/ASCII and read it back through the clipboard, record the screen for 3s and extract frames.

Four traps worth reading before use: localized app names are mandatory; element IDs churn on every snapshot; `peekaboo type` drops spaces (use clipboard paste); modal sheets need `dialog click --button`, not element clicks.

## License

MIT。代码可直接商用/二次分发，无需署名（保留 LICENSE 即可）。