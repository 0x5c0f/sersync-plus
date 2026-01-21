# 配置指南

## 基本配置

Sersync Plus 完全兼容原版 sersync 的 XML 配置文件格式，同时扩展了新功能。

### 最小配置示例

```xml
<?xml version="1.0" encoding="UTF-8"?>
<head version="2.5">
    <host hostip="localhost" port="8008"/>
    
    <sersync>
        <localpath watch="/data/sync">
            <remote ip="192.168.1.100" name="backup"/>
        </localpath>
        
        <rsync>
            <commonParams params="-artuz"/>
        </rsync>
    </sersync>
</head>
```

### 完整配置示例

```xml
<?xml version="1.0" encoding="UTF-8"?>
<head version="2.5">
    <!-- 基本配置 -->
    <host hostip="localhost" port="8008"/>
    <debug start="false"/>
    <fileSystem xfs="false"/>
    
    <!-- 文件过滤 -->
    <filter start="true">
        <exclude expression="(.*)\.tmp"/>
        <exclude expression="(.*)\.swp"/>
        <exclude expression="^\.git"/>
    </filter>
    
    <!-- 事件监听 -->
    <inotify>
        <delete start="true"/>
        <createFolder start="true"/>
        <createFile start="true"/>
        <closeWrite start="true"/>
        <moveFrom start="true"/>
        <moveTo start="true"/>
        <attrib start="false"/>
        <modify start="false"/>
    </inotify>
    
    <!-- 同步配置 -->
    <sersync>
        <localpath watch="/data/sync">
            <remote ip="192.168.1.100" name="backup"/>
            <remote ip="192.168.1.101" name="backup2"/>
        </localpath>
        
        <rsync>
            <commonParams params="-artuz"/>
            <auth start="true" users="rsync_user" passwordfile="/etc/rsync.pass"/>
            <userDefinedPort start="false" port="873"/>
            <timeout start="true" time="100"/>
            <ssh start="false"/>
        </rsync>
        
        <failLog path="/tmp/rsync_fail_log.sh" timeToExecute="60"/>
        
        <crontab start="true" schedule="600">
            <crontabfilter start="false">
                <exclude expression="*.log"/>
            </crontabfilter>
        </crontab>
    </sersync>
    
    <!-- 扩展功能 -->
    <web enabled="true" port="8000"/>
    
    <database enabled="true" path="/var/sersync/sersync.db">
        <cleanup enabled="true">
            <days>7</days>
            <max_records>100000</max_records>
        </cleanup>
    </database>
    
    <logging level="INFO" format="text">
        <console enabled="true"/>
        <file enabled="false" path="/var/sersync/sersync.log"/>
    </logging>
    
    <notification enabled="false">
        <apprise_config path="/etc/sersync/apprise.yml"/>
    </notification>
</head>
```

## 双向同步配置

```xml
<sersync>
    <localpath watch="/data/shared">
        <remote ip="192.168.1.100" name="backup" 
                mode="bidirectional" 
                node_id="node-1"
                conflict_strategy="keep_newer" 
                sync_interval="60">
            
            <!-- 可选：自定义元数据路径 -->
            <metadata sync_state_dir="/var/sersync/metadata/shared"
                      conflict_backup_dir="/var/sersync/conflicts/shared"
                      lock_file="/var/sersync/locks/shared.lock"/>
        </remote>
    </localpath>
</sersync>

<!-- 双向同步全局配置 -->
<bidirectional enabled="true" 
               default_conflict_strategy="keep_newer"
               default_sync_interval="60"
               metadata_base_dir="/var/sersync/bidirectional"
               enable_conflict_backup="true"
               max_conflict_backups="10"/>
```

## 通知系统配置

### XML 配置

```xml
<notification enabled="true">
    <apprise_config path="/etc/sersync/apprise.yml"/>
    
    <rules>
        <rule event="sync_failed" notify="immediate" tags="admin,alert"/>
        <rule event="sync_success" notify="batch" tags="monitor" 
              batch_size="100" batch_interval="600"/>
        <rule event="daily_report" notify="schedule" tags="report" 
              cron="0 9 * * *"/>
    </rules>
    
    <templates>
        <template name="sync_failed">
            <title>🚨 同步失败</title>
            <body>文件: {file_path}
远程: {remote_ip}::{remote_module}
错误: {error_message}
时间: {timestamp}</body>
        </template>
    </templates>
</notification>
```

### Apprise 配置文件

```yaml
# /etc/sersync/apprise.yml
urls:
  # 企业微信
  - wxteams://corpid/corpsecret/agentid
    tag: admin,ops
  
  # 钉钉
  - dingtalk://access_token/secret
    tag: admin,ops
  
  # 邮件
  - mailto://user:password@smtp.example.com?to=admin@example.com
    tag: admin,alert
  
  # Telegram
  - tg://bottoken/ChatID
    tag: admin
```

## 命令行参数

### 基本参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `-o, --config` | 配置文件路径 | `-o /etc/sersync.xml` |
| `-r, --initial-sync` | 启动前全量同步 | `-r` |
| `-d, --daemon` | 后台运行 | `-d` |
| `-n, --threads` | 线程数 | `-n 20` |

### Web 界面参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--web` | 启用 Web 界面 | `--web` |
| `--web-port` | Web 端口 | `--web-port 8080` |

### 日志参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--log-level` | 日志级别 | `--log-level DEBUG` |
| `--log-format` | 日志格式 | `--log-format json` |
| `--log-file` | 日志文件 | `--log-file /var/log/sersync.log` |

### 数据库参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--db-path` | 数据库路径 | `--db-path /var/sersync/custom.db` |

## 配置优先级

配置的优先级顺序（高到低）：
1. **命令行参数** - 最高优先级
2. **XML 配置文件** - 中等优先级  
3. **默认值** - 最低优先级

## 环境变量

支持的环境变量：

```bash
export SERSYNC_CONFIG_PATH="/etc/sersync.xml"
export SERSYNC_LOG_LEVEL="INFO"
export SERSYNC_DB_PATH="/var/sersync/sersync.db"
```

## 最佳实践

### 生产环境配置

```xml
<database enabled="true" path="/var/sersync/sersync.db">
    <cleanup enabled="true">
        <days>30</days>
        <max_records>500000</max_records>
    </cleanup>
</database>

<logging level="INFO" format="json">
    <console enabled="false"/>
    <file enabled="true" path="/var/log/sersync/sersync.log" max_size="50MB">
        <backup_count>10</backup_count>
    </file>
</logging>
```

### 开发环境配置

```xml
<database enabled="true" path="./dev/sersync.db">
    <cleanup enabled="true">
        <days>1</days>
        <max_records>10000</max_records>
    </cleanup>
</database>

<logging level="DEBUG" format="text">
    <console enabled="true"/>
    <file enabled="true" path="./dev/sersync.log"/>
</logging>
```