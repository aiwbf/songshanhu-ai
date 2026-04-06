# OpenClaw 本地联调说明

## 1. 安装依赖

```powershell
python -m pip install -r requirements.txt
```

## 2. 启动后端咨询服务

```powershell
python -m uvicorn app.server:app --host 127.0.0.1 --port 8000
```

## 3. 准备网关配置

```powershell
$env:OPENCLAW_GATEWAY_CONFIG="C:\Users\Administrator\myproj\2024\config\openclaw.sample.json"
$env:OPENCLAW_SHARED_TOKEN="local-dev-token"
```

## 4. 启动 gateway-adapter

```powershell
python apps/gateway-adapter/main.py
```

## 5. 发送私聊测试消息

```powershell
curl.exe -X POST http://127.0.0.1:8010/events/openclaw ^
  -H "Content-Type: application/json" ^
  -H "X-OpenClaw-Token: local-dev-token" ^
  -d "{\"eventId\":\"evt-direct-001\",\"occurredAt\":\"2026-03-08T10:00:00Z\",\"channel\":\"feishu\",\"binding\":\"default\",\"sender\":{\"senderId\":\"parent-001\",\"displayName\":\"Parent A\",\"paired\":true},\"conversation\":{\"peerId\":\"dm-parent-001\",\"peerType\":\"direct\"},\"message\":{\"messageId\":\"msg-direct-001\",\"type\":\"text\",\"text\":\"请问小学一年级报名需要什么材料？\"},\"metadata\":{}}"
```

## 6. 发送群聊 @ 机器人测试消息

```powershell
curl.exe -X POST http://127.0.0.1:8010/events/openclaw ^
  -H "Content-Type: application/json" ^
  -H "X-OpenClaw-Token: local-dev-token" ^
  -d "{\"eventId\":\"evt-group-001\",\"occurredAt\":\"2026-03-08T10:01:00Z\",\"channel\":\"feishu\",\"binding\":\"default\",\"sender\":{\"senderId\":\"parent-002\",\"displayName\":\"Parent B\",\"paired\":true},\"conversation\":{\"peerId\":\"group-001\",\"peerType\":\"group\"},\"message\":{\"messageId\":\"msg-group-001\",\"type\":\"text\",\"text\":\"@招生机器人 转学有哪些限制？\",\"mentions\":[\"admissions-bot\"]},\"metadata\":{}}"
```

## 7. 预期结果

1. Gateway 返回 `normalized_message`
2. `route_mode` 默认为 `parent_consultation`
3. `routed_agent` 为 `admissions-consultation`
4. 审计事件包含 `incoming_message`、`normalized_message`、`routed_agent`、`response_status`

## 8. 模拟降级

将 `orchestratorBaseUrl` 改为无效地址后重新启动 gateway，再发送同样请求，预期：

1. `response_status = degraded`
2. `degradation_code = api_unavailable` 或 `api_timeout`
3. `routed_agent = fallback-human-handoff`
