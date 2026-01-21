"""
Rsync 同步引擎

功能:
- 构建 rsync 命令
- 异步执行同步
- 失败重试
- 多远程目标支持
"""

import asyncio
import subprocess
from pathlib import Path
from typing import List, Optional
import structlog

from sersync.config.models import RsyncConfig, RemoteConfig, FailLogConfig

logger = structlog.get_logger()


class SyncEngine:
    """Rsync 同步引擎"""

    def __init__(
        self,
        config: RsyncConfig,
        remotes: List[RemoteConfig],
        watch_path: str,
        fail_log: FailLogConfig
    ):
        """
        初始化同步引擎

        Args:
            config: Rsync 配置
            remotes: 远程目标列表
            watch_path: 监控路径
            fail_log: 失败日志配置
        """
        self.config = config
        self.remotes = remotes
        self.watch_path = Path(watch_path)
        self.fail_log = fail_log

        self.stats = {
            'total_syncs': 0,
            'success_syncs': 0,
            'failed_syncs': 0,
            'bytes_transferred': 0,
        }

        logger.info(
            "Sync engine initialized",
            watch_path=str(self.watch_path),
            remotes=len(self.remotes)
        )

    async def sync_file(self, file_path: str, event_type: str) -> dict:
        """
        同步单个文件到所有远程目标

        Args:
            file_path: 文件路径
            event_type: 事件类型

        Returns:
            同步结果字典
        """
        results = []

        for remote in self.remotes:
            result = await self._rsync_to_remote(file_path, remote, event_type)
            results.append({
                'remote': f"{remote.ip}::{remote.name}",
                'success': result['success'],
                'output': result.get('output', ''),
                'error': result.get('error', ''),
            })

            # 记录失败
            if not result['success']:
                await self._log_failure(file_path, remote, event_type)

        # 更新统计
        self.stats['total_syncs'] += len(self.remotes)
        self.stats['success_syncs'] += sum(1 for r in results if r['success'])
        self.stats['failed_syncs'] += sum(1 for r in results if not r['success'])

        return {
            'file_path': file_path,
            'event_type': event_type,
            'results': results,
            'all_success': all(r['success'] for r in results)
        }

    async def sync_full_directory(
        self,
        filters: Optional[List[str]] = None
    ) -> dict:
        """
        全量同步整个监控目录

        Args:
            filters: 过滤规则列表（可选）

        Returns:
            同步结果
        """
        logger.info("Starting full directory sync", path=str(self.watch_path))

        results = []
        for remote in self.remotes:
            result = await self._rsync_full_dir(remote, filters)
            results.append({
                'remote': f"{remote.ip}::{remote.name}",
                'success': result['success'],
                'output': result.get('output', ''),
            })

        success_count = sum(1 for r in results if r['success'])

        logger.info(
            "Full directory sync completed",
            total_remotes=len(self.remotes),
            success=success_count
        )

        return {
            'type': 'full_sync',
            'results': results,
            'all_success': all(r['success'] for r in results)
        }

    async def _rsync_to_remote(
        self,
        source: str,
        remote: RemoteConfig,
        event_type: str
    ) -> dict:
        """
        执行 rsync 命令到指定远程目标

        Args:
            source: 源文件路径
            remote: 远程目标配置
            event_type: 事件类型

        Returns:
            执行结果
        """
        # 对于删除事件，检查源文件/目录是否仍然存在
        if event_type.startswith('DELETE'):
            source_path = Path(source)
            if not source_path.exists():
                # 文件/目录已经不存在，这是正常的删除情况
                # 我们仍然需要同步删除到远程，但需要特殊处理
                logger.debug(
                    "Source already deleted, proceeding with remote deletion",
                    source=source,
                    remote=f"{remote.ip}::{remote.name}",
                    event_type=event_type
                )
                
                # 对于已删除的文件/目录，使用父目录作为rsync的工作目录
                parent_dir = source_path.parent
                if not parent_dir.exists():
                    # 如果父目录也不存在，说明整个目录树被删除了
                    logger.warning(
                        "Parent directory also deleted, skipping sync",
                        source=source,
                        parent=str(parent_dir),
                        remote=f"{remote.ip}::{remote.name}"
                    )
                    return {
                        'success': True,  # 认为这是成功的，因为目标已经达到（文件被删除）
                        'returncode': 0,
                        'output': 'Source already deleted, sync skipped',
                        'error': '',
                    }

        cmd = self._build_rsync_cmd(source, remote, event_type)

        logger.debug(
            "Executing rsync",
            source=source,
            remote=f"{remote.ip}::{remote.name}",
            event_type=event_type
        )

        try:
            # 尝试创建子进程，处理 Python 3.12 的兼容性问题
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            except NotImplementedError:
                # Python 3.12 在某些情况下可能抛出 NotImplementedError
                # 回退到使用 subprocess.Popen 的同步方式
                logger.debug("Falling back to synchronous subprocess execution")
                import subprocess
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                stdout, stderr = process.communicate()
                
                # 模拟 asyncio 子进程的接口
                class ProcessWrapper:
                    def __init__(self, popen_process, stdout, stderr):
                        self.returncode = popen_process.returncode
                        self._stdout = stdout
                        self._stderr = stderr
                    
                    async def communicate(self):
                        return self._stdout, self._stderr
                
                process = ProcessWrapper(process, stdout, stderr)
                stdout, stderr = await process.communicate()
            else:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.config.timeout if self.config.timeout_enabled else None
                )

            success = process.returncode == 0
            stderr_text = stderr.decode('utf-8', errors='ignore')

            # 对于删除操作，如果rsync报告"No such file or directory"，
            # 但返回码是23，这通常意味着文件已经被删除，可以认为是成功的
            if not success and event_type.startswith('DELETE') and process.returncode == 23:
                if "No such file or directory" in stderr_text:
                    logger.debug(
                        "Rsync reported file not found for delete operation, treating as success",
                        source=source,
                        remote=f"{remote.ip}::{remote.name}"
                    )
                    success = True

            if success:
                logger.debug(
                    "Rsync completed successfully",
                    source=source,
                    remote=f"{remote.ip}::{remote.name}"
                )
            else:
                logger.warning(
                    "Rsync failed",
                    source=source,
                    remote=f"{remote.ip}::{remote.name}",
                    returncode=process.returncode,
                    stderr=stderr_text[:500]
                )

            return {
                'success': success,
                'returncode': process.returncode,
                'output': stdout.decode('utf-8', errors='ignore'),
                'error': stderr_text,
            }

        except asyncio.TimeoutError:
            logger.error("Rsync timeout", source=source, remote=f"{remote.ip}::{remote.name}")
            return {
                'success': False,
                'error': 'Timeout'
            }
        except Exception as e:
            logger.error(
                "Rsync exception",
                source=source,
                remote=f"{remote.ip}::{remote.name}",
                error=str(e),
                exc_info=True
            )
            return {
                'success': False,
                'error': str(e)
            }

    def _build_rsync_cmd(
        self,
        source: str,
        remote: RemoteConfig,
        event_type: str
    ) -> List[str]:
        """
        构建 rsync 命令

        Args:
            source: 源文件路径
            remote: 远程目标
            event_type: 事件类型

        Returns:
            命令列表
        """
        cmd = ['rsync']

        # 通用参数
        cmd.extend(self.config.common_params.split())

        # 删除事件
        if event_type.startswith('DELETE'):
            cmd.append('--delete')
            # 对于删除操作，如果源文件不存在，使用父目录进行同步
            source_path = Path(source)
            if not source_path.exists():
                # 使用父目录作为源，这样rsync可以正确处理删除
                parent_dir = source_path.parent
                if parent_dir.exists():
                    source = str(parent_dir) + '/'  # 添加尾部斜杠表示目录内容
                    logger.debug(
                        "Using parent directory for delete sync",
                        original_source=str(source_path),
                        parent_source=source
                    )

        # 认证
        if self.config.auth_enabled and self.config.auth_passwordfile:
            cmd.append(f'--password-file={self.config.auth_passwordfile}')

        # 超时
        if self.config.timeout_enabled:
            cmd.append(f'--timeout={self.config.timeout}')

        # 端口
        if self.config.custom_port_enabled:
            cmd.append(f'--port={self.config.custom_port}')

        # 构建目标路径
        if self.config.ssh_enabled:
            # SSH 模式
            cmd.extend(['-e', 'ssh'])
            # 计算相对路径
            try:
                relative_path = Path(source).relative_to(self.watch_path)
            except ValueError:
                relative_path = Path(source).name

            dest = f'{remote.ip}:{remote.name}/{relative_path}'
        else:
            # Rsync daemon 模式
            user_prefix = f'{self.config.auth_users}@' if self.config.auth_users else ''
            try:
                relative_path = Path(source).relative_to(self.watch_path)
            except ValueError:
                relative_path = Path(source).name

            dest = f'{user_prefix}{remote.ip}::{remote.name}/{relative_path}'

        cmd.extend([source, dest])

        return cmd

    async def _rsync_full_dir(
        self,
        remote: RemoteConfig,
        filters: Optional[List[str]] = None
    ) -> dict:
        """
        全量同步目录

        Args:
            remote: 远程目标
            filters: 过滤规则

        Returns:
            执行结果
        """
        cmd = ['rsync']

        # 通用参数
        cmd.extend(self.config.common_params.split())

        # 删除不存在的文件
        cmd.append('--delete')

        # 认证
        if self.config.auth_enabled and self.config.auth_passwordfile:
            cmd.append(f'--password-file={self.config.auth_passwordfile}')

        # 过滤规则
        if filters:
            for pattern in filters:
                cmd.append(f'--exclude={pattern}')

        # 端口
        if self.config.custom_port_enabled:
            cmd.append(f'--port={self.config.custom_port}')

        # 源和目标
        source = str(self.watch_path) + '/'  # 尾部斜杠很重要
        if self.config.ssh_enabled:
            cmd.extend(['-e', 'ssh'])
            dest = f'{remote.ip}:{remote.name}/'
        else:
            user_prefix = f'{self.config.auth_users}@' if self.config.auth_users else ''
            dest = f'{user_prefix}{remote.ip}::{remote.name}/'

        cmd.extend([source, dest])

        logger.info("Executing full directory sync", remote=f"{remote.ip}::{remote.name}")

        try:
            # 尝试创建子进程，处理 Python 3.12 的兼容性问题
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
            except NotImplementedError:
                # Python 3.12 在某些情况下可能抛出 NotImplementedError
                # 回退到使用 subprocess.Popen 的同步方式
                logger.debug("Falling back to synchronous subprocess execution for full sync")
                import subprocess
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                stdout, stderr = process.communicate()

            success = process.returncode == 0

            return {
                'success': success,
                'returncode': process.returncode,
                'output': stdout.decode('utf-8', errors='ignore'),
                'error': stderr.decode('utf-8', errors='ignore'),
            }

        except Exception as e:
            logger.error("Full sync exception", remote=f"{remote.ip}::{remote.name}", error=str(e))
            return {
                'success': False,
                'error': str(e)
            }

    async def _log_failure(
        self,
        file_path: str,
        remote: RemoteConfig,
        event_type: str
    ):
        """
        记录失败日志到 failLog 文件

        Args:
            file_path: 文件路径
            remote: 远程目标
            event_type: 事件类型
        """
        try:
            cmd = self._build_rsync_cmd(file_path, remote, event_type)
            cmd_str = ' '.join(cmd)

            # 追加到失败日志文件
            fail_log_path = Path(self.fail_log.path)
            fail_log_path.parent.mkdir(parents=True, exist_ok=True)

            # 确保文件有正确的 shebang 和可执行权限
            if not fail_log_path.exists():
                fail_log_path.write_text('#!/bin/bash\n# FailLog retry script - generated by sersync\nRETRY_COUNT=0\nFAILED_COUNT=0\n\n')
                fail_log_path.chmod(0o755)
            else:
                # 检查是否有 shebang，如果没有则添加
                content = fail_log_path.read_text()
                if not content.startswith('#!/bin/bash'):
                    fail_log_path.write_text('#!/bin/bash\n# FailLog retry script - generated by sersync\nRETRY_COUNT=0\nFAILED_COUNT=0\n\n' + content)
                elif 'RETRY_COUNT=0' not in content:
                    # 如果已有shebang但没有变量初始化，添加变量
                    lines = content.split('\n')
                    lines.insert(2, '# FailLog retry script - generated by sersync')
                    lines.insert(3, 'RETRY_COUNT=0')
                    lines.insert(4, 'FAILED_COUNT=0')
                    lines.insert(5, '')
                    fail_log_path.write_text('\n'.join(lines))

            # 添加时间戳和注释
            import datetime
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 改进的失败命令记录，支持多个命令的批量重试
            with open(fail_log_path, 'a') as f:
                f.write(f"# Failed at {timestamp} - {event_type} {file_path} -> {remote.ip}::{remote.name}\n")
                f.write(f"echo 'Retrying: {cmd_str}'\n")
                f.write(f"{cmd_str}\n")
                f.write(f"RETRY_RESULT=$?\n")
                f.write(f"if [ $RETRY_RESULT -eq 0 ]; then\n")
                f.write(f"    echo 'SUCCESS: {cmd_str}'\n")
                f.write(f"else\n")
                f.write(f"    echo 'FAILED: {cmd_str} (exit code: '$RETRY_RESULT')'\n")
                f.write(f"    FAILED_COUNT=$((FAILED_COUNT + 1))\n")
                f.write(f"fi\n")
                f.write(f"RETRY_COUNT=$((RETRY_COUNT + 1))\n")
                f.write(f"\n")

            logger.info(
                "Failure logged to retry script", 
                file=file_path, 
                remote=f"{remote.ip}::{remote.name}",
                script=str(fail_log_path)
            )

        except Exception as e:
            logger.error("Failed to write failure log", error=str(e))

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            **self.stats,
            'success_rate': (
                self.stats['success_syncs'] / self.stats['total_syncs'] * 100
                if self.stats['total_syncs'] > 0 else 0
            )
        }
