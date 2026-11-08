# Research: Web 执行能力补齐（M3.8）

> Phase 0 产物。每项决策格式：Decision / Rationale / Alternatives considered。
> 所有关键事实均已用代码核实（Constitution II）。

## R1 mock 的地址模式语法：Playwright 原生 glob

**Decision**: 地址模式直接用浏览器引擎的通配语法（`**/api/demo`、`*/api/*`），平台语义层不做二次翻译。
**Rationale**: URL 模式是纯 URL 语汇，不存在跨引擎语义差异（不像 locator 需要语义层/引擎语汇层分离）；做翻译层反而引入两套写法。本批次仅 WEB 端，无多引擎冲突。
**Alternatives**: 自定义正则语法（更精确但用例作者易写错，且需要转义处理）；语义 DSL（过度设计）。均否决。

## R2 动作拆分：3 个 mock 相关动作而非 1 个复合动作

**Decision**: `mock_route`（声明）/ `unmock_route`（解除）/ `wait_for_response`（等待检索）三个独立动作。
**Rationale**: 三者参数正交（声明要 body/status，解除只要 pattern，检索要过滤+output_var）；复合动作需要 mode 参数 + 条件必填，schema 复杂、校验分支多。D6「语义自明」优先。D12「单动作栈语义」的先例针对的是"进/出"互逆且参数极简的场景，此处不适用。
**Alternatives**: `network_mock(action=declare/remove/wait, ...)`——单动作多形态，params_schema 无法用 JSON Schema 必填表达"按 mode 变化的必填集"。否决。

## R3 mock 注册表与覆盖语义

**Decision**: 适配器维护 `_active_routes: dict[tuple[pattern, method], handler]`；同 (pattern, method) 重复声明 = 后者覆盖前者；`unmock_route` 按 key 精确移除，key 不存在抛 `ValidationFailed`；`reset_case_scope()` 清空注册表并 `unroute_all()`。
**Rationale**: FR-003 要求"解除不存在报明确错误"，Playwright 原生 `unroute` 对不存在模式静默 no-op，必须自建注册表记账；覆盖语义符合"最少惊讶"。
**Alternatives**: 不记账直接 unroute（无法满足 FR-003）；按 pattern 模糊匹配解除（通配写法差异导致误删）。均否决。

## R4 响应收集器与 wait_for_response 时间窗

**Decision**: adapter `start()` 即挂 `page.on("response")` 收集器（内存 deque，maxlen=500，记录 ts/url/status/method）；`wait_for_response(pattern, method?, expect_status?, output_var?)` 在 `ctx.timeout_ms` 窗口内轮询，匹配 `ts >= ctx.case_started_ts` 的最新一条；超时失败 message 附最近 5 条响应摘要。`ActionContext` 新增 `case_started_ts: float | None = None`（additive，执行器 `_run_case` 填充）。
**Rationale**: 动作串行执行，"先等后触发"会死锁（等的时候点击还没发生）；必须基于历史收集 + 参考时间过滤。参考时间取"当前用例开始"是精度与易用性的平衡点（spec Assumptions 允许 plan 定夺）。
**Alternatives**: 匹配全部执行历史（旧用例的响应会污染后续用例断言）；只匹配本步骤开始之后（错配"点击与等待分两步"的常见写法）。均否决。
**注**: 收集器与 trace/HAR 录制互不依赖（M3.6 诊断开关独立），maxlen 防长执行内存膨胀。

## R5 用例边界自动清理：适配器生命周期钩子

**Decision**: `EngineAdapter` 基类新增 `async def reset_case_scope(self) -> None: return None`（非动作，不进 action_catalog，同 `finalize_diagnostics` 先例）；Playwright 覆写为 `unroute_all() + _frame_stack.clear() + _active_routes.clear()`；执行器在**每个用例开始时**调用（前用例异常中断也能兜住）。
**Rationale**: FR-004 要求 mock 不跨用例泄漏；同执行串行复用 adapter 是 M3.1 既有语义。**顺带修复既有隐患**：当前 `_frame_stack` 跨用例不清理（用例 A 进 iframe 未退，用例 B 的定位全落在 iframe 里）——这是实现踩坑，回填《实现踩坑清单》。
**Alternatives**: 依赖用例作者显式 unmock/退栈（违背 FR-004，且容易漏）；执行结束统一清理（不满足用例边界隔离）。均否决。

## R6 下载：expect_download 包裹点击 + 产物通道复用

**Decision**: `download_file` 实现 = `async with page.expect_download(timeout=ctx.timeout_ms)` 包裹 `locator.click()`；文件保存到 `{artifacts_dir}/exec-{ctx.execution_id}/downloads/<seq>-<suggested_filename>`（重名用步骤 seq 前缀避免覆盖）；`ctx.artifacts.append({"kind": "DOWNLOAD", ...})`，落库由执行器既有逻辑完成；`output_var` 存最终文件名。
**Rationale**: FR34 语义（适配器只给路径事实）完全复用 screenshot 先例；artifact.kind 列是 VARCHAR(32)（schema.sql:270 已核实），新增 DOWNLOAD 值零迁移；产物下载接口的归属校验 + realpath 防护（M3.2 FR49）自动生效。
**Alternatives**: 新增下载专用表（过度设计）；适配器直接落库（违反 FR34）。均否决。

## R7 iframe 按元素：绑元素规则统一为一处

**Decision**: `case_service._special_element_need` 扩展两条：`switch_to_iframe` 绑定元素时需要 chain、`download_file` 恒需要元素；执行器 `execution_service` 的 `needs_element` 判断改为 import 同一函数（**写入口与执行口共用一份规则**，M3.2 踩坑先例）；`switch_to_iframe` 实现：`element_handle().content_frame()` 取 Frame 入栈，非 iframe 节点报 ValidationFailed；`index is not None and chain is not None` 组合在写入口与执行口均拒绝。
**Rationale**: 现状 `_special_element_need` 只认 `screenshot(target=element)`，是现成扩展点；"共用一份规则"是 M3.2 冻结原则（踩坑 13）。
**Alternatives**: 执行器无脑 resolve 所有绑定元素的步骤（省特判但让"绑元素无意义"的错配静默通过）；给 switch_to_iframe 加 use_element 开关参数（冗余，绑元素本身就是意图）。均否决。

## R8 执行级变量：双层视图 + 显式写入

**Decision**: `ActionContext` 新增 `shared_variables: dict`（additive，默认空 dict）；执行器 `execute()` 每次执行建一份 `execution_vars`，逐用例传入 ctx；`dispatch` 的参数渲染改传 `ChainMap(case_vars, execution_vars)`（render 函数零改动——它只做 Mapping 协议访问）；`set_variable` 内建 handler 读 `scope` 参数（`case` 默认 → `ctx.set_var`；`execution` → 新增 `ctx.set_shared_var`）；其余动作的 `output_var` 一律落 case 层（`set_var` 行为不变）。
**Rationale**: spec FR-012/013 与 Assumptions（output_var 恒为 case 级）一致；ChainMap 让"用例级优先、执行级兜底"成为读取路径的自然性质；执行结束 `execution_vars` 随栈帧销毁，满足"执行结束即失效、不落库"。
**Alternatives**: render 内部合并两个 dict（每步拷贝，浪费且可能变更丢失）；set_variable 直接写 ctx.variables 再区分命名空间前缀（变量名污染，用例作者可感知）。均否决。

## R9 字典与矩阵的同步成本：两处代码 + 自动 seed

**Decision**: 新动作落地 = `action_keys.py` 加 4 条 ActionDef（category 新增 `NETWORK`）+ `capabilities.py` `_WEB` 集合加 4 项；DB `action_catalog` 由启动 seed 自动同步（db.py:77 已核实存在 seed 逻辑，tasks 阶段确认其为 upsert 语义）；`seed_action_catalog.sql` 用 `scripts/gen_seed_sql.py` 重新生成（文件头声明勿手工编辑）；`audit_status.py --check` 自动覆盖新动作（矩阵声明 vs 适配器覆写强校验，CI 门禁）。
**Rationale**: 与 M4.1/M4.2 加动作的成本模型一致（踩坑 8：1 个适配器文件 + 3 处声明）。
**Alternatives**: 手工 INSERT DB（seed 会 DELETE+INSERT 冲突）；改 seed SQL 不改代码（违反"单一事实来源"声明）。均否决。

## 待 tasks 阶段核对的两个小项

1. `db.py` 启动 seed 对"已有 action_catalog 行"是否 upsert（若是仅首次插入，开发库需重新 seed 或手工补 4 行——CI 全新库不受影响）。
2. 前端编排页对"动作可否绑定元素"是否存在硬编码清单（若有，需与 `_special_element_need` 对齐）。
