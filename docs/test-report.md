# 测试报告

## 时间

- 生成时间：2026-03-08

## 执行命令

```powershell
python -m unittest discover -s tests -v
python scripts/run_evals.py
python scripts/run_redteam.py
python scripts/demo_flow.py
```

## 结果摘要

- 单元 / 集成测试：`44/44` 通过
- 核心回归集：`22/22` 通过
- 红队集：`12/12` 通过
- Release blocker：`0`

## 核心回归指标

来自 `evals/reports/latest_eval_report.json`：

- `overall_pass_rate`: `1.0`
- `classification_accuracy`: `1.0`
- `necessary_followup_accuracy`: `1.0`
- `citation_correctness`: `1.0`
- `hallucination_rate`: `0.0`
- `timeliness_risk_miss_rate`: `0.0`
- `handoff_miss_rate`: `0.0`

## 红队指标

来自 `evals/reports/latest_redteam_report.json`：

- `overall_pass_rate`: `1.0`
- `classification_accuracy`: `1.0`
- `necessary_followup_accuracy`: `1.0`
- `hallucination_rate`: `0.0`
- `timeliness_risk_miss_rate`: `0.0`
- `handoff_miss_rate`: `0.0`

## 已验证能力

- OpenClaw Gateway 没有越权到业务判断层
- `NormalizedMessage -> Orchestrator -> Evidence -> AnswerPayload -> EscalationDecision` 闭环可运行
- 最新政策问法会做时效保护并转人工
- 低信息问题会补问，不会强答
- 房产锁定/解锁、资料修改、单位账号、B1 名额、优才卡、优粤卡、华侨华人、台湾学生、香港/澳门学童、B3/C 并行申请均已覆盖
- 回答证据链可输出 `source_id / title / page / chunk_id`
- OpenClaw 安全审计项全部通过：allowlist、requireMention、pairing、fallback、routing isolation

## 演示脚本结果

来自 `data/generated/demo_flow_latest.json`：

- 最新政策场景：`handoff`
- 多轮补问场景：首轮 `need_info`，二轮继续 `need_info`，并保留 `remembered_facts`
- OpenClaw DM dry-run：`delivery_allowed=true`，且返回稳定 `routing_key`

## 结论

当前仓库已经达到“可运行、可联调、可评估、可演示”的交付状态。
