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
    
    def __init__(self, config: dict):
        """初始化日志收集器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.crash_log_dir = Path(config['logging']['crash_log_dir'])
        self.status_log_file = Path(config['logging']['status_log_file'])
        
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
            
            # 尝试获取一些相关日志
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
            cmd = "adb shell logcat -d -t 120 | grep -E '(ActivityManager|System)'"
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
            # 获取最近10分钟的应用相关日志
            cmd = f"adb shell logcat -d -t 600 | grep {self.config['app']['package_name']}"
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()
            
            if stdout:
                lines = stdout.decode('utf-8', errors='ignore').strip().split('\n')
                return [line for line in lines if line.strip()]
            return []
            
        except Exception as e:
            print(f"❌ 获取崩溃日志失败: {e}")
            return []
            
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