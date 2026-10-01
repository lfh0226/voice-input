# 架构文档

## 组件图

```
┌─ voice-input daemon(Python, systemd 用户服务)──────────────┐
│ evdev 热键(Alt_R) → StreamingRecorder(80ms 块)              │
│   → ASR 后端适配层(xunfei / funasr / …可插拔)                │
│   → 讯飞流式 WS(dwa=wpgs 语境纠错)                          │
│   → VoiceIMClient(Unix socket IPC)                          │
│   → 失败自动回退:wl-clipboard + ydotool 粘贴                │
└──────────────┬───────────────────────────────────────────────┘
               │ /run/user/$UID/voice-input/im.sock
               │ 行分隔 JSON(ready 握手 → partial/final → ack)
┌──────────────▼───────────────────────────────────────────────┐
│ fcitx5 voiceim 插件(C++,常驻 fcitx5 进程)                    │
│ partial → clientPreedit(流式灰字)                            │
│ final → commitString(光标处正式上屏)                          │
│ 焦点未就绪 → pendingFinal_ 定时重试(100ms×30)自动补上屏        │
└──────────────────────────────────────────────────────────────┘
```

## IPC 协议(v1)

- 传输:Unix 流式套接字,`$XDG_RUNTIME_DIR/voice-input/im.sock`
- 握手:插件 accept 后发送 `{"type":"ready"}`;客户端收到 ready 后才允许发数据
  (fcitx5 事件循环为边缘触发,ready 握手保证不丢首条消息)
- 消息:行分隔 JSON,UTF-8,字段 `type` + `text`
  - 客户端 → 插件:`{"type":"partial","text":"…"}` / `{"type":"final","text":"…"}`
    / `{"type":"ping"}`
  - 插件 → 客户端:`{"type":"pong"}` / `{"type":"ack","committed":true|false}`
- 焦点未就绪时,插件暂存 final 并以 100ms 间隔重试 commit(上限 3 秒),
  期间不发 ack;超时发 `committed:false`,客户端转剪贴板回退

## Python / C++ 分工原则

| 层 | 语言 | 职责 | 迭代频率 |
|---|---|---|---|
| fcitx5 插件 | C++ | 预编辑渲染与文字提交(必须在 fcitx5 进程内才有效) | 极低,协议稳定后基本不动 |
| daemon | Python | 热键/录音/ASR/纠错/分段策略/回退 | 高,所有迭代在此 |

边界即 IPC 协议。换 ASR 厂商、换模型、换纠错策略都只改 Python 层。

## 回退链

```
fcitx5 插件 commit(最优) → 剪贴板+ydotool 粘贴 → 剪贴板留存(人工粘贴)
```
每级失败自动降到下一级,识别内容永不丢失。

