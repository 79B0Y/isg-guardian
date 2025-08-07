#!/usr/bin/env python3
"""
应用守护模块

负责应用的生命周期管理，包括:
- 处理应用崩溃
- 自动重启应用
- 重启策略管理（限制重启次数、冷却机制）
"""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
# Import will be done locally to avoid circular imports


class AppGuardian:
    """应用守护器
    
    负责监控应用状态并在必要时重启应用
    """
    
    def __init__(self, config: dict, adb_manager=None):
        """初始化应用守护器
        
        Args:
            config: 配置字典
            adb_manager: ADB管理器实例
        """
        self.config = config
        self.restart_count = 0
        self.last_restart: Optional[datetime] = None
        self.cooldown_until: Optional[datetime] = None
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
        """启动守护器"""
        print("🛡️ 应用守护器启动")
        
    async def handle_crash(self, status) -> bool:
        """处理应用崩溃
        
        Args:
            status: 崩溃时的应用状态
            
        Returns:
            bool: 是否成功处理崩溃
        """
        print(f"💥 检测到应用异常 - PID: {status.pid}, 运行时长: {status.uptime}s")
        
        # 捕获崩溃日志
        try:
            from logger import CrashLogger
            logger = CrashLogger(self.config)
            
            # 根据状态决定使用哪种日志捕获方法
            if hasattr(status, 'crash_type') and status.crash_type == 'force_stop':
                crash_file = await logger.capture_force_stop_event(status)
            else:
                crash_file = await logger.capture_crash_logs(status)
                
            if crash_file:
                print(f"📝 事件日志已保存: {Path(crash_file).name}")
        except ImportError as e:
            print(f"⚠️ 无法导入日志模块: {e}")
        
        # 尝试重启应用
        return await self.restart_app()
        
    async def start_app(self) -> bool:
        """启动应用
        
        Returns:
            bool: 启动是否成功
        """
        try:
            print("🚀 启动 iSG 应用...")
            
            # 先确保应用完全停止
            await self._force_stop_app()
            await asyncio.sleep(2)
            
            # 启动应用
            package = self.config['app']['package_name']
            activity = self.config['app']['activity_name']
            adb_prefix = self._get_adb_prefix()
            cmd = f"{adb_prefix} shell am start -n {package}/{activity}"
            
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                print("✅ 应用启动成功")
                await asyncio.sleep(3)  # 等待应用完全启动
                return True
            else:
                error_msg = stderr.decode('utf-8', errors='ignore').strip()
                print(f"❌ 应用启动失败: {error_msg}")
                return False
                
        except Exception as e:
            print(f"❌ 启动应用异常: {e}")
            return False
            
    async def restart_app(self) -> bool:
        """重启应用
        
        Returns:
            bool: 重启是否成功
        """
        now = datetime.now()
        
        # 检查冷却时间
        if self.cooldown_until and now < self.cooldown_until:
            remaining = int((self.cooldown_until - now).total_seconds())
            print(f"⏳ 重启冷却中，还需等待 {remaining} 秒")
            return False
            
        # 检查重启次数限制
        if (self.last_restart and 
            now - self.last_restart < timedelta(hours=1) and
            self.restart_count >= self.config['monitor']['max_restarts']):
            
            # 进入冷却期
            cooldown_seconds = self.config['monitor']['cooldown_time']
            self.cooldown_until = now + timedelta(seconds=cooldown_seconds)
            print(f"🚫 重启次数过多，进入冷却期 {cooldown_seconds} 秒")
            return False
            
        # 重置计数器(如果距离上次重启超过1小时)
        if not self.last_restart or now - self.last_restart > timedelta(hours=1):
            self.restart_count = 0
            
        # 执行重启
        self.restart_count += 1
        print(f"🔄 尝试重启应用 (第 {self.restart_count} 次)")
        
        # 强制停止应用
        await self._force_stop_app()
        await asyncio.sleep(self.config['monitor']['restart_delay'])
        
        # 启动应用
        success = await self.start_app()
        
        if success:
            self.last_restart = now
            print(f"✅ 应用重启成功")
            
            # 如果重启成功，检查是否可以重置计数器
            if self.restart_count >= self.config['monitor']['max_restarts']:
                print("🎯 达到最大重启次数，下次重启将有冷却时间")
        else:
            print(f"❌ 应用重启失败")
            
        return success
        
    async def _force_stop_app(self):
        """强制停止应用"""
        try:
            package = self.config['app']['package_name']
            adb_prefix = self._get_adb_prefix()
            cmd = f"{adb_prefix} shell am force-stop {package}"
            
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            print("🛑 应用已强制停止")
            
        except Exception as e:
            print(f"❌ 强制停止应用失败: {e}")
            
    async def check_app_installation(self) -> bool:
        """检查应用是否已安装
        
        Returns:
            bool: 应用是否已安装
        """
        try:
            package = self.config['app']['package_name']
            adb_prefix = self._get_adb_prefix()
            cmd = f"{adb_prefix} shell pm list packages | grep {package}"
            
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()
            
            return bool(stdout.decode('utf-8', errors='ignore').strip())
            
        except Exception as e:
            print(f"❌ 检查应用安装状态失败: {e}")
            return False
            
    async def get_app_info(self) -> dict:
        """获取应用信息
        
        Returns:
            dict: 应用信息
        """
        try:
            package = self.config['app']['package_name']
            adb_prefix = self._get_adb_prefix()
            
            # 获取应用版本信息
            version_cmd = f"{adb_prefix} shell dumpsys package {package} | grep versionName"
            process = await asyncio.create_subprocess_shell(
                version_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()
            version_output = stdout.decode('utf-8', errors='ignore').strip()
            
            version = "Unknown"
            if "versionName=" in version_output:
                version = version_output.split("versionName=")[1].split()[0]
                
            # 获取应用安装时间
            install_cmd = f"{adb_prefix} shell dumpsys package {package} | grep firstInstallTime"
            process = await asyncio.create_subprocess_shell(
                install_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()
            install_output = stdout.decode('utf-8', errors='ignore').strip()
            
            install_time = "Unknown"
            if "firstInstallTime=" in install_output:
                install_time = install_output.split("firstInstallTime=")[1].strip()
                
            return {
                "package_name": package,
                "version": version,
                "install_time": install_time,
                "activity": self.config['app']['activity_name'],
                "restart_count": self.restart_count,
                "last_restart": self.last_restart.isoformat() if self.last_restart else None,
                "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else None
            }
            
        except Exception as e:
            print(f"❌ 获取应用信息失败: {e}")
            return {}
            
    def get_restart_status(self) -> dict:
        """获取重启状态信息
        
        Returns:
            dict: 重启状态
        """
        now = datetime.now()
        
        return {
            "restart_count": self.restart_count,
            "max_restarts": self.config['monitor']['max_restarts'],
            "last_restart": self.last_restart.isoformat() if self.last_restart else None,
            "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else None,
            "in_cooldown": bool(self.cooldown_until and now < self.cooldown_until),
            "cooldown_remaining": int((self.cooldown_until - now).total_seconds()) if self.cooldown_until and now < self.cooldown_until else 0,
            "can_restart": not (self.cooldown_until and now < self.cooldown_until)
        }
        
    async def clear_restart_history(self):
        """清除重启历史记录"""
        self.restart_count = 0
        self.last_restart = None
        self.cooldown_until = None
        print("🗑️ 重启历史记录已清除")