#!/bin/bash
# Install voice-input

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🔧 安装 Voice Input..."

# 1. 创建虚拟环境并安装依赖
cd "$PROJECT_DIR"
if [ ! -d "venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv
fi

echo "📦 安装 Python 依赖..."
source venv/bin/activate
pip install --upgrade pip -q
pip install -e . -q

# 2. 创建符号链接
echo "🔗 创建系统命令..."
sudo ln -sf "$PROJECT_DIR/scripts/voice-input.sh" /usr/local/bin/lb-voice

# 3. 安装桌面快捷方式
echo "🖥️  安装桌面启动项..."
mkdir -p ~/.local/share/applications
cp "$SCRIPT_DIR/voice-input.desktop" ~/.local/share/applications/

# 4. 添加用户到 input 组
if ! groups | grep -q input; then
    echo "🔐 添加用户到 input 组..."
    sudo usermod -a -G input $USER
    NEED_RELOGIN=true
fi

# 5. 创建配置文件
if [ ! -f "$PROJECT_DIR/config.yaml" ]; then
    echo "📝 创建配置文件..."
    cp "$PROJECT_DIR/config.yaml.example" "$PROJECT_DIR/config.yaml"
fi

echo ""
echo "✅ 安装完成！"
echo ""
echo "📝 下一步："
echo "1. 编辑配置文件填入 API 密钥："
echo "   nano $PROJECT_DIR/config.yaml"
echo ""
if [ "$NEED_RELOGIN" = true ]; then
    echo "2. 重新登录系统（使 input 组权限生效）"
    echo ""
    echo "3. 启动程序："
else
    echo "2. 启动程序："
fi
echo "   lb-voice"
echo ""