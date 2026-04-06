# Admin Ops

## 目标

`apps/web/src/admin.html` 是运营 / 人工客服后台，用来观察咨询质量、接管 OpenClaw 会话，并把人工修正沉淀成 FAQ 或规则修订建议。

## 核心看板

后台首页包含：

- 会话记录列表
- 问题热度排行
- 未命中问题池
- FAQ 命中率
- 规则命中率
- 过期文档命中提醒
- 人工接管列表
- FAQ 别名维护
- 坏案例转修复项

## 数据来源

### 会话数据

会话由 `app/chat.py` 维护，已扩展以下元数据：

- `channel`
- `entry_point`
- `is_openclaw`
- `source_session_id`
- `source_target`
- `manual_takeover`
- `takeover_status`
- `takeover_by`
- `takeover_note`
- `last_resolution_source`

### 运营事件

`app/ops.py` 将 `/ask` 与 `/chat` 的结果记录到 `data/runtime/operations.json`，聚合出：

- 热点问题
- 未命中问题
- FAQ / 规则命中率
- 过期文档提醒
- 接管队列
- FAQ 别名
- 修复项

## OpenClaw 联动

`/openclaw/inbound` 现在直接复用 `ChatService`，因此：

- 后台能看到消息来源渠道
- 后台能看到该会话是否来自 OpenClaw
- 后台能查看 OpenClaw 的来源会话标识与目标
- 后台能把该会话标记为人工处理中

## 后台接口

后台页面直接使用：

- `GET /admin`
- `GET /conversations`
- `GET /chat/{conversation_id}`
- `GET /ops/dashboard`
- `GET /ops/faq-aliases`
- `POST /ops/faq-aliases`
- `GET /ops/repair-items`
- `POST /ops/repair-items`
- `POST /ops/conversations/{conversation_id}/takeover`

## FAQ 别名维护

别名存储在 `data/runtime/operations.json`。知识检索层支持通过 `KnowledgeStore.search_faq(..., alias_records=...)` 参与检索，运行时由 `Runtime` 注入别名提供器。

## 坏案例转修复项

修复项的目标不是直接改线上规则，而是形成可审阅的运营待办：

- `faq`：建议补 FAQ 或修 FAQ
- `rule`：建议修改规则或追问策略
- `prompt`：建议优化编排提示
- `manual`：仅做人工备注

## 人工接管规则

人工接管不会删除机器人历史，而是更新会话状态：

- `requested`
- `human`
- `resolved`

会话详情页始终保留原始消息时间线和系统结论，便于复盘。
