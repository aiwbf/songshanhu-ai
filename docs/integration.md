# 联调说明

## 角色边界

- OpenClaw Gateway 只负责接入、标准化、路由和安全控制。
- Consultation API 才负责分类、检索、回答组装和人工转接。
- Knowledge / Rules 层不直接暴露给渠道，而是由 Consultation API 调度。

## 联调顺序

1. 启动 `app.server`
2. 调 `GET /health`
3. 调 `POST /api/consultation/orchestrate`
4. 启动 `apps/gateway-adapter/main.py`
5. 由 OpenClaw 或模拟事件调用 `POST /events/openclaw`

## Consultation API 请求样例

```json
{
  "normalized_message": {
    "event_id": "evt-001",
    "message_id": "msg-001",
    "occurred_at": "2026-03-08T10:00:00Z",
    "channel": "openclaw:wechat",
    "binding": "default",
    "kind": "text",
    "text": "我家孩子属于哪一类？",
    "mentions_bot": false,
    "peer": {
      "peer_id": "dm-001",
      "peer_type": "direct"
    },
    "session": {
      "session_key": "dm-001:user-001"
    },
    "sender": {
      "sender_id": "user-001"
    },
    "attachments": [],
    "metadata": {}
  }
}
```

## OpenClaw Gateway 请求样例

```json
{
  "eventId": "evt-direct-001",
  "occurredAt": "2026-03-08T10:00:00Z",
  "channel": "feishu",
  "binding": "default",
  "sender": {
    "senderId": "parent-001",
    "displayName": "Parent A",
    "paired": true
  },
  "conversation": {
    "peerId": "dm-parent-001",
    "peerType": "direct"
  },
  "message": {
    "messageId": "msg-direct-001",
    "type": "text",
    "text": "什么情况下不能申请松山湖公办中小学转学？"
  },
  "metadata": {}
}
```

## 联调检查点

- `dm / group / admin` 是否路由正确
- 群聊未 `@mention` 是否被安全拦截
- `delivery_allowed` 是否与 allowlist / pairing 一致
- 回答是否总是先给类别/问题判断，再给依据，再给步骤
- `citations` 是否始终包含 `source_id / title / page / chunk_id`
- `metadata.shared_contracts` 是否存在且字段完整
