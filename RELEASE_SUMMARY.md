# Voice Input v1.0.0 发布总结

## 📦 项目概述

**Voice Input** 是一个 Linux 平台的流式语音输入工具，支持通过快捷键触发语音识别，并将识别结果自动输入到光标位置。

- **版本**: v1.0.0
- **发布日期**: 2026-03-22
- **许可证**: MIT
- **平台**: Linux (Ubuntu 20.04+)

## ✨ 核心功能

1. **流式语音识别** - 支持讯飞/腾讯/百度三种后端
2. **快捷键触发** - 按住录音，松开识别
3. **自动输入** - 支持 X11/Wayland 桌面环境
4. **单例运行** - 防止重复启动
5. **后台模式** - 支持守护进程运行
6. **桌面通知** - 可选的状态反馈
7. **完善日志** - 便于调试和问题排查

## 🎯 目标用户

- Linux 桌面用户
- 需要频繁文字输入的工作者
- 中文输入用户（支持普通话、粤语）
- 开发者和内容创作者

## 📋 系统要求

### 最低要求
- Ubuntu 20.04+ / Debian 11+
- Python 3.10+
- 2GB RAM
- 麦克风设备
- 网络连接（API 调用）

### 推荐配置
- Ubuntu 22.04 LTS
- Python 3.11+
- 4GB RAM
- 高质量麦克风
- 稳定网络连接

## 🔧 依赖清单

### 系统依赖
```bash
python3 python3-pip python3-venv
portaudio19-dev
libevdev2
xdotool (X11) / wtype (Wayland)
xclip wl-clipboard (可选)
```

### Python 依赖
```
sounddevice>=0.4.6
numpy>=1.24.0
pyyaml>=6.0
websocket-client>=1.6.0
pyperclip>=1.8.2
python-xlib>=0.33
evdev>=1.6.1
```

## 📖 文档清单

1. **README.md** - 完整使用文档
2. **INSTALL_UBUNTU.md** - Ubuntu 快速安装指南
3. **RELEASE_CHECKLIST.md** - 发布检查清单
4. **config.yaml.example** - 配置文件模板
5. **OPTIMIZATION.md** - 性能优化说明

## 🚀 安装方式

### 方式一：自动安装（推荐）

```bash
git clone https://github.com/lifuhaolife/lb-voice.git
cd lb-voice
./scripts/install.sh
```

### 方式二：手动安装

```bash
# 安装系统依赖
sudo apt install -y python3 python3-pip python3-venv portaudio19-dev libevdev2 xdotool wtype

# 克隆项目
git clone https://github.com/lifuhaolife/lb-voice.git
cd lb-voice

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装 Python 依赖
pip install -e .

# 配置 API
cp config.yaml.example config.yaml
nano config.yaml
```

## 🎮 使用流程

1. **申请 API** - 访问讯飞开放平台申请免费 API
2. **配置密钥** - 编辑 `config.yaml` 填入凭证
3. **启动程序** - 运行 `lb-voice`
4. **使用快捷键** - 按住 Alt 键录音，松开识别
5. **自动输入** - 识别结果自动输入到光标位置

## 🔍 测试建议

### 基础测试
- [ ] 安装脚本执行成功
- [ ] 命令行工具可用
- [ ] 配置文件正确加载
- [ ] 麦克风设备识别

### 功能测试
- [ ] 快捷键触发录音
- [ ] 语音识别准确
- [ ] 文字正确输入
- [ ] 中文无乱码

### 兼容性测试
- [ ] Ubuntu 20.04 LTS
- [ ] Ubuntu 22.04 LTS
- [ ] Ubuntu 24.04 LTS
- [ ] GNOME (X11/Wayland)
- [ ] KDE Plasma

## ⚠️ 已知限制

1. **仅支持 Linux** - macOS/Windows 暂不支持
2. **需要网络** - 依赖云端 API（本地 Whisper 实验中）
3. **API 额度** - 讯飞免费版每日 500 次
4. **输入法兼容** - 部分输入法可能需要使用剪贴板方式
5. **权限要求** - 需要 input 组权限（快捷键监听）

## 🐛 已知问题

### 已修复
- ✅ 锁文件路径不一致 - 统一使用 `~/.local/share/lb-voice/`
- ✅ 默认输入方式 - 改为 `clipboard` 提高兼容性
- ✅ 版本号不一致 - 统一更新到 1.0.0

### 待改进
- 添加更多快捷键组合支持
- 改进错误提示信息
- 完善 Whisper 本地识别
- 支持更多桌面环境

## 📊 性能指标

### 延迟
- 录音启动: < 100ms
- 流式识别: 实时返回（边说边显示）
- 文字输入: < 50ms

### 资源占用
- 内存: ~50-100MB
- CPU: 录音时 5-15%（可通过配置优化）
- 网络: 流式传输，约 16KB/s

## 🔐 安全考虑

1. **API 密钥** - 存储在本地配置文件，不上传
2. **音频数据** - 仅发送到选定的 API 服务商
3. **权限最小化** - 仅请求必要的系统权限
4. **进程隔离** - 使用虚拟环境运行

## 📈 后续计划

### v1.1.0 (计划)
- [ ] 支持更多语音识别后端
- [ ] 改进 Whisper 本地识别
- [ ] 添加语音命令功能
- [ ] 支持自定义词库

### v1.2.0 (计划)
- [ ] GUI 配置界面
- [ ] 系统托盘图标
- [ ] 录音波形显示
- [ ] 识别历史记录

### 长期计划
- macOS 支持
- Windows 支持
- 多语言界面
- 插件系统

## 🤝 贡献指南

欢迎提交：
- Bug 报告
- 功能建议
- 代码贡献
- 文档改进

提交方式：
- GitHub Issues: https://github.com/lifuhaolife/lb-voice/issues
- Pull Requests: https://github.com/lifuhaolife/lb-voice/pulls

## 📞 支持渠道

- **文档**: README.md 和 INSTALL_UBUNTU.md
- **Issues**: GitHub Issues
- **讨论**: GitHub Discussions（如启用）

## 📝 发布清单

- [x] 代码完成并测试
- [x] 文档更新完整
- [x] 版本号统一更新
- [x] 配置文件示例完善
- [x] 安装脚本测试通过
- [ ] 创建 Git 标签 v1.0.0
- [ ] 推送到 GitHub
- [ ] 创建 GitHub Release
- [ ] 添加更新日志
- [ ] 社区宣传（可选）

## 🎉 致谢

- 讯飞开放平台 - 提供优质的语音识别服务
- 开源社区 - 提供的各种工具和库
- 早期测试用户 - 反馈和建议

---

**发布者**: lifuhaolife  
**发布日期**: 2026-03-22  
**项目地址**: https://github.com/lifuhaolife/lb-voice
