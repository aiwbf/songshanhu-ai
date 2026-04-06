# OpenClaw Security Checklist

## 必查项

1. allowlist 是否默认关闭高风险开放模式
- 配置要求：`allowlist.enabled=true`
- 配置要求：`allowlist.default_open_mode=false`
- 风险：未知 target 也能直接外发

2. group requireMention 是否启用
- 配置要求：`group.require_mention=true`
- 风险：群聊模糊发问触发误答，容易扩散错误结论或个人信息

3. pairing 是否启用
- 配置要求：`pairing.enabled=true`
- 风险：未验证来源可直接驱动机器人发消息

4. fallback 是否安全
- 配置要求：`fallback.mode` 只能是 `safe_handoff` 或 `dry_run_only`
- 配置要求：`fallback.allow_direct_answer=false`
- 风险：安全检查失败后仍直接发送模型答案

5. 渠道路由是否串会话
- 配置要求：`routing.session_key_fields` 至少包含 `channel`、`target`，以及 `conversation_id / thread_id / sender_id` 之一
- 配置要求：`routing.allow_cross_channel_thread_reuse=false`
- 风险：不同群、不同私聊、不同渠道共享上下文

## 默认安全配置

- 默认配置文件：`data/seed/openclaw_policy.json`
- 安全基线样例：`evals/openclaw/policy.secure.json`
- 反例样例：`evals/openclaw/policy.insecure.json`

## 审计方法

```powershell
python -X utf8 scripts/run_evals.py
python -X utf8 scripts/run_redteam.py
```

报告中的 `OpenClaw Security Audit` 会给出五项检查的 `pass/fail`。

## 运行时校验

- `OpenClawBridge` 会在发送前评估：
  - target 是否在 allowlist
  - 群聊是否满足 mention
  - pairing 是否满足
  - 路由键是否退化为 `stateless`
- 当 `delivery_allowed=false` 时，即使 `dry_run=false`，也不会实际发送

## 发布前要求

- 五项检查全部通过
- 红队集中至少覆盖：
  - 未 mention 的群聊
  - 未 pairing 的 direct message
  - off-allowlist target
  - 路由键包含 channel/target/thread/sender
