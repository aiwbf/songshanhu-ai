# 工作日志

## 2026-04-05 重建 Markdown 知识库

- 活跃招生年度: `2025`
- 来源页: `24`
- 主题页: `35`
- 年份页: `7`
- 已同步更新 `wiki/index.md`、`wiki/sources/`、`wiki/topics/`、`wiki/years/`。
- 当前回答程序应优先引用结构化知识和官方来源，不把业务 FAQ 当成高优先级政策依据。

## [2026-04-05] rewrite | 运行时与模型重写
- scope: 将运行时装配、后台会话认证从 `app/server.py` 剥离，并建立知识库技能对应的最小 wiki 层。
- files touched:
  `app/admin_session.py`
  `app/runtime.py`
  `app/models.py`
  `app/server.py`
  `wiki/index.md`
  `wiki/runtime-rewrite.md`
  `wiki/log.md`
- summary: 保留现有接口地址不变，重写内部运行时结构，减少服务入口文件的耦合。
- follow-up: 继续把知识编译和编排逻辑从旧 `app/*` 模块逐步迁移到更稳定的 package 边界。
