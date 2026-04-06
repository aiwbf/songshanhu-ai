# OpenClaw 配置说明

配置样例见：

- `config/openclaw.sample.json`

所有字符串值支持环境变量占位：

- `${ENV_NAME}`
- `${ENV_NAME:-default-value}`

## 1. `service`

```json
{
  "listenHost": "127.0.0.1",
  "listenPort": 8010,
  "orchestratorBaseUrl": "http://127.0.0.1:8000",
  "orchestratorPath": "/api/consultation/orchestrate",
  "timeoutMs": 6000
}
```

说明：

- `listenHost` / `listenPort`: gateway-adapter 监听地址
- `orchestratorBaseUrl`: 后端统一咨询服务地址
- `orchestratorPath`: 统一 adapter 调用的后端 API 路径
- `timeoutMs`: 后端超时阈值

## 2. `security`

```json
{
  "defaultDeny": true,
  "headerName": "X-OpenClaw-Token",
  "sharedToken": "${OPENCLAW_SHARED_TOKEN:-change-me-in-production}",
  "allowlist": {
    "channels": ["feishu", "wechat_service", "webchat"],
    "senders": [],
    "peers": []
  },
  "pairing": {
    "required": true,
    "trustedSenders": ["ops_console_bot"],
    "metadataKey": "paired"
  }
}
```

说明：

- `defaultDeny`: 未命中 allowlist 时直接拒绝
- `headerName`: OpenClaw 到 gateway 的共享令牌头
- `sharedToken`: 共享令牌
- `allowlist.channels`: 允许接入的渠道
- `allowlist.senders`: 可选，收紧到特定 sender
- `allowlist.peers`: 可选，收紧到特定会话或群
- `pairing.required`: 是否必须先完成 sender pairing
- `pairing.trustedSenders`: 可绕过 pairing 的后台 sender
- `pairing.metadataKey`: 从事件 metadata 中读取配对结果的键名

## 3. `routing`

```json
{
  "group": {
    "requireMention": true
  },
  "perSenderSession": true,
  "fallbackAgent": "fallback-human-handoff",
  "channelBindings": {
    "default": {
      "routeMode": "parent_consultation",
      "requireMention": true,
      "perSenderSession": true
    }
  }
}
```

说明：

- `group.requireMention`: 群聊是否必须 @ 机器人
- `perSenderSession`: 是否按 sender 隔离会话
- `fallbackAgent`: 后端异常时的统一兜底 agent
- `channelBindings`: 某个 binding 或 channel 的覆盖配置

## 4. `channelBindings`

建议至少保留三类 binding：

### `default`

- `routeMode = parent_consultation`
- 面向家长咨询

### `unit_admin_console`

- `routeMode = organization_admin`
- 面向单位管理员、单位审核、流程答疑

### `operations_console`

- `routeMode = operations_support`
- 面向运营和人工客服后台

## 5. 会话隔离

当 `perSenderSession = true` 时，session key 结构为：

```text
channel:binding:peer_id[:thread_id]:sender_id
```

当 `perSenderSession = false` 时，session key 结构为：

```text
channel:binding:peer_id[:thread_id]
```

推荐生产默认保留 `true`，避免群聊串话。

## 6. 降级矩阵

| 场景 | `degradation_code` | 标准回复方向 |
| --- | --- | --- |
| 知识库不可用 | `knowledge_unavailable` | 转人工，提示稍后重试 |
| API 超时 | `api_timeout` | 返回保守答复，建议稍后重试 |
| 规则引擎异常 | `rule_engine_exception` | 转人工复核 |
| 文档索引未就绪 | `document_index_not_ready` | 提示索引未就绪，建议稍后再试 |
| 后端整体不可用 | `api_unavailable` | 进入 fallback agent |

## 7. 推荐环境变量

```powershell
$env:OPENCLAW_GATEWAY_CONFIG="C:\Users\Administrator\myproj\2024\config\openclaw.sample.json"
$env:OPENCLAW_SHARED_TOKEN="replace-with-real-secret"
$env:CONSULTATION_ORCHESTRATOR_URL="http://127.0.0.1:8000"
```
