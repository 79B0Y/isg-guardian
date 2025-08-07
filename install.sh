#!/bin/bash
# iSG Guardian 一键安装脚本
# 专为Termux环境设计

set -e  # 出错时退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

print_step() {
    print_message $BLUE "🔧 $1"
}

print_success() {
    print_message $GREEN "✅ $1"
}

print_warning() {
    print_message $YELLOW "⚠️  $1"
}

print_error() {
    print_message $RED "❌ $1"
}

print_info() {
    print_message $CYAN "ℹ️  $1"
}

# 获取脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 显示欢迎信息
echo
print_message $PURPLE "╔══════════════════════════════════════════════════════════╗"
print_message $PURPLE "║                  iSG App Guardian                       ║"
print_message $PURPLE "║              轻量级应用监控守护服务                        ║"
print_message $PURPLE "║                   一键安装脚本                           ║"
print_message $PURPLE "╚══════════════════════════════════════════════════════════╝"
echo

# 检查是否在Termux环境中
print_step "检查运行环境..."
if [[ "$PREFIX" == *"com.termux"* ]]; then
    print_success "检测到Termux环境"
    PACKAGE_MANAGER="pkg"
    PYTHON_CMD="python"
    PIP_CMD="pip"
else
    print_info "非Termux环境，使用标准Linux命令"
    PACKAGE_MANAGER="apt"
    PYTHON_CMD="python3"
    PIP_CMD="pip3"
fi

# 检查必需工具
print_step "检查基本工具..."
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

if ! command_exists $PYTHON_CMD; then
    print_error "Python未安装"
    if [[ "$PACKAGE_MANAGER" == "pkg" ]]; then
        print_info "正在安装Python..."
        pkg update && pkg install python
    else
        print_error "请手动安装Python3"
        exit 1
    fi
fi

print_success "Python已就绪"

# 检查pip
if ! command_exists $PIP_CMD; then
    print_warning "pip未找到，尝试安装..."
    if [[ "$PACKAGE_MANAGER" == "pkg" ]]; then
        pkg install python-pip
    else
        print_error "请手动安装pip"
        exit 1
    fi
fi

print_success "pip已就绪"

# 检查是否在虚拟环境中
if [[ -n "$VIRTUAL_ENV" ]]; then
    print_info "检测到虚拟环境: $VIRTUAL_ENV"
    VENV_PYTHON="$VIRTUAL_ENV/bin/python"
elif [[ -d ".venv" ]]; then
    print_info "检测到本地虚拟环境: .venv"
    VENV_PYTHON="$(pwd)/.venv/bin/python"
else
    VENV_PYTHON=""
fi

# 安装系统依赖
print_step "安装系统依赖..."
if [[ "$PACKAGE_MANAGER" == "pkg" ]]; then
    # Termux环境
    print_info "安装ADB和Mosquitto..."
    pkg update
    
    # 安装依赖包
    PACKAGES_TO_INSTALL=""
    
    if ! command_exists adb; then
        PACKAGES_TO_INSTALL="$PACKAGES_TO_INSTALL android-tools"
    fi
    
    if ! command_exists mosquitto_pub; then
        PACKAGES_TO_INSTALL="$PACKAGES_TO_INSTALL mosquitto"
    fi
    
    if [[ -n "$PACKAGES_TO_INSTALL" ]]; then
        print_info "安装包:$PACKAGES_TO_INSTALL"
        pkg install $PACKAGES_TO_INSTALL
    fi
    
else
    # 标准Linux环境
    print_warning "请手动安装以下依赖:"
    print_info "  - adb: sudo apt install android-tools-adb"
    print_info "  - mosquitto: sudo apt install mosquitto-clients"
fi

# 验证依赖安装
print_step "验证系统依赖..."
if command_exists adb; then
    print_success "ADB已安装: $(adb version | head -1)"
else
    print_error "ADB未安装，请手动安装"
    exit 1
fi

if command_exists mosquitto_pub; then
    print_success "Mosquitto客户端已安装"
else
    print_warning "Mosquitto客户端未安装，MQTT功能将不可用"
fi

# 安装Python依赖
print_step "安装Python依赖..."
if [[ -f "requirements.txt" ]]; then
    print_info "安装requirements.txt中的依赖..."
    
    # 如果在虚拟环境中，使用虚拟环境的pip
    if [[ -n "$VENV_PYTHON" ]]; then
        print_info "使用虚拟环境安装依赖..."
        $VENV_PYTHON -m pip install -r requirements.txt
    else
        # 尝试常规安装，如果失败则提供建议
        if ! $PIP_CMD install -r requirements.txt 2>/dev/null; then
            print_warning "全局安装失败，建议使用虚拟环境："
            print_info "python3 -m venv .venv"
            print_info "source .venv/bin/activate"
            print_info "pip install -r requirements.txt"
            print_error "请设置虚拟环境后重新运行安装脚本"
            exit 1
        fi
    fi
    
    print_success "Python依赖安装完成"
else
    print_warning "requirements.txt未找到，跳过Python依赖安装"
fi

# 创建配置文件
print_step "创建配置文件..."
if [[ ! -f "config.yaml" ]]; then
    if [[ -f "config.yaml.example" ]]; then
        cp config.yaml.example config.yaml
        print_success "已创建config.yaml配置文件"
        print_warning "请根据需要修改config.yaml中的配置"
    else
        print_error "配置模板文件config.yaml.example未找到"
        exit 1
    fi
else
    print_info "配置文件config.yaml已存在"
fi

# 设置可执行权限
print_step "设置文件权限..."
if [[ -f "isg-guardian" ]]; then
    chmod +x isg-guardian
    print_success "已设置isg-guardian可执行权限"
else
    print_error "主程序文件isg-guardian未找到"
    exit 1
fi

# 创建全局命令链接
print_step "创建全局命令..."
LOCAL_BIN_DIR="$HOME/.local/bin"
mkdir -p "$LOCAL_BIN_DIR"

# 创建符号链接
GUARDIAN_PATH="$SCRIPT_DIR/isg-guardian"
GLOBAL_LINK="$LOCAL_BIN_DIR/isg-guardian"

if [[ -L "$GLOBAL_LINK" ]]; then
    rm "$GLOBAL_LINK"
fi

ln -s "$GUARDIAN_PATH" "$GLOBAL_LINK"
print_success "已创建全局命令链接: $GLOBAL_LINK"

# 更新PATH环境变量
print_step "配置环境变量..."
SHELL_RC=""
if [[ "$SHELL" == *"bash"* ]]; then
    SHELL_RC="$HOME/.bashrc"
elif [[ "$SHELL" == *"zsh"* ]]; then
    SHELL_RC="$HOME/.zshrc"
else
    SHELL_RC="$HOME/.profile"
fi

# 检查PATH是否已包含~/.local/bin
if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
    if [[ -f "$SHELL_RC" ]]; then
        echo '' >> "$SHELL_RC"
        echo '# iSG Guardian PATH' >> "$SHELL_RC"
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
        print_success "已更新$SHELL_RC，添加了PATH配置"
        print_warning "请运行 'source $SHELL_RC' 或重新打开终端以生效"
    else
        print_warning "无法自动配置PATH，请手动添加以下内容到你的shell配置文件:"
        print_info "export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi
else
    print_info "PATH已包含~/.local/bin目录"
fi

# 创建数据目录
print_step "创建数据目录..."
mkdir -p data/crash_logs data/exports
print_success "已创建数据目录"

# 检查Android设备连接（可选）
print_step "检查Android设备连接..."
if command_exists adb; then
    if adb devices 2>/dev/null | grep -q "device"; then
        print_success "检测到Android设备已连接"
    else
        print_warning "未检测到Android设备"
        print_info "请确保:"
        print_info "  1. Android设备已通过USB连接"
        print_info "  2. 已启用开发者选项"
        print_info "  3. 已启用USB调试"
        print_info "  4. 已授权此计算机的调试访问"
    fi
fi

# 更新shebang以使用正确的Python解释器
print_step "配置Python解释器..."
if [[ -n "$VENV_PYTHON" && -f "$VENV_PYTHON" ]]; then
    print_info "更新脚本以使用虚拟环境Python..."
    # 更新shebang行
    sed -i.bak "1s|.*|#!$VENV_PYTHON|" isg-guardian
    print_success "已配置使用虚拟环境Python: $VENV_PYTHON"
fi

# 测试安装
print_step "测试安装..."
if "$GUARDIAN_PATH" --version >/dev/null 2>&1; then
    print_success "主程序测试通过"
    
    # 显示版本信息
    VERSION_INFO=$("$GUARDIAN_PATH" --version 2>&1)
    print_info "$VERSION_INFO"
else
    print_error "主程序测试失败"
    print_info "请检查Python依赖是否正确安装"
    
    # 如果有虚拟环境，提供调试信息
    if [[ -n "$VENV_PYTHON" ]]; then
        print_info "尝试直接使用虚拟环境Python测试:"
        print_info "$VENV_PYTHON $GUARDIAN_PATH --version"
    fi
    exit 1
fi

# 显示完成信息
echo
print_message $GREEN "╔══════════════════════════════════════════════════════════╗"
print_message $GREEN "║                   🎉 安装完成！                         ║"
print_message $GREEN "╚══════════════════════════════════════════════════════════╝"
echo

print_message $CYAN "📋 下一步操作:"
echo
print_info "1. 配置应用设置（如需要）:"
print_message $NC "   nano config.yaml"
echo
print_info "2. 启动守护服务:"
print_message $NC "   isg-guardian start"
echo
print_info "3. 查看运行状态:"
print_message $NC "   isg-guardian status"
echo
print_info "4. 查看帮助信息:"
print_message $NC "   isg-guardian --help"
echo

print_message $CYAN "📊 管理命令:"
print_message $NC "   isg-guardian start      # 启动服务"
print_message $NC "   isg-guardian stop       # 停止服务"
print_message $NC "   isg-guardian restart    # 重启服务"
print_message $NC "   isg-guardian status     # 查看状态"
print_message $NC "   isg-guardian logs       # 查看日志"
echo

print_message $CYAN "📁 项目目录: $SCRIPT_DIR"
print_message $CYAN "📝 配置文件: $SCRIPT_DIR/config.yaml"
print_message $CYAN "📊 数据目录: $SCRIPT_DIR/data/"
echo

if [[ ! "$PATH" =~ "$HOME/.local/bin" ]]; then
    print_warning "重要提醒: 请重新加载shell配置或重新打开终端"
    print_info "运行命令: source $SHELL_RC"
fi

print_success "iSG Guardian 安装完成！"