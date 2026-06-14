# Voice Input v1.0.0 发布清单

## ✅ 已完成

### 文档
- [x] README.md 更新到 v1.0.0
- [x] 添加完整的 Ubuntu 安装指南
- [x] 说明所有系统依赖
- [x] 添加多后端支持说明
- [x] 添加通知功能说明
- [x] 更新配置文件说明

### 代码
- [x] 版本号更新到 1.0.0 (pyproject.toml, main.py)
- [x] 进程单例锁实现
- [x] 日志系统完善
- [x] 多后端支持（讯飞/腾讯/百度）
- [x] 桌面通知功能
- [x] 后台运行支持

### 脚本
- [x] install.sh - 自动安装脚本
- [x] lb-voice.sh - 启动脚本（支持后台运行）
- [x] enable-autostart.sh - 开机自启动
- [x] disable-autostart.sh - 禁用自启动

## 📋 发布前检查

### 1. 依赖检查

**Python 依赖** (pyproject.toml):
```
sounddevice>=0.4.6
numpy>=1.24.0
pyyaml>=6.0
websocket-client>=1.6.0
pyperclip>=1.8.2
python-xlib>=0.33
evdev>=1.6.1
```

**系统依赖** (Ubuntu/Debian):
```bash
# 必需
python3 (>=3.10)
python3-pip
python3-venv
portaudio19-dev
libevdev2

# 输入工具（至少一个）
xdotool (X11)
wtype (Wayland 推荐)
ydotool (Wayland 备选)

# 可选
xclip (剪贴板 - X11)
wl-clipboard (剪贴板 - Wayland)
```

### 2. 功能测试清单

#### 基础功能
- [ ] 安装脚本正常运行
- [ ] 虚拟环境创建成功
- [ ] 依赖安装无错误
- [ ] 配置文件正确加载
- [ ] 命令行工具可用 (`lb-voice --version`)

#### 录音功能
- [ ] 麦克风设备正确识别 (`lb-voice --list-devices`)
- [ ] 快捷键触发录音
- [ ] 录音状态正确显示
- [ ] 音频流正常采集

#### 语音识别
- [ ] 讯飞 API 连接正常
- [ ] 流式识别实时返回
- [ ] 识别结果准确
- [ ] 错误处理正确

#### 文本输入
- [ ] X11 环境 xdotool 输入正常
- [ ] Wayland 环境 wtype 输入正常
- [ ] 剪贴板方式输入正常
- [ ] 中文输入无乱码

#### 进程管理
- [ ] 单例锁防止重复启动
- [ ] 前台运行正常退出
- [ ] 后台运行正常启动
- [ ] 进程终止清理正确

#### 日志系统
- [ ] 日志文件正确创建 (`~/.local/share/lb-voice/logs/`)
- [ ] 日志级别配置生效
- [ ] 调试模式输出详细信息

#### 通知功能
- [ ] 桌面通知正常显示（如启用）
- [ ] 通知内容正确

### 3. 兼容性测试

#### 桌面环境
- [ ] GNOME (X11)
- [ ] GNOME (Wayland)
- [ ] KDE Plasma
- [ ] XFCE
- [ ] 其他 DE

#### Ubuntu 版本
- [ ] Ubuntu 20.04 LTS
- [ ] Ubuntu 22.04 LTS
- [ ] Ubuntu 24.04 LTS

#### 其他发行版（可选）
- [ ] Debian 11/12
- [ ] Arch Linux
- [ ] Fedora

### 4. 文档验证

- [ ] README 中的所有命令可执行
- [ ] 配置示例正确
- [ ] 故障排除步骤有效
- [ ] API 申请链接可访问

### 5. 发布准备

#### Git 仓库
- [ ] 所有更改已提交
- [ ] 创建 v1.0.0 标签
- [ ] 推送到 GitHub

#### GitHub Release
- [ ] 创建 Release v1.0.0
- [ ] 添加更新日志
- [ ] 上传必要文件（如有）

#### 可选
- [ ] 创建演示视频/GIF
- [ ] 添加截图到 README
- [ ] 准备社区发布文案

## 🐛 已知问题

### 需要修复
1. **锁文件位置不一致**
   - `lb-voice.sh` 使用 `/tmp/lb-voice.lock`
   - `process_lock.py` 使用 `~/.local/share/lb-voice/lb-voice.lock`
   - **建议**: 统一使用 `~/.local/share/lb-voice/lb-voice.lock`

2. **配置文件默认值不一致**
   - `config.py` 默认 `input.method: "type"`
   - `config.yaml.example` 默认 `input.method: "clipboard"`
   - **建议**: 统一使用 `"clipboard"` 作为默认值

3. **快捷键说明不一致**
   - README 说默认是 `Alt+M`
   - config.yaml.example 默认是 `alt_r`（右 Alt）
   - **建议**: 明确说明 `alt_r` 就是右 Alt 键

### 待改进
1. 添加更详细的错误提示
2. 支持更多快捷键组合
3. 添加配置验证功能
4. 改进 Whisper 本地识别（实验性）

## 📝 发布后任务

1. 监控 GitHub Issues
2. 收集用户反馈
3. 更新文档（根据反馈）
4. 规划 v1.1.0 功能

## 🔗 相关链接

- GitHub: https://github.com/lifuhaolife/lb-voice
- 讯飞开放平台: https://console.xfyun.cn/
- 腾讯云语音: https://console.cloud.tencent.com/asr
- 百度 AI: https://console.bce.baidu.com/ai/#/ai/speech/
