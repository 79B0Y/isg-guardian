#!/usr/bin/env python3
"""
ADB连接管理模块

负责管理Android Debug Bridge连接，包括:
- 自动建立ADB连接
- 连接状态检测和恢复
- 特殊环境的连接设置
"""

import asyncio
import subprocess
import time
from typing import Optional, List


class ADBManager:
    """ADB连接管理器
    
    处理ADB连接的建立、维护和故障恢复
    """
    
    def __init__(self, config: dict):
        """初始化ADB管理器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.adb_config = config.get('adb', {})
        self.host = self.adb_config.get('host', '127.0.0.1')
        self.port = self.adb_config.get('port', 5555)
        self.tcp_port = self.adb_config.get('tcp_port', 5555)
        self.retry_count = self.adb_config.get('retry_count', 3)
        self.retry_delay = self.adb_config.get('retry_delay', 5)
        self.setup_commands = self.adb_config.get('setup_commands', [])
        self.auto_connect = self.adb_config.get('auto_connect', True)
        self.connection_established = False
        self.target_device = f"{self.host}:{self.port}"
        
    def get_adb_prefix(self) -> str:
        """获取带设备指定的ADB命令前缀
        
        Returns:
            str: ADB命令前缀，如 'adb -s 127.0.0.1:5555'
        """
        return f"adb -s {self.target_device}"
        
    async def start(self):
        """启动ADB管理器"""
        print("🔌 ADB连接管理器启动")
        
        if self.auto_connect:
            success = await self.establish_connection()
            if success:
                print("✅ ADB连接已建立")
            else:
                print("⚠️ ADB连接建立失败，将在监控过程中重试")
        else:
            print("ℹ️ ADB自动连接已禁用")
            
    async def establish_connection(self) -> bool:
        """建立ADB连接
        
        Returns:
            bool: 连接是否成功建立
        """
        print(f"🔌 正在建立ADB连接到 {self.host}:{self.port}")
        
        try:
            # 执行预设置命令
            if self.setup_commands:
                print("🔧 执行ADB设置命令...")
                for cmd in self.setup_commands:
                    await self._run_setup_command(cmd)
                    await asyncio.sleep(1)  # 命令间等待
                    
            # 等待服务启动
            await asyncio.sleep(2)
            
            # 尝试连接
            for attempt in range(self.retry_count):
                print(f"🔄 连接尝试 {attempt + 1}/{self.retry_count}")
                
                success = await self._attempt_connection()
                if success:
                    self.connection_established = True
                    return True
                    
                if attempt < self.retry_count - 1:
                    print(f"⏳ 等待 {self.retry_delay} 秒后重试...")
                    await asyncio.sleep(self.retry_delay)
                    
            print("❌ ADB连接建立失败")
            return False
            
        except Exception as e:
            print(f"❌ ADB连接过程异常: {e}")
            return False
            
    async def _run_setup_command(self, command: str):
        """执行设置命令
        
        Args:
            command: 要执行的命令
        """
        try:
            print(f"🔧 执行: {command}")
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                print(f"✅ 命令执行成功")
            else:
                error_msg = stderr.decode('utf-8', errors='ignore').strip()
                if error_msg:
                    print(f"⚠️ 命令警告: {error_msg}")
                    
        except Exception as e:
            print(f"❌ 命令执行失败 [{command}]: {e}")
            
    async def _attempt_connection(self) -> bool:
        """尝试建立连接
        
        Returns:
            bool: 连接是否成功
        """
        try:
            # 使用adb connect命令
            connect_cmd = f"adb connect {self.host}:{self.port}"
            process = await asyncio.create_subprocess_shell(
                connect_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            output = stdout.decode('utf-8', errors='ignore').strip()
            print(f"🔌 ADB连接输出: {output}")
            
            # 检查连接是否成功
            if "connected to" in output.lower() or "already connected" in output.lower():
                # 验证设备是否可用
                return await self.check_device_availability()
            else:
                return False
                
        except Exception as e:
            print(f"❌ 连接尝试失败: {e}")
            return False
            
    async def check_device_availability(self) -> bool:
        """检查设备可用性
        
        Returns:
            bool: 设备是否可用
        """
        try:
            process = await asyncio.create_subprocess_shell(
                "adb devices",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            output = stdout.decode('utf-8', errors='ignore')
            
            # 检查是否有设备连接
            lines = output.strip().split('\n')
            for line in lines[1:]:  # 跳过标题行
                if '\tdevice' in line:
                    device_id = line.split('\t')[0]
                    print(f"✅ 检测到设备: {device_id}")
                    return True
                    
            print("❌ 未检测到可用设备")
            return False
            
        except Exception as e:
            print(f"❌ 设备检查失败: {e}")
            return False
            
    async def check_connection_status(self) -> dict:
        """检查ADB连接状态
        
        Returns:
            dict: 连接状态信息
        """
        try:
            # 检查设备列表
            process = await asyncio.create_subprocess_shell(
                "adb devices",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                return {
                    'connected': False,
                    'error': 'ADB command failed',
                    'devices': [],
                    'target_device': f"{self.host}:{self.port}"
                }
                
            output = stdout.decode('utf-8', errors='ignore')
            lines = output.strip().split('\n')
            
            devices = []
            target_connected = False
            target_device = f"{self.host}:{self.port}"
            
            for line in lines[1:]:  # 跳过标题行
                if '\t' in line:
                    device_id, status = line.split('\t')
                    devices.append({'id': device_id, 'status': status})
                    
                    if device_id == target_device and status == 'device':
                        target_connected = True
                        
            return {
                'connected': target_connected,
                'devices': devices,
                'target_device': target_device,
                'device_count': len([d for d in devices if d['status'] == 'device'])
            }
            
        except Exception as e:
            return {
                'connected': False,
                'error': str(e),
                'devices': [],
                'target_device': f"{self.host}:{self.port}"
            }
            
    async def ensure_connection(self) -> bool:
        """确保ADB连接正常
        
        Returns:
            bool: 连接是否正常
        """
        if not self.auto_connect:
            return await self.check_device_availability()
            
        # 检查当前连接状态
        status = await self.check_connection_status()
        
        if status['connected']:
            return True
            
        # 如果未连接，尝试重新建立连接
        print("🔄 检测到ADB连接断开，正在重新连接...")
        return await self.establish_connection()
        
    async def disconnect(self):
        """断开ADB连接"""
        if not self.connection_established:
            return
            
        try:
            disconnect_cmd = f"adb disconnect {self.host}:{self.port}"
            process = await asyncio.create_subprocess_shell(
                disconnect_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            
            self.connection_established = False
            print(f"🔌 已断开ADB连接: {self.host}:{self.port}")
            
        except Exception as e:
            print(f"❌ 断开ADB连接失败: {e}")
            
    async def get_device_info(self) -> dict:
        """获取设备信息
        
        Returns:
            dict: 设备信息
        """
        try:
            # 获取设备属性，使用设备指定
            adb_prefix = self.get_adb_prefix()
            commands = {
                'model': f'{adb_prefix} shell getprop ro.product.model',
                'brand': f'{adb_prefix} shell getprop ro.product.brand',
                'version': f'{adb_prefix} shell getprop ro.build.version.release',
                'sdk': f'{adb_prefix} shell getprop ro.build.version.sdk',
                'serial': f'{adb_prefix} shell getprop ro.serialno'
            }
            
            device_info = {}
            
            for key, cmd in commands.items():
                try:
                    process = await asyncio.create_subprocess_shell(
                        cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await process.communicate()
                    
                    if process.returncode == 0:
                        value = stdout.decode('utf-8', errors='ignore').strip()
                        if value:
                            device_info[key] = value
                            print(f"📱 {key}: {value}")
                        else:
                            device_info[key] = 'Unknown'
                            print(f"⚠️ {key}: 空值")
                    else:
                        error_msg = stderr.decode('utf-8', errors='ignore').strip()
                        device_info[key] = 'Unknown'
                        print(f"❌ {key} 获取失败: {error_msg}")
                        
                except Exception as e:
                    device_info[key] = 'Unknown'
                    print(f"❌ {key} 执行异常: {e}")
                    
            # 添加诊断信息
            if all(value == 'Unknown' for value in device_info.values()):
                print(f"⚠️ 所有设备信息都为Unknown，可能是ADB连接问题")
                print(f"   目标设备: {self.target_device}")
                print(f"   使用的ADB前缀: {adb_prefix}")
            else:
                print(f"✅ 成功获取部分设备信息")
                
            return device_info
            
        except Exception as e:
            print(f"❌ 获取设备信息失败: {e}")
            return {}