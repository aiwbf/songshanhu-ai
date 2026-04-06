# 第二阶段路线图

## 1. 单一规则内核

- 将 `packages/rules` 收敛为唯一分类内核
- 用统一的 `CaseProfile / ClassificationResult / EvidenceHit` 驱动运行时回答
- 逐步淘汰 `app.models` 中重复 schema

## 2. 知识更新自动化

- 接入 2025/2026 官方资料采集
- 建立文档版本对比与失效提醒
- 对“历史政策冒充现行政策”加入发布门禁

## 3. 权限与审计

- 后台登录鉴权
- 操作留痕
- PII 脱敏导出
- 人工接管 SLA 与队列统计

## 4. OpenClaw 多渠道扩展

- 支持更多渠道 binding
- 增强群聊策略
- 补齐附件、截图、语音等多模态转文字链路

## 5. 运营效率

- FAQ / repair item 审核流
- 坏案例自动聚类
- 高风险问法自动红队回归
