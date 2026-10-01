# Ubuntu 24.04 / GNOME Wayland 语音输入参考项目分析

> 目标：为本项目 `voice-input` 后续实现/重构提供方案参考。重点关注：Ubuntu 24.04、GNOME Wayland、中文输入、光标位置输入、讯飞/Whisper/Vosk 多后端、系统权限与 Python 环境隔离。

## 本机环境基线

当前开发机环境：

- OS：Ubuntu 24.04.4 LTS
- 桌面：GNOME 46，实际图形会话大概率为 Wayland
- 内存：约 30GB，可运行 Whisper small/medium，谨慎常驻 large-v3
- GPU：Intel Arrow Lake-P 集显
- Python：系统 Python 3.12.3
- 已有输入相关工具：
  - `/usr/bin/xdotool`
  - `/usr/bin/wtype`
  - `/usr/bin/ydotool`
  - `/usr/bin/wl-copy`
  - `/usr/bin/arecord`

注意：在 Hermes/Agent 的非图形终端中，`XDG_SESSION_TYPE` 可能为空，不能代表真实桌面会话。输入测试必须在图形桌面终端中执行。

---

## 本项目现状

项目路径：

```text
/home/lfh/projects/daily/voice-input
```

已有能力：

- Python 实现
- 讯飞 IAT WebSocket 流式识别：`src/voice_input/recognizer/xunfei.py`
- 全局快捷键监听：`src/voice_input/hotkey.py`，基于 `evdev`
- 录音与流式音频发送
- 多种文本输入方式：`src/voice_input/typer.py`
  - `clipboard`
  - `xdotool`
  - `wtype`
  - `ydotool`
  - `pynput`
  - `wl-copy + ydotool Ctrl+V`
- 已有测试脚本：`test_cursor_input.py`

Git 记录显示曾尝试默认使用 `xdotool` 做直接光标输入，但最终因为 GNOME Wayland 限制回退到 clipboard：

```text
Revert to clipboard method: GNOME Wayland limitations prevent direct cursor input
```

因此后续设计应承认现实：**GNOME Wayland 下“直接模拟键盘输入任意 Unicode 文本”不稳定，优先做“无感自动粘贴到光标位置”。**

---

## 推荐参考项目排序

### 1. Vocalinux

Git 地址：

```bash
git clone https://github.com/jatinkrmalik/vocalinux.git
```

基本信息：

- Stars：约 370
- 语言：Python
- 定位：Linux 桌面语音输入，支持 X11 + Wayland
- 后端：whisper.cpp / Whisper / Vosk
- GUI：GTK
- 状态：Beta，但有一定社区验证

参考价值：**最高**。

适合学习：

- Python 项目结构
- 多 STT 后端抽象
- X11 / Wayland 输入策略
- GTK 桌面应用结构
- 模型管理与离线识别集成

对本项目的启发：

```text
Recognizer 抽象层：Xunfei / Whisper / Vosk
InputBackend 抽象层：ClipboardPaste / Xdotool / Wtype / Ydotool / IBus
GUI/Tray 可独立于核心逻辑
```

---

### 2. sunapi386/voice-dictation

Git 地址：

```bash
git clone https://github.com/sunapi386/voice-dictation.git
```

基本信息：

- Stars：0
- 语言：Python
- 定位：Ubuntu 24.04+ 离线实时语音输入
- 后端：faster-whisper
- 支持：X11 + Wayland
- 特性：托盘图标、模型常驻内存、systemd user service、自启动

参考价值：**高**，但成熟度低。

适合学习：

- Ubuntu 24.04 适配
- faster-whisper 集成
- system tray 设计
- systemd user service
- 模型常驻内存降低启动延迟

风险：

- Star 很少，踩坑人数少
- 安装脚本需审查，不能直接 `curl | bash`
- 常驻模型会增加内存占用

---

### 3. Voxtype

Git 地址：

```bash
git clone https://github.com/peteonrails/voxtype.git
```

基本信息：

- Stars：约 842
- 语言：Rust
- 定位：Linux/Wayland push-to-talk 语音输入
- 后端：Whisper / Parakeet / Cohere / SenseVoice / Paraformer 等
- 特性：多后端、性能优化、Wayland-first、CJK 支持

参考价值：**中高**。

适合学习：

- Wayland 输入路径设计
- 多引擎切换
- 文本后处理
- 性能优化和低延迟架构

限制：

- Rust 技术栈，不适合直接合并到本 Python 项目
- 可能更偏 Wayland compositor 生态，需要验证 GNOME 兼容性

---

### 4. hyprwhspr

Git 地址：

```bash
git clone https://github.com/goodroot/hyprwhspr.git
```

基本信息：

- Stars：约 1063
- 语言：Python
- 定位：Linux 原生系统级语音输入
- 支持：Arch/Debian/Ubuntu/Fedora/openSUSE，Wayland session
- 后端：Cohere / Parakeet / Whisper / Gemini / ElevenLabs / REST API 等

参考价值：**中高**。

适合学习：

- Python + Linux 原生集成
- 多后端配置
- Wayland 下自动粘贴/输入
- 状态可视化

限制：

- 名称和生态偏 Hyprland
- GNOME Wayland 下需实测

---

### 5. Blurt

Git 地址：

```bash
git clone https://github.com/QuantiusBenignus/blurt.git
```

基本信息：

- Stars：约 108
- 语言：JavaScript / GNOME Shell Extension
- 定位：GNOME Shell 扩展，基于 whisper.cpp 的离线语音输入
- 支持：GNOME 49 及以下；Ubuntu 24.04 的 GNOME 46 理论匹配

参考价值：**中**。

适合学习：

- GNOME Shell 扩展如何做 UI/快捷键
- whisper.cpp server / 本地命令调用方式
- GNOME 桌面集成

限制：

- 不是 Python 项目
- GNOME 扩展受 Shell 版本影响大

---

### 6. OpenWhispr

Git 地址：

```bash
git clone https://github.com/OpenWhispr/openwhispr.git
```

基本信息：

- Stars：约 3770
- 语言：TypeScript
- 定位：跨平台语音输入成品应用，替代 WisprFlow / Granola
- 平台：macOS / Windows / Linux
- 安装：Linux AppImage / deb / rpm
- 后端：本地 Whisper/Parakeet + 云模型 BYOK

参考价值：**中高，偏产品设计参考**。

适合学习：

- 成品应用体验
- 热键交互
- 模型选择 UI
- 本地/云端模型切换
- 日志、设置、用户体验

限制：

- Electron/TypeScript 技术栈，不能直接复用 Python 代码

---

## 低优先级参考项目

### VoxFree

```bash
git clone https://github.com/owaistnt/VoxFree.git
```

- Ubuntu 24.04 GNOME/Wayland 定向
- Star 很少
- 更像个人实验/脚本集合

### kolenchuk/speech-to-text

```bash
git clone https://github.com/kolenchuk/speech-to-text.git
```

- Ubuntu 24.04 定向
- Python
- 支持 hold-to-talk / X11 + Wayland / uinput / clipboard
- Star 很少，但可以参考小而完整的实现

### VoiceRecUbuntu

```bash
git clone https://github.com/wmbravo2014/VoiceRecUbuntu.git
```

- Ubuntu 24.04 Wayland 定向
- Python
- Vosk bundled，IBus/Clipboard fallback
- 需注意默认 Vosk 模型语言是否适合中文/英文

### voice-to-text

```bash
git clone https://github.com/marceloperrone01/voice-to-text.git
```

- Ubuntu 24.04 / X11 专用
- faster-whisper + xdotool
- 不适合 GNOME Wayland 主路线，但可参考 X11 简化实现

---

## 输入方案分析

### X11：直接输入最容易

可用方式：

```bash
xdotool type --clearmodifiers --delay 12 -- "文本"
```

优点：

- 简单
- 能直接打到光标位置
- 中文/英文混合较好

缺点：

- 只适合 X11 或部分 XWayland 窗口
- Ubuntu 24.04 GNOME 默认更偏 Wayland

### GNOME Wayland：推荐“无感自动粘贴”

推荐路径：

```text
识别文本 → wl-copy 写入剪贴板 → ydotool/wtype 发送 Ctrl+V → 可选恢复原剪贴板
```

优点：

- 对中文最稳定
- 与当前项目已有实现最接近
- 用户体验接近直接输入

缺点：

- 本质仍是剪贴板粘贴
- 需要处理剪贴板被覆盖的问题
- `ydotool` 可能需要 daemon / input 权限

### IBus / D-Bus：长期更正统但复杂

可能路径：

```text
实现/调用 IBus engine 或通过 D-Bus 向当前输入上下文 commit_text
```

优点：

- 更符合 GNOME/Wayland 输入架构
- 理论上比模拟键盘更自然

缺点：

- 实现复杂
- 调试难度高
- 需要深入 IBus/GTK/GNOME 输入法机制

### ydotool 直接 type：不推荐用于中文

优点：

- 可跨 Wayland 走 uinput

缺点：

- 权限复杂
- Unicode/中文输入不稳定
- 更适合发送快捷键，比如 Ctrl+V

---

## 推荐本项目目标架构

```text
voice_input/
├── app.py / main.py
├── config.py
├── audio/
│   └── recorder.py
├── recognizer/
│   ├── base.py
│   ├── xunfei.py
│   ├── whisper_local.py
│   └── vosk.py
├── input/
│   ├── base.py
│   ├── clipboard_paste.py
│   ├── xdotool.py
│   ├── wtype.py
│   ├── ydotool.py
│   └── ibus.py  # 长期探索
├── hotkey/
│   └── evdev_listener.py
├── tray/
│   └── appindicator.py
└── diagnostics/
    └── environment_check.py
```

关键原则：

1. 识别后端与输入后端解耦。
2. 不把 API 密钥写死在项目配置中，优先环境变量。
3. GNOME Wayland 默认使用 `clipboard_paste`。
4. X11 默认使用 `xdotool`。
5. 所有系统输入能力都提供诊断命令。
6. 安装脚本不要污染系统 Python，遵守项目 Python/uv 规范。

---

## 推荐近期实现路线

### 第 1 阶段：稳住现有讯飞版本

目标：让当前 `voice-input` 在 Ubuntu 24.04 GNOME Wayland 下稳定“无感粘贴”。

任务：

- 保留 `xunfei.py`
- 改造配置读取：支持环境变量覆盖 `config.yaml`
- 增强 `typer.py`：
  - Wayland 默认 `wl-copy + ydotool Ctrl+V`
  - 粘贴前保存原剪贴板
  - 粘贴后可选恢复原剪贴板
  - 失败时提示手动 Ctrl+V
- 增加 `diagnose` 命令：检测桌面环境、工具、权限、麦克风、API 配置是否完整

### 第 2 阶段：增加离线后端

优先参考 Vocalinux / voice-dictation：

- faster-whisper local
- whisper.cpp 可选
- Vosk 可选轻量后端

推荐模型：

- 中文短指令：Whisper `base` / `small`
- 低内存：Vosk small 中文模型
- 不建议常驻 large-v3

### 第 3 阶段：桌面体验增强

- 托盘图标
- 开机自启 systemd user service
- 模型选择 UI
- 日志查看
- 快捷键配置

### 第 4 阶段：探索 IBus / GNOME 扩展

目标：减少剪贴板依赖，接近真正输入法体验。

---

## 安全与环境规范

### 密钥

讯飞配置建议支持：

```bash
XUNFEI_APP_ID
XUNFEI_API_KEY
XUNFEI_API_SECRET
```

`config.yaml.example` 只保留占位符，不提交真实 `config.yaml`。

### Python 环境

遵守用户 Python 环境规范：

- 不全局 `pip install`
- 优先 `uv`
- 项目独立 `.venv`
- 依赖写入 `pyproject.toml` / `uv.lock`
- 使用 `uv run` 运行测试和脚本

推荐命令：

```bash
cd /home/lfh/projects/daily/voice-input
uv venv --python /usr/bin/python3
uv sync
uv run python test_cursor_input.py
```

---

## 最建议先 clone 的参考仓库

```bash
mkdir -p /home/lfh/projects/reference/voice-input
cd /home/lfh/projects/reference/voice-input

git clone https://github.com/jatinkrmalik/vocalinux.git
git clone https://github.com/sunapi386/voice-dictation.git
git clone https://github.com/peteonrails/voxtype.git
git clone https://github.com/QuantiusBenignus/blurt.git
```

优先阅读顺序：

1. `vocalinux`：Python 架构与多后端
2. `voice-dictation`：Ubuntu 24.04/faster-whisper/system tray
3. `voxtype`：Wayland 输入和多引擎设计
4. `blurt`：GNOME Shell/whisper.cpp 集成

---

## 一句话结论

本项目不要再强求 GNOME Wayland 下“纯键盘模拟直接输入中文”。现实路线应该是：

```text
短期：讯飞/Whisper 识别 + wl-copy + 自动 Ctrl+V + 剪贴板恢复
中期：增加 faster-whisper / Vosk 离线后端
长期：探索 IBus / GNOME 扩展实现更原生输入
```
