#!/usr/bin/env python3
"""
日志收集模块

负责收集和管理应用日志，包括:
- 记录应用状态日志
- 捕获崩溃日志
- 管理日志文件生命周期
"""

import json
import asyncio
import aiofiles
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List
# Import will be done locally to avoid circular imports


class CrashLogger:
    """崩溃日志收集器
    
    负责收集应用崩溃日志和状态记录
    """
    
    def __init__(self, config: dict, adb_manager=None):
        """初始化日志收集器
        
        Args:
            config: 配置字典
            adb_manager: ADB管理器实例
        """
        self.config = config
        self.crash_log_dir = Path(config['logging']['crash_log_dir'])
        self.status_log_file = Path(config['logging']['status_log_file'])
        self.adb_manager = adb_manager
        
    def _get_adb_prefix(self) -> str:
        """获取ADB命令前缀
        
        Returns:
            str: ADB命令前缀
        """
        if self.adb_manager:
            return self.adb_manager.get_adb_prefix()
        else:
            return "adb"
        
    async def start(self):
        """启动日志收集器"""
        self.crash_log_dir.mkdir(parents=True, exist_ok=True)
        self.status_log_file.parent.mkdir(parents=True, exist_ok=True)
        print(f"📝 日志收集器启动 - 目录: {self.crash_log_dir}")
        
    async def log_status(self, status):
        """记录应用状态
        
        Args:
            status: 应用状态对象
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        status_line = (
            f"{timestamp} | "
            f"{'✅运行' if status.running else '❌停止'} | "
            f"PID:{status.pid or 'N/A'} | "
            f"运行:{status.uptime}s | "
            f"内存:{status.memory_mb:.1f}MB"
        )
        
        try:
            async with aiofiles.open(self.status_log_file, 'a', encoding='utf-8') as f:
                await f.write(status_line + '\n')
        except Exception as e:
            print(f"❌ 写入状态日志失败: {e}")
        
    async def capture_crash_logs(self, status) -> str:
        """捕获崩溃日志
        
        Args:
            status: 崩溃时的应用状态
            
        Returns:
            str: 崩溃日志文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        crash_file = self.crash_log_dir / f"crash_{timestamp}.log"
        
        print(f"📝 正在捕获崩溃日志: {crash_file.name}")
        
        try:
            # 获取应用相关的logcat日志
            crash_logs = await self._get_crash_logcat()
            
            # 构建崩溃报告
            crash_report = {
                "timestamp": datetime.now().isoformat(),
                "package_name": self.config['app']['package_name'],
                "crash_type": self._detect_crash_type(crash_logs),
                "uptime_before_crash": status.uptime,
                "memory_usage": status.memory_mb,
                "pid": status.pid,
                "logcat_lines": len(crash_logs),
                "crash_logs": crash_logs[-100:] if len(crash_logs) > 100 else crash_logs  # 保留最后100行
            }
            
            # 保存到文件
            await self._write_json_file(crash_file, crash_report)
            
            # 清理旧日志
            await self._cleanup_old_logs()
            
            return str(crash_file)
            
        except Exception as e:
            print(f"❌ 捕获崩溃日志失败: {e}")
            return ""
            
    async def capture_force_stop_event(self, status) -> str:
        """捕获强制停止事件
        
        Args:
            status: 停止时的应用状态
            
        Returns:
            str: 事件日志文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        crash_file = self.crash_log_dir / f"crash_{timestamp}.log"
        
        print(f"📝 记录应用停止事件: {crash_file.name}")
        
        try:
            # 构建停止事件报告
            event_report = {
                "timestamp": datetime.now().isoformat(),
                "package_name": self.config['app']['package_name'],
                "crash_type": "force_stop",
                "uptime_before_stop": status.uptime if hasattr(status, 'uptime') else 0,
                "memory_usage": status.memory_mb if hasattr(status, 'memory_mb') else 0.0,
                "pid": status.pid if hasattr(status, 'pid') else None,
                "description": "应用被强制停止或意外终止"
            }
            
            # 获取应用相关的logcat日志
            app_logs = await self._get_crash_logcat()
            if app_logs:
                event_report["crash_logs"] = app_logs[-100:] if len(app_logs) > 100 else app_logs
                event_report["logcat_lines"] = len(app_logs)
                
            # 获取系统相关日志
            recent_logs = await self._get_recent_system_logs()
            if recent_logs:
                event_report["system_logs"] = recent_logs[-50:]  # 保留最后50行
                
            # 保存到文件
            await self._write_json_file(crash_file, event_report)
            
            # 清理旧日志
            await self._cleanup_old_logs()
            
            return str(crash_file)
            
        except Exception as e:
            print(f"❌ 记录停止事件失败: {e}")
            return ""
            
    async def _get_recent_system_logs(self) -> List[str]:
        """获取最近的系统日志
        
        Returns:
            List[str]: 系统日志行列表
        """
        try:
            # 获取最近2分钟的系统相关日志
            adb_prefix = self._get_adb_prefix()
            cmd = f"{adb_prefix} shell logcat -d -t 120 | grep -E '(ActivityManager|System)'"
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()
            
            if process.returncode == 0:
                return stdout.decode('utf-8', errors='ignore').strip().split('\n')
            else:
                return []
                
        except Exception as e:
            print(f"❌ 获取系统日志失败: {e}")
            return []
        
    async def _get_crash_logcat(self) -> List[str]:
        """获取崩溃相关的logcat日志
        
        Returns:
            List[str]: 日志行列表
        """
        try:
            package_name = self.config['app']['package_name']
            adb_prefix = self._get_adb_prefix()
            all_logs = []
            
            # 优先使用--pid方法获取iSG进程的错误日志
            isg_error_logs = await self._get_isg_error_logs()
            if isg_error_logs:
                all_logs.extend(isg_error_logs)
                print(f"📋 获取到 {len(isg_error_logs)} 行iSG错误日志")
            
            # 方法2: 获取ActivityManager相关日志（应用启动/停止/崩溃）
            cmd2 = f"{adb_prefix} shell logcat -d -t 600 | grep -E 'ActivityManager.*{package_name}'"
            process2 = await asyncio.create_subprocess_shell(
                cmd2,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout2, _ = await process2.communicate()
            
            if stdout2:
                lines2 = stdout2.decode('utf-8', errors='ignore').strip().split('\n')
                am_logs = [f"[AM] {line}" for line in lines2 if line.strip()]
                all_logs.extend(am_logs)
                if am_logs:
                    print(f"📋 获取到 {len(am_logs)} 行ActivityManager日志")
            
            # 方法3: 获取系统级别的崩溃相关日志
            cmd3 = f"{adb_prefix} shell logcat -d -t 300 | grep -E '(FATAL|CRASH|ANR).*{package_name}'"
            process3 = await asyncio.create_subprocess_shell(
                cmd3,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout3, _ = await process3.communicate()
            
            if stdout3:
                lines3 = stdout3.decode('utf-8', errors='ignore').strip().split('\n')
                sys_logs = [f"[SYS] {line}" for line in lines3 if line.strip()]
                all_logs.extend(sys_logs)
                if sys_logs:
                    print(f"📋 获取到 {len(sys_logs)} 行系统崩溃日志")
            
            # 如果获取到日志，按时间排序并添加调试信息
            if all_logs:
                print(f"📋 总共获取到 {len(all_logs)} 行相关日志")
                return all_logs
            else:
                # 没有获取到日志时，尝试获取基本的logcat输出以验证ADB连接
                print("⚠️ 未获取到应用相关日志，检查ADB连接...")
                test_cmd = f"{adb_prefix} shell logcat -d -t 10"
                test_process = await asyncio.create_subprocess_shell(
                    test_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                test_stdout, test_stderr = await test_process.communicate()
                
                if test_process.returncode == 0 and test_stdout:
                    print("✅ ADB连接正常，但应用日志为空")
                    return [f"[INFO] ADB连接正常，但未找到 {package_name} 相关日志"]
                else:
                    error_msg = test_stderr.decode('utf-8', errors='ignore').strip()
                    print(f"❌ ADB连接问题: {error_msg}")
                    return [f"[ERROR] ADB连接失败: {error_msg}"]
            
        except Exception as e:
            print(f"❌ 获取崩溃日志失败: {e}")
            return [f"[ERROR] logcat获取异常: {str(e)}"]
            
    async def _get_isg_error_logs(self) -> List[str]:
        """使用--pid参数获取iSG进程的错误日志
        
        Returns:
            List[str]: iSG进程错误日志列表
        """
        try:
            package_name = self.config['app']['package_name']
            adb_prefix = self._get_adb_prefix()
            
            # 首先获取iSG进程的PID
            pidof_cmd = f"{adb_prefix} shell pidof {package_name}"
            pid_process = await asyncio.create_subprocess_shell(
                pidof_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            pid_stdout, _ = await pid_process.communicate()
            
            if pid_process.returncode != 0 or not pid_stdout.strip():
                print("⚠️ iSG进程未运行，无法获取--pid日志")
                return []
            
            pid = pid_stdout.decode('utf-8', errors='ignore').strip().split()[0]
            if not pid.isdigit():
                print(f"⚠️ 获取到无效PID: {pid}")
                return []
                
            print(f"📱 iSG进程PID: {pid}")
            
            # 使用--pid参数获取该进程的错误日志
            logcat_cmd = f"{adb_prefix} shell logcat --pid={pid} -d -v time '*:E'"
            print(f"🔧 执行命令: {logcat_cmd}")
            
            logcat_process = await asyncio.create_subprocess_shell(
                logcat_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            logcat_stdout, logcat_stderr = await logcat_process.communicate()
            
            if logcat_process.returncode != 0:
                error_msg = logcat_stderr.decode('utf-8', errors='ignore').strip()
                print(f"❌ logcat --pid命令失败: {error_msg}")
                return []
            
            if logcat_stdout:
                lines = logcat_stdout.decode('utf-8', errors='ignore').strip().split('\n')
                error_logs = [f"[PID-ERROR] {line}" for line in lines if line.strip()]
                if error_logs:
                    print(f"✅ 通过--pid获取到 {len(error_logs)} 行错误日志")
                return error_logs
            else:
                print("ℹ️ iSG进程当前没有错误日志")
                return [f"[PID-INFO] iSG进程 (PID:{pid}) 当前没有错误日志"]
                
        except Exception as e:
            print(f"❌ 获取iSG进程错误日志失败: {e}")
            return [f"[PID-ERROR] 获取进程日志异常: {str(e)}"]
            
    def _detect_crash_type(self, logs: List[str]) -> str:
        """检测崩溃类型
        
        Args:
            logs: 日志行列表
            
        Returns:
            str: 崩溃类型
        """
        if not logs:
            return "process_missing"
            
        log_text = '\n'.join(logs).upper()
        
        # 按严重程度检测
        if 'FATAL EXCEPTION' in log_text:
            return 'fatal_exception'
        elif 'ANR' in log_text or 'APPLICATION NOT RESPONDING' in log_text:
            return 'anr'
        elif 'OUTOFMEMORYERROR' in log_text:
            return 'oom'
        elif 'SIGNAL' in log_text and 'SIGSEGV' in log_text:
            return 'native_crash'
        elif 'SIGABRT' in log_text:
            return 'abort'
        elif 'SIGKILL' in log_text:
            return 'killed'
        else:
            return 'unknown'
            
    async def _write_json_file(self, file_path: Path, data: Dict):
        """异步写入JSON文件
        
        Args:
            file_path: 文件路径
            data: 要写入的数据
        """
        try:
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"❌ 写入崩溃日志失败: {e}")
            
    async def _cleanup_old_logs(self):
        """清理旧日志文件"""
        try:
            # 获取所有崩溃日志文件
            log_files = list(self.crash_log_dir.glob("crash_*.log"))
            
            # 按修改时间排序（最新的在前）
            log_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            max_files = self.config['logging']['max_log_files']
            retention_days = self.config['logging']['retention_days']
            cutoff_time = datetime.now() - timedelta(days=retention_days)
            
            deleted_count = 0
            
            # 删除超过数量限制的文件
            for old_file in log_files[max_files:]:
                old_file.unlink()
                deleted_count += 1
                
            # 删除超过保留期的文件
            for log_file in log_files[:max_files]:  # 只检查保留的文件
                file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
                if file_time < cutoff_time:
                    log_file.unlink()
                    deleted_count += 1
                    
            if deleted_count > 0:
                print(f"🧹 清理了 {deleted_count} 个旧日志文件")
                
        except Exception as e:
            print(f"❌ 清理日志失败: {e}")
            
    async def get_crash_statistics(self) -> Dict:
        """获取崩溃统计信息
        
        Returns:
            Dict: 统计信息
        """
        try:
            log_files = list(self.crash_log_dir.glob("crash_*.log"))
            today = datetime.now().strftime("%Y%m%d")
            
            # 统计今日崩溃
            today_crashes = [f for f in log_files if today in f.name]
            
            # 统计崩溃类型
            crash_types = {}
            for log_file in log_files[-10:]:  # 最近10次崩溃
                try:
                    async with aiofiles.open(log_file, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        data = json.loads(content)
                        crash_type = data.get('crash_type', 'unknown')
                        crash_types[crash_type] = crash_types.get(crash_type, 0) + 1
                except:
                    continue
                    
            return {
                "total_crashes": len(log_files),
                "today_crashes": len(today_crashes),
                "recent_crash_types": crash_types,
                "oldest_log": min([f.stat().st_mtime for f in log_files]) if log_files else 0,
                "newest_log": max([f.stat().st_mtime for f in log_files]) if log_files else 0
            }
            
        except Exception as e:
            print(f"❌ 获取统计信息失败: {e}")
            return {}