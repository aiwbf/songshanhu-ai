# Source Priority

本子系统把 `authority_rank` 和 `priority_bucket` 分开处理：

- `authority_rank` 表示法规层级。原始政策文件通常最高。
- `priority_bucket` 表示招生问答时实际采用顺序。当前招生年度的官方操作口径优先。

## Source Registry

每条 `source` 必含以下字段：

- `source_id`
- `title`
- `source_type`
- `year`
- `effective_date`
- `expiry_date`
- `scope`
- `authority_rank`
- `reliability_rank`
- `staleness_flag`

## Priority Buckets

1. 当前招生年度指南 / 官方答疑 / 平台操作指引
2. 当前年度优待政策汇总表
3. 原始政策文件
4. 业务 FAQ / 内部口径 / 咨询统计

当前仓库内，`active_cycle_year` 自动识别为 `2024`。

## Ranking Rules

- 检索排序先看文本匹配，再加 `priority_bucket` 权重。
- 同等匹配度下，优先返回 `priority_bucket` 更高的来源。
- `business_faq` 会被导入，但会施加负权，确保只能作为补充解释层。
- 如果检索结果同时命中 `priority_bucket=1` 与 `priority_bucket>=3`，系统显式输出 warning：
  - 已优先采用 2024 年度指南 / 答疑 / 操作口径。

## FAQ Non-Override Rule

- `business_faq` 允许补充：
  - 高频问法
  - 材料细项
  - 平台操作说明
- `business_faq` 不允许覆盖：
  - A/B/C 分类结论
  - 优待政策结论
  - 过期年份的流程时点

如果业务 FAQ 与官方资料的类别标签不一致，检索层会标记冲突并压制 FAQ 覆盖。
