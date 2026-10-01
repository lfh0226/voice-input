# Voice Input

🎤 **流式语音输入工具** - Linux 上的实时语音转文字输入工具，当前主线使用讯飞 WebSocket/API 流式识别，边说边出文字。

**版本**: v1.0.0

> 🚀 **v1.1.0 已发布**:新增 fcitx5 原生流式插件——语音文字通过输入法通道直接落入光标处,零粘贴。见 [CHANGELOG.md](CHANGELOG.md)。

## v1.1.0 新架构(fcitx5 流式插件)

```
按住右 Alt ──► daemon:切 voice IM + 录音 + 讯飞流式(80ms/批,dwa=wpgs 语境纠错)
                     │ 中间结果(每批)                │ 最终结果
                     ▼                               ▼
            fcitx5 voiceim 插件(预编辑灰字)      commitString 直接上屏
```

安装 fcitx5 插件(需已编译):

```bash
./scripts/build-fcitx5-addon.sh
./scripts/install-fcitx5-addon.sh
```

插件特性:预编辑流式显示、commit 延迟 <10ms、失败自动回退剪贴板粘贴。

## 快速开始

```bash
# 1. 安装系统依赖
sudo apt update
sudo apt install -y python3 python3-venv portaudio19-dev libevdev2 wl-clipboard ydotool

# 2. 克隆并安装
git clone https://github.com/lifuhaolife/voice-input.git
cd voice-input
uv sync

# 3. 配置 API（填入讯飞密钥）
nano config.yaml

# 4. 前台运行
uv run lb-voice

# 或后台运行
./scripts/voice-input.sh --background
```

## 功能特性

- 🎙️ **快捷键触发** - 按住快捷键录音，松开自动识别并输入到光标位置
- 🔄 **流式识别** - 支持讯飞流式语音识别，边说边显示，支持动态修正
- 🔌 **Web/API 识别** - 当前主线使用讯飞 WebSocket/API；不依赖本地 Whisper 模型
- ⚡ **低延迟** - 按键立即录音，连接期间缓存音频，松开后快速输出识别结果
- ⌨️ **自动输入** - GNOME Wayland 默认使用 wl-copy + ydotool Ctrl+V 粘贴
- 🔒 **单例运行** - 自动防止重复启动
- 🔔 **通知提示** - 可选的桌面通知反馈
- 🔧 **后台运行** - 支持后台守护进程模式运行
- 📝 **调试日志** - 默认不记录完整识别文本，只记录长度和链路诊断信息

## 系统要求

- **操作系统**: Ubuntu 20.04+ / Debian 11+ 或其他 Linux 发行版
- **Python**: 3.10+
- **桌面环境**: X11 或 Wayland
- **硬件**: 麦克风设备
- **API**: 讯飞/腾讯/百度开放平台账号（免费额度充足）

## 安装

### 1. 安装系统依赖

**Ubuntu/Debian:**

```bash
# 更新软件源
sudo apt update

# 安装基础依赖
sudo apt install -y python3 python3-pip python3-venv portaudio19-dev libevdev2

# GNOME Wayland 用户（当前推荐）
sudo apt install -y wl-clipboard ydotool

# X11 用户可额外安装
sudo apt install -y xdotool

# 其他 Wayland 合成器如支持 virtual keyboard，可选安装 wtype
sudo apt install -y wtype
```

**其他发行版:**

- **Arch Linux**: `sudo pacman -S python portaudio libevdev xdotool wtype`
- **Fedora**: `sudo dnf install python3 portaudio-devel libevdev xdotool wtype`

### 2. 克隆仓库

```bash
git clone https://github.com/lifuhaolife/voice-input.git
cd voice-input
```

### 3. 使用 uv 安装依赖

```bash
# 推荐：使用 uv 创建 .venv 并同步依赖
uv sync

# 验证命令入口
uv run lb-voice --version
```

如果需要传统安装方式，也可以运行 `./scripts/install.sh`，但开发和测试默认使用 `uv`。

### 4. 配置语音识别 API

#### 讯飞语音（推荐）

1. 访问 [讯飞开放平台](https://console.xfyun.cn/) 创建应用
2. 开通"语音听写（流式版）"服务
3. 获取 `APPID`、`APIKey`、`APISecret`

#### 腾讯云语音（备选）

1. 访问 [腾讯云语音识别](https://console.cloud.tencent.com/asr)
2. 开通"实时语音识别"服务
3. 获取 `AppID`、`SecretId`、`SecretKey`

#### 百度云语音（备选）

1. 访问 [百度 AI 开放平台](https://console.bce.baidu.com/ai/#/ai/speech/)
2. 创建应用并开通"短语音识别"
3. 获取 `AppID`、`API Key`、`Secret Key`

### 5. 创建配置文件

```bash
# 复制配置模板
cp config.yaml.example config.yaml

# 编辑配置文件
nano config.yaml  # 或使用你喜欢的编辑器
```

填入你的 API 密钥：

```yaml
# 选择后端: xunfei / tencent / baidu
backend: xunfei

# 讯飞配置
xunfei:
  app_id: "你的APPID"
  api_key: "你的APIKey"
  api_secret: "你的APISecret"
```

配置文件查找顺序：
1. `~/.config/voice-input/config.yaml`（推荐）
2. `~/.voice-input/config.yaml`
3. 项目目录下的 `config.yaml`

## 使用方法

### 首次使用

**重要**: 安装后需要重新登录系统，以使 `input` 组权限生效。

### CLI 启动和关闭

```bash
# 前台启动（推荐调试；按 Ctrl+C 关闭）
uv run lb-voice

# 后台启动（常用）
./scripts/voice-input.sh --background
# 或简写
./scripts/voice-input.sh -b

# 查看后台进程
ps -eo pid,cmd | grep lb-voice

# 关闭后台进程
kill <PID>

# 只关闭本项目后台进程
pkill -f "voice-input/.venv/bin/python3 .venv/bin/lb-voice"

# 查看后台日志
tail -f ~/.local/state/voice-input/voice-input.log
```

后台启动后，按住配置的热键（默认 `alt_r`）说话，松开后自动识别并粘贴到当前光标位置。

### 快捷键操作

- **按住** `右 Alt`（默认 `alt_r`）开始录音
- **松开** 自动停止录音并输入文字
- 识别结果会自动输入到当前光标位置

### 命令行选项

```bash
# 查看帮助
uv run lb-voice --help

# 列出音频设备
uv run lb-voice --list-devices

# 使用自定义配置
uv run lb-voice --config /path/to/config.yaml

# 详细日志（调试模式）
uv run lb-voice -v

# 查看版本
uv run lb-voice --version
```

## 配置说明

配置文件位于 `~/.config/voice-input/config.yaml`、`~/.voice-input/config.yaml` 或项目目录 `config.yaml`：

```yaml
# 语音识别后端
backend: xunfei  # xunfei / tencent / baidu

# 快捷键设置
hotkey:
  trigger: "alt_r"    # 支持: alt, alt_l, alt_r, ctrl, shift, super 或组合键
  mode: "hold"        # hold(按住) 或 toggle(切换)

# 录音设置
recording:
  sample_rate: 16000
  channels: 1
  chunk_ms: 80        # 每块音频时长(毫秒)，80-160ms 可降低 CPU 占用
  max_duration: 30    # 最长录音时长(秒)

# 常驻监听（V2.1，实验性，默认关闭）
resident:
  enabled: false          # 开启后麦克风持续采集；必须显式同意隐私取舍
  speech_rms_threshold: 500.0
  start_frames: 2         # 连续 2 帧(80ms/帧)确认说话，减少误触发
  end_silence_ms: 700     # 静音 hangover，避免词语间停顿切段
  min_speech_ms: 240      # 过短声音不提交 ASR
  prebuffer_ms: 240       # 回放确认前的音频，避免丢首字
  max_segment_ms: 60000   # 超长语音强制分段

# 讯飞语音识别配置
xunfei:
  app_id: ""
  api_key: ""
  api_secret: ""
  language: "zh_cn"   # zh_cn(中文), en_us(英文)
  accent: "mandarin"  # mandarin(普通话), cantonese(粤语)
  vad_eos: 5000       # 语音结束静默时长(毫秒)
  max_audio_queue_size: 400  # 流式识别发送队列最大长度
  batch_chunks: 4     # 每次发送的音频块数量（4-8 可减少 CPU 负载）
  reuse_connection: false      # 是否复用 WebSocket，默认关闭
  final_result_timeout: 3.0    # 无中间结果时等待服务端 final 的秒数

# 腾讯语音识别配置
tencent:
  app_id: ""
  secret_id: ""
  secret_key: ""

# 百度语音识别配置
baidu:
  app_id: ""
  api_key: ""
  secret_key: ""

# 音效反馈
sound:
  enabled: false

# 文本输入设置
input:
  method: "clipboard"  # clipboard(推荐) / xdotool / wtype / ydotool / type
  type_delay: 0.005

# 通知设置
notification:
  enabled: false       # 是否启用桌面通知
  show_status: false   # 显示录音状态通知
  show_result: false   # 显示识别结果通知

# 日志设置
logging:
  level: "info"       # debug, info, warning, error
  show_audio_chunks: false    # 打印音频块信息（debug 级别）
  show_recognized_text: false # 打印识别的文本内容（debug 级别）
```

### 输入方式说明

- **clipboard**（推荐）: GNOME Wayland 默认方案，使用 `wl-copy` 写入剪贴板，再用 `ydotool` 触发 Ctrl+V
- **xdotool**: X11 / XWayland 环境下模拟按键输入
- **wtype**: 仅适用于支持 virtual keyboard 协议的 Wayland 合成器；GNOME Wayland 通常不支持
- **ydotool**: uinput 方式，直接输入中文不可靠，主要用于发送 Ctrl+V
- **type**: 自动检测并选择合适的输入方式

### 调试模式

在 `config.yaml` 中设置：

```yaml
logging:
  level: "debug"
  show_audio_chunks: true      # 查看音频块处理
  show_recognized_text: true   # 查看识别文本内容
```

或使用命令行参数：

```bash
lb-voice -v
```

## 开机自启动

```bash
# 启用开机自启动
./scripts/enable-autostart.sh

# 禁用开机自启动
./scripts/disable-autostart.sh
```

## 故障排除

### 按住快捷键没有反应，日志出现 `Invalid sample rate [PaErrorCode -9997]`

说明程序没有运行在桌面会话环境里（缺少 `XDG_RUNTIME_DIR` 等变量），PortAudio 会退回到
裸 ALSA 硬件设备（如 `hw:0,0`，只支持 48kHz），导致 16kHz 录音直接失败。

```bash
# 从桌面终端启动（推荐），脚本会自动补齐会话变量
./scripts/voice-input.sh --background

# 检查日志中的音频自检结果
grep "音频输入就绪" ~/.local/state/voice-input/voice-input.log
```

程序启动时会做音频自检并打印 `音频输入就绪: 设备 N (default) @ 16000Hz`；
若设备本身不支持 16kHz，程序会自动改用它支持的采样率并重采样到 16kHz。

### 麦克风无法使用

```bash
# 检查麦克风设备
arecord -l

# 测试录音
arecord -d 3 test.wav
aplay test.wav

# 列出 lb-voice 识别的设备
lb-voice --list-devices
```

### 快捷键不响应

1. **权限问题**: 确保已将用户添加到 `input` 组并重新登录
   ```bash
   groups  # 检查是否包含 input 组
   sudo usermod -a -G input $USER  # 添加到 input 组
   ```

2. **快捷键冲突**: 尝试使用其他快捷键组合
   ```yaml
   hotkey:
     trigger: "ctrl+alt+v"  # 或其他组合
   ```

3. **设备权限**: 检查 `/dev/input/` 权限
   ```bash
   ls -l /dev/input/event*
   ```

### 文字没有输入到光标位置

1. **GNOME Wayland 用户**: 推荐使用剪贴板方案
   ```bash
   sudo apt install wl-clipboard ydotool
   
   # 配置文件中设置
   input:
     method: "clipboard"
   ```

   如果日志出现 `已复制到剪贴板，请按 Ctrl+V 粘贴`，说明识别和复制已完成，但自动 Ctrl+V 未触发，可先手动 Ctrl+V 验证剪贴板内容。

   常见原因是 `ydotoold` 以 root 运行，套接字 `/tmp/.ydotool_socket` 权限为
   `600 root:root`，普通用户无法连接（手动执行 `ydotool key 0:0` 会报
   `failed to open uinput device`）。执行一次以下脚本即可修复（需 sudo）：

   ```bash
   ./scripts/fix-ydotool-socket.sh
   ```

2. **X11 用户**: 确保安装了 xdotool
   ```bash
   sudo apt install xdotool
   
   # 配置文件中设置
   input:
     method: "xdotool"
   ```

3. **查看日志**
   ```bash
   tail -f ~/.local/state/voice-input/voice-input.log
   ```

### 程序已在运行错误

```bash
# 查找进程
ps aux | grep lb-voice

# 终止进程
kill <PID>

# 或删除锁文件
rm -f "$XDG_RUNTIME_DIR/voice-input.lock" ~/.local/share/voice-input/voice-input.lock
```

### 语音识别 API 错误

1. **检查配置**: 确认 `config.yaml` 中的 API 密钥正确
2. **检查网络**: 确保能访问对应的 API 服务
3. **查看日志**: 使用 `-v` 参数查看详细错误信息
   ```bash
   lb-voice -v
   ```
4. **检查额度**: 登录对应平台查看 API 调用额度

### CPU 占用过高

调整配置文件中的参数：

```yaml
recording:
  chunk_ms: 160  # 增大音频块时长

xunfei:
  batch_chunks: 8  # 增大批量发送数量
```

## 开发与测试

```bash
# 同步依赖
uv sync

# 运行无外部副作用的安全测试
uv run pytest -q -m "not live_api and not audio_device and not desktop_input and not manual"

# 代码检查
uv run ruff check src tests
uv run black --check src tests
```

默认测试不会调用真实 API、麦克风、剪贴板或桌面输入。真实 API / 音频 / 桌面输入测试需要人工确认后单独执行。

## 项目结构

```
voice-input/
├── src/voice_input/
│   ├── run.py               # 启动入口（处理日志和单例）
│   ├── main.py              # 主程序逻辑
│   ├── config.py            # 配置管理
│   ├── recorder.py          # 录音模块（流式）
│   ├── hotkey.py            # 快捷键监听
│   ├── typer.py             # 文本输入（支持X11/Wayland）
│   ├── sound.py             # 音效反馈
│   ├── notify.py            # 桌面通知
│   ├── process_lock.py      # 进程单例锁
│   ├── logger_config.py     # 日志配置
│   └── recognizer/          # 语音识别后端
│       ├── base.py          # 基类接口
│       ├── xunfei.py        # 讯飞流式识别
│       └── whisper_backend.py  # 历史/实验代码，当前主线不使用本地模型
├── scripts/
│   ├── install.sh           # 安装脚本
│   ├── voice-input.sh       # 启动脚本（支持后台运行）
│   ├── enable-autostart.sh  # 启用开机自启动
│   ├── disable-autostart.sh # 禁用开机自启动
│   ├── uninstall.sh         # 卸载脚本
│   └── lb-voice.desktop  # 桌面启动项
├── config.yaml.example      # 配置模板
├── pyproject.toml           # Python 项目配置
└── README.md
```

## 常见问题

**Q: 支持哪些语言？**  
A: 取决于选择的后端。讯飞支持中文（普通话、粤语）和英文。

**Q: 免费额度够用吗？**  
A: 讯飞每日 500 次免费调用，个人使用完全足够。

**Q: 可以离线使用吗？**  
A: 当前主线依赖 Web/API 语音识别，不使用 Whisper/Torch 等本地模型。

**Q: 支持 macOS 或 Windows 吗？**  
A: 目前仅支持 Linux。其他平台支持计划中。

**Q: 识别准确率如何？**  
A: 讯飞识别准确率较高，普通话环境下可达 95%+。

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

## 更新日志

### 当前分支：低延迟与 uv 测试基线

- ⚡ 热键监听改为事件等待，降低空闲 CPU 占用
- 🎙️ 按下热键后立即开始录音，连接 WebSocket 期间缓存音频，减少开头丢字
- 📋 GNOME Wayland 使用 `wl-copy` + `ydotool` 粘贴，避免直接中文输入失败
- 🔐 默认不记录完整识别文本，日志只记录长度和链路诊断
- 🧪 新增 pytest 安全测试基线，默认不触发真实 API / 麦克风 / 桌面输入
- 📦 使用 `uv` 管理 Python 环境和依赖锁定

### v1.0.0 (2026-03-22)

- 🎉 首个稳定版本发布
- ✨ 支持讯飞/腾讯/百度三种语音识别后端
- ✨ 支持 X11 和 Wayland 桌面环境
- ✨ 流式语音识别，实时返回结果
- ✨ 多种文本输入方式（剪贴板/xdotool/wtype/ydotool）
- ✨ 进程单例锁，防止重复运行
- ✨ 可选的桌面通知功能
- ✨ 完善的日志系统
- 📝 完整的文档和配置说明

## 致谢

- [讯飞开放平台](https://www.xfyun.cn/) - 提供优质的语音识别服务
- 所有贡献者和用户的支持
