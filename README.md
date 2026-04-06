# 松山湖入学咨询 AI 系统

这是一个面向松山湖/东莞入学咨询场景的智能客服系统，包含：

- `OpenClaw Gateway` 渠道接入与会话路由
- `Consultation API` 分类、规则判断、证据检索、结构化回答
- `Knowledge + Rules` 文档导入、切块、向量化、FAQ/规则卡片
- `Web` 家长咨询前台与运营后台

当前仓库已经升级为“双版本知识库”：

- `2025` 版为默认运行版本
- `2024` 版完整保留，可随时切回

## 2025 升级结果

系统现在会递归读取 `2025年入学政策相关资料/` 目录中的全部 PDF，并将内容写入 2025 知识库。

当前已纳入 2025 知识源的核心文件包括：

- `2025年松山湖中小学、幼儿园入学申请指南.pdf`
- `2025年机器人业务文档（2025合并修订版）(1).pdf`
- `2025年广东省人民政府关于印发广东省人才优粤卡实施办法的通知.pdf`
- `2025年关于修订华侨华人子女及华侨学生在我市就读有关规定的通知.pdf`
- `2025年东莞市教育局关于印发《东莞市企业人才子女入学实施办法》的通知.pdf`
- `2025年东莞市非户籍适龄儿童少年积分入读公办义务教育学校实施方案.pdf`
- `2025年东莞市授予荣誉市民称号办法.pdf`
- `2025年“莞爱人才”服务保障实施办法.pdf`

### 向量化说明

本项目当前采用内置本地向量化方案，而不是外部向量数据库：

- 每条 FAQ 会写入 `vector`
- 每个文档切片会写入 `vector`
- 运行时检索使用 `关键词召回 + 章节/规则卡片加权 + 向量余弦相似度`

生成结果位于：

- `data/generated/knowledge_base_2024.json`
- `data/generated/knowledge_base_2025.json`
- `data/generated/knowledge_base.json` 当前激活版本别名
- `data/generated/knowledge_manifest.json`

## 版本切换

通过 `.env` 控制运行版本：

```env
ACTIVE_KNOWLEDGE_YEAR=2025
KNOWLEDGE_YEAR=2025
```

如需切回 2024：

```env
ACTIVE_KNOWLEDGE_YEAR=2024
KNOWLEDGE_YEAR=2024
```

切换后重启服务即可。

## 快速启动

### 1. 安装依赖

```powershell
python -m pip install -r requirements.txt
```

### 2. 准备环境变量

```powershell
Copy-Item .env.example .env
```

至少确认这些值：

```env
LLM_PROVIDER=ollama
LLM_BASE_URL=https://ollama.com/v1
OLLAMA_MODEL=minimax-m2.5:cloud
OLLAMA_API_KEY=

ADMIN_USERNAME=admin
ADMIN_PASSWORD=你的后台密码
ADMIN_SESSION_SECRET=一串随机长字符串

ACTIVE_KNOWLEDGE_YEAR=2025
KNOWLEDGE_YEAR=2025
```

### 3. 重建知识库

```powershell
python scripts/build_knowledge.py
python scripts/import_sources.py
```

### 4. 启动服务

```powershell
python -m uvicorn app.server:app --host 127.0.0.1 --port 8000 --reload
```

页面入口：

- 前台：`http://127.0.0.1:8000/`
- 后台：`http://127.0.0.1:8000/admin`

健康检查：

```powershell
curl.exe http://127.0.0.1:8000/health
```

正常时会返回：

- `knowledge_loaded = true`
- `knowledge_year = 2025`
- `available_knowledge_years = [2024, 2025]`

## OpenClaw 联调

示例配置：

- `config/openclaw.sample.json`

网关入口：

- `POST /openclaw/inbound`

Dry-run 示例：

```powershell
curl.exe -X POST http://127.0.0.1:8000/openclaw/inbound ^
  -H "Content-Type: application/json" ^
  -d "{\"channel\":\"feishu\",\"target\":\"oc_test\",\"source_session_id\":\"demo-parent-001\",\"sender_id\":\"demo-parent-001\",\"paired\":true,\"message\":\"房产锁定规则是什么？\",\"dry_run\":true}"
```

## 测试

### 单元测试

```powershell
python -m unittest discover -s tests -v
```

### 回归评估

```powershell
python scripts/run_evals.py
```

### 红队测试

```powershell
python scripts/run_redteam.py
```

## 当前运行原则

- 默认按 `2025` 资料回答
- 仍保留 `2024` 历史资料用于追溯和兼容测试
- 不允许把历史文件冒充成“最新政策”
- 低置信度、实时平台状态、跨年度比较时优先转人工
- 关键结论必须带来源：`source_id / title / page / chunk_id`

## 关键文件

- `app/server.py`：FastAPI 主服务
- `app/assistant.py`：咨询主链路
- `app/knowledge.py`：知识库检索与向量相似度
- `apps/api/orchestrator.py`：规则编排与证据选择
- `scripts/build_knowledge.py`：双版本知识库构建脚本
- `packages/knowledge/catalog.py`：知识源注册与 2025 动态发现

## 已知边界

- 当前“向量化”是内置本地向量方案，不是外部向量库
- 2025 主库会优先命中 2025 文件，但仍会回退到 2024 历史来源补齐专项政策
- 如果后续新增 2026 目录，需要扩展 `ACTIVE_KNOWLEDGE_YEAR` 和构建脚本的年份枚举
