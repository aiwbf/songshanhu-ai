# Gateway Runbook

## 1. 目标

本 runbook 面向值班同学，用于处理 `apps/gateway-adapter` 的常见故障、降级和恢复。

## 2. 服务清单

- 咨询服务: `app.server`
- 网关适配层: `apps/gateway-adapter/main.py`
- 配置样例: `config/openclaw.sample.json`

## 3. 健康检查

### 检查 orchestrator

```powershell
curl.exe http://127.0.0.1:8000/health
```

### 检查 gateway

```powershell
curl.exe http://127.0.0.1:8010/health
```

## 4. 常见问题处理

### 4.1 `403 invalid_gateway_token`

处理：

1. 检查 OpenClaw 到 gateway 的请求头名是否与 `headerName` 一致
2. 检查 `sharedToken` 是否已替换 sample 值
3. 检查环境变量是否覆盖了配置文件值

### 4.2 `403 channel_not_allowed` / `sender_not_allowed` / `peer_not_allowed`

处理：

1. 核对 `allowlist`
2. 核对 binding 是否打到了错误渠道
3. 若是新渠道接入，先加到 sample config，再走变更发布

### 4.3 `403 pairing_required`

处理：

1. 检查事件 metadata 是否携带 `paired=true`
2. 检查 sender 是否应加入 `trustedSenders`
3. 不要通过关闭 `pairing.required` 规避生产问题

### 4.4 大量 `response_status=degraded`

处理：

1. 先看 `degradation_code`
2. 若为 `api_timeout`，检查 orchestrator 响应耗时
3. 若为 `api_unavailable`，检查后端服务是否存活
4. 若为 `knowledge_unavailable` 或 `document_index_not_ready`，检查知识构建与索引状态
5. 若为 `rule_engine_exception`，检查后端最近发布

## 5. 日志检查

网关审计日志关键事件：

- `incoming_message`
- `normalized_message`
- `routed_agent`
- `response_status`

优先核对以下字段：

- `request_id`
- `channel`
- `binding`
- `session_key`
- `route_mode`
- `routed_agent`
- `degradation_code`
- `escalation`

## 6. 恢复步骤

### 网关服务重启

```powershell
python apps/gateway-adapter/main.py
```

### 咨询服务重启

```powershell
python -m uvicorn app.server:app --host 127.0.0.1 --port 8000
```

### 知识重新构建

```powershell
python scripts/build_knowledge.py
```

## 7. 回滚原则

1. 先回滚 gateway 配置，再回滚业务服务
2. 不允许通过放开 allowlist、关闭 pairing、关闭 requireMention 来临时止血
3. 必须保留 `fallbackAgent`，不要在故障时移除兜底
