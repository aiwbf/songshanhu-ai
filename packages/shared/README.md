# Shared Contracts

`packages/shared` 承载跨网关、编排服务、后台共用的 schema。

当前已定义：

- `NormalizedMessage`
- `CaseProfile`
- `ClassificationResult`
- `EvidenceHit`
- `AnswerPayload`
- `EscalationDecision`

这些类型的目标是先冻结接口边界，再启动并行开发，避免多个线程各自发明不同的消息格式和证据结构。
