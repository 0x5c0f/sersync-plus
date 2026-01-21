#!/bin/bash
# Sersync Plus 快速构建脚本

set -e  # 遇到错误立即退出

echo "🚀 Sersync Plus 二进制构建"
echo "=========================="

# 检查是否在项目根目录
if [ ! -f "pyproject.toml" ]; then
    echo "❌ 请在项目根目录运行此脚本"
    exit 1
fi

# 清理构建目录
echo "🧹 清理构建目录..."
rm -rf build/ dist/ *.spec

# 安装 PyInstaller（如果未安装）
echo "📦 检查 PyInstaller..."
if ! command -v pyinstaller &> /dev/null; then
    echo "   安装 PyInstaller..."
    pip install pyinstaller
fi

# 构建二进制文件
echo "🔨 构建二进制文件..."
pyinstaller \
    --onefile \
    --name sersync-plus \
    --add-data "examples:examples" \
    --add-data "sersync/web/static:sersync/web/static" \
    --hidden-import sersync.cli \
    --hidden-import sersync.core.engine \
    --hidden-import sersync.web \
    --hidden-import uvicorn \
    --hidden-import fastapi \
    --hidden-import sqlalchemy \
    --hidden-import apprise \
    --console \
    sersync/cli.py

# 测试构建结果
echo "🧪 测试二进制文件..."
if [ -f "dist/sersync-plus" ]; then
    ./dist/sersync-plus --help > /dev/null
    echo "✅ 构建成功!"
    
    # 显示文件信息
    echo "📊 构建信息:"
    ls -lh dist/sersync-plus
    echo ""
    echo "💡 使用方法:"
    echo "   ./dist/sersync-plus --help"
    echo "   ./dist/sersync-plus --web -o examples/confxml.xml"
else
    echo "❌ 构建失败，找不到二进制文件"
    exit 1
fi