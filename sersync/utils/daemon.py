"""
守护进程模块
"""

import sys
import os
import atexit
from pathlib import Path
import structlog

logger = structlog.get_logger()


def daemonize(
    pidfile: str = '/var/run/sersync.pid',
    stdin: str = '/dev/null',
    stdout: str = '/var/log/sersync.log',
    stderr: str = '/var/log/sersync.log',
):
    """
    将进程转换为守护进程

    Args:
        pidfile: PID 文件路径
        stdin: 标准输入重定向路径
        stdout: 标准输出重定向路径
        stderr: 标准错误重定向路径
    """
    # 检查是否已经是守护进程
    if os.getppid() == 1:
        logger.info("Already running as daemon")
        return

    try:
        # 第一次 fork
        pid = os.fork()
        if pid > 0:
            # 父进程退出
            sys.exit(0)
    except OSError as e:
        logger.error("First fork failed", error=str(e))
        sys.exit(1)

    # 脱离终端
    os.chdir('/')
    os.setsid()
    os.umask(0)

    try:
        # 第二次 fork
        pid = os.fork()
        if pid > 0:
            # 第一个子进程退出
            sys.exit(0)
    except OSError as e:
        logger.error("Second fork failed", error=str(e))
        sys.exit(1)

    # 重定向标准文件描述符
    sys.stdout.flush()
    sys.stderr.flush()

    si = open(stdin, 'r')
    so = open(stdout, 'a+')
    se = open(stderr, 'a+')

    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())

    # 写入 PID 文件
    pid = str(os.getpid())
    pidfile_path = Path(pidfile)
    pidfile_path.parent.mkdir(parents=True, exist_ok=True)

    with open(pidfile, 'w+') as f:
        f.write(f"{pid}\n")

    # 注册退出时删除 PID 文件
    atexit.register(lambda: _remove_pidfile(pidfile))

    logger.info("Daemon started", pid=pid, pidfile=pidfile)


def _remove_pidfile(pidfile: str):
    """删除 PID 文件"""
    try:
        if os.path.exists(pidfile):
            os.remove(pidfile)
    except Exception as e:
        logger.error("Failed to remove pidfile", pidfile=pidfile, error=str(e))
