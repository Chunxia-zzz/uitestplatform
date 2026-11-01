# UI 自动化平台 · M2 详细设计：元素库与多端 Locator

| 项 | 值 |
|---|---|
| **文档编号** | D2-M2 |
| **版本** | v1.0 |
| **日期** | 2026-10-19 |
| **上游依赖** | 《UI自动化平台技术方案》v1.0（D1–D6）· 《M1 详细设计》v1.1（D7–D13，已冻结） |
| **同链文档** | D0 技术选型报告 · D1 总技术方案 · D1a 移动端对接方案 · D2-M1 · **D2-M2 本文** · D2-M3/M4 · D3 工程约定 |
| **本文性质** | **施工图**。M1 回答"引擎怎么插进来"，本文回答"**元素资产怎么建、怎么定位、怎么验证**" |
| **状态** | 待评审 |

---

## 0. 本文定位与阅读指引

### 0.1 文档链中的位置

```
D0  技术选型报告          ← 为什么选这条路                 （已完成）
D1  总技术方案            ← 架构 / 数据模型 / 里程碑划分    （已完成）
D1a 移动端对接方案        ← 二期预留，不实现               （已完成）
D2-M1 项目骨架与适配层    ← 引擎可插拔，已冻结 v1.1         （已完成）
D2-M2 本文                ← 元素库与多端 Locator            ★你在读
D2-M3 / M4               ← 编排执行报告 / 扩端              （待写）
D3  工程约定              ← 目录 / 命名 / 错误码 / 日志 / Git （待写）
```

**阅读方式建议**：

| 你是 | 建议读 |
|---|---|
| 要评估工作量 | §1.2 交付物、附录 C 文件清单 |
| 要动手写代码 | §2 后端设计（逐文件）、附录 A/B |
| 要评审设计 | **§0.6 四处修正**（其中 2 处是 M1/总方案的真问题）、§6 冻结声明 |
| 要验收 | §1.4 验收标准 V1–V10、§5.5 验收演练 |
| 要理解"为什么" | §2.4 树形模型、§2.5 定位字典分层、§2.8 验证器 |

### 0.2 与 M1 的分工（谁讲什么，不重复）

| 内容 | M1（已冻结） | M2（本文） |
|---|---|---|
| 适配器接口 / 动作字典 / 分发机制 | ✅ 完整定义 | **引用不动**，只新增 1 个诊断方法（§0.6 F-M2-3） |
| `element` / `element_locator` 建表 | ✅ DDL 已给 | ✅ **修正 1 处唯一键缺陷**（F-M2-2）+ 补索引 |
| 定位类型校验字典 | ⚠️ 只填了 `WEB` | ✅ **三端完整 + 拆"语义类型 / 引擎语汇"两层**（F-M2-1） |
| `LocatorResolver` 回退链 | ✅ 实现 + 6 个单测 | **直接复用，不改一行** |
| 元素 / 定位符 API | ⚠️ 只有 GET + POST | ✅ **补全 PATCH / DELETE / 移动 / 重排 / 验证** |
| 元素库前端 | ❌ 明确不做 | ✅ **本文的主战场**（树形 + 拖拽 + 定位符面板） |
| 执行链路 | ✅ 同步版跑通 | 复用，M2 只需"用例步骤用 `element_id` 引用" |
| 用例编辑 / 报告 | ❌ | ❌ 仍属 M3 |

**一句话**：M1 让引擎能跑，M2 让**元素成为可管理的资产**——这是"平台"和"脚本集合"的分水岭。

### 0.3 本文依据的决策

**继承（上游已确认）**：D1 从零自建 · D2 Python+FastAPI · D3 一期仅 Web · D5 端只有三个 · D6 动作英文命名 · D7 按里程碑横切 · D9 monorepo · D10 SQL 先嵌文档 · D11 `run_python` 默认禁用 · D12 iframe 栈语义 · D13 M1 前端不装组件库。

**本文新增（用户已确认，2026-10-19）**：

| # | 决策 | 选定 | 对 M2 的约束 |
|---|---|---|---|
| **D14** | 元素拾取器（页面上点选生成定位符） | ❌ **不做**。改为「**手工录入 + 一键验证**」 | 取而代之的是 §2.8 的 `LocatorVerifier`：在真实页面上逐条试跑，返回命中数与样例。拾取器推迟到 M3（届时已有调试器面板） |
| **D15** | 元素树组织模型 | ✅ **纯树，任意层级**（`parent_id` + `path`） | 只用 M1 已有的 `parent_id` / `path` / `sort`，**不引入 Page/Module 固定层级**；配套深度上限与循环检测（§2.4） |
| **D16** | 跨项目元素共享（`is_shared`） | ❌ **M2 不做**，字段保留但不启用 | M2 所有元素 `is_shared` 恒为 1；API 不接受该参数，UI 不展示开关（§2.3.3 说明为什么"先不暴露"） |
| **D17** | 文档推进顺序 | ✅ **M2 → M3 → M4 → D3 工程约定 → 开工** | 本文只覆盖 M2，不提前写 M3 细节 |
| **D18** | M2 前端依赖（D13 留下的选型） | ✅ **仍不引入 UI 组件库**，但引入 **SortableJS**（经 `vuedraggable` 封装）专做拖拽 | 理由见 §4.2：手写树形拖拽的边界情况成本远高于 12KB 依赖；这是"单一职责小库"而非"全家桶组件库" |

> **D14 的连锁影响值得单独说**：不做拾取器，意味着"定位符写得对不对"这件事**必须在保存前后都能验证**，否则元素库会退化成"一堆没人确认过的字符串"。所以 `LocatorVerifier` 不是可选项，而是 D14 的**必要配套**。它同时替代了拾取器的核心价值——"这条定位符到底能不能命中"。

### 0.4 M2 相对 M1 的增量总览

| 层 | 增量 | 数量 |
|---|---|---|
| 数据表 | 无新表；`element` 改 1 处唯一键 + 加 2 列 1 索引；`element_locator` 加 1 列 | §0.6 F-M2-2 / 附录 A |
| 领域常量 | `locator_types.py` 从 1 端扩到 3 端，且结构升级为 `LocatorTypeSpec` | 1 个文件重写 |
| 后端服务 | `element_service` / `locator_service` / `tree_service` / `locator_verify_service` / `reference_service` | 5 个新模块 |
| 适配器 | `EngineAdapter.probe_locator()`（诊断方法，非动作）+ Playwright 覆写 | 1 个方法 |
| API | 元素 9 个 + 定位符 7 个 + 元数据 2 个 = **18 个端点** | §3.3 |
| 前端 | 元素库三栏页面 + 6 个视图组件 + 4 个 UI 原语 + 拖拽/搜索/验证交互 | §4 |
| 错误码 | 新增 17 个（`ELEMENT_*` 11 个 / `ELEMENT_LOCATOR_*` 3 个 / `LOCATOR_VERIFY_*` 2 个 / 通用 1 个） | §3.2 |
| 测试 | 18 组单测 + 7 组集成 + 3 组 e2e | §5 |

### 0.5 事实来源声明

**M1 附录 A 是 DDL 的 M1 阶段事实源**。本文因发现唯一键缺陷必须改 `element` 表，处理原则：

| 情况 | 做法 |
|---|---|
| **M1 尚未开工**（当前状态：0 行代码） | ✅ **直接改 M1 附录 A 的建表语句**，避免"建完表立刻 ALTER"的荒谬产物。本文附录 A 给出改后的最终态，并已回写 M1 |
| 若 M1 已开工、`schema.sql` 已生成 | 用本文附录 A.3 的 `ALTER TABLE` 增量脚本（已备好，防御性保留） |

> 依据：M1 §6.4 明确"**冻结从 M1 验收通过之日生效**"。当前 M1 未验收，改 DDL 合法，但必须**在 M1 追加变更记录**（已执行）。

### 0.6 ★ 四处修正（2 处是上游文档的真问题）

写这份施工图时逐行核对 M1 与总方案，发现四处会让实现者写错或写不出来。前两处**不是笔误，是设计缺陷**。

| # | 位置 | 原文 | M2 修正为 | 为什么必须改 |
|---|---|---|---|---|
| **F-M2-1** | 总方案 §5.1 三端定位字典 | `ANDROID` 允许值里含 **`-android uiautomator`(Appium)**、**`resourceId`(u2)**；`IOS` 含 **`-ios predicate string`(Appium)** | `locator_type` **只表达语义**（`resource_id` / `accessibility_id` / `text` …），**引擎语汇下沉到适配器翻译层** | **这会让 P2 的通配机制直接失效。** 同一个「登录按钮」的 resource-id 是**同一条业务事实**，但在旧字典下必须写成 `resourceId=...`(u2) 和 `id=...`(Appium) **两条不同 `locator_type` 的记录** → `engine_key='*'` 通配无从谈起**。更糟的是每加一个 Android 引擎就要加一个枚举值 —— 正是 P1 要避免的"字段值爆炸"。语义与语汇必须分层：**库存在语义层，翻译在引擎层**（M1 的 `_to_selector` 已是这么做 Web 的） |
| **F-M2-2** | M1 附录 A `element` 表 | `UNIQUE KEY uk_element_name (project_id, parent_id, element_name, is_deleted)` | 加 `deleted_seq BIGINT NOT NULL DEFAULT 0`；唯一键改为 `(project_id, parent_id, element_name, deleted_seq)`；删除时 `deleted_seq = id` | **软删除下这个唯一键必然冲突。** 删除第一个名为「登录按钮」的元素 → `is_deleted=1`；再删第二个同名元素 → 也想写 `is_deleted=1` → **唯一键冲突，删不掉**。这是软删 + 布尔唯一键的经典死锁，M2 的元素 CRUD 一写就会撞上。用 `deleted_seq`（活=0，删=自身 id）让每条已删记录唯一 |
| **F-M2-3** | M1 §2.5.2 `EngineAdapter` | 只有"动作方法"，无诊断能力 | 新增**非动作**方法 `probe_locator(chain, ctx) -> LocatorProbe`（命中数 + 样例），默认实现基于 `check_exists` 兜底 | 验证器需要"命中 N 个"，而 `check_exists` 只返回 `bool` —— 用 `element_list` 拼凑会污染动作语义。**它不进 `action_catalog`**：动作是"用例能编排的步骤"，诊断是"平台自己的能力"。不违反 FR4（FR4 约束的是动作方法名 == `action_key`，诊断方法不在其列）。默认实现让**桩适配器不被强迫实现** |
| **F-M2-4** | M1 §6.3 输入清单 | "定位符 CRUD API ✅ API 就绪" | ⚠️ **下调**：M1 实际只有 `GET` + `POST`，缺 `PATCH` / `DELETE` / 重排 / 验证 | 不是错误，是措辞过度乐观。M2 需补 6 个定位符端点 + 5 个元素端点，别按"已就绪"估工时 |

> F-M2-1 已回写总方案 §5.1；F-M2-2 已回写 M1 附录 A 并追加变更记录。

---

## 1. 里程碑目标、范围与验收

### 1.1 一句话目标

**让「登录按钮」成为一个有身份、有多端定位符、可被验证、可被复用的资产 —— 而不是散落在用例步骤里的一串字符串。**

M1 结束时，用例步骤里的元素定位还是"内联写死的选择器"（RD 的做法）。M2 结束时，同一个元素可以在 Web / Android / iOS 三端各挂一套定位符，执行时按 `(platform, engine_key)` 自动解析出**带回退链**的定位符 —— 这是 P2 从设计主张变成可运行事实的里程碑。

### 1.2 交付物清单

| # | 交付物 | 落点 | 验收对应 |
|---|---|---|---|
| 1 | `element` 表 DDL 修正 + `element_locator` 补列 | `backend/sql/schema.sql`（由 M1 附录 A 落成） | V6 |
| 2 | 三端定位字典（`LocatorTypeSpec` 结构） | `backend/app/domain/locator_types.py` | V8 |
| 3 | 树形服务：创建 / 移动 / 子树查询 / 循环检测 / 深度限制 | `backend/app/services/tree_service.py` | V1 / V7 |
| 4 | 元素服务：CRUD / 软删 / 引用保护 / 重名校验 | `backend/app/services/element_service.py` | V5 / V6 |
| 5 | 定位符服务：CRUD / `priority` 重排 / `is_primary` 唯一 | `backend/app/services/locator_service.py` | V2 / V9 |
| 6 | ★ **定位符验证器** | `backend/app/services/locator_verify_service.py` | V3 / V4 |
| 7 | `probe_locator` 诊断方法 + Playwright 覆写 | `backend/app/engines/base.py` + `adapters/playwright_adapter.py` | V4 |
| 8 | 引用查询（被哪些用例/步骤用到） | `backend/app/services/reference_service.py` | V5 |
| 9 | 18 个 REST 端点 + 17 个错误码 | `backend/app/api/v1/elements.py` 等 | V10 |
| 10 | 前端元素库（三栏 + 树 + 拖拽 + 定位符面板 + 验证结果） | `frontend/src/views/ElementLibrary/` | F1–F9 |
| 11 | 用例步骤改用 `element_id` 引用 | 复用 M1 的 `case_service` + e2e 用例 | V10 |
| 12 | 3 个 e2e fixture 页面（多端定位 + 回退 + 多命中） | `fixtures/web/` | V3 / V4 |

### 1.3 范围边界

**M2 做**：

- 元素树的完整 CRUD（含 FOLDER 目录节点）、拖拽排序、跨父移动
- 一个元素挂**多端多引擎**定位符，每条可独立启用/禁用/设首选/排序
- **定位符验证**（保存前验草稿、保存后验存量，返回命中数与样例）
- 元素被引用时的**删除保护**
- 三端定位类型字典 + 引擎维度的合法性校验

**M2 明确不做**（不是遗漏，是刻意排除）：

| 不做 | 原因 | 何时做 |
|---|---|---|
| 页面拾取器（点选生成定位符） | D14 已定 | M3（有调试器面板时） |
| 跨项目共享元素 | D16 已定 | 二期（真有第二个项目接入时） |
| 定位符健康度统计页（哪个定位符最稳） | 需要**执行数据积累**，M2 时还没有数据 | M3 之后（数据来自 `execution_step_result`） |
| 定位自愈（自动改定位符） | 依赖健康度统计 | 二期 |
| 批量导入 / Excel 导出元素 | 不阻塞核心闭环 | 视需要 |
| 元素版本历史 / 操作审计 | 独立复杂度 | 二期 |
| 用例编辑器里的元素选择器 | M3 的 StepEditor 负责 | M3 |
| 元素级权限（谁能改哪个元素） | 登录鉴权 M3 才做 | M3 之后 |

> **"不做拾取器"的代价要正视**：用户必须自己知道 `data-testid` / `resource-id` 是什么。缓解手段有三条 —— ① 定位类型下拉带示例值（`testid` → `login-submit`）；② 验证器即时反馈"命中 0 个"；③ M3 调试器里补"点选"入口。M2 先保证**验证闭环**，拾取只是录入效率问题，不是能力问题。

### 1.4 验收标准（V1–V10）

每条都是**可执行的操作**，不是"看起来对"。

| # | 验收项 | 操作 | 期望 |
|---|---|---|---|
| **V1** | 元素树 CRUD 与移动 | 建 `登录模块/` (FOLDER) → 其下建「登录按钮」→ 把模块整体移到 `公共组件/` 下 | 移动后：① 模块自身 `path` 变成 `/公共组件id/模块id/`；② **子元素的 `path` 自动跟着重写**；③ 子树查询仍能查全；④ `sort` 不乱 |
| **V2** | 三端定位符共存 | 给「登录按钮」配：WEB `testid=login-submit`、ANDROID `resource_id=com.demo:id/login`、IOS `accessibility_id=loginBtn` | 三端互不干扰；`GET locators` 按 platform 分组返回；Web 用例执行时只取 WEB 那一条 |
| **V3** | ★ **回退链生效** | 把 V2 的 WEB 首选定位符**故意改成不存在的** `testid=not-exist`，保留第 2 条 `css=#submit`，执行登录用例 | ① 执行仍 `PASSED`；② 结果里该步骤 `fallback_index=1`、`used_locator_id` = 第 2 条的 id；③ M1 前端结果表的 `fallback_index` 列显示 `1` 并高亮 |
| **V4** | 定位符验证器 | ① 对草稿 `css=.btn` 点验证 → 返回 `matched=3`；② 对 `testid=login-submit` 验证 → `matched=1`；③ 对 `#not-exist` → `matched=0` | ① `matched=3` 判为 **MULTIPLE（警告，不落 INVALID）**；② `VALID` 且 `verified_at` 被写；③ `NONE` → `status` 落 `INVALID` |
| **V5** | 引用保护 | 用例 3 的第 2 步引用了「登录按钮」→ 尝试删除该元素 | 返回 `409 ELEMENT_REFERENCED`，响应体含**引用它的用例清单**（`case_id` / `title` / `step_seq`）；加 `?force=true` 可强制软删，但响应带 `affected_cases` 警告 |
| **V6** | 软删除唯一性（★ F-M2-2 的回归） | 建「按钮A」→ 删除 → 再建「按钮A」→ 再删除 | 两次删除都成功，**不报唯一键冲突**；两次都重建成功 |
| **V7** | 循环与深度 | ① 把 `A` 移到它自己的子节点 `A/B` 下；② 连续建 9 层目录 | ① `422 ELEMENT_MOVE_INTO_DESCENDANT`；② 第 9 层 `422 ELEMENT_DEPTH_EXCEEDED`（上限 8） |
| **V8** | 引擎维度校验（★ F-M2-1 的回归） | 给 IOS 元素配 `css`；给 `uiautomator2` 配 `uiautomator`（Appium 专属） | ① `422 ELEMENT_LOCATOR_TYPE_INVALID`；② `422 ELEMENT_LOCATOR_TYPE_ENGINE_UNSUPPORTED`。**但**给 `uiautomator2` 配 `resource_id` 必须成功（语义通用） |
| **V9** | 拖拽排序 | 定位符面板拖拽把第 3 条拖到第 1 位 → 保存 | 三条的 `priority` 重排为连续值（10/20/30）；`LocatorResolver` 解析顺序随之改变；**元素树拖拽同理改 `sort`** |
| **V10** | 用例改用元素引用 | 把 M1 的 `login.html` e2e 用例从"内联选择器"改为 `element_id` 引用，重新执行 | 仍 `PASSED`；且删掉该元素的 WEB 定位符后执行 → `ERROR`，错误信息指出"元素 X 在 WEB/playwright 下无定位符" |

### 1.5 完成定义（DoD）

M2 视为完成，需同时满足：

- [ ] V1–V10 全部通过，且**每条都有对应的自动化测试**（不许只手工点过）
- [ ] `pytest tests/unit` + `pytest tests/integration` 全绿
- [ ] 三端定位字典与 `probe_locator` 的引擎支持声明**双向一致**（启动时校验，见 §2.5.5）
- [ ] 附录 A 的 DDL 已落成 `backend/sql/schema.sql`，且 M1 附录 A 已同步（本文明示了怎么改）
- [ ] `CHANGELOG.md` / `api.md` / `README.md` 已更新，与代码完全一致
- [ ] 前端在**不刷新页面**的情况下完成"建元素 → 配三端定位符 → 验证 → 拖拽调序"整套流程

### 1.6 关键路径与风险分布

```
       ┌──────────────────────────────────────────────┐
       │  §2.3 DDL 修正（F-M2-2）                      │  ← 30 分钟，但错了要重建数据
       └───────────────┬──────────────────────────────┘
                       ↓
       ┌───────────────┴──────────────┐
       │  §2.4 树形模型（path 维护）    │  ← 最容易出隐性 bug（移动后子树路径）
       └───────────────┬──────────────┘
                       ↓
   ┌───────────────────┴────────────────────┐
   │  §2.5 三端字典 ──→ §2.7 定位符服务      │
   └───────────────────┬────────────────────┘
                       ↓
       ┌───────────────┴──────────────┐
       │  §2.8 验证器（需 probe_locator）│  ← M2 唯一"新能力"，也是 D14 的支点
       └───────────────┬──────────────┘
                       ↓
       ┌───────────────┴──────────────┐
       │  §3 API ──→ §4 前端三栏 + 拖拽 │  ← 体量最大，但契约已冻结
       └──────────────────────────────┘
```

**风险集中在两处**：① **树形 `path` 的维护**（移动子树时一条 SQL 写错，整棵树就废了，且不会报错）；② **验证器的 session 生命周期**（起浏览器、超时、清理，最容易留下僵尸进程）。

### 1.7 与 M1 的关系：不重写，只增量

M2 **不修改** M1 的任何已冻结契约（除 §0.6 那三处，且都是加法）：

| M1 资产 | M2 动作 |
|---|---|
| `LocatorChain` / `Locator` / `LocatorResolver` | **零改动**，直接调用 |
| `SessionManager`（非单例） | **零改动**，验证器用它的多实例能力（F-M2-3 的第二个回报） |
| `EngineAdapter` 的 42 个动作方法 | **零改动**，只加一个 `probe_locator` |
| `action_catalog` 51 条 | **零改动**，M2 不新增任何动作 |
| `execution_step_result` 埋点列 | **零改动**，M2 只消费不改结构 |
| M1 前端 Engines / Executions 页 | **零改动**，M2 新增独立路由 `/elements` |

> 这条"只增量"是 M1 架构定型是否成功的**第一个真实检验**：如果 M2 需要回头改适配器接口或动作字典，说明 M1 的分层没做对。目前看不需要 —— 除 `probe_locator` 这个**新增**的诊断维度。

---

## 2. 后端设计

### 2.1 工程结构增量

只列出 M2 新增 / 改动的文件。M1 的目录结构（§2.1）保持不变。

```
backend/app/
├─ domain/
│  ├─ locator_types.py          ★ 重写：三端字典 + LocatorTypeSpec + 引擎维度
│  └─ element_errors.py         [新] 元素/定位符的错误码常量与文案
├─ services/
│  ├─ tree_service.py           [新] path 维护、循环检测、深度、同级排序
│  ├─ element_service.py        [新] 元素 CRUD、软删、引用保护、重名
│  ├─ locator_service.py        [新] 定位符 CRUD、priority 重排、is_primary
│  ├─ locator_verify_service.py [新] ★ 验证器
│  └─ reference_service.py      [新] 元素引用查询
├─ repositories/
│  ├─ element_repo.py           [新] 含子树 SQL（LIKE path + SUBSTRING 批量重写）
│  └─ locator_repo.py           [新] find_locators 已由 M1 的 LocatorResolver 依赖
├─ schemas/
│  ├─ element.py                [新] 请求/响应模型
│  └─ locator.py                [新]
├─ api/v1/
│  ├─ elements.py               [新] 9 个端点
│  ├─ locators.py               [新] 7 个端点
│  └─ meta.py                   [新] 定位类型字典 + 统计
└─ engines/
   ├─ base.py                   ✏️ 加 LocatorProbe + probe_locator 默认实现
   └─ adapters/playwright_adapter.py  ✏️ 覆写 probe_locator（精确 count）

frontend/src/
├─ views/ElementLibrary/
│  ├─ index.vue                 [新] 三栏布局外壳
│  ├─ ElementTree.vue           [新] 树（搜索/展开/拖拽/右键菜单）
│  ├─ ElementDetail.vue         [新] 逻辑名 / 描述 / memo / 路径
│  ├─ LocatorPanel.vue          [新] 三端 tab + 回退链列表
│  ├─ LocatorRow.vue            [新] 单条（类型/值/状态灯/验证按钮）
│  └─ VerifyResult.vue          [新] 命中数 + 样例 + 结论
├─ components/
│  ├─ AppTree.vue               [新] 通用树（可复用给 M3 的用例目录）
│  └─ AppToast.ts / AppModal.vue [新] D13/D18 下自建的极简 UI 原语
├─ api/elements.ts  locators.ts  [新]
└─ stores/element.ts            [新]

fixtures/web/
├─ locators.html                [新] 11 种定位方式各一份语义元素（V4/V8）
├─ multi-hit.html               [新] 故意 3 个同 class 元素（验证 MULTIPLE）
└─ nested/                      [新] 3 层目录 + iframe（验证树与 V1 无关但供 M3 用）
```

### 2.2 分层与红线（沿用 M1）

**新增两条 import 红线**（写进 `import-linter` 配置，与 M1 的规则并列）：

| 红线 | 规则 | 为什么 |
|---|---|---|
| RL-M2-1 | `services/element_service.py` **不得** import `engines/*` | 元素管理是纯业务，不该碰引擎。若需要"验证"，走 `locator_verify_service` 注入 |
| RL-M2-2 | `domain/locator_types.py` **不得** import 除 `typing` / `dataclasses` 之外的任何模块 | 它是"字典"，必须零依赖，否则 M1 的 `registry` 与它会形成循环依赖 |

> RL-M2-2 不是洁癖：`locator_types` 要被 `registry`（引擎注册）、`element_service`（写入校验）、`api/meta`（前端下拉）三方引用。一旦它引入任何业务模块，就会立刻出现循环 import。

### 2.3 数据层

#### 2.3.1 `element` 表：修正软删除唯一键（F-M2-2）

**问题复现**（这是会在 V6 验收时必然踩到的 bug）：

```
1. 建元素 name='登录按钮'                      → is_deleted=0  ✓
2. 软删它         → UPDATE is_deleted=1       → 表里出现 (proj=1,parent=0,'登录按钮',1)
3. 再建同名元素   → is_deleted=0              ✓（不冲突）
4. 再软删它       → UPDATE is_deleted=1       → ✗ Duplicate entry '1-0-登录按钮-1'
```

根因：**用一个只有两个取值的布尔列参与唯一键**，删除第 2 条同名记录时必然撞上第 1 条。

**修正**：新增 `deleted_seq BIGINT NOT NULL DEFAULT 0`，唯一键包含它。规则 —— **未删除恒为 0，删除时置为自身 `id`**（`id` 天然唯一）。

```sql
`deleted_seq`  BIGINT       NOT NULL DEFAULT 0 COMMENT '软删序号：0=未删；删除时置为自身 id，使已删记录互不冲突',
...
UNIQUE KEY `uk_element_name` (`project_id`, `parent_id`, `element_name`, `deleted_seq`),
KEY `idx_element_name` (`project_id`, `element_name`),
```

> `is_deleted` / `deleted_at` **保留不动**（列表过滤仍用 `is_deleted=0`，语义更直观）。`deleted_seq` 只服务唯一键，不参与业务判断 —— 两者职责分离，避免"M1 已有代码全部要改"。
>
> **为什么不直接去掉唯一键、改应用层校验**：并发两个请求同时建同名元素时，应用层"先查再插"会双双通过。数据库唯一键是最后一道防线，不能拆。

#### 2.3.2 `element_locator` 表：补 1 列

```sql
`probe_detail`  JSON  NULL COMMENT '最近一次验证结果：{matched, status, sample, error, at}，供 UI 展示，不参与解析',
```

**为什么需要它**：V4 要求 UI 显示"上次验证：命中 3 个"。若不复用，用户每进一次页面就要重跑一次验证（每次起一个浏览器，几秒钟）。存下来后列表直接显示，仅"重新验证"时才真跑。

> `status` / `verified_at` M1 已有，继续用。`probe_detail` 只做补充（存样例与错误原因），**不放宽 `status` 的语义**：`status` 仍只有 `UNVERIFIED/VALID/INVALID` 三态。

#### 2.3.3 `is_shared` 的处置（D16）

字段保留、M2 不启用。三个具体约束：

| 位置 | 做法 |
|---|---|
| DDL | 默认 `1`，注释改为 `'1=项目内共享（M2 固定为 1，字段预留给二期的跨项目共享）'` |
| API | `POST/PATCH /elements` **不接受** `is_shared` 参数；若传入 → 忽略（不报错，避免前端版本错配时崩掉） |
| UI | **不展示**"共享/私有"开关 |

> **为什么"不报错而是忽略"**：这是个尚未定义语义的字段。报错会让前端耦合一个"将来会变"的校验；忽略则前端无论传不传都能工作。但**必须在响应里返回真实值 `1`**，让前端有据可依，而不是自己猜。

#### 2.3.4 索引复核（M2 的查询模式）

| 查询 | 走哪个索引 | M1 是否已有 |
|---|---|---|
| 元素树全量（按项目） | `idx_element_project (project_id, is_deleted)` | ✅ |
| 子树查询 | `idx_element_path (project_id, path)` | ✅ |
| 按名字搜索 | `idx_element_name (project_id, element_name)` | ❌ **M2 新增** |
| 定位符回退链 | `idx_locator_lookup (element_id, platform, engine_key, enabled, priority)` | ✅ |
| 引用查询（反查） | `idx_step_element (element_id)` | ✅ |

> **路径前缀查询的索引可用性**：`path LIKE '/1/12/%'` 是**前缀匹配**，`idx_element_path` 能走索引（不是 `%xxx` 全模糊）。这是选物化路径而非递归 CTE 的直接收益 —— MySQL 8 的递归 CTE 在元素树这种高频读场景上更慢。

### 2.4 树形模型（D15 · 纯树任意层级）

#### 2.4.1 `path` 的格式与不变量

**格式**：`/` 开头、`/` 结尾、每层是元素的 `id`。

```
根目录（id=0 的虚拟根，不入库）  /
登录模块        id=7             /7/
  └ 登录页      id=12            /7/12/
      └ 登录按钮 id=45           /7/12/45/
```

**三条不变量**（M2 全部写进单测）：

| # | 不变量 | 校验方式 |
|---|---|---|
| INV-1 | 每个节点的 `path` = 父 `path` + 自身 `id` + `/` | `tree_service.assert_path_integrity()` 可全量校验（供运维排查） |
| INV-2 | `path` 以自身 `id` 结尾 | 同上 |
| INV-3 | 深度 = `path` 中 `/` 的个数 - 1，且 ≤ `MAX_DEPTH`（默认 8） | 写入时校验 |

> **为什么 `path` 含自身**：移动子树时只需重写前缀，不必重算"父链"；且 `LIKE '/7/12/%'` 天然包含自身，子树查询一条 SQL 完成。

#### 2.4.2 创建：为什么要两次写

`id` 是自增主键，**建之前不知道**，而 `path` 又依赖它。两条路：

| 方案 | 做法 | 代价 |
|---|---|---|
| A（采用） | 事务内：`INSERT`（`path` 临时存 `''`）→ 取 `lastrowid` → `UPDATE path` | 2 次写；但简单、无额外列 |
| B | 预生成雪花 id / UUID 作 `path` 段 | 1 次写；但 `path` 可读性差，且与自增主键并存要维护两套 id |

```python
async def create_node(db, *, project_id: int, parent_id: int, name: str,
                      node_type: str, **fields) -> Element:
    parent_path = "/" if parent_id == 0 else (await _get_or_404(db, parent_id)).path

    # 1) 先插入占位
    node = Element(project_id=project_id, parent_id=parent_id, path="",
                   element_name=name, node_type=node_type, **fields)
    db.add(node)
    await db.flush()                    # 拿到 node.id，仍在同一事务

    # 2) 回填 path 并校验深度
    node.path = f"{parent_path}{node.id}/"
    tree_service.assert_depth(node.path)     # 超限抛 ELEMENT_DEPTH_EXCEEDED
    await db.commit()
    return node
```

> 两次写都在同一事务内，外部看不到中间态。**并发安全**：`path` 只依赖自己的 `id`，不存在两个请求互相覆盖的可能。

#### 2.4.3 移动子树：一条 SQL 重写全部后代

这是 M2 **最危险的一条 SQL** —— 写错了不报错，只是整棵树的 `path` 静默错位。

```python
async def move_node(db, *, element_id: int, new_parent_id: int, index: int | None) -> None:
    node = await _get_or_404(db, element_id)
    new_parent_path = "/" if new_parent_id == 0 else (await _get_or_404(db, new_parent_id)).path

    # ① 不能移到自己或自己的子树下（自环 / 环）
    if new_parent_id == element_id or new_parent_path.startswith(node.path):
        raise ElementMoveIntoDescendant(element_id, new_parent_id)

    # ② 深度：新父深度 + 子树高度 不能超限
    subtree_height = await element_repo.subtree_height(db, node)      # 相对高度（根=1）
    tree_service.assert_depth(new_parent_path, extra_height=subtree_height)

    old_prefix = node.path
    new_prefix = f"{new_parent_path}{node.id}/"
    async with db.begin():
        # ③ 一步重写：把子树中所有 path 的旧前缀替换为新前缀
        await element_repo.rewrite_path_prefix(db, node.project_id, old_prefix, new_prefix)
        # ④ 改父与排序（子树的 path 已变，父链自然正确）
        node.parent_id = new_parent_id
        if index is not None:
            await element_repo.insert_at(db, node.project_id, new_parent_id, node, index)
```

对应 SQL（`rewrite_path_prefix`）：

```sql
UPDATE `element`
SET `path` = CONCAT(:new_prefix, SUBSTRING(`path`, :old_prefix_len + 1))
WHERE `project_id` = :project_id
  AND `path` LIKE CONCAT(:old_prefix, '%');
```

**逐字解释，因为这里最容易错**：

| 片段 | 含义 | 错一步会怎样 |
|---|---|---|
| `LIKE CONCAT(:old_prefix, '%')` | 匹配子树**全部**节点（含自身），因为 `path` 以 `/` 结尾 | 漏掉 `%` → 只更新自身，后代全成孤儿 |
| `SUBSTRING(path, old_len + 1)` | 取"旧前缀之后"的部分（MySQL `SUBSTRING` 是 **1-based**） | 写成 `old_len` 会多留一个字符，`path` 变成 `/7/12/45` → `/7/112/45` 这类脏数据 |
| `CONCAT(new_prefix, ...)` | 新前缀已以 `/` 结尾，所以拼出来仍是 `/.../` 结尾 | `new_prefix` 忘带尾斜杠 → 后代的 `id` 与前缀粘连 |

> **为什么不用递归 CTE 逐层改**：树深 ≤ 8，但节点数可能上万；一条 `UPDATE` 比 N 次往返快一个量级，且**天然原子**（一条语句要么全成要么全不成）。递归 CTE 的更新中途失败会留下半棵树。

#### 2.4.4 同级排序：全量提交，不做增量

拖拽后的排序**整批提交**，而不是"把 A 插到 B 前面"这种相对指令。

```jsonc
// PUT /elements/{id}/children-order
{ "parent_id": 0, "ordered_ids": [45, 12, 7] }
```

服务端校验：

| 检查 | 失败码 |
|---|---|
| `ordered_ids` 的集合 **恰好等于** 当前该父下的全部子节点 id（不多、不少、不重） | `ELEMENT_ORDER_INCOMPLETE` |
| 长度 ≤ 500（一次拖拽不该有几千个子节点） | `BATCH_LIMIT_EXCEEDED` |

通过后按序号重写 `sort = (i + 1) * 10`（**留 10 的间隔**，为将来"插一条"留空间，但 M2 不依赖间隔，靠全量重排）。

> **为什么不做"相对指令"**：相对指令（`{after_id}`）在并发下会产生两种合理解释（按提交顺序还是按当前顺序），而全量提交的语义唯一。代价是请求体大一点 —— 一个父节点下几十个子节点，忽略不计。

#### 2.4.5 FOLDER 与 ELEMENT 的差异

| 行为 | `FOLDER` | `ELEMENT` |
|---|---|---|
| 可挂子节点 | ✅ | ❌（`ELEMENT_PARENT_MUST_BE_FOLDER`） |
| 可挂定位符 | ❌（`ELEMENT_FOLDER_HAS_NO_LOCATOR`） | ✅ |
| 被用例步骤引用 | ❌ | ✅ |
| 删除时有子节点 | ❌ 拒绝（`ELEMENT_FOLDER_NOT_EMPTY`） | — |

> **为什么允许 `FOLDER` 在 `ELEMENT` 下不存在子节点**：纯树模型的代价就是"用户可能把元素当目录用"。M2 用**拒绝**（`ELEMENT_PARENT_MUST_BE_FOLDER`）而不是自动转换 —— 自动把 `ELEMENT` 改成 `FOLDER` 会让"这个元素昨天还有定位符、今天变成目录"的诡异状态出现。

### 2.5 三端定位字典（F-M2-1 的落地）

#### 2.5.1 核心原则：语义层与语汇层分离

```
┌──────────────────────────────────────────────────────────┐
│  语义层（入库）  element_locator.locator_type = 'resource_id'  │
│  含义：这是个资源 ID —— 与用什么引擎无关的业务事实          │
└───────────────────────┬──────────────────────────────────┘
                        │  LocatorResolver 按 (platform, engine_key) 取出
                        ▼
┌──────────────────────────────────────────────────────────┐
│  翻译层（引擎适配器内）                                      │
│    appium      → id=com.demo:id/login                      │
│    uiautomator2→ resourceId=com.demo:id/login              │
│    playwright  → [data-testid="login"]（不适用，不同类型）   │
└──────────────────────────────────────────────────────────┘
```

**结论**：一条 `(element, ANDROID, '*', resource_id, 'com.demo:id/login')` 记录**同时服务两个 Android 引擎**。若按总方案原字典（`resourceId` / `id` 分成两个 type），同样的信息要写两条，且 `'*'` 通配无意义。

> 这与 M1 的 `_to_selector` 是同一套思路 —— M1 里 Web 的 `locator_type='testid'` 也不是 Playwright 的语汇（Playwright 叫 `data-testid`），而是语义，翻译发生在适配器。**M2 只是把同一条原则贯彻到移动端**。

#### 2.5.2 数据结构

```python
# backend/app/domain/locator_types.py
"""定位类型字典（三端）。

分层约束（冻结项 FR18）：
  1. 本字典只表达**语义**，绝不出现引擎语汇（如 '-android uiautomator'、'resourceId='）
  2. engines 字段声明"哪些引擎能翻译这个语义" → 写入期做引擎维度校验
  3. 本模块零业务依赖（RL-M2-2），可被 registry / service / api 三方引用
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class LocatorTypeSpec:
    key: str                    # 语义标识（入库值），英文 snake_case
    label: str                  # 中文展示名（前端下拉）
    example: str                # 示例值（前端 placeholder）
    engines: frozenset[str]     # ★ 支持翻译该语义的引擎
    rank: int                   # 建议顺序（1=最稳），用于新建时默认 priority 与前端排序提示
    note: str = ""              # 何时该用/不该用


@dataclass(frozen=True, slots=True)
class PlatformLocators:
    platform: str
    label: str
    engines: frozenset[str]              # 该平台的全部引擎（须与 registry 一致）
    types: dict[str, LocatorTypeSpec] = field(default_factory=dict)
```

#### 2.5.3 三端完整字典

**WEB**（11 种，`engines={"playwright"}`）

| rank | `locator_type` | 中文 | 示例 | 什么时候用 |
|---|---|---|---|---|
| 1 | `testid` | 测试标识 | `login-submit` | **首选**。前后端约定 `data-testid`，最稳、与样式解耦 |
| 2 | `role` | 无障碍角色 | `button[name="登录"]` | 语义稳定，适合表单与可访问性良好的页面 |
| 3 | `label` | 表单标签 | `用户名` | 适合 `getByLabel` 场景 |
| 4 | `placeholder` | 占位符 | `请输入用户名` | 输入框专用 |
| 5 | `id` | 元素 id | `loginForm` | 稳定但易被前端重构改掉 |
| 6 | `css` | CSS 选择器 | `#loginForm .btn-primary` | 通用兜底，注意别写太深 |
| 7 | `text` | 可见文本 | `登录` | 文案会变；只用于稳定文案 |
| 8 | `title` | title 属性 | `提交登录` | 少用 |
| 9 | `alt` | 图片 alt | `用户头像` | 图片专用 |
| 10 | `class` | class 名 | `btn-primary` | **最不稳**，样式类名最易变 |
| 11 | `xpath` | XPath | `//button[@type="submit"]` | **最后手段**，慢且脆 |

**ANDROID**（7 种，`engines={"appium","uiautomator2"}`）

| rank | `locator_type` | 中文 | 示例 | 引擎支持 | 说明 |
|---|---|---|---|---|---|
| 1 | `resource_id` | 资源 ID | `com.demo:id/login_btn` | appium, u2 | **首选**。语义 = Android 的 `resource-id` |
| 2 | `accessibility_id` | 无障碍 ID | `loginBtn` | appium, u2 | 对应 `content-desc`，跨端最一致 |
| 3 | `uiautomator` | UiSelector 表达式 | `new UiSelector().text("登录")` | **仅 appium** | 引擎专属表达式，**不能通配** |
| 4 | `text` | 精确文本 | `登录` | appium, u2 | 文案会变 |
| 5 | `text_contains` | 文本包含 | `登 录` | appium, u2 | 精确匹配不到时的兜底 |
| 6 | `class_name` | 控件类名 | `android.widget.Button` | appium, u2 | 粒度太粗，常匹配多个 |
| 7 | `xpath` | XPath | `//android.widget.Button[@text="登录"]` | appium, u2 | 最后手段，慢 |

**IOS**（5 种，`engines={"appium"}`）

| rank | `locator_type` | 中文 | 示例 | 说明 |
|---|---|---|---|---|
| 1 | `accessibility_id` | 无障碍 ID | `loginBtn` | **首选**。需开发在 XCUITest 里设 `accessibilityIdentifier` |
| 2 | `predicate` | 谓词表达式 | `type == 'XCUIElementTypeButton' AND label == '登录'` | 灵活，性能可接受 |
| 3 | `class_chain` | 类链 | `**/XCUIElementTypeButton[\`label == "登录"\`]` | 比 XPath 快得多 |
| 4 | `name` | name 属性 | `loginBtn` | 兼容旧写法 |
| 5 | `xpath` | XPath | `//XCUIElementTypeButton[@name="loginBtn"]` | ⚠️ **必须放最后**：iOS 上 XPath 逐节点求值，页面复杂时可达秒级 |

> **iOS 的顺序不是随意排的**：`xpath` 在 iOS 上性能极差是社区共识，也是《移动端对接方案》已写明的约束。`rank` 直接决定"新建定位符时的默认 `priority`"，所以排序本身就是设计。

#### 2.5.4 字典是"代码事实"，不是业务数据

与 M1 的 `CAPABILITY_MATRIX` 同理：**不入库**。理由 —— 引擎能力随版本变化（Appium 加新 locator strategy），这是代码演进，不该让运维去改表。

前端需要它做下拉 → 通过 `GET /api/v1/locator-types` 暴露（一次请求拿三端全量，含 `label` / `example` / `engines` / `rank`）。

#### 2.5.5 启动时的一致性校验（★ 对齐 M1 的做法）

M1 已建立"能力矩阵 vs 动作字典"的双向校验。M2 对定位字典做**同样的第三组校验**：

```python
def assert_locator_dict_consistency(registry) -> None:
    """启动时执行，失败则拒绝启动。三道检查缺一不可。"""
    # ① 字典里的每个 platform 都必须是 registry 认识的端
    for p in LOCATOR_TYPES:
        assert p in registry.platforms, f"字典含未知平台 {p}"

    # ② registry 的每个 (platform, engine) 都必须在字典中"有类型可配"
    for p, engines in registry.platform_engines.items():
        for e in engines:
            supported = [t for t in LOCATOR_TYPES[p].types.values() if e in t.engines]
            assert supported, f"平台 {p} 的引擎 {e} 在字典中无任何可用定位类型 → 该引擎无法配置元素"

    # ③ 每个类型的 engines 必须 ⊆ 该平台的 engines（防止抄错）
    for p, pl in LOCATOR_TYPES.items():
        for t in pl.types.values():
            assert t.engines <= pl.engines, f"{p}.{t.key} 声明了不属于该平台的引擎 {t.engines - pl.engines}"
```

**第 ② 条是真正有价值的**：如果将来接入一个引擎（比如 Android 上某个新驱动），而字典里没有任何它支持的类型，那么**该引擎的元素永远配不出来** —— 但系统不会报错，只会在执行时"找不到定位符"。这条校验把这个沉默故障提前到启动阶段。

#### 2.5.6 写入期校验的三个层次

`POST/PATCH locator` 时按序校验，**顺序不能乱**（决定了用户看到哪条报错）：

| 序 | 检查 | 失败码 | 示例 |
|---|---|---|---|
| 1 | `locator_type` 是否存在于该 platform 的字典 | `ELEMENT_LOCATOR_TYPE_INVALID` | 给 IOS 配 `css` |
| 2 | 该 type 的 `engines` 是否包含目标 `engine_key` | `ELEMENT_LOCATOR_TYPE_ENGINE_UNSUPPORTED` | 给 `uiautomator2` 配 `uiautomator` |
| 3 | 若 `engine_key='*'`，该 type 是否被平台**全部**引擎支持 | `ELEMENT_LOCATOR_WILDCARD_UNSCOPED` | `engine_key='*'` + `uiautomator`（仅 appium） |

**第 3 条是 F-M2-1 的直接产物**，值得单独解释：

`engine_key='*'` 的语义是"这个平台下**所有**引擎通用"。如果一条记录写 `'*'` + `uiautomator`（只有 appium 能翻译），那么 Android 上跑 u2 引擎时，`LocatorResolver` 会把它当候选取出，然后**适配器抛异常** —— 一个本该在写入期拒绝的配置，变成了运行期的崩溃。

> 报错文案要给出解法，不能只说"不支持"：`"定位类型 uiautomator 仅 appium 支持，不能用于 engine_key='*'。请显式指定 engine_key='appium'，或改用 resource_id（两个引擎都支持）"`。

### 2.6 `tree_service` / `element_service`

#### 2.6.1 树的读取：一次查询 + 内存组装

```python
async def list_tree(db, project_id: int, *, parent_id: int | None = None,
                    keyword: str | None = None, include_locator_count: bool = True):
    """parent_id 为空 → 全量树；给值 → 该节点的子树（含自身）。
    keyword 命中时返回扁平结果 + 每个结果的 path（前端高亮祖先链）。"""
    if keyword:
        rows = await element_repo.search(db, project_id, keyword)     # LIKE %kw%
        return _flat(rows)          # 搜索不做树，返回扁平列表更实用
    rows = await element_repo.list_by_project(db, project_id)         # 一次全查
    return _assemble_tree(rows, parent_id)                            # Python 里组装
```

**为什么全量查再内存组装，而不是逐层 `WHERE parent_id=?`**：

| 方案 | 查询次数 | 问题 |
|---|---|---|
| 逐层递归 | O(深度) ≈ 8 次 | 展开整棵树时要 8 次往返；前端"展开全部"会打 8 个请求 |
| **全量 + 内存组装** | **1 次** | 元素总量级在千级，一次查完几十 KB，完全可接受 |

> **规模上限说明**：元素数 > 5000 时应改为"懒加载（点开才查子节点）"。M2 不做，但在 `element-stats` 接口里返回 `total_elements`，让用户能看见何时该升级。

#### 2.6.2 `locator_count` 的聚合

树的每个节点要显示"已配 N 条定位符"（这是用户判断"哪些元素还没配定位符"的主要依据）。**不能 N+1 查询**：

```sql
SELECT e.id, COUNT(l.id) AS locator_count,
       SUM(l.platform='WEB') AS web_cnt,
       SUM(l.platform='ANDROID') AS android_cnt,
       SUM(l.platform='IOS') AS ios_cnt
FROM `element` e LEFT JOIN `element_locator` l
  ON l.element_id = e.id AND l.enabled = 1
WHERE e.project_id = :pid AND e.is_deleted = 0
GROUP BY e.id;
```

一次 `LEFT JOIN + GROUP BY` 拿到全项目的覆盖情况。**这个数据同时喂给 `element-stats` 接口**，让"Web 端还有 12 个元素没配定位符"成为可看见的事实。

#### 2.6.3 删除的三种情形

| 情形 | 行为 | 错误码 / 结果 |
|---|---|---|
| `ELEMENT` 被用例步骤引用 | 拒绝 | `409 ELEMENT_REFERENCED`（含引用清单） |
| `ELEMENT` 无引用 | 软删 + **级联软删其定位符** | `204` |
| `FOLDER` 有未删除子节点 | 拒绝 | `409 ELEMENT_FOLDER_NOT_EMPTY` |
| `FOLDER` 空 | 软删 | `204` |
| 任意 + `?force=true` | 软删，跳过引用检查 | `200` + `affected_cases: [{case_id,title,step_seq}]` |

> **为什么定位符要级联软删**：`element_locator` 没有 `is_deleted` 列（M1 DDL）。如果元素软删而定位符"还在"，它们会继续被 `LocatorResolver` 通过 `element_id` 查到（虽然元素已不可见）。M2 的选择：**定位符直接物理删除**（它们是元素的附属物，没有独立生命周期，也没有引用方）。这比加一个 `is_deleted` 列更简单，且不会留下孤儿数据。

#### 2.6.4 重名校验的双保险

| 层 | 作用 |
|---|---|
| 应用层：插入前 `SELECT ... WHERE project_id=? AND parent_id=? AND element_name=? AND deleted_seq=0` | 给出友好报错 `409 ELEMENT_NAME_DUPLICATED`，并提示"同级已有同名节点" |
| 数据库：`uk_element_name` | 兜住并发穿透（两个请求同时通过应用层检查时，第二条被 DB 拒绝） |

`PATCH` 改名时同样走这两层（改名 = 换个名字，唯一键自然生效）。

### 2.7 `locator_service`

#### 2.7.1 `priority` 的语义与重排

**`priority` 是"同一 `(element, platform, engine_key)` 组内的排序号，小的先试"**。两条规则：

1. **由排序决定，不让用户手填**。新建时取 `rank` 换算的默认值（`priority = rank * 10`），之后全靠拖拽。
2. **重排后归一化为 10/20/30…**，不留空洞。

```python
async def reorder(db, element_id: int, platform: str, engine_key: str,
                  ordered_ids: list[int]) -> None:
    """全量提交（与元素排序同协议）。缺 id、多 id、重复 id 一律拒绝。"""
    current = await locator_repo.ids_in_group(db, element_id, platform, engine_key)
    _assert_same_set(current, ordered_ids, err=ElementOrderIncomplete)
    async with db.begin():
        for i, lid in enumerate(ordered_ids, start=1):
            await locator_repo.set_priority(db, lid, i * 10)
```

> **为什么必须整组提交**：`priority` 只有组内相对意义。如果前端只提交"被拖的那一条"，服务端无法知道它该落在哪两条之间（中间可能被别的用户改过）。整组提交让"最终顺序"成为唯一事实。

#### 2.7.2 `is_primary` 的唯一性

同一 `(element, platform, engine_key)` 组内**最多一条** `is_primary=1`。设置时在同一事务内先清零同组，再置 1：

```python
async def set_primary(db, locator_id: int) -> None:
    loc = await _get_or_404(db, locator_id)
    async with db.begin():
        await locator_repo.clear_primary(db, loc.element_id, loc.platform, loc.engine_key)
        await locator_repo.set_primary(db, locator_id)
```

**`is_primary` 到底影响什么？** 答案是：**不影响执行**（执行永远走 `priority` 排序的回退链）。它只影响两件事：

| 用途 | 说明 |
|---|---|
| UI 展示 | 列表里那条带「主」标记，用户一眼看出"这条是大家认可的首选" |
| 新建时的默认 `priority` | 设为 primary 时若它的 `priority` 不是最小，提示"是否同时提到第 1 位？" |

> **为什么不设成"执行只走 primary"**：那就是把回退链废掉了。primary 是**给人看的共识标记**，`priority` 才是**给机器执行的顺序**。两者分离，避免"某人标了 primary 但执行顺序不变"时产生困惑 —— 因为文档明确说了它们不联动。

#### 2.7.3 启用/禁用的语义

`enabled=0` 的定位符：**不参与解析**（`LocatorResolver._build` 已过滤），但**保留在库里**。

用途：某条定位符在特定环境失效（比如测试环境没有 `data-testid`），用户想暂时停用它而不想删掉（删了 `priority` 顺序就乱了）。UI 上是"眼睛"图标。

### 2.8 ★ 定位符验证器（D14 的支点）

#### 2.8.1 它到底做什么

一句话：**起一个真实浏览器/设备会话，打开指定页面，把每条候选定位符挨个试一遍，报告"命中几个"。**

它**不是**执行用例 —— 不跑步骤、不断言、不写 `execution` 表。它是"元素配置的体检"。

```
选择 target（决定用哪个环境的浏览器）
        ↓
adapter.start(config)          ← 复用 M1 的 SessionManager（非单例）
        ↓
navigate(url 或 target.base_url + path)
        ↓
for each 候选定位符（含未保存的草稿）:
    probe_locator(LocatorChain.of([单条]))   ← 逐条独立试，不是回退链
        ↓
返回 [{matched, sample, duration}] + 结论
        ↓
finally: adapter.stop()        ← 必须无条件执行
```

#### 2.8.2 为什么"逐条独立试"而不是"跑整条回退链"

回退链跑一次只能告诉你"第 N 条命中了"，**其余条目的好坏仍然未知**。而验证的目的是**给每条定位符打分**，所以必须一条一条试。

实现上不需要新接口：把单条定位符包成只含一个元素的 `LocatorChain`，调 `probe_locator` 即可。**这是 M1 把 `LocatorChain` 设计成"可空可单"的直接好处**。

#### 2.8.3 `probe_locator`：M1 接口的唯一新增（F-M2-3）

```python
# engines/base.py（M1 已有文件的增量）
@dataclass(frozen=True, slots=True)
class LocatorProbe:
    count: int                        # 命中元素个数
    sample: dict | None = None        # 第一个命中元素的 {tag, text, visible, attrs}
    elapsed_ms: int = 0
    error: str | None = None          # 定位表达式本身非法时的原因


class EngineAdapter(ABC):
    # ... M1 的 42 个动作方法保持不变 ...

    async def probe_locator(self, chain: LocatorChain, ctx: ActionContext) -> LocatorProbe:
        """诊断用：探测该定位符能命中几个元素。**不是用例动作**，不进 action_catalog。

        默认实现基于 check_exists 兜底（count ∈ {0,1}），桩适配器无需覆写。
        需要精确计数的引擎（如 Playwright）应覆写。
        """
        ok = await self.check_exists(chain, ctx)
        return LocatorProbe(count=1 if ok else 0)
```

Playwright 覆写（精确计数 + 样例）：

```python
async def probe_locator(self, chain: LocatorChain, ctx: ActionContext) -> LocatorProbe:
    loc = chain.first
    selector = self._to_selector(loc)          # 复用 M1 的翻译
    t0 = time.perf_counter()
    try:
        locator = self._current_frame.locator(selector)
        count = await locator.count()
        sample = None
        if count:
            first = locator.first
            sample = {
                "tag": await first.evaluate("el => el.tagName.toLowerCase()"),
                "text": (await first.inner_text())[:80],
                "visible": await first.is_visible(),
            }
        return LocatorProbe(count=count, sample=sample,
                            elapsed_ms=int((time.perf_counter() - t0) * 1000))
    except PlaywrightError as e:
        return LocatorProbe(count=0, error=str(e)[:300],
                            elapsed_ms=int((time.perf_counter() - t0) * 1000))
```

> **为什么不把 `probe_locator` 做成 `action_key='probe_locator'` 的动作**：动作会进 `action_catalog`，就会出现在 M3 的 StepEditor 下拉里 —— 用户可以编排"探测一下这个元素"当步骤。这是无意义的：探测是**平台自己的诊断行为**，不该成为用例的一部分。**动作字典的纯洁性比"复用一套分发机制"更重要。**

#### 2.8.4 结果判定：四态，但只有两态落库

| 探测结果 | 判定 | 落库 `status` | 理由 |
|---|---|---|---|
| `count == 1` | ✅ VALID | `VALID` + `verified_at=now` | 唯一命中，最理想 |
| `count > 1` | ⚠️ MULTIPLE | **不改 status**（保持原值），只写 `probe_detail` | **列表页、重复按钮是合法场景**。3 个元素同 class 不一定是错，可能就是要操作第 1 个。**不能因为"多条命中"就把定位符标成无效** |
| `count == 0` | ❌ NONE | `INVALID` + `verified_at=now` | 确定无效 |
| 抛异常（表达式非法） | 💥 ERROR | `INVALID` + `probe_detail.error` | 表达式本身写错（如 XPath 语法错误） |

> **这是本设计最容易做错的地方**：直觉上会写"count != 1 就是无效"。但那样会把"列表项定位符"（本来就命中 20 行）全部误判为无效，用户在页面上看到一片红灯后就会**不再相信这个功能** —— 一个体检工具一旦误报，就没人用了。

#### 2.8.5 超时、并发与清理

| 约束 | 值 | 为什么 |
|---|---|---|
| 单次验证总超时 | 30s | 起浏览器 + 导航 + N 条探测，正常 2–5s；超过 30s 一定是环境问题 |
| 单条探测超时 | 5s | XPath 在最坏页面上可能很慢，但不能无限等 |
| 单次最多验 | 20 条 | 超过则拒绝 `BATCH_LIMIT_EXCEEDED`，避免"验 200 条"变成一次全量扫描 |
| 项目级并发 | 1（进程内 `asyncio.Lock`） | 同时起 5 个浏览器会打爆内存；M3 有多 worker 时改 Redis 分布式锁 |
| 清理 | `finally: await adapter.stop()` | **不清理会留下僵尸 Chromium 进程**，跑几次验证后开发机的内存就满了 |

```python
async def verify(db, element_id: int, req: VerifyRequest) -> VerifyResponse:
    async with _project_lock(req.project_id):                 # 项目级串行
        adapter = registry.create(req.engine_key)              # 新实例（SessionManager 非单例）
        try:
            await asyncio.wait_for(adapter.start(cfg), timeout=15)
            await asyncio.wait_for(adapter.navigate(chain=None, ctx=ctx, url=url), timeout=10)
            results = []
            for cand in candidates:
                probe = await asyncio.wait_for(
                    adapter.probe_locator(LocatorChain.of(element_id, [cand.locator]),
                                          ctx), timeout=5)
                results.append(_judge(cand, probe))
            await _persist(db, results)                        # 只写 probe_detail / status
            return _response(results)
        except asyncio.TimeoutError:
            raise LocatorVerifyTimeout(...)
        finally:
            try:
                await adapter.stop()
            except Exception:                                  # stop 失败不能掩盖真正的错误
                logger.warning("adapter.stop failed", exc_info=True)
```

> `stop()` 的异常**必须吞掉**。否则：验证本身因为超时失败了，`stop()` 又抛一个异常 → 用户看到的是"关闭浏览器失败"，而真正的问题（页面打不开）被掩盖。

#### 2.8.6 草稿验证："先验后存"

D14 决定了没有拾取器，所以用户是"手打一串选择器 → 心里没底 → 想先试试"。因此验证接口必须支持**未保存的草稿**：

```jsonc
POST /api/v1/elements/45/locators:verify
{
  "platform": "WEB", "engine_key": "playwright", "target_id": 3,
  "url": "/login",                                  // 相对 target.base_url
  "include_saved": true,                            // 验已存的
  "drafts": [                                       // 同时验没保存的
    { "locator_type": "css", "locator_value": "#submit" },
    { "locator_type": "xpath", "locator_value": "//button[1]" }
  ]
}
```

草稿结果里 `locator_id: null`，`status` 只在响应里给（不落库）。前端拿到后显示在"草稿区"，用户满意了点保存 → 保存的就是验过的那条。

**这条闭环是 M2 的核心用户体验**：**先验证，再保存**，而不是"先存一堆猜测，再去执行时才发现全错"。

### 2.9 `reference_service`

```python
async def find_references(db, element_id: int) -> list[ElementReference]:
    """返回引用该元素的用例与步骤（供删除保护与"我在哪用过它"查询）。"""
```

```sql
SELECT c.id AS case_id, c.title, s.seq, s.action_key
FROM `test_step` s JOIN `test_case` c ON c.id = s.case_id
WHERE s.element_id = :eid AND c.is_deleted = 0
ORDER BY c.id, s.seq;
```

> **走 `idx_step_element`**（M1 已有）。若某元素被 200 个步骤引用，响应会较长 —— 设置上限 500 条并在超出时标记 `truncated: true`。

### 2.10 校验矩阵（全量，实现时逐条对照）

| 端点 | 校验 | 错误码 |
|---|---|---|
| `POST /projects/{p}/elements` | 项目存在 | `PROJECT_NOT_FOUND` |
| | `parent_id` 存在且属于同项目 | `ELEMENT_PARENT_NOT_FOUND` |
| | 父节点必须是 `FOLDER`（或 0=根） | `ELEMENT_PARENT_MUST_BE_FOLDER` |
| | 深度 ≤ 8 | `ELEMENT_DEPTH_EXCEEDED` |
| | 同级重名 | `ELEMENT_NAME_DUPLICATED` |
| | `node_type` 合法 | `VALIDATION_ERROR` |
| `PATCH /elements/{id}` | 存在 | `ELEMENT_NOT_FOUND` |
| | 改名时同级重名 | `ELEMENT_NAME_DUPLICATED` |
| | `node_type` 变更需无子节点 / 无定位符 | `ELEMENT_NODE_TYPE_CONFLICT` |
| `POST /elements/{id}/move` | 目标父存在、属同项目 | `ELEMENT_PARENT_NOT_FOUND` |
| | 不能移到自身或子树 | `ELEMENT_MOVE_INTO_DESCENDANT` |
| | 深度（含子树高度）≤ 8 | `ELEMENT_DEPTH_EXCEEDED` |
| | 目标父下重名 | `ELEMENT_NAME_DUPLICATED` |
| `PUT /elements/{id}/children-order` | id 集合与现有子节点完全一致 | `ELEMENT_ORDER_INCOMPLETE` |
| | 数量 ≤ 500 | `BATCH_LIMIT_EXCEEDED` |
| `DELETE /elements/{id}` | 无引用（未被 force） | `ELEMENT_REFERENCED` |
| | FOLDER 无子节点 | `ELEMENT_FOLDER_NOT_EMPTY` |
| `POST /elements/{id}/locators` | 元素存在且为 `ELEMENT` | `ELEMENT_NOT_FOUND` / `ELEMENT_FOLDER_HAS_NO_LOCATOR` |
| | 类型在平台字典内 | `ELEMENT_LOCATOR_TYPE_INVALID` |
| | 类型被该引擎支持 | `ELEMENT_LOCATOR_TYPE_ENGINE_UNSUPPORTED` |
| | `engine_key='*'` 时类型需全引擎支持 | `ELEMENT_LOCATOR_WILDCARD_UNSCOPED` |
| | 同 (element,platform,engine,type,value) 不重复 | `ELEMENT_LOCATOR_DUPLICATED` |
| `PUT .../locators/order` | id 集合与组内现有完全一致 | `ELEMENT_ORDER_INCOMPLETE` |
| `POST .../locators:verify` | `target_id` 或 `url` 至少一个 | `LOCATOR_VERIFY_TARGET_REQUIRED` |
| | 候选数 ≤ 20 | `BATCH_LIMIT_EXCEEDED` |
| | 总耗时 ≤ 30s | `LOCATOR_VERIFY_TIMEOUT` |

### 2.11 CLI（可选但建议）

M1 有 CLI（§2.9）。M2 加三个子命令，便于**批量体检**与**CI 前置检查**：

```bash
# 体检某项目所有元素在指定端下的定位符健康度
python -m app.cli locators audit --project 1 --platform WEB

# 输出示例（表格，非 JSON）：
#  元素                定位符                          状态    命中  耗时
#  登录/登录按钮        testid=login-submit            VALID   1    42ms
#  登录/登录按钮        css=#submit                    VALID   1    38ms
#  登录/错误提示        testid=err-msg                 NONE    0    ——      ← 红
#  公共/顶部导航        class=nav-item                 MULTI   7    51ms    ← 黄

# 校验 DDL 与文档一致（附录 A 是否已落成 schema.sql）
python -m app.cli schema check

# 校验定位字典与引擎注册表一致（等价于 2.5.5 的启动校验，但可单独跑）
python -m app.cli locators doctor
```

> `audit` 的价值：**M2 交付时可以用它对 e2e fixture 页跑一遍，作为 V4 的批量证据**；更重要的是它能在 M4 接 App 后，一次性告出"Android 端有多少元素根本没配定位符"。

---

## 3. 接口契约（M2 全量）

### 3.1 通用规范（继承 M1，不重新定义）

| 项 | 规范 |
|---|---|
| 前缀 | `/api/v1` |
| 错误体 | `{"error": {"code": "...", "message": "...", "detail": {...}, "trace_id": "..."}}` |
| 错误码命名 | `<域>_<语义>`，域 = **资源名**（`ELEMENT` / `ELEMENT_LOCATOR` / `LOCATOR_VERIFY`） |
| 时间 | ISO 8601 带时区 |
| 布尔 | JSON `true/false`（DB 里是 `TINYINT`，序列化层转换） |
| 分页 | `?page=1&size=50`，响应 `{items, total, page, size}`；**树接口不分页** |
| 软删 | 列表默认只返回未删；`?include_deleted=true` 才带（仅调试用） |

> **域 = 资源名，不是操作名** —— 这条是 M1 `ELEMENT_LOCATOR_TYPE_INVALID` 已经隐含的约定（它的域是「元素定位符」这个资源，不是「元素」）。M2 沿用，不发明新风格。

### 3.2 错误码增量（17 个）

| HTTP | 错误码 | 触发 | `detail` 含什么 |
|---|---|---|---|
| 404 | `ELEMENT_NOT_FOUND` | 元素不存在或已删 | `element_id` |
| 422 | `ELEMENT_PARENT_NOT_FOUND` | 父节点不存在 / 跨项目 | `parent_id` |
| 422 | `ELEMENT_PARENT_MUST_BE_FOLDER` | 想挂到 `ELEMENT` 下 | `parent_id`, `parent_type` |
| 422 | `ELEMENT_DEPTH_EXCEEDED` | 深度 > 8 | `depth`, `max_depth` |
| 422 | `ELEMENT_MOVE_INTO_DESCENDANT` | 移到自己/子树下 | `element_id`, `target_parent_id` |
| 409 | `ELEMENT_NAME_DUPLICATED` | 同级重名 | `element_name`, `parent_id`, `conflict_id` |
| 409 | `ELEMENT_REFERENCED` | 被用例引用时删除 | **`references: [{case_id, title, step_seq, action_key}]`** |
| 409 | `ELEMENT_FOLDER_NOT_EMPTY` | 删非空目录 | `child_count` |
| 422 | `ELEMENT_FOLDER_HAS_NO_LOCATOR` | 给目录配定位符 | `element_id` |
| 409 | `ELEMENT_NODE_TYPE_CONFLICT` | 改 `node_type` 但有子节点/定位符 | `child_count`, `locator_count` |
| 422 | `ELEMENT_ORDER_INCOMPLETE` | 排序提交的 id 集合不符 | `missing_ids`, `extra_ids` |
| 409 | `ELEMENT_LOCATOR_DUPLICATED` | 同 element+platform+engine+type+value 重复 | `existing_id` |
| 422 | `ELEMENT_LOCATOR_TYPE_ENGINE_UNSUPPORTED` | 类型不被该引擎支持 | `locator_type`, `engine_key`, `supported_engines` |
| 422 | `ELEMENT_LOCATOR_WILDCARD_UNSCOPED` | `'*'` + 引擎专属类型 | `locator_type`, `only_engines` |
| 422 | `LOCATOR_VERIFY_TARGET_REQUIRED` | 既没 `target_id` 也没 `url` | — |
| 504 | `LOCATOR_VERIFY_TIMEOUT` | 验证超 30s | `stage`（start/navigate/probe） |
| 422 | `BATCH_LIMIT_EXCEEDED` | 批量超上限 | `limit`, `actual` |

> **`ELEMENT_REFERENCED` 的 `detail` 是本设计里信息量最大的一个**：它不只是说"删不掉"，而是告诉你"**谁在用它**"（用例名 + 第几步 + 什么动作）。没有这个，用户只能自己去翻用例 —— 元素库就会变成"越用越不敢删"的死水。

### 3.3 端点清单（18 个）

**元素（9）**

| # | 方法 | 路径 | 用途 |
|---|---|---|---|
| E1 | GET | `/projects/{pid}/elements` | 元素树 / 子树 / 搜索（`?parent_id=&keyword=&depth=`） |
| E2 | GET | `/elements/{eid}` | 详情（含 `path`、`depth`、`locator_count` 分端统计） |
| E3 | POST | `/projects/{pid}/elements` | 新建元素 / 目录 |
| E4 | PATCH | `/elements/{eid}` | 改名 / 描述 / memo / `sort` |
| E5 | DELETE | `/elements/{eid}` | 软删（`?force=true` 跳过引用检查） |
| E6 | POST | `/elements/{eid}/move` | 移动到新父 / 指定位置 |
| E7 | PUT | `/elements/{eid}/children-order` | 同级重排（全量 id 列表） |
| E8 | GET | `/elements/{eid}/references` | 被哪些用例步骤引用 |
| E9 | POST | `/elements/{eid}/duplicate` | 复制（含全部定位符），`?target_parent_id=` |

**定位符（7）**

| # | 方法 | 路径 | 用途 |
|---|---|---|---|
| L1 | GET | `/elements/{eid}/locators` | 按 platform/engine 分组返回全部定位符 |
| L2 | POST | `/elements/{eid}/locators` | 新增（或 `bulk: true` 批量新增多端） |
| L3 | PATCH | `/element-locators/{lid}` | 改值 / `enabled` / `remark` |
| L4 | DELETE | `/element-locators/{lid}` | 物理删除 |
| L5 | PUT | `/elements/{eid}/locators/order` | 组内重排（全量 id 列表） |
| L6 | POST | `/elements/{eid}/locators:verify` | ★ 验证（含草稿） |
| L7 | POST | `/element-locators/{lid}:set-primary` | 设为首选（同组唯一） |

**元数据（2）**

| # | 方法 | 路径 | 用途 |
|---|---|---|---|
| M1 | GET | `/locator-types` | 三端定位字典（前端下拉 + 示例值 + 引擎支持） |
| M2 | GET | `/projects/{pid}/element-stats` | 元素/定位符覆盖统计（分端缺配数、验证状态分布） |

### 3.4 关键接口的请求/响应

#### E1 · 取元素树

```jsonc
// GET /api/v1/projects/1/elements?parent_id=0
{
  "items": [
    { "id": 7, "parent_id": 0, "path": "/7/", "depth": 1,
      "element_name": "登录模块", "node_type": "FOLDER", "sort": 10,
      "locator_count": { "WEB": 0, "ANDROID": 0, "IOS": 0 },
      "children": [
        { "id": 45, "parent_id": 7, "path": "/7/45/", "depth": 2,
          "element_name": "登录按钮", "node_type": "ELEMENT", "sort": 10,
          "locator_count": { "WEB": 3, "ANDROID": 1, "IOS": 0 },
          "children": [] }
      ] }
  ],
  "total": 2
}
```

> `locator_count` 是**该元素自身**的统计（不含子节点）。前端在树节点右侧显示 `WEB 3 / A 1 / I 0` 三个小徽标 —— 一眼看出"iOS 还没配"。这是 M2 里最省事却最有用的一个字段。

#### E3 · 新建元素

```jsonc
// POST /api/v1/projects/1/elements
{ "parent_id": 7, "element_name": "登录按钮", "node_type": "ELEMENT",
  "description": "登录页主按钮", "memo": "提交用户名密码；成功后跳 /home" }

// 201
{ "id": 45, "parent_id": 7, "path": "/7/45/", "depth": 2,
  "element_name": "登录按钮", "node_type": "ELEMENT",
  "is_shared": 1,                      // D16：恒为 1，前端传了也忽略
  "created_at": "2026-10-19T15:02:11+08:00" }
```

#### L1 · 取定位符（按端分组）

```jsonc
// GET /api/v1/elements/45/locators
{
  "element_id": 45,
  "groups": [
    { "platform": "WEB", "engine_key": "playwright", "primary_id": 771,
      "items": [
        { "id": 771, "locator_type": "testid", "locator_value": "login-submit",
          "priority": 10, "is_primary": true, "enabled": true,
          "status": "VALID", "verified_at": "2026-10-19T15:20:03+08:00",
          "probe_detail": { "matched": 1, "sample": { "tag": "button", "text": "登录" } } },
        { "id": 772, "locator_type": "css", "locator_value": "#submit",
          "priority": 20, "is_primary": false, "enabled": true,
          "status": "UNVERIFIED", "verified_at": null, "probe_detail": null }
      ] },
    { "platform": "ANDROID", "engine_key": "*", "primary_id": null, "items": [ /* ... */ ] },
    { "platform": "IOS", "engine_key": "appium", "primary_id": null, "items": [] }
  ],
  "coverage": { "WEB": 3, "ANDROID": 1, "IOS": 0 }
}
```

> **空组也要返回**。iOS 一条都没有时返回 `{"platform":"IOS","items":[]}`，前端才能稳定渲染三个 tab 并把空 tab 标灰。如果只返回有数据的组，前端要自己拼三个 tab 并判断"哪个缺失" —— 又是一个能省则省的逻辑。

#### L2 · 新增定位符（批量）

```jsonc
// POST /api/v1/elements/45/locators  {"bulk": true, "items": [...]}
{ "bulk": true, "items": [
    { "platform": "WEB",     "engine_key": "playwright",
      "locator_type": "testid", "locator_value": "login-submit", "priority": 10 },
    { "platform": "ANDROID", "engine_key": "*",
      "locator_type": "resource_id", "locator_value": "com.demo:id/login_btn", "priority": 10 },
    { "platform": "IOS",     "engine_key": "appium",
      "locator_type": "accessibility_id", "locator_value": "loginBtn", "priority": 10 }
  ]
}

// 201 —— 全成或全败（同一事务）
{ "created": [774, 775, 776], "failed": [] }

// 207（部分失败）—— 只在 bulk 时使用，逐条给结果
{ "created": [774], "failed": [
    { "index": 1, "code": "ELEMENT_LOCATOR_TYPE_ENGINE_UNSUPPORTED",
      "message": "定位类型 uiautomator 仅 appium 支持，不能用于 engine_key='*'" }
  ] }
```

> **为什么批量允许"部分成功"（207）而不是全回滚**：用户在建一个元素时通常会一次性配三端。如果因为 iOS 那条类型写错，导致 Web 和 Android 也白填 —— 这是很差的体验。逐条返回结果，前端标红错的那条，其余保留。**事务粒度按条，而不是按请求**。
>
> 但**单条模式**（`bulk` 缺省）是全成或全败，因为那时请求体只有一条，没有"I 部分成功"的语义。

#### L6 · ★ 验证定位符

```jsonc
// POST /api/v1/elements/45/locators:verify
{
  "platform": "WEB", "engine_key": "playwright", "target_id": 3, "url": "/login",
  "include_saved": true,
  "drafts": [
    { "locator_type": "css",        "locator_value": "#submit" },
    { "locator_type": "xpath",      "locator_value": "//button[@id='nope']" }
  ]
}

// 200
{
  "checked_at": "2026-10-19T15:31:40+08:00",
  "target_id": 3, "url": "http://localhost:8899/login",
  "duration_ms": 1834,
  "results": [
    { "locator_id": 771, "locator_type": "testid", "locator_value": "login-submit",
      "verdict": "VALID", "matched": 1, "duration_ms": 42,
      "sample": { "tag": "button", "text": "登录", "visible": true },
      "persisted_status": "VALID" },
    { "locator_id": 772, "locator_type": "css", "locator_value": "#submit",
      "verdict": "VALID", "matched": 1, "duration_ms": 38,
      "sample": { "tag": "button", "text": "登录", "visible": true },
      "persisted_status": "VALID" },
    { "locator_id": null, "locator_type": "css", "locator_value": "#submit",
      "verdict": "MULTIPLE", "matched": 3, "duration_ms": 45,
      "sample": { "tag": "button", "text": "登录" },
      "persisted_status": null },
    { "locator_id": null, "locator_type": "xpath", "locator_value": "//button[@id='nope']",
      "verdict": "NONE", "matched": 0, "duration_ms": 31,
      "sample": null, "persisted_status": null }
  ],
  "summary": { "valid": 2, "multiple": 1, "none": 1, "error": 0 },
  "verdict": "HAS_PROBLEM"
}
```

`verdict` 取值：

| 值 | 含义 | UI 呈现 |
|---|---|---|
| `ALL_VALID` | 全部唯一命中 | 绿色条「4 条定位符全部有效」 |
| `HAS_PROBLEM` | 有 MULTIPLE / NONE / ERROR | 黄色条「1 条命中多个，1 条未命中」 |
| `ALL_INVALID` | 全部无效 | 红色条「全部未命中，检查页面是否加载正确」 |

### 3.5 并发、幂等与失败模式

| 场景 | 行为 | 说明 |
|---|---|---|
| 两人同时拖拽同一父节点 | **后写覆盖**，且先写者若集合不匹配会收到 `ELEMENT_ORDER_INCOMPLETE` | 全量提交协议天然"快速失败"：A 拖完 → B 的 `ordered_ids` 与当前不符 → B 收到 409 → 前端重新拉取树。**不会出现静默错乱的排序** |
| 两人同时改同一元素名 | 一个成功，一个收到 `ELEMENT_NAME_DUPLICATED` 或 200（若名字不同） | 唯一键兜底 |
| 同一元素并发验证 | 项目级锁串行；第二个请求**排队**（最多等 30s），超时 `LOCATOR_VERIFY_TIMEOUT` | 不做"复用正在进行的验证结果"—— 因为两次请求的草稿可能不同 |
| 验证过程中删掉了该元素 | 验证继续跑完（用的是内存快照），`_persist` 时定位符已不在 → 跳过写入并记 `warning` | 不因"数据被删"让整个请求 500 |
| 重复 `POST /elements`（同一内容） | **不幂等**，第二次 `ELEMENT_NAME_DUPLICATED` | 元素创建没有天然幂等键，不做 Idempotency-Key（M2 无此需求） |

> **乐观并发锁是刻意的"不做"**（RV10）：全量提交协议已经让冲突"可见且可恢复"，加 `If-Match` + `version` 列的收益不足以抵消复杂度（前端每处编辑都要带 version）。等真正出现"多人同时编辑元素"的投诉再补。

---

## 4. 前端设计（M2 的主战场）

### 4.1 范围与不做

**M2 前端只做一件事：让人能高效地"建元素、配三端定位符、验证它、调顺序"。**

| 做 | 不做 |
|---|---|
| 元素库三栏页面（树 / 详情 / 定位符） | 页面拾取器（D14） |
| 树形拖拽（排序 + 跨父移动） | 虚拟滚动（元素 > 1000 时看情况） |
| 三端 tab + 回退链拖拽调序 | 定位符健康度图表（M3 后） |
| 验证（含草稿）+ 结果条 | 元素版本历史 |
| 搜索（按名字，含祖先链高亮） | 批量导入 / Excel |
| 空状态引导（"还没有元素，先建一个目录"） | 权限控制 |

### 4.2 技术选型（落实 D13 留下的决定）

| 需求 | 方案 | 理由 |
|---|---|---|
| UI 基础（按钮/输入/弹层/toast） | **自建 4 个原语**：`AppButton` / `AppInput` / `AppModal` / `AppToast` | 延续 D13。M2 需要控件的种类不超过 6 种，引入组件库（Element Plus ≈ 200KB+）不划算 |
| **拖拽排序** | **`vuedraggable@4`（底层 SortableJS，gzip ≈ 12KB）** | **D18 的决策点**。手写 HTML5 DnD 处理"拖到节点上方/内部/下方"三态 + 触摸 + 自动滚动至少 300 行，且边界情况（拖到自己子树、拖到 `ELEMENT` 内）全靠自己判 —— 12KB 换 300 行高 bug 风险代码，值 |
| 树组件 | **自建 `AppTree.vue`** | 树是本项目最核心的交互，第三方树的 API（懒加载/虚拟滚动/自定义拖拽约束）反而束缚手脚。自建 ≈ 250 行，完全可控，且 M3 的用例目录能复用 |
| 状态 | Pinia（M1 已装） | — |
| 请求 | axios 封装（M1 已有） + `toastError`（M1 已建） | — |

> **D18 与 D13 的关系要说清**：D13 拒绝的是"**全家桶组件库**"（为一张表格装 200KB，且样式体系会渗透到整个应用）。D18 接受的是"**单一职责的小库**"（只做拖拽，不提供任何视觉样式，不侵入组件体系）。判据不是"体积"，而是"**是否引入一套需要遵循的设计体系**"。SortableJS 不引入体系，它只是一个 DOM 事件库。

### 4.3 页面布局：三栏

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 元素库  项目: Demo Web 中台 ▾      [搜索元素名…]            [新建目录] [新建元素] │
├────────────────────┬────────────────────────────────────────────────────────┤
│ 元素树（可拖拽）     │ 登录按钮                                    [保存] [删除] │
│                    │ 路径: /登录模块/登录页/登录按钮   类型: 元素              │
│ ▾ 登录模块      W3 │ 描述: [登录页主按钮                    ]                  │
│   ▾ 登录页      W2 │ 说明: [提交用户名密码；成功后跳 /home   ]  ← memo          │
│     • 登录按钮  W3 ├────────────────────────────────────────────────────────┤
│     • 错误提示  W1 │ 定位符        [ WEB 3 ] [ ANDROID 1 ] [ IOS 0 ]          │
│   ▸ 注册页       — │ ┌──────────────────────────────────────────────────────┐ │
│ ▸ 公共组件      W5 │ │ ⠿ ● testid   login-submit        VALID  1命中  [验证] │ │
│                    │ │ ⠿ ○ css      #submit            VALID  1命中  [验证] │ │
│                    │ │ ⠿ ○ xpath    //button[1]        未验证         [验证] │ │
│                    │ │ ──────────────────────────────────────────────────── │ │
│                    │ │ + 添加定位符    [类型▾] [值___________] [先验证] [保存]│ │
│                    │ └──────────────────────────────────────────────────────┘ │
│                    │ ┌ 验证结果 ────────────────────────────────────────────┐ │
│                    │ │ ✅ 2 条有效   ⚠️ 1 条命中多个(3)   ❌ 1 条未命中        │ │
│                    │ │ ❌ xpath //button[@id='nope']  → 0 个命中 (31ms)      │ │
│                    │ └──────────────────────────────────────────────────────┘ │
└────────────────────┴────────────────────────────────────────────────────────┘
```

**为什么是三栏而不是"列表 + 弹窗编辑"**：元素库的核心动作是"在树里找一个元素，改它的定位符，然后验证"。列表 + 弹窗会让这四步变成"列表 → 点开弹窗 → 改 → 关弹窗 → 再点开"的来回跳转。三栏让**树、元素、定位符同时在视野内**，切换元素时只有右侧变化，树的展开状态不丢。

### 4.4 交互设计（逐条给出实现约束）

#### 4.4.1 树的拖拽：三种落点

| 落点 | 视觉 | 行为 | 约束 |
|---|---|---|---|
| **上边缘** | 上方 2px 蓝线 | 插到该节点**前面**（同级） | — |
| **下边缘** | 下方 2px 蓝线 | 插到该节点**后面**（同级） | — |
| **中间** | 整行高亮 | 移入该节点**成为子节点** | 仅目标为 `FOLDER` 时允许；目标是 `ELEMENT` 时**降级为同级插入** |

> **"拖到 ELEMENT 上自动降级为同级"** 是必要的：用户拖一个元素到另一个元素上时，意图通常是"我想把它放在它旁边"，而不是"我要创建一个层级错误"。直接拒绝（弹 toast"不能挂到元素下"）会让拖拽体验变差。降级 + 一次轻微的 toast 提示（"已插入为同级节点"）是更顺的处理。
>
> **但服务端仍然严格拒绝**（`ELEMENT_PARENT_MUST_BE_FOLDER`）。前端降级是**体验优化**，不是**放宽约束** —— 万一前端有 bug 或有人直接调 API，数据依然合法。

拖拽实现要点（SortableJS 配置）：

```ts
const draggable = new Sortable(treeEl, {
  group: { name: 'elements', pull: true, put: true },
  handle: '.drag-handle',          // 只有手柄可拖，避免误触
  fallbackOnBody: true,
  invertSwap: true,                // 相邻节点间隙小时仍能正确判定前后
  onEnd: async ({ item, to, newIndex, oldIndex }) => {
    const movedId = Number(item.dataset.id)
    const newParentId = Number(to.dataset.parentId ?? 0)
    // 统一走"移动 + 排序"一个接口：先 move（改父），再 children-order（定序）
    await api.moveElement(movedId, { parent_id: newParentId, index: newIndex })
    await refreshTree(newParentId)      // 服务端返回的 path/sort 才是事实，本地乐观更新只用于瞬时反馈
  },
})
```

> **不要在本地"改完就完事"**：`path` 与 `sort` 的最终值由服务端计算（`path` 依赖 `id`，`sort` 依赖归一化）。前端只做**瞬时**视觉反馈，收到响应后以服务端数据重绘。**否则会出现"前端显示对、刷新后错位"** —— 这是树形拖拽最常见的坑。

#### 4.4.2 定位符面板：三端 tab + 回退链

| 元素 | 设计 |
|---|---|
| Tab | 固定三个（`WEB` / `ANDROID` / `IOS`），标题带条数徽标；空 tab 文字灰显但**可点**（点进去就是"添加第一条"的引导） |
| 组内排序 | 一个 tab 内可能有多组（Android 有 `*` 与 `appium` 两组）。**按组分区展示**，组标题写 `engine_key`，组内是回退链 |
| 行内元素 | `⠿` 拖拽手柄 · 状态灯 · `locator_type` 标签 · 值（等宽字体，可复制） · 命中数 · `[验证]` · `[⋮]`（设为首选 / 禁用 / 删除） |
| 编辑方式 | **行内点击值即进入编辑**（`contenteditable` 或 input），失焦自动保存；类型不可行内改（改类型要走删除 + 新建，避免"改了类型值不适配"） |
| 新增 | 底部一行：类型下拉（来自 `GET /locator-types`，带 `example` 作为 placeholder）+ 值输入 + `[先验证]` / `[直接保存]` |

**状态灯的四色语义**（必须与 §2.8.4 的判定一致）：

| 灯 | 条件 | 含义 |
|---|---|---|
| ⚪ 灰 | `UNVERIFIED` | 没验过，不代表错 |
| 🟢 绿 | `VALID` 且 `matched=1` | 唯一命中 |
| 🟡 黄 | 最近一次 `matched>1` | 命中多个 —— **不一定是错**，需人判断 |
| 🔴 红 | `INVALID`（`matched=0` 或表达式非法） | 确定无效 |

> **灰色必须存在且不能是"淡红"**。用户新加一条定位符还没验时，如果显示成红色，他会以为出错了。M2 里"未验证"是一个**合法且常见**的状态。

#### 4.4.3 "先验证，再保存"的闭环（D14 的核心体验）

```
[输入 css #submit] ──点[先验证]──> 调 verify(drafts=[这条])
                                        ↓
                          结果条显示「✅ 1 个命中 · button「登录」· 38ms」
                                        ↓
                        ┌───────────────┴───────────────┐
                   满意 → [保存]                    不满意 → 改值重验
                   （保存时不再验）                  （草稿覆盖）
```

**关键约束**：

| 约束 | 原因 |
|---|---|
| 验证结果挂在**草稿对象**上（`localId`），不依赖 `locator_id` | 草稿还没 id |
| 保存时**不重新验证** | 用户已经看过了；再验一次会让"保存"慢 2 秒 |
| 保存后把草稿的验证结果**带入**新记录（写 `probe_detail`） | 避免"刚验过，保存后又变成未验证" |
| 草稿可多条一起验 | 用户常一次写 3 条候选，想一次性看谁有效 |

#### 4.4.4 搜索：扁平结果 + 祖先链

搜索时不返回树，返回扁平列表，每条带 `path_names`（祖先名数组）：

```
[登录模块 / 登录页]  登录按钮      W3 A1 I0
[公共组件 / 顶部导航] 用户头像      W1 A0 I0
```

点结果 → 自动展开树的祖先链并选中该节点。**这个"展开祖先链"是搜索唯一有点难度的部分**：需要先把 `path` 拆成 id 列表，逐层 `expand`。

#### 4.4.5 删除确认的内容

删除确认框里必须显示**引用情况**（先调 `E8 references`）：

```
删除「登录按钮」？

该元素被 2 个用例的 3 个步骤引用：
  · 登录成功流程 - 第 2 步 click
  · 登录成功流程 - 第 5 步 get_text
  · 登录失败提示 - 第 3 步 assert_visible

⚠️ 删除后这些步骤将无法执行。
[取消]  [强制删除]      ← 只在有引用时出现，且是危险色
```

> **不要提供"删除并自动跳过那些步骤"**。那是破坏用户用例的行为，M2 不做。用户要么先改用例，要么明确强制删除（自己承担后果）。

### 4.5 状态管理

```ts
// stores/element.ts
export const useElementStore = defineStore('element', () => {
  const projectId = ref<number | null>(null)
  const tree = ref<ElementNode[]>([])            // 全量树（一次加载）
  const expandedIds = ref<Set<number>>(new Set())
  const selectedId = ref<number | null>(null)
  const detail = ref<ElementDetail | null>(null)
  const locatorGroups = ref<LocatorGroup[]>([])  // 当前元素的定位符（按组）
  const drafts = ref<LocatorDraft[]>([])         // 未保存的草稿
  const verifyResult = ref<VerifyResponse | null>(null)
  const loading = reactive({ tree: false, detail: false, verify: false })

  // 派生：当前选中节点的祖先链（用于面包屑与搜索定位）
  const ancestorChain = computed(() => /* 从 path 拆 id → 找节点 */)
  return { /* ... */ }
})
```

**为什么 `drafts` 要放在 store 而不是组件内**：切换选中元素时如果草稿在组件里，会被组件的重新渲染清掉 —— 用户"写了一半去看别的元素再回来"就丢了。放 store 里并按 `elementId` 分组保存草稿。

### 4.6 与后端的对接点

| 前端动作 | 后端接口 | 备注 |
|---|---|---|
| 进入元素库 | `GET /projects/{pid}/elements` + `GET /locator-types` | 两个请求并发；字典可缓存（同一会话内不变） |
| 选中节点 | `GET /elements/{eid}` + `GET /elements/{eid}/locators` | 并发 |
| 新建元素 | `POST /projects/{pid}/elements` | 成功后插入树（用返回的 `path` 定位父节点） |
| 拖拽结束 | `POST /elements/{eid}/move` | 统一走 move（含 index） |
| 删除前 | `GET /elements/{eid}/references` | 先查再弹确认 |
| 删除 | `DELETE /elements/{eid}` | 被拒时展示 `detail.references` |
| 新增定位符 | `POST /elements/{eid}/locators` | 草稿带验证结果时，一并传 `probe_detail` |
| 拖拽定位符 | `PUT /elements/{eid}/locators/order` | 组内全量 id |
| 点验证 | `POST /elements/{eid}/locators:verify` | `include_saved` + `drafts` |
| 统计条 | `GET /projects/{pid}/element-stats` | 页面顶部"Web 缺配 12 个" |

### 4.7 交互验收（F1–F9）

| # | 操作 | 期望 |
|---|---|---|
| **F1** | 打开元素库（空项目） | 显示引导"还没有元素。先建一个目录，再在目录下建元素"，两个按钮可用 |
| **F2** | 新建 3 层目录 + 1 个元素 | 树立刻出现；元素节点显示 `W0 A0 I0` 三个灰徽标 |
| **F3** | 拖元素到另一目录 | 树即时移动；刷新页面后位置**不变**（验证服务端 `path` 已更新） |
| **F4** | 拖元素到另一个元素「中间」 | 不报错，插入为同级，并出现轻提示"已插入为同级节点" |
| **F5** | 给元素加 Web 定位符并"先验证" | 结果条显示命中数与样例文本；点保存后行内状态灯变绿 |
| **F6** | 故意写一个不存在的 xpath 验证 | 红灯 + "0 个命中"；保存后 `status=INVALID` |
| **F7** | 切到 Android tab 加 `resource_id` | 成功；切到 iOS tab 加 `css` | iOS tab 的类型下拉里**没有 css 选项**（前端已按字典过滤） |
| **F8** | 拖定位符调整顺序后执行用例 | 执行结果 `fallback_index` 的分布随顺序变化（第 1 位命中则 `fallback_index=0`） |
| **F9** | 删除被引用的元素 | 弹窗列出引用清单；点强制删除后元素消失，用例步骤仍指向已删元素（M3 执行时报 `ELEMENT_NOT_FOUND`） |

> **F7 的后半句是本设计的一个额外收益**：既然 `GET /locator-types` 已经带了"每个类型被哪些引擎支持"，前端**可以直接把不合法的选项过滤掉** —— 用户根本选不到"给 iOS 配 css"。服务端校验是防线，前端过滤是体验。**两层都要有。**

---

## 5. 测试与验收

### 5.1 测试分层（沿用 M1 的三层，但 M2 的集成层更重）

| 层 | 环境 | 覆盖什么 | 不覆盖什么 |
|---|---|---|---|
| **单测** | SQLite in-memory + `FakeAdapter` | `path` 算法、循环检测、深度、唯一性逻辑、字典校验、排序归一化、引用计数、验证结果判定 | MySQL 特有行为（`LIKE` 前缀索引、`SUBSTRING` 语义、唯一键） |
| **集成** | 真实 **MySQL 8** | DDL 生效、唯一键冲突（V6）、`rewrite_path_prefix` 的 SQL 正确性、批量事务与 207 | 浏览器行为 |
| **e2e** | 真实 Playwright + 静态 fixture | 回退链（V3）、验证器（V4）、用例改用元素引用（V10） | 移动端（M4） |

> **M2 必须加重集成层的原因**：`rewrite_path_prefix` 的核心是 `CONCAT + SUBSTRING + LIKE` 三个 MySQL 函数联用。SQLite 上 `SUBSTRING` 与 `LIKE` 的行为差异（大小写、`LIKE` 转义）足以让单测绿、线上红。**这条 SQL 必须在真 MySQL 上验**。

### 5.2 单测清单（18 组）

| # | 文件 | 覆盖 | 表驱动要点 |
|---|---|---|---|
| U1 | `test_locator_types.py` | 字典完整性：三端每个类型字段非空、`rank` 唯一、`engines ⊆ platform.engines`、**不允许出现引擎语汇**（正则黑名单：`uiautomator`/`predicate string`/`resourceId=` 等） | 遍历 + 断言 |
| U2 | `test_locator_dict_consistency.py` | §2.5.5 的三道启动校验，各造一个违反场景 | 3 个反例 |
| U3 | `test_tree_path_build.py` | `path` 组装：根 / 1 层 / 8 层 / 超 8 层 | 4 组 |
| U4 | `test_tree_depth.py` | 深度计算（`/` 计数 - 1）与 `MAX_DEPTH` 边界（7、8、9） | 3 组 |
| U5 | `test_tree_cycle.py` | 循环检测：移到自身 / 移到直接子 / 移到孙子 / 移到无关节点（应通过） | 4 组 |
| U6 | `test_tree_rewrite.py`（单测版，仅验证拼接逻辑） | `new_prefix + tail` 的字符串拼接（不含 SQL） | 5 组 |
| U7 | `test_tree_order.py` | 同级排序归一化：`[45,12,7]` → `sort = 10,20,30`；集合不符 → `ELEMENT_ORDER_INCOMPLETE` | 3 组 |
| U8 | `test_element_name_unique.py` | 同级重名；**软删后同名可重建**（V6 的单测版） | 3 组 |
| U9 | `test_element_delete.py` | 有引用拒绝 / 无引用软删 / FOLDER 非空拒绝 / force 通过 | 4 组 |
| U10 | `test_locator_validate.py` | 三层校验：类型非法 / 引擎不支持 / 通配不限域 | 6 组（含"通配 + 通用类型应通过"） |
| U11 | `test_locator_priority.py` | 新建默认 `priority = rank*10`；重排归一化；与 `LocatorResolver` 的解析顺序一致 | 4 组 |
| U12 | `test_locator_primary.py` | 组内唯一；跨组互不影响（同元素不同 platform 各有一条 primary） | 3 组 |
| U13 | `test_locator_duplicate.py` | 同五元组重复 → `ELEMENT_LOCATOR_DUPLICATED` | 2 组 |
| U14 | `test_verify_judge.py` | ★ 判定四态：1/0/多/异常；**MULTIPLE 不改 status** | 8 组 |
| U15 | `test_verify_persist.py` | 只写 `probe_detail` / `status` / `verified_at`，不写 `execution` 表 | 2 组 |
| U16 | `test_references.py` | 引用查询含 `case_id/title/seq/action_key`；超 500 条标记 `truncated` | 2 组 |
| U17 | `test_element_stats.py` | `LEFT JOIN GROUP BY` 的分端计数（含"元素无任何定位符"应计 0 而不是被丢弃） | 3 组 |
| U18 | `test_probe_default.py` | `FakeAdapter` 未覆写 `probe_locator` 时走默认实现（count ∈ {0,1}），**不抛 NotImplementedError** | 2 组 |

> **U18 是 F-M2-3 的守门测试**。若默认实现不小心写成 `raise NotImplementedError`，桩适配器在验证时就会崩 —— 而 M4 之前所有 Android/iOS 适配器都是桩。这条测试锁住"诊断能力对桩也必须可用"。

### 5.3 集成测试（7 组，真 MySQL）

| # | 覆盖 | 关键断言 |
|---|---|---|
| I1 | DDL 冒烟 | 两张表建成；`uk_element_name` 存在且含 `deleted_seq`；`idx_element_name` 存在 |
| I2 | ★ V6 软删除唯一性 | 建→删→建→删 同名元素，**两次都成功**（F-M2-2 的回归测试） |
| I3 | ★ `rewrite_path_prefix` | 3 层子树移到另一个父下：所有后代 `path` 前缀正确、长度正确、无粘连 |
| I4 | 前缀查询走索引 | `EXPLAIN` 断言 `path LIKE '/7/%'` 使用 `idx_element_path`（**不是全表扫**） |
| I5 | 批量定位符事务 | `bulk` 全成功提交；含一条非法时返回 207 且合法那条已落库 |
| I6 | 并发建同名 | 两个协程同时建同名元素：一个 201、一个 409，**不出现两条同名记录** |
| I7 | 并发排序 | A、B 同时提交不同的 `ordered_ids`：一个成功、一个 `ELEMENT_ORDER_INCOMPLETE` |

### 5.4 e2e（3 组，真浏览器）

| # | 场景 | 步骤 | 断言 |
|---|---|---|---|
| E1 | ★ V3 回退链 | `login.html` 上配三条定位符：① 故意错的 `testid` ② 正确的 `css=#submit` ③ `xpath` | 执行登录用例 `PASSED`；`fallback_index=1`；`used_locator_id` = ② 的 id |
| E2 | ★ V4 验证器 | 对 `locators.html` 逐类型验证 11 种 Web 定位符 | 每种都能命中 1 个；`multi-hit.html` 的 class 定位符返回 `matched=3`（MULTIPLE） |
| E3 | V10 元素引用 | 用例步骤从内联选择器改为 `element_id` | 修前修后都 `PASSED`；删掉 WEB 定位符后 `ERROR` 且错误信息含"无定位符" |

**e2e 的 fixture 页面要点**（`fixtures/web/locators.html`）：

```html
<!-- 11 种定位方式各命中一个"语义相同"的元素，用于验证 _to_selector 的每一种翻译 -->
<button data-testid="login-submit"
        id="loginSubmit"
        class="btn btn-primary"
        role="button"
        aria-label="登录按钮"
        aria-placeholder="点击登录"
        title="提交登录"
        alt="登录">登录</button>
```

> 一个元素同时具备 11 种可定位特征 → **同一条 HTML 能验证 11 种翻译**，且验证结果可对比"哪种最稳"。这比写 11 个不同元素更能暴露翻译错误（比如 `label` 映射错成 `aria-label` 之外的东西）。

### 5.5 验收演练（人工走一遍，10 分钟）

按 §1.4 的 V1–V10 逐条操作。**特别要盯住这三处**：

1. **V3**：改坏首选定位符后**必须**仍能跑通，且 `fallback_index` 真的是 1（不是 0）。若显示 0，说明排序规则错了 —— 检查 `priority` 是否被重排归一化打乱。
2. **V6**：**连续删两次同名元素**。这是 F-M2-2 的现场检验，一撞就会看到 `Duplicate entry` 的 500。
3. **V8**：给 `uiautomator2` 配 `resource_id` **必须成功**（这是 F-M2-1 的核心价值），而配 `uiautomator` **必须被拒**。两者都错或都对，说明字典的 `engines` 维度没生效。

### 5.6 实测步骤（M2 结束前必须做的 3 件事）

| # | 事项 | 产出 |
|---|---|---|
| 1 | 用 `python -m app.cli locators audit --project 1 --platform WEB` 跑 fixture 页 | 一张真实健康度表，作为 V4 的批量证据 |
| 2 | 在真 MySQL 上跑 I3（`rewrite_path_prefix`）并手工 `SELECT path` 核对 | 子树 `path` 快照（前后对比） |
| 3 | 前端连点 20 次"验证" | 观察 `ps` 里无残留 chromium 进程（清理正确） |

---

## 6. 对后续 M 的接口冻结声明

### 6.1 冻结项（M2 验收通过后生效）

| # | 冻结内容 | 位置 | 改它的代价 |
|---|---|---|---|
| **FR18** | ★ **`locator_type` 只表达语义，不得含引擎语汇**；新增类型必须给 `engines` 集合 | §2.5 | 改则所有已配定位符要迁移；且通配机制失效 |
| **FR19** | ★ `probe_locator` 是**诊断方法、不进 `action_catalog`**；默认实现必须可用（不抛 `NotImplementedError`） | §2.8.3 | 桩适配器验证功能全崩 |
| **FR20** | ★ `element.deleted_seq` 的存在与语义（0=活，删=自身 id）；唯一键含它 | 附录 A | 软删除永久不可用（V6） |
| **FR21** | `element.path` 格式 `/id/id/`（含自身、以 `/` 结尾）；`MAX_DEPTH=8` | §2.4.1 | 整棵树数据要重算 |
| **FR22** | 排序提交协议：**全量有序 id 列表**，集合必须完全一致 | §2.4.4 / §2.7.1 | 前端两处拖拽全要改 |
| **FR23** | 错误码域 = 资源名（`ELEMENT` / `ELEMENT_LOCATOR` / `LOCATOR_VERIFY`） | §3.2 | 前端错误分支失效 |
| **FR24** | 验证器：只读、30s 总超时、5s 单条、单项目并发 1、`finally` 必清理 | §2.8.5 | 僵尸进程 + 误报 |
| **FR25** | 验证判定：`matched>1` **不落 INVALID**（只警告） | §2.8.4 | 列表页定位符全变红，功能失去信任 |
| **FR26** | `is_shared` M2 固定为 1，API 忽略该参数、UI 不展示 | §2.3.3 | 用户误用未定义语义 |
| **FR27** | `GET /locator-types` 的响应结构（含 `label` / `example` / `engines` / `rank`） | §3.3 M1 | 前端下拉与过滤逻辑返工 |

> **FR18 / FR19 / FR20 是 M2 里最不能动的三条**。它们分别保护：多端复数性的根基、桩适配器的可用性、软删除的正确性。任何一条被改，都会让 M2 的核心价值回退。

### 6.2 M2 预留项（可变，变更需通知下游）

| # | 内容 | 为什么留可变 | 变更影响 |
|---|---|---|---|
| RV10 | 乐观并发锁（`version` + `If-Match`） | 全量提交协议已让冲突可见，暂不需要 | 4 个写接口加版本参数 |
| RV11 | 元素数 > 5000 时改懒加载 / 虚拟滚动 | 一期项目量级在千级 | 树接口加 `lazy` 参数 |
| RV12 | 拾取器入口（M3 调试器内） | D14 已定推迟 | 新增接口，不改现有 |
| RV13 | 跨项目共享元素 | D16 已定推迟 | `is_shared` 语义启用 + 引用计数 |
| RV14 | `element_locator` 加 `healed_at` / `heal_source` | 二期自愈用 | 加列（FR16 允许） |
| RV15 | 验证的分布式锁（Redis） | M3 有多 worker 时 | 替换 `asyncio.Lock` |

### 6.3 交给 M3 的输入清单

| M3 需要 | M2 已提供 | 状态 |
|---|---|---|
| 元素选择器（StepEditor 里选元素） | `GET /projects/{pid}/elements` 树 + `keyword` 搜索 | ✅ |
| 步骤的 `element_id` 校验 | `ELEMENT_NOT_FOUND` + `node_type=ELEMENT` 判定 | ✅ |
| 回退链解析 | `LocatorResolver`（M1）+ 三端字典（M2） | ✅ |
| `fallback_index` 的展示依据 | M1 埋点 + M2 的验证结果 | ✅ |
| 元素覆盖度看板 | `GET /projects/{pid}/element-stats` | ✅ 数据就绪，图表待做 |
| 定位符健康度（谁最稳） | 数据源已就绪（`execution_step_result` + `probe_detail`） | 🟡 **需 M3 有执行数据后聚合** |
| 用例目录复用树组件 | `components/AppTree.vue` | ✅ |

**M3 必须补的**（相对 M2）：Redis 队列 + worker、WebSocket 推送、StepEditor（含元素选择器）、报告渲染、通知、定位符健康度聚合页。

### 6.4 变更流程

与 M1 §6.4 一致：任何对 §6.1 冻结项的修改，必须 ① 在本文末尾追加「变更记录」② 同步回写 M1/总方案对应章节 ③ 涉及历史数据则给 Alembic 迁移 ④ 在受影响文档标注依据。

**M2 期间的例外**：冻结从 **M2 验收通过之日**生效。当前未开工，可自由调整。

---

## 附录 A：DDL（M2 最终态）

> **用法**：M1 尚未开工（0 行代码），因此**直接改 M1 附录 A 的这两张表**，不产生"建完再 ALTER"的荒谬产物。已回写 M1 并在 M1 追加变更记录。
> 若 M1 已开工并生成了 `schema.sql`，用 **A.3** 的 `ALTER` 脚本。

### A.1 `element`（含 F-M2-2 修正）

```sql
-- ── 3. element —— 逻辑元素（树形；不含任何定位信息）────────
DROP TABLE IF EXISTS `element`;
CREATE TABLE `element` (
  `id`           BIGINT       NOT NULL AUTO_INCREMENT,
  `project_id`   BIGINT       NOT NULL,
  `parent_id`    BIGINT       NOT NULL DEFAULT 0 COMMENT '父节点，0=根',
  `path`         VARCHAR(512) NOT NULL DEFAULT '/' COMMENT '物化路径，含自身，如 /7/12/45/；LIKE 前缀可查子树',
  `element_name` VARCHAR(255) NOT NULL COMMENT '逻辑名，如「登录按钮」',
  `node_type`    ENUM('ELEMENT','FOLDER') NOT NULL DEFAULT 'ELEMENT' COMMENT '元素 / 目录',
  `description`  VARCHAR(512) NULL,
  `memo`         TEXT         NULL COMMENT '业务语义说明，供人与 AI 理解该元素是什么',
  `is_shared`    TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '1=项目内共享（M2 固定为 1，字段预留给二期的跨项目共享）',
  `sort`         INT          NOT NULL DEFAULT 0,
  `is_deleted`   TINYINT(1)   NOT NULL DEFAULT 0,
  -- ★ M2 新增：软删除唯一键的序号列（0=未删；删除时置为自身 id）
  `deleted_seq`  BIGINT       NOT NULL DEFAULT 0 COMMENT '软删序号：0=未删；删除时置为自身 id，使已删记录互不冲突',
  `deleted_at`   DATETIME     NULL,
  `created_by`   BIGINT       NULL,
  `updated_by`   BIGINT       NULL,
  `created_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  -- ★ M2 改：原 (project_id,parent_id,element_name,is_deleted) 在软删下必然冲突
  UNIQUE KEY `uk_element_name` (`project_id`, `parent_id`, `element_name`, `deleted_seq`),
  KEY `idx_element_project` (`project_id`, `is_deleted`),
  KEY `idx_element_path` (`project_id`, `path`),
  -- ★ M2 新增：按名字搜索
  KEY `idx_element_name` (`project_id`, `element_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='逻辑元素（树形）';
```

### A.2 `element_locator`（含 `probe_detail`）

```sql
-- ── 4. ★ element_locator —— 多端定位符映射（P2，本方案核心）──
DROP TABLE IF EXISTS `element_locator`;
CREATE TABLE `element_locator` (
  `id`            BIGINT       NOT NULL AUTO_INCREMENT,
  `element_id`    BIGINT       NOT NULL,
  -- ★ 二维定位：platform（业务端） × engine_key（技术引擎）
  `platform`      ENUM('WEB','ANDROID','IOS') NOT NULL,
  `engine_key`    VARCHAR(64)  NOT NULL DEFAULT '*' COMMENT '* 表示该平台下所有引擎通用；也可指定具体引擎',
  -- ★ 只存语义类型（FR18），引擎语汇由适配器翻译
  `locator_type`  VARCHAR(32)  NOT NULL COMMENT '语义定位类型，取值受 platform + engine 约束，见 M2 §2.5',
  `locator_value` TEXT         NOT NULL COMMENT '定位表达式（语义层写法，不含引擎前缀）',
  `priority`      INT          NOT NULL DEFAULT 100 COMMENT '组内回退顺序，小的先试；重排后归一化为 10/20/30',
  `is_primary`    TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否首选（仅展示标记，不影响执行顺序）',
  `verified_at`   DATETIME     NULL COMMENT '最后一次验证时间',
  `status`        ENUM('UNVERIFIED','VALID','INVALID') NOT NULL DEFAULT 'UNVERIFIED',
  -- ★ M2 新增：最近一次验证详情（供 UI 展示，不参与解析）
  `probe_detail`  JSON         NULL COMMENT '最近验证：{matched, verdict, sample, error, at}',
  `enabled`       TINYINT(1)   NOT NULL DEFAULT 1,
  `remark`        VARCHAR(255) NULL,
  `created_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_locator` (`element_id`, `platform`, `engine_key`, `locator_type`, `locator_value`(128)),
  KEY `idx_locator_lookup` (`element_id`, `platform`, `engine_key`, `enabled`, `priority`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='元素多端定位符映射';
```

### A.3 防御性 `ALTER`（仅当 M1 已开工时使用）

```sql
-- 若 schema.sql 已按 M1 v1.1 生成，改用以下增量（幂等，可重复执行前先检查）
ALTER TABLE `element`
  ADD COLUMN `deleted_seq` BIGINT NOT NULL DEFAULT 0
    COMMENT '软删序号：0=未删；删除时置为自身 id' AFTER `is_deleted`,
  ADD KEY `idx_element_name` (`project_id`, `element_name`);

-- 先把历史已删记录的 deleted_seq 填成 id，再换唯一键（顺序不能反）
UPDATE `element` SET `deleted_seq` = `id` WHERE `is_deleted` = 1;

ALTER TABLE `element`
  DROP INDEX `uk_element_name`,
  ADD UNIQUE KEY `uk_element_name` (`project_id`, `parent_id`, `element_name`, `deleted_seq`),
  MODIFY COLUMN `is_shared` TINYINT(1) NOT NULL DEFAULT 1
    COMMENT '1=项目内共享（M2 固定为 1，字段预留给二期的跨项目共享）';

ALTER TABLE `element_locator`
  ADD COLUMN `probe_detail` JSON NULL
    COMMENT '最近验证：{matched, verdict, sample, error, at}' AFTER `status`;
```

---

## 附录 B：`locator_types.py` 完整代码（可直接落地）

```python
# backend/app/domain/locator_types.py
"""定位类型字典（三端）。零业务依赖（RL-M2-2）。

分层约束（冻结项 FR18）：
  1. 只表达**语义**，绝不出现引擎语汇（'-android uiautomator' / 'resourceId=' / '-ios predicate string'）
  2. `engines` 声明哪些引擎能翻译该语义 → 写入期做引擎维度校验
  3. 不入库：引擎能力随版本演进，这是代码事实而非业务数据
"""
from __future__ import annotations

from dataclasses import dataclass, field

PLATFORM_WEB, PLATFORM_ANDROID, PLATFORM_IOS = "WEB", "ANDROID", "IOS"

WEB_ENGINES = frozenset({"playwright"})
ANDROID_ENGINES = frozenset({"appium", "uiautomator2"})
IOS_ENGINES = frozenset({"appium"})


@dataclass(frozen=True, slots=True)
class LocatorTypeSpec:
    key: str                    # 入库值，英文 snake_case
    label: str                  # 中文展示名
    example: str                # 前端 placeholder
    engines: frozenset[str]     # ★ 支持翻译该语义的引擎
    rank: int                   # 1=最稳；决定新建时默认 priority = rank*10
    note: str = ""


@dataclass(frozen=True, slots=True)
class PlatformLocators:
    platform: str
    label: str
    engines: frozenset[str]
    types: dict[str, LocatorTypeSpec] = field(default_factory=dict)

    def get(self, key: str) -> LocatorTypeSpec | None:
        return self.types.get(key)


def _t(key, label, example, engines, rank, note="") -> LocatorTypeSpec:
    return LocatorTypeSpec(key, label, example, frozenset(engines), rank, note)


# ── WEB：11 种（与 MokaTest 的 locator_type 枚举对齐，便于团队复用其心智）
WEB = PlatformLocators("WEB", "Web 端", WEB_ENGINES, {
    "testid":      _t("testid", "测试标识", "login-submit", WEB_ENGINES, 1,
                      "首选。前后端约定 data-testid，最稳、与样式解耦"),
    "role":        _t("role", "无障碍角色", 'button[name="登录"]', WEB_ENGINES, 2,
                      "语义稳定，适合表单与可访问性良好的页面"),
    "label":       _t("label", "表单标签", "用户名", WEB_ENGINES, 3, "对应 getByLabel"),
    "placeholder": _t("placeholder", "占位符", "请输入用户名", WEB_ENGINES, 4, "输入框专用"),
    "id":          _t("id", "元素 ID", "loginForm", WEB_ENGINES, 5, "稳定，但易被前端重构改掉"),
    "css":         _t("css", "CSS 选择器", "#loginForm .btn-primary", WEB_ENGINES, 6,
                      "通用兜底；别写太深的层级"),
    "text":        _t("text", "可见文本", "登录", WEB_ENGINES, 7, "文案会变；只用于稳定文案"),
    "title":       _t("title", "title 属性", "提交登录", WEB_ENGINES, 8, "少用"),
    "alt":         _t("alt", "图片 alt", "用户头像", WEB_ENGINES, 9, "图片专用"),
    "class":       _t("class", "class 名", "btn-primary", WEB_ENGINES, 10,
                      "最不稳：样式类名最易变"),
    "xpath":       _t("xpath", "XPath", '//button[@type="submit"]', WEB_ENGINES, 11,
                      "最后手段，慢且脆"),
})

# ── ANDROID：7 种（语义归一，两个引擎共用；仅 uiautomator 是 Appium 专属）
ANDROID = PlatformLocators("ANDROID", "Android 端", ANDROID_ENGINES, {
    "resource_id":      _t("resource_id", "资源 ID", "com.demo:id/login_btn", ANDROID_ENGINES, 1,
                           "首选。语义 = resource-id；Appium 译为 id=…，u2 译为 resourceId=…"),
    "accessibility_id": _t("accessibility_id", "无障碍 ID", "loginBtn", ANDROID_ENGINES, 2,
                           "对应 content-desc，跨引擎最一致"),
    "uiautomator":      _t("uiautomator", "UiSelector 表达式",
                           'new UiSelector().text("登录")', {"appium"}, 3,
                           "引擎专属表达式，不能用于 engine_key='*'"),
    "text":             _t("text", "精确文本", "登录", ANDROID_ENGINES, 4, "文案会变"),
    "text_contains":    _t("text_contains", "文本包含", "登 录", ANDROID_ENGINES, 5,
                           "精确匹配不到时的兜底"),
    "class_name":       _t("class_name", "控件类名", "android.widget.Button", ANDROID_ENGINES, 6,
                           "粒度太粗，常命中多个"),
    "xpath":            _t("xpath", "XPath", '//android.widget.Button[@text="登录"]',
                           ANDROID_ENGINES, 7, "最后手段，慢"),
})

# ── IOS：5 种（★ xpath 必须最后：iOS 上逐节点求值，可慢到秒级）
IOS = PlatformLocators("IOS", "iOS 端", IOS_ENGINES, {
    "accessibility_id": _t("accessibility_id", "无障碍 ID", "loginBtn", IOS_ENGINES, 1,
                           "首选。需开发设 accessibilityIdentifier"),
    "predicate":        _t("predicate", "谓词表达式",
                           "type == 'XCUIElementTypeButton' AND label == '登录'", IOS_ENGINES, 2,
                           "灵活，性能可接受"),
    "class_chain":      _t("class_chain", "类链",
                           '**/XCUIElementTypeButton[`label == "登录"`]', IOS_ENGINES, 3,
                           "比 XPath 快得多"),
    "name":             _t("name", "name 属性", "loginBtn", IOS_ENGINES, 4, "兼容旧写法"),
    "xpath":            _t("xpath", "XPath", '//XCUIElementTypeButton[@name="loginBtn"]',
                           IOS_ENGINES, 5, "⚠️ 必须放最后：iOS 上 XPath 性能极差"),
})

LOCATOR_TYPES: dict[str, PlatformLocators] = {
    PLATFORM_WEB: WEB,
    PLATFORM_ANDROID: ANDROID,
    PLATFORM_IOS: IOS,
}

#: 引擎语汇黑名单：出现在 locator_type 里就说明分层被破坏（U1 测试会扫这个）
FORBIDDEN_TYPE_TOKENS = (
    "uiautomator2", "-android", "-ios", "predicate string", "resourceId=", "classChain",
    "css=", "xpath=", "testid=", "~",       # 前缀/语汇不得作为类型名
)


def get_spec(platform: str, locator_type: str) -> LocatorTypeSpec | None:
    pl = LOCATOR_TYPES.get(platform)
    return pl.get(locator_type) if pl else None


def default_priority(platform: str, locator_type: str) -> int:
    """新建定位符时的默认 priority = rank * 10。"""
    spec = get_spec(platform, locator_type)
    return (spec.rank * 10) if spec else 100


def platform_engines(platform: str) -> frozenset[str]:
    pl = LOCATOR_TYPES.get(platform)
    return pl.engines if pl else frozenset()
```

---

## 附录 C：文件清单（M2 增量，共 26 个）

| 类别 | 文件 | 数量 |
|---|---|---|
| 领域 | `domain/locator_types.py`（重写）、`domain/element_errors.py` | 2 |
| 服务 | `tree_service` / `element_service` / `locator_service` / `locator_verify_service` / `reference_service` | 5 |
| 仓储 | `element_repo` / `locator_repo` | 2 |
| Schema | `schemas/element.py` / `schemas/locator.py` | 2 |
| API | `api/v1/elements.py` / `locators.py` / `meta.py` | 3 |
| 适配器 | `engines/base.py`（✏️）+ `playwright_adapter.py`（✏️） | 2 |
| 前端视图 | `ElementLibrary/index|ElementTree|ElementDetail|LocatorPanel|LocatorRow|VerifyResult` | 6 |
| 前端组件 | `AppTree` / `AppModal` / `AppToast` / `AppButton`+`AppInput`（可合并） | 4 |
| 前端 api/store | `api/elements.ts` / `api/locators.ts` / `stores/element.ts` | 3 |
| 测试 | 18 组单测 + 7 组集成 + 3 组 e2e + 3 个 fixture | — |

**工作量重心**：`locator_verify_service` + `tree_service` 占后端 60%；`ElementTree` + `LocatorPanel` 占前端 60%。

---

## 附录 D：树形操作速查（实现时对照）

| 操作 | SQL / 逻辑 | 陷阱 |
|---|---|---|
| 取子树（含自身） | `WHERE project_id=? AND path LIKE CONCAT('/7/','%')` | 必须 `LIKE 'prefix%'`（前缀），不是 `LIKE '%prefix%'` |
| 取直接子节点 | `WHERE project_id=? AND parent_id=? AND is_deleted=0 ORDER BY sort, id` | 别用 `path` 反推层级（能算但慢） |
| 移动子树 | `UPDATE ... SET path = CONCAT(:new, SUBSTRING(path, :oldlen+1)) WHERE path LIKE CONCAT(:old,'%')` | `SUBSTRING` 是 1-based；`new` 必须带尾 `/` |
| 深度 | `path.count('/') - 1` | `/7/` → 2-1=1（根下第 1 层） |
| 循环检测 | `new_parent.path.startswith(node.path)` | 用 `startswith` 而非 `in`（`in` 会误判 `/17/` 含 `/7/`） |
| 同级重排 | 全量 id → `sort = (i+1)*10` | 集合必须完全一致，否则 `ELEMENT_ORDER_INCOMPLETE` |
| 面包屑 | 按 `path` 拆 id 逐个查 | 一次 `WHERE id IN (...)` 拿全，再按 path 顺序拼 |

> **最后一个陷阱值得强调**：判断"新父是否在自己的子树里"**必须用字符串前缀比较** `startswith`。用 `in` 会让元素 `7` 认为父节点 `17`、`27`、`170` 都在自己子树里（因为 `"/17/"` 包含 `"/7/"`？—— 实际不包含，但 `"/1/7/"` 包含 `"/7/"` 是真的）。这类"id 是字符串子串"的错误极难发现，因为只有特定 id 组合才触发。**U5 的测试用例必须包含 `id=7` 与 `id=17` 的组合。**

---

## 变更记录

| # | 日期 | 条目 | 原因 | 影响面 |
|---|---|---|---|---|
| 1 | 2026-10-19 | v1.0 初稿 | M2 详细设计成稿，落实 D14–D18 | 新增本文；回写 M1 附录 A（F-M2-2）+ 总方案 §5.1（F-M2-1） |



