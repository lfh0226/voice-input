#!/bin/bash
# 安装 fcitx5 voice 插件到用户目录并重启 fcitx5
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

mkdir -p ~/.local/lib/fcitx5 ~/.local/share/fcitx5/addon
cp "$DIR/fcitx5-addon/build/libvoiceim.so" ~/.local/lib/fcitx5/voiceim.so
cp "$DIR/fcitx5-addon/voiceim.conf" ~/.local/share/fcitx5/addon/voiceim.conf

echo "✅ 插件已安装,重启 fcitx5..."
systemctl --user try-restart fcitx5-restored.service 2>/dev/null || true
sleep 1
pkill -HUP fcitx5 2>/dev/null || true
echo "完成。输入法列表中应出现 '语音输入 (流式)'"

