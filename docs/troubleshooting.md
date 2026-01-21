# 故障排查指南

## 常见问题

### Python 3.12 兼容性问题

**问题**: 在 Python 3.12 中出现 `NotImplementedError`

**解决方案**: 已自动修复，程序会自动检测并设置合适的事件循环策略。

### 目录删除警告

**问题**: 删除目录时出现 rsync 警告

**解决方案**: 已修复事件处理竞争条件，现在会智能过滤子文件删除事件。

### Web 界面无法访问

**检查步骤**:
1. 确认端口未被占用: `netstat -tlnp | grep 8000`
2. 检查防火墙设置
3. 确认服务正常启动

### 同步历史记录性能问题

**优化方案**:
- 使用分页加载（20/50/100/200 条）
- 启用数据库自动清理
- 定期清理旧记录

## 配置问题

### 数据库和日志路径

支持通过命令行参数或配置文件指定：

```bash
# 命令行指定
sersync-plus --db-path /custom/path/sersync.db --log-file /custom/path/sersync.log

# 配置文件指定
<database enabled="true" path="/custom/path/sersync.db"/>
<logging file_enabled="true" file_path="/custom/path/sersync.log"/>
```

### 双向同步配置

确保元数据目录不在监控目录内：

```xml
<remote ip="192.168.1.100" name="backup" mode="bidirectional">
    <metadata sync_state_dir="/var/sersync/metadata/shared"
              conflict_backup_dir="/var/sersync/conflicts/shared"/>
</remote>
```

## 性能优化

### 大数据量处理

1. **启用分页**: 在 Web 界面选择合适的分页大小
2. **数据清理**: 定期清理旧的同步记录
3. **索引优化**: 数据库会自动创建必要的索引

### 内存使用优化

1. **缓存管理**: 系统会自动管理查询缓存
2. **连接池**: 数据库连接会自动管理
3. **批量操作**: 支持批量插入和查询

## 日志分析

### 查看详细日志

```bash
# 启用调试日志
sersync-plus --log-level DEBUG

# 查看特定组件日志
grep "sync_engine" /var/log/sersync.log
```

### 常见日志信息

- `Event filtered by parent directory delete`: 正常的事件过滤
- `Rsync completed successfully`: 同步成功
- `WebSocket client connected`: Web 客户端连接

## 联系支持

如果问题仍未解决，请：

1. 收集相关日志信息
2. 记录复现步骤
3. 在 GitHub 提交 Issue
4. 提供系统环境信息（Python 版本、操作系统等）