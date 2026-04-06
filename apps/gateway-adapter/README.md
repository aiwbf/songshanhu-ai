# Gateway Adapter

`apps/gateway-adapter` 负责把 OpenClaw 及未来其他渠道的原始消息，统一适配成 `NormalizedMessage`，然后路由到咨询编排服务。

## 设计边界

- 这里只做接入、标准化、路由、安全控制、降级回复。
- 这里不做政策判断，不做最终资格结论。
- 任何渠道专有字段都留在 `raw_payload_ref` 或 `metadata`，不污染业务核心模型。

## 核心能力

- `dm / group / admin` 三种对话策略
- `pairing / allowlist / requireMention` 安全开关
- `channel binding` 到不同 `agent_profile`
- Consultation API 故障时的标准降级模板

## 样例配置

- [config/channel-bindings.example.yaml](/C:/Users/Administrator/myproj/2024/apps/gateway-adapter/config/channel-bindings.example.yaml)
- [config/gateway-policy.example.yaml](/C:/Users/Administrator/myproj/2024/apps/gateway-adapter/config/gateway-policy.example.yaml)

## 与现有原型的关系

现有 [app/openclaw_bridge.py](/C:/Users/Administrator/myproj/2024/app/openclaw_bridge.py) 可以作为发送器与回包格式的早期参考，但新网关必须以 `NormalizedMessage` 为中心重构。
