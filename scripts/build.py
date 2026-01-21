#!/usr/bin/env python3
"""
Sersync Plus 构建脚本
用于将项目打包为二进制文件
"""

import os
import sys
import shutil
import subprocess
import platform
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist"
SPEC_FILE = PROJECT_ROOT / "build.spec"

def clean_build():
    """清理构建目录"""
    print("🧹 清理构建目录...")
    
    for dir_path in [BUILD_DIR, DIST_DIR]:
        if dir_path.exists():
            shutil.rmtree(dir_path)
            print(f"   删除: {dir_path}")
    
    # 清理 __pycache__
    for pycache in PROJECT_ROOT.rglob("__pycache__"):
        shutil.rmtree(pycache)
        print(f"   删除: {pycache}")

def install_dependencies():
    """安装构建依赖"""
    print("📦 安装构建依赖...")
    
    try:
        # 检查是否在 Poetry 环境中
        result = subprocess.run(["poetry", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print("   使用 Poetry 安装依赖...")
            subprocess.run(["poetry", "install", "--with", "dev"], check=True)
        else:
            print("   使用 pip 安装 PyInstaller...")
            subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ 依赖安装失败: {e}")
        sys.exit(1)

def build_binary():
    """构建二进制文件"""
    print("🔨 开始构建二进制文件...")
    
    # 构建命令
    cmd = [
        "pyinstaller",
        "--clean",  # 清理临时文件
        "--noconfirm",  # 不询问覆盖
        str(SPEC_FILE)
    ]
    
    print(f"   执行命令: {' '.join(cmd)}")
    
    try:
        # 在项目根目录执行
        result = subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)
        print("✅ 构建成功!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 构建失败: {e}")
        return False

def test_binary():
    """测试构建的二进制文件"""
    print("🧪 测试二进制文件...")
    
    # 查找生成的可执行文件
    if platform.system() == "Windows":
        binary_name = "sersync-plus.exe"
    else:
        binary_name = "sersync-plus"
    
    binary_path = DIST_DIR / binary_name
    
    if not binary_path.exists():
        print(f"❌ 找不到二进制文件: {binary_path}")
        return False
    
    # 测试 --help 命令
    try:
        result = subprocess.run([str(binary_path), "--help"], 
                              capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and "Sersync Plus" in result.stdout:
            print("✅ 二进制文件测试通过!")
            return True
        else:
            print(f"❌ 二进制文件测试失败: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("❌ 二进制文件测试超时")
        return False
    except Exception as e:
        print(f"❌ 二进制文件测试异常: {e}")
        return False

def show_build_info():
    """显示构建信息"""
    print("\n📊 构建信息:")
    
    # 查找生成的文件
    if DIST_DIR.exists():
        for file_path in DIST_DIR.iterdir():
            if file_path.is_file():
                size_mb = file_path.stat().st_size / (1024 * 1024)
                print(f"   📁 {file_path.name}: {size_mb:.1f} MB")
    
    print(f"\n📍 构建输出目录: {DIST_DIR}")
    print(f"🖥️  系统平台: {platform.system()} {platform.machine()}")
    print(f"🐍 Python 版本: {sys.version}")

def main():
    """主函数"""
    print("🚀 Sersync Plus 二进制构建工具")
    print("=" * 50)
    
    # 检查是否在项目根目录
    if not (PROJECT_ROOT / "pyproject.toml").exists():
        print("❌ 请在项目根目录运行此脚本")
        sys.exit(1)
    
    # 构建步骤
    steps = [
        ("清理构建目录", clean_build),
        ("安装构建依赖", install_dependencies),
        ("构建二进制文件", build_binary),
        ("测试二进制文件", test_binary),
    ]
    
    for step_name, step_func in steps:
        print(f"\n📋 {step_name}")
        print("-" * 30)
        
        if step_func == build_binary or step_func == test_binary:
            # 这些步骤有返回值
            if not step_func():
                print(f"\n❌ 构建失败于步骤: {step_name}")
                sys.exit(1)
        else:
            step_func()
    
    # 显示构建结果
    show_build_info()
    
    print("\n🎉 构建完成!")
    print("\n💡 使用方法:")
    print(f"   ./dist/sersync-plus --help")
    print(f"   ./dist/sersync-plus --web -o examples/confxml.xml")

if __name__ == "__main__":
    main()