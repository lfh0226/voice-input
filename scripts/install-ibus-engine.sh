#!/bin/bash
# 安装 voice-input IBus 引擎（用户级）
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPONENT_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/ibus/component"

chmod +x "$PROJECT_DIR/scripts/ibus-engine-launch.sh"
mkdir -p "$COMPONENT_DIR"
cp "$PROJECT_DIR/scripts/voice-input-ibus.component" "$COMPONENT_DIR/"

echo "✅ 组件已安装到 $COMPONENT_DIR/voice-input-ibus.component"
echo "执行 ibus write-cache 刷新引擎列表..."
ibus write-cache
echo "完成。然后在 GNOME 设置或 Super+Space 里切换到 'Voice Input (流式语音)' 输入法。"

