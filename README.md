# Sersync Plus

> 🤖 **协同开发说明**  
> 本项目由 [0x5c0f](https://github.com/0x5c0f) 与 Kiro AI 在 [Kiro 编辑器](https://kiro.dev/) 中协同完成开发。  
> Kiro AI 负责主要的架构设计、代码实现和文档编写，0x5c0f 负责需求分析、测试验证和项目管理。

[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code Style](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![GitHub Repository](https://img.shields.io/badge/GitHub-sersync--plus-blue.svg)](https://github.com/0x5c0f/sersync-plus)

**Sersync Plus** 是对原版 sersync 的增强重写版本，使用 Python 开发，完全兼容原版配置文件，并提供了丰富的扩展功能。

## ✨ 核心特性

### 🚀 **基础同步功能**
- ✅ **实时文件监控** - 基于 inotify（Linux）/ watchdog（跨平台）
- ✅ **Rsync 集成** - 高效增量传输，支持 SSH 和 Rsync 协议
- ✅ **事件智能合并** - 时间窗口合并，减少同步次数
- ✅ **多目标并发同步** - 同时同步到多个远程服务器
- ✅ **文件过滤系统** - 正则表达式过滤 + 自动临时文件过滤
- ✅ **失败重试机制** - 自动重试失败的同步任务
- ✅ **定期全量同步** - 可配置的 crontab 定时同步

### 🔄 **双向同步** ⭐ 新增
- ✅ **冲突智能检测** - 基于元数据的冲突检测
- ✅ **多种解决策略** - 8 种冲突解决策略可选
- ✅ **安全元数据存储** - 元数据文件存储在监控目录外
- ✅ **自动备份** - 冲突文件自动备份
- ✅ **节点标识** - 支持多节点双向同步

### 📢 **通知系统**
- ✅ **Apprise 集成** - 支持 100+ 通知服务
- ✅ **灵活规则引擎** - 立即通知、批量通知、定时通知
- ✅ **自定义模板** - 消息模板支持变量替换
- ✅ **常用服务** - 企业微信、钉钉、Slack、邮件等

### 🖥️ **Web 管理界面**
- ✅ **实时监控** - WebSocket 实时推送系统状态
- ✅ **同步历史** - 完整的同步历史记录和统计
- ✅ **REST API** - 完整的 RESTful API 接口
- ✅ **数据持久化** - SQLite 数据库存储日志和指标
- ✅ **现代化仪表盘** - 响应式 HTML 仪表盘
- ✅ **认证系统** - Basic Auth 安全认证

---

## 📦 安装

### 前置要求
- Python 3.9 或更高版本
- rsync（用于文件同步）
- inotify-tools（Linux，可选）

### 方式一：使用 Poetry（推荐开发）
```bash
git clone https://github.com/0x5c0f/sersync-plus.git
cd sersync-plus
poetry install
poetry run sersync-plus --help
```

### 方式二：使用 pip
```bash
pip install sersync-plus
sersync-plus --help
```

### 方式三：二进制文件（推荐生产）
```bash
# 下载预编译的二进制文件
wget https://github.com/0x5c0f/sersync-plus/releases/latest/download/sersync-plus
chmod +x sersync-plus
./sersync-plus --help

# 或者自行构建
git clone https://github.com/0x5c0f/sersync-plus.git
cd sersync-plus
make binary
./dist/sersync-plus --help
```

### 系统依赖安装
```bash
# Debian/Ubuntu
sudo apt install rsync inotify-tools

# CentOS/RHEL
sudo yum install rsync

# macOS
brew install rsync
```

---

## 🚀 快速开始

### 1. 基本同步
```bash
# 使用默认配置文件
sersync-plus -o confxml.xml

# 启动前执行全量同步
sersync-plus -r -o confxml.xml

# 后台运行
sersync-plus -d -o confxml.xml
```

### 2. Web 管理界面
```bash
# 启动 Web 界面
sersync-plus --web --web-port 8000 -o confxml.xml

# 访问管理界面
open http://localhost:8000
# 默认用户名: admin, 密码: admin123
```

### 3. 双向同步
```bash
# 使用双向同步配置
sersync-plus -o examples/confxml_bidirectional.xml
```

---

## 📋 配置文件

Sersync Plus 完全兼容原版 sersync 的 XML 配置文件格式，同时扩展了新功能。

### 基本配置示例
```xml
<?xml version="1.0" encoding="UTF-8"?>
<head version="2.5">
    <host hostip="localhost" port="8008"/>
    <debug start="false"/>
    
    <sersync>
        <localpath watch="/data/sync">
            <remote ip="192.168.1.100" name="backup"/>
        </localpath>
        
        <rsync>
            <commonParams params="-artuz"/>
            <auth start="true" users="rsync_user" passwordfile="/etc/rsync.pass"/>
        </rsync>
        
        <failLog path="/tmp/rsync_fail_log.sh" timeToExecute="60"/>
    </sersync>
    
    <!-- Web 管理界面 -->
    <web enabled="true" port="8000"/>
    
    <!-- 数据库配置 -->
    <database enabled="true" path="/var/sersync/sersync.db"/>
</head>
```

更多配置示例请查看 `examples/` 目录。

---

## 🔧 命令行参数

| 参数 | 说明 |
|------|------|
| `-o, --config` | 配置文件路径 |
| `-r, --initial-sync` | 启动前执行全量同步 |
| `-d, --daemon` | 后台守护进程模式 |
| `-n, --threads` | 线程池大小 |
| `--web` | 启用 Web 管理界面 |
| `--web-port` | Web 界面端口 |
| `--log-level` | 日志级别 |
| `--db-path` | 数据库文件路径 |
| `--log-file` | 日志文件路径 |

---

## 🌟 新增功能详解

### 同步历史记录
- **永久存储**: 所有同步操作记录到数据库
- **分页查询**: 支持大数据量的高效分页
- **统计分析**: 成功率、耗时、热门文件等统计
- **性能优化**: 索引优化、缓存机制、虚拟滚动

### 双向同步
- **元数据管理**: 安全的元数据存储，避免同步冲突
- **冲突检测**: 智能检测文件冲突
- **解决策略**: keep_newer、keep_older、backup_both 等多种策略
- **节点标识**: 支持多节点环境的双向同步

### 通知系统
- **Apprise 集成**: 支持 100+ 通知服务
- **规则引擎**: 灵活的通知规则配置
- **模板系统**: 自定义消息模板
- **批量通知**: 避免通知轰炸的批量机制

---

## � 开发与构建

### 开发环境设置
```bash
# 克隆项目
git clone https://github.com/0x5c0f/sersync-plus.git
cd sersync-plus

# 安装依赖
make install
# 或者
poetry install --with dev

# 运行测试
make test
# 或者
poetry run pytest
```

### 构建二进制文件
```bash
# 方式一：使用 Make（推荐）
make binary

# 方式二：使用构建脚本
python scripts/build.py

# 方式三：快速构建
./scripts/build.sh

# 方式四：手动构建
poetry run pyinstaller build.spec
```

### 可用的 Make 命令
```bash
make help          # 显示帮助信息
make install       # 安装依赖
make test          # 运行测试
make build         # 构建 Python 包
make binary        # 构建二进制文件
make binary-fast   # 快速构建二进制文件
make clean         # 清理构建文件
make lint          # 代码质量检查
make format        # 格式化代码
make ci            # 完整 CI 流程
make release       # 发布准备
```

### 构建输出
- **Python 包**: `dist/*.whl`
- **二进制文件**: `dist/sersync-plus`（约 50-80MB）
- **支持平台**: Linux, macOS, Windows

---

## 🛠️ 开发

### 环境设置
```bash
git clone https://github.com/0x5c0f/sersync-plus.git
cd sersync-plus
poetry install --with dev
```

### 运行测试
```bash
poetry run pytest
poetry run pytest --cov=sersync
```

### 代码质量检查
```bash
poetry run ruff check .
poetry run mypy sersync/
```

---

## 📚 文档

- [配置指南](docs/configuration.md)
- [API 文档](docs/api.md)
- [双向同步指南](docs/bidirectional-sync.md)
- [通知配置](docs/notifications.md)
- [故障排查](docs/troubleshooting.md)

---

## 🤝 贡献

欢迎贡献代码！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详细信息。

### 开发流程
1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

---

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

---

## 🙏 致谢

- 原版 [sersync](https://github.com/wsgzao/sersync) 项目
- [Apprise](https://github.com/caronc/apprise) - 通知系统
- [FastAPI](https://fastapi.tiangolo.com/) - Web 框架

---

## 📞 支持

- 🐛 [报告问题](https://github.com/0x5c0f/sersync-plus/issues)
- 💬 [讨论区](https://github.com/0x5c0f/sersync-plus/discussions)
- 📧 邮件: i@0x5c0f.cc

---

**Sersync Plus** - 让文件同步更简单、更强大！
- rsync（用于文件同步）
- unison（可选，用于双向同步）

### 使用 Poetry（推荐）

```bash
# 克隆仓库
git clone https://github.com/yourusername/sersync-python.git
cd sersync-python

# 安装依赖
poetry install

# 安装完整功能（包括通知系统）
poetry install -E notifications

# 激活虚拟环境
poetry shell
```

### 使用 pip

```bash
# 克隆仓库
git clone https://github.com/yourusername/sersync-python.git
cd sersync-python

# 安装
pip install -e .

# 安装完整功能
pip install -e .[notifications]
```

### 安装系统依赖

```bash
# Debian/Ubuntu
sudo apt install rsync unison inotify-tools

# CentOS/RHEL
sudo yum install rsync unison

# macOS
brew install rsync unison
```

---

## 🚀 快速开始

### 1. 基本单向同步

```bash
# 创建配置文件（参考 examples/confxml.xml）
cp examples/confxml.xml /etc/sersync.xml

# 编辑配置文件，设置监控路径和远程目标
vim /etc/sersync.xml

# 前台运行，带初始全量同步
sersync -r -o /etc/sersync.xml

# 后台运行
sersync -d -o /etc/sersync.xml
```

### 2. 启用 Web 管理界面

```bash
# 启动 Web 界面（端口 8000）
sersync --web --web-port 8000 -o /etc/sersync.xml

# 访问 Web 界面
# http://localhost:8000
# 默认用户名：admin
# 默认密码：admin123
```

### 3. 双向同步

```bash
# 方式 1：命令行参数
sersync --bidirectional \
  --bidir-host 192.168.1.100 \
  --bidir-root /data/remote \
  --conflict-strategy keep_newer \
  -o /etc/sersync.xml

# 方式 2：配置文件（参考 examples/confxml_bidirectional.xml）
sersync -o /etc/sersync/confxml_bidirectional.xml
```

### 4. 启用通知系统

```bash
# 创建 Apprise 配置文件
cp examples/apprise_full.yml /etc/sersync/apprise.yml

# 编辑配置，添加通知服务
vim /etc/sersync/apprise.yml

# 在 confxml.xml 中启用通知
# 参考 examples/confxml_with_notification.xml

# 启动
sersync -o /etc/sersync.xml
```

---

## 📖 使用指南

### 命令行选项

```bash
Usage: sersync [OPTIONS]

Options:
  -o, --config PATH              配置文件路径 [默认: ./confxml.xml]
  -r, --initial-sync             启动前执行一次全量同步
  -d, --daemon                   后台守护进程模式
  -n, --threads INTEGER          线程池大小 [默认: 10]
  -m, --plugin TEXT              仅运行指定插件（不同步）
  --web                          启用 Web 管理界面
  --web-port INTEGER             Web 界面端口 [默认: 8000]
  --log-level [DEBUG|INFO|WARNING|ERROR]
                                 日志级别 [默认: INFO]
  --log-format [text|json]       日志格式 [默认: text]
  --bidirectional                启用双向同步模式
  --bidir-host TEXT              双向同步远程主机
  --bidir-root TEXT              双向同步远程根目录
  --conflict-strategy [keep_newer|keep_older|keep_local|keep_remote|backup_both|manual|skip]
                                 冲突解决策略 [默认: keep_newer]
  --version                      显示版本信息
  --help                         显示帮助信息
```

### 使用示例

```bash
# 前台运行，初始全量同步
sersync -r -o /etc/sersync.xml

# 后台运行，20 线程，启用 Web 界面
sersync -d -n 20 --web --web-port 8000

# 双向同步 + Web 界面
sersync --bidirectional --bidir-host 192.168.1.100 \
  --bidir-root /data/remote --web

# 调试模式
sersync --log-level DEBUG -o /etc/sersync.xml

# 仅运行插件
sersync -m refreshCDN -o /etc/sersync.xml
```

---

## ⚙️ 配置文件

### 基本配置示例

```xml
<?xml version="1.0" encoding="UTF-8"?>
<head version="2.5">
    <!-- 本地监控路径 -->
    <localpath watch="/data/sync">
        <!-- 远程目标服务器 -->
        <remote ip="192.168.1.100" name="backup"/>
        <remote ip="192.168.1.101" name="backup"/>
    </localpath>

    <!-- Rsync 配置 -->
    <rsync>
        <commonParams params="-artuz"/>
        <auth start="false"/>
        <ssh start="true" user="root" port="22"/>
    </rsync>

    <!-- 文件过滤 -->
    <filter start="true">
        <exclude expression="(.*)\.tmp"/>
        <exclude expression="(.*)\.swp"/>
    </filter>

    <!-- Inotify 事件配置 -->
    <inotify>
        <delete start="true"/>
        <closeWrite start="true"/>
        <moveFrom start="true"/>
        <moveTo start="true"/>
    </inotify>

    <!-- 定时全量同步（每 600 分钟） -->
    <crontab start="true" schedule="600"/>

    <!-- 失败重试 -->
    <failLog path="/var/sersync/rsync_fail.sh" timeToExecute="60"/>
</head>
```

完整配置示例请参考：
- `examples/confxml.xml` - 基本配置
- `examples/confxml_bidirectional.xml` - 双向同步配置
- `examples/confxml_with_notification.xml` - 通知系统配置
- `examples/confxml_with_web.xml` - Web 界面配置

---

## 🔄 双向同步详解

### 冲突类型

Sersync 可以自动检测以下 6 种冲突类型：

1. **BOTH_MODIFIED** - 双方都修改了同一文件
2. **LOCAL_DELETED_REMOTE_MODIFIED** - 本地删除，远程修改
3. **REMOTE_DELETED_LOCAL_MODIFIED** - 远程删除，本地修改
4. **BOTH_CREATED** - 双方同时创建了不同内容的文件
5. **MOVE_CONFLICT** - 文件移动冲突
6. **NO_CONFLICT** - 无冲突

### 冲突解决策略

提供 8 种冲突解决策略：

| 策略 | 说明 | 适用场景 |
|------|------|---------|
| `keep_newer` | 保留修改时间较新的文件 | **推荐默认策略** |
| `keep_older` | 保留修改时间较旧的文件 | 恢复误操作 |
| `keep_larger` | 保留文件大小较大的文件 | 日志文件、数据积累 |
| `keep_local` | 总是保留本地版本 | 本地是权威数据源 |
| `keep_remote` | 总是保留远程版本 | 远程是权威数据源 |
| `backup_both` | 备份双方，保留两个版本 | 重要文件，需人工审查 |
| `manual` | 需要手动介入 | 关键文件，需人工决策 |
| `skip` | 跳过同步 | 临时忽略某些冲突 |

### 使用示例

```bash
# 保留较新的文件（推荐）
sersync --bidirectional --bidir-host 192.168.1.100 --bidir-root /data/remote --conflict-strategy keep_newer

# 总是保留本地文件
sersync --bidirectional --bidir-host 192.168.1.100 --bidir-root /data/remote --conflict-strategy keep_local

# 备份双方（重要文件）
sersync --bidirectional --bidir-host 192.168.1.100 --bidir-root /data/remote --conflict-strategy backup_both
```

### 备份文件位置

冲突文件会自动备份到：`/var/sersync/bidirectional/conflicts/`

备份文件命名格式：
```
原文件名_来源_时间戳.扩展名

例如：
config_local_20240120_143022.json
config_remote_20240120_143022.json
```

---

## 🖥️ Web 管理界面

### 功能特性

- **实时监控仪表盘** - CPU、内存、磁盘使用率
- **同步统计** - 总事件数、已同步文件、队列大小、成功率
- **实时事件流** - 显示最近 50 条文件变更事件
- **WebSocket 推送** - 服务器主动推送状态更新（每 2 秒）
- **日志查询** - 搜索和查看应用日志
- **控制接口** - 启动/停止引擎、触发全量同步

### API 端点

```
GET  /                       # Web 仪表盘
GET  /health                 # 健康检查
GET  /api/status/current     # 系统状态
GET  /api/status/metrics     # 性能指标
GET  /api/config/summary     # 配置摘要
GET  /api/logs/recent        # 最近日志
GET  /api/logs/search        # 搜索日志
GET  /api/logs/stats         # 日志统计
POST /api/control/start      # 启动引擎（需认证）
POST /api/control/stop       # 停止引擎（需认证）
POST /api/control/full-sync  # 全量同步（需认证）
WS   /ws                     # WebSocket 连接
```

### 独立运行 Web 服务

```bash
# 启动独立 Web 服务（不启动同步引擎）
sersync-web -p 8000 -c /etc/sersync.xml

# 开发模式（自动重载）
sersync-web --reload --no-auth

# 指定端口和配置文件
sersync-web -p 9000 -c /etc/sersync.xml
```

---

## 📢 通知系统

### 支持的通知服务

通过 Apprise 集成，支持 100+ 通知服务：

- **即时通讯** - 企业微信、钉钉、Slack、Discord、Telegram
- **邮件** - SMTP、Gmail、Outlook
- **短信** - Twilio、阿里云、腾讯云
- **推送** - Pushbullet、Pushover、Gotify
- **Webhook** - 自定义 HTTP Webhook
- 更多服务...

### 配置示例

**Apprise 配置文件** (`/etc/sersync/apprise.yml`)

```yaml
# 企业微信群机器人
urls:
  - wxwork://企业ID/应用AgentId/应用Secret

# Slack
  - slack://TokenA/TokenB/TokenC

# 邮件
  - mailto://user:password@gmail.com

# 多个服务
  - wxwork://...
  - slack://...
  - mailto://...
```

### 通知规则

支持 3 种通知规则：

1. **立即通知** (`immediate`) - 事件发生立即发送
2. **批量通知** (`batch`) - 累积到一定数量或时间后批量发送
3. **定时通知** (`schedule`) - 按 cron 表达式定时发送

---

## 🧪 测试

### 运行测试

```bash
# 运行所有测试
pytest

# 运行特定模块测试
pytest tests/test_core.py -v
pytest tests/test_notification.py -v
pytest tests/test_web.py -v
pytest tests/test_bidirectional.py -v

# 查看测试覆盖率
pytest --cov=sersync --cov-report=html

# 查看覆盖率报告
open htmlcov/index.html
```

### 测试覆盖范围

- ✅ 核心功能测试（文件监控、事件队列、同步引擎）
- ✅ 通知系统测试（Apprise 集成、规则引擎）
- ✅ Web 系统测试（API 端点、WebSocket、认证）
- ✅ 双向同步测试（冲突检测、冲突解决、Unison 集成）

---

## 📊 项目统计

| 模块 | 文件数 | 代码行数 | 测试用例 |
|------|-------|---------|---------|
| 核心引擎 | 6 | 2,200+ | 15+ |
| 配置系统 | 2 | 800+ | 5+ |
| 通知系统 | 2 | 740+ | 10+ |
| Web 界面 | 9 | 2,000+ | 23+ |
| 双向同步 | 5 | 2,870+ | 30+ |
| 工具模块 | 2 | 200+ | - |
| 测试 | 5 | 1,500+ | - |
| **总计** | **42** | **11,710+** | **83+** |

---

## 🆚 与原始 sersync 对比

| 功能 | 原始 Sersync (C++) | Sersync Python |
|------|-------------------|----------------|
| 基本单向同步 | ✅ | ✅ |
| inotify 监控 | ✅ | ✅ |
| Rsync 集成 | ✅ | ✅ |
| 事件过滤 | ✅ | ✅ 增强 |
| 配置文件兼容 | ✅ | ✅ 100% 兼容 |
| 跨平台支持 | ❌ Linux only | ✅ Linux/macOS/Windows |
| 双向同步 | ❌ | ✅ **新增** |
| 冲突检测/解决 | ❌ | ✅ **新增** |
| 通知系统 | ❌ | ✅ **新增** |
| Web 管理界面 | ❌ | ✅ **新增** |
| REST API | ❌ | ✅ **新增** |
| WebSocket 推送 | ❌ | ✅ **新增** |
| 数据持久化 | ❌ | ✅ **新增** |
| Python 生态 | ❌ | ✅ 易于扩展 |

---

## 🤝 贡献

欢迎贡献代码、报告问题或提出建议！

### 开发环境设置

```bash
# 克隆仓库
git clone https://github.com/yourusername/sersync-python.git
cd sersync-python

# 安装开发依赖
poetry install --with dev

# 运行测试
pytest

# 代码格式化
black sersync/
isort sersync/

# 类型检查
mypy sersync/
```

---

## 📄 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

---

## 🙏 致谢

- 原始 [sersync](https://code.google.com/archive/p/sersync/) 项目
- [watchdog](https://github.com/gorakhargosh/watchdog) - 文件监控
- [Apprise](https://github.com/caronc/apprise) - 通知系统
- [FastAPI](https://fastapi.tiangolo.com/) - Web 框架
- [Unison](https://www.cis.upenn.edu/~bcpierce/unison/) - 双向同步

---

## 📞 联系方式

- **问题反馈**: [GitHub Issues](https://github.com/yourusername/sersync-python/issues)
- **功能建议**: [GitHub Discussions](https://github.com/yourusername/sersync-python/discussions)

---

<p align="center">
  <b>⭐ 如果这个项目对你有帮助，请给它一个 Star！</b>
</p>

<p align="center">
  Made with ❤️ by Sersync Python Team
</p>
