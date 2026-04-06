# Answer Schema

## AnswerPayload

- `status`
  - `answered | need_info | handoff | out_of_scope`
- `scope`
  - `admissions_consultation | out_of_scope`
- `question_type`
  - 规则引擎识别的问题类型
- `initial_conclusion`
  - 初步结论
- `eligibility_or_issue`
  - 可申报类别 / 当前问题判断
- `judgement_basis`
  - 判断依据列表
- `required_materials`
  - 需要准备的材料列表
- `next_actions`
  - 下一步操作列表
- `risk_alerts`
  - 风险提醒列表
- `human_support`
  - 人工协助方式
- `follow_up_questions`
  - 缺信息时需要追问的 1 到 3 个关键问题

## EscalationDecision

- `action`
  - `none | ask_follow_up | handoff_human | scope_redirect`
- `should_handoff`
- `reasons`
- `summary`
- `confidence`
- `official_contact`

## Citation

- `source_id`
- `title`
- `page`
- `chunk_id`
- `quote_snippet`

## SessionUpdate

- `conversation_id`
- `retained_profile`
  - 仅保留业务必要字段，不保存无关敏感信息
- `last_intent`
- `last_scope`
- `asked_missing_fields`
- `follow_up_rounds`
- `flags`

## Audit Log

JSONL 每行保存一次编排结果，包含：

- trace id
- 归一化消息摘要
- scope 判断
- profile 摘要
- missing context
- rule classification
- citations
- answer payload
- escalation decision
- session update
