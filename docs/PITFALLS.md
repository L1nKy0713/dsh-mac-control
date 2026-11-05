# 实测坑记（Peekaboo 4.9.7 + macOS 26 / Apple Silicon，2026-11）

本文件记录开发过程中所有**真实撞到并已解决**的问题，附原始报错文本，方便按词搜索。

---

## 1. `--app` 只认系统本地化名

```bash
peekaboo see --app "Calculator"        # Application 'Calculator' not found
peekaboo see --app "com.apple.calculator"  # Application 'com.apple.calculator' not found
peekaboo see --app "计算器"             # ✓ 正常，37 个元素 / 24 可交互
```

更坑的是某些名称会返回完全不相干的措辞：

```
The desktop observation provider returned inconsistent response evidence: application selector.
```

这句**不是**"选择器有 bug"，而是"这个名字在我的 App 列表里解析不出来"的包装说法。解决办法只有两个：抄 `peekaboo app list --json` 里的中文本地化名，或者用 `--pid`。

`app list --json` 的键是 `data.apps`（不是 `applications`），偶发返回 `count: 0` 或夹一坨 `debug_logs`，重试即可。另外它的运行时是 **remote onDemand via daemon socket**（`~/Library/Application Support/Peekaboo/daemon-*.sock`），所以驱动的是常驻守护进程而不是每次新起进程。

---

## 2. 元素 ID 在每次观测后重新编号

```
第 1 次 see → elem_26 = "等于"
第 2 次 see → elem_28 = "等于"
```

所以流程必须是 `see → 动作 → see → 动作`，不能"先扫一遍记下表，后面慢慢点"。计算器按钮是中文 label（`全部清除 / 加 / 乘 / 等于 / 百分比 / 更改正负号`），按 label 找元素比记 ID 可靠；显示区是一个 `role: other`、`label: '编辑字段'`、`value: '...'` 的元素，读数值就读它的 `value`。

---

## 3. `peekaboo type` 吞空格

```
输入 "hello mac-control"      → 剪贴板回读 "hellomac-control"
输入 "peekaboo 输入测试 OK 123" → 剪贴板回读 "peek-a-boo输入测试 OK123"
输入 "peek-a-boo输入测试 OK123" （OK 与 123 之间的空格还在，但中文前后的丢了）
```

规律不稳定，别试图绕。可靠做法是**剪贴板 + `cmd+v`**：

```bash
p=$(pbpaste)                            # 1. 备份用户剪贴板
peekaboo clipboard set --text "要写的文字"
peekaboo press cmd+v --app "文本编辑" --foreground
printf '%s' "$p" | pbcopy               # 2. 还原
```

实测 35 字符中英混排（`mac-control smoke test · 中文空格都保留 OK`）写入后 `cmd+a` / `cmd+c` / `pbpaste` 回读**完全一致**。

---

## 4. 输入必须带 `--app` 或 `--foreground`

```
Raw key presses require explicit foreground consent unless a fresh exact receipt pins background delivery
Keyboard input requires --app, --pid, --window-id, or --snapshot for background delivery
```

`--app X --foreground` 组合可用（`⚠️ Key press dispatched but not verified … 📊 Total presses: 1`）。**千万别裸用 `--foreground`**：最前台是哪个 App 就把键送哪儿。开发时裸跑 `cmd+n` 直接在 DSH 自己的窗口里新建了会话，文本也写进了对话输入框 —— 这就是 `allow.json` 里 `deny_always: ["DeepSeek Harness"]` 的由来。

---

## 5. 报错 ≠ 没生效

```
Typing did not return an accepted outcome
```

上面这句出现时，文字其实**已经进去了**。同理 `click` 常回 `⚠️ Click dispatched but not verified` 但已经点中。所以：**动作后必须回读验证**（再 `see` 一次读 `value`，或 `cmd+a/c` + `pbpaste`，或前后截图对比），别信 rc。

---

## 6. 模态 sheet 不能点元素

`cmd+w` 弹出「你要保留此新文稿"未命名"吗？」后：

```bash
peekaboo click --app "文本编辑" --elem elem_61
# Error: Window focus did not complete with a verified exact target … focusVerificationTimeout(1056)

peekaboo press cmd+d --app "文本编辑" --foreground
# rc=1

peekaboo dialog click --button "删除" --app "文本编辑"
# ✓ Clicked '删除' button      （窗口数 3 → 2）
```

`window list` 会把 sheet 也算成一个窗口（title 为 `None`），这是识别"当前有模态面板"的简易信号。`dialog` 子命令还支持 `input --text --field`、`file --path --name --select`、`dismiss [--force]`。

---

## 7. 录屏：Peekaboo 不产视频

- `peekaboo capture live` 是**变更感知帧采样**（`--duration` 默认 60s、上限 180s，`--idle-fps 2` / `--active-fps 8`），不是录像。
- 要视频文件只能用 `screencapture -v -V N out.mov`（本机 3 秒 → 4.8MB，duration 3.04s）。
- 抽帧用 `ffmpeg -vf fps=1/N`；`ffmpeg -f avfoundation -list_devices true -i ""` 在本机会报 `Input/output error`（列设备这条路不通，直接录反而正常）。

---

## 8. `doctor.py` 的 AX 探针要考虑最小化的窗口

前台 App 窗口最小化时，`see` 会回：

```
Desktop observation target was not found: shareable window for 文本编辑.
Candidates: #0 id=1059 '保存' 377x294 alpha=1.00 reason=window minimized …
```

这不是权限问题。`doctor.py` 的处理：前台失败 → 遍历 `app list` 找一个非 DSH 的 `--pid` 复测 → 成功则 `ok: true` 并把原始错误记到 `fallback_for`；若仍失败但错误属于"窗口/名字"这一类（`shareable window`、`not found`、`application selector`、`inconsistent response evidence`），判为软失败，`ready` 仍为 `true`。

---

## 9. Electron 应用（含 DSH 自己）的 AX 树很浅

DSH 前台 `see` 只有 12–13 个元素、3 个可交互。这类目标的深层内容只能靠截图 + 坐标点击，别指望 AX 元素表。