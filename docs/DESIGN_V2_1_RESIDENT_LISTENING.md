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
3. V2.1 已在 `main.py` 接入 `resident.enabled`。配置默认关闭；启用后 daemon
   持续采集麦克风、跳过 Alt_R 热键模式，并由 VAD/接力层驱动会话。真机仍需
   校准阈值和分段节奏后再建议用户开启。

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

## 当前实现边界

- 启用常驻监听时日志会明确提示“麦克风持续采集”，关闭方式是
  `resident.enabled=false` 后重启 daemon。
- 常驻模式独占录音器并停用热键监听，避免两个控制路径同时 start/stop。
- final 仅通过 fcitx5 插件 commit；没有按键手势上下文时不会盲目执行
  剪贴板粘贴回退。
