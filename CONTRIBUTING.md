# 贡献指南

感谢您对 Sersync Plus 项目的关注！我们欢迎各种形式的贡献。

## 🤝 如何贡献

### 报告问题
- 使用 [GitHub Issues](https://github.com/0x5c0f/sersync-plus/issues) 报告 bug
- 搜索现有 issue，避免重复报告
- 提供详细的复现步骤和环境信息

### 提出功能请求
- 在 Issues 中使用 "enhancement" 标签
- 详细描述功能需求和使用场景
- 说明为什么这个功能对项目有价值

### 提交代码
1. Fork 项目到您的 GitHub 账户
2. 创建功能分支：`git checkout -b feature/amazing-feature`
3. 提交更改：`git commit -m 'Add amazing feature'`
4. 推送到分支：`git push origin feature/amazing-feature`
5. 创建 Pull Request

## 🛠️ 开发环境设置

### 前置要求
- Python 3.9+
- Poetry
- Git

### 环境搭建
```bash
# 克隆项目
git clone https://github.com/0x5c0f/sersync-plus.git
cd sersync-plus

# 安装依赖
poetry install --with dev

# 激活虚拟环境
poetry shell

# 运行测试
pytest

# 代码质量检查
ruff check .
mypy sersync/
```

## 📝 代码规范

### Python 代码风格
- 使用 [ruff](https://github.com/astral-sh/ruff) 进行代码检查
- 使用 [black](https://github.com/psf/black) 进行代码格式化
- 遵循 [PEP 8](https://www.python.org/dev/peps/pep-0008/) 规范

### 类型提示
- 所有公共 API 必须有类型提示
- 使用 [mypy](http://mypy-lang.org/) 进行类型检查

### 文档字符串
- 所有公共函数和类必须有文档字符串
- 使用 Google 风格的文档字符串

```python
def sync_file(file_path: str, remote_target: str) -> bool:
    """同步单个文件到远程目标.

    Args:
        file_path: 要同步的文件路径
        remote_target: 远程目标地址

    Returns:
        同步是否成功

    Raises:
        SyncError: 同步失败时抛出
    """
    pass
```

## 🧪 测试

### 运行测试
```bash
# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_sync_engine.py

# 运行覆盖率测试
pytest --cov=sersync

# 生成 HTML 覆盖率报告
pytest --cov=sersync --cov-report=html
```

### 测试要求
- 新功能必须包含测试
- 测试覆盖率不低于 80%
- 核心模块测试覆盖率不低于 90%

### 测试类型
- **单元测试**：测试单个函数或方法
- **集成测试**：测试模块间的交互
- **端到端测试**：测试完整的工作流程

## 📋 提交规范

### 提交消息格式
```
<类型>(<范围>): <描述>

<详细说明>

<脚注>
```

### 类型
- `feat`: 新功能
- `fix`: 修复 bug
- `docs`: 文档更新
- `style`: 代码格式化
- `refactor`: 代码重构
- `test`: 测试相关
- `chore`: 构建过程或辅助工具的变动

### 示例
```
feat(sync): 添加双向同步支持

- 实现基于元数据的冲突检测
- 添加多种冲突解决策略
- 支持自定义元数据存储路径

Closes #123
```

## 🔍 代码审查

### Pull Request 要求
- 清晰的标题和描述
- 关联相关的 Issue
- 通过所有 CI 检查
- 至少一个维护者的审查

### 审查清单
- [ ] 代码符合项目规范
- [ ] 包含适当的测试
- [ ] 文档已更新
- [ ] 向后兼容性
- [ ] 性能影响评估

## 🏗️ 项目结构

```
sersync-plus/
├── sersync/              # 主要代码
│   ├── core/            # 核心引擎
│   ├── config/          # 配置管理
│   ├── web/             # Web 界面
│   ├── notification/    # 通知系统
│   ├── bidirectional/   # 双向同步
│   └── utils/           # 工具模块
├── tests/               # 测试代码
├── docs/                # 文档
├── examples/            # 示例配置
└── pyproject.toml       # 项目配置
```

## 📚 开发指南

### 添加新功能
1. 在 `sersync/` 下创建相应模块
2. 编写单元测试
3. 更新配置模型（如需要）
4. 更新文档
5. 添加示例配置

### 修复 Bug
1. 创建复现测试
2. 修复问题
3. 确保测试通过
4. 更新相关文档

### 性能优化
1. 添加性能基准测试
2. 实施优化
3. 验证性能提升
4. 更新性能文档

## 🎯 优先级

### 高优先级
- 安全问题修复
- 数据丢失 bug 修复
- 性能严重问题
- 兼容性问题

### 中优先级
- 新功能开发
- 用户体验改进
- 文档完善
- 测试覆盖率提升

### 低优先级
- 代码重构
- 依赖更新
- 工具链改进

## 📞 获取帮助

### 沟通渠道
- [GitHub Discussions](https://github.com/0x5c0f/sersync-plus/discussions) - 一般讨论
- [GitHub Issues](https://github.com/0x5c0f/sersync-plus/issues) - Bug 报告和功能请求
- 邮件：i@0x5c0f.cc - 私人问题

### 资源
- [项目文档](docs/)
- [API 参考](docs/api.md)
- [配置指南](docs/configuration.md)
- [故障排查](docs/troubleshooting.md)

## 🙏 致谢

感谢所有为 Sersync Plus 做出贡献的开发者！

### 贡献者
- 您的名字将出现在这里

### 特别感谢
- 原版 sersync 项目的开发者
- 所有提供反馈和建议的用户
- 开源社区的支持

---

再次感谢您的贡献！让我们一起让 Sersync Plus 变得更好！