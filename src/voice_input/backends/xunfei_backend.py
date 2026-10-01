"""讯飞流式听写后端(dwa=wpgs 语境动态纠错)。"""

from typing import Callable

from voice_input.recognizer.xunfei import XunfeiStreamer


class XunfeiBackend:
    name = "xunfei"

    def create_streamer(self, config, on_result: Callable[[str, bool], None]):
        x = config.xunfei
        return XunfeiStreamer(
            app_id=x.get("app_id", ""),
            api_key=x.get("api_key", ""),
            api_secret=x.get("api_secret", ""),
            language=x.get("language", "zh_cn"),
            accent=x.get("accent", "mandarin"),
            on_result=on_result,
            vad_eos=x.get("vad_eos", 5000),
            max_audio_queue_size=x.get("max_audio_queue_size", 400),
            batch_chunks=x.get("batch_chunks", 2),
        )

