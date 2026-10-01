# V2.1 常驻监听设计：VAD 分段 + ASR 会话接力

## 目标

把“按键后才开始连接 ASR”的首句延迟去掉：麦克风持续采集，本地 VAD 决定何时
打开/结束识别会话；上一个会话在后台等最终结果时，下一个会话已经处于可接收
音频状态。

## 决策

1. 第一阶段不引入模型级 VAD 依赖，使用 `EnergyVAD`：
   - 80ms 帧能量 + RMS 阈值；
   - 2 帧确认，避免单次碰撞误触发；
   - `prebuffer_ms=240` 回放确认前的音频，不丢首字；
   - 700ms 静音 hangover，避免词语间短停顿切段；
   - 单段上限 60s，超过后强制接力。
2. `ASRSessionRelay` 负责会话生命周期：
   - `warm()` 后台调用 `prepare_session()` + `start()`；
   - VAD 确认说话时立即 `send_audio()`，连接建立期间的音频进入后端队列；
   - 静音后当前会话移出活动位，后台 `stop()` 等最终结果；
   - 移出后立刻 `warm()` 下一个会话，形成接力。
3. V2.1 只落地纯 Python 策略层，默认关闭。等真机确认阈值和分段节奏后，
   再在 `main.py` 中接入 `resident.enabled` 配置并做系统服务回归。

## 数据流

```
PortAudio 持续流 → EnergyVAD.feed()
  ├─ speech start: ASRSessionRelay.warm() 后已经 ready → send_audio(prebuffer)
  ├─ speech: send_audio(pcm) → 后端 partial → VoiceIMClient.send_partial()
  └─ silence end: ASRSessionRelay.finish_segment()
        ├─ 后台: session.stop() → final text → commit/回退
        └─ 立即: warm() → 下一句低延迟
```

## 验证标准

1. 单测：VAD 不丢首帧、静音分段、最短语音过滤；
2. 单测：会话接力期间发送的音频不丢失；
3. 真机：连续两句话，第二句的 `音频批次 T+` 首包相对第一句无额外 WS 建连等待；
4. 隐私：未确认启用前默认 `resident.enabled=false`；正式接入时文档必须
   说明常驻麦克风语义。
