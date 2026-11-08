# Data Model: Web 执行能力补齐（M3.8）

> Phase 1 产物。结论先行：**零新表、零列变更、零 Alembic 迁移**。全部数据影响面如下。

## 1. 受影响实体总览

| 实体 | 变更类型 | 说明 |
|---|---|---|
| `action_catalog`（表） | **行新增 ×4**（启动 seed 自动） | mock_route / unmock_route / wait_for_response / download_file；category 新值 `NETWORK` |
| `artifact`（表） | **无 DDL 变更**，kind 新值 `DOWNLOAD` | `kind` 为 VARCHAR(32)（schema.sql:270），非 DB 枚举；应用层无白名单校验（登记走 `_record` 透传） |
| `test_step`（表） | 无变更 | switch_to_iframe 按元素 = 复用既有 `element_id` 列 + `params.index` 互斥校验 |
| 执行级变量 | **纯内存态**，不落库 | 随单次执行创建、执行结束销毁（research R8） |
| 网络响应收集器 | **纯内存态**，不落库 | deque(maxlen=500)，随 adapter 会话生命周期（research R4） |

## 2. action_catalog 新增行（契约详情见 contracts/action-schema.md）

| action_key | category | platforms | engines | requires_element | required |
|---|---|---|---|---|---|
| `mock_route` | NETWORK（新值） | WEB | playwright | 0 | pattern |
| `unmock_route` | NETWORK | WEB | playwright | 0 | pattern |
| `wait_for_response` | NETWORK | WEB | playwright | 0 | pattern |
| `download_file` | ELEMENT | WEB | playwright | 1 | （无 params 必填） |

- `set_variable`：props 新增可选 `scope`（enum: case/execution，默认 case）——**参数扩展，行内容随 seed 更新**。
- `switch_to_iframe`：props 语义扩展（index 与元素绑定互斥）——schema 本身不变（index 本就可选），**校验规则变更留痕于设计文档变更记录**。

## 3. artifact.kind 取值域（扩展后）

`SCREENSHOT`（既有，步骤级）· `TRACE` / `VIDEO` / `HAR`（既有，执行级）· **`DOWNLOAD`（新增，步骤级，走 step_result_id 挂靠）**

- 登记路径：适配器 `ctx.artifacts.append(...)` → 执行器 `_record` 落库（FR34，与 SCREENSHOT 同通道）。
- 下载文件物理位置：`{artifacts_dir}/exec-{id}/downloads/`，与 trace/video/har 同级，纳入既有产物目录组织与下载接口防护（归属 + realpath 校验自动生效）。

## 4. 执行级变量（内存态）生命周期

```text
execute() 开始 ──► execution_vars = {}
                    │
      每用例 ──────► ActionContext(variables=case_vars, shared_variables=execution_vars)
                    │     读取: ChainMap(case_vars, execution_vars)  # case 优先
                    │     写入: set_variable(scope=case,默认) → case_vars
                    │           set_variable(scope=execution) → execution_vars
                    │           其余动作 output_var → case_vars（不变）
      用例边界 ────► adapter.reset_case_scope()   # mock/frame 栈清理，变量不受影响
                    │
execute() 结束 ──► execution_vars 随作用域销毁（不落库、不跨执行）
```

## 5. 校验规则（写入口与执行口共用）

| 规则 | 错误 | 生效点 |
|---|---|---|
| `switch_to_iframe` 同时绑定元素与 `index` | ValidationFailed | `case_service`（写）+ `execution_service`（执行） |
| `download_file` 未绑定元素 | ValidationFailed | 同上（经 `_special_element_need` 统一规则） |
| `unmock_route` 解除未声明模式 | ValidationFailed | playwright_adapter 执行时 |
| `wait_for_response` 超时无匹配 | ValidationFailed（message 附近邻响应摘要） | playwright_adapter 执行时 |
| mock `json` 与 `body` 同时给出 | ValidationFailed | `case_service` 写入口（schema 层面）+ 适配器防御 |
