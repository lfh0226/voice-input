# Voice Input - Ubuntu 快速安装指南

## 一键安装（推荐）

```bash
# 1. 安装系统依赖
sudo apt update
sudo apt install -y python3 python3-pip python3-venv portaudio19-dev libevdev2 xdotool wtype xclip wl-clipboard

# 2. 克隆项目
git clone https://github.com/lifuhaolife/lb-voice.git
cd lb-voice

# 3. 运行安装脚本
./scripts/install.sh

# 4. 配置 API
cp config.yaml.example config.yaml
nano config.yaml  # 填入你的讯飞 API 密钥

# 5. 重新登录系统（使 input 组权限生效）
# 然后运行
lb-voice
```

## 系统依赖说明

### 必需依赖

| 包名 | 用途 | 安装命令 |
|------|------|----------|
| python3 | Python 运行环境 (>=3.10) | `sudo apt install python3` |
| python3-pip | Python 包管理器 | `sudo apt install python3-pip` |
| python3-venv | 虚拟环境支持 | `sudo apt install python3-venv` |
| portaudio19-dev | 音频采集库 | `sudo apt install portaudio19-dev` |
| libevdev2 | 输入设备事件库 | `sudo apt install libevdev2` |

### 输入工具（根据桌面环境选择）

| 桌面环境 | 推荐工具 | 安装命令 |
|----------|----------|----------|
| X11 | xdotool | `sudo apt install xdotool` |
| Wayland | wtype | `sudo apt install wtype` |
| Wayland (备选) | ydotool | `sudo apt install ydotool` |
| 通用（推荐） | 剪贴板 | `sudo apt install xclip wl-clipboard` |

## Python 依赖

安装脚本会自动安装以下 Python 包：

```
sounddevice>=0.4.6      # 音频录制
numpy>=1.24.0           # 数值计算
pyyaml>=6.0             # 配置文件解析
websocket-client>=1.6.0 # WebSocket 通信
pyperclip>=1.8.2        # 剪贴板操作
python-xlib>=0.33       # X11 窗口管理
evdev>=1.6.1            # 输入设备监听
```

## API 申请

### 讯飞语音（推荐）

1. 访问 https://console.xfyun.cn/
2. 注册/登录账号
3. 创建新应用
4. 开通"语音听写（流式版）"服务
5. 获取凭证：
   - APPID
   - APIKey
   - APISecret

**免费额度**: 每日 500 次调用

### 配置示例

编辑 `config.yaml`:

```yaml
backend: xunfei

xunfei:
  app_id: "12345678"
  api_key: "abcdef1234567890abcdef12"
  api_secret: "abcdef1234567890abcdef1234567890"
```

## 验证安装

```bash
# 检查版本
lb-voice --version

# 列出音频设备
lb-voice --list-devices

# 测试运行（前台）
lb-voice

# 后台运行
./scripts/lb-voice.sh -b
```

## 常见问题

### 1. 快捷键不响应

```bash
# 检查是否在 input 组
groups

# 如果没有，添加并重新登录
sudo usermod -a -G input $USER
```

### 2. 麦克风无法使用

```bash
# 测试麦克风
arecord -d 3 test.wav && aplay test.wav

# 检查设备
lb-voice --list-devices
```

### 3. 文字无法输入

在 `config.yaml` 中设置：

```yaml
input:
  method: "clipboard"  # 最稳定的方式
```

### 4. 程序已在运行

```bash
# 查找进程
ps aux | grep lb-voice

# 终止进程
kill <PID>

# 或删除锁文件
rm -f ~/.local/share/lb-voice/lb-voice.lock
```

## 卸载

```bash
cd lb-voice
./scripts/uninstall.sh
```

## 获取帮助

- GitHub Issues: https://github.com/lifuhaolife/lb-voice/issues
- 完整文档: [README.md](README.md)
