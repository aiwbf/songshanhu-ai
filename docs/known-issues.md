# 已知问题

1. 当前知识主体仍以 2024 年资料为主，系统会主动做时效拦截，但这也意味着“最新政策”类问题多数会进入谨慎回答或人工复核。
2. 运行时回答链路与 `packages/rules` 的结构化分类引擎已经通过共享 contracts 和知识 bundle 接轨，但家长端主回答仍以现有 `app -> apps/api/orchestrator` 路径为主，尚未完全切换到单一引擎。
3. `app.models` 与 `packages/shared/contracts.py` 目前采用“运行时兼容 + canonical projection”方式并存，后续应继续收敛到单一 public schema。
4. Web 前后台目前是静态前端 + FastAPI API，权限控制仍依赖上层网络隔离和 `/ops/*` 访问控制，未引入完整登录鉴权。
5. OpenClaw 渠道实发依赖外部 `run_openclaw_action.ps1` 和实际 OpenClaw 环境，当前仓库默认以 dry-run 联调为主。
