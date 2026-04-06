# 演示流程

## 一键跑演示

```powershell
python scripts/demo_flow.py
```

默认输出：

- `data/generated/demo_flow_latest.json`

## 演示场景

### 1. 最新政策问法

请求：

```powershell
curl.exe -X POST http://127.0.0.1:8000/ask ^
  -H "Content-Type: application/json" ^
  -d "{\"question\":\"2026年最新政策有变化吗？\"}"
```

预期：

- 不冒充 2026 最新政策
- 明确当前知识边界
- 给出依据和人工复核建议

### 2. 多轮补问

第一轮：

```powershell
curl.exe -X POST http://127.0.0.1:8000/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"message\":\"我家孩子属于哪一类？\"}"
```

第二轮：

```powershell
curl.exe -X POST http://127.0.0.1:8000/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"conversation_id\":\"<上一轮返回的ID>\",\"facts\":{\"child_hukou\":\"东莞其他镇街\",\"parent_work_in_songshanhu\":true,\"has_songshanhu_property\":false,\"stage\":\"小学一年级\",\"is_transfer\":false},\"message\":\"补充这些条件后请继续判断。\"}"
```

预期：

- 第一轮返回 `need_info`
- 第二轮继续沿用同一会话上下文
- `remembered_facts` 累积更新

### 3. OpenClaw dry-run

```powershell
curl.exe -X POST http://127.0.0.1:8000/openclaw/inbound ^
  -H "Content-Type: application/json" ^
  -d "{\"channel\":\"feishu\",\"target\":\"oc_test\",\"source_session_id\":\"demo-parent-001\",\"sender_id\":\"demo-parent-001\",\"paired\":true,\"message\":\"什么情况下不能申请松山湖公办中小学转学？\",\"dry_run\":true}"
```

预期：

- 返回渠道适配后的 `reply_text`
- 返回 `routing_key`
- 返回 `delivery_allowed`
- 返回结构化 `answer`

### 4. 运营后台接管

先通过 Web 或 OpenClaw 产生一个会话，再调用：

```powershell
curl.exe -X POST http://127.0.0.1:8000/ops/conversations/<conversation_id>/takeover ^
  -H "Content-Type: application/json" ^
  -d "{\"agent_name\":\"人工客服\",\"note\":\"转人工复核\",\"status\":\"human\"}"
```

预期：

- 会话状态转为 `manual_takeover=true`
- `takeover_status=human`
