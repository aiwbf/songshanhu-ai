# 部署说明

## 组件

- `app.server`
  咨询编排 API、家长端页面、运营后台、OpenClaw 直连入口。
- `apps/gateway-adapter/main.py`
  OpenClaw Gateway 适配层，负责渠道标准化、安全开关和路由。

## 依赖

```powershell
python -m pip install -r requirements.txt
```

## 环境变量

复制 [.env.example](/C:/Users/Administrator/myproj/2024/.env.example) 作为部署起点，并至少确认：

- `OPENCLAW_SHARED_TOKEN`
- `CONSULTATION_ORCHESTRATOR_URL`
- `OPENCLAW_ENABLE_SEND`
- `OFFICIAL_CONTACT`

## 知识库导入

运行时维护两份知识资产：

- legacy 运行时检索包：`data/generated/knowledge_base.json`
- 结构化知识 bundle：`data/generated/knowledge_bundle.json`

导入命令：

```powershell
python scripts/build_knowledge.py
python scripts/import_sources.py
```

或直接调用 API：

```powershell
curl.exe -X POST http://127.0.0.1:8000/ingest
```

## 启动 Consultation API

```powershell
python -m uvicorn app.server:app --host 127.0.0.1 --port 8000
```

页面入口：

- 家长端：`http://127.0.0.1:8000/`
- 运营后台：`http://127.0.0.1:8000/admin`

## 启动 OpenClaw Gateway

```powershell
$env:OPENCLAW_GATEWAY_CONFIG="C:\Users\Administrator\myproj\2024\config\openclaw.sample.json"
python apps/gateway-adapter/main.py
```

Gateway 默认转发到：

- `http://127.0.0.1:8000/api/consultation/orchestrate`

## 生产注意事项

- 默认安全策略应保持 `allowlist.enabled=true`、`pairing.enabled=true`、`group.require_mention=true`。
- 不要把 `OPENCLAW_ENABLE_SEND=1` 和宽松 allowlist 一起上线。
- `data/generated/audit/consultation_orchestrator.jsonl` 需要纳入日志轮转和备份。
- 反向代理层应限制 `/ops/*` 和 `/admin` 的访问来源。
