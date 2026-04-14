# Eval Report

- Generated at: 2026-04-13T14:24:44.415797+00:00
- Dataset: `C:\Users\Administrator\myproj\2024\evals\datasets\core_regression.json`
- Total cases: 22
- Overall pass rate: 100.00%

## Metrics

| Metric | Value |
| --- | --- |
| 分类准确率 | 100.00% |
| 必要追问准确率 | 100.00% |
| 引用正确率 | 100.00% |
| 幻觉率 | 0.00% |
| 时效风险漏报率 | 0.00% |
| 人工转接漏判率 | 0.00% |

## Release Blockers

- None

## Failure Modes

- None

## OpenClaw Security Audit

| Check | Status | Detail |
| --- | --- | --- |
| allowlist 默认关闭高风险开放模式 | pass | allowlist 已启用，且默认不是开放模式。 |
| 群聊 requireMention 已启用 | pass | 群聊仅在明确提及时允许触发回复。 |
| pairing 已启用 | pass | 高风险渠道要求 pairing 才允许发送。 |
| fallback 配置安全 | pass | fallback 仅允许安全转人工或 dry-run，不允许直接放行答案。 |
| 渠道路由不会串会话 | pass | 路由键包含 channel、target 和会话区分字段，且禁止跨渠道复用线程。 |

## Case Details

| Case | Topic | Status | Pass | Notes |
| --- | --- | --- | --- | --- |
| `a1-grandparent-property` | A1 / A3 | answered | pass | ok |
| `a2-vs-b2-choice` | A2 | answered | pass | ok |
| `a3-definition` | A3 | answered | pass | ok |
| `b1-one-year-rule` | B1 | answered | pass | ok |
| `b2-enterprise-talent` | B2 | answered | pass | ok |
| `b3-ranking` | B3 | answered | pass | ok |
| `c-points-admission` | C | answered | pass | ok |
| `youcai-card-b2` | 优才卡 | answered | pass | ok |
| `youyue-card` | 优粤卡 | answered | pass | ok |
| `hk-macao-child` | 香港/澳门学童 | answered | pass | ok |
| `taiwan-student` | 台湾学生 | answered | pass | ok |
| `overseas-chinese` | 华侨华人 | answered | pass | ok |
| `property-lock` | 房产锁定 | answered | pass | ok |
| `property-unlock` | 房产解锁 | answered | pass | ok |
| `profile-update` | 资料修改 | answered | pass | ok |
| `unit-account-registration` | 单位账号注册 | answered | pass | ok |
| `unit-account-review` | 单位审核 | answered | pass | ok |
| `b1-quota-query` | B1 名额查询 | handoff | pass | ok |
| `simultaneous-b3-and-c` | 同时申请 B3 与 C | answered | pass | ok |
| `ambiguous-group-question` | 群聊中模糊发问 | need_info | pass | ok |
| `non-admissions-question` | 非招生问题误入 | out_of_scope | pass | ok |
| `historical-policy-asked-as-current` | 历史政策误问为当前政策 | handoff | pass | ok |
