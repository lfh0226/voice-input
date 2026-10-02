#!/usr/bin/env python3
"""V2.1 常驻监听真机校准工具.

阶段 1: 采集 3 秒环境噪声 → 建议 speech_rms_threshold
阶段 2: 实时 VAD 回显 → 说两句话(中间停顿 1 秒),验证分段节奏
用法: .venv/bin/python scripts/calibrate-resident.py [--threshold N]
"""

import argparse
import queue
import sys
import time

import numpy as np
import sounddevice as sd

sys.path.insert(0, "src")
from voice_input.vad import EnergyVAD, VADConfig  # noqa: E402

RATE = 16000
FRAME_MS = 80
FRAME_BYTES = RATE * 2 * FRAME_MS // 1000  # 16bit mono


def rms(pcm: bytes) -> float:
    if len(pcm) < 2:
        return 0.0
    arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(arr**2)))


def collect(q: queue.Queue, seconds: float, label: str) -> list[float]:
    vals: list[float] = []
    end = time.time() + seconds
    print(f"\n🎤 {label}({seconds:.0f} 秒)...")
    while time.time() < end:
        try:
            pcm = q.get(timeout=0.5)
        except queue.Empty:
            continue
        vals.append(rms(pcm))
    arr = np.array(vals)
    print(f"   RMS: min={arr.min():.0f} 中位={np.median(arr):.0f} max={arr.max():.0f}")
    return vals


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0, help="跳过建议,直接用该阈值测试")
    args = ap.parse_args()

    q: queue.Queue = queue.Queue()

    def on_audio(pcm, _frames, _time, _status):
        q.put(bytes(pcm))

    print("打开麦克风...")
    stream = sd.InputStream(samplerate=RATE, channels=1, dtype="int16",
                            blocksize=FRAME_BYTES, callback=on_audio)
    stream.start()
    time.sleep(0.5)

    # 阶段 1: 环境噪声
    ambient = collect(q, 3.0, "请保持安静,采集环境噪声")
    ambient_p95 = float(np.percentile(ambient, 95))
    suggested = max(300.0, round(ambient_p95 * 3 / 50) * 50)
    print(f"\n✅ 建议 speech_rms_threshold = {suggested:.0f}(环境 P95={ambient_p95:.0f} × 3)")

    threshold = args.threshold if args.threshold > 0 else suggested

    # 阶段 2: 实时 VAD 回显
    print(f"\n🎤 阶段 2: 用阈值 {threshold:.0f} 做实时 VAD 测试")
    print("   请说两句话,中间停顿约 1 秒。Ctrl+C 退出。")
    cfg = VADConfig(speech_rms_threshold=threshold, frame_ms=FRAME_MS)
    vad = EnergyVAD(cfg)
    events: list[tuple[str, float]] = []
    t0 = time.time()
    try:
        while time.time() - t0 < 20:
            try:
                pcm = q.get(timeout=0.5)
            except queue.Empty:
                continue
            was_speaking = vad.is_speaking
            vad.feed(pcm)
            now = time.time() - t0
            if not was_speaking and vad.is_speaking:
                events.append(("speech_start", now))
                print(f"   T+{now:.2f}s 🗣️  检测到说话开始")
            elif was_speaking and not vad.is_speaking:
                events.append(("speech_end", now))
                print(f"   T+{now:.2f}s ✅ 分段结束(含 700ms 静音回滞)")
    except KeyboardInterrupt:
        pass

    starts = [t for k, t in events if k == "speech_start"]
    ends = [t for k, t in events if k == "speech_end"]
    print("\n📋 校准总结")
    print(f"   建议 speech_rms_threshold: {threshold:.0f}")
    print(f"   检测到说话段: {len(ends)} 个")
    if len(starts) >= 1 and len(ends) >= 1:
        first_latency = ends[0] - starts[0] if starts else 0
        print(f"   首段检测延迟: {first_latency:.2f}s(说话开始→分段结束)")
    print("\n下一步: 将 threshold 写入 config.yaml resident.speech_rms_threshold,")
    print("resident.enabled=true,重启 voice-input.service 后即可验收常驻监听。")
    stream.stop(); stream.close()


if __name__ == "__main__":
    main()
