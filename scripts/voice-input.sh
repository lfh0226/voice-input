#!/bin/bash
# Voice Input Launcher

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# 恢复桌面会话环境变量。
# 如果缺少 XDG_RUNTIME_DIR / PULSE_SERVER 等变量，PortAudio 会退回到裸 ALSA
# 硬件设备（如 hw:0,0，只支持 48kHz），导致 16kHz 录音直接失败。
if [ -z "${XDG_RUNTIME_DIR:-}" ] && [ -d "/run/user/$(id -u)" ]; then
    export XDG_RUNTIME_DIR="/run/user/$(id -u)"
fi

if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ] && [ -S "${XDG_RUNTIME_DIR:-/nonexistent}/bus" ]; then
    export DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus"
fi

if [ -z "${WAYLAND_DISPLAY:-}" ] && [ -n "${XDG_RUNTIME_DIR:-}" ]; then
    for sock in "$XDG_RUNTIME_DIR"/wayland-*; do
        case "$sock" in
            *.lock) continue ;;
        esac
        if [ -S "$sock" ]; then
            export WAYLAND_DISPLAY="$(basename "$sock")"
            break
        fi
    done
fi

if [ -z "${DISPLAY:-}" ]; then
    export DISPLAY=":0"
fi

# 粘贴环节自检：Wayland 下自动 Ctrl+V 依赖 ydotoold 套接字对当前用户可读写
if [ "${XDG_SESSION_TYPE:-}" = "wayland" ] && command -v ydotool >/dev/null 2>&1; then
    if [ ! -r /tmp/.ydotool_socket ] || [ ! -w /tmp/.ydotool_socket ]; then
        echo "⚠️  ydotool 套接字不可读写（$(ls -l /tmp/.ydotool_socket 2>/dev/null || echo '未运行')）"
        echo "   识别结果将只能停留在剪贴板，无法自动粘贴。修复：sudo ./scripts/fix-ydotool-socket.sh"
    fi
fi

# 解析参数
BACKGROUND=false
for arg in "$@"; do
    case $arg in
        --background|-b) BACKGROUND=true ;;
    esac
done

# 锁文件路径（与 process_lock.py 保持一致）
LOCK_FILE="$HOME/.local/share/voice-input/voice-input.lock"

# 单例检查
if [ -f "$LOCK_FILE" ]; then
    EXISTING_PID=$(cat "$LOCK_FILE" 2>/dev/null)
    if [ -n "$EXISTING_PID" ] && kill -0 "$EXISTING_PID" 2>/dev/null; then
        echo "❌ 语音输入已在运行 (PID: $EXISTING_PID)"
        echo "   如需重启，请先运行：kill $EXISTING_PID"
        exit 1
    fi
    rm -f "$LOCK_FILE"
fi

# 构建命令
if [ -x .venv/bin/lb-voice ]; then
    VOICE_CMD=(".venv/bin/lb-voice")
elif [ -x venv/bin/lb-voice ]; then
    VOICE_CMD=("venv/bin/lb-voice")
elif [ -x venv/bin/voice-input ]; then
    VOICE_CMD=("venv/bin/voice-input")
else
    VOICE_CMD=("uv" "run" "lb-voice")
fi

if [ -r /dev/input/event0 ]; then
    CMD=("${VOICE_CMD[@]}")
else
    CMD=("sudo" "-E" "${VOICE_CMD[@]}")
fi

LOG_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/voice-input"
mkdir -p "$LOG_DIR"
chmod 700 "$LOG_DIR"
LOG_FILE="$LOG_DIR/voice-input.log"

# 后台运行
if [ "$BACKGROUND" = true ]; then
    echo "启动语音输入（后台模式）..."
    nohup "${CMD[@]}" > "$LOG_FILE" 2>&1 &
    echo "语音输入已在后台启动，PID: $!"
    echo "日志输出：$LOG_FILE"
else
    exec "${CMD[@]}"
fi
