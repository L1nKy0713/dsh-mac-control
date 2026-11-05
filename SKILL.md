---
name: mac-control
description: 在本机 macOS 上"看屏幕、动鼠标键盘"，替用户完成指定 App 里的操作。当用户要求截屏/录屏、看清当前屏幕或某个窗口、在某个 App 里点击/输入/拖拽/滚动/按快捷键、把某个流程替他跑一遍、或说"帮我在 XX 里点一下/填一下/导出一下"时使用。基于 Peekaboo 4.9.7（已带辅助功能 + 屏幕录制 + 事件合成三项授权），观察用 AX 元素表 + 截图，动作一律锁定目标 App 并留审计日志。
---

# mac-control：本机 GUI 操作

把「看一眼屏幕」和「动一下鼠标键盘」拆成可验证的小步：**观察 → 定位元素 → 动作 → 截图验证 → 记审计**。没有验证过的动作等于没做。

## 0. 先体检（每次会话第一次用）

```bash
python3 ~/.dsh/skills/mac-control/scripts/doctor.py
```

`ready: true` 才能干活。若三项权限缺一，让用户在「系统设置 → 隐私与安全性」里给 **Peekaboo**（或运行它的终端/宿主）勾上；`source: bridge` 说明权限由本机 Peekaboo 守护进程持有，移动二进制不会重置授权。

## 1. 观察

```bash
# 整屏（先缩到 1400 宽省 token）
python3 .../shot.py --scale 1400
# 带 AX 元素表的观测（拿 elem_N 供点击）
python3 .../gui.py see --app "文本编辑"
# 列 App / 列窗口 / 进程号定向
python3 .../gui.py apps
python3 .../gui.py wins --app "文本编辑"
python3 .../gui.py see --pid 57331
```

截图路径拿到后**必须用 `read_image` 真的看**，别靠猜坐标。`see` 返回的 `elements` 里 `is_actionable: true` 且带 `label` 的就是可点目标；Element ID（`elem_3`）会随界面变化失效，**每次动作前重新 see**。

**App 名必须是系统本地化名**（本机是中文 macOS）：`计算器` / `访达` / `文本编辑` / `系统设置` —— 写 `Calculator`、`TextEdit`、`com.apple.calculator` 都会报 `Application '…' not found`（4.9.7 把"查不到"包装成 `application selector` / `inconsistent response evidence`，别被那个措辞骗了）。名字不确定时先 `gui.py apps` 抄中文名，或直接用 `--pid`（最稳）。

Electron 应用（含 DSH 自己）AX 树很浅，深层内容只能靠截图 + 坐标。

## 2. 动作（全部锁 App）

```bash
python3 .../gui.py focus  --app "TextEdit"                 # 提到前台
python3 .../gui.py click  --app "TextEdit" --elem elem_5   # 按元素点
python3 .../gui.py click  --app "TextEdit" --at 400,300    # 按坐标点（先验证坐标）
python3 .../gui.py type   --app "文本编辑" "要写的文字"     # 内部走剪贴板+cmd+v，空格不会被吞
python3 .../gui.py keys   --app "TextEdit" "cmd+s"
python3 .../gui.py scroll --app "Safari"   --dy -5
python3 .../gui.py drag   --app "TextEdit" --from 100,200 --to 400,200
python3 .../gui.py launch --app "计算器"
python3 .../gui.py dialog click --button "删除" --app "文本编辑"   # 模态 sheet 必须走 dialog
```

**模态对话框（存盘面板、权限弹窗、"要保留吗？"）不能 `click --elem`** —— sheet 会让焦点校验失败（`Window focus did not complete with a verified exact target … focusVerificationTimeout`）。用 `dialog`：

```bash
python3 .../gui.py dialog click   --button "删除" --app "文本编辑"   # 按钮文字同界面
python3 .../gui.py dialog dismiss --app "文本编辑"                  # 取消/Esc
python3 .../gui.py dialog input   --text "mac-control" --field "名称" --app "App"
python3 .../gui.py dialog file    --path /tmp --name poem.rtf --select 保存 --app "文本编辑"
```

## 3. 录屏

```bash
python3 .../rec.py capture --seconds 3            # 定时录 → mov
python3 .../rec.py start --out ~/Movies/demo.mov  # 长录，之后 stop
python3 .../rec.py stop
python3 .../rec.py frames --mov /tmp/x.mov --every 1 --out /tmp/frames
```

视频只能走 `screencapture -v`（Peekaboo 的 `capture live` 是变更感知帧采样，不产视频）。抽帧需要 ffmpeg。

## 4. 铁律

1. **绝不裸用 `--foreground` 敲键盘**：最前台可能是 DSH 自己，`cmd+n` 会在 DSH 里开新会话、文本会写进对话输入框（真实踩过）。一切输入必须 `--app` 或 `--window-id`；脚本默认拒绝操作 DSH 本体。
2. **`type` 会吞空格**（原生 `peekaboo type "hello mac"` → `hellomac`，中文与空格丢得更随机）。`gui.py type` 已默认改成「存剪贴板 → `clipboard set` → `press cmd+v` → 还原剪贴板」，实测中文 + 空格 + 标点全保留；确实要原生命令才加 `--raw`。
3. **报错不等于没生效**：`type` 常返回 `Typing did not return an accepted outcome` 但文本已经进去了。动作后必须回读校验：`cmd+a` → `cmd+c` → `pbpaste`，或再截一张图看。
4. **每次动作前重新观测**：元素 ID 与坐标都会变；跨窗口操作先 `focus` 再 `see`。
5. **破坏性操作先问**：删除、发送、支付、提交表单、关窗丢弃未保存内容 —— 先说明要点什么，等用户确认。
6. **审计留痕**：每次动作写 `~/.local/state/mac-control/audit.jsonl`；出问题先读它还原时序。
7. 慢：单次 `see` 约 4s，一个 5 步流程 30s 起，别高频轮询截图，改成"动作 → 一次验证"。

## 5. 常用配方

**在某个 App 里写一段字并确认写进去了**
```
gui.py launch --app "文本编辑"
gui.py keys   --app "文本编辑" "cmd+n"      # 新文档
gui.py type   --app "文本编辑" "…文本…"     # 剪贴板粘贴，保留空格
gui.py keys   --app "文本编辑" "cmd+a"
gui.py keys   --app "文本编辑" "cmd+c"
pbpaste                                    # 回读比对
```

**点按钮并验证界面变了**
```
shot.py --out /tmp/before.png --scale 1400     # read_image 看
gui.py see --app "App"                          # 找 elem_N / 坐标
gui.py click --app "App" --elem elem_N
shot.py --out /tmp/after.png --scale 1400      # read_image 对比
```

**点计算器按钮验证数字变化**（本机真跑过 6×7=42）：
```
for label in 全部清除 6 乘 7 等于: do
  gui.py see --app "计算器" → 按 label 找 elem_N   # 每步都重 see，id 会变
  gui.py click --app "计算器" --elem elem_N
done
gui.py see --app "计算器" → 读 label='编辑字段' 的 value   # = 42
```

**收尾模态面板**：`gui.py keys --app X "cmd+w"` → 面板出现 → `gui.py dialog click --button "删除" --app X`。

**填表单**：每个字段 = `click --elem` → 输入（`type` 或 `clipboard set` + `keys cmd+v`）→ 截图确认；提交前把整表单截一张给用户看。

## 6. 验收（本机 2026-11-05 真跑结果，出问题先照这三条复现）

| 用例 | 命令链 | 实测结果 |
|---|---|---|
| 点按钮 | `launch 计算器` → 循环 `see` 找 label → `click --elem` → `see` 读 `编辑字段` 的 `value` | `全部清除 6 乘 7 等于` → **42**，5 次 click 全 `rc=0` |
| 输入 | `launch 文本编辑` → `keys cmd+n` → `type "…"` → `keys cmd+a/cmd+c` → `pbpaste` | 35 字符中英混排，**回读完全一致** |
| 录屏 | `rec.py capture --seconds 3 --out /tmp/rec4.mov` → `rec.py frames --mov … --every 1` | **3.04s / 4.8MB**，抽帧 2816×1762 PNG |
| 模态面板 | `keys cmd+w` → `dialog click --button "删除"` | 面板关闭，窗口数 3→2 |

`doctor.py` 的 `ax` 探针会先把前台 App 试一遍，前台窗口最小化/名字解析不到时自动换一个有窗口的 App（`fallback_for` 记原始错误）；这种情况 `ready` 仍为 true。

## 7. 依赖与修

- 引擎：`~/.local/bin/peekaboo`（4.9.7，装在 `~/.local/share/mac-control/peekaboo-4.9.7/`）
- 重装/换机：`bash ~/.dsh/skills/mac-control/scripts/setup.sh`（走 npmmirror，不需要 GitHub）
- 白名单：`~/.dsh/skills/mac-control/allow.json` 的 `allow`（空数组 = 除 DSH 外都允许）
- 卸载：删掉本目录与 `~/.local/share/mac-control`，并在系统设置里移除 Peekaboo 的授权条目