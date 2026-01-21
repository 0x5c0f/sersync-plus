# 配置示例

本目录包含了 Sersync Plus 的各种配置示例，帮助您快速上手和了解不同功能的配置方法。

## 📁 文件说明

### XML 配置文件

| 文件名 | 说明 | 适用场景 |
|--------|------|----------|
| `confxml_minimal.xml` | 最小配置示例 | 快速测试、简单同步 |
| `confxml.xml` | 完整功能配置 | 生产环境、全功能使用 |
| `confxml_bidirectional.xml` | 双向同步配置 | 双向文件同步场景 |

### 通知配置文件

| 文件名 | 说明 | 适用场景 |
|--------|------|----------|
| `apprise.yml` | 通知服务配置 | 配置各种通知平台 |

## 🚀 快速开始

### 1. 基本同步
```bash
# 使用最小配置
sersync-plus -o examples/confxml_minimal.xml

# 使用完整配置
sersync-plus -o examples/confxml.xml
```

### 2. Web 管理界面
```bash
# 启动 Web 界面
sersync-plus --web -o examples/confxml.xml

# 访问管理界面
open http://localhost:8000
```

### 3. 双向同步
```bash
# 使用双向同步配置
sersync-plus -o examples/confxml_bidirectional.xml
```

## ⚙️ 配置说明

### 最小配置 (`confxml_minimal.xml`)

包含运行 Sersync Plus 所需的最基本设置：
- 基础文件监控
- 单个远程目标
- 简单的文件过滤
- 失败重试机制

**适用场景**：
- 快速测试和验证
- 简单的单向同步
- 学习和了解基本配置

### 完整配置 (`confxml.xml`)

展示了 Sersync Plus 的所有功能：
- 多目标同步
- Web 管理界面
- 数据库存储
- 通知系统
- 双向同步
- 详细的日志配置

**适用场景**：
- 生产环境部署
- 需要完整功能的场景
- 企业级文件同步

### 双向同步配置 (`confxml_bidirectional.xml`)

专门展示双向同步功能：
- 冲突检测和解决
- 元数据管理
- 多节点支持
- 安全的元数据存储

**适用场景**：
- 多节点文件同步
- 需要双向同步的场景
- 分布式文件系统

## 🔧 自定义配置

### 修改监控路径
```xml
<localpath watch="/your/path/to/sync">
    <remote ip="your.server.ip" name="your_module"/>
</localpath>
```

### 添加多个远程目标
```xml
<localpath watch="/data/sync">
    <remote ip="192.168.1.100" name="backup1"/>
    <remote ip="192.168.1.101" name="backup2"/>
    <remote ip="192.168.1.102" name="backup3"/>
</localpath>
```

### 配置认证
```xml
<rsync>
    <auth start="true" users="your_user" passwordfile="/path/to/password"/>
</rsync>
```

### 启用 SSH 传输
```xml
<rsync>
    <ssh start="true"/>
</rsync>
```

## 📢 通知配置

### 配置企业微信
```yaml
# apprise.yml
urls:
  - wxteams://your_corp_id/your_corp_secret/your_agent_id
    tag: admin,ops
```

### 配置钉钉
```yaml
urls:
  - dingtalk://your_access_token/your_secret
    tag: admin,ops
```

### 配置邮件
```yaml
urls:
  - mailto://user:password@smtp.example.com?to=admin@example.com
    tag: admin,alert,report
```

## 🛠️ 环境配置

### 开发环境
- 使用 `confxml_minimal.xml`
- 启用调试模式：`<debug start="true"/>`
- 使用相对路径存储数据

### 测试环境
- 使用 `confxml.xml`
- 启用 Web 界面进行监控
- 配置测试通知服务

### 生产环境
- 使用 `confxml.xml`
- 禁用调试模式：`<debug start="false"/>`
- 配置完整的通知和监控
- 使用绝对路径存储数据

## 📋 检查清单

在使用配置文件之前，请检查：

- [ ] 修改监控路径 `watch` 属性
- [ ] 配置正确的远程服务器 IP 和模块名
- [ ] 设置合适的 rsync 参数
- [ ] 配置认证信息（如需要）
- [ ] 调整文件过滤规则
- [ ] 设置数据库和日志路径
- [ ] 配置通知服务（如需要）
- [ ] 验证权限设置

## 🔍 故障排查

### 常见问题

1. **连接失败**
   - 检查网络连通性
   - 验证 rsync 服务器配置
   - 确认认证信息正确

2. **权限错误**
   - 检查文件和目录权限
   - 验证 rsync 用户权限
   - 确认密码文件权限（600）

3. **同步失败**
   - 查看详细日志
   - 检查磁盘空间
   - 验证文件路径

### 调试技巧

```bash
# 启用调试日志
sersync-plus --log-level DEBUG -o your_config.xml

# 测试 rsync 连接
rsync -artuz --dry-run /test/path/ user@server::module/

# 验证配置文件
sersync-plus --config-check -o your_config.xml
```

## 📚 更多资源

- [配置指南](../docs/configuration.md)
- [故障排查](../docs/troubleshooting.md)
- [API 文档](../docs/api.md)
- [贡献指南](../CONTRIBUTING.md)
- [GitHub 仓库](https://github.com/0x5c0f/sersync-plus)

---

如有问题，请查看文档或在 [GitHub Issues](https://github.com/0x5c0f/sersync-plus/issues) 提交问题！