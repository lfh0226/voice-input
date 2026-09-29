#!/bin/bash
# 修复 ydotool 粘贴权限。
#
# 背景：Ubuntu 的 ydotoold 以 root 运行，套接字固定为 /tmp/.ydotool_socket，
# 默认权限 600 root:root；普通用户调用 `ydotool key` 会报
# "ydotoold backend unavailable" / "failed to open uinput device"，
# 于是语音输入只能把文字放进剪贴板，无法自动 Ctrl+V 粘贴。
#
# 本脚本通过 systemd drop-in 在 ydotoold 启动后，把套接字属主改为当前用户
# （权限 600，不对其他用户开放），并立即生效。

set -euo pipefail

TARGET_USER="${SUDO_USER:-$(id -un)}"
SOCKET="/tmp/.ydotool_socket"
HELPER="/usr/local/lib/voice-input/ydotool-socket-owner"
DROPIN_DIR="/etc/systemd/system/ydotoold.service.d"

echo "🔧 修复 ydotoold 套接字权限（授权给用户: $TARGET_USER）..."

if ! systemctl cat ydotoold.service >/dev/null 2>&1; then
    echo "❌ 未找到 ydotoold.service"
    echo "   请先启动 ydotoold 守护进程，例如："
    echo "   sudo tee /etc/systemd/system/ydotoold.service >/dev/null <<'EOF'"
    echo "   [Unit]"
    echo "   Description=ydotoold daemon"
    echo "   After=multi-user.target"
    echo "   [Service]"
    echo "   Type=simple"
    echo "   ExecStart=/usr/bin/ydotoold"
    echo "   Restart=always"
    echo "   [Install]"
    echo "   WantedBy=multi-user.target"
    echo "   EOF"
    echo "   sudo systemctl enable --now ydotoold"
    exit 1
fi

# 1. 辅助脚本：等待套接字出现后修改属主（放在文件里，避免 systemd 展开 $ 变量）
sudo install -D -m 0755 /dev/stdin "$HELPER" <<'EOF'
#!/bin/sh
# 把 /tmp/.ydotool_socket 的属主改为指定用户，使该用户调用 ydotool 时可用。
set -u

user="${1:-}"
[ -n "$user" ] || exit 0

i=0
while [ "$i" -lt 50 ]; do
    if [ -S /tmp/.ydotool_socket ]; then
        chown "$user:$user" /tmp/.ydotool_socket 2>/dev/null || true
        chmod 600 /tmp/.ydotool_socket 2>/dev/null || true
        exit 0
    fi
    i=$((i + 1))
    sleep 0.1
done
exit 0
EOF

# 2. systemd drop-in：每次 ydotoold 启动后修正套接字属主
sudo mkdir -p "$DROPIN_DIR"
printf '[Service]\nExecStartPost=%s %s\n' "$HELPER" "$TARGET_USER" |
    sudo tee "$DROPIN_DIR/10-socket-owner.conf" >/dev/null

sudo systemctl daemon-reload
sudo systemctl restart ydotoold

# 3. 立即修正当前套接字并校验
if [ -S "$SOCKET" ]; then
    sudo chown "$TARGET_USER:$TARGET_USER" "$SOCKET"
    sudo chmod 600 "$SOCKET"
fi

echo
echo "套接字状态："
ls -l "$SOCKET" || true
echo

if RESULT=$(sudo -u "$TARGET_USER" ydotool key 0:0 2>&1); then
    echo "✅ 完成：用户 $TARGET_USER 已可调用 ydotool（语音输入将能自动 Ctrl+V 粘贴）"
else
    echo "⚠️  套接字权限已修正，但 ydotool 仍报错：$RESULT"
    echo "   请检查 /dev/uinput 是否存在以及 ydotoold 是否正常运行"
    exit 1
fi
