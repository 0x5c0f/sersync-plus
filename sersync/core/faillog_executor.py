"""
FailLog 执行器 - 独立监控和执行失败重试脚本

功能:
- 独立线程监控 failLog 脚本文件
- 按照 timeToExecute 配置定期执行脚本
- 简单的成功/失败处理和脚本清理
- 与生成器完全解耦，互不干扰
"""

import asyncio
import subprocess
from pathlib import Path
from typing import Optional
import structlog

from sersync.config.models import FailLogConfig

logger = structlog.get_logger()


class FailLogExecutor:
    """FailLog 执行器 - 独立监控和执行失败重试脚本"""

    def __init__(self, config: FailLogConfig):
        """
        初始化执行器

        Args:
            config: FailLog 配置
        """
        self.config = config
        self.script_path = Path(config.path)
        self.retry_interval = config.time_to_execute  # timeToExecute 已经是秒
        self._running = False
        self._task: Optional[asyncio.Task] = None

        logger.info(
            "FailLog executor initialized",
            script_path=str(self.script_path),
            interval_seconds=config.time_to_execute
        )

    async def start(self):
        """启动执行器"""
        if self._running:
            logger.warning("FailLog executor already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        
        logger.info(
            "FailLog executor started",
            interval_seconds=self.retry_interval
        )

    async def stop(self):
        """停止执行器"""
        if not self._running:
            return

        logger.info("Stopping FailLog executor")
        self._running = False

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("FailLog executor stopped")

    async def _monitor_loop(self):
        """监控循环 - 定期检查和执行脚本"""
        logger.info(
            "FailLog monitor loop started",
            script_path=str(self.script_path),
            check_interval=self.retry_interval
        )

        while self._running:
            try:
                # 等待指定的重试间隔
                await asyncio.sleep(self.retry_interval)

                if not self._running:
                    break

                # 检查并执行脚本
                await self._check_and_execute()

            except asyncio.CancelledError:
                logger.info("FailLog monitor loop cancelled")
                break
            except Exception as e:
                logger.error(
                    "FailLog monitor loop error",
                    error=str(e),
                    exc_info=True
                )
                # 继续运行，不因单次错误而停止

        logger.info("FailLog monitor loop stopped")

    async def _check_and_execute(self):
        """检查脚本文件并执行"""
        try:
            # 检查脚本文件是否存在
            if not self.script_path.exists():
                logger.debug(
                    "FailLog script does not exist",
                    path=str(self.script_path)
                )
                return

            # 检查脚本文件大小
            file_size = self.script_path.stat().st_size
            if file_size <= 12:  # 只有 "#!/bin/bash\n" 的大小
                logger.debug(
                    "FailLog script is empty",
                    path=str(self.script_path),
                    size=file_size
                )
                return

            # 检查脚本是否有实际的 rsync 命令
            content = self.script_path.read_text()
            if not self._has_rsync_commands(content):
                logger.debug(
                    "FailLog script has no rsync commands",
                    path=str(self.script_path)
                )
                return

            logger.info(
                "Executing FailLog script",
                path=str(self.script_path),
                size=file_size
            )

            # 在执行前添加结果检查逻辑
            self._add_result_check_to_script()

            # 执行脚本
            success = await self._execute_script()

            if success:
                logger.info(
                    "FailLog script executed successfully",
                    path=str(self.script_path)
                )
                # 清空脚本（保留 shebang）
                self._clear_script()
            else:
                logger.warning(
                    "FailLog script execution failed",
                    path=str(self.script_path)
                )
                # 脚本执行失败，进行增量清理
                await self._perform_incremental_cleanup()

        except Exception as e:
            logger.error(
                "Error checking and executing FailLog script",
                path=str(self.script_path),
                error=str(e),
                exc_info=True
            )

    def _has_rsync_commands(self, content: str) -> bool:
        """检查脚本内容是否包含 rsync 命令"""
        lines = content.strip().split('\n')
        for line in lines:
            if line.strip().startswith('rsync '):
                return True
        return False

    async def _execute_script(self) -> bool:
        """
        执行脚本文件

        Returns:
            bool: 执行是否成功
        """
        try:
            # 确保脚本可执行
            self.script_path.chmod(0o755)

            # 执行脚本，处理 Python 3.12 兼容性
            try:
                process = await asyncio.create_subprocess_exec(
                    '/bin/bash',
                    str(self.script_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
            except NotImplementedError:
                # Python 3.12 在某些情况下可能抛出 NotImplementedError
                # 回退到使用 subprocess.Popen 的同步方式
                logger.debug("Falling back to synchronous subprocess execution")
                process = subprocess.Popen(
                    ['/bin/bash', str(self.script_path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                stdout, stderr = process.communicate()

            stdout_text = stdout.decode('utf-8', errors='ignore')
            stderr_text = stderr.decode('utf-8', errors='ignore')

            # 记录执行结果
            if process.returncode == 0:
                logger.info(
                    "FailLog script execution completed",
                    returncode=process.returncode,
                    stdout_preview=stdout_text[:200] if stdout_text else "No output"
                )
                return True
            else:
                logger.warning(
                    "FailLog script execution failed",
                    returncode=process.returncode,
                    stderr_preview=stderr_text[:500] if stderr_text else "No error output",
                    stdout_preview=stdout_text[:200] if stdout_text else "No output"
                )
                return False

        except Exception as e:
            logger.error(
                "Exception during FailLog script execution",
                error=str(e),
                exc_info=True
            )
            return False

    def _clear_script(self):
        """清空脚本文件，只保留 shebang"""
        try:
            self.script_path.write_text('#!/bin/bash\n')
            logger.debug(
                "FailLog script cleared",
                path=str(self.script_path)
            )
        except Exception as e:
            logger.error(
                "Failed to clear FailLog script",
                path=str(self.script_path),
                error=str(e)
            )

    def _add_result_check_to_script(self):
        """在脚本末尾添加结果检查逻辑"""
        try:
            content = self.script_path.read_text()
            
            # 检查是否已经有结果检查逻辑
            if 'echo "=== FailLog Retry Summary ===" ' in content:
                return  # 已经添加过了
            
            # 添加结果检查和汇总逻辑
            result_check = '''
# === FailLog Retry Results ===
echo "=== FailLog Retry Summary ==="
echo "Total retry attempts: $RETRY_COUNT"
echo "Failed attempts: $FAILED_COUNT"
echo "Successful attempts: $((RETRY_COUNT - FAILED_COUNT))"

if [ $FAILED_COUNT -eq 0 ]; then
    echo "All retries successful - clearing failLog"
    exit 0
else
    echo "Some retries failed - will regenerate script with only failed commands"
    exit 1
fi
'''
            
            # 将结果检查添加到脚本末尾
            updated_content = content.rstrip() + result_check
            self.script_path.write_text(updated_content)
            
            logger.debug(
                "Added result check to FailLog script",
                path=str(self.script_path)
            )
            
        except Exception as e:
            logger.error(
                "Failed to add result check to FailLog script",
                path=str(self.script_path),
                error=str(e)
            )

    async def _perform_incremental_cleanup(self):
        """执行增量清理：分析执行输出，只保留失败的命令"""
        try:
            # 重新执行脚本并捕获详细输出来分析结果
            success, output = await self._execute_script_with_analysis()
            
            if success:
                # 所有命令都成功了，清空脚本
                logger.info(
                    "All commands succeeded during analysis, clearing script",
                    path=str(self.script_path)
                )
                self._clear_script()
                return
            
            # 分析输出，找出失败的命令
            failed_commands = self._parse_failed_commands_from_output(output)
            
            if not failed_commands:
                # 没有明确的失败命令，保守起见保留原脚本
                logger.warning(
                    "Could not identify specific failed commands, keeping original script",
                    path=str(self.script_path)
                )
                return
            
            # 重新生成脚本，只包含失败的命令
            new_script_content = self._generate_script_with_commands(failed_commands)
            
            # 写入新脚本
            self.script_path.write_text(new_script_content)
            self.script_path.chmod(0o755)
            
            logger.info(
                "Incremental cleanup completed",
                path=str(self.script_path),
                original_commands=self._count_rsync_commands_in_content(self.script_path.read_text()),
                remaining_commands=len(failed_commands)
            )
            
        except Exception as e:
            logger.error(
                "Failed to perform incremental cleanup",
                path=str(self.script_path),
                error=str(e),
                exc_info=True
            )

    async def _execute_script_with_analysis(self):
        """执行脚本并返回详细输出用于分析"""
        try:
            # 确保脚本可执行
            self.script_path.chmod(0o755)

            # 执行脚本，处理 Python 3.12 兼容性
            try:
                process = await asyncio.create_subprocess_exec(
                    '/bin/bash',
                    str(self.script_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
            except NotImplementedError:
                # Python 3.12 在某些情况下可能抛出 NotImplementedError
                # 回退到使用 subprocess.Popen 的同步方式
                logger.debug("Falling back to synchronous subprocess execution for analysis")
                process = subprocess.Popen(
                    ['/bin/bash', str(self.script_path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                stdout, stderr = process.communicate()

            stdout_text = stdout.decode('utf-8', errors='ignore')
            stderr_text = stderr.decode('utf-8', errors='ignore')
            
            return process.returncode == 0, stdout_text

        except Exception as e:
            logger.error(
                "Exception during script analysis execution",
                error=str(e),
                exc_info=True
            )
            return False, ""

    def _parse_failed_commands_from_output(self, output: str) -> list:
        """从执行输出中解析失败的命令"""
        failed_commands = []
        lines = output.split('\n')
        
        current_retrying_cmd = None
        
        for line in lines:
            line = line.strip()
            
            # 查找 "Retrying: " 行来识别正在重试的命令
            if line.startswith('Retrying: '):
                current_retrying_cmd = line.replace('Retrying: ', '')
            
            # 查找 "FAILED: " 行来确认命令失败
            elif line.startswith('FAILED: ') and current_retrying_cmd:
                # 提取失败的命令
                failed_cmd = current_retrying_cmd
                if failed_cmd not in [cmd['command'] for cmd in failed_commands]:
                    failed_commands.append({
                        'command': failed_cmd,
                        'output_line': line
                    })
                current_retrying_cmd = None
            
            # 查找 "SUCCESS: " 行来重置当前命令
            elif line.startswith('SUCCESS: '):
                current_retrying_cmd = None
        
        return failed_commands

    def _generate_script_with_commands(self, commands: list) -> str:
        """根据命令列表生成新脚本"""
        script_lines = [
            '#!/bin/bash',
            '# FailLog retry script - generated by sersync (incremental cleanup)',
            'RETRY_COUNT=0',
            'FAILED_COUNT=0',
            ''
        ]
        
        for i, cmd_info in enumerate(commands):
            cmd = cmd_info['command']
            script_lines.extend([
                f"# Retry command {i+1} (previously failed)",
                f"echo 'Retrying: {cmd}'",
                cmd,
                'RETRY_RESULT=$?',
                'if [ $RETRY_RESULT -eq 0 ]; then',
                f"    echo 'SUCCESS: {cmd}'",
                'else',
                f"    echo 'FAILED: {cmd} (exit code: '$RETRY_RESULT')'",
                '    FAILED_COUNT=$((FAILED_COUNT + 1))',
                'fi',
                'RETRY_COUNT=$((RETRY_COUNT + 1))',
                ''
            ])
        
        return '\n'.join(script_lines)

    def _count_rsync_commands_in_content(self, content: str) -> int:
        """计算脚本内容中的rsync命令数量"""
        lines = content.split('\n')
        return len([line for line in lines if line.strip().startswith('rsync ') and 'echo' not in line])

    def is_running(self) -> bool:
        """检查执行器是否正在运行"""
        return self._running

    def get_status(self) -> dict:
        """获取执行器状态信息"""
        return {
            'running': self._running,
            'script_path': str(self.script_path),
            'retry_interval_seconds': self.retry_interval,
            'script_exists': self.script_path.exists(),
            'script_size': self.script_path.stat().st_size if self.script_path.exists() else 0
        }