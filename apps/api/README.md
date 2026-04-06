# Consultation API

`apps/api` 是咨询编排层，对外提供统一 API，负责把规则、检索、提示词和人工兜底编排成标准结果。

## 责任

- 接收 `NormalizedMessage` 或 Web 端标准请求
- 更新 `CaseProfile`
- 生成 `ClassificationResult`
- 调用规则引擎与知识检索
- 返回 `AnswerPayload` 或 `EscalationDecision`

## 约束

- 先分类，再解释依据，再给步骤
- 低置信度、证据冲突、时效不明时不强答
- 每个关键结论必须带证据引用

## 迁移建议

现有 [app/server.py](/C:/Users/Administrator/myproj/2024/app/server.py) 和 [app/assistant.py](/C:/Users/Administrator/myproj/2024/app/assistant.py) 可逐步拆分迁移到这里，但不要直接复制原有单体结构。
