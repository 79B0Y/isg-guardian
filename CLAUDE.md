# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**iSG App Guardian** is a lightweight application monitoring daemon service specifically designed for the Termux environment. It monitors the iSG Android application's process status, detects crashes, records logs, and automatically restarts the application when needed.

## Architecture

This is a Python-based project using AsyncIO for efficient asynchronous operations:

### Core Components

- **Main Script**: `isg-guardian` - Command-line interface with daemon functionality
- **Process Monitor**: `src/monitor.py` - Monitors Android app process via ADB
- **Crash Logger**: `src/logger.py` - Collects and manages crash logs in JSON format
- **App Guardian**: `src/guardian.py` - Handles app lifecycle and restart logic
- **MQTT Publisher**: `src/mqtt_publisher.py` - Integrates with Home Assistant via MQTT

### Technology Stack

- **Python 3.8+** with AsyncIO
- **ADB** for Android Debug Bridge communication
- **MQTT** via mosquitto_pub CLI tool
- **YAML** configuration files
- **JSON** structured logging

## Development Setup

### Prerequisites

```bash
# Termux environment
pkg update
pkg install python android-tools mosquitto git

# Python dependencies
pip install -r requirements.txt
```

### Quick Start

```bash
# 1. Install dependencies
./install.sh

# 2. Configure the application
cp config.yaml.example config.yaml
# Edit config.yaml as needed

# 3. Test the application
./isg-guardian --help
./isg-guardian status
```

## Common Development Commands

### Running the Application

```bash
# Start daemon service
./isg-guardian start

# Stop daemon service
./isg-guardian stop

# Check status
./isg-guardian status

# View real-time logs
./isg-guardian logs
```

### Development and Testing

```bash
# Run in foreground for debugging
python isg-guardian

# Test individual modules
python -c "
import sys, yaml, asyncio
sys.path.insert(0, 'src')
from monitor import ProcessMonitor
config = yaml.safe_load(open('config.yaml'))
monitor = ProcessMonitor(config)
status = asyncio.run(monitor.check_app_status())
print(f'App status: {status}')
"

# Check Python dependencies
pip list | grep -E "(yaml|aiofiles|setproctitle)"

# Validate configuration
python -c "import yaml; print(yaml.safe_load(open('config.yaml')))"
```

### Maintenance Commands

```bash
# View crash logs
ls -la data/crash_logs/

# Check disk usage
du -sh data/

# Monitor memory usage
ps -o pid,ppid,cmd,rss,cpu -p $(pgrep -f 'iSG App Guardian')

# Test MQTT connection
mosquitto_pub -h localhost -t "test" -m "hello"
```

## File Structure

```
isg-guardian/
├── isg-guardian              # Main executable script
├── install.sh               # One-click install script
├── requirements.txt         # Python dependencies
├── config.yaml.example     # Configuration template
├── README.md               # Project documentation
├── src/                    # Source code modules
│   ├── monitor.py         # Process monitoring
│   ├── logger.py          # Log management
│   ├── guardian.py        # App lifecycle management
│   └── mqtt_publisher.py  # MQTT integration
└── data/                   # Data directory (auto-created)
    ├── crash_logs/        # Crash log files
    ├── app_status.log     # Application status log
    ├── guardian.log       # Daemon service log
    └── guardian.pid       # Process PID file
```

## Configuration

The main configuration is in `config.yaml`:

- **app**: Target Android application settings (package name, activity)
- **monitor**: Monitoring intervals and restart policies
- **logging**: Log file management and retention
- **mqtt**: Home Assistant integration via MQTT

## Key Design Patterns

- **Single Process Architecture**: Uses setproctitle for process identification
- **Asyncio Concurrency**: Efficient async/await for I/O operations  
- **CLI-based Integration**: Uses mosquitto_pub instead of persistent MQTT connections
- **File-based Storage**: JSON logs instead of database for lightweight operation
- **Defensive Error Handling**: Graceful degradation when optional components fail

## Termux-Specific Considerations

- Uses `pkg` package manager commands in install script
- Designed for user-space execution (no root required)
- Compatible with Android file system permissions
- Optimized for resource-constrained environment

## Home Assistant Integration

The service publishes these MQTT entities:
- `binary_sensor.isg_app_running` - App running status
- `sensor.isg_crashes_today` - Daily crash count  
- `sensor.isg_app_uptime` - Application uptime
- `sensor.isg_app_memory` - Memory usage
- `button.restart_isg_app` - Restart button

## Performance Targets

- Memory usage: < 15MB
- Startup time: < 2 seconds
- CPU usage: < 0.5% average
- Single process architecture for simplicity

## Debugging

For troubleshooting:
1. Check `data/guardian.log` for service logs
2. Use `./isg-guardian status` for current state
3. Test ADB connection: `adb devices`
4. Verify config: `python -c "import yaml; yaml.safe_load(open('config.yaml'))"`
5. Run in foreground mode for detailed output