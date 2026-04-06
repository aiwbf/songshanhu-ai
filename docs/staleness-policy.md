# Staleness Policy

## Staleness Flags

每个 source 都会写入 `staleness_flag`：

- `current`
- `historical`
- `expired`
- `unknown`

## High Risk Rule

`retrieve_evidence(question, profile)` 命中已过 `expiry_date` 的文档时：

- `high_risk_staleness = true`
- warning 中显式返回：
  - `命中的 2024 年资料已过有效期，返回 high_risk_staleness。`

## Mixed-Year Conflict Rule

如果同一次检索同时命中：

- 当前招生年度官方资料
- 旧政策或业务 FAQ

则触发冲突提示：

- 已优先采用当前年度指南 / 答疑 / 操作口径
- 旧政策只作为背景依据
- FAQ 只作为辅助解释层

## Practical Outcome For This Repo

当前仓库资料的最新招生年度是 `2024`，而参考日期固定为 `2026-03-08`。

这意味着：

- `2024 指南 / 答疑 / 平台操作指引 / 汇总表` 会被标记为 `expired`
- `2017-2023 原始政策文件` 会被标记为 `historical`
- 原始政策仍可作为规范性背景依据
- 但具体招生操作、时间窗口、平台步骤必须优先采用 2024 年度官方口径，并显式提示其已过期
