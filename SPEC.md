# Voice Input — 项目规格书

> 语音流式输入工具:按住热键说话,松开文字直接出现在光标处。零粘贴、语境纠错、隐私合规。

- **版本**: v1.2.0
- **许可证**: MIT
- **平台**: Linux (GNOME Wayland, Ubuntu 24.04+)
- **输入法框架**: fcitx5
- **ASR 后端**: 讯飞流式听写(可插拔)

---

## 1. 项目目标

在 Linux 桌面上实现与 Windows 语音输入同等的体验:
- 按住热键说话 → 文字逐段出现在光标处
- 松开 → 语境纠错后的最终文本替换已上屏内容
- 零粘贴、零退格删除、隐私合规(松开即停止采集)

## 2. 架构

### 2.1 组件图

```
┌─ voice-input daemon (Python, systemd 用户服务) ──────────────┐
│                                                              │
│  HotkeyListener (evdev, Alt_R)                              │
│       │                                                      │
│       ▼                                                      │
│  StreamingRecorder (PortAudio, 16kHz/80ms帧)                │
│       │                                                      │
│       ▼                                                      │
│  ASR 后端适配层 (backends/)                                  │
│       ├─ XunfeiBackend (讯飞流式听写, dwa=wpgs)             │
│       └─ (V2.2: funasr / 腾讯 / 百度 …)                     │
│       │                                                      │
│       ▼                                                      │
│  VoiceIMClient (Unix socket IPC)                            │
│       │ 失败回退: wl-clipboard + ydotool 粘贴                │
└───────┼──────────────────────────────────────────────────────┘
        │ /run/user/$UID/voice-input/im.sock
        │ 行分隔 JSON
┌───────▼───────────────────────────────────────────────────────┐
│  fcitx5 voiceim 插件 (C++, 常驻 fcitx5 进程)                  │
│    partial → inputPanel().setClientPreedit()                  │
│    final   → commitString() (原子替换预编辑)                   │
│    普通按键全部透传                                             │
└───────────────────────────────────────────────────────────────┘
```

### 2.2 组件职责

| 组件 | 语言 | 职责 | 迭代频率 |
|---|---|---|---|
| daemon (`src/voice_input/`) | Python | 热键、录音、ASR 对接、纠错、分段策略、回退 | 高 |
| fcitx5 插件 (`fcitx5-addon/`) | C++ | 预编辑渲染、文字提交(必须在 fcitx5 进程内) | 极低 |
| 后端适配层 (`backends/`) | Python | ASR 服务商适配(可插拔) | 中 |
| IPC (`ipc/`) | Python | Unix socket 客户端 | 低 |

### 2.3 数据流

```
用户按住 Alt_R
  │
  ├─ daemon: 切换到 voice IM (fcitx5-remote -s voice)
  ├─ daemon: 注入 Shift 敲击(强制 IC 重挂载 voice 引擎)
  ├─ daemon: recorder.start() → 80ms 帧队列
  │
  │    讯飞 WS(流式) ◄── 80ms/批 音频
  │         │
  │         ▼ 中间结果(partial) ──► commitString(增量上屏)
  │         ▼ 最终结果(final)   ──► commitString(完整文本)
  │
用户松开 Alt_R
  │
  ├─ daemon: recorder.stop() → end frame → 等服务端 final
  └─ commit 完成 → 下一会话预热
```

## 3. IPC 协议

### 3.1 传输层

| 属性 | 值 |
|---|---|
| 类型 | Unix 流式套接字 (SOCK_STREAM) |
| 路径 | `$XDG_RUNTIME_DIR/voice-input/im.sock` |
| 格式 | 行分隔 JSON (UTF-8, `\n` 分隔) |
| 生命周期 | 插件创建并监听,daemon 连接;fcitx5 重启后自动重建 |

### 3.2 握手

1. 客户端 connect → 插件 accept
2. 插件注册 IO watcher(边缘触发语义)
3. 插件手动 drain 一次(处理注册前已到达的数据)
4. 插件发送 `{"type":"ready"}`
5. 客户端收到 ready 后才开始发数据(保证不丢边缘事件)

### 3.3 消息类型

| 方向 | type | 字段 | 说明 |
|---|---|---|---|
| C→P | `partial` | text | 中间结果(预编辑区显示) |
| C→P | `final` | text | 最终结果(原子替换预编辑) |
| C→P | `ping` | — | 心跳 |
| P→C | `ready` | — | 通道就绪握手 |
| P→C | `ack` | committed (bool) | final 处理确认 |
| P→C | `pong` | — | ping 应答 |

### 3.4 焦点未就绪处理

当 `final` 到达但焦点 IC 未就绪时(切换 IM 竞态):
1. 插件暂存文本,每 100ms 重试 commit
2. 最多 30 次(3 秒)
3. 超时后发送 `ack: committed=false`
4. 客户端转剪贴板回退

## 4. 模块规格

### 4.1 `src/voice_input/main.py` — 主控制器

| 方法 | 职责 |
|---|---|
| `_on_hotkey_press` | 门控打开:切 IM + Shift 注入 + recorder.start + relay 会话激活 |
| `_on_hotkey_release` | 门控关闭:recorder.stop + relay.finish_segment(后台 final commit) |
| `_on_resident_result` | 处理讯飞中间结果:增量 commit 到光标 |
| `_on_relay_result` | relay 会话结果回调(委托 _on_resident_result) |
| `_on_relay_final` | relay 最终结果:替换式上屏(退格+commit)或回退 |
| `_on_resident_final` | 常驻模式最终结果:同上 |

### 4.2 `src/voice_input/backends/` — ASR 后端适配层

| 后端 | 文件 | 中间结果粒度 | 纠错 | 免费额度 |
|---|---|---|---|---|
| xunfei | xunfei_backend.py | 2~8s/批(服务端决定) | ✅ dwa=wpgs | ✅ 每日免费 |
| funasr | (V2.2) | 200~300ms/批 | ❌ | ✅ 离线免费 |
| whisper | whisper_backend.py | 非流式(松开后一次性) | ❌ | ✅ 离线免费 |

### 4.3 `fcitx5-addon/voiceim.cpp` — fcitx5 插件

| 方法 | 职责 |
|---|---|
| `do_process_key_event` | 拦截 Alt_R(键码 100),按住→开始,松开→结束 |
| `do_enable` / `do_disable` | 引擎激活/停用生命周期 |
| `_session_worker` | 单次录音会话:等待松开→收最终结果→commit |
| `_on_result` | 处理讯飞中间/最终结果 |
| `_update_preedit` | 设置预编辑文字 |
| `_commit_and_clear` | 清预编辑 + commitString |

### 4.4 `src/voice_input/resident.py` — 会话接力

| 方法 | 职责 |
|---|---|
| `warm` | 后台创建+启动新 ASR 会话 |
| `is_ready` | 会话是否可接收音频 |
| `send_audio` | 向活跃会话发送音频 |
| `finish_segment` | 结束当前段,后台等 final,立即 warm 下一会话 |
| `recycle_if_stale` | 空闲会话超时回收 |

## 5. 配置规格

### 5.1 `config.yaml`

```yaml
backend: xunfei          # ASR 后端: xunfei / funasr / whisper

hotkey:
  trigger: "alt_r"       # 触发键: alt_r / alt_l / ctrl 等
  mode: "hold"           # hold(按住) / toggle(切换)

recording:
  sample_rate: 16000
  channels: 1
  chunk_ms: 80           # 音频帧大小(毫秒)
  max_duration: 30       # 单次最长录音(秒)

xunfei:
  app_id: "..."
  api_key: "..."
  api_secret: "..."
  language: "zh_cn"
  accent: "mandarin"
  vad_eos: 60000
  batch_chunks: 1        # 音频批次大小(1=最低延迟)
  reuse_connection: false

input:
  method: "clipboard"    # clipboard / fcitx5_plugin

resident:
  enabled: false         # 常驻监听(VAD 自动分段,无需热键)
  speech_rms_threshold: 500
  start_frames: 2
  end_silence_ms: 700

logging:
  level: "info"
  timeline: true         # 毫秒级时间线日志
```

### 5.2 fcitx5 插件配置

| 文件 | 位置 | 说明 |
|---|---|---|
| `voiceim.conf` | `/usr/share/fcitx5/addon/` | 插件注册(Type=SharedLibrary, Library=libvoiceim) |
| `voice.conf` | `/usr/share/fcitx5/inputmethod/` | 输入法条目(Name=voice, Addon=voiceim) |

**注意**: inputmethod 条目必须有 `Addon=` 字段关联插件名,否则不注册。

## 6. 部署规格

### 6.1 依赖

| 包 | 用途 |
|---|---|
| fcitx5 | 输入法框架 |
| libfcitx5core-dev | 插件编译 |
| portaudio19-dev | 麦克风采集 |
| ydotool | 键盘注入(Shift 敲击/回退) |
| wl-clipboard | 剪贴板(回退粘贴) |
| uv | Python 包管理 |

### 6.2 服务

| 服务 | 类型 | 说明 |
|---|---|---|
| `voice-input.service` | systemd 用户服务 | daemon 常驻 |
| `fcitx5` | 桌面自动启动 | 输入法框架 |

### 6.3 安装步骤

```bash
# 1. 系统依赖
sudo apt install -y python3 python3-venv portaudio19-dev libevdev2 \
  wl-clipboard ydotool libfcitx5core-dev cmake g++

# 2. Python 环境
uv sync

# 3. 配置 API 密钥
cp config.yaml.example config.yaml
nano config.yaml  # 填入讯飞 app_id/api_key/api_secret

# 4. 构建 fcitx5 插件
cd fcitx5-addon && cmake -S . -B build && cmake --build build && cd ..
sudo cp fcitx5-addon/build/libvoiceim.so /usr/lib/x86_64-linux-gnu/fcitx5/
sudo cp fcitx5-addon/voiceim.conf /usr/share/fcitx5/addon/
sudo cp fcitx5-addon/voice.conf /usr/share/fcitx5/inputmethod/

# 5. 安装 systemd 服务
mkdir -p ~/.config/systemd/user
cp ops/voice-input.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now voice-input.service

# 6. 重启 fcitx5
pkill -x fcitx5 && setsid fcitx5 &
```

## 7. 测试规格

| 测试文件 | 覆盖 | 运行环境 |
|---|---|---|
| test_config_and_entrypoints.py | 配置加载/入口点 | CI + 本地 |
| test_hotkey_listener.py | 热键解析 | CI + 本地 |
| test_xunfei_streamer.py | 讯飞流式协议解析 | CI + 本地 |
| test_resident_listening.py | 常驻监听 VAD/接力 | CI + 本地 |
| test_recorder.py | 录音器(需麦克风) | 仅本地 |
| test_streaming_voice_input.py | 端到端集成(需麦克风) | 仅本地 |
| test_text_input.py | 文字输入 | 仅本地 |

CI 运行命令:
```bash
uv run pytest -q \
  --ignore=tests/test_streaming_voice_input.py \
  --ignore=tests/test_recorder.py \
  --ignore=tests/test_hotkey_listener.py \
  --ignore=tests/test_text_input.py
```

## 8. 已知限制

| # | 限制 | 原因 | 可能的解决方案 |
|---|---|---|---|
| 1 | 中间结果粒度 2~8s/批 | 讯飞服务端出字节奏(dwa=wpgs) | V2.2 funasr 本地后端(200~300ms) |
| 2 | Codex/Electron 不渲染 client 预编辑 | Electron 对 fcitx5 client preedit 支持不完整 | 面板预编辑(悬浮窗)或无预编辑 |
| 3 | GNOME Wayland 不支持 fcitx5 waylandim | GNOME 未实现 zwp_input_method_v2 | 通过 GTK_IM_MODULE=fcitx 使用 |
| 4 | 切 IM 后 IC focusOut 不自动恢复 | GNOME/GTK IM 模块行为 | Shift 敲击注入(已实现) |
| 5 | 短句(<2s)无流式可看 | 服务端不返回中间结果 | 松开后一次性 commit |

## 9. 路线图

| 版本 | 内容 | 状态 |
|---|---|---|
| v1.0.0 | 讯飞流式 + 剪贴板自动粘贴 | ✅ 已发布 |
| v1.1.0 | fcitx5 原生流式插件 | ✅ 已发布 |
| v1.2.0 | 热键门控+预热接力+分段上屏+时间线 | ✅ 已发布 |
| v1.3.0 | 稳定版(当前) | ✅ 运行中 |
| **v2.0.0** | funasr 本地后端(200~300ms 出字) | 📋 规划 |
| **v2.1.0** | 常驻监听模式(VAD 自动分段) | 📋 规划 |
| **v3.0.0** | 开源化收尾(双语 README/CONTRIBUTING/演示 GIF) | 📋 规划 |

## 10. 文件清单

```
voice-input/
├── SPEC.md                      ← 本文件
├── README.md                    ← 项目说明(中文)
├── CHANGELOG.md                 ← 更新日志
├── LICENSE                      ← MIT
├── config.yaml                  ← 运行配置(含 API 密钥,.gitignore 排除)
├── config.yaml.example          ← 配置模板
├── pyproject.toml               ← Python 项目定义
├── uv.lock                      ← 依赖锁定
├── src/voice_input/             ← Python 源码
│   ├── main.py                  ← 主控制器
│   ├── run.py                   ← 入口点
│   ├── config.py                ← 配置加载
│   ├── hotkey.py                ← 热键监听(evdev)
│   ├── recorder.py              ← 录音器(PortAudio)
│   ├── typer.py                 ← 文字输入(剪贴板/ydotool)
│   ├── timeline.py              ← 毫秒级时间线
│   ├── resident.py              ← ASR 会话接力
│   ├── vad.py                   ← 能量 VAD
│   ├── recognizer/              ← ASR 后端(讯飞/whisper)
│   ├── backends/                ← ASR 后端抽象层(V2)
│   ├── ipc/                     ← Unix socket IPC 客户端
│   └── ibus_engine/             ← IBus 引擎(实验性,已废弃)
├── fcitx5-addon/                ← fcitx5 C++ 插件
│   ├── voiceim.cpp              ← 插件实现
│   ├── voiceim.conf             ← 插件注册
│   ├── voice.conf               ← 输入法条目
│   └── CMakeLists.txt           ← 构建配置
├── scripts/                     ← 部署/运维脚本
│   ├── voice-input.sh           ← 启动器
│   ├── install.sh               ← 安装
│   ├── uninstall.sh             ← 卸载
│   ├── build-fcitx5-addon.sh    ← 构建插件
│   ├── install-fcitx5-addon.sh  ← 安装插件
│   └── calibrate-resident.py    ← VAD 校准
├── ops/github-workflows/        ← GitHub Actions(待 workflow scope 启用)
├── tests/                       ← 测试套件
└── docs/                        ← 文档
```

