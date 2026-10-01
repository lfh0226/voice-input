#!/bin/bash
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/fcitx5-addon"
cmake -S "$DIR" -B "$DIR/build" -DCMAKE_BUILD_TYPE=Release
cmake --build "$DIR/build" -j"$(nproc)"
echo "✅ 构建完成: $DIR/build/voiceim.so"

