#!/usr/bin/env python3
"""
进程监控模块

负责监控Android应用的进程状态，包括:
- 使用ADB检查进程运行状态
- 获取进程详细信息（PID、内存使用、运行时长等）
- 检测应用崩溃情况
"""

import asyncio
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class AppStatus:
    """应用状态数据类
    
    Attributes:
        running: 应用是否正在运行
        crashed: 应用是否崩溃
        pid: 进程ID
        uptime: 运行时长（秒）
        memory_mb: 内存使用量（MB）
        timestamp: 状态检查时间戳
        crash_type: 崩溃类型（'logcat_crash'或'force_stop'）
    """
    running: bool = False
    crashed: bool = False
    pid: Optional[int] = None
    uptime: int = 0
    memory_mb: float = 0.0
    timestamp: datetime = datetime.now()
    crash_type: Optional[str] = None


class ProcessMonitor:
    """进程监控器
    
    负责监控目标Android应用的运行状态
    """
    
    def __init__(self, config: dict, adb_manager=None):
        """初始化进程监控器
        
        Args:
            config: 配置字典
            adb_manager: ADB管理器实例
        """
        self.config = config
        self.package_name = config['app']['package_name']
        self.last_pid = None
        self.start_time = None
        self.last_seen_running = False
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
        """启动监控器"""
        print(f"👀 开始监控应用: {self.package_name}")
        
    async def check_app_status(self) -> AppStatus:
        """检查应用状态
        
        Returns:
            AppStatus: 应用当前状态
        """
        try:
            # 使用pidof检查Android应用进程
            adb_prefix = self._get_adb_prefix()
            cmd = f"{adb_prefix} shell pidof {self.package_name}"
            result = await self._run_command(cmd)
            
            if result.returncode == 0 and result.stdout.strip():
                # 应用正在运行
                pids = result.stdout.strip().split()
                pid = int(pids[0]) if pids and pids[0].isdigit() else None
                if pid:
                    self.last_seen_running = True
                    return await self._get_running_status(pid)
                else:
                    # 进程ID无效
                    return AppStatus(running=False, crashed=False)
            else:
                # 应用未运行，检查是否是意外停止
                crashed = False
                crash_type = None
                
                if self.last_seen_running:
                    # 应用之前在运行，现在停止了，认为是崩溃/意外停止
                    crashed = True
                    crash_type = "force_stop"  # 默认认为是强制停止
                    print(f"💥 检测到应用意外停止 (PID: {self.last_pid})")
                    
                    # 检查是否有真正的崩溃日志
                    logcat_crash = await self._check_recent_crash()
                    if logcat_crash:
                        crash_type = "logcat_crash"
                        
                    # 重置状态
                    self.last_pid = None
                    self.start_time = None
                    
                self.last_seen_running = False
                return AppStatus(running=False, crashed=crashed, crash_type=crash_type)
                
        except Exception as e:
            print(f"❌ 检查应用状态失败: {e}")
            return AppStatus()
            
    async def _get_running_status(self, pid: int) -> AppStatus:
        """获取运行中应用的详细状态
        
        Args:
            pid: 进程ID
            
        Returns:
            AppStatus: 运行状态详情
        """
        # 检查是否是新进程
        if self.last_pid != pid:
            self.last_pid = pid
            self.start_time = datetime.now()
            print(f"🆕 检测到新的应用进程: PID {pid}")
            
        # 计算运行时间
        uptime = int((datetime.now() - self.start_time).total_seconds()) if self.start_time else 0
        
        # 获取内存使用
        memory_mb = await self._get_memory_usage(pid)
        
        return AppStatus(
            running=True,
            pid=pid,
            uptime=uptime,
            memory_mb=memory_mb,
            timestamp=datetime.now()
        )
        
    async def _check_recent_crash(self) -> bool:
        """检查最近是否有崩溃
        
        Returns:
            bool: 是否检测到崩溃
        """
        try:
            # 检查最近2分钟的logcat
            crash_patterns = [
                f'{self.package_name}.*FATAL',
                f'{self.package_name}.*CRASH',
                f'{self.package_name}.*ANR'
            ]
            
            for pattern in crash_patterns:
                cmd = f"adb shell logcat -d -t 120 | grep -E '{pattern}'"
                result = await self._run_command(cmd)
                if result.returncode == 0 and result.stdout.strip():
                    return True
                    
            return False
        except Exception as e:
            print(f"❌ 检查崩溃状态失败: {e}")
            return False
        
    async def _get_memory_usage(self, pid: int) -> float:
        """获取进程内存使用
        
        Args:
            pid: 进程ID
            
        Returns:
            float: 内存使用量（MB）
        """
        try:
            adb_prefix = self._get_adb_prefix()
            cmd = f"{adb_prefix} shell cat /proc/{pid}/status"
            result = await self._run_command(cmd)
            
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if line.startswith('VmRSS:'):
                        parts = line.split()
                        if len(parts) >= 2 and parts[1].isdigit():
                            kb = int(parts[1])
                            return kb / 1024.0  # 转换为MB
        except Exception as e:
            print(f"❌ 获取内存使用失败: {e}")
            
        return 0.0
        
    async def _run_command(self, command: str) -> subprocess.CompletedProcess:
        """执行shell命令
        
        Args:
            command: 要执行的命令
            
        Returns:
            subprocess.CompletedProcess: 命令执行结果
        """
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            return subprocess.CompletedProcess(
                command, 
                process.returncode, 
                stdout.decode('utf-8', errors='ignore'), 
                stderr.decode('utf-8', errors='ignore')
            )
        except Exception as e:
            print(f"❌ 执行命令失败 [{command}]: {e}")
            return subprocess.CompletedProcess(command, 1, "", str(e))