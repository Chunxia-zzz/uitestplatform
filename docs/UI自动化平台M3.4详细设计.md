# UI 自动化平台 · M3.4 详细设计：一键接入（Scaffold）

| 项 | 内容 |
|---|---|
| **文档编号** | D2-M3.4 |
| **版本** | v1.1 |
| **日期** | 2026-10-19 |
| **上游依赖** | D1 技术方案（D1–D6）· D2-M1（适配层）· D2-M2（元素库）· D2-M3（执行内核 / 四层模型） |
| **本文性质** | 施工图。回答"一条 URL + 一组动作，如何自动装配成可执行的用例集并跑起来" |
| **状态** | ✅ **已实现**（`POST /scaffold` + `/scaffold` 页面），见 §7 实现记录 |

---

## 0. 目标与边界

### 0.1 一句话目标

> 给一个网页地址 + 一组操作动作，平台**一次调用**完成
> **建项目 → 建执行目标 → 建元素 + 定位符 → 建用例 + 步骤 → 建用例集 → 触发执行**，
> 并返回从项目到执行的完整 id 链。

这条链路把 M1–M3.3 已有的能力**串起来**，本身不引入新的执行语义 ——
它是"编排层的编排"：把四层模型（项目 / 用例集 / 用例 / 元素）的创建动作合成一个入口。

### 0.2 为什么需要它

现有流程要人工走 5 个页面、7 次保存：建项目 → 配执行目标 → 录元素与定位符 →
编用例步骤 → 建用例集加成员 → 点运行。一个新页面接进来，光"接线"就要十几分钟。

Scaffold 把这个过程压成一份 JSON。它的价值不在"少点几次"，而在**可版本化**：
同一份 scaffold 输入可以进 Git、可以在 CI 里重放、可以作为"这个页面该怎么测"的文档。

### 0.3 明确不做

| 不做 | 理由 |
|---|---|
| **元素拾取器**（打开页面点选元素自动生成定位符） | D14 已决策不做；Scaffold 的元素定位符由输入提供 |
| **AI 生成用例** | 不在本期；输入是"人给出的动作"，不是自然语言 |
| **执行结果断言**（跑完判断"页面是否真的对") | 断言是动作（`assert_*`），由输入自己带；Scaffold 只负责装配与触发 |
| **多页面/多项目的批量接入** | 一次调用一个 `(project.code, url, actions)` 组合 |
| **跨项目元素共享** | D16 仍不启用 |

### 0.4 与既有决策的关系

| 决策 | 对本篇的约束 |
|---|---|
| **D1 只借鉴架构** | 本篇从零实现，不参考任何上游代码 |
| **D5 端只有 3 个** | `platform ∈ {WEB, ANDROID, IOS}`；本期只支持 `WEB`（Appium 仍是桩） |
| **D14 不做拾取器** | 定位符必须由输入提供，且**必填** —— 没有"自动猜"的兜底 |
| **D17 文档顺序** | 本篇作为 M3.2 之后的新批次插入，编号 M3.4（M3.3 已用于用例集） |
| **D26 削减平台管理** | 不引入新的权限/审批；接口无鉴权，与全站一致 |

---

## 1. 处理流程、依赖与衔接

### 1.1 七步链路（严格串行）

```
输入: { url, actions[], elements[], project{...}, case{...}, suite{...} }
  │
  ├─ S0  静态校验（不碰数据库）
  │      URL 合法 · actions 非空 · 动作存在 · params 匹配 schema
  │      · 每个元素动作都能解析到元素声明 · 定位符类型与端/引擎匹配
  │      失败 → 422，**不产生任何数据**
  │
  ├─ S1  Project          幂等键: code
  │      out: project_id
  ├─ S2  ExecutionTarget  幂等键: (project_id, base_url)
  │      out: target_id   ← project.target_id 回写
  ├─ S3  Element(V1.0)    幂等键: (project_id, parent_id=0, element_name)
  │      out: element_id[]
  ├─ S4  ElementLocator   幂等键: (element, platform, engine, type, value)
  │      out: locator_id[]
  ├─ S5  TestCase + TestStep
  │      幂等键: (project_id, title)；seq = 动作在输入中的序号（从 1 起）
  │      out: case_id, step_id[]
  ├─ S6  TestSuite + TestSuiteCase
  │      幂等键: (project_id, name) / (suite_id, case_id)
  │      out: suite_id
  └─ S7  Execution        （仅当 run=true）
         out: execution_id（202 语义，异步执行）
```

**为什么必须是这个顺序**：每一步的输入都包含前一步的产物（`target.project_id`、`element.project_id`、
`locator.element_id`、`step.element_id`、`suite_case.case_id`、`execution.suite_id`）。
没有任何一步可以并行或提前 —— 这不是约定，是外键语义决定的。

### 1.2 各步输入 / 输出 / 依赖

| 步 | 输入 | 输出 | 依赖 | 失败后果 |
|---|---|---|---|---|
| **S0** | 整个请求体 | 规范化后的 `NormalizedSpec`（内存对象） | 无（纯函数） | 返回 422；**零写入** |
| **S1** | `project{name, code, platform, engine_key}` | `project_id`、`created` | S0 | 之后全部中止 |
| **S2** | `url` 解析出的 origin、`target.options` | `target_id`、`created` | S1 | 补偿删 S1（若本次新建） |
| **S3** | `elements[]`（name / description） | `element_id[]`、`created[]` | S1 | 补偿删 S1–S2 |
| **S4** | `elements[].locators[]` | `locator_id[]` | S3 | 补偿删 S1–S3 |
| **S5** | `actions[]` + `element_key → element_id` 映射 | `case_id`、`step_id[]` | S3（元素动作） | 补偿删 S1–S4 |
| **S6** | `case_id` | `suite_id` | S5 | 补偿删 S1–S5 |
| **S7** | `suite_id` | `execution_id` | S6 | 资产保留（已经建好了），返回 warnings |

> **S7 失败不回滚资产**：用例集已经建好，执行失败（例如队列满）是运行时问题，
> 回滚资产会让用户白填一遍。返回 `execution=null` + `warnings`，用户可稍后手动运行。

### 1.3 事务边界：为什么是"补偿"而不是"回滚"

现有服务（`element_service.create` / `locator_service.create` / `case_service.create_step` /
`suite_service.create`）**各自 commit**，并且这些签名已在 M1/M2/M3 冻结。
Scaffold 不修改它们，因此无法把 7 步包进一个事务。

所以采用**两段式**：

1. **S0 全量静态校验**——把"能提前发现的错误"全部挡在写库之前。
   这一步是主力：绝大多数错误（动作写错、缺定位符、参数不符 schema）根本走不到 S1。
2. **补偿删除**——只兜"写库中途抛异常"这种低概率情形。逆序软删本次新建的
   `suite → case → element → target → project`。软删后同名可重建（`deleted_seq` 机制）。

> **诚实边界**：补偿是"尽力而为"，不是数据库级原子性。极端情况（补偿删除本身失败）
> 会留下孤儿行。这些行在 API 层不可见（全部按 `is_deleted` 过滤），但会在 DB 里。
> 验收标准里不承诺"DB 零残留"，只承诺"**API 视角无残留**"。

### 1.4 幂等语义（重复提交同一份输入）

| 对象 | 幂等键 | 命中时的行为 |
|---|---|---|
| Project | `code`（仅未删） | 复用；`platform`/`engine_key` 不一致 → **409 `SCAFFOLD_PROJECT_CONFLICT`** |
| ExecutionTarget | `(project_id, base_url)` | 复用，更新 `options`（以本次输入为准） |
| Element | `(project_id, parent_id=0, element_name)` | 复用；不覆盖 `description` |
| ElementLocator | `(element_id, platform, engine_key, type, value)` | 跳过已存在；缺的补上 |
| TestCase | `(project_id, title)` | `strategy=reuse`（默认）→ 复用，**不动步骤**；`recreate` → 软删旧用例后新建 |
| TestSuite | `(project_id, name)` | 复用；缺失的成员补上 |
| TestSuiteCase | `(suite_id, case_id)` | 跳过 |
| Execution | 无（事件不可幂等） | **每次 run=true 都新建一次** |

**验收口径**：同一份输入连提两次 → 前 6 类 id **完全不变**，只有 `execution.id` 递增。

### 1.5 元素来源：只接受显式声明（D14 的必然结果）

Scaffold 不做拾取，所以元素必须由输入给出。规范化形态是：

```jsonc
"elements": [
  { "key": "username", "name": "用户名输入框",
    "locators": [ { "locator_type": "testid", "locator_value": "username" } ] }
],
"actions": [
  { "action_key": "input", "element_key": "username", "params": { "text": "jerry" } }
]
```

- `key` 只在**本次请求内**有效，用于动作引用，不落库。
- 一个元素可带多条定位符 → 形成回退链（`priority` 由字典的 `rank` 决定）。
- **前端**允许用户在动作行里直接填元素名与定位符，提交前由前端拆成 `elements + actions`
  （见 §4.2）。后端只认规范化形态 —— 保持 API 一种写法，避免两套校验。

---

## 2. 后端设计

### 2.1 模块划分

| 文件 | 职责 |
|---|---|
| `app/schemas/scaffold.py`（新） | 请求/响应模型 + 规范化（`NormalizedSpec`） |
| `app/services/scaffold_service.py`（新） | S0–S7 编排、幂等查询、补偿 |
| `app/api/v1/scaffold.py`（新） | `POST /scaffold` 端点 |
| `app/core/errors.py` | 新增 4 个错误码 |
| `app/domain/action_keys.py` | `navigate` 增加 `wait_until`（GAP-11） |
| `app/engines/adapters/playwright_adapter.py` | `navigate` 透传 `wait_until` |

**分层约束**：`scaffold_service` 只能依赖 `domain` / `models` / 其他 `services`，
**不得直接 import 适配器**（import-linter 契约已覆盖 `element_service`，本篇同样适用）。

### 2.2 规范化（S0）的具体规则

```python
@dataclass
class NormalizedAction:
    seq: int
    action_key: str
    element_key: str | None
    params: dict
    output_var: str | None
    timeout_ms: int | None
    on_failure: str
    retry_times: int
```

校验顺序（任一失败即 422，**全部在写库前**）：

1. `url.startswith(("http://", "https://"))` → 否则 `SCAFFOLD_INVALID_URL`
2. `actions` 非空 → 否则 `SCAFFOLD_EMPTY_ACTIONS`
3. 每个 `action_key` 存在于 `ACTION_BY_KEY` → 否则 `VALIDATION_ERROR`（复用）
4. `params` 通过 `jsonschema.validate` → 否则 `VALIDATION_ERROR`
5. `requires_element` 与 `element_key` 必须一致：
   - 需要元素但没给 → `SCAFFOLD_ELEMENT_REQUIRED`
   - 不需要元素却给了 → `SCAFFOLD_ELEMENT_UNEXPECTED`
   - **特例**：`screenshot` + `target=element` 需要元素（复用 `case_service._special_element_need`）
6. 每个 `element_key` 必须能在 `elements[]` 里找到 → 否则 `SCAFFOLD_UNKNOWN_ELEMENT_KEY`
7. 每个元素至少 1 条定位符 → 否则 `SCAFFOLD_ELEMENT_WITHOUT_LOCATOR`
8. 定位符类型必须被 `(platform, engine_key)` 支持（`locator_service.validate_type`）
9. 元素 `name` 在请求内唯一；`key` 唯一

> 第 8 条复用已有的 `validate_type`，不另写一套字典 —— **一处事实，一处定义**。

### 2.3 执行目标（S2）

- `base_url` = `url` 的 `scheme://host[:port]`（**不含 path**）。
  步骤里的 `navigate` 用**相对路径**（`/login.html`），这样换环境只改 `base_url`。
- 若输入动作里的 `navigate.url` 是绝对 URL，原样保留（允许跨站跳转）。
- `target.options` 透传（viewport / device / storage_state 等），默认为空对象。

### 2.4 步骤生成（S5）

- `seq` = 动作在 `actions[]` 中的下标 + 1（**与输入顺序一致，不排序**）。
- `element_key` → `element_id` 查表替换。
- `navigate` 若无 `wait_until`，**Scaffold 生成的步骤补默认值 `load`**：
  一键接入场景下 `domcontentloaded` 经常拿不到 SPA 的元素，`load` 更稳。
  这条只影响 Scaffold 生成的步骤，不影响手写用例（手写默认仍由动作字典决定）。

### 2.5 补偿删除顺序

```
suite(软删) → case(软删) → locator(物理删) → element(软删) → target(物理删) → project(软删)
```

只删**本次 created=true** 的对象；复用的对象绝不删。

---

## 3. 接口契约

### 3.1 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/v1/scaffold` | 一次完成 S1–S7；`run=false` 时只建资产 |

### 3.2 请求

```jsonc
{
  "project": {
    "name": "Demo Web 中台",
    "code": "demo-web-scaffold",
    "platform": "WEB",
    "engine_key": "playwright",
    "description": "可选"
  },
  "url": "http://127.0.0.1:8899/login.html",
  "case": { "title": "登录主链路", "strategy": "reuse" },
  "suite": { "name": "冒烟回归", "schedule_cron": null },
  "elements": [
    { "key": "username", "name": "用户名输入框",
      "locators": [{ "locator_type": "testid", "locator_value": "username" }] },
    { "key": "submit", "name": "登录按钮",
      "locators": [
        { "locator_type": "testid", "locator_value": "submit-not-exist" },
        { "locator_type": "css", "locator_value": "#submit" }
      ] }
  ],
  "actions": [
    { "action_key": "navigate", "params": { "url": "/login.html" } },
    { "action_key": "input", "element_key": "username", "params": { "text": "jerry" } },
    { "action_key": "click", "element_key": "submit", "params": {} }
  ],
  "run": true
}
```

字段说明：

| 字段 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `project.code` | ✅ | — | 幂等键，全局唯一（未删范围内） |
| `project.platform` / `engine_key` | ✅ | — | 本期只允许 `WEB` / `playwright` |
| `url` | ✅ | — | 绝对 URL，用于推导 `base_url` |
| `actions` | ✅ | — | ≥1 条 |
| `elements` | 条件 | `[]` | 凡动作引用元素就必须声明 |
| `case.title` | ✅ | — | 用例标题（也是幂等键） |
| `case.strategy` | — | `reuse` | `reuse` / `recreate` |
| `suite.name` | ✅ | — | 用例集名（幂等键） |
| `run` | — | `true` | 是否创建后立即执行 |

### 3.3 响应（200）

```jsonc
{
  "project":  { "id": 3, "code": "demo-web-scaffold", "created": true },
  "target":   { "id": 4, "base_url": "http://127.0.0.1:8899", "created": true },
  "elements": [
    { "id": 21, "name": "用户名输入框", "created": true, "locator_ids": [41] },
    { "id": 22, "name": "登录按钮",   "created": true, "locator_ids": [42, 43] }
  ],
  "case":     { "id": 12, "title": "登录主链路", "created": true, "step_ids": [71, 72, 73] },
  "suite":    { "id": 5, "name": "冒烟回归", "created": true, "case_count": 1 },
  "execution": { "id": 88, "status": "PENDING", "queued_at": "2026-10-19T16:02:11" },
  "warnings": [
    "navigate 未指定 wait_until，已按 load 生成（SPA 场景更稳）"
  ],
  "duration_ms": 143
}
```

`execution = null` 的情形：`run=false`，或 S7 失败（此时 `warnings` 里有原因）。

### 3.4 错误码（新增 6 个）

| 码 | HTTP | 含义 |
|---|---|---|
| `SCAFFOLD_INVALID_URL` | 422 | URL 不是 http/https |
| `SCAFFOLD_EMPTY_ACTIONS` | 422 | 动作清单为空 |
| `SCAFFOLD_UNKNOWN_ELEMENT_KEY` | 422 | 动作引用了未声明的元素 key |
| `SCAFFOLD_ELEMENT_WITHOUT_LOCATOR` | 422 | 元素没有任何定位符 |
| `SCAFFOLD_ELEMENT_REQUIRED` | 422 | 动作需要元素但未提供 |
| `SCAFFOLD_ELEMENT_UNEXPECTED` | 422 | 动作不需要元素却提供了 |
| `SCAFFOLD_PROJECT_CONFLICT` | 409 | `code` 已存在但 `platform`/`engine_key` 不一致 |

> 优先复用 `VALIDATION_ERROR`（动作不存在 / 参数不符 schema / 定位类型不支持），
> 只有"Scaffold 特有的结构问题"才新增码 —— 错误码表不为一个端点膨胀。

---

## 4. 前端设计

### 4.1 页面：`/scaffold`（快速接入）

三段式：

```
┌─ 输入 ────────────────────────────────────────────────┐
│ 网页地址 [http://127.0.0.1:8899/login.html          ]   │
│ 项目 code [demo-web-scaffold]  名称 [...]  端/引擎 [WEB/playwright] │
│ 用例标题 [登录主链路]   用例集 [冒烟回归]               │
├─ 动作清单（可增删、可上下移）───────────────────────────┤
│ # │ 动作 │ 元素名 │ 定位符（类型+值，可多条）│ 参数      │
│ 1 │navigate│  —   │ —                        │ url=...  │
│ 2 │input   │用户名│ testid=username          │ text=... │
├─ 结果 ────────────────────────────────────────────────┤
│ ✅ 项目 #3 · 元素 2 个 · 用例 #12 · 用例集 #5 · 执行 #88 │
│ [查看执行结果]  [查看报告]                              │
└───────────────────────────────────────────────────────┘
```

### 4.2 前端的两处"便捷 → 规范"转换

1. **元素内联 → `elements[]`**：用户在某行填了元素名 + 定位符，
   提交前按 `name` 去重聚合成 `elements`，动作改写为 `element_key`。
2. **参数表单**：复用 M3.2 的 `SchemaParams` 组件（按 `params_schema` 生成），
   不另写一套 —— 否则两处的参数校验会漂移。

### 4.3 交互细节

- 动作行支持"加一条定位符"（回退链直接可见）。
- 「生成并运行」按钮在提交期间禁用，避免重复提交产生两条执行。
- 结果面板的 id 全部可点击：项目 → 元素库；用例 → 用例编排；执行 → 执行详情。
- 失败时展示 `error.code` + `detail`（与全站统一错误信封一致）。

---

## 5. 测试与验收

### 5.1 单元测试（`tests/unit/test_scaffold_service.py`）

| # | 用例 | 断言 |
|---|---|---|
| 1 | 最小输入（1 元素 + 2 动作） | 7 个 id 齐全，`case.steps` 的 `element_id` 正确 |
| 2 | 幂等：同输入两次 | project/element/case/suite id 不变；`created=false`；步骤数不翻倍 |
| 3 | `case.strategy=recreate` | 旧用例软删，新用例 id 不同 |
| 4 | 项目 code 冲突（platform 不同） | 409 `SCAFFOLD_PROJECT_CONFLICT` |
| 5 | URL 非法 | 422，且**未创建任何项目** |
| 6 | 动作引用未声明 key | 422 `SCAFFOLD_UNKNOWN_ELEMENT_KEY`，零写入 |
| 7 | 元素无定位符 | 422 `SCAFFOLD_ELEMENT_WITHOUT_LOCATOR` |
| 8 | 动作缺元素 / 多给元素 | 422，两个不同码 |
| 9 | 定位符类型与端不匹配（如 iOS 配 css） | 422（复用 `validate_type`） |
| 10 | 多定位符 | 按 rank 形成 priority，首条 `is_primary=1` |
| 11 | `navigate` 未写 `wait_until` | 生成步骤带 `wait_until=load` + warning |
| 12 | `run=false` | `execution=null`，资产齐全 |

### 5.2 端到端（`scripts/smoke_m34.py`）

真跑浏览器，链路必须 PASSED：

| # | 检查 | 判定 |
|---|---|---|
| V1 | `POST /scaffold` 返回 200 | 7 个 id 非空 |
| V2 | 元素定位符落库 | `GET /elements/{id}/locators` 条数 = 输入条数 |
| V3 | 步骤绑定正确 | `GET /cases/{id}` 的 `steps[].element_id` ∈ 元素 id |
| V4 | 执行终态 | `PASSED`，且 `click` 步 `fallback_index=1`（首条定位符故意写错） |
| V5 | 报告 | `GET /executions/{id}/report` 含用例集名 |
| V6 | 幂等 | 再提交一次：前 6 类 id 不变，execution.id 变大 |
| V7 | 失败不残留 | 非法 URL / 未知 key 各一次 → 4xx，且项目 code 查不到 |
| V8 | `run=false` | 资产齐全、`execution=null` |

### 5.3 验收时重点检查的 5 个关键节点

1. **id 链自洽**：`steps[].element_id` ⊂ `elements[].id`；`suite.case_count=1`；
   `execution.suite_id == suite.id`；`execution.case_ids == [case.id]`。
2. **幂等真的生效**：第二次提交 `created` 全为 false，且**步骤没有翻倍**
   （这是最容易写错的地方：复用了 case 却又追加了一遍 steps）。
3. **执行真的跑了**：`status=PASSED`、`duration_ms > 0`、报告文件非空；
   若首条定位符故意写错，`fallback_index=1` 证明回退链在工作。
4. **失败真的没留垃圾**：非法输入后按 code 查项目 → 404；
   这条比"成功路径"更能说明补偿/前置校验有效。
5. **报告可追溯**：报告抬头显示用例集名与端/引擎，而不是"临时用例"。

---

## 6. 对后续批次的接口冻结声明

| # | 冻结项 | 变更影响 |
|---|---|---|
| **FR54** | `POST /scaffold` 的请求/响应结构（§3.2 / §3.3） | 前端与脚本全改 |
| **FR55** | 七步顺序 S1→S7 固定，不得并行或调换 | 外键语义会崩 |
| **FR56** | 幂等键定义（§1.4）：`project.code` / `(project_id, name)` / `(project_id, title)` | 幂等语义变，重复接入会产生脏数据 |
| **FR57** | 静态校验（S0）必须在写库前完成；失败时零写入 | 退化成"先建后删"，失败会留残留 |
| **FR58** | `navigate.wait_until` 参数取值 `commit/domcontentloaded/load/networkidle`（GAP-11）；Scaffold 生成时默认 `load` | 手写用例默认不变，仍是动作字典默认 |
| **FR59** | 本期 `platform` 只允许 `WEB`；其余端返回 422 | 放开需先实现 M4 适配器 |

---

## 7. 实现记录（2026-10-19 交付）

### 7.1 落点

| 层 | 文件 | 说明 |
|---|---|---|
| 请求模型 | `backend/app/schemas/scaffold.py`（新） | 6 个模型；`locators` 用 `min_length=1` 在 Pydantic 层先拦一次 |
| 编排服务 | `backend/app/services/scaffold_service.py`（新） | `normalize()` / `_precheck_project()` / `validate_locator_types()` / 7 个 `_ensure_*` / `_compensate()` / `run()` |
| 端点 | `backend/app/api/v1/scaffold.py`（新） | `POST /scaffold` |
| 复用改造 | `case_service.validate_action()` / `element_requirement()` / `create_case()` | 把"动作校验"从"具体 element_id"解耦，Scaffold 与 Cases API 共用一份规则 |
| GAP-11 | `action_keys.py` + `playwright_adapter.navigate()` | `wait_until ∈ {commit, domcontentloaded, load, networkidle}`，默认仍是 `domcontentloaded` |
| 前端 | `views/ScaffoldView.vue`（新）+ `components/SchemaParams.vue`（新） | 参数表单抽成公共组件，CasesView 同步改用（去掉一套重复实现） |
| 测试 | `tests/unit/test_scaffold_service.py`（20 条）+ `scripts/smoke_m34.py`（30 项） | 见 §7.3 |

### 7.2 实现期修正的两处设计偏差

| # | 偏差 | 修正 |
|---|---|---|
| **F-M3.4-1** | 原设计在 `normalize()` 里同时校验"只支持 WEB"和"定位类型与端匹配" | 会导致**已存在的 Android 项目**报"定位类型不属于 ANDROID"而不是更准确的 `SCAFFOLD_PROJECT_CONFLICT`。改为三段：结构校验 → 项目判定（冲突/端支持）→ 定位类型校验 |
| **F-M3.4-2** | 原设计假设 `case` 复用就完全不碰步骤 | 若复用的用例**没有任何步骤**（历史遗留/手动建的空用例），用例集跑起来是"0 步通过"，会骗过所有人。改为：有步骤则整体复用；无步骤则补步骤 |

### 7.3 验证结果

| 命令 | 结果 |
|---|---|
| `pytest -q` | **134 passed**（+20：装配 2 / 幂等 4 / 幂等边界 1 / 前置校验 8 / 执行衔接 3 / 软删回收 1 / 其他 1） |
| `scripts/smoke_m34.py` | **30/30**（V1 8 · V2 1 · V3 4 · V4 4 · V5 1 · V6 5 · V7 4 · V8 2 · 清理） |
| `scripts/smoke_m32.py` | **24/24** 回归 |
| `scripts/smoke_ui.py` | **9/9**（新增 `/scaffold` 页面 + "载入示例→生成并运行"交互） |
| `lint-imports` / `alembic check` | 2 kept / 无差异 |

端到端的关键证据：

- `POST /scaffold` **一次调用**返回 project/target/4 个 element/case(7 步)/suite/execution；
- 执行 `PASSED`，`click` 步 **`fallback_index=1`**（首条定位符故意写错，回退链生效）；
- 同输入第二次提交：前六类 id 全不变、**步骤数仍为 7 不翻倍**，只有 `execution.id` 递增；
- 非法 URL / 未知 element_key：422 且按 code **查不到项目**（前置校验真的在写库之前）。

### 7.4 已知限制

| 限制 | 说明 |
|---|---|
| 只支持 `WEB` | `platform != WEB` 且项目不存在 → 422；已存在且端不一致 → 409。放开要等 M4 适配器 |
| 无 AI 生成 | 动作与定位符都由输入给出（D14 不做拾取器） |
| 补偿非事务 | 底层服务各自 commit（签名已冻结），补偿只保证 **API 视角**无残留 |
| 每个项目只建一个 target | 以 `base_url` 为幂等键；同一项目多套环境（dev/staging）会建多个 target，但 `project.target_id` 只指向最后匹配的那个 |

---

## 变更记录

| # | 日期 | 条目 | 依据 |
|---|---|---|---|
| 1 | 2026-10-19 | v1.0 初稿：七步链路、幂等矩阵、补偿语义、`POST /scaffold`、FR54–FR59 | 用户验收目标：URL + 动作 → 自动建项目/元素/用例/用例集并执行 |
| 2 | 2026-10-19 | **v1.1 已实现**：新增 §7 实现记录；修正两处设计偏差（校验顺序、空用例补步骤）；`SchemaParams` 抽为公共组件（CasesView 同步改造） | `pytest` 134 passed；`smoke_m34.py` 30/30；`smoke_ui.py` 9/9 |
