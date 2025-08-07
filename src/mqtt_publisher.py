#!/usr/bin/env python3
"""
MQTT发布模块

负责与Home Assistant集成，包括:
- 发布应用状态到MQTT
- 设置Home Assistant自动发现
- 发布崩溃告警
"""

import json
import asyncio
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional
# Import will be done locally to avoid circular imports


class MQTTPublisher:
    """MQTT消息发布器
    
    使用mosquitto_pub命令行工具发布消息到MQTT代理
    """
    
    def __init__(self, config: dict):
        """初始化MQTT发布器
        
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
        
    async def setup_discovery(self):
        """设置Home Assistant自动发现
        
        创建所有需要的实体配置
        """
        print("📡 配置 Home Assistant 自动发现...")
        
        device_info = {
            "identifiers": [self.device_id],
            "name": "iSG App Guardian",
            "model": "Guardian v2.0",
            "manufacturer": "iSG Bridge Project",
            "sw_version": "2.0.0"
        }
        
        # 应用状态传感器 (binary_sensor)
        app_status_config = {
            "name": "iSG App Running",
            "device_class": "running",
            "state_topic": f"{self.topic_prefix}/{self.device_id}/app_status/state",
            "unique_id": f"{self.device_id}_app_running",
            "icon": "mdi:application",
            "payload_on": "ON",
            "payload_off": "OFF",
            "device": device_info
        }
        
        # 今日崩溃次数传感器
        crashes_today_config = {
            "name": "iSG Crashes Today",
            "state_topic": f"{self.topic_prefix}/{self.device_id}/crashes_today/state",
            "unique_id": f"{self.device_id}_crashes_today",
            "icon": "mdi:alert-circle-outline",
            "unit_of_measurement": "crashes",
            "state_class": "total_increasing",
            "device": device_info
        }
        
        # 运行时间传感器
        uptime_config = {
            "name": "iSG App Uptime",
            "state_topic": f"{self.topic_prefix}/{self.device_id}/uptime/state",
            "unit_of_measurement": "s",
            "unique_id": f"{self.device_id}_uptime",
            "icon": "mdi:timer-outline",
            "state_class": "total_increasing",
            "device": device_info
        }
        
        # 内存使用传感器
        memory_config = {
            "name": "iSG App Memory",
            "state_topic": f"{self.topic_prefix}/{self.device_id}/memory/state",
            "unit_of_measurement": "MB",
            "unique_id": f"{self.device_id}_memory",
            "icon": "mdi:memory",
            "state_class": "measurement",
            "device": device_info
        }
        
        # 重启按钮
        restart_button_config = {
            "name": "Restart iSG App",
            "command_topic": f"{self.topic_prefix}/{self.device_id}/restart/set",
            "unique_id": f"{self.device_id}_restart",
            "icon": "mdi:restart",
            "device": device_info
        }
        
        # 守护进程状态传感器
        guardian_status_config = {
            "name": "iSG Guardian Status",
            "state_topic": f"{self.topic_prefix}/{self.device_id}/guardian_status/state",
            "unique_id": f"{self.device_id}_guardian_status",
            "icon": "mdi:shield-check",
            "device": device_info
        }
        
        # ADB连接状态传感器
        adb_connection_config = {
            "name": "iSG ADB Connection",
            "device_class": "connectivity",
            "state_topic": f"{self.topic_prefix}/{self.device_id}/adb_connection/state",
            "unique_id": f"{self.device_id}_adb_connection",
            "icon": "mdi:usb",
            "payload_on": "connected",
            "payload_off": "disconnected",
            "device": device_info
        }
        
        # 设备信息传感器
        device_info_config = {
            "name": "iSG Device Info",
            "state_topic": f"{self.topic_prefix}/{self.device_id}/device_info/state",
            "unique_id": f"{self.device_id}_device_info",
            "icon": "mdi:information",
            "device": device_info
        }
        
        # 发布所有发现配置
        configs = [
            ("binary_sensor", "app_running", app_status_config),
            ("sensor", "crashes_today", crashes_today_config),
            ("sensor", "uptime", uptime_config),
            ("sensor", "memory", memory_config),
            ("button", "restart", restart_button_config),
            ("sensor", "guardian_status", guardian_status_config),
            ("binary_sensor", "adb_connection", adb_connection_config),
            ("sensor", "device_info", device_info_config)
        ]
        
        success_count = 0
        for component, object_id, config in configs:
            if await self._publish_discovery(component, object_id, config):
                success_count += 1
                
        print(f"✅ Home Assistant 实体注册完成 ({success_count}/{len(configs)})")
        
        # 发布初始状态
        await self._publish("guardian_status/state", "online")
        
    async def publish_status(self, status):
        """发布应用状态
        
        Args:
            status: 应用状态对象
        """
        try:
            # 发布应用运行状态
            await self._publish("app_status/state", "ON" if status.running else "OFF")
            
            # 发布今日崩溃次数
            crashes_today = await self._get_crashes_today()
            await self._publish("crashes_today/state", str(crashes_today))
            
            # 发布运行时间
            await self._publish("uptime/state", str(status.uptime))
            
            # 发布内存使用
            await self._publish("memory/state", f"{status.memory_mb:.1f}")
            
            # 更新守护进程状态时间戳
            await self._publish("guardian_status/state", "online")
            
        except Exception as e:
            # 静默处理MQTT错误，不影响核心监控功能
            pass
            
    async def publish_crash_alert(self, crash_type: str, crash_reason: str):
        """发布崩溃告警
        
        Args:
            crash_type: 崩溃类型
            crash_reason: 崩溃原因
        """
        try:
            alert_data = {
                "timestamp": datetime.now().isoformat(),
                "type": crash_type,
                "reason": crash_reason,
                "severity": "critical"
            }
            
            success = await self._publish("crash_alert/state", json.dumps(alert_data))
            if success:
                print(f"🚨 已发布崩溃告警")
            
        except Exception as e:
            print(f"❌ 发布崩溃告警失败: {e}")
            
    async def publish_adb_status(self, connection_status: dict):
        """发布ADB连接状态
        
        Args:
            connection_status: ADB连接状态信息
        """
        try:
            # 发布连接状态
            is_connected = connection_status.get('connected', False)
            await self._publish("adb_connection/state", "connected" if is_connected else "disconnected")
            
            # 发布设备信息
            if is_connected and connection_status.get('devices'):
                device_info = {
                    "timestamp": datetime.now().isoformat(),
                    "target_device": connection_status.get('target_device', ''),
                    "device_count": connection_status.get('device_count', 0),
                    "devices": connection_status.get('devices', [])
                }
                await self._publish("device_info/state", json.dumps(device_info))
            
        except Exception as e:
            # 静默处理MQTT错误
            pass
            
    async def publish_device_info(self, device_info: dict):
        """发布设备详细信息
        
        Args:
            device_info: 设备信息字典
        """
        try:
            if device_info:
                info_data = {
                    "timestamp": datetime.now().isoformat(),
                    **device_info
                }
                await self._publish("device_info/state", json.dumps(info_data))
                
        except Exception as e:
            # 静默处理MQTT错误
            pass
            
    async def publish_guardian_offline(self):
        """发布守护进程离线状态"""
        try:
            await self._publish("guardian_status/state", "offline", retain=True)
            await self._publish("app_status/state", "OFF", retain=True)
        except:
            pass
        
    async def _publish_discovery(self, component: str, object_id: str, config: dict) -> bool:
        """发布Home Assistant自动发现配置
        
        Args:
            component: 组件类型
            object_id: 对象ID
            config: 配置字典
            
        Returns:
            bool: 发布是否成功
        """
        topic = f"homeassistant/{component}/{self.device_id}_{object_id}/config"
        return await self._publish_mosquitto(topic, json.dumps(config), retain=True)
        
    async def _publish(self, subtopic: str, payload: str, retain: bool = False) -> bool:
        """发布消息到MQTT
        
        Args:
            subtopic: 子主题
            payload: 消息内容
            retain: 是否保留消息
            
        Returns:
            bool: 发布是否成功
        """
        topic = f"{self.topic_prefix}/{self.device_id}/{subtopic}"
        return await self._publish_mosquitto(topic, payload, retain)
        
    async def _publish_mosquitto(self, topic: str, payload: str, retain: bool = False) -> bool:
        """使用mosquitto_pub发布消息
        
        Args:
            topic: 主题
            payload: 消息内容
            retain: 是否保留消息
            
        Returns:
            bool: 发布是否成功
        """
        try:
            cmd = [
                "mosquitto_pub",
                "-h", self.broker_host,
                "-p", str(self.broker_port),
                "-t", topic,
                "-m", payload
            ]
            
            # 添加认证参数
            if self.username:
                cmd.extend(["-u", self.username])
                if self.password:
                    cmd.extend(["-P", self.password])
                    
            # 添加retain标志
            if retain:
                cmd.append("-r")
                
            # 异步执行命令 (静默执行，避免输出干扰)
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE
            )
            
            _, stderr = await process.communicate()
            
            # 只在错误时输出
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore').strip()
                print(f"❌ MQTT发布失败 [{topic}]: {error_msg}")
                return False
                
            return True
                
        except FileNotFoundError:
            print("❌ mosquitto_pub 命令未找到，请安装: pkg install mosquitto")
            return False
        except Exception as e:
            print(f"❌ MQTT发布异常: {e}")
            return False
            
    async def _get_crashes_today(self) -> int:
        """获取今日崩溃次数
        
        Returns:
            int: 今日崩溃次数
        """
        try:
            today = datetime.now().strftime("%Y%m%d")
            crash_log_dir = Path(self.config['logging']['crash_log_dir'])
            
            if not crash_log_dir.exists():
                return 0
                
            crash_files = list(crash_log_dir.glob(f"crash_{today}_*.log"))
            return len(crash_files)
            
        except Exception as e:
            print(f"❌ 获取崩溃统计失败: {e}")
            return 0
            
    async def test_connection(self) -> bool:
        """测试MQTT连接
        
        Returns:
            bool: 连接是否正常
        """
        try:
            test_topic = f"{self.topic_prefix}/{self.device_id}/test"
            test_payload = f"connection_test_{datetime.now().timestamp()}"
            
            return await self._publish_mosquitto(test_topic, test_payload)
            
        except Exception as e:
            print(f"❌ MQTT连接测试失败: {e}")
            return False
            
    def get_mqtt_info(self) -> dict:
        """获取MQTT配置信息
        
        Returns:
            dict: MQTT配置信息
        """
        return {
            "enabled": self.mqtt_config.get('enabled', False),
            "broker": f"{self.broker_host}:{self.broker_port}",
            "topic_prefix": self.topic_prefix,
            "device_id": self.device_id,
            "has_auth": bool(self.username),
            "discovery_prefix": "homeassistant"
        }