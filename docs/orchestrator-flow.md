# Consultation Orchestrator Flow

## Goal

把 OpenClaw Gateway 送来的归一化消息，编排成一个完整、克制、可追溯的招生咨询回答，并给出稳定的人工转接决策。

## Runtime Steps

1. `detect_scope`
   - 判断是否属于 2024 年松山湖/东莞招生咨询范围。
   - 超出范围时直接做 scope gating，不继续做个案硬判。
2. `extract_case_profile`
   - 合并会话记忆、已有 profile、当前消息提取结果。
   - 仅保留业务必要字段，例如户籍、工作、房产、学段、转学、特殊情形。
   - 如发现前后资料冲突，记录冲突并进入人工转接判断。
3. `identify_missing_fields`
   - 对个案类问题识别关键缺失字段。
   - 仅追问 1 到 3 个最关键问题。
4. `classify_case`
   - 识别问题类型、是否要求人工、是否触发最新年度拦截、是否属于平台实时状态问题。
5. `retrieve_evidence`
   - 优先检索官方 PDF / 指南 / 政策来源。
   - FAQ/运营答疑只作为补充参考，不作为法定依据。
   - 输出标准化引用：`source_id / title / page / chunk_id / quote_snippet`。
6. `generate_answer`
   - 统一输出 7 段结构：
     - 初步结论
     - 可申报类别 / 当前问题判断
     - 判断依据
     - 需要准备的材料
     - 下一步操作
     - 风险提醒
     - 人工协助方式
7. `evaluate_confidence`
   - 基于证据强度、官方来源覆盖度、缺失信息、冲突、实时性风险等打分。
8. `decide_escalation`
   - 输出 `EscalationDecision`。
   - 决策动作包括：
     - `none`
     - `ask_follow_up`
     - `handoff_human`
     - `scope_redirect`
9. `persist_log`
   - 写入审计日志 JSONL。
   - 记录 trace id、输入摘要、分类结果、引用、回答、转接决策和 session update。

## Guardrails

- 不生成录取概率。
- 不编造名额与审核状态。
- 信息不足时不硬判 A/B/C。
- 文档过期时不冒充最新口径。
- FAQ 不作为法定依据直接落结论。

## Channel Awareness

- 私聊：输出完整 7 段结构。
- 群聊：默认简洁，只保留初步结论、当前判断、关键补充项和人工引导。
- 管理员：附带 trace id、置信度、转接原因和更多流程信息。
