"""进程锁模块 - 确保单实例运行"""

import fcntl
import os
from pathlib import Path


class ProcessLock:
    """进程锁，确保只有一个实例运行"""

    def __init__(self, lock_file: str = None):
        """初始化进程锁

        Args:
            lock_file: 锁文件路径，默认使用用户目录
        """
        if lock_file is None:
            # 优先使用用户运行时目录
            runtime_dir = os.getenv("XDG_RUNTIME_DIR")
            if runtime_dir:
                lock_file = Path(runtime_dir) / "voice-input.lock"
            else:
                # 降级到用户目录
                lock_file = Path.home() / ".local" / "share" / "voice-input" / "voice-input.lock"

        self.lock_file = Path(lock_file)
        self.lock_fd = None

    def acquire(self) -> bool:
        """获取锁

        Returns:
            True 如果成功获取锁，False 如果已有实例运行
        """
        try:
            self.lock_file.parent.mkdir(parents=True, exist_ok=True)
            self.lock_fd = open(self.lock_file, "w")
            fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lock_fd.write(str(os.getpid()))
            self.lock_fd.flush()
            return True
        except (IOError, OSError):
            if self.lock_fd:
                self.lock_fd.close()
                self.lock_fd = None
            return False

    def release(self):
        """释放锁"""
        if self.lock_fd:
            try:
                fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_UN)
                self.lock_fd.close()
                if self.lock_file.exists():
                    self.lock_file.unlink()
            except Exception:
                pass
            self.lock_fd = None

    def get_existing_pid(self) -> int | None:
        """获取已运行实例的 PID

        Returns:
            PID 如果有实例运行，None 如果没有
        """
        if not self.lock_file.exists():
            return None
        try:
            with open(self.lock_file, "r") as f:
                pid = int(f.read().strip())
            # 检查进程是否存在
            os.kill(pid, 0)
            return pid
        except (ProcessLookupError, ValueError, FileNotFoundError, PermissionError):
            # 进程不存在或无权限，清理锁文件
            try:
                if self.lock_file.exists():
                    self.lock_file.unlink()
            except Exception:
                pass
            return None
