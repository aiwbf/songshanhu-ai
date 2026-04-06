# 知识库重建说明

## 目标

- 把仓库里实际参与咨询的知识源统一重建为可追踪的结构化知识库。
- 在运行时优先引用官方来源、当年指南和专项政策，不让业务 FAQ 覆盖政策结论。
- 为人工维护补齐 Markdown 索引层，做到“程序可检索，人也能顺着索引查”。

## 当前结构

- `data/generated/knowledge_bundle_*.json`
  - 结构化知识包，按 `source` / `chunk` / `tag` / `year` 组织。
- `wiki/sources/`
  - 每个知识源一个页面，记录来源、年份、失效状态、代表性片段。
- `wiki/topics/`
  - 按主题和标签聚合来源，方便人工核查。
- `wiki/years/`
  - 按年度查看知识源分布。
- `wiki/index.md`
  - 总入口。
- `wiki/log.md`
  - 每次重建的工作日志。

## 运行时改写方向

- 回答时先做规则判断，再走证据检索。
- 证据检索优先官方来源、当前年度指南、专项政策。
- 历史资料和业务 FAQ 只作为补充，不覆盖当前有效口径。
- 涉及跨年度、实时平台状态、概率承诺的问题，直接转人工或保守边界回答。

## 重建命令

```powershell
python scripts/import_sources.py
```

执行后会同步刷新：

- `knowledge_bundle_*.json`
- `wiki/index.md`
- `wiki/sources/*.md`
- `wiki/topics/*.md`
- `wiki/years/*.md`
- `wiki/log.md`
