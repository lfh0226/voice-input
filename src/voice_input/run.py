"""Voice Input 启动脚本 - 处理日志和单例"""

import os
import sys


def main():
    """主函数"""
    from voice_input.process_lock import ProcessLock
    from voice_input.logger_config import setup_logger, get_log_file
    from voice_input.main import main as voice_main

    # 单例检查
    lock = ProcessLock()
    existing_pid = lock.get_existing_pid()

    if existing_pid:
        print(f"❌ 语音输入已在运行 (PID: {existing_pid})")
        print(f"   如需重启，请先运行：kill {existing_pid}")
        sys.exit(1)

    if not lock.acquire():
        print("❌ 无法获取进程锁，可能已有实例运行")
        sys.exit(1)

    try:
        # 设置日志
        log_file = get_log_file()
        logger = setup_logger("voice_input", log_file=str(log_file), level="info")

        logger.info("=" * 60)
        logger.info("Voice Input 启动")
        logger.info(f"日志文件：{log_file}")
        logger.info(f"进程 PID: {os.getpid()}")
        logger.info("=" * 60)

        # 运行主程序
        voice_main()

    finally:
        # 释放锁
        lock.release()
        print("\n✅ 语音输入已停止")


if __name__ == "__main__":
    main()
