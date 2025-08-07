#!/usr/bin/env python3
"""
MQTT订阅模块

负责监听Home Assistant的控制命令，包括:
- 监听重启按钮命令
- 处理其他控制命令
- 与主Guardian进程通信
"""

import asyncio
import json
import subprocess
import signal
import os
from datetime import datetime
from typing import Optional, Callable
from pathlib import Path


class MQTTSubscriber:
    """MQTT命令订阅器
    
    监听Home Assistant发送的控制命令
    """
    
    def __init__(self, config: dict):
        """初始化MQTT订阅器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.mqtt_config = config['mqtt']
        self.broker_host = self.mqtt_config['broker']
        self.broker_port = self.mqtt_config['port']
        self.topic_prefix = self.mqtt_config['topic_prefix']
        self.device_id = self.mqtt_config['device_id']
        self.username = self.mqtt_config.get('username', '')
        self.password = self.mqtt_config.get('password', '')
        
        # 命令处理回调
        self.restart_callback: Optional[Callable] = None
        self.running = False
        self.subscriber_process: Optional[asyncio.subprocess.Process] = None
        
    async def start(self):
        """启动MQTT订阅器"""
        if not self.mqtt_config.get('enabled', False):
            print("ℹ️ MQTT未启用，跳过命令订阅")
            return
            
        print("📡 启动MQTT命令订阅器...")
        
        # 订阅重启命令
        restart_topic = f"{self.topic_prefix}/{self.device_id}/restart/set"
        await self._start_subscriber(restart_topic)
        
    async def stop(self):
        """停止MQTT订阅器"""
        self.running = False
        if self.subscriber_process:
            try:
                self.subscriber_process.terminate()
                await self.subscriber_process.wait()
            except:
                pass
        print("📡 MQTT订阅器已停止")
        
    def set_restart_callback(self, callback: Callable):
        """设置重启回调函数
        
        Args:
            callback: 重启回调函数
        """
        self.restart_callback = callback
        
    async def _start_subscriber(self, topic: str):
        """启动订阅进程
        
        Args:
            topic: 要订阅的主题
        """
        try:
            cmd = [
                "mosquitto_sub",
                "-h", self.broker_host,
                "-p", str(self.broker_port),
                "-t", topic
            ]
            
            # 添加认证参数
            if self.username:
                cmd.extend(["-u", self.username])
                if self.password:
                    cmd.extend(["-P", self.password])
            
            print(f"📡 订阅MQTT主题: {topic}")
            
            # 启动订阅进程
            self.subscriber_process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            self.running = True
            
            # 启动消息处理任务
            asyncio.create_task(self._process_messages())
            
        except FileNotFoundError:
            print("❌ mosquitto_sub 命令未找到，请安装: pkg install mosquitto")
        except Exception as e:
            print(f"❌ MQTT订阅启动失败: {e}")
            
    async def _process_messages(self):
        """处理MQTT消息"""
        if not self.subscriber_process:
            return
            
        try:
            while self.running and self.subscriber_process.returncode is None:
                # 读取消息
                line = await self.subscriber_process.stdout.readline()
                if not line:
                    break
                    
                message = line.decode('utf-8', errors='ignore').strip()
                if message:
                    await self._handle_command(message)
                    
        except Exception as e:
            print(f"❌ MQTT消息处理异常: {e}")
            
    async def _handle_command(self, message: str):
        """处理控制命令
        
        Args:
            message: 收到的MQTT消息
        """
        try:
            print(f"📡 收到MQTT命令: {message}")
            
            # 处理重启命令
            if message.lower() in ['restart', 'on', '1', 'true']:
                print("🔄 执行应用重启命令...")
                if self.restart_callback:
                    # 在后台执行重启，避免阻塞
                    asyncio.create_task(self._execute_restart())
                else:
                    print("⚠️ 未设置重启回调函数")
                    
        except Exception as e:
            print(f"❌ 处理MQTT命令失败: {e}")
            
    async def _execute_restart(self):
        """执行重启操作"""
        try:
            if self.restart_callback:
                success = await self.restart_callback()
                if success:
                    print("✅ 应用重启成功 (通过MQTT命令)")
                else:
                    print("❌ 应用重启失败 (通过MQTT命令)")
        except Exception as e:
            print(f"❌ 执行重启操作异常: {e}")
            
    async def test_connection(self) -> bool:
        """测试MQTT连接
        
        Returns:
            bool: 连接是否正常
        """
        try:
            test_topic = f"{self.topic_prefix}/{self.device_id}/test_sub"
            
            cmd = [
                "timeout", "5",  # 5秒超时
                "mosquitto_sub",
                "-h", self.broker_host,
                "-p", str(self.broker_port),
                "-t", test_topic,
                "-C", "1"  # 只接收1条消息后退出
            ]
            
            # 添加认证参数
            if self.username:
                cmd.extend(["-u", self.username])
                if self.password:
                    cmd.extend(["-P", self.password])
                    
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # 等待进程结束，但不超过6秒
            try:
                await asyncio.wait_for(process.wait(), timeout=6.0)
                return True
            except asyncio.TimeoutError:
                process.terminate()
                return False
                
        except Exception as e:
            print(f"❌ MQTT订阅连接测试失败: {e}")
            return False