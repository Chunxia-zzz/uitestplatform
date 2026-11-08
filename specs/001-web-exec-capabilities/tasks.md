# Tasks: Web 执行能力补齐（M3.8）

**Feature**: specs/001-web-exec-capabilities · **Plan**: [plan.md](./plan.md) · **Contracts**: [contracts/action-schema.md](./contracts/action-schema.md)

**Tests 惯例**（项目 Constitution V）：单测随实现同文件批次交付；每故事有独立验收；冒烟脚本进 `scripts/`。路径均相对仓库根 `F:\jerryyang-uitestplatform`。

## File-Creation Order（依赖序总览）

```text
Phase 1 Setup（核实）
  → Phase 2 Foundational（字典/矩阵/上下文/执行器/校验 —— 全部故事的公共前置）
    → Phase 3 US1 网络 mock（P1）
    → Phase 4 US2 下载（P2）        ← 与 US1 共享 adapter 文件，建议顺序执行
    → Phase 5 US3 iframe（P3）      ← 同上
    → Phase 6 US4 执行级变量（P3）  ← 实现主体在 Phase 2，本阶段只做端到端验收
      → Phase 7 Polish（冒烟/回归/文档/收尾）
```

## Phase 1 — Setup（核实，不写产品代码）

- [ ] T001 核实 `backend/app/core/db.py` 启动 seed 语义（对已有 action_catalog 行是 upsert 还是仅首次插入）；若非 upsert，在 T010 中补"开发库重 seed"步骤。证据贴入本任务勾选备注。
- [ ] T002 核实前端编排页是否存在"动作可否绑定元素"硬编码清单（`frontend/src/` 检索 requires_element / element 相关判定）；存在则记入 T018 前端任务范围，不存在记录结论。

## Phase 2 — Foundational（阻塞全部故事）

- [ ] T003 `backend/app/engines/base.py`：`ActionContext` 增加 additive 字段 `shared_variables: dict` 与 `case_started_ts: float | None`；新增 `set_shared_var(name, value)` 方法（写 shared_variables；`set_var` 行为不变）。
- [ ] T004 `backend/app/engines/base.py`：`EngineAdapter` 新增 `async def reset_case_scope(self) -> None: return None`（非动作，不进 action_catalog；docstring 注明 finalize_diagnostics 先例）。同步 stub/appium 适配器确认继承 no-op 即可（不改文件）。
- [ ] T005 `backend/app/domain/action_keys.py` + `backend/app/domain/capabilities.py`：新增 4 条 ActionDef（mock_route / unmock_route / wait_for_response → category=`NETWORK` 新值；download_file → ELEMENT、requires_element=1，schema 按 contracts）；`set_variable` props 加可选 `scope`（enum case/execution 默认 case）；`switch_to_iframe` props 注释补充互斥语义（schema 不变）；`_WEB` 集合 += 4。
- [ ] T006 `backend/app/engines/actions.py` + `backend/app/services/execution_service.py`：`dispatch` 参数渲染改传 `ChainMap(ctx.variables, ctx.shared_variables)`（render 零改动）；`_builtin_set_variable` 读 `scope`，execution → `ctx.set_shared_var`；`execute()` 每次执行建 `execution_vars` 并逐用例传入；`_run_case` 填 `case_started_ts`、用例开始处 `await adapter.reset_case_scope()`；`needs_element` 判定改为 import `case_service.element_requirement`（写入口/执行口共用一份规则）。
- [ ] T007 `backend/app/services/case_service.py`：`_special_element_need` 扩展——`switch_to_iframe` 绑定元素即需 chain 且与 `params.index` 互斥（同给抛 ValidationFailed）；`download_file` 恒需元素；mock `json`/`body` 同时给出抛 ValidationFailed。
- [ ] T008 单测（`backend/tests/unit/`）：变量作用域四场景（spec US4 场景 1–4，ChainMap 优先级 + output_var 恒 case 级 + scope=execution 写入）；`element_requirement` 新规则（switch_to_iframe 三形态、download_file、互斥 422 语义）；`reset_case_scope` 基类契约。**验收**：`pytest -q` 全绿（新增用例不计回归）。

## Phase 3 — US1 网络 mock 与响应检索（P1）

Story: spec US1 · Independent Test: quickstart §1–§2

- [ ] T009 `backend/app/engines/adapters/playwright_adapter.py`：`start()` 挂 `page.on("response")` 收集器（`collections.deque(maxlen=500)`，记录 ts/url/status/method）；`stop()` 随会话清理；收集器异常吞掉只记日志（不影响主流程）。
- [ ] T010 `playwright_adapter.py`：实现 `mock_route`（`page.route` + `_active_routes: dict[(pattern, method), ...]`；abort=true 走 `route.abort()`；status/content_type/body/json 组装 fulfill；同 key 后写覆盖 = 先 unroute 再 route）与 `unmock_route`（key 精确移除 + `page.unroute`；不存在抛 ValidationFailed）；`reset_case_scope()` 覆写：`unroute_all()` + `_frame_stack.clear()` + `_active_routes.clear()`。
- [ ] T011 `playwright_adapter.py`：实现 `wait_for_response`（`ctx.timeout_ms` 窗口轮询收集器，匹配 `ts >= ctx.case_started_ts`、pattern、可选 method/expect_status；命中返回 `{url, status, method}` 经 output_var 入 case 变量；超时抛 ValidationFailed 且 message 附最近 5 条 `url+status` 摘要）。
- [ ] T012 `scripts/serve_fixtures.py`：新增 mock 演示页（页面脚本 fetch `/api/demo` 并渲染成功/失败两态）与 fixture 端点 `/api/demo`（返回 `from-real`）。
- [ ] T013 单测（新增 `backend/tests/unit/test_playwright_network.py`，沿用既有适配器测试基建/fake page 方式）：mock 生效返回声明体、abort 中断、同 key 覆盖、解除不存在报错、收集器检索命中与 expect_status 过滤、超时近邻摘要、reset_case_scope 后 mock 失效。**验收**：`pytest -q` 全绿。

## Phase 4 — US2 下载产物化（P2）

Story: spec US2 · Independent Test: quickstart §3

- [ ] T014 `playwright_adapter.py`：实现 `download_file`（`expect_download` 包裹绑定元素 click；保存 `{settings.artifacts_dir}/exec-{ctx.execution_id}/downloads/{seq}-{suggested_filename}`，重名 seq 前缀防覆盖；`ctx.artifacts.append(kind=DOWNLOAD)`；output_var=最终文件名；超时自然失败 message 明确）。
- [ ] T015 `scripts/serve_fixtures.py`：新增 `/downloads` 页（attachment 链接，服务端 Content-Disposition）。核对前端产物列表/报告对 kind=DOWNLOAD 的展示兼容性（T002 结论；仅当有白名单渲染时补一个分支/图标文案）。
- [ ] T016 单测（`test_playwright_download.py`）：产物登记路径/大小、重名前缀、output_var 文件名、无下载超时失败。**验收**：`pytest -q` 全绿。

## Phase 5 — US3 iframe 按元素（P3）

Story: spec US3 · Independent Test: quickstart §4

- [ ] T017 `playwright_adapter.py`：`switch_to_iframe` 增加元素形态——`chain` 非空时走 `element_handle().content_frame()` 入栈；命中非 iframe 节点抛 ValidationFailed（message 说明命中了什么）；`chain is not None and index is not None` 执行口同样拒绝（防御，写入口已拦）。
- [ ] T018 前端（仅当 T002 有硬编码）：编排页允许 switch_to_iframe / download_file 绑定元素；若无硬编码则记录"零改动"结论。`scripts/serve_fixtures.py`：双 iframe 页 + 调换序变体页。
- [ ] T019 单测（`test_playwright_iframe_element.py`）：按元素进入后定位落在 iframe 内、弹栈回主文档、非 iframe 报错、互斥拒绝；顺序无关性用两个 fixture 变体页各断言一次。**验收**：`pytest -q` 全绿。

## Phase 6 — US4 执行级变量端到端（P3）

Story: spec US4（实现主体在 T003/T006）· Independent Test: quickstart §5

- [ ] T020 集成级单测（`backend/tests/` 沿用执行服务测试基建）：套件 A/B 两用例——execution 变量跨用例可见、case 同名覆盖、缺省 scope 对照组、二次执行变量不残留。**验收**：`pytest -q` 全绿。

## Phase 7 — Polish & Cross-Cutting

- [ ] T021 `scripts/smoke_m38.py`：覆盖 quickstart §1–§5 全部验收场景（含泄漏检查、互斥 422、产物取回一致、顺序无关、变量对照），输出 V1–Vn 逐项 PASS/FAIL，对齐既有冒烟脚本风格。
- [ ] T022 回归门禁全绿：`pytest -q`（基线 275+new）· `ruff check` · `lint-imports`（2 kept）· `audit_status.py --check` · `alembic check` · 既有五册 Web 冒烟（m3/m32/m34/m35/m36）零回归 —— 一条命令 `bash scripts/ci_local.sh` + 五册冒烟。
- [ ] T023 文档收尾：`scripts/gen_seed_sql.py` 重新生成 `backend/sql/seed_action_catalog.sql`（55 条，含 NETWORK category 白名单核对）；更新 `docs/api.md`（/actions 数量与新 schema）、`README`（能力计数）、`CHANGELOG.md`；《docs/待办与缺口跟踪.md》GAP-09/10/12/13 置 ✅ 并附证据命令（引 specs/001 为施工图）；《实现踩坑清单》回填 R5 发现的 frame 栈跨用例泄漏隐患修复。
- [ ] T024 `docs/HANDOVER.md` 更新（当前状态/下一步/字典 55 条/新决策 D45 记录本批次语义），commit + push（代理命令见 HANDOVER §4）。

## Dependencies & Execution Order

```text
T001/T002 → T003–T007（T005 依赖 T001 结论决定是否补 seed 步骤）
T003–T007 → T008 → US1（T009–T013）→ US2（T014–T016）→ US3（T017–T019）→ US4（T020）→ T021–T024
```

## Parallel Execution Examples

- **US2/US3/US4 的 fixture 页与单测编写**（T012/T015/T018/T016/T019/T020）相互独立，可并行起草；adapter 实现任务（T010/T011/T014/T017）同文件，**必须串行**。
- 单测编写（T008）可与 T009/T012 并行（接口形状以 contracts 为准先行）。

## Implementation Strategy

- MVP = Phase 2 + US1（mock 是价值核心）；US2/US3 增量交付；US4 收尾（改动最小、依赖 Phase 2 基建）。
- 每阶段验收 = `pytest -q` 全绿再进下一阶段；禁止带着红测试前进（Constitution I/II）。
- 冻结项扩展（set_variable / switch_to_iframe）在 T023 设计留痕前不得合入主干文档快照。
