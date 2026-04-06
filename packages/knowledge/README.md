# Knowledge Package

`packages/knowledge` 负责文档导入、切块、检索、来源登记与时效管理。

## 近期目标

- 接管现有 [scripts/build_knowledge.py](/C:/Users/Administrator/myproj/2024/scripts/build_knowledge.py)
- 建立 `knowledge_source` / `knowledge_chunk` 数据映射
- 为 FAQ、PDF、DOCX 建立统一导入接口
- 明确历史文件、现行文件、未知时效文件的标记规则

## 输出

- source registry
- chunk index
- retrieval API
- freshness warnings

## 约束

- 检索结果不能脱离来源元数据单独使用
- 当只有历史资料时，必须显式标记风险
