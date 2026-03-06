# OpenClaw Lite 原型

这是一个**轻量化、可本地部署**的 OpenClaw 智能体原型，聚焦：

1. 文档办公（生成、编辑、翻译、音视频摘要）
2. 事项管理（时间获取、任务管理、主动提醒）

## 设计目标

- **多端统一**：通过 HTTP API 支持手机/平板/PC。
- **用户隔离**：每个用户独立 `data/<user_id>/workspace.db`。
- **轻量化运行**：仅使用 Python 标准库（`http.server + sqlite3`），减少依赖与资源占用。
- **可裁剪能力**：移除与“专业文秘”定位无关的默认能力。
- **模型留空**：`ModelAdapter.call` 由你接入自用模型。

## 快速运行

```bash
python3 prototype/openclaw_lite_agent.py
```

默认端口 `8080`，可用 `OPENCLAW_PORT` 覆盖。

## API 示例

### 1) 创建事项

```bash
curl -X POST http://127.0.0.1:8080/v1/task/create \
  -H 'content-type: application/json' \
  -d '{"user_id":"alice","title":"周报提交","due_at":"2026-01-01T10:00:00"}'
```

### 2) 查询提醒

```bash
curl -X POST http://127.0.0.1:8080/v1/task/reminders \
  -H 'content-type: application/json' \
  -d '{"user_id":"alice"}'
```

### 3) 文档生成

```bash
curl -X POST http://127.0.0.1:8080/v1/doc/write \
  -H 'content-type: application/json' \
  -d '{"user_id":"alice","prompt":"写一封项目延期但可控的沟通邮件"}'
```

## 预制 skills（面向专业文秘）

见 `prototype/skills/`：
- `meeting_minutes.md`
- `executive_scheduler.md`
- `doc_quality_guard.md`

## 安全建议

- 默认仅监听内网环境，生产请放在 API 网关后并启用 TLS。
- `user_id` 已做字符白名单，但仍建议在网关层做鉴权与签名。
- 如需调用设备能力（通知、日历、文件系统），建议使用平台原生权限控制并最小化授权。

## 下一步可扩展

- 用消息队列/系统定时器替代轮询提醒。
- 将 `ModelAdapter` 替换为你的模型 SDK。
- 增加文档版本管理、向量检索（可选轻量索引）。
