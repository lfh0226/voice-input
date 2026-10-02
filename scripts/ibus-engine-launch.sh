#!/bin/bash
# IBus 引擎启动器：由 ibus-daemon 调用，切换到工作目录后运行引擎
cd "$(dirname "$0")/.."

# ibus write-cache / ibus-daemon 会用 --xml 询问组件的引擎清单
if [ "${1:-}" = "--xml" ]; then
    cat << 'EOF'
<?xml version="1.0" encoding="utf-8"?>
<engines>
  <engine>
    <name>voice-input</name>
    <language>*</language>
    <license>MIT</license>
    <author>lfh</author>
    <layout>default</layout>
    <longname>Voice Input (流式语音)</longname>
    <description>按住 Alt_R 说话，松开上屏（流式，不使用剪贴板）</description>
    <rank>99</rank>
    <icon>audio-input-microphone</icon>
    <symbol>🎤</symbol>
  </engine>
</engines>
EOF
    exit 0
fi

exec .venv/bin/python -m voice_input.ibus_engine.main
