# 运行时重写说明

## Summary
- 本次重写采用“知识库优先”的工作方式，但不改变对外接口。
- 重点是把运行时生命周期、后台认证、协议模型从原来的大文件中拆出来。
- 当前仍兼容：
  `/`
  `/admin`
  `/health`
  `/ask`
  `/chat`
  `/openclaw/inbound`
  `/admin-api/*`

## Key facts
- `app/runtime.py` 现在负责：
  - 设置加载
  - 知识库与结构化 bundle 的确保/重建
  - Assistant / ChatService / OperationsService 的装配
- `app/admin_session.py` 现在负责：
  - 登录开关判断
  - cookie 签名
  - 过期与空闲超时校验
  - 后台鉴权
- `app/server.py` 现在退化为：
  - FastAPI 组装
  - 路由绑定
  - 将请求委托给 runtime 中的服务对象
- `app/models.py` 现在做了一次协议层重写：
  - 去掉重复定义
  - 保留现有兼容字段
  - 统一模型顺序与边界

## Detailed notes
- 这次没有直接推翻现有业务逻辑，主要原因是当前仓库已有可运行接口和测试。
- 如果直接“一次性重写全部业务”，风险会落在：
  - 现有接口兼容性
  - 测试基线
  - OpenClaw 回包格式
  - 运营后台读写路径
- 所以本轮先重写“组合层”和“协议层”，为后续继续替换知识检索与编排内核创造条件。

## Relationships
- 运行时入口：[app/server.py](C:/Users/Administrator/myproj/2024/app/server.py)
- 运行时装配：[app/runtime.py](C:/Users/Administrator/myproj/2024/app/runtime.py)
- 后台会话认证：[app/admin_session.py](C:/Users/Administrator/myproj/2024/app/admin_session.py)
- 协议模型：[app/models.py](C:/Users/Administrator/myproj/2024/app/models.py)
- 现有结构化 contracts：[packages/shared/contracts.py](C:/Users/Administrator/myproj/2024/packages/shared/contracts.py)

## Open questions
- 是否下一轮要继续把 `app/knowledge.py` 的运行时检索逻辑改写为直接复用 `packages/knowledge`。
- 是否要把 `apps/api/orchestrator.py` 再向 `packages/rules` / `packages/knowledge` 收敛，减少 `app/*` 与 `apps/*` 双栈并存。
- 是否要把前后台页面也一起重写成更严格的 API 客户端分层。

## Sources
- [系统蓝图](C:/Users/Administrator/myproj/2024/docs/system-blueprint.md)
- [README](C:/Users/Administrator/myproj/2024/README.md)
- [知识包说明](C:/Users/Administrator/myproj/2024/packages/knowledge/README.md)

## Last updated
2026-04-05
