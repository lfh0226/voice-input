#!/usr/bin/env python3
"""测试 WebSocket 连接复用优化"""

import time
from src.voice_input.config import Config
from src.voice_input.recognizer.xunfei import XunfeiStreamer

def test_connection_reuse():
    """测试连接复用性能"""
    config = Config()
    
    print("=" * 60)
    print("测试 WebSocket 连接复用优化")
    print("=" * 60)
    
    # 创建识别器
    print("\n1. 创建识别器并建立初始连接...")
    start_time = time.time()
    
    streamer = XunfeiStreamer(
        app_id=config.xunfei.get("app_id", ""),
        api_key=config.xunfei.get("api_key", ""),
        api_secret=config.xunfei.get("api_secret", ""),
        language=config.xunfei.get("language", "zh_cn"),
        accent=config.xunfei.get("accent", "mandarin"),
        on_result=lambda text, is_final: print(f"   识别: {text}"),
    )
    
    if not streamer.start():
        print("❌ 连接失败")
        return
    
    connect_time = time.time() - start_time
    print(f"   ✓ 初始连接耗时: {connect_time:.3f}秒")
    
    # 停止但保持连接
    streamer.stop(close_connection=False)
    time.sleep(0.5)
    
    # 测试复用连接
    print("\n2. 测试连接复用（模拟 5 次录音）...")
    reuse_times = []
    
    for i in range(5):
        print(f"\n   第 {i+1} 次录音:")
        
        start_time = time.time()
        
        # 复用连接启动
        if not streamer.start():
            print(f"   ❌ 第 {i+1} 次启动失败")
            continue
        
        reuse_time = time.time() - start_time
        reuse_times.append(reuse_time)
        
        # 模拟短暂录音
        time.sleep(0.5)
        
        # 停止但保持连接
        streamer.stop(close_connection=False)
        
        print(f"   ✓ 启动耗时: {reuse_time:.3f}秒")
        
        time.sleep(0.3)
    
    # 清理
    print("\n3. 清理资源...")
    streamer.cleanup()
    
    # 统计
    print("\n" + "=" * 60)
    print("性能统计:")
    print("=" * 60)
    print(f"初始连接耗时: {connect_time:.3f}秒")
    print(f"平均复用耗时: {sum(reuse_times)/len(reuse_times):.3f}秒")
    print(f"\n✅ 连接复用减少了 {((connect_time - sum(reuse_times)/len(reuse_times)) / connect_time * 100):.1f}% 的启动时间")
    print("=" * 60)

if __name__ == "__main__":
    try:
        test_connection_reuse()
    except KeyboardInterrupt:
        print("\n\n测试中断")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
