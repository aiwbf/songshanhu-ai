# Repair Prompt Skeleton: Missing Evidence

当答案缺少证据字段时：

- 删除无法落地到 `EvidenceHit` 的结论
- 保留可证实部分
- 把剩余问题改写为补问或人工转接建议
