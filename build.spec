# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 配置文件 - Sersync Plus
用于将 Python 项目打包为独立的二进制文件
"""

import os
import sys
from pathlib import Path

# 项目根目录
project_root = Path(__file__).parent
sersync_path = project_root / "sersync"

# 收集数据文件
def collect_data_files():
    """收集需要包含的数据文件"""
    data_files = []
    
    # Web 静态文件
    web_static = sersync_path / "web" / "static"
    if web_static.exists():
        for static_file in web_static.rglob("*"):
            if static_file.is_file():
                rel_path = static_file.relative_to(sersync_path)
                data_files.append((str(static_file), f"sersync/{rel_path}"))
    
    # 配置模板文件
    examples_dir = project_root / "examples"
    if examples_dir.exists():
        for example_file in examples_dir.glob("*.xml"):
            data_files.append((str(example_file), "examples"))
        for example_file in examples_dir.glob("*.yml"):
            data_files.append((str(example_file), "examples"))
    
    return data_files

# 隐藏导入（PyInstaller 可能无法自动检测的模块）
hidden_imports = [
    # 核心模块
    'sersync.cli',
    'sersync.core.engine',
    'sersync.core.sync_engine',
    'sersync.core.event_queue',
    'sersync.core.monitor',
    'sersync.core.faillog_executor',
    
    # 配置模块
    'sersync.config.parser',
    'sersync.config.models',
    
    # Web 模块
    'sersync.web',
    'sersync.web.routes.sync_history',
    'sersync.web.database',
    'sersync.web.cache',
    
    # 双向同步
    'sersync.bidirectional.metadata_manager',
    'sersync.bidirectional.sync_engine',
    
    # 通知系统
    'sersync.notification',
    
    # 工具模块
    'sersync.utils',
    
    # 第三方依赖
    'uvicorn',
    'fastapi',
    'sqlalchemy',
    'aiosqlite',
    'apprise',
    'structlog',
    'watchdog',
    'click',
    'pydantic',
    'tenacity',
    'psutil',
    'bcrypt',
    'websockets',
    'jinja2',
]

# Linux 特定模块
if sys.platform.startswith('linux'):
    hidden_imports.append('pyinotify')

# 分析配置
a = Analysis(
    ['sersync/cli.py'],  # 入口点
    pathex=[str(project_root)],
    binaries=[],
    datas=collect_data_files(),
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的模块以减小体积
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'jupyter',
        'IPython',
        'pytest',
        'mypy',
        'ruff',
        'black',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# 去重和优化
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# 单文件可执行程序配置
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='sersync-plus',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # 启用 UPX 压缩（如果可用）
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 控制台应用
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 可以添加图标文件路径
)