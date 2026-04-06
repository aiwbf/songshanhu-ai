# Eval Plan

## 目标

这套评估子系统用于在每次 prompt、规则、知识库或版本发布前，自动检查以下风险：

- 类别判断错误：A1 / A2 / A3 / B1 / B2 / B3 / C
- 特殊人群映射错误：优才卡、优粤卡、香港/澳门学童、台湾学生、华侨华人
- 流程型问题误答：房产锁定/解锁、资料修改、单位账号注册与审核、B1 名额查询
- 时效误用：把 2024 资料冒充当前或最新政策
- 安全问题：群聊模糊发问、PII 泄露、渠道路由串会话、未 mention 回复、未 pairing 外发

## 数据集

- 主回归集：`evals/datasets/core_regression.json`
  - 覆盖全部必测政策主题和操作主题
  - 用于发布前回归、分类准确率、追问准确率、引用正确率统计
- 红队集：`evals/datasets/redteam.json`
  - 覆盖幻觉、时效误用、隐私泄露、OpenClaw 配置失守、渠道串会话
- 失败模式库：`evals/failure_modes/top20.json`
  - 作为 case 标注和报告聚合维度

## 指标

- 分类准确率：`question_type`、类别标签、关键结论词是否匹配预期
- 必要追问准确率：缺关键信息时是否返回 `need_info` 且补问正确
- 引用正确率：是否有证据、证据文件是否符合预期、source tier 是否过低
- 幻觉率：是否出现超出安全状态的确定性回答、禁用词或无依据直答
- 时效风险漏报率：涉及“今年/现在/最新/2025/2026”时是否显式提示知识边界
- 人工转接漏判率：应 handoff 的样本是否仍被自动放行

## 四类测试

- Unit tests
  - 评估引擎的打分逻辑
  - OpenClaw 安全审计器
  - 数据集覆盖完整性
- Integration tests
  - `AdmissionsAssistant` 实际跑样本
  - `OpenClawBridge` 的安全审计与路由键
- Regression tests
  - 固定主回归集，保证每次发布前有同一套样本可重复执行
- Red-team tests
  - 模拟时效误用、FAQ 冒充政策、群聊泄露、OpenClaw 配置失守

## 运行方式

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_evals.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run_redteam.ps1
python -m unittest discover -s tests -v
```

## 输出

- JSON 报告
- `evals/reports/latest_eval_report.json`
- `evals/reports/latest_redteam_report.json`
- Markdown 报告
- `evals/reports/latest_eval_report.md`
- `evals/reports/latest_redteam_report.md`

## 发布门槛建议

- `historical_as_current`、`missed_handoff`、`pii_leak_in_group`、`channel_route_mixup` 不允许出现 blocker failure
- OpenClaw 安全审计五项必须全部通过
- 主回归集每次变更都要重跑并保留报告
