# UI 自动化平台 · M1 详细设计：项目骨架与引擎适配层

| 项 | 值 |
|---|---|
| **文档编号** | D2-M1 |
| **版本** | v1.2 |
| **日期** | 2026-10-14（v1.0 初稿 · v1.1 评审结论 · v1.2 M2 回写的 DDL 修正） |
| **上游依赖** | 《UI自动化平台技术方案》v1.0（决策 D1–D6） |
| **同链文档** | D0 技术选型报告 · D1 总技术方案 · D2-M1 本文 · D2-M2 · D3 工程约定 |
| **本文性质** | **施工图**。总方案回答"为什么这样设计"，本文回答"M1 具体写哪些文件、每个类长什么样、怎么验收" |
| **状态** | ✅ **评审通过**（决策 D7–D13 已确认）· 文末「变更记录」#1–#3 为 M2 阶段回写，可开工 |

---

## 0. 本文定位与阅读指引

### 0.1 文档链中的位置

```
D0  技术选型报告          ← 为什么选这条路（已完成）
D1  总技术方案            ← 整体架构 / 数据模型 / 接口形状 / 里程碑划分（已完成）
D1a 移动端对接方案        ← 二期预留，不实现（已完成）
D2-M1 本文                ← M1 的详细设计（施工图）  ★你在读
D2-M2 / M3 / M4          ← 后续里程碑的详细设计（待写）
D3  工程约定              ← 目录 / 命名 / 错误码 / 日志 / Git / 测试规范（待写）
```

**阅读方式建议**：

| 你是 | 建议读 |
|---|---|
| 要评估工作量 | §1 目标与验收、附录 C 文件清单 |
| 要动手写代码 | §2 后端设计（逐文件）、附录 A/B |
| 要评审设计 | §0.5 三处修正、§6 接口冻结声明 |
| 要验收 | §1.4 验收标准、§5.5 验收演练 |

### 0.2 与前序文档的关系（谁讲什么）

| 内容 | 总方案 D1 | 本文 D2-M1 |
|---|---|---|
| 分层架构、设计原则 P1–P6 | ✅ 完整 | 引用，不重复 |
| 数据模型 DDL | ✅ 设计说明（解释"为什么"） | ✅ **冻结版全文**（附录 A，可直接执行） |
| `EngineAdapter` 接口 | ✅ 形状 | ✅ **完整代码 + 签名冻结**（§2.5.2） |
| 能力矩阵 | ✅ 示例 | ✅ **完整 + 双向强校验**（§2.5.3） |
| 动作字典 | ✅ 节选 20 条 | ✅ **一期全集 51 条 + 完整 params_schema**（附录 B） |
| REST API 契约 | ❌ D4 排除 | ✅ **M1 范围内定义**（§3） |
| 前端页面清单 | ❌ D4 排除 | ✅ **M1 范围内定义**（§4） |
| 测试策略 | ✅ 分层表 | ✅ **逐条测试用例清单**（§5） |

### 0.3 事实来源声明（避免三处 DDL 漂移）

DDL 在本项目里会出现在三个地方，必须明确**优先级**，否则必然漂移：

| 位置 | 角色 | 优先级 |
|---|---|---|
| 本文 **附录 A** | M1 的**冻结快照**（可直接执行，M1 期间的事实来源） | 🥇 M1 阶段 |
| `backend/sql/schema.sql`（实现后生成） | **DDL 的最终唯一事实来源** | 🥇 M1 完成后 |
| 总方案 D1 §3.2 | **设计说明**（解释每个字段为什么存在） | 🥈 参考 |

**规则**：M1 开工时以附录 A 初始化；M1 结束时将附录 A 原样落成 `backend/sql/schema.sql`，此后**只改 `schema.sql`**，并回写本文与总方案。总方案 §11 RK10 已约定"里程碑完成时同步更新文档"，这里给出具体执行方式。

### 0.4 本文依据的决策

**已确认（上游）**：

| # | 决策 | 对 M1 的约束 |
|---|---|---|
| D1 | 从零自建，只借鉴架构 | 不引入 `toolium` / `mops` / `@wix-pilot/*` |
| D2 | Python + FastAPI | 见 §2.4 依赖清单 |
| D3 | 一期仅 Web + 适配器骨架 | Appium/u2 只留桩（§2.5.9）。**后续**：appium 已在 M4.1/M4.2 实现（Android），u2 仍为桩 |
| D4 | 完整方案（不含 API 契约） | M1 契约在 §3 内补齐（范围仅 M1） |
| D5 | 端只有 `WEB` / `ANDROID` / `IOS` | 全部 ENUM 不含 `WAP` |
| D6 | 动作命名英文 `snake_case`、语义自明 | 附录 B 全部动作 key 遵循此约定 |

**本文新增（用户已确认）**：

| # | 决策 | 选定 |
|---|---|---|
| **D7** | 详细设计文档切分 | 按里程碑横切：`D2-M1` ~ `D2-M4`，每份六节固定结构 |
| **D8** | 下一份文档 | 《M1 详细设计》= 本文 |
| **D9** | 代码仓库组织 | **monorepo**：`backend/` + `frontend/` + `docs/` |
| **D10** | SQL 落盘时机 | 先嵌入本文附录，M1 开工时抽成 `backend/sql/*.sql` |

**评审结论（2026-10-14，用户已确认）**：

| # | 决策 | 选定 | 影响 |
|---|---|---|---|
| **D11** | `run_python` 的处置 | ✅ **保留该动作**，默认禁用（`UIP_ALLOW_RUN_PYTHON=false`），需显式配置开启，开启时受限命名空间执行 + 强制超时强杀 | 动作字典保持 **51 条**（不删）；RV3 收敛 |
| **D12** | `switch_to_iframe` 的语义 | ✅ **保持单动作 + 栈语义**（带参进、无参弹栈），**不新增** `switch_to_main_frame` | 动作字典条目数不变；RV5 收敛 |
| **D13** | M1 前端是否引入 UI 组件库 | ✅ **不引入**。M1 用原生 CSS，组件库选型推迟到 M2（做元素库树形/拖拽时决策） | 前端依赖只剩 Vue 3 + Vite；RV2 收敛 |

> D11–D13 三项都是「待评审项已定」—— 对应的 RV2 / RV3 / RV5 已从 §6.2 预留项中移出，转为**冻结项**（见 §6.1 FR17 说明）。

### 0.5 ★ 对总技术方案的三处修正

写这份施工图时逐行核对总方案，发现三处**会让实现者写错**的不一致。此处修正，并已回写总方案。

| # | 位置 | 总方案原文 | M1 修正为 | 为什么必须改 |
|---|---|---|---|---|
| **F1** | §4.2 `EngineAdapter` 接口签名 | `def click(self, loc, ctx) -> None`（**同步**） | 全部 `async def` | 总方案 §4.5 的 `PlaywrightAdapter` 实现用的是 `async_playwright` + `await`，**接口与实现矛盾**。Playwright Python 的 async API 是官方推荐路径，且 FastAPI 本身是 async。若按同步签名落地，`await` 会无处安放。 |
| **F2** | §4.3 `assert_catalog_consistency()` | 只校验 `action_catalog.engines` → `CAPABILITY_MATRIX`（**单向**） | 改**双向**校验 | 单向只能发现"声明了但矩阵没有"。反过来"矩阵里有但字典没声明"会导致该动作**永远选不到**（前端下拉由字典驱动）→ 死代码，且无人发现。§10 测试策略其实已要求"双向一致"，代码未落实。 |
| **F3** | §4.2 接口基类 | `Protocol` + `@runtime_checkable` | 改 **`ABC`**，核心动作 `@abstractmethod` | `@runtime_checkable` 的 `isinstance` **只检查属性是否存在，不校验签名**。而 M1–M4 里最可能犯的错正是"桩适配器漏实现某个动作"或"签名漂移"。`ABC` 在**实例化时**立刻报 `TypeError`，把错误提前到进程启动阶段。测试替身 `FakeAdapter` 继承 `ABC` 同样简单，总方案"便于写测试替身"的收益并未丢失。 |

> 三处修正都是"让实现不可能写错"的方向，不改变任何设计意图。F1 已同步回写总方案 §4.2。

---

## 1. M1 目标、范围与验收

### 1.1 一句话目标

**把"显式路由 → 可插拔适配器 → 统一动作 → 真实执行"这条主脉跑通，并用 Playwright 作为唯一真实实现证明它可用。**

M1 的价值不在功能多，而在**架构定型**：如果 M1 结束时"新增一个引擎 = 加一个文件 + 注册一行"这条路被真实走通并且被测试锁住，那么 M4 的 Appium/iOS 就只是实现问题，不是架构问题。

### 1.2 交付物清单

| # | 交付物 | 落点 | 验收对应 |
|---|---|---|---|
| 1 | 后端工程脚手架（配置 / 日志 / DB / lifespan） | `backend/app/core/` | V1 |
| 2 | 全量 DDL 与初始化脚本 | `backend/sql/schema.sql` | V1 |
| 3 | 动作字典种子数据（一期全集） | `backend/sql/seed_action_catalog.sql` | V1 / V5 |
| 4 | Alembic 初始迁移 | `backend/alembic/versions/0001_initial.py` | V1 |
| 5 | **`base.py`**：值对象 + 异常体系 + `EngineAdapter` 抽象基类 | `backend/app/engines/base.py` | V2 / V7 |
| 6 | **`capabilities.py`**：能力矩阵 + 双向强校验 | `backend/app/engines/capabilities.py` | V5 |
| 7 | **`registry.py`**：注册表 + `resolve()` | `backend/app/engines/registry.py` | V3 |
| 8 | **`resolver.py`**：`LocatorResolver` 回退链 | `backend/app/engines/resolver.py` | V6 |
| 9 | **`session.py`**：`SessionManager`（**非单例**，§5.6-7） | `backend/app/engines/session.py` | V6 / V9 |
| 10 | **`actions.py`**：动作分发器 + 平台内建动作 | `backend/app/engines/actions.py` | V4 |
| 11 | **`PlaywrightAdapter`**：完整实现 | `backend/app/engines/adapters/playwright_adapter.py` | V2 / V4 / V8 |
| 12 | `AppiumAdapter` / `UiAutomator2Adapter`：**桩** | `backend/app/engines/adapters/*.py` | V3 |
| 13 | `import-linter` 红线配置 | `backend/importlinter.ini` | V7 |
| 14 | CLI 执行入口（跑硬编码 ActionPlan） | `backend/app/cli.py` | V2 / V8 |
| 15 | 测试：契约测试 + 单测 + e2e fixture | `backend/tests/` | V2–V9 |
| 16 | 前端最小骨架：2 个页面 + API 封装 | `frontend/src/` | V9 |
| 17 | 最小 API 集（见 §3） | `backend/app/api/` | V9 |

### 1.3 M1 明确不做

| 不做 | 归属 |
|---|---|
| 元素库 CRUD + 树形拖拽 UI | M2 |
| 元素定位符的多端配置界面 | M2 |
| 用例编辑器（StepEditor） | M3 |
| 执行队列（Redis）/ 调度 / WebSocket 实时看板 | M3 |
| HTML / JUnit 报告导出、截图/视频/trace 归档 | M3 |
| 钉钉 / 企业微信通知 | M3 |
| Appium / uiautomator2 真实实现 | M4（方案见《移动端对接方案》） |
| 定位自愈（AI heal） | 二期 |

> **M1 允许"丑"**：前端只有一个页面，元素/用例可以先通过 CLI 或 SQL 造数据。M1 的产出是**架构与契约**，不是可用性。

### 1.4 验收标准

总方案 §9 给了 M1 的 4 条验收，这里**细化为 9 条可执行检查**（每条都必须能一条命令跑出来）：

| # | 验收项 | 判定方式（执行级） | 通过标准 |
|---|---|---|---|
| **V1** | 骨架可启动、DDL 可建表 | `alembic upgrade head` → 启动 `uvicorn` | 11 张表全部建成；`GET /healthz` 返回 `{"status":"ok","engines":3,"db":"ok"}` |
| **V2** | Playwright 端到端跑通 | `python -m app.cli run-plan tests/fixtures/plans/login_web.json` | 退出码 0；日志出现 `navigate → input → click → get_text → screenshot` 全 `PASSED`；截图文件真实产生 |
| **V3** | 显式路由生效 | `pytest tests/unit/test_registry.py`（**未落地**，见 GAP-49） | `resolve("WEB","playwright")` 成功；`resolve("ANDROID","appium")` 成功（桩）；`resolve("WEB","appium")` 抛 `ValueError`；`resolve("WEB","nope")` 抛 `LookupError` |
| **V4** | 动作分发与参数映射正确 | `pytest tests/unit/test_actions.py`（**未落地**，见 GAP-49） | 每个引擎动作经 `dispatch` 后**恰好一次**调用到 adapter 同名方法，参数与 `params_schema` 一致 |
| **V5** | 能力矩阵一致性双向强校验 | `pytest tests/unit/test_domain_dicts.py` | 故意从字典删一条动作 → 启动自检**拒绝启动**并报出具体 action_key |
| **V6** | 回退链按优先级 + 精确优先通配 | `pytest tests/unit/test_resolver.py` | 表驱动覆盖 §2.5.5 的 6 个用例（含 `engine_key='*'` 通配） |
| **V7** | 架构红线（L3 不得 import 引擎库） | `lint-imports` | 0 个 violation；**并且**故意在 `services/` 里 `import playwright` → 必须报错 |
| **V8** | 桩适配器不静默失败 | `pytest tests/unit/test_stub_adapter.py` | `AppiumAdapter().start()` 抛 `NotImplementedError` 且消息含 "M4" |
| **V9** | 二期友好性（6+1 项，纯本地） | `pytest tests/unit/test_phase2_readiness.py`（**未落地**，见 GAP-49） | §5.6 全部通过（含 `SessionManager` 非单例） |

### 1.5 完成定义（DoD）

M1 视为完成，当且仅当：

1. V1–V9 **全部通过**，且测试可在无外网环境下执行；
2. `schema.sql` / `seed_action_catalog.sql` 已从附录 A/B 落成实体文件，且与本文一致；
3. `README.md` 含"5 分钟跑通"步骤（起 MySQL → 迁移 → 起服务 → 跑 CLI）；
4. **契约测试（§5.2）对 3 个 adapter 全绿** —— 桩也必须通过契约测试的"能力声明一致性"部分；
5. 本文 §6 冻结项已确认，无遗留"待定"。

---

## 2. 后端设计

### 2.1 工程结构（M1 实际落地）

标注：`[新]` M1 新建 · `[桩]` 仅骨架 · `[空]` 建目录占位

```
ui-test-platform/                            ← monorepo 根（D9）
├─ backend/
│  ├─ app/
│  │  ├─ main.py                    [新] FastAPI 入口 + lifespan 启动自检
│  │  ├─ cli.py                     [新] M1 执行入口（跑 ActionPlan，不依赖队列）
│  │  ├─ core/
│  │  │  ├─ config.py               [新] pydantic-settings 全量配置
│  │  │  ├─ db.py                   [新] async engine / sessionmaker
│  │  │  ├─ logging.py              [新] 结构化日志 + trace_id
│  │  │  └─ errors.py               [新] 业务异常 + 统一错误体（§3.1）
│  │  ├─ api/
│  │  │  ├─ __init__.py             [新] 路由汇总
│  │  │  ├─ health.py               [新] GET /healthz
│  │  │  ├─ engines.py              [新] GET /engines, GET /engines/{key}/capabilities
│  │  │  ├─ projects.py             [新] M1 最小 CRUD
│  │  │  ├─ elements.py             [新] 只读（写操作 M2 补 UI）
│  │  │  ├─ cases.py                [新] 只读 + 步骤读取
│  │  │  ├─ executions.py           [新] 同步执行（M3 换异步队列）
│  │  │  └─ ws.py                   [空] M3
│  │  ├─ schemas/                   [新] Pydantic DTO
│  │  │  ├─ common.py  project.py  element.py  case.py  execution.py  engine.py
│  │  ├─ models/                    [新] SQLAlchemy ORM（11 张表）
│  │  │  ├─ base.py  project.py  element.py  case.py  execution.py  report.py
│  │  ├─ services/                  [新] L3 业务层（★禁止 import 引擎库）
│  │  │  ├─ project_service.py  element_service.py  case_service.py
│  │  │  └─ execution_service.py
│  │  ├─ domain/                    [新] 纯领域常量
│  │  │  ├─ locator_types.py        [新] §5.1 定位类型字典（按 platform 约束）
│  │  │  └─ action_keys.py          [新] 动作 key 常量（与附录 B 一一对应）
│  │  ├─ engines/                   ★ L2 适配层
│  │  │  ├─ base.py                 [新] §2.5.2
│  │  │  ├─ capabilities.py         [新] §2.5.3
│  │  │  ├─ registry.py             [新] §2.5.4
│  │  │  ├─ resolver.py             [新] §2.5.5
│  │  │  ├─ session.py              [新] §2.5.6
│  │  │  ├─ actions.py              [新] §2.5.7
│  │  │  ├─ logsink.py              [新] LogSink 抽象（M1 用 MemoryLogSink）
│  │  │  └─ adapters/
│  │  │     ├─ __init__.py          [新] 唯一注册点
│  │  │     ├─ playwright_adapter.py [新] §2.5.8
│  │  │     ├─ appium_adapter.py     [桩] §2.5.9
│  │  │     └─ uiautomator2_adapter.py [桩] §2.5.9
│  │  ├─ runner/                    [空] M3（worker/scheduler/plan）
│  │  └─ ws/                        [空] M3
│  ├─ alembic/
│  │  ├─ env.py                     [新]
│  │  └─ versions/0001_initial.py   [新]
│  ├─ sql/
│  │  ├─ schema.sql                 [新] = 附录 A
│  │  └─ seed_action_catalog.sql    [新] = 附录 B
│  ├─ tests/
│  │  ├─ conftest.py                [新]
│  │  ├─ contract/test_adapter_contract.py  [新] §5.2
│  │  ├─ unit/                      [新] §5.3（9 个文件）
│  │  └─ e2e/                       [新] §5.4
│  ├─ fixtures/web/                 [新] 本地被测页面（§5.4、附录 D）
│  ├─ pyproject.toml                [新] §2.4
│  └─ importlinter.ini              [新] §2.2
├─ frontend/                        [新] §4
└─ docs/                            [新] 三份文档归档
```

### 2.2 分层与红线

```
L4 frontend  ──HTTP──►  L3 app/api + app/services
                            │  （只依赖 L2 的 base/capabilities/resolver/registry）
                            ▼
                        L2 app/engines  ★
                            │
                            ▼
                        L1 core/db + MySQL + artifacts
```

**红线（`importlinter.ini`）**：

```ini
[importlinter]
root_package = app
include_external_packages = True

[importlinter:contract:l3-must-not-import-engine-libs]
name = 应用层不得直接依赖引擎库
type = forbidden
source_modules =
    app.services
    app.api
    app.runner
forbidden_modules =
    playwright
    playwright.async_api
    appium
    uiautomator2
    app.engines.adapters

[importlinter:contract:adapters-are-only-leaf]
name = 适配器不得反向依赖上层
type = forbidden
source_modules =
    app.engines.adapters
forbidden_modules =
    app.services
    app.api
```

**为什么连 `app.engines.adapters` 也禁止 L3 import**：否则有人会写 `if project.engine_key == "playwright": from ...adapters.playwright_adapter import PlaywrightAdapter` —— 这等于把路由硬编码回业务层，`registry` 就白设计了。**只能通过 `registry.resolve()` 拿类**。

### 2.3 配置与启动

`app/core/config.py`：

```python
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="UIP_", extra="ignore")

    # 运行
    app_name: str = "ui-test-platform"
    env: str = "dev"
    debug: bool = True
    api_prefix: str = "/api/v1"

    # 数据库
    db_url: str = "mysql+aiomysql://root:root@127.0.0.1:3306/ui_test?charset=utf8mb4"

    # 产物
    artifacts_root: str = "./artifacts"
    artifact_storage: str = "LOCAL"          # LOCAL | MINIO | S3（二期）

    # 引擎
    default_timeout_ms: int = 15000
    max_threads: int = 4                     # 一期上限（总方案 §6.3）
    headless: bool = True
    browser_channel: str | None = "chrome"   # 本机 Chrome；容器内设为 None → 用 Playwright 自带 chromium

    # 启动自检
    strict_capability_check: bool = True     # V5：不一致时拒绝启动
    fail_on_unknown_action: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`app/main.py` 的 lifespan（**启动自检是 M1 的核心机制**）：

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import engine
from app.core.logging import setup_logging
from app.engines import adapters as _register_adapters   # ← 触发注册（副作用导入）
from app.engines.capabilities import assert_catalog_consistency, assert_matrix_coverage
from app.engines.registry import all_engines


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    setup_logging(s.debug)

    # 1) 注册表非空
    assert all_engines(), "没有任何引擎适配器被注册"

    # 2) 读动作字典 → 与能力矩阵双向校验（F2）
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT action_key, engines FROM action_catalog WHERE enabled = 1"
        ))).mappings().all()
    assert_catalog_consistency(rows)     # 字典 → 矩阵
    assert_matrix_coverage(rows)         # 矩阵 → 字典（★ F2 新增方向）

    yield
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="UI Test Platform", lifespan=lifespan)
    from app.api import api_router
    app.include_router(api_router, prefix=get_settings().api_prefix)
    from app.api.health import health_router
    app.include_router(health_router)      # /healthz 不带前缀
    return app


app = create_app()
```

### 2.4 依赖清单

```toml
[tool.poetry]
name = "ui-test-platform-backend"
version = "0.1.0"
python = "^3.11"

[tool.poetry.dependencies]
python = "^3.11"
fastapi = "^0.115"
uvicorn = { extras = ["standard"], version = "^0.32" }
sqlalchemy = "^2.0"
aiomysql = "^0.2"
alembic = "^1.13"
pydantic = "^2.9"
pydantic-settings = "^2.6"
playwright = "^1.51"
# ↓ M1 预留不安装，M4 启用
# appium-python-client = "^4.0"
# uiautomator2 = "^3.5"

[tool.poetry.group.dev.dependencies]
pytest = "^8.3"
pytest-asyncio = "^0.24"
aiosqlite = "^0.20"          # 单测内存库（§5.1 分层说明）
import-linter = "^2.0"
ruff = "^0.8"
mypy = "^1.13"
httpx = "^0.28"              # FastAPI TestClient

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = ["e2e: 需要真实浏览器的测试"]

[tool.ruff]
line-length = 100
target-version = "py311"
```

> **注意 `redis` / `apscheduler` / `jinja2` 不在 M1 清单里** —— 总方案 §8 列了它们，但那是 M3 的依赖。M1 装了不用会误导人（并让"L3 不得 import 引擎库"之类的红线检查失焦）。M3 时再加。

**Playwright 浏览器安装**：M1 的 README 必须写 `python -m playwright install chromium`。若配置 `browser_channel="chrome"` 则直接用本机 Chrome，无需下载浏览器 —— 这对 Windows 开发机更省事（附录 B.1 已确认开发机为 Windows）。

### 2.5 L2 引擎适配层 ★

#### 2.5.1 模块职责与依赖方向

```
        ┌────────────────────────────────────────────┐
        │  L3 services / api / runner                 │
        └───────────────┬────────────────────────────┘
                        │ 只允许依赖 ↓
   ┌────────────────────┼────────────────────┬──────────────┬────────────┐
   ▼                    ▼                    ▼              ▼            ▼
base.py          capabilities.py        registry.py    resolver.py   session.py
(契约)            (能力声明)              (注册+路由)     (定位解析)    (生命周期)
   ▲                    ▲                    ▲              ▲            │
   │                    │                    │              │            │
   └────────────────────┴────────────────────┘              │            │
                        │ 适配器依赖契约                       │            │
                  ┌─────▼──────┐                                   │
                  │  adapters/ │◄──────────────────────────────────┘
                  │  playwright│  session 从 registry 拿类并实例化
                  │  appium(桩)│
                  └────────────┘
        actions.py ──依赖 base + capabilities──► 被 L3 runner 调用
```

**禁止的方向**：`base` / `capabilities` 不得 import `registry` / `adapters`（否则循环）。

#### 2.5.2 `base.py` —— 契约（F1 / F3 落地）

```python
"""引擎适配层的唯一契约（L2）。

L3 应用层只依赖本模块，绝不 import 具体引擎库（import-linter 强制）。
设计修正见《M1 详细设计》§0.5：
  F1 全部动作方法为 async（对齐 Playwright async API 与 FastAPI）
  F3 以 ABC 替代 Protocol（漏实现动作时在实例化阶段即报错，而非运行时）
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal, Sequence

Platform = Literal["WEB", "ANDROID", "IOS"]
LogFn = Any  # Callable[[str, dict[str, Any]], None]


# ─────────────────────────── 值对象 ───────────────────────────

@dataclass(frozen=True, slots=True)
class Locator:
    """一条定位符。

    locator_id 对应 element_locator.id —— 用于 execution_step_result.used_locator_id 埋点
    （总方案 §3.2.7「定位稳定性度量」的数据基础）。手工构造的链可为 None。
    """
    type: str
    value: str
    index: int = 0
    locator_id: int | None = None

    def describe(self) -> str:
        suffix = f"[{self.index}]" if self.index else ""
        return f"{self.type}={self.value}{suffix}"


@dataclass(frozen=True, slots=True)
class LocatorChain:
    """一个元素在某端某引擎下的回退链，按优先级有序。"""
    element_id: int
    locators: tuple[Locator, ...]

    def __bool__(self) -> bool:
        return bool(self.locators)

    def __len__(self) -> int:
        return len(self.locators)

    def __iter__(self):
        return iter(self.locators)

    def describe_all(self) -> list[str]:
        return [l.describe() for l in self.locators]

    @classmethod
    def of(cls, element_id: int, locators: Sequence[Locator]) -> "LocatorChain":
        return cls(element_id=element_id, locators=tuple(locators))


@dataclass
class ActionContext:
    """单个动作的执行上下文，由平台注入（避免 rd 式 6 个位置参数）。"""
    step_seq: int
    timeout_ms: int
    variables: dict[str, Any] = field(default_factory=dict)
    artifacts_dir: str = "."
    on_log: LogFn | None = None
    execution_id: int | None = None
    case_id: int | None = None

    #: 当前活动的端 / 引擎。一期恒为项目端与引擎；
    #: 二期 WebView 上下文栈会改写它（总方案 §4.6 + 移动端方案 §5）
    active_platform: Platform = "WEB"
    active_engine: str = "playwright"

    def log(self, event: str, payload: dict[str, Any] | None = None) -> None:
        if self.on_log is not None:
            self.on_log(event, payload or {})


# ─────────────────────────── 异常体系 ───────────────────────────

class EngineError(Exception):
    """引擎层统一异常基类。

    关键约定：error_type 会写入 execution_step_result.error_type，
    并被上层用来判定「FAILED（断言失败=产品 bug）」还是
    「ERROR（引擎异常=测试/环境问题）」（总方案 §6.2）。
    """
    error_type: ClassVar[str] = "ENGINE_ERROR"

    def __init__(self, message: str, *, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class LocatorNotFoundError(EngineError):
    """回退链全部未命中 —— 属「测试资产问题」，不计为产品 bug。"""
    error_type: ClassVar[str] = "LOCATOR_NOT_FOUND"


class ActionTimeoutError(EngineError):
    error_type: ClassVar[str] = "TIMEOUT"


class UnsupportedActionError(EngineError):
    """引擎不支持该动作（能力矩阵未声明）。执行前应已被拦截。"""
    error_type: ClassVar[str] = "UNSUPPORTED_ACTION"


class SessionCrashedError(EngineError):
    """session 崩溃 —— 唯一允许触发「重建 session 后重试」的错误类型。"""
    error_type: ClassVar[str] = "SESSION_CRASHED"


class DriverDisconnectedError(EngineError):
    error_type: ClassVar[str] = "DRIVER_DISCONNECTED"


class ScriptExecutionError(EngineError):
    """平台内建 run_python 的失败。"""
    error_type: ClassVar[str] = "SCRIPT_ERROR"


# ─────────────────────────── 适配器契约 ───────────────────────────

class EngineAdapter(ABC):
    """统一引擎适配器。新增引擎 = 实现本类 + 在 adapters/__init__.py 注册一行。

    方法签名约定（★ 冻结项，见 §6.1）：
        元素类动作： async def xxx(self, loc: LocatorChain, ctx: ActionContext, *,
                                   **与 action_catalog.params_schema 同名的关键字参数)
        非元素动作： async def xxx(self, ctx: ActionContext, *,
                                   **与 params_schema 同名的关键字参数)
    该约定让 actions.py 可以用 getattr(adapter, action_key) + **params 直接分发，
    无需 if-else 长链，也无需为每个动作写映射表。
    """

    #: 注册表 key，如 "playwright" / "appium" / "uiautomator2"
    key: ClassVar[str]
    #: 支持的业务端，取值仅 WEB / ANDROID / IOS
    platforms: ClassVar[frozenset[Platform]]
    #: 本适配器支持的动作 key 集合（必须与 CAPABILITY_MATRIX[key] 同一对象）
    capabilities: ClassVar[frozenset[str]]

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        self._options: dict[str, Any] = options or {}
        self._started = False

    # ── 生命周期 ──
    @classmethod
    @abstractmethod
    def create(cls, target_options: dict[str, Any]) -> "EngineAdapter":
        """工厂。target_options 来自 execution_target.options。"""

    @abstractmethod
    async def start(self) -> None:
        """启动 driver / browser。**必须幂等**（重复调用无副作用）。"""

    @abstractmethod
    async def stop(self) -> None:
        """释放资源。**必须可安全重复调用**（M1 二期友好性检查第 6 条）。"""

    @property
    @abstractmethod
    def session_id(self) -> str | None:
        """底层 session 标识，用于日志关联与产物归档。"""

    # ── 核心元素动作（必须实现）──
    @abstractmethod
    async def click(self, loc: LocatorChain, ctx: ActionContext, *,
                    button: str = "left") -> None: ...

    @abstractmethod
    async def input(self, loc: LocatorChain, ctx: ActionContext, *,
                    text: str, clear_first: bool = True) -> None: ...

    @abstractmethod
    async def get_text(self, loc: LocatorChain, ctx: ActionContext) -> str: ...

    @abstractmethod
    async def get_attribute(self, loc: LocatorChain, ctx: ActionContext, *,
                            name: str) -> str | None: ...

    @abstractmethod
    async def wait_element(self, loc: LocatorChain, ctx: ActionContext, *,
                           state: str = "visible") -> None: ...

    @abstractmethod
    async def check_exists(self, loc: LocatorChain, ctx: ActionContext) -> bool: ...

    @abstractmethod
    async def screenshot(self, ctx: ActionContext, *,
                         full_page: bool = False,
                         path: str | None = None) -> str: ...

    # ── 可选动作（默认不支持；支持则覆盖并同步 capabilities）──
    #    一期只需 Playwright 覆盖下面这些；桩类保持默认实现即可。
    async def hover(self, loc: LocatorChain, ctx: ActionContext) -> None:
        raise UnsupportedActionError(f"{self.key} 不支持 hover")

    async def select_option(self, loc: LocatorChain, ctx: ActionContext, *,
                            option: str | None = None, label: str | None = None,
                            value: str | None = None, index: int | None = None) -> None:
        raise UnsupportedActionError(f"{self.key} 不支持 select_option")

    async def double_click(self, loc: LocatorChain, ctx: ActionContext) -> None:
        raise UnsupportedActionError(f"{self.key} 不支持 double_click")

    async def long_press(self, loc: LocatorChain, ctx: ActionContext, *,
                         duration_ms: int = 1000) -> None:
        raise UnsupportedActionError(f"{self.key} 不支持 long_press")

    async def scroll_to_element(self, loc: LocatorChain, ctx: ActionContext) -> None:
        raise UnsupportedActionError(f"{self.key} 不支持 scroll_to_element")

    async def drag(self, loc: LocatorChain, ctx: ActionContext, *,
                   target: LocatorChain | None = None,
                   target_x: int | None = None, target_y: int | None = None) -> None:
        raise UnsupportedActionError(f"{self.key} 不支持 drag")

    async def coordinate_click(self, ctx: ActionContext, *, x: int, y: int) -> None:
        raise UnsupportedActionError(f"{self.key} 不支持 coordinate_click")

    # Web 专属
    async def navigate(self, ctx: ActionContext, *, url: str) -> None:
        raise UnsupportedActionError(f"{self.key} 不支持 navigate")

    async def go_back(self, ctx: ActionContext) -> None:
        raise UnsupportedActionError(f"{self.key} 不支持 go_back")

    async def go_forward(self, ctx: ActionContext) -> None:
        raise UnsupportedActionError(f"{self.key} 不支持 go_forward")

    async def refresh(self, ctx: ActionContext) -> None:
        raise UnsupportedActionError(f"{self.key} 不支持 refresh")

    async def get_url(self, ctx: ActionContext) -> str:
        raise UnsupportedActionError(f"{self.key} 不支持 get_url")

    async def get_title(self, ctx: ActionContext) -> str:
        raise UnsupportedActionError(f"{self.key} 不支持 get_title")

    async def switch_to_iframe(self, ctx: ActionContext, *,
                               element: LocatorChain | None = None,
                               index: int | None = None) -> None:
        raise UnsupportedActionError(f"{self.key} 不支持 switch_to_iframe")

    async def switch_to_page(self, ctx: ActionContext, *, index: int = -1) -> None:
        raise UnsupportedActionError(f"{self.key} 不支持 switch_to_page")

    async def accept_dialog(self, ctx: ActionContext, *,
                            accept: bool = True, prompt_text: str | None = None) -> None:
        raise UnsupportedActionError(f"{self.key} 不支持 accept_dialog")

    async def upload_file(self, loc: LocatorChain, ctx: ActionContext, *,
                          files: list[str]) -> None:
        raise UnsupportedActionError(f"{self.key} 不支持 upload_file")

    async def get_cookies(self, ctx: ActionContext) -> list[dict[str, Any]]:
        raise UnsupportedActionError(f"{self.key} 不支持 get_cookies")

    async def set_cookies(self, ctx: ActionContext, *, cookies: list[dict[str, Any]]) -> None:
        raise UnsupportedActionError(f"{self.key} 不支持 set_cookies")

    async def delete_cookies(self, ctx: ActionContext) -> None:
        raise UnsupportedActionError(f"{self.key} 不支持 delete_cookies")

    async def page_scroll(self, ctx: ActionContext, *,
                          x: int | None = None, y: int | None = None,
                          to: str | None = None) -> None:
        raise UnsupportedActionError(f"{self.key} 不支持 page_scroll")

    async def element_scroll(self, loc: LocatorChain, ctx: ActionContext, *,
                             direction: str = "down", distance: int = 300) -> None:
        raise UnsupportedActionError(f"{self.key} 不支持 element_scroll")

    # App 专属（一期桩默认实现即为此）
    async def start_app(self, ctx: ActionContext) -> None:
        raise UnsupportedActionError(f"{self.key} 不支持 start_app")

    async def stop_app(self, ctx: ActionContext) -> None:
        raise UnsupportedActionError(f"{self.key} 不支持 stop_app")

    async def go_home(self, ctx: ActionContext) -> None:
        raise UnsupportedActionError(f"{self.key} 不支持 go_home")

    async def get_contexts(self, ctx: ActionContext) -> list[str]:
        raise UnsupportedActionError(f"{self.key} 不支持 get_contexts")

    async def switch_to_context(self, ctx: ActionContext, *, name: str) -> None:
        raise UnsupportedActionError(f"{self.key} 不支持 switch_to_context")
```

**关于"必须实现"与"默认不支持"的分界**（冻结项）：

| 类别 | 是否 `@abstractmethod` | 理由 |
|---|---|---|
| `start` / `stop` / `session_id` / `create` | ✅ 抽象 | 生命周期是每个引擎的必然职责，漏实现无意义 |
| `click` / `input` / `get_text` / `get_attribute` / `wait_element` / `check_exists` / `screenshot` | ✅ 抽象 | 任何 UI 引擎都必须有这 7 个 —— 它们是"最小完整闭环"（V2 验收用的正好是这条链） |
| 其余全部 | ❌ 有默认 `raise UnsupportedActionError` | 能力不对称是常态（P3）。默认实现 + `capabilities` 声明 = **双保险**：声明少了会被 `supports()` 拦，声明多了会在此抛错 |

> 桩适配器（§2.5.9）因此要显式实现那 7+4 个抽象成员，其余动作自动继承"不支持"的默认行为 —— 这正是我们要的：**桩不是空类，而是"能力已声明、实现待补"的完整契约形状**。

#### 2.5.3 `capabilities.py` —— 能力矩阵 + 双向强校验（F2 落地）

```python
"""能力矩阵：唯一事实来源（Single Source of Truth）。

★ 冻结项：CAPABILITY_MATRIX 的 value 对象必须与 EngineAdapter.capabilities
   是同一个 frozenset 对象（适配器里写 capabilities = CAPABILITY_MATRIX[key]），
   避免两处手写导致漂移。
"""
from __future__ import annotations

from typing import Any, Iterable

#: 一期动作全集 = 三个引擎动作集的并集 + 平台内建动作（见附录 B）
CAPABILITY_MATRIX: dict[str, frozenset[str]] = {
    "playwright": frozenset({
        # 元素
        "click", "input", "get_text", "get_attribute", "wait_element",
        "check_exists", "hover", "select_option", "double_click",
        "scroll_to_element", "drag", "screenshot", "coordinate_click",
        "upload_file", "element_scroll",
        # Web 专属
        "navigate", "go_back", "go_forward", "refresh",
        "switch_to_iframe", "switch_to_page", "get_url", "get_title",
        "get_cookies", "set_cookies", "delete_cookies", "accept_dialog",
        "page_scroll",
    }),
    "appium": frozenset({
        # 元素
        "click", "input", "get_text", "get_attribute", "wait_element",
        "check_exists", "hover", "select_option", "double_click",
        "long_press", "scroll_to_element", "drag", "screenshot",
        "coordinate_click", "page_swipe", "multi_finger_swipe",
        # App 生命周期
        "start_app", "stop_app", "restart_app", "background_foreground",
        "go_back", "go_home",
        # 上下文（WebView）
        "get_contexts", "switch_to_context",
    }),
    "uiautomator2": frozenset({
        "click", "input", "get_text", "get_attribute", "wait_element",
        "check_exists", "long_press", "scroll_to_element", "screenshot",
        "coordinate_click", "swipe_up", "swipe_down", "element_list",
        "start_app", "stop_app", "go_back", "go_home", "fix_orientation",
        # 注意：无 get_contexts / switch_to_context / hover / select_option
        #      / multi_finger_swipe / drag —— 与 rd 实测的 Android 动作集一致（附录 C.4）
    }),
}

#: 平台内建动作：不需要任何引擎实现（engines = []）
PLATFORM_BUILTIN_ACTIONS: frozenset[str] = frozenset({
    "assert_equals", "assert_contains", "assert_matches",
    "assert_visible", "assert_not_exists",
    "set_variable", "eval_expression",
    "db_query", "run_python",
})


def supports(engine_key: str, action_key: str) -> bool:
    """能力矩阵查表。执行前的第一道拦截（总方案 §4.4）。"""
    return action_key in CAPABILITY_MATRIX.get(engine_key, frozenset())


def engines_of(action_key: str) -> frozenset[str]:
    """反查：某动作被哪些引擎支持。用于 /engines/{key}/capabilities 与错误提示。"""
    return frozenset(k for k, v in CAPABILITY_MATRIX.items() if action_key in v)


# ─────────────────── 启动自检：双向校验（★ F2）───────────────────

class CapabilityInconsistency(AssertionError):
    """能力矩阵与动作字典不一致 —— 启动时抛此异常，进程拒绝启动。"""


def assert_catalog_consistency(rows: Iterable[dict[str, Any]]) -> None:
    """方向 A：动作字典 → 能力矩阵。

    字典声明某动作支持引擎 E，则 E 的矩阵里必须真的有这个动作。
    否则会出现"前端能选，引擎不支持"。
    """
    problems: list[str] = []
    for row in rows:
        key = row["action_key"]
        declared = row["engines"] or []
        for eng in declared:
            if eng not in CAPABILITY_MATRIX:
                problems.append(f"[未知引擎] {key} 声明支持 {eng}，但该引擎未在矩阵中注册")
            elif key not in CAPABILITY_MATRIX[eng]:
                problems.append(f"[漏实现] {key} 声明支持 {eng}，但 {eng} 的矩阵不含该动作")
    if problems:
        raise CapabilityInconsistency(
            "动作字典 → 能力矩阵 校验失败（共 %d 处）：\n  - %s"
            % (len(problems), "\n  - ".join(problems))
        )


def assert_matrix_coverage(rows: Iterable[dict[str, Any]]) -> None:
    """方向 B：能力矩阵 → 动作字典（★ F2 新增）。

    矩阵里声明支持的每个引擎动作，都必须在字典里有一行且 engines 含该引擎。
    否则该动作在 UI 上永远选不到 → 死代码，且无人发现。
    """
    declared: dict[str, set[str]] = {}
    for row in rows:
        declared[row["action_key"]] = set(row["engines"] or [])

    problems: list[str] = []
    for eng, actions in CAPABILITY_MATRIX.items():
        for action in sorted(actions):
            if action not in declared:
                problems.append(f"[孤儿动作] {eng}.{action} 在矩阵中，但字典里没有这一行")
            elif eng not in declared[action]:
                problems.append(
                    f"[声明缺失] {eng}.{action} 在矩阵中，但字典该行的 engines={sorted(declared[action])} 不含 {eng}"
                )
    for action in sorted(PLATFORM_BUILTIN_ACTIONS):
        if action not in declared:
            problems.append(f"[孤儿内建动作] {action} 在 PLATFORM_BUILTIN_ACTIONS 中，但字典里没有这一行")
    if problems:
        raise CapabilityInconsistency(
            "能力矩阵 → 动作字典 校验失败（共 %d 处）：\n  - %s"
            % (len(problems), "\n  - ".join(problems))
        )
```

**为什么两个方向都要**（这就是 F2 的价值）：

| 方向 | 漏了会怎样 | 谁能发现 |
|---|---|---|
| A 字典→矩阵 | 前端配了一个动作，跑到一半抛 `AttributeError` | 只有运行到该步骤的人 |
| B 矩阵→字典 | 适配器实现了动作，但 UI 永远不给选 → 死代码 | **没人会发现** |

> 附录 B 的种子数据是按 `CAPABILITY_MATRIX ∪ PLATFORM_BUILTIN_ACTIONS` **反向生成**的，因此 V1 就能通过双向校验。这是"先定矩阵、再生成字典"的顺序带来的好处：**矩阵是手写的（少），字典是推出来的（多）**。

#### 2.5.4 `registry.py` —— 注册表与路由

```python
"""引擎注册表。新增引擎只需在 adapters/__init__.py 里 import 后 register()。"""
from __future__ import annotations

from typing import Type

from app.engines.base import EngineAdapter, Platform

_REGISTRY: dict[str, Type[EngineAdapter]] = {}


def register(adapter_cls: Type[EngineAdapter]) -> Type[EngineAdapter]:
    """注册适配器。用作装饰器或显式调用均可。"""
    key = adapter_cls.key
    if not key:
        raise ValueError(f"{adapter_cls.__name__}.key 不能为空")
    if not adapter_cls.platforms:
        raise ValueError(f"{adapter_cls.__name__}.platforms 不能为空")
    existing = _REGISTRY.get(key)
    if existing is not None and existing is not adapter_cls:
        raise ValueError(f"引擎 key 重复注册：{key}（已有 {existing.__name__}）")
    _REGISTRY[key] = adapter_cls
    return adapter_cls


def get_adapter_class(engine_key: str) -> Type[EngineAdapter]:
    try:
        return _REGISTRY[engine_key]
    except KeyError:
        raise LookupError(
            f"未注册的引擎：{engine_key}。已注册：{sorted(_REGISTRY)}"
        ) from None


def all_engines() -> dict[str, Type[EngineAdapter]]:
    return dict(_REGISTRY)


def clear_registry() -> None:
    """仅供测试使用（注册表是模块级全局状态）。"""
    _REGISTRY.clear()


def resolve(platform: Platform | str, engine_key: str) -> Type[EngineAdapter]:
    """路由入口：显式校验 platform 与 engine_key 是否匹配（P1 落地）。"""
    cls = get_adapter_class(engine_key)
    if platform not in cls.platforms:
        raise ValueError(
            f"项目端 {platform} 与引擎 {engine_key} 不匹配"
            f"（该引擎支持：{sorted(cls.platforms)}）"
        )
    return cls
```

`adapters/__init__.py`（**唯一注册点**）：

```python
"""引擎适配器的唯一注册点。

禁止在其他任何地方调用 register() —— 否则"新增引擎 = 加一个文件 + 注册一行"
会退化成"到处找在哪注册"。本模块由 app/main.py 的 lifespan 导入触发。
"""
from app.engines.adapters.playwright_adapter import PlaywrightAdapter
from app.engines.adapters.appium_adapter import AppiumAdapter
from app.engines.adapters.uiautomator2_adapter import UiAutomator2Adapter
from app.engines.registry import register

register(PlaywrightAdapter)
register(AppiumAdapter)          # 一期为桩（§2.5.9）
register(UiAutomator2Adapter)    # 一期为桩（§2.5.9）

__all__ = ["PlaywrightAdapter", "AppiumAdapter", "UiAutomator2Adapter"]
```

#### 2.5.5 `resolver.py` —— 定位解析与回退链

```python
"""LocatorResolver：把 (element_id, platform, engine_key) 解析成有序的回退链。

排序规则（冻结项）：
  1) engine_key 精确匹配 优先于 '*' 通配
  2) 同组内按 priority 升序（小者先试）
  3) 完全并列时按 element_locator.id 升序（保证结果稳定可复现）
"""
from __future__ import annotations

from dataclasses import dataclass

from app.engines.base import Locator, LocatorChain, LocatorNotFoundError, Platform


@dataclass(frozen=True, slots=True)
class LocatorRow:
    """element_locator 的一行（用于单测注入的轻量结构）。"""
    id: int
    element_id: int
    platform: str
    engine_key: str
    locator_type: str
    locator_value: str
    priority: int
    enabled: bool = True


class LocatorResolver:
    """数据获取通过注入的 repo 完成 —— 便于单测用内存数据（§5.1）。"""

    def __init__(self, repo) -> None:          # repo: LocatorRepository Protocol
        self._repo = repo

    def resolve(self, element_id: int, platform: Platform | str,
                engine_key: str) -> LocatorChain:
        rows = self._repo.find_locators(element_id, platform, engine_key)
        return self._build(element_id, rows, engine_key)

    def resolve_optional(self, element_id: int | None, platform: Platform | str,
                         engine_key: str) -> LocatorChain | None:
        """requires_element=0 的步骤传 None，直接返回 None。"""
        if element_id is None:
            return None
        chain = self.resolve(element_id, platform, engine_key)
        if not chain:
            raise LocatorNotFoundError(
                f"元素 {element_id} 在 platform={platform}, engine={engine_key} 下无任何定位符；"
                f"该元素已配置的端：{self._repo.list_platforms(element_id)}",
                detail={"element_id": element_id, "platform": platform, "engine_key": engine_key},
            )
        return chain

    @staticmethod
    def _build(element_id: int, rows: list[LocatorRow], engine_key: str) -> LocatorChain:
        enabled = [r for r in rows if r.enabled]
        # 精确匹配(0) 先于 通配(1)；再按 priority；再按 id 稳定
        enabled.sort(key=lambda r: (0 if r.engine_key == engine_key else 1, r.priority, r.id))
        return LocatorChain.of(
            element_id,
            [Locator(type=r.locator_type, value=r.locator_value, locator_id=r.id)
             for r in enabled],
        )
```

**排序行为表（就是 V6 的表驱动用例）**：

| # | 输入（element 101, platform=ANDROID, engine=appium） | 期望顺序 |
|---|---|---|
| 1 | appium/priority=100, `*`/priority=10 | appium(100) 在前，`*`(10) 在后 → **精确优先于通配，即使 priority 更大** |
| 2 | appium/10, appium/100, appium/50 | 10 → 50 → 100 |
| 3 | `*`/10, `*`/20 | 10 → 20 |
| 4 | 全部 enabled=0 | 空链 → `resolve_optional` 抛 `LOCATOR_NOT_FOUND` |
| 5 | platform=IOS 全无记录 | 空链 → 抛错，且消息含"已配置的端：['ANDROID','WEB']" |
| 6 | appium/10 与 `*`/10 同 priority | appium 优先；同组并列按 id 升序（结果稳定） |

> **精确优先于通配是刻意的**：通配行是"跨端兜底"，精确行是"为这个引擎实测过的定位符"。哪怕兜底行 priority 更小（更"想先试"），也应让专用定位符先上 —— priority 只在**同一 engine_key 分组内**比较，不跨组。

**LocatorRepository 的 M1 实现**（`app/services/element_service.py` 内）：

```python
class SqlLocatorRepository:
    """M1 直连 element_locator 表；M2 元素库上线后仍是同一接口。"""

    def __init__(self, session):            # AsyncSession
        self._s = session

    async def find_locators(self, element_id: int, platform: str,
                            engine_key: str) -> list[LocatorRow]:
        stmt = (
            select(ElementLocator)
            .where(
                ElementLocator.element_id == element_id,
                ElementLocator.platform == platform,
                ElementLocator.engine_key.in_((engine_key, "*")),
                ElementLocator.enabled.is_(True),
            )
        )
        rows = (await self._s.scalars(stmt)).all()
        return [LocatorRow(**r.as_locator_row()) for r in rows]

    async def list_platforms(self, element_id: int) -> list[str]:
        stmt = select(ElementLocator.platform).where(
            ElementLocator.element_id == element_id).distinct()
        return sorted((await self._s.scalars(stmt)).all())
```

#### 2.5.6 `session.py` —— 生命周期（★ 非单例约束）

```python
"""SessionManager：管理适配器实例的生命周期。

★★ 架构约束（冻结项，见总方案 §4.6 与《移动端对接方案》§6-7）：
    SessionManager 必须是「可实例化的普通对象」，绝不是单例、不注册为全局依赖。
    原因：二期 WebView 场景下，一次 execution 内要同时持有
          「主 Appium 实例 + 次 Playwright 实例」（上下文栈）。
          若做成单例，二期必然架构级返工。
    M1 用一条测试锁住这条约束（V9 / §5.6-7）。
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from app.engines.base import EngineAdapter, EngineError, Platform
from app.engines.registry import resolve


class SessionManager:
    """一个 SessionManager 实例 = 一次 execution 的适配器管家。

    - 可以同时持有多个 adapter（键 = engine_key），为二期 WebView 预留
    - 每个 adapter 只启动一次（幂等）
    - stop 时按启动的逆序关闭，任一失败不阻断其余
    """

    def __init__(self, *, on_log=None) -> None:
        self._adapters: dict[str, EngineAdapter] = {}
        self._lock = asyncio.Lock()
        self._on_log = on_log

    # ── 主路径：按项目路由取用（一期唯一入口）──
    async def adapter_for(self, platform: Platform | str, engine_key: str,
                          target_options: dict[str, Any] | None = None) -> EngineAdapter:
        async with self._lock:
            inst = self._adapters.get(engine_key)
            if inst is None:
                cls = resolve(platform, engine_key)      # ← 显式路由（P1）
                inst = cls.create(target_options or {})
                await inst.start()
                self._adapters[engine_key] = inst
            return inst

    # ── 二期预留：主动塞入一个已启动的实例（WebView 接棒时用）──
    async def attach(self, adapter: EngineAdapter) -> None:
        async with self._lock:
            if adapter.key in self._adapters:
                raise ValueError(f"engine {adapter.key} 已存在于本 session")
            self._adapters[adapter.key] = adapter

    def get(self, engine_key: str) -> EngineAdapter | None:
        return self._adapters.get(engine_key)

    @property
    def active_engines(self) -> list[str]:
        return sorted(self._adapters)

    async def stop_all(self) -> None:
        """逆序关闭；把 stop 的异常降级为日志，确保其余实例仍被释放。"""
        async with self._lock:
            keys = list(self._adapters)[::-1]
        for k in keys:
            inst = self._adapters.pop(k, None)
            if inst is None:
                continue
            try:
                await inst.stop()
            except Exception as e:                    # noqa: BLE001
                if self._on_log:
                    self._on_log("session.stop_failed",
                                 {"engine": k, "error": str(e)})

    @asynccontextmanager
    async def use(self, platform: Platform | str, engine_key: str,
                  target_options: dict[str, Any] | None = None):
        """with 语法：异常路径也保证释放（总方案 §4.6 兜底要求）。"""
        adapter = await self.adapter_for(platform, engine_key, target_options)
        try:
            yield adapter
        except EngineError:
            raise
        finally:
            await self.stop_all()
```

> **M1 里 SessionManager 仍然"看起来像单例"** —— 一次 execution 只用一个 adapter，所以它只有一个元素。但类本身按多实例设计：`__init__` 无副作用、无类变量缓存、不注册到 FastAPI `app.state` 之外的地方。这就是"免二期返工"的全部成本：**现在多写 20 行，二期省一次重构**。

#### 2.5.7 `actions.py` —— 动作分发器

```python
"""动作分发器：把 action_key + params 变成一次适配器调用，或一次平台内建动作。

设计要点（对应总方案 §4.4 的 ACTION_DISPATCH）：
  1) 引擎动作**不写映射表**，用 getattr(adapter, action_key) 直接取同名方法。
     这依赖一条冻结约定：adapter 的方法名 == action_key，参数名 == params_schema 属性名。
  2) 平台内建动作（断言 / 变量 / 脚本 / SQL）不经过适配器 ——
     防止断言逻辑漂移到引擎层（总方案 §3.2.5 说明 2）。
  3) 分发前先做能力校验，让不支持的动作用 UNSUPPORTED_ACTION 提前失败。
"""
from __future__ import annotations

import re
from typing import Any, Awaitable, Callable

from app.engines.base import (ActionContext, EngineAdapter, LocatorChain,
                              UnsupportedActionError)
from app.engines.capabilities import PLATFORM_BUILTIN_ACTIONS, supports

# ─────────────────── 参数渲染（${var} 变量替换）───────────────────

_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_.]*)\}")


def render(value: Any, variables: dict[str, Any]) -> Any:
    """递归替换字符串里的 ${var}。未定义的变量原样保留（便于排查）。"""
    if isinstance(value, str):
        def sub(m: re.Match) -> str:
            path = m.group(1)
            cur: Any = variables
            for part in path.split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    return m.group(0)      # 保留原样，不静默变空串
            return str(cur)
        return _VAR_RE.sub(sub, value)
    if isinstance(value, dict):
        return {k: render(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v, variables) for v in value]
    return value


# ─────────────────── 平台内建动作 ───────────────────
# 9 个内建动作（assert_* / set_variable / eval_expression / db_query / run_python）
# 的实现要点见 §2.7 的表格。handler 两种签名：
#   plain   类： async def handler(ctx: ActionContext, params: dict) -> Any
#   element 类： async def handler(ctx: ActionContext, chain: LocatorChain, params: dict) -> Any
# 内建动作**不经过适配器** —— 防止断言逻辑漂移到引擎层。
```

**`ActionSpec` 与 `dispatch`**：

```python
@dataclass(frozen=True, slots=True)
class ActionSpec:
    action_key: str
    kind: Literal["element", "plain"]      # element → 需注入 LocatorChain
    needs_engine: bool                     # False = 平台内建
    handler: Callable[..., Any] | None = None   # 仅内建动作有

    @property
    def is_builtin(self) -> bool:
        return not self.needs_engine


#: 平台内建动作表（引擎动作不在此登记，直接 getattr 转发）
BUILTIN_SPECS: dict[str, ActionSpec] = {
    "assert_equals":    ActionSpec("assert_equals",    "plain", False, _builtin_assert_equals),
    "assert_contains":  ActionSpec("assert_contains",  "plain", False, _builtin_assert_contains),
    "assert_matches":   ActionSpec("assert_matches",   "plain", False, _builtin_assert_matches),
    "assert_visible":   ActionSpec("assert_visible",   "element", False, _builtin_assert_visible),
    "assert_not_exists": ActionSpec("assert_not_exists","element", False, _builtin_assert_not_exists),
    "set_variable":     ActionSpec("set_variable",     "plain", False, _builtin_set_variable),
    "eval_expression":  ActionSpec("eval_expression",  "plain", False, _builtin_eval_expression),
    "db_query":         ActionSpec("db_query",         "plain", False, _builtin_db_query),
    "run_python":       ActionSpec("run_python",       "plain", False, _builtin_run_python),
}


async def dispatch(action_key: str, adapter: EngineAdapter | None,
                   chain: LocatorChain | None, params: dict[str, Any],
                   ctx: ActionContext) -> Any:
    """统一入口。返回动作结果（可能有 output_var 语义的值）。"""
    params = render(params, ctx.variables)

    # 1) 平台内建
    spec = BUILTIN_SPECS.get(action_key)
    if spec is not None:
        if spec.kind == "element" and chain is not None:
            return await spec.handler(ctx, chain, params)
        return await spec.handler(ctx, params)

    # 2) 引擎动作：先能力校验（提前失败，不跑到一半才炸）
    if adapter is None:
        raise UnsupportedActionError(f"动作 {action_key} 需要引擎，但未提供适配器")
    if not supports(adapter.key, action_key):
        raise UnsupportedActionError(
            f"引擎 {adapter.key} 不支持动作 {action_key}",
            detail={"engine": adapter.key, "action_key": action_key},
        )

    fn = getattr(adapter, action_key, None)
    if fn is None or not callable(fn):
        # 能力矩阵声明了但适配器没实现 —— ABC 应已阻止，这里是最后一道
        raise UnsupportedActionError(
            f"适配器 {adapter.key} 声明支持 {action_key} 但未实现同名方法"
        )

    ctx.log("action.invoke", {"action_key": action_key,
                              "element_id": chain.element_id if chain else None,
                              "params": params})
    if _needs_element(action_key):
        if chain is None:
            raise UnsupportedActionError(f"动作 {action_key} 需要元素，但步骤未提供 element_id")
        return await fn(chain, ctx, **params)
    return await fn(ctx, **params)


#: 需要元素的引擎动作（与附录 B 的 requires_element 一致）
_ELEMENT_ACTIONS = frozenset({
    "click", "input", "get_text", "get_attribute", "wait_element", "check_exists",
    "hover", "select_option", "double_click", "long_press", "scroll_to_element",
    "drag", "upload_file", "element_scroll", "swipe_up", "swipe_down",
    "multi_finger_swipe", "assert_visible", "assert_not_exists",
})


def _needs_element(action_key: str) -> bool:
    return action_key in _ELEMENT_ACTIONS
```

**为什么这套设计值得（对比 rd）**：

| 维度 | rd-uitest-platform | 本设计 |
|---|---|---|
| 加一个动作 | 改动作字典表 + 改 `*_method.py` + 可能改路由模块 | 加方法 + 加矩阵一行 + 加字典一行（字典由矩阵生成） |
| 参数传递 | 每个方法自己解 `element_type/element/text` 三件套 | `**params` 按名映射，schema 已校验 |
| 不支持的动作 | 运行到才 `AttributeError` | `supports()` 前置拦截 → `UNSUPPORTED_ACTION` |
| 断言逻辑位置 | 混在用例执行里 | 平台内建，`needs_engine=False` |

#### 2.5.8 `adapters/playwright_adapter.py` —— 一期唯一真实实现

**动作映射表（全部 28 个动作，`_to_selector` 之外的实现要点）**：

| action_key | Playwright 调用 | 要点 |
|---|---|---|
| `click` | `el.click(timeout=...)` | `button` 参数透传 |
| `input` | `el.fill(text)` | `clear_first=True` 时先 `el.clear()`；否则 `el.type(text)` |
| `get_text` | `el.inner_text()` | 空元素返回 `""` 不抛错 |
| `get_attribute` | `el.get_attribute(name)` | 返回 `None` 合法 |
| `wait_element` | `el.wait_for(state=state)` | `state ∈ visible/attached/hidden/detached`，默认 `visible` |
| `check_exists` | `page.locator(sel).count() > 0` | **不抛错**（它是判断动作，不是等待） |
| `hover` | `el.hover()` | |
| `select_option` | `el.select_option(...)` | `value/label/index` 三选一 |
| `double_click` | `el.dblclick()` | |
| `scroll_to_element` | `el.scroll_into_view_if_needed()` | |
| `drag` | `el.drag_to(target)` | 需 target 元素或坐标 |
| `screenshot` | `page.screenshot(path=..., full_page=...)` | 返回绝对路径 |
| `coordinate_click` | `page.mouse.click(x, y)` | |
| `upload_file` | `el.set_input_files(files)` | |
| `element_scroll` | `el.evaluate("e => e.scrollTop += d")` | `direction` + `distance` |
| `navigate` | `page.goto(url, wait_until="domcontentloaded")` | 用 `domcontentloaded` 而非 `load`：更快且更少超时 |
| `go_back` / `go_forward` | `page.go_back()` / `go_forward()` | |
| `refresh` | `page.reload()` | |
| `switch_to_iframe` | `page.frame_locator(sel)` → 存 `self._iframe_stack` | **M1 用栈**，`switch_to_iframe(index=None)` 弹栈 |
| `switch_to_page` | `page = context.pages[index]` | `index=-1` 取最后一个（新标签页） |
| `get_url` / `get_title` | `page.url` / `page.title()` | |
| `get_cookies` / `set_cookies` / `delete_cookies` | `context.cookies()` / `add_cookies()` / `clear_cookies()` | |
| `accept_dialog` | `page.on("dialog", handler)` → 注册一次性处理器 | **M1 采用"预注册"模式**：`start()` 时挂全局 handler，`accept_dialog` 只设置策略（见下） |
| `page_scroll` | `page.mouse.wheel(x, y)` 或 `el.scroll_into_view` | `to="bottom"` 特例 |

**三个 M1 特有的实现决策**（都要写清，否则实现者会各自发明）：

**① 定位符翻译 `_to_selector`（11 种 Web 类型）**

```python
@staticmethod
def _to_selector(loc: Locator) -> str:
    t, v = loc.type, loc.value
    if t == "css":         return v
    if t == "xpath":       return f"xpath={v}"
    if t == "testid":      return f"[data-testid='{v}']"
    if t == "text":        return f"text={v}"
    if t == "role":        return v                       # 形如 "button[name=Submit]"
    if t == "placeholder": return f"[placeholder='{v}']"
    if t == "label":       return f"label:has-text('{v}')"
    if t == "title":       return f"[title='{v}']"
    if t == "alt":         return f"[alt='{v}']"
    if t == "id":          return f"#{v}"
    if t == "class":       return f".{v}"
    raise UnsupportedActionError(f"Playwright 不支持的定位类型：{t}")
```

> **待实测（总方案 §12.4 已列为待确认项）**：`role` 的正则匹配语义、`label` 对 `for=` 关联的覆盖范围、`testid` 在 Playwright 里其实有原生 `data-testid` 配置（`testIdAttribute`）—— M1 期间用 fixtures 页面（附录 D）实测，若与预期不符则修正本函数并回写文档。**M1 的 fixture 页面里必须有一个专门覆盖这 11 种定位类型的页面。**

**② `accept_dialog` 的处理方式**

Playwright 的 dialog 是事件驱动的 —— 弹窗出现后若不处理，页面会**永久阻塞**。所以不能"出现后再调 `accept_dialog` 动作"，必须预注册：

```python
class PlaywrightAdapter(EngineAdapter):
    def __init__(self, options=None):
        super().__init__(options)
        self._dialog_policy: dict[str, Any] = {"accept": True, "prompt_text": None}
        self._last_dialog: dict[str, Any] | None = None

    async def start(self) -> None:
        ...
        self._page.on("dialog", self._on_dialog)       # ← 预注册，永不阻塞

    async def _on_dialog(self, dialog) -> None:
        self._last_dialog = {"type": dialog.type, "message": dialog.message}
        p = self._dialog_policy
        if p["accept"]:
            await dialog.accept(p.get("prompt_text") or "")
        else:
            await dialog.dismiss()

    async def accept_dialog(self, ctx, *, accept=True, prompt_text=None) -> None:
        """设置**后续**弹窗的处理策略（不处理已经弹出的）。"""
        self._dialog_policy = {"accept": accept, "prompt_text": prompt_text}
```

> 这个语义差异**必须写进动作字典的 `params_schema` 描述**，否则用户会以为"点一下就能关掉当前弹窗"。M1 起就在 `remark` 里注明。

**③ iframe 用栈而非单层**

```python
async def switch_to_iframe(self, ctx, *, element=None, index=None) -> None:
    """element 给定时进入该 iframe；element/index 均为 None 时**退出到上一层**。"""
    if element is None and index is None:
        if self._iframe_stack:
            self._iframe_stack.pop()
        self._rebind_page()
        return
    ...
```

理由：总方案没规定"如何退出 iframe"。若用单层（`switch_to_iframe` / `switch_to_main` 两个动作）就要新增动作；用栈则只需"带参进、无参出"，**不增加动作字典条目**。二期 WebView 的上下文栈（移动端方案 §5）是同一思路 —— **一处设计，两处复用**。

> ✅ **已确认（决策 D12，2026-10-14 评审）**：采用**单动作 + 栈语义**，**不新增** `switch_to_main_frame`。理由已在上文：动作字典保持精简，且与二期 WebView 上下文栈共用同一套心智模型。此条已从 §6.2 预留项转出，列为冻结项 FR17。

**PlaywrightAdapter 完整骨架**：

```python
"""Playwright 适配器 —— 一期唯一真实实现的引擎（platform=WEB）。"""
from __future__ import annotations

import os
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from app.engines.adapters import register
from app.engines.base import (ActionContext, EngineAdapter, Locator, LocatorChain,
                              LocatorNotFoundError, ActionTimeoutError,
                              UnsupportedActionError)
from app.engines.capabilities import CAPABILITY_MATRIX


@register
class PlaywrightAdapter(EngineAdapter):
    key = "playwright"
    platforms = frozenset({"WEB"})
    capabilities = CAPABILITY_MATRIX["playwright"]      # ★ 同一对象，不复制

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        super().__init__(options)
        self._pw = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._iframe_stack: list[str] = []
        self._dialog_policy: dict[str, Any] = {"accept": True, "prompt_text": None}
        self._session_id: str | None = None

    @classmethod
    def create(cls, target_options: dict[str, Any]) -> "PlaywrightAdapter":
        return cls(target_options)

    @property
    def session_id(self) -> str | None:
        return self._session_id

    # ── 生命周期（幂等）──
    async def start(self) -> None:
        if self._started:
            return                                    # 幂等（§5.6-6）
        o = self._options
        self._pw = await async_playwright().start()
        launcher = getattr(self._pw, o.get("browser", "chromium"))
        launch_kwargs: dict[str, Any] = {"headless": o.get("headless", True)}
        if o.get("channel"):
            launch_kwargs["channel"] = o["channel"]     # "chrome" → 本机 Chrome
        self._browser = await launcher.launch(**launch_kwargs)

        ctx_args: dict[str, Any] = {"viewport": o.get("viewport", {"width": 1440, "height": 900})}
        for k in ("is_mobile", "has_touch", "user_agent", "locale", "timezone_id"):
            if o.get(k) is not None:
                ctx_args[k] = o[k]
        if o.get("storage_state"):
            ctx_args["storage_state"] = o["storage_state"]
        if o.get("record_video") and o.get("artifacts_dir"):
            ctx_args["record_video_dir"] = o["artifacts_dir"]
            ctx_args["record_video_size"] = ctx_args["viewport"]

        self._context = await self._browser.new_context(**ctx_args)
        self._page = await self._context.new_page()
        self._page.set_default_timeout(o.get("default_timeout_ms", 15000))
        self._page.on("dialog", self._on_dialog)
        self._session_id = f"pw-{id(self._context):x}"
        self._started = True

    async def stop(self) -> None:
        for closer in (self._context, self._browser):
            if closer is not None:
                try:
                    await closer.close()
                except Exception:                     # noqa: BLE001
                    pass
        if self._pw is not None:
            try:
                await self._pw.stop()
            except Exception:                         # noqa: BLE001
                pass
        self._pw = self._browser = self._context = self._page = None
        self._started = False

    # ── 定位（回退链 + 埋点）──
    async def _find(self, chain: LocatorChain, ctx: ActionContext,
                    state: str = "visible"):
        """按优先级依次尝试；命中即记 locator.hit（含 fallback_index）。"""
        if self._page is None:
            raise UnsupportedActionError("Playwright 适配器未启动")
        timeout = ctx.timeout_ms
        last: Exception | None = None
        for idx, loc in enumerate(chain.locators):
            try:
                el = self._page.locator(self._to_selector(loc)).first
                await el.wait_for(state=state, timeout=timeout)
                ctx.log("locator.hit", {
                    "element_id": chain.element_id,
                    "locator_id": loc.locator_id,
                    "locator": loc.describe(),
                    "fallback_index": idx,
                })
                return el, idx, loc
            except Exception as e:                    # noqa: BLE001
                last = e
                ctx.log("locator.miss", {
                    "element_id": chain.element_id,
                    "locator_id": loc.locator_id,
                    "locator": loc.describe(),
                    "fallback_index": idx,
                })
        raise LocatorNotFoundError(
            f"元素 {chain.element_id} 的 {len(chain)} 条定位符全部未命中："
            f"{chain.describe_all()}",
            detail={"element_id": chain.element_id,
                    "tried": chain.describe_all()},
        ) from last
```

> `_find` 返回 `(element, fallback_index, locator)` —— **第三个返回值就是 `used_locator_id` 的来源**。执行器把它写进 `execution_step_result.used_locator_id` / `fallback_index`（总方案 §3.2.7 埋点）。**M1 的 CLI 必须把这两个字段打印出来**，否则 V2 无法验证埋点通路。

**清单：M1 必须实现的 28 个动作**

```
元素类(15): click input get_text get_attribute wait_element check_exists
            hover select_option double_click scroll_to_element drag
            screenshot coordinate_click upload_file element_scroll
Web 类(13): navigate go_back go_forward refresh switch_to_iframe switch_to_page
            get_url get_title get_cookies set_cookies delete_cookies
            accept_dialog page_scroll
```

#### 2.5.9 桩适配器（appium / uiautomator2）

桩的写法要**统一模板**，目的是让 M4 只需要"把 `raise` 换成实现"，不动其他任何文件：

```python
"""Appium 适配器 —— M1 为桩（决策 D3）。

本类的存在意义有两条，都不是"占位"：
  1) 证明"新增引擎 = 加一个文件 + adapters/__init__.py 注册一行"这条路径可用（V3）
  2) 让能力矩阵与动作字典的双向校验（V5）在**三引擎**规模下被验证，
     而不是等到 M4 才发现矩阵结构不支持多引擎
所有动作方法继承 base.EngineAdapter 的默认实现（raise UnsupportedActionError），
M1 只需显式实现生命周期与 7 个核心动作 —— 它们在 M1 一律抛 NotImplementedError，
以便与"能力不支持"（UnsupportedActionError）在语义上严格区分。
"""
from __future__ import annotations

from typing import Any

from app.engines.adapters import register
from app.engines.base import (ActionContext, EngineAdapter, LocatorChain)
from app.engines.capabilities import CAPABILITY_MATRIX

_M4_HINT = "Appium 适配器计划于 M4 实现，详见《UI自动化平台·移动端对接方案》§3"


@register
class AppiumAdapter(EngineAdapter):
    key = "appium"
    platforms = frozenset({"ANDROID", "IOS"})
    capabilities = CAPABILITY_MATRIX["appium"]

    @classmethod
    def create(cls, target_options: dict[str, Any]) -> "AppiumAdapter":
        return cls(target_options)

    async def start(self) -> None:
        raise NotImplementedError(_M4_HINT)

    async def stop(self) -> None:
        raise NotImplementedError(_M4_HINT)

    @property
    def session_id(self) -> str | None:
        raise NotImplementedError(_M4_HINT)

    async def click(self, loc: LocatorChain, ctx: ActionContext, *, button: str = "left") -> None:
        raise NotImplementedError(_M4_HINT)

    async def input(self, loc: LocatorChain, ctx: ActionContext, *,
                    text: str, clear_first: bool = True) -> None:
        raise NotImplementedError(_M4_HINT)

    async def get_text(self, loc: LocatorChain, ctx: ActionContext) -> str:
        raise NotImplementedError(_M4_HINT)

    async def get_attribute(self, loc: LocatorChain, ctx: ActionContext, *, name: str) -> str | None:
        raise NotImplementedError(_M4_HINT)

    async def wait_element(self, loc: LocatorChain, ctx: ActionContext, *,
                           state: str = "visible") -> None:
        raise NotImplementedError(_M4_HINT)

    async def check_exists(self, loc: LocatorChain, ctx: ActionContext) -> bool:
        raise NotImplementedError(_M4_HINT)

    async def screenshot(self, ctx: ActionContext, *, full_page: bool = False,
                         path: str | None = None) -> str:
        raise NotImplementedError(_M4_HINT)
```

`uiautomator2_adapter.py` 同模板，仅 `key = "uiautomator2"`、`platforms = frozenset({"ANDROID"})`、`capabilities = CAPABILITY_MATRIX["uiautomator2"]`。

> **`NotImplementedError` vs `UnsupportedActionError` 的语义分界（冻结项）**：
> - `NotImplementedError` = **这个引擎该支持，但一期还没写** → 属"里程碑未到"，V8 以此判定桩是否正确
> - `UnsupportedActionError` = **这个引擎本来就不支持** → 属"能力边界"，是永久事实
>
> 混用会让 M4 的工作量失去可追踪性（分不清"待实现"与"不该实现"）。

### 2.6 数据层

| 项 | M1 做法 |
|---|---|
| ORM | SQLAlchemy 2.0 声明式（`Mapped[...]` + `mapped_column`），11 张表对应 §2.1 的 `models/` |
| 迁移 | Alembic；`0001_initial.py` 由 `schema.sql` 手工转写（**不用 autogenerate** —— 一次写对，避免 autogenerate 漏 ENUM/COMMENT/索引） |
| 初始化 | `alembic upgrade head`（V1） |
| 种子 | `seed_action_catalog.sql`（附录 B）→ M1 提供 `scripts/seed.py` 执行 |
| 单测 DB | **aiosqlite 内存库**（见下） |

**为什么单测用 SQLite 而 DDL 用 MySQL 方言**（这是个必须说清的工程决策）：

| 层 | 数据库 | 覆盖什么 | 不覆盖什么 |
|---|---|---|---|
| 单测（`tests/unit`） | SQLite in-memory（aiosqlite）+ `Base.metadata.create_all` | `LocatorResolver` 排序、`registry`、`capabilities` 校验、`actions` 分发、状态机 | MySQL 特有行为（ENUM 约束、中文排序规则） |
| 冒烟（`tests/e2e` / CI） | 真实 MySQL 8 | `schema.sql` 可执行性、启动自检、CLI 端到端 | — |

> 风险提示：SQLAlchemy 会把 `ENUM` 在 SQLite 上落成 `VARCHAR + CHECK`，行为**接近但不完全等同**。因此凡"依赖 ENUM 拒绝非法值"的测试，一律放在 MySQL 冒烟层，不放单测 —— 避免出现"单测绿、线上红"。

### 2.7 平台内建动作（M1 实现 9 个）

| action_key | 语义 | 参数 | 实现要点 |
|---|---|---|---|
| `assert_equals` | 值相等 | `actual`, `expected` | 字符串化后比较，避免 `1` vs `"1"` 误判 |
| `assert_contains` | 包含子串 | `actual`, `expected` | |
| `assert_matches` | 正则匹配 | `actual`, `pattern` | |
| `assert_visible` | 元素可见 | `element_id` | 走 `adapter.check_exists` + `wait_element` 组合，**不新增引擎动作** |
| `assert_not_exists` | 元素不存在 | `element_id` | |
| `set_variable` | 设变量 | `name`, `value` | 写入 `ctx.variables` |
| `eval_expression` | 变量表达式 | `expression`, `output_var` | 安全求值：**只支持白名单运算**，禁止 `eval` |
| `db_query` | 查库 | `sql`, `params`, `output_var` | 只读连接 + 结果行数上限 |
| `run_python` | 执行脚本 | `code` | ✅ **已确认保留（决策 D11）**：**M1 默认禁用**（`UIP_ALLOW_RUN_PYTHON=false`），需显式配置开启，开启时在受限命名空间执行并强制超时强杀。沙箱强化见 §6.3「M1 可以先不做」 |

> **`run_python` 的处置已于 2026-10-14 评审确认（决策 D11）**：rd 与 MokaTest 都有类似能力，它带来任意代码执行风险，因此**保留动作但默认关闭**，需显式配置 `UIP_ALLOW_RUN_PYTHON=true` 才可用，且执行时施加超时强杀。动作字典因此保持 **51 条不变**（不删该条目）。沙箱强度属预留项，不在 M1 范围。

### 2.8 日志、错误码与可观测性

**日志（`core/logging.py`）**：结构化 JSON（`json.dumps` 单行），字段固定：

```jsonc
{ "ts": "2026-10-14T20:41:03.221+08:00", "level": "INFO",
  "logger": "app.engines.adapters.playwright",
  "trace_id": "e8c1...",           // 每个 execution 一个
  "execution_id": 12, "case_id": 3, "step_seq": 4,
  "event": "locator.hit",
  "payload": { "element_id": 101, "fallback_index": 0 } }
```

**`on_log` 与日志的关系**：`ctx.on_log` 是**执行事件流**（面向 UI/结果表），不是应用日志。两者字段部分重叠，但**职责不同、不合并**：

| | `ctx.on_log` 事件 | 应用日志 |
|---|---|---|
| 消费者 | 执行器 → 结果表 / 未来 WebSocket | 运维 / 排查 |
| 内容 | 动作与定位符的**语义事件** | 全量技术细节 |
| M1 实现 | `MemoryLogSink`（收集到列表，由 CLI 打印） | 结构化输出到 stdout |

`app/engines/logsink.py`：

```python
class LogSink(Protocol):
    def __call__(self, event: str, payload: dict[str, Any]) -> None: ...


class MemoryLogSink:
    """M1：收集事件供 CLI / 测试断言。M3 换成 WsLogSink（WebSocket 推送）。"""
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, event: str, payload: dict[str, Any]) -> None:
        self.events.append((event, payload))

    def of(self, event: str) -> list[dict[str, Any]]:
        return [p for e, p in self.events if e == event]
```

> `LogSink` 是 Callable Protocol —— 意味着 `ctx.on_log` 可以**同时**被 CLI 的 `MemoryLogSink` 和 M3 的 `WsLogSink` 满足，而不改任何引擎代码。这是 M1 为 M3 埋的第二个"零返工"点。

### 2.9 CLI —— M1 的执行入口

`app/cli.py`（M1 的 V2 验收就靠它）：

```bash
# 跑一个硬编码 ActionPlan（不依赖 DB，验证适配层）
python -m app.cli run-plan tests/fixtures/plans/login_web.json --target tests/fixtures/targets/chrome_desktop.json

# 跑 DB 里的真实用例（验证 路由 + 定位解析 + 结果落库）
python -m app.cli run-case --project-code demo-web --case-id 3

# 打印注册表与能力矩阵（验证 V3 / V5）
python -m app.cli engines
python -m app.cli check-capabilities
```

`login_web.json`（硬编码 Plan，**这就是 V2 的输入**）：

```jsonc
{
  "variables": { "username": "demo", "password": "demo123" },
  "steps": [
    { "seq": 1, "action_key": "navigate",      "params": { "url": "http://127.0.0.1:8899/login.html" } },
    { "seq": 2, "action_key": "input",  "element_locators": [ { "type": "testid", "value": "username" } ],
      "params": { "text": "${username}" } },
    { "seq": 3, "action_key": "input",  "element_locators": [ { "type": "testid", "value": "password" } ],
      "params": { "text": "${password}" } },
    { "seq": 4, "action_key": "click",  "element_locators": [ { "type": "testid", "value": "submit" } ] },
    { "seq": 5, "action_key": "wait_element", "element_locators": [ { "type": "testid", "value": "welcome" } ],
      "timeout_ms": 10000 },
    { "seq": 6, "action_key": "get_text", "element_locators": [ { "type": "testid", "value": "welcome" } ],
      "output_var": "welcome" },
    { "seq": 7, "action_key": "assert_contains", "params": { "actual": "${welcome}", "expected": "欢迎" } },
    { "seq": 8, "action_key": "screenshot", "params": { "full_page": true } }
  ]
}
```

CLI 输出（**验收要能看到 `fallback_index`**）：

```
[execution] id=-  plan=login_web  engine=playwright platform=WEB
  seq=1 navigate                 PASSED   312ms
  seq=2 input                    PASSED    88ms   locator=testid=username fallback_index=0
  seq=3 input                    PASSED    76ms   locator=testid=password fallback_index=0
  seq=4 click                    PASSED   143ms   locator=testid=submit   fallback_index=0
  seq=5 wait_element             PASSED   201ms   locator=testid=welcome  fallback_index=0
  seq=6 get_text                 PASSED    12ms   locator=testid=welcome  fallback_index=0  -> welcome="欢迎回来，demo"
  seq=7 assert_contains          PASSED     1ms
  seq=8 screenshot               PASSED   268ms   -> artifacts/…/step_8.png
[result] 8/8 PASSED  duration=1.10s  artifacts=1
```

> **`fallback_index` 在 CLI 里可见**，是 M1 埋点通路的最小验证。M2 的验收（"故意写错首选定位符，验证回退到第 2 条"）会直接复用这条输出。

---

## 3. 接口契约（M1 范围）

总方案 D4 排除了 REST API 契约，但 M1 的 V9 验收需要"前端能调到后端"。所以本节**只定义 M1 涉及的最小集**，M2/M3 的完整契约在 D3《工程约定》或各里程碑文档里扩充。**本节的所有约定（路径、错误体、分页）一旦定下即为全项目规范**，后续里程碑只增不减。

### 3.1 通用规范

| 项 | 规范 |
|---|---|
| 基础路径 | `/api/v1`（`/healthz` 除外，不带前缀） |
| 资源命名 | 复数名词、kebab-case：`/projects`、`/execution-targets`、`/element-locators` |
| 请求体 | JSON，`snake_case` 字段名（与 DB 列一致，减少心智转换） |
| 成功响应 | **直接返回资源或 `{"items": [...], "total": n}`**，不套 `{code,data}` 外壳；HTTP 状态码即语义 |
| 失败响应 | 统一错误体（见下）+ 合适的 4xx/5xx |
| 分页 | `?page=1&size=20`（**不用 offset/limit**，便于前端换 cursor 时少改）；响应含 `total` |
| 排序 | `?sort=-created_at`（`-` 前缀=降序） |
| 过滤 | 平铺 query 参数：`?project_id=3&platform=WEB` |
| 认证 | **M1 不做鉴权**（内网自用），但所有写操作记录 `created_by`/`updated_by` 字段留位（V9 不校验，M3 接入登录时不改表） |
| 幂等 | 写操作不特殊处理；执行触发用 `POST /executions`，重复提交产生新批次（不做幂等键） |
| trace | 每个请求生成 `trace_id`，响应头 `X-Trace-Id` 返回，日志可按它串联 |

**统一错误体**：

```jsonc
{
  "error": {
    "code": "ENGINE_UNSUPPORTED_ACTION",   // 机器可读，见 §3.2
    "message": "引擎 playwright 不支持动作 get_contexts",
    "detail": { "engine": "playwright", "action_key": "get_contexts" },
    "trace_id": "e8c1f0a2..."
  }
}
```

`app/core/errors.py`：

```python
class AppError(Exception):
    """业务异常基类。code 见 §3.2 错误码表。"""
    code: ClassVar[str] = "COMMON_ERROR"
    http_status: ClassVar[int] = 400

    def __init__(self, message: str, *, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class NotFoundError(AppError):
    code, http_status = "COMMON_NOT_FOUND", 404


class ValidationError(AppError):
    code, http_status = "COMMON_VALIDATION_ERROR", 422


class ConflictError(AppError):
    code, http_status = "COMMON_CONFLICT", 409


def install_exception_handlers(app: FastAPI) -> None:
    """把 AppError / EngineError / 兜底异常统一成 §3.1 的错误体。"""
    @app.exception_handler(AppError)
    async def _app_error(request, exc: AppError):
        return JSONResponse(status_code=exc.http_status,
                            content={"error": {"code": exc.code, "message": exc.message,
                                               "detail": exc.detail,
                                               "trace_id": request.state.trace_id}})
    # EngineError → ENGINE_* 前缀；未捕获异常 → COMMON_INTERNAL_ERROR（500）
```

> **`EngineError` 也要被统一处理**：M1 的 `POST /executions` 是同步执行，引擎异常会冒泡到 HTTP 层。透出时用 `ENGINE_*` 错误码，与 §3.2 对齐。

### 3.2 错误码表（M1 全量）

命名规范：`<域>_<语义>`，全大写下划线。**域**：`COMMON` / `PROJECT` / `ELEMENT` / `CASE` / `EXECUTION` / `ENGINE`。

| HTTP | code | 触发场景 |
|---|---|---|
| 400 | `COMMON_ERROR` | 未细分的业务错误（兜底，尽量不用） |
| 404 | `COMMON_NOT_FOUND` | 资源不存在 |
| 409 | `COMMON_CONFLICT` | 唯一键冲突（如 `project.code` 重复） |
| 422 | `COMMON_VALIDATION_ERROR` | 入参校验失败（Pydantic 校验也归这里） |
| 500 | `COMMON_INTERNAL_ERROR` | 未捕获异常 |
| 404 | `PROJECT_NOT_FOUND` | |
| 409 | `PROJECT_CODE_DUPLICATED` | |
| 422 | `PROJECT_PLATFORM_ENGINE_MISMATCH` | `platform` 与 `engine_key` 不匹配（★ P1 的写入期拦截） |
| 404 | `ELEMENT_NOT_FOUND` | |
| 422 | `ELEMENT_LOCATOR_TYPE_INVALID` | 定位类型不在该 platform 的字典里（§5.1） |
| 422 | `ELEMENT_LOCATOR_DUPLICATED` | `uk_locator` 冲突 |
| 404 | `CASE_NOT_FOUND` | |
| 422 | `CASE_STEP_ACTION_UNKNOWN` | `action_key` 不在 `action_catalog` |
| 422 | `CASE_STEP_PARAMS_INVALID` | `params` 不满足 `params_schema` |
| 422 | `CASE_STEP_ELEMENT_REQUIRED` | `requires_element=1` 但 `element_id` 为空 |
| 404 | `EXECUTION_NOT_FOUND` | |
| 409 | `EXECUTION_ALREADY_RUNNING` | 同项目已有 RUNNING 批次（M1 暂不实现，M3 用） |
| 200 | `EXECUTION_PARTIAL_FAILED` | ⚠️ **不是错误**：执行完成但有失败用例，仍返回 200 + 结果体，仅在 `execution.status` 上体现 |
| 400 | `ENGINE_UNKNOWN` | `engine_key` 未注册 |
| 400 | `ENGINE_PLATFORM_MISMATCH` | `resolve()` 抛出 |
| 422 | `ENGINE_UNSUPPORTED_ACTION` | 动作不在能力矩阵 |
| 502 | `ENGINE_LOCATOR_NOT_FOUND` | 回退链全未命中 |
| 504 | `ENGINE_TIMEOUT` | 动作超时 |
| 502 | `ENGINE_SESSION_CRASHED` | session 崩溃 |

> **`EXECUTION_PARTIAL_FAILED` 特判**：这是本设计里唯一"看起来像错误、实际不是"的条目。它的存在是为了防止实现者把"用例失败"当成 5xx（那会让 CI/监控误判为平台故障）。**用例失败是产品问题，不是平台故障** —— 与 §6.2 的 `FAILED` vs `ERROR` 分离是同一个原则。

### 3.3 端点清单（M1）

| 方法 | 路径 | 用途 | M1 状态 |
|---|---|---|---|
| GET | `/healthz` | 健康检查（返回引擎数、DB 状态、动作字典条数） | ✅ |
| GET | `/api/v1/engines` | 列出注册的引擎 + platforms + 动作数 | ✅ V3 |
| GET | `/api/v1/engines/{key}/capabilities` | 某引擎的动作清单（前端下拉数据源） | ✅ V5 |
| GET | `/api/v1/actions` | 动作字典全量（前端 StepEditor 数据源，M3 主要用） | ✅ V5 |
| GET/POST | `/api/v1/projects` | 列表 / 新建 | ✅ |
| GET/PATCH/DELETE | `/api/v1/projects/{id}` | 详情 / 改 / 软删 | ✅ |
| GET | `/api/v1/execution-targets` | 执行目标列表 | ✅ |
| GET | `/api/v1/projects/{id}/elements` | 元素树（M1 只读） | ✅ 只读 |
| POST | `/api/v1/projects/{id}/elements` | 新建元素 | 🟡 M1 提供 API，UI 在 M2 |
| GET | `/api/v1/elements/{id}/locators` | 某元素的多端定位符 | ✅ 只读 |
| POST | `/api/v1/elements/{id}/locators` | 新增定位符 | 🟡 API 就绪，UI 在 M2 |
| GET | `/api/v1/projects/{id}/cases` | 用例列表 | ✅ 只读 |
| GET | `/api/v1/cases/{id}` | 用例 + 步骤详情 | ✅ 只读 |
| POST | `/api/v1/executions` | **同步**触发一次执行（M3 改异步 + 返回 202） | ✅ V9 |
| GET | `/api/v1/executions/{id}` | 批次详情（含步骤结果） | ✅ |
| GET | `/api/v1/executions?project_id=` | 批次列表 | ✅ |

**`POST /api/v1/executions` 的请求/响应**（M1 的关键接口）：

```jsonc
// 请求
{ "project_id": 1, "case_ids": [3, 4], "target_id": null }   // target_id 为空 → 用 project.target_id

// 响应 200
{
  "id": 12, "project_id": 1, "platform": "WEB", "engine_key": "playwright",
  "status": "PASSED", "total": 2, "passed": 2, "failed": 0, "errored": 0, "skipped": 0,
  "duration_ms": 4210,
  "cases": [
    { "case_id": 3, "title": "登录成功", "status": "PASSED",
      "steps": [
        { "seq": 1, "action_key": "navigate", "status": "PASSED", "duration_ms": 312,
          "used_locator_id": null, "fallback_index": null },
        { "seq": 2, "action_key": "input", "status": "PASSED", "duration_ms": 88,
          "used_locator_id": 771, "fallback_index": 0, "active_platform": "WEB",
          "active_engine": "playwright" }
      ] }
  ]
}
```

> `active_platform` / `active_engine` 在 M1 恒为 `("WEB","playwright")` —— 这是二期 WebView 预留列（总方案 §3.2.7），**M1 就要写入**，这样二期上线时历史数据格式一致。

**写入期拦截（M1 必须实现的三处，全在 service 层）**：

| 检查 | 位置 | 错误码 |
|---|---|---|
| `project.platform` 与 `engine_key` 匹配（走 `registry.resolve` 的校验逻辑） | `project_service.create/update` | `PROJECT_PLATFORM_ENGINE_MISMATCH` |
| `entity.locator_type` 在该 platform 的字典内 | `element_service.upsert_locator` | `ELEMENT_LOCATOR_TYPE_INVALID` |
| `step.action_key` 存在 + `params` 符合 schema + `entity` 与 `requires_element` 一致 | `case_service.upsert_step` | `CASE_STEP_*` |

> 这三条是 P1/P2/P3 在**写入期**的落地。总方案把它们放在"路由前校验"与"写入时校验"两处 —— M1 明确为：**写入期拦截为主，执行期校验为兜底**。因为写入期能给出更精确的报错，而执行期还要防"数据被 SQL 直接改坏"。

### 3.4 WebSocket（M1 只留接口）

M1 不实现推送（`api/ws.py` 为空文件），但**事件名与载荷在 M1 冻结**（总方案 §6.4 已定），M3 只实现传输不改协议：

```
/ws/executions/{execution_id}     event: execution.started | case.started | step.finished
                                        | case.finished | execution.finished
/ws/projects/{project_id}         项目级汇总
```

M1 的 `MemoryLogSink` 事件名与上表**子集对齐**（`locator.hit` / `locator.miss` / `action.invoke` 是 M1 新增的内部事件，不对外推送）。这样 M3 写推送时，只是把 `LogSink` 换成 `WsLogSink` + 加事件映射，**引擎层零改动**。

---

## 4. 前端设计（M1 最小骨架）

### 4.1 范围与不做

**M1 前端只做一件事：让人能看见"引擎注册了什么、执行跑出了什么"。**

| 做 | 不做（M2/M3） |
|---|---|
| 工程骨架：Vue 3 + Vite + TS + 路由 + Pinia + axios 封装 | 元素库树形拖拽 |
| `Engines` 页：引擎列表 + 能力矩阵表格 | 用例编辑器 / StepEditor |
| `Executions` 页：触发执行 + 步骤结果表（含 `fallback_index` 列） | 实时看板（WebSocket） |
| 统一请求层（错误体解包、`trace_id` 提示） | 报告导出 / 图表 |
| — | 登录鉴权 |

> **`fallback_index` 必须在 M1 的结果表里作为一列显示** —— 它是 P2 设计价值的唯一可视化证据，也是 M2 验收（"故意写错定位符"）的操作入口。

### 4.2 工程结构与依赖

```
frontend/
├─ src/
│  ├─ main.ts
│  ├─ App.vue
│  ├─ router/index.ts            # /engines  /executions  /executions/:id
│  ├─ api/
│  │  ├─ http.ts                 # axios 实例：baseURL=/api/v1、错误体解包、trace_id
│  │  ├─ engines.ts  projects.ts  executions.ts
│  ├─ stores/
│  │  ├─ engine.ts  execution.ts
│  ├─ views/
│  │  ├─ EnginesView.vue         # 引擎 + 能力矩阵
│  │  ├─ ExecutionListView.vue   # 触发 + 批次列表
│  │  └─ ExecutionDetailView.vue # ★ 步骤结果表（fallback_index / used_locator_id 列）
│  ├─ components/
│  │  ├─ CapabilityMatrix.vue    # 引擎×动作 的矩阵热力表
│  │  └─ StepResultTable.vue
│  └─ types/api.d.ts             # 与后端 DTO 对齐（M1 手工维护，M3 起可考虑 openapi 生成）
├─ vite.config.ts                # server.proxy: /api → http://127.0.0.1:8000
├─ tsconfig.json
└─ package.json
```

**依赖（M1 只装这些）**：

```jsonc
{
  "dependencies": {
    "vue": "^3.5", "vue-router": "^4.4", "pinia": "^2.2",
    "axios": "^1.7"
  },
  "devDependencies": {
    "vite": "^6.0", "@vitejs/plugin-vue": "^5.2",
    "typescript": "^5.6", "vue-tsc": "^2.1"
  }
}
```

> **UI 组件库 M1 不装**。总方案 §10 写"参考 Arco Design / Element Plus"但未定 —— 组件库选型应该在 M2 做元素库树形/拖拽时决策（那时才知道需要哪些组件）。M1 用原生 CSS，**避免为了一个表格引入 200KB 依赖**。
> ✅ **已确认为决策 D13（2026-10-14 评审）**：M1 前端依赖只有 Vue 3 + Vite + Vue Router，**零 UI 组件库**。组件库选型正式推迟到 M2，并由 M2 详细设计文档给出选型依据。

### 4.3 页面清单

**① `EnginesView`** —— 验证 V3 / V5

```
┌─ 引擎注册表 ─────────────────────────────────────────────┐
│ 已注册 3 个引擎                                           │
├──────────────┬───────────┬────────┬──────────────────────┤
│ engine_key   │ platforms │ 动作数  │ 实现状态              │
├──────────────┼───────────┼────────┼──────────────────────┤
│ playwright   │ WEB       │  28    │ ✅ 已实现             │
│ appium       │ ANDROID,  │  24    │ ⛔ 桩（计划 M4）      │
│              │ IOS       │        │                      │
│ uiautomator2 │ ANDROID   │  18    │ ⛔ 桩（计划 M4）      │
└──────────────┴───────────┴────────┴──────────────────────┘

┌─ 能力矩阵（引擎 × 动作）──────────────────────────────────┐
│ action_key        │ playwright │ appium │ uiautomator2 │
│ click             │     ●      │   ●    │      ●       │
│ hover             │     ●      │   ●    │      ○       │  ○ = 不支持
│ get_contexts      │     ○      │   ●    │      ○       │
│ navigate          │     ●      │   ○    │      ○       │
│ assert_equals     │  内建      │ 内建    │    内建       │  平台内建
└──────────────────────────────────────────────────────────┘
```

**② `ExecutionDetailView`** —— 验证 V2 / V9

```
┌─ 执行 #12 · demo-web · WEB/playwright · PASSED (2/2) · 4.21s ───────┐
│ 用例：登录成功 (PASSED)                                            │
├─────┬────────────────┬────────┬────────┬──────────────┬───────────┤
│ seq │ action_key     │ status │ 耗时   │ 命中定位符    │ fallback  │
├─────┼────────────────┼────────┼────────┼──────────────┼───────────┤
│  1  │ navigate       │ ✅     │ 312ms  │ —            │ —         │
│  2  │ input          │ ✅     │  88ms  │ testid=user  │ 0         │
│  3  │ input          │ ✅     │  76ms  │ testid=pass  │ 0         │
│  4  │ click          │ ✅     │ 143ms  │ testid=submit│ 0         │  ★
│  5  │ wait_element   │ ✅     │ 201ms  │ testid=welc  │ 1         │  ← 回退了 1 次
└─────┴────────────────┴────────┴────────┴──────────────┴───────────┘
```

> `fallback_index > 0` 的行**要变色高亮**（如淡黄底）。理由：这一列的语义是"首选定位符失效了" —— 它是二期自愈功能的种子信号，也是给用户的最早预警。**如果 M1 就把它可视化，M2 的验收会自然产生。**

### 4.4 与后端的对接点

| 前端动作 | 后端接口 | 备注 |
|---|---|---|
| 打开 `Engines` 页 | `GET /engines` + `GET /engines/{key}/capabilities` ×3 | M1 可并发取 |
| 触发执行 | `POST /executions` | M1 同步，前端要显示 loading（可能跑十几秒） |
| 查看结果 | `GET /executions/{id}` | |
| 错误提示 | 解包 `error.code` / `error.message` / `error.trace_id` | **必须显示 `trace_id`**，否则排查时要用户复述操作 |

`api/http.ts` 的响应拦截器（M1 唯一的"框架级"代码）：

```ts
// M1 无 UI 组件库（决策 D13）→ 用自带的极简 toast，放在 ui/toast.ts（约 20 行原生 DOM）
import { toastError } from '@/ui/toast'

http.interceptors.response.use(
  (r) => r.data,
  (e) => {
    const body = e?.response?.data?.error
    const msg = body ? `[${body.code}] ${body.message}` : e.message
    const trace = e?.response?.headers?.['x-trace-id'] ?? body?.trace_id
    toastError(trace ? `${msg}（trace: ${trace}）` : msg)
    return Promise.reject(e)
  },
)
```

> **注意**：这里**不能**写 `ElMessage?.error(...)`。M1 不装组件库（D13），`ElMessage` 是 Element Plus 的 API —— 写了既不报错（可选链吞掉）也不显示，会成为静默失效的假代码。统一走 `ui/toast.ts`。

### 4.5 交互验收

| # | 操作 | 期望 |
|---|---|---|
| F1 | 打开 `/engines` | 3 个引擎都显示；playwright 标"已实现"，另两个标"桩（计划 M4）" |
| F2 | 矩阵里 `navigate` 行 | 只有 playwright 列是 ●，另两个是 ○ |
| F3 | 输入 project_id + case_ids 点"执行" | loading → 显示结果；失败时提示含 `trace_id` |
| F4 | 打开执行详情 | 步骤表含 `fallback_index` 列；>0 的行高亮 |
| F5 | 直接访问 `/executions/99999` | 显示"批次不存在"（`COMMON_NOT_FOUND`），不是白屏 |

---

## 5. 测试与验收

### 5.1 测试分层

| 层 | 目录 | 数据库 | 是否需要浏览器 | 标记 |
|---|---|---|---|---|
| 契约测试 | `tests/contract/` | 无 | 无 | — |
| 单元测试 | `tests/unit/` | SQLite in-memory | 无 | — |
| 端到端 | `tests/e2e/` | 真实 MySQL | ✅ 本机 Chrome/Chromium | `@pytest.mark.e2e` |
| API 测试 | `tests/unit/test_api_*.py` | SQLite + httpx ASGI | 无 | — |

默认 `pytest` **只跑 unit + contract**（快、无外部依赖）；e2e 用 `pytest -m e2e` 显式触发。CI 里 e2e 单独一个 job（带 MySQL service + `playwright install`）。

### 5.2 契约测试（M1 的核心测试资产）

**一个测试文件，跑所有 adapter** —— 这是"可插拔"能被锁住的唯一方式：

```python
# tests/contract/test_adapter_contract.py
import pytest
from app.engines.registry import all_engines
from app.engines.base import EngineAdapter
from app.engines.capabilities import CAPABILITY_MATRIX

ADAPTER_CLASSES = list(all_engines().values())


@pytest.mark.parametrize("cls", ADAPTER_CLASSES, ids=lambda c: c.key)
def test_declares_required_classvars(cls):
    assert cls.key
    assert cls.platforms and cls.platforms <= {"WEB", "ANDROID", "IOS"}
    assert cls.capabilities is CAPABILITY_MATRIX[cls.key], "capabilities 必须是矩阵里的同一个对象"


@pytest.mark.parametrize("cls", ADAPTER_CLASSES, ids=lambda c: c.key)
def test_implements_all_abstract_members(cls):
    """ABC 会在实例化时检查；这里提前把错误定位到具体方法名。"""
    from app.engines.base import EngineAdapter as Base
    missing = getattr(cls, "__abstractmethods__", frozenset())
    assert not missing, f"{cls.key} 未实现抽象成员：{sorted(missing)}"


@pytest.mark.parametrize("cls", ADAPTER_CLASSES, ids=lambda c: c.key)
def test_capability_methods_exist(cls):
    """矩阵里声明的每个动作，适配器必须真有同名可调用成员。"""
    for action in cls.capabilities:
        assert callable(getattr(cls, action, None)), \
            f"{cls.key} 声明支持 {action}，但没有同名方法"


@pytest.mark.parametrize("cls", ADAPTER_CLASSES, ids=lambda c: c.key)
@pytest.mark.asyncio
async def test_unimplemented_distinguishable_from_unsupported(cls):
    """桩的未实现必须是 NotImplementedError，而非 UnsupportedActionError（§2.5.9 冻结项）。"""
    ...
```

### 5.3 单元测试清单（逐条）

| 文件 | 覆盖 | 关键用例 |
|---|---|---|
| `test_registry.py` | V3（**未落地**，见 GAP-49） | 成功 resolve；platform 不匹配抛 `ValueError`；未注册 key 抛 `LookupError`；重复注册抛错；`clear_registry()` 可用 |
| `test_capabilities.py` | V5 | 正常数据通过；方向 A 故意删一条 → 抛；方向 B 故意加一条矩阵 → 抛；`engines=[]` 的内建动作不参与方向 A |
| `test_resolver.py` | V6 | §2.5.5 的 6 个表驱动用例 |
| `test_actions.py` | V4（**未落地**，见 GAP-49） | 引擎动作转发（mock adapter，断言调用次数=1、参数名匹配）；内建动作不触达 adapter；`supports=False` 时抛 `UNSUPPORTED_ACTION`；`needs_element` 但 chain 为 None 时抛 |
| `test_render.py` | — | `${var}` 替换；未定义变量保留原样；嵌套 dict/list；非字符串原样返回 |
| `test_session.py` | V9-7 | **两个 SessionManager 实例互不干扰**；`adapter_for` 幂等（同一实例）；`stop_all` 逆序且在异常时仍释放其余；`active_engines` 可含 2 个引擎（模拟二期） |
| `test_builtin_actions.py` | — | 9 个内建动作各 1–2 例；`assert_equals` 的 `1` vs `"1"` 行为；`eval_expression` 拒绝白名单外表达式 |
| `test_stubs.py` | V8 | appium/u2 的 `start()` 抛 `NotImplementedError` 且消息含 "M4"；可选动作抛 `UnsupportedActionError`（语义区分） |
| `test_api_executions.py` | V9 | `POST /executions` 用 FakeAdapter 跑通；错误体结构符合 §3.1；`GET /executions/99999` → 404 + `COMMON_NOT_FOUND` |
| `test_locator_types.py` | — | `locator_types.py` 字典与附录 B 的 `platforms` 字段一致（防止两处手写） |

**`FakeAdapter`（测试替身，也是 V4 的关键）**：

```python
# tests/conftest.py
from app.engines.base import EngineAdapter, LocatorChain, ActionContext

class FakeAdapter(EngineAdapter):
    """记录所有调用；核心动作返回可预测值。用于 V4 / V9 的执行链路测试。"""
    key = "fake"
    platforms = frozenset({"WEB"})
    capabilities = frozenset({"click", "input", "get_text", "screenshot", "navigate"})

    def __init__(self, options=None):
        super().__init__(options)
        self.calls: list[tuple[str, dict]] = []
        self.started = self.stopped = 0

    @classmethod
    def create(cls, target_options): return cls(target_options)
    async def start(self): self.started += 1
    async def stop(self): self.stopped += 1
    @property
    def session_id(self): return "fake-session"

    async def click(self, loc, ctx, *, button="left"):
        self.calls.append(("click", {"locator": loc.describe_all(), "button": button}))
    async def input(self, loc, ctx, *, text, clear_first=True):
        self.calls.append(("input", {"text": text}))
    async def get_text(self, loc, ctx):
        self.calls.append(("get_text", {})); return "欢迎回来，demo"
    async def screenshot(self, ctx, *, full_page=False, path=None):
        self.calls.append(("screenshot", {"full_page": full_page})); return "/tmp/fake.png"
    async def navigate(self, ctx, *, url):
        self.calls.append(("navigate", {"url": url}))
```

> **`FakeAdapter` 让"执行链路"完全不依赖真实浏览器** —— M1 的 `ExecutionService` 单测因此可以跑得飞快。这是 `EngineAdapter` 用 ABC 而非直接调 Playwright 的最大回报。（注意：`FakeAdapter` 的 `capabilities` 是自建集合，**不参与启动自检的矩阵校验** —— 它只在测试里注册，不进 `adapters/__init__.py`。）

### 5.4 e2e fixture 页面

`backend/fixtures/web/` 下的静态页面，由 `python -m http.server 8899` 或 pytest fixture 起的本地服务提供。**不依赖外网**（总方案 §10 要求）。

| 文件 | 覆盖 | 必须包含 |
|---|---|---|
| `login.html` | V2 主链路 | `data-testid` 的 username/password/submit/welcome；纯前端 JS 校验（不写后端） |
| `locators.html` | ★ 11 种 Web 定位类型 | 同一批元素分别可用 `id`/`class`/`css`/`xpath`/`testid`/`role`/`text`/`placeholder`/`label`/`title`/`alt` 命中 —— **用于实测 `_to_selector` 与预期是否一致** |
| `iframe.html` | iframe 栈 | 两层嵌套 iframe + 每层一个 `testid` 按钮 |
| `dialog.html` | 弹窗策略 | `alert` / `confirm` / `prompt` 三个按钮 |
| `upload.html` | 上传 | `<input type="file">` |
| `tabs.html` | 多标签 | `target="_blank"` 链接 |
| `scroll.html` | 滚动 | 长页面（`page_scroll`）+ 内部滚动容器（`element_scroll`） |

### 5.5 验收演练（按 V1–V9 逐条执行）

```bash
# ── 准备 ──
cd backend
poetry install
python -m playwright install chromium          # 或配 browser_channel=chrome 跳过

# ── V1 骨架与 DDL ──
mysql -uroot -p -e "CREATE DATABASE ui_test DEFAULT CHARSET utf8mb4"
alembic upgrade head
mysql -uroot -p ui_test -e "SHOW TABLES"        # 期望 11 张 + alembic_version
python scripts/seed.py                          # 灌入附录 B 的动作字典
uvicorn app.main:app --port 8000 &
curl -s localhost:8000/healthz | jq            # {"status":"ok","engines":3,...}

# ── V5 能力矩阵一致性（故意破坏 → 必须拒绝启动）──
mysql -uroot -p ui_test -e "DELETE FROM action_catalog WHERE action_key='navigate'"
uvicorn app.main:app --port 8001                # 期望：启动失败，报 [孤儿动作] playwright.navigate
mysql -uroot -p ui_test -e "INSERT ..."         # 恢复
pytest tests/unit/test_domain_dicts.py -v

# ── V2 CLI 端到端 ──
python -m http.server 8899 --directory fixtures/web &
python -m app.cli run-plan tests/fixtures/plans/login_web.json \
    --target tests/fixtures/targets/chrome_desktop.json
# 期望：8/8 PASSED；日志含 locator.hit 且 fallback_index=0；artifacts/ 下有 png

# ── V3 / V8 路由与桩 ──
pytest tests/unit/test_adapter_contract.py tests/unit/test_stub_adapter.py -v
python -m app.cli engines
python -m app.cli check-capabilities

# ── V7 红线（正向 + 反向）──
lint-imports                                     # 期望 0 violations
# 反向验证：临时在 services/project_service.py 顶部加 import playwright → lint-imports 必须报错 → 删掉

# ── V9 二期友好性 ──
# V9（二期友好性）目前无自动化测试，见 GAP-49

# ── 全量 ──
pytest -q && pytest -m e2e -q
```

### 5.6 二期友好性检查（★ 纯本地，M1 必须全绿）

来自《移动端对接方案》第 6 节的 10 条依赖清单，**M1 阶段可验证的 6 项 + 本文新增 1 项**：

| # | 检查 | M1 判定方式 | 为什么现在必须过 |
|---|---|---|---|
| 1 | `platform` 是 project 的独立字段（不与 engine 合并） | `test_api_projects.py` 断言字段存在且可独立更新 | 二期 WebView 要按 platform 决定 `element_locator` 维度 |
| 2 | `element_locator.engine_key` 维度存在且支持 `'*'` | `test_resolver.py` 用例 1/6 | 二期 Android 双引擎语汇不同 |
| 3 | `LocatorChain`（而非单 Locator）贯穿接口 | 契约测试断言所有元素动作首参为 `LocatorChain` | 二期回退链顺序在 iOS 上不同（xpath 必须最后） |
| 4 | 能力矩阵**双引擎**能共存（不假设单引擎） | `test_capabilities.py` 用 3 引擎数据跑双向校验 | 二期矩阵要容纳 appium + u2 |
| 5 | start/stop **幂等** | `test_session.py`：连续 2 次 `adapter_for` 只 start 一次 | 二期 WebView 会重复取用同一 adapter |
| 6 | `import-linter` 红线生效（含 adapters 不可反向依赖） | `lint-imports` | 二期新增 adapter 文件不会引入循环依赖 |
| **7** | ★ **`SessionManager` 不是单例** | `test_session.py`：两个实例的 `_adapters` 互不影响；`active_engines` 可容纳 2 个 key | ★★ **二期 WebView 需同时持有 Appium + Playwright 实例，不做则架构级返工** |
| — | （8–10 已在 §2.7/§4 落地：`options` 用 JSON、StepEditor 由字典驱动、预留 `active_platform/active_engine` 列） | 见对应章节 | — |

**第 7 项的测试写法**（这是全项目最重要的一条测试）：

```python
# tests/unit/test_phase2_readiness.py
async def test_session_manager_is_not_a_singleton():
    """★ 二期 WebView 依赖此约束：一次 execution 内并存两个 adapter。"""
    from app.engines.session import SessionManager
    from app.engines.base import EngineAdapter

    a, b = SessionManager(), SessionManager()
    assert a is not b and a._adapters is not b._adapters     # 无共享状态

    class FakeA(EngineAdapter):  # 模拟 Appium
        key, platforms = "appium", frozenset({"ANDROID"})
        capabilities = frozenset()
        ...
    fake_a = FakeA()
    await a.attach(fake_a)
    # 同一 session 内允许存在第二个引擎（模拟 WebView 接棒后的双实例）
    assert a.active_engines == ["appium"]
    assert b.active_engines == []                            # 另一实例不受影响
```

---

## 6. 接口冻结声明

本节是 M1 → M2/M3 的**契约接口**。总方案 §9 说"M1 → M2 是关键路径（架构定型）"，本节就是"定型"的具体内容。

### 6.1 M1 冻结项（后续里程碑**不得修改**）

| # | 冻结内容 | 位置 | 改动的代价 |
|---|---|---|---|
| **FR1** | `EngineAdapter` 的全部方法签名（含 `async`、`LocatorChain` 首参、keyword-only 参数） | §2.5.2 | 所有 adapter 重写；桩与实现都要改 |
| **FR2** | `Locator` / `LocatorChain` / `ActionContext` 的字段与语义 | §2.5.2 | 引擎层与执行器全面波及 |
| **FR3** | `EngineError.error_type` 取值集合 | §2.5.2 | 历史结果数据的 `error_type` 含义漂移 |
| **FR4** | adapter 方法名 == `action_key`、参数名 == `params_schema` 属性名 | §2.5.2 / §2.5.7 | `dispatch` 的 `**params` 转发机制失效 |
| **FR5** | `registry` 是唯一路由入口（禁止在别处 `import adapters`） | §2.5.4 | 红线作废，可插拔性丢失 |
| **FR6** | `CAPABILITY_MATRIX` 是能力唯一事实来源，且 `capabilities` 必须是同一对象 | §2.5.3 | 双处手写必然漂移 |
| **FR7** | 双向一致性校验（`assert_catalog_consistency` + `assert_matrix_coverage`） | §2.5.3 | 死代码无人发现（F2） |
| **FR8** | `SessionManager` 非单例 | §2.5.6 | ★★ 二期架构级返工 |
| **FR9** | `LocatorChain` 排序规则（精确优先通配 → priority → id） | §2.5.5 | 已有用例定位行为改变 |
| **FR10** | 错误体 `{"error": {code, message, detail, trace_id}}` 与路径 `/api/v1` | §3.1 | 前端全部要改 |
| **FR11** | 错误码命名规范 `<域>_<语义>` | §3.2 | 前端错误处理分支失效 |
| **FR12** | `FAILED`（断言失败）与 `ERROR`（引擎异常）**语义分离** | §3.2 / 总方案 §6.2 | 统计口径与通知策略失效 |
| **FR13** | WebSocket 事件名与载荷（M1 冻结，M3 实现） | §3.4 | 前端推送协议返工 |
| **FR14** | `MemoryLogSink` 与 `LogSink` 的形状：`(event: str, payload: dict) -> None` | §2.8 | 引擎层事件调用点全改 |
| **FR15** | 桩用 `NotImplementedError`、能力边界用 `UnsupportedActionError` | §2.5.9 | 无法区分"待实现"与"不该实现" |
| **FR16** | 11 张表的表名与关键列名（可加列，不可改名/删列） | 附录 A | 迁移与历史数据爆炸 |
| **FR17** | ★ 三项评审结论：① `run_python` 保留但默认禁用（`UIP_ALLOW_RUN_PYTHON=false`）② `switch_to_iframe` 单动作 + 栈语义，不新增 `switch_to_main_frame` ③ M1 前端不引入 UI 组件库 | §0.4 D11–D13 | 动作字典条目数（51）、执行器安全策略、前端依赖树 |

> **FR16 的边界**：允许**加**列（如二期可能加 `element_locator.healed_at`），**不允许**改列名或删列。加列必须走 Alembic 迁移且更新 `schema.sql`。
>
> **FR17 的边界**：三项都是**已确认的决策**，不是"暂定"。若后续要改（例如团队后来要求禁用 `run_python`），属于**需求变更**，需同步改 §0.4 决策表 + 附录 B 动作字典 + `UIP_ALLOW_RUN_PYTHON` 配置说明三处。

### 6.2 M1 预留项（可变，但变更需通知下游）

| # | 内容 | 为什么留可变 | 变更影响 |
|---|---|---|---|
| RV1 | `_to_selector` 的 11 种类型映射细节 | 需用 `locators.html` 实测（§2.5.8 待确认项） | 只影响 Playwright 适配器内部 |
| RV4 | `page_scroll` 的参数形态（坐标 vs `to="bottom"`） | 需实测 Playwright wheel 行为 | 动作字典一行 + 适配器 |
| RV6 | 执行目标 `options` 的字段集 | 需实测 Playwright `device` 描述符覆盖范围 | 只影响 `execution_target` 数据 |
| RV7 | `POST /executions` 的同步→异步切换 | M3 引入队列 | 前端加轮询/WS |
| RV8 | `screenshot` 的默认文件名与落盘策略 | M3 接 ArtifactStore 时统一 | 适配器内部 |
| RV9 | 分页默认 `size` | 数据量未知 | 前端一参数 |

> **已收敛（不再是预留项）**：原 RV2（前端组件库）→ **D13**、RV3（`run_python` 开关）→ **D11**、RV5（`switch_to_iframe` 语义）→ **D12**，三项均已确认，转为冻结项 FR17。
> 剩余 RV1 / RV4 / RV6 是**实测类**（需跑代码才知道答案），**不阻塞 M1 开工**，按 §5.6 的实测步骤落地后回写本文。

### 6.3 交给 M2 / M3 的输入清单

**M2（元素库与多端 Locator）可以依赖的既有资产**：

| M2 需要 | M1 已提供 | 状态 |
|---|---|---|
| `element` / `element_locator` 表 | 附录 A | ✅ |
| 定位类型校验字典 | `domain/locator_types.py` | ✅ 需 M2 补 `ANDROID`/`IOS` 条目（一期只填 WEB 也行） |
| 回退链解析 | `LocatorResolver` + 6 个单测 | ✅ |
| 定位符 CRUD API | §3.3 的 `POST /elements/{id}/locators` | ⚠️ **仅 GET + POST**；PATCH / DELETE / 重排 / 验证由 M2 补（见 M2 §3.3 的 L3–L7） |
| ★ 回退验证的可观测性 | CLI/接口返回 `fallback_index` + `used_locator_id` | ✅ M2 验收第 3 条直接复用 |
| 元素树形结构的 DDL | `element.parent_id` + `path` + `sort` | ✅ |
| 共享/私有字段 | `element.is_shared` | ✅ |

**M2 必须补的**：① `ELEMENT_LOCATOR_TYPE_INVALID` 的完整字典（三端）；② 树形查询（`path` 前缀匹配）；③ 前端元素库页面；④ 定位符拖拽排序 → 写 `priority`。

**M3（编排/执行/报告）可以依赖的既有资产**：

| M3 需要 | M1 已提供 | 状态 |
|---|---|---|
| 动作字典（前端下拉 + 校验） | `action_catalog` 51 条 + `GET /actions` | ✅ |
| 参数校验 | `params_schema`（附录 B 内嵌 JSON Schema） | ✅ M3 只需在 `case_service` 里执行校验 |
| 动作分发 | `dispatch()` + `ActionSpec` | ✅ |
| 执行链路 | `ExecutionService`（M1 同步版）+ `SessionManager` | ✅ M3 改为"投队列 + worker 消费" |
| 结果落库 | `execution_step_result` 全部列（含埋点） | ✅ |
| 实时推送 | `LogSink` 抽象 + 事件名冻结 | ✅ M3 实现 `WsLogSink` |
| 断言 | 9 个平台内建动作 | ✅ |
| 报告数据 | `execution` 的 passed/failed/errored/skipped | ✅ 渲染与导出待做 |

**M3 必须补的**：① Redis 队列 + APScheduler + worker；② `WsSink` 与 WebSocket 端点；③ HTML/JUnit 报告渲染；④ ArtifactStore（LOCAL/MINIO）；⑤ StepEditor 前端；⑥ 通知（钉钉/企业微信）；⑦ Alembic 新版本（若加表）。

### 6.4 变更流程

任何对 §6.1 冻结项的修改，必须：

1. 在本文件末尾追加「变更记录」条目（日期 / 条目 / 原因 / 影响面）；
2. 同步更新总方案 D1 的对应章节（总方案 §11 RK10 的"文档与代码一致"要求）；
3. 若已影响历史数据 → 提供 Alembic 迁移，不允许"改表不改数据"；
4. 若影响其他里程碑文档 → 在受影响的文档里标注"依据 D2-M1 vX.Y 变更记录 #N"。

**M1 期间的例外**：M1 尚未交付，冻结项可自由调整 —— **冻结从 M1 验收通过之日生效**。

---

---

## 附录 A：`schema.sql`（v1.0 冻结版，可直接执行）

> **用法**：M1 开工时原样落成 `backend/sql/schema.sql`，供 Alembic `0001_initial` 参考与首次初始化使用。
> **与总方案的关系**：总方案 §3.2 是**设计说明**（解释字段为什么存在），本附录是**可执行快照**。两者冲突时以本附录为准，并立即回写总方案。
> **11 张表**：`project` `execution_target` `element` `element_locator` `action_catalog` `test_case` `test_step` `execution` `execution_step_result` `report` `artifact`

```sql
-- ============================================================
--  UI 自动化平台 · schema.sql  v1.0（M1 冻结版）
--  MySQL 8.0+ / utf8mb4
--  来源：《UI自动化平台M1详细设计》附录 A
--  注意：不含 WAP（决策 D5）；platform 仅 WEB/ANDROID/IOS
-- ============================================================
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ── 1. project —— 显式路由（P1）────────────────────────────
DROP TABLE IF EXISTS `project`;
CREATE TABLE `project` (
  `id`            BIGINT       NOT NULL AUTO_INCREMENT,
  `name`          VARCHAR(128) NOT NULL COMMENT '项目名称',
  `code`          VARCHAR(64)  NOT NULL COMMENT '项目英文标识，唯一',
  -- ★ 显式路由三件套：禁止用"用例里用了什么动作"反推端类型
  `platform`      ENUM('WEB','ANDROID','IOS') NOT NULL COMMENT '目标端（业务维度），仅 3 个取值，见 D5',
  `engine_key`    VARCHAR(64)  NOT NULL COMMENT '引擎适配器 key，如 playwright / appium / uiautomator2（技术维度）',
  `target_id`     BIGINT       NULL     COMMENT '默认执行目标，见 execution_target',
  -- 运行配置
  `base_url`      VARCHAR(512) NULL     COMMENT 'Web 项目根地址',
  `app_package`   VARCHAR(255) NULL     COMMENT 'App 包名（Android）/ bundleId（iOS）',
  `app_activity`  VARCHAR(255) NULL     COMMENT 'App 启动 Activity（Android）',
  `no_reset`      TINYINT(1)   NOT NULL DEFAULT 1 COMMENT 'App：执行前是否保留应用数据',
  `default_timeout_ms` INT     NOT NULL DEFAULT 15000 COMMENT '默认元素等待超时',
  -- 并发与通知
  `threads`       INT          NOT NULL DEFAULT 1 COMMENT '并发线程数',
  `notify_type`   ENUM('NONE','DINGTALK','WECOM') NOT NULL DEFAULT 'NONE',
  `notify_token`  VARCHAR(512) NULL,
  `notify_secret` VARCHAR(512) NULL,
  -- 软删除
  `is_deleted`    TINYINT(1)   NOT NULL DEFAULT 0,
  `deleted_at`    DATETIME     NULL,
  `created_by`    BIGINT       NULL,
  `updated_by`    BIGINT       NULL,
  `created_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_project_code` (`code`, `is_deleted`),
  KEY `idx_project_platform_engine` (`platform`, `engine_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='测试项目';

-- ── 2. execution_target —— 执行目标（借鉴 Toolium 配置驱动）──
DROP TABLE IF EXISTS `execution_target`;
CREATE TABLE `execution_target` (
  `id`         BIGINT       NOT NULL AUTO_INCREMENT,
  `name`       VARCHAR(128) NOT NULL COMMENT '目标名称，如 "Chrome-桌面" / "Pixel7-API34-AVD"',
  `platform`   ENUM('WEB','ANDROID','IOS') NOT NULL,
  `engine_key` VARCHAR(64)  NOT NULL,
  `options`    JSON         NOT NULL COMMENT '引擎/设备参数，schema 由 adapter 定义',
  `is_default` TINYINT(1)   NOT NULL DEFAULT 0,
  `enabled`    TINYINT(1)   NOT NULL DEFAULT 1,
  `created_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_target_platform_engine` (`platform`, `engine_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='执行目标（环境/设备）';

-- ── 3. element —— 逻辑元素（树形；不含任何定位信息）────────
DROP TABLE IF EXISTS `element`;
CREATE TABLE `element` (
  `id`           BIGINT       NOT NULL AUTO_INCREMENT,
  `project_id`   BIGINT       NOT NULL,
  `parent_id`    BIGINT       NOT NULL DEFAULT 0 COMMENT '父节点，0=根',
  `path`         VARCHAR(512) NOT NULL DEFAULT '/' COMMENT '物化路径，如 /1/12/ 便于子树查询',
  `element_name` VARCHAR(255) NOT NULL COMMENT '逻辑名，如「登录按钮」',
  `node_type`    ENUM('ELEMENT','FOLDER') NOT NULL DEFAULT 'ELEMENT' COMMENT '元素 / 目录',
  `description`  VARCHAR(512) NULL,
  `memo`         TEXT         NULL COMMENT '业务语义说明，供人与 AI 理解该元素是什么',
  `is_shared`    TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '1=项目内共享；M2 起固定为 1，字段预留给二期跨项目共享（D16）',
  `sort`         INT          NOT NULL DEFAULT 0,
  `is_deleted`   TINYINT(1)   NOT NULL DEFAULT 0,
  -- ★ M2 变更（F-M2-2）：软删除唯一键的序号列，0=未删；删除时置为自身 id
  `deleted_seq`  BIGINT       NOT NULL DEFAULT 0 COMMENT '软删序号：0=未删；删除时置为自身 id，使已删记录互不冲突',
  `deleted_at`   DATETIME     NULL,
  `created_by`   BIGINT       NULL,
  `updated_by`   BIGINT       NULL,
  `created_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  -- ★ M2 变更：原 (project_id,parent_id,element_name,is_deleted) 在软删下必然冲突，见变更记录 #1
  UNIQUE KEY `uk_element_name` (`project_id`, `parent_id`, `element_name`, `deleted_seq`),
  KEY `idx_element_project` (`project_id`, `is_deleted`),
  KEY `idx_element_path` (`project_id`, `path`),
  -- ★ M2 新增：按名字搜索（M2 §2.3.4）
  KEY `idx_element_name` (`project_id`, `element_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='逻辑元素（树形）';

-- ── 4. ★ element_locator —— 多端定位符映射（P2，本方案核心）──
DROP TABLE IF EXISTS `element_locator`;
CREATE TABLE `element_locator` (
  `id`            BIGINT       NOT NULL AUTO_INCREMENT,
  `element_id`    BIGINT       NOT NULL,
  -- ★ 二维定位：platform（业务端） × engine_key（技术引擎）
  `platform`      ENUM('WEB','ANDROID','IOS') NOT NULL,
  `engine_key`    VARCHAR(64)  NOT NULL DEFAULT '*' COMMENT '* 表示该平台下所有引擎通用；也可指定具体引擎',
  `locator_type`  VARCHAR(32)  NOT NULL COMMENT '语义定位类型，取值受 platform + engine 约束，见《技术方案》§5.1 与 M2 §2.5',
  `locator_value` TEXT         NOT NULL COMMENT '定位表达式（语义层写法，不含引擎前缀，见 M2 F-M2-1）',
  -- 回退链：同一 element+platform+engine 下可有多条，按 priority 由小到大依次尝试
  `priority`      INT          NOT NULL DEFAULT 100,
  `is_primary`    TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否首选（UI 展示标记，不影响执行顺序）',
  `verified_at`   DATETIME     NULL COMMENT '最后一次人工/自动验证通过时间',
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

-- ── 5. action_catalog —— 统一动作字典（P4）──────────────────
DROP TABLE IF EXISTS `action_catalog`;
CREATE TABLE `action_catalog` (
  `id`               BIGINT       NOT NULL AUTO_INCREMENT,
  `action_key`       VARCHAR(64)  NOT NULL COMMENT '统一动作标识（英文 snake_case，见 D6）',
  `name`             VARCHAR(64)  NOT NULL COMMENT '中文名，如「点击」（仅展示，与 action_key 解耦）',
  `category`         ENUM('ELEMENT','APP_LIFECYCLE','CONTEXT','NAVIGATION','ASSERT','DATA','SYSTEM')
                     NOT NULL COMMENT '动作分类，驱动前端分组',
  `platforms`        JSON         NOT NULL COMMENT '适用端，如 ["WEB"]，取值仅 WEB/ANDROID/IOS',
  `engines`          JSON         NOT NULL COMMENT '适用引擎，如 ["playwright"]；[] = 平台内建动作',
  `params_schema`    JSON         NOT NULL COMMENT '参数契约（JSON Schema），驱动前端表单与后端校验',
  `requires_element` TINYINT(1)   NOT NULL DEFAULT 0,
  `sort`             INT          NOT NULL DEFAULT 0,
  `enabled`          TINYINT(1)   NOT NULL DEFAULT 1,
  `created_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_action_key` (`action_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='统一动作字典';

-- ── 6. test_case ────────────────────────────────────────────
DROP TABLE IF EXISTS `test_case`;
CREATE TABLE `test_case` (
  `id`           BIGINT       NOT NULL AUTO_INCREMENT,
  `project_id`   BIGINT       NOT NULL,
  `title`        VARCHAR(255) NOT NULL,
  `description`  TEXT         NULL,
  `level`        ENUM('P0','P1','P2','P3') NOT NULL DEFAULT 'P1',
  `tags`         JSON         NULL,
  `expected_fail` TINYINT(1)  NOT NULL DEFAULT 0 COMMENT '0=预期成功 1=预期失败',
  `record_video` TINYINT(1)   NOT NULL DEFAULT 0,
  `state`        TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '1=启用 0=停用',
  `is_deleted`   TINYINT(1)   NOT NULL DEFAULT 0,
  `deleted_at`   DATETIME     NULL,
  `created_by`   BIGINT       NULL,
  `updated_by`   BIGINT       NULL,
  `created_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_case_project` (`project_id`, `is_deleted`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='测试用例';
-- 注：无 project_type —— 端类型统一从 project 继承（P1）

-- ── 7. test_step ────────────────────────────────────────────
DROP TABLE IF EXISTS `test_step`;
CREATE TABLE `test_step` (
  `id`            BIGINT       NOT NULL AUTO_INCREMENT,
  `case_id`       BIGINT       NOT NULL,
  `seq`           INT          NOT NULL COMMENT '执行顺序，从 1 开始',
  `action_key`    VARCHAR(64)  NOT NULL COMMENT '指向 action_catalog.action_key',
  `element_id`    BIGINT       NULL     COMMENT 'requires_element=1 时必填',
  `params`        JSON         NOT NULL COMMENT '动作参数，schema 见 action_catalog.params_schema',
  `output_var`    VARCHAR(64)  NULL     COMMENT '把动作结果存入变量，供后续步骤引用，如 ${text}',
  `assert_expr`   JSON         NULL     COMMENT '断言表达式（Web：表达式；通用：字面量）',
  `timeout_ms`    INT          NULL     COMMENT '覆盖项目默认超时',
  `on_failure`    ENUM('ABORT','CONTINUE','RETRY') NOT NULL DEFAULT 'ABORT',
  `retry_times`   INT          NOT NULL DEFAULT 0,
  `enabled`       TINYINT(1)   NOT NULL DEFAULT 1,
  `remark`        VARCHAR(255) NULL,
  `created_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_step_seq` (`case_id`, `seq`),
  KEY `idx_step_element` (`element_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用例步骤';

-- ── 8. execution ────────────────────────────────────────────
DROP TABLE IF EXISTS `execution`;
CREATE TABLE `execution` (
  `id`           BIGINT      NOT NULL AUTO_INCREMENT,
  `project_id`   BIGINT      NOT NULL,
  `target_id`    BIGINT      NULL     COMMENT '执行目标快照来源',
  `trigger_type` ENUM('MANUAL','SCHEDULE','API') NOT NULL DEFAULT 'MANUAL',
  `case_ids`     JSON        NOT NULL COMMENT '本次执行的用例 id 列表',
  `engine_key`   VARCHAR(64) NOT NULL COMMENT '执行时实际使用的引擎（快照，便于历史回溯）',
  `platform`     ENUM('WEB','ANDROID','IOS') NOT NULL COMMENT '同上，快照',
  `status`       ENUM('PENDING','RUNNING','PASSED','FAILED','ERROR','CANCELLED') NOT NULL DEFAULT 'PENDING',
  `total`        INT NOT NULL DEFAULT 0,
  `passed`       INT NOT NULL DEFAULT 0,
  `failed`       INT NOT NULL DEFAULT 0,
  `errored`      INT NOT NULL DEFAULT 0,
  `skipped`      INT NOT NULL DEFAULT 0,
  `started_at`   DATETIME NULL,
  `finished_at`  DATETIME NULL,
  `duration_ms`  BIGINT   NULL,
  `created_by`   BIGINT   NULL,
  `created_at`   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_exec_project_time` (`project_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='执行批次';

-- ── 9. execution_step_result（含定位稳定性埋点 + 二期预留列）──
DROP TABLE IF EXISTS `execution_step_result`;
CREATE TABLE `execution_step_result` (
  `id`            BIGINT      NOT NULL AUTO_INCREMENT,
  `execution_id`  BIGINT      NOT NULL,
  `case_id`       BIGINT      NOT NULL,
  `step_id`       BIGINT      NULL     COMMENT '冗余可空：脚本类步骤可能无 step',
  `seq`           INT         NOT NULL,
  `action_key`    VARCHAR(64) NOT NULL,
  `element_id`    BIGINT      NULL,
  `status`        ENUM('PASSED','FAILED','ERROR','SKIPPED') NOT NULL,
  `used_locator_id` BIGINT    NULL COMMENT '★ 实际命中的定位符（回退链的第几条），用于定位稳定性分析',
  `fallback_index`  INT       NULL COMMENT '★ 0=首选命中，>0=第 N 条回退命中',
  -- ★ 二期预留：WebView 上下文栈。一期（仅 Web）恒为 ('WEB','playwright')
  `active_platform` ENUM('WEB','ANDROID','IOS') NULL COMMENT '★ 该步骤执行时的活动端',
  `active_engine`   VARCHAR(64) NULL COMMENT '★ 该步骤执行时的活动引擎',
  `input_snapshot`  JSON      NULL,
  `actual_output`   TEXT      NULL,
  `expected_output` TEXT      NULL,
  `error_type`    VARCHAR(64) NULL COMMENT '如 TIMEOUT / LOCATOR_NOT_FOUND / ENGINE_ERROR',
  `error_message` TEXT        NULL,
  `stack_trace`   TEXT        NULL,
  `duration_ms`   BIGINT      NULL,
  `started_at`    DATETIME    NULL,
  `created_at`    DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_esr_exec` (`execution_id`, `case_id`, `seq`),
  KEY `idx_esr_locator` (`used_locator_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='步骤级执行结果';

-- ── 10. report ──────────────────────────────────────────────
DROP TABLE IF EXISTS `report`;
CREATE TABLE `report` (
  `id`            BIGINT      NOT NULL AUTO_INCREMENT,
  `execution_id`  BIGINT      NOT NULL,
  `project_id`    BIGINT      NOT NULL,
  `status`        ENUM('PASSED','FAILED','ERROR') NOT NULL,
  `pass_rate`     DECIMAL(5,2) NOT NULL DEFAULT 0 COMMENT '通过率 %',
  `summary`       JSON        NOT NULL COMMENT '按用例/按失败类型聚合',
  `html_path`     VARCHAR(512) NULL COMMENT '自渲染报告路径',
  `junit_path`    VARCHAR(512) NULL,
  `created_at`    DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_report_exec` (`execution_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='执行报告';

-- ── 11. artifact ────────────────────────────────────────────
DROP TABLE IF EXISTS `artifact`;
CREATE TABLE `artifact` (
  `id`           BIGINT      NOT NULL AUTO_INCREMENT,
  `execution_id` BIGINT      NOT NULL,
  `case_id`      BIGINT      NULL,
  `step_result_id` BIGINT    NULL,
  `type`         ENUM('SCREENSHOT','VIDEO','TRACE','LOG','DOM_SNAPSHOT','PAGE_SOURCE') NOT NULL,
  `storage`      ENUM('LOCAL','MINIO','S3') NOT NULL DEFAULT 'LOCAL',
  `uri`          VARCHAR(1024) NOT NULL,
  `size_bytes`   BIGINT      NULL,
  `created_at`   DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_artifact_exec` (`execution_id`, `type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='执行产物';

SET FOREIGN_KEY_CHECKS = 1;
-- ── schema.sql 结束（11 张表）──
```

**M1 的 Alembic 初始迁移**：`0001_initial.py` 的 `upgrade()` 内按上表顺序 `op.create_table(...)`，**不使用 autogenerate**。理由：autogenerate 对 MySQL `ENUM`、列 `COMMENT`、`UNIQUE KEY ... (col(128))` 前缀索引的处理不可靠，一次手写比反复校对更快。

---

## 附录 B：`seed_action_catalog.sql`（一期动作全集，**51 条**）

> **生成方式**：由 `CAPABILITY_MATRIX ∪ PLATFORM_BUILTIN_ACTIONS` **反向推出**（§2.5.3），保证 V5 双向校验一次通过。
> **构成**：引擎动作 **42** 条（playwright 28 / appium 24 / uiautomator2 18 的并集）+ 平台内建 **9** 条。
> **落点**：M1 原样落成 `backend/sql/seed_action_catalog.sql`，由 `scripts/seed.py` 执行。

```sql
-- ============================================================
--  seed_action_catalog.sql  v1.0（M1）
--  51 条 = 引擎动作 42 + 平台内建 9
--  engines = [] 表示平台内建动作（不需要引擎实现）
--  命名规范：英文 snake_case、动词开头（决策 D6）
-- ============================================================
SET NAMES utf8mb4;

DELETE FROM `action_catalog`;

INSERT INTO `action_catalog`
  (`id`,`action_key`,`name`,`category`,`platforms`,`engines`,`params_schema`,`requires_element`,`sort`,`enabled`)
VALUES
-- ── ELEMENT 类：元素操作（三引擎通用）────────────────────────
(1,'click','点击','ELEMENT','["WEB","ANDROID","IOS"]','["playwright","appium","uiautomator2"]',
 '{"type":"object","properties":{"button":{"type":"string","enum":["left","right","middle"],"default":"left"}},"additionalProperties":false}',1,110,1),
(2,'input','输入文本','ELEMENT','["WEB","ANDROID","IOS"]','["playwright","appium","uiautomator2"]',
 '{"type":"object","properties":{"text":{"type":"string"},"clear_first":{"type":"boolean","default":true}},"required":["text"],"additionalProperties":false}',1,120,1),
(3,'get_text','获取文本','ELEMENT','["WEB","ANDROID","IOS"]','["playwright","appium","uiautomator2"]',
 '{"type":"object","properties":{},"additionalProperties":false}',1,130,1),
(4,'get_attribute','获取属性值','ELEMENT','["WEB","ANDROID","IOS"]','["playwright","appium","uiautomator2"]',
 '{"type":"object","properties":{"name":{"type":"string"}},"required":["name"],"additionalProperties":false}',1,140,1),
(5,'wait_element','等待元素出现','ELEMENT','["WEB","ANDROID","IOS"]','["playwright","appium","uiautomator2"]',
 '{"type":"object","properties":{"state":{"type":"string","enum":["visible","attached","hidden","detached"],"default":"visible"}},"additionalProperties":false}',1,150,1),
(6,'check_exists','判断元素存在','ELEMENT','["WEB","ANDROID","IOS"]','["playwright","appium","uiautomator2"]',
 '{"type":"object","properties":{},"additionalProperties":false}',1,160,1),
(7,'hover','悬停','ELEMENT','["WEB","ANDROID","IOS"]','["playwright","appium"]',
 '{"type":"object","properties":{},"additionalProperties":false}',1,170,1),
(8,'select_option','下拉选择','ELEMENT','["WEB","ANDROID","IOS"]','["playwright","appium"]',
 '{"type":"object","properties":{"option":{"type":"string"},"label":{"type":"string"},"value":{"type":"string"},"index":{"type":"integer"}},"minProperties":1,"additionalProperties":false}',1,180,1),
(9,'double_click','双击','ELEMENT','["WEB","ANDROID","IOS"]','["playwright","appium"]',
 '{"type":"object","properties":{},"additionalProperties":false}',1,190,1),
(10,'long_press','长按','ELEMENT','["ANDROID","IOS"]','["appium","uiautomator2"]',
 '{"type":"object","properties":{"duration_ms":{"type":"integer","default":1000,"minimum":100}},"additionalProperties":false}',1,200,1),
(11,'scroll_to_element','滚动到元素','ELEMENT','["WEB","ANDROID","IOS"]','["playwright","appium","uiautomator2"]',
 '{"type":"object","properties":{},"additionalProperties":false}',1,210,1),
(12,'drag','拖拽','ELEMENT','["WEB","ANDROID","IOS"]','["playwright","appium"]',
 '{"type":"object","properties":{"target_element_id":{"type":"integer"},"target_x":{"type":"integer"},"target_y":{"type":"integer"}},"additionalProperties":false}',1,220,1),
(13,'coordinate_click','坐标点击','ELEMENT','["WEB","ANDROID","IOS"]','["playwright","appium","uiautomator2"]',
 '{"type":"object","properties":{"x":{"type":"integer"},"y":{"type":"integer"}},"required":["x","y"],"additionalProperties":false}',0,230,1),
(14,'upload_file','上传文件','ELEMENT','["WEB"]','["playwright"]',
 '{"type":"object","properties":{"files":{"type":"array","items":{"type":"string"},"minItems":1}},"required":["files"],"additionalProperties":false}',1,240,1),
(15,'element_scroll','元素内滚动','ELEMENT','["WEB"]','["playwright"]',
 '{"type":"object","properties":{"direction":{"type":"string","enum":["up","down","left","right"],"default":"down"},"distance":{"type":"integer","default":300}},"additionalProperties":false}',1,250,1),
(16,'page_swipe','页面滑动','ELEMENT','["ANDROID","IOS"]','["appium"]',
 '{"type":"object","properties":{"direction":{"type":"string","enum":["up","down","left","right"]},"distance":{"type":"integer","default":300}},"additionalProperties":false}',0,260,1),
(17,'multi_finger_swipe','多指滑动','ELEMENT','["ANDROID","IOS"]','["appium"]',
 '{"type":"object","properties":{"direction":{"type":"string","enum":["up","down","left","right"]},"distance":{"type":"integer","default":300}},"additionalProperties":false}',1,270,1),
(18,'swipe_up','向上滑动','ELEMENT','["ANDROID"]','["uiautomator2"]',
 '{"type":"object","properties":{"distance":{"type":"integer","default":300}},"additionalProperties":false}',0,280,1),
(19,'swipe_down','向下滑动','ELEMENT','["ANDROID"]','["uiautomator2"]',
 '{"type":"object","properties":{"distance":{"type":"integer","default":300}},"additionalProperties":false}',0,290,1),
(20,'element_list','获取元素列表','ELEMENT','["ANDROID"]','["uiautomator2"]',
 '{"type":"object","properties":{},"additionalProperties":false}',1,300,1),

-- ── NAVIGATION 类：导航（Web）─────────────────────────────────
(21,'navigate','前往 URL','NAVIGATION','["WEB"]','["playwright"]',
 '{"type":"object","properties":{"url":{"type":"string"}},"required":["url"],"additionalProperties":false}',0,310,1),
(22,'go_back','后退','NAVIGATION','["WEB","ANDROID","IOS"]','["playwright","appium","uiautomator2"]',
 '{"type":"object","properties":{},"additionalProperties":false}',0,320,1),
(23,'go_forward','前进','NAVIGATION','["WEB"]','["playwright"]',
 '{"type":"object","properties":{},"additionalProperties":false}',0,330,1),
(24,'refresh','刷新页面','NAVIGATION','["WEB"]','["playwright"]',
 '{"type":"object","properties":{},"additionalProperties":false}',0,340,1),
(25,'switch_to_iframe','进入/退出 iframe','NAVIGATION','["WEB"]','["playwright"]',
 '{"type":"object","properties":{"index":{"type":"integer"}},"description":"element_id 给定时进入该 iframe；element 与 index 均为空时退出到上一层（栈语义）","additionalProperties":false}',0,350,1),
(26,'switch_to_page','切换标签页','NAVIGATION','["WEB"]','["playwright"]',
 '{"type":"object","properties":{"index":{"type":"integer","default":-1}},"additionalProperties":false}',0,360,1),
(27,'page_scroll','页面滚动','NAVIGATION','["WEB"]','["playwright"]',
 '{"type":"object","properties":{"x":{"type":"integer"},"y":{"type":"integer"},"to":{"type":"string","enum":["top","bottom"]}},"additionalProperties":false}',0,370,1),

-- ── CONTEXT 类：上下文（WebView，二期）───────────────────────
(28,'get_contexts','获取上下文列表','CONTEXT','["ANDROID","IOS"]','["appium"]',
 '{"type":"object","properties":{},"additionalProperties":false}',0,380,1),
(29,'switch_to_context','切换到上下文','CONTEXT','["ANDROID","IOS"]','["appium"]',
 '{"type":"object","properties":{"name":{"type":"string"}},"required":["name"],"additionalProperties":false}',0,390,1),

-- ── APP_LIFECYCLE 类：App 生命周期（二期）────────────────────
(30,'start_app','启动应用','APP_LIFECYCLE','["ANDROID","IOS"]','["appium","uiautomator2"]',
 '{"type":"object","properties":{"app_package":{"type":"string"},"app_activity":{"type":"string"}},"additionalProperties":false}',0,400,1),
(31,'stop_app','关闭应用','APP_LIFECYCLE','["ANDROID","IOS"]','["appium","uiautomator2"]',
 '{"type":"object","properties":{},"additionalProperties":false}',0,410,1),
(32,'restart_app','重启应用','APP_LIFECYCLE','["ANDROID","IOS"]','["appium"]',
 '{"type":"object","properties":{},"additionalProperties":false}',0,420,1),
(33,'background_foreground','后台再前台','APP_LIFECYCLE','["ANDROID","IOS"]','["appium"]',
 '{"type":"object","properties":{"background_ms":{"type":"integer","default":3000}},"additionalProperties":false}',0,430,1),
(34,'go_home','返回桌面','APP_LIFECYCLE','["ANDROID","IOS"]','["appium","uiautomator2"]',
 '{"type":"object","properties":{},"additionalProperties":false}',0,440,1),
(35,'fix_orientation','固定屏幕方向','APP_LIFECYCLE','["ANDROID"]','["uiautomator2"]',
 '{"type":"object","properties":{"orientation":{"type":"string","enum":["PORTRAIT","LANDSCAPE"],"default":"PORTRAIT"}},"additionalProperties":false}',0,450,1),

-- ── SYSTEM 类：系统/取值/浏览器状态 ──────────────────────────
(36,'screenshot','截图','SYSTEM','["WEB","ANDROID","IOS"]','["playwright","appium","uiautomator2"]',
 '{"type":"object","properties":{"full_page":{"type":"boolean","default":false},"path":{"type":"string"}},"additionalProperties":false}',0,510,1),
(37,'get_url','获取当前 URL','SYSTEM','["WEB"]','["playwright"]',
 '{"type":"object","properties":{},"additionalProperties":false}',0,520,1),
(38,'get_title','获取页面标题','SYSTEM','["WEB"]','["playwright"]',
 '{"type":"object","properties":{},"additionalProperties":false}',0,530,1),
(39,'get_cookies','获取所有 Cookie','SYSTEM','["WEB"]','["playwright"]',
 '{"type":"object","properties":{},"additionalProperties":false}',0,540,1),
(40,'set_cookies','设置 Cookie','SYSTEM','["WEB"]','["playwright"]',
 '{"type":"object","properties":{"cookies":{"type":"array","items":{"type":"object"}}},"required":["cookies"],"additionalProperties":false}',0,550,1),
(41,'delete_cookies','清除 Cookie','SYSTEM','["WEB"]','["playwright"]',
 '{"type":"object","properties":{},"additionalProperties":false}',0,560,1),
(42,'accept_dialog','设置弹窗处理策略','SYSTEM','["WEB"]','["playwright"]',
 '{"type":"object","properties":{"accept":{"type":"boolean","default":true},"prompt_text":{"type":"string"}},"description":"设置【后续】弹窗的处理策略。弹窗为事件驱动，已在 M1 预注册 handler，本动作不处理已弹出的弹窗","additionalProperties":false}',0,570,1),

-- ── ASSERT 类：平台内建（engines=[]）─────────────────────────
(43,'assert_equals','断言：等于','ASSERT','["WEB","ANDROID","IOS"]','[]',
 '{"type":"object","properties":{"actual":{},"expected":{}},"required":["actual","expected"],"additionalProperties":false}',0,610,1),
(44,'assert_contains','断言：包含','ASSERT','["WEB","ANDROID","IOS"]','[]',
 '{"type":"object","properties":{"actual":{},"expected":{"type":"string"}},"required":["actual","expected"],"additionalProperties":false}',0,620,1),
(45,'assert_matches','断言：正则匹配','ASSERT','["WEB","ANDROID","IOS"]','[]',
 '{"type":"object","properties":{"actual":{},"pattern":{"type":"string"}},"required":["actual","pattern"],"additionalProperties":false}',0,630,1),
(46,'assert_visible','断言：元素可见','ASSERT','["WEB","ANDROID","IOS"]','[]',
 '{"type":"object","properties":{},"additionalProperties":false}',1,640,1),
(47,'assert_not_exists','断言：元素不存在','ASSERT','["WEB","ANDROID","IOS"]','[]',
 '{"type":"object","properties":{},"additionalProperties":false}',1,650,1),

-- ── DATA 类：变量 / 数据（engines=[]）────────────────────────
(48,'set_variable','设置变量','DATA','["WEB","ANDROID","IOS"]','[]',
 '{"type":"object","properties":{"name":{"type":"string"},"value":{}},"required":["name","value"],"additionalProperties":false}',0,710,1),
(49,'eval_expression','变量表达式求值','DATA','["WEB","ANDROID","IOS"]','[]',
 '{"type":"object","properties":{"expression":{"type":"string"},"output_var":{"type":"string"}},"required":["expression"],"description":"仅支持白名单运算，禁止任意代码执行","additionalProperties":false}',0,720,1),
(50,'db_query','数据库查询','DATA','["WEB","ANDROID","IOS"]','[]',
 '{"type":"object","properties":{"sql":{"type":"string"},"params":{"type":"array"},"output_var":{"type":"string"}},"required":["sql"],"description":"只读连接 + 结果行数上限","additionalProperties":false}',0,730,1),

-- ── SYSTEM 类：脚本（engines=[]）────────────────────────────
(51,'run_python','执行 Python 代码','SYSTEM','["WEB","ANDROID","IOS"]','[]',
 '{"type":"object","properties":{"code":{"type":"string"},"output_var":{"type":"string"}},"required":["code"],"description":"默认禁用（UIP_ALLOW_RUN_PYTHON=false）；开启时受限命名空间 + 强制超时","additionalProperties":false}',0,910,1);

-- 校验：应为 51 行
SELECT COUNT(*) AS total_actions FROM `action_catalog`;            -- 期望 51
SELECT COUNT(*) AS builtin_actions FROM `action_catalog`
  WHERE JSON_LENGTH(`engines`) = 0;                                -- 期望 9
```

**分段统计（供人工核对）**：

| category | 条数 | action_key |
|---|---|---|
| `ELEMENT` | 20 | click · input · get_text · get_attribute · wait_element · check_exists · hover · select_option · double_click · long_press · scroll_to_element · drag · coordinate_click · upload_file · element_scroll · page_swipe · multi_finger_swipe · swipe_up · swipe_down · element_list |
| `NAVIGATION` | 7 | navigate · go_back · go_forward · refresh · switch_to_iframe · switch_to_page · page_scroll |
| `CONTEXT` | 2 | get_contexts · switch_to_context |
| `APP_LIFECYCLE` | 6 | start_app · stop_app · restart_app · background_foreground · go_home · fix_orientation |
| `SYSTEM` | 8 | screenshot · get_url · get_title · get_cookies · set_cookies · delete_cookies · accept_dialog · run_python |
| `ASSERT` | 5 | assert_equals · assert_contains · assert_matches · assert_visible · assert_not_exists |
| `DATA` | 3 | set_variable · eval_expression · db_query |
| **合计** | **51** | 引擎动作 42 + 平台内建 9 |

**M1 实际实现的子集**（供进度追踪，不代表字典裁剪）：

| 引擎 | 字典声明 | M1 实现 | 未实现部分 |
|---|---|---|---|
| `playwright` | 28 | **28 全部** | — |
| `appium` | 24 | 0（全部 `NotImplementedError`） | M4 |
| `uiautomator2` | 18 | 0（同上） | M4 |
| 平台内建 | 9 | **9 全部**（`run_python` 默认禁用但已实现） | — |

---

## 附录 C：M1 文件清单与工作量分解

**规模判断**：M1 的代码量**集中在 L2 适配层**（约 55%），L3 只有薄薄一层，前端最小。这个分布是刻意的 —— M1 买的是"架构骨架"，不是功能。

| 分组 | 文件数 | 关键度 | 说明 |
|---|---|---|---|
| 脚手架（core / main / cli） | 7 | 🟡 | 配置、日志、DB、错误、lifespan 自检、CLI |
| **L2 适配层** | **11** | 🔴 **最关键** | base / capabilities / registry / resolver / session / actions / logsink + 3 adapter + 注册点 |
| 数据层（models / alembic / sql） | 10 | 🟡 | 11 表 ORM + 初始迁移 + 2 份 SQL |
| L3 服务与 API | 12 | 🟡 | 4 个 service + 7 个 router + 路由汇总 |
| DTO（schemas） | 6 | 🟢 | Pydantic 模型 |
| 领域常量 | 2 | 🔴 | `locator_types.py` / `action_keys.py`（校验与字典的一致性锚点） |
| 测试 | 14 | 🔴 | 契约 1 + 单测 10 + e2e 3 |
| fixtures（页面 + plan + target） | 10 | 🟡 | 附录 D |
| 配置（pyproject / importlinter / .env.example） | 3 | 🟡 | |
| 前端 | 14 | 🟢 | 3 视图 + 2 组件 + API 层 + 配置 |
| **合计** | **约 89 个文件** | | |

**关键路径（必须先做，否则后面全部返工）**：

```
base.py ──► capabilities.py ──► registry.py ──► adapters/__init__.py
   │                                              │
   └──► actions.py                                ▼
            │                            playwright_adapter.py
            ▼                                     │
     resolver.py / session.py                     ▼
            │                              app/cli.py（V2 在这里第一次跑通）
            ▼
     services/execution_service.py ──► api/executions.py ──► 前端
```

**建议实现顺序（10 步，每步都可独立验证）**：

| 步 | 内容 | 完成即可验证 |
|---|---|---|
| 1 | 脚手架 + `pyproject` + `importlinter.ini` | V7（正向：`lint-imports` 通过） |
| 2 | `models/` + `schema.sql` 落盘 + Alembic `0001_initial` | V1（DDL 建成） |
| 3 | `seed_action_catalog.sql` + `scripts/seed.py` | 字典 51 行入库 |
| 4 | **`base.py` + `capabilities.py` + `registry.py`** | V3 / V5 单测 |
| 5 | 三个适配器（playwright 完整 + 两桩）+ 注册点 | 契约测试全绿（§5.2） |
| 6 | `actions.py` + `resolver.py` + `session.py` | V4 / V6 / V9-7 |
| 7 | `cli.py` + fixtures 页面 + plan | **V2（端到端首次跑通）** |
| 8 | `services/` + `api/` | V9（API 层） |
| 9 | 前端骨架 | F1–F5 |
| 10 | `README` + 8 个 e2e 用例 + 收尾 | V8，DoD |

> **第 4–7 步是 M1 的全部风险所在**。第 1–3 步是体力活，第 8–10 步是在已定型的接口上填内容。若时间紧张，**优先保证 4–7 步质量**，8–10 可以延后 —— 因为 8–10 依赖的契约已经冻结，补起来不会有结构性返工。

**明确标注为"M1 可以先不做"的项**（不违反 DoD）：

- 前端 UI 美观度（M1 只要信息正确）
- `on_failure=RETRY` 的重试逻辑（M1 只识别枚举值，不实现重试；M3 补）
- `execution` 的 `trigger_type=SCHEDULE`（M3）
- `artifact.storage=MINIO/S3`（M3）
- 通知（M3）
- `run_python` 的沙箱强化（按 **D11**：M1 默认禁用即可，受限命名空间 + 超时强杀已足够）

---

## 附录 D：e2e fixture 页面结构要点

`fixtures/web/` 下的**纯静态页面**，**无后端依赖**，用 `python -m http.server 8899` 提供。

### D.1 `login.html` —— V2 主链路

```html
<!doctype html>
<meta charset="utf-8"><title>Demo Login</title>
<body>
  <form id="f">
    <input data-testid="username" placeholder="用户名">
    <input data-testid="password" type="password" placeholder="密码">
    <button data-testid="submit" type="button">登录</button>
  </form>
  <div data-testid="welcome" style="display:none"></div>
  <script>
    document.querySelector('[data-testid=submit]').onclick = () => {
      const u = document.querySelector('[data-testid=username]').value
      const w = document.querySelector('[data-testid=welcome]')
      w.textContent = '欢迎回来，' + u
      w.style.display = 'block'
    }
  </script>
</body>
```

**必须有的 testid**：`username` `password` `submit` `welcome`（与 `login_web.json` 计划一一对应）。
**注意**：`welcome` 初始 `display:none` → `wait_element(state="visible")` 才有意义（若用 `attached` 会立即返回，测不出等待语义）。

### D.2 `locators.html` —— ★ 11 种 Web 定位类型实测页

这是**修正 `_to_selector` 的唯一依据**（RV1）。页面必须让同一批语义元素**分别**可被 11 种方式命中：

| locator_type | 页面必须提供 |
|---|---|
| `id` | `<button id="btn-id">` |
| `class` | `<button class="btn-class">` |
| `css` | `<div class="wrap"><button class="css-target">` |
| `xpath` | 任一元素（用绝对/相对路径定位） |
| `testid` | `<button data-testid="btn-testid">` |
| `role` | `<button name="提交">提交</button>` + `<input type="checkbox" name="同意">` |
| `text` | 唯一文案的按钮：`<button>确定并继续</button>` |
| `placeholder` | `<input placeholder="请输入手机号">` |
| `label` | `<label for="lbl">邮箱</label><input id="lbl">` |
| `title` | `<button title="关闭弹窗">×</button>` |
| `alt` | `<img alt="品牌标识" src="data:image/gif;base64,R0lGOD...">` |

**M1 必须产出的一张表**（写进 README 或 §6.2 变更记录）：

| locator_type | `_to_selector` 产物 | 实测通过 | 备注 |
|---|---|---|---|
| `css` | `v` | ☐ | |
| `xpath` | `xpath=v` | ☐ | |
| `testid` | `[data-testid='v']` | ☐ | ⚠️ 也可用 Playwright 原生 `testIdAttribute` 配置 |
| `text` | `text=v` | ☐ | ⚠️ 默认子串匹配，需确认是否需要 `text="v"` 精确 |
| `role` | `v` | ☐ | ⚠️ 需确认 `button[name=Submit]` 的 name 是否支持正则、是否匹配可见名 |
| `placeholder` | `[placeholder='v']` | ☐ | |
| `label` | `label:has-text('v')` | ☐ | ⚠️ 注意这是定位 **label 元素**，可能需改为 `:has-text()` 的关联 input |
| `title` | `[title='v']` | ☐ | |
| `alt` | `[alt='v']` | ☐ | |
| `id` | `#v` | ☐ | ⚠️ 值含特殊字符（`.` `:`）会失败，需转义 |
| `class` | `.v` | ☐ | 同上 |

> **`label` 那一行是已知风险最高的**：`label:has-text('邮箱')` 命中的是 `<label>` 本身而非被关联的 `<input>`，`fill()` 会失败。M1 实测后很可能要改成 `input#lbl` 或 `:has(:text("邮箱"))` 之类的写法。**这正是把"待实测"写成表格而不是拍脑袋实现的原因。**

### D.3 其余 fixture

| 文件 | 结构要点 |
|---|---|
| `iframe.html` | 外层 `<iframe src="iframe_inner.html">`，内层再嵌一层；每层各有一个 `data-testid` 按钮 + 一个 `data-testid` 文本节点。**用于验证 iframe 栈的"进两层、退一层"** |
| `dialog.html` | 三个按钮分别触发 `alert('hi')` / `confirm('ok?')` / `prompt('name')`；页面上有 `data-testid="dialog-result"` 显示上次结果（用于断言） |
| `upload.html` | `<input type="file" data-testid="file">` + `<div data-testid="filename">` |
| `tabs.html` | `<a target="_blank" href="tabs_child.html" data-testid="open">`；`tabs_child.html` 有 `data-testid="child-title"` |
| `scroll.html` | ① 高度 5000px 的主页面（测 `page_scroll`）② `overflow:auto; height:200px` 的内层容器（测 `element_scroll`），容器底部有 `data-testid="scroll-bottom"` |

**fixture 配套的两个 JSON**：

- `tests/fixtures/targets/chrome_desktop.json`：`{"browser":"chromium","channel":"chrome","headless":true,"viewport":{"width":1440,"height":900}}`
- `tests/fixtures/targets/chrome_mobile.json`：`{"browser":"chromium","device":"iPhone 15","is_mobile":true,"has_touch":true}` ← **D5 的实证**：同一份 plan 换这个 target 就跑移动视口，**用例与定位符零改动**

---

## 附录 E：M1 交付检查清单

### E.1 功能与架构

- [ ] `schema.sql` 11 张表可在 MySQL 8 建表成功
- [ ] `seed_action_catalog.sql` 灌入 51 条（校验 SQL 输出 51 / 9）
- [ ] `EngineAdapter` 为 `ABC`，7 个核心动作 + 4 个生命周期成员为 `@abstractmethod`
- [ ] 所有动作方法 `async def`（F1）
- [ ] `capabilities` 与 `CAPABILITY_MATRIX[key]` 是**同一对象**（`is` 断言）
- [ ] `registry.resolve()` 是唯一路由入口，`adapters` 不被 L3 import
- [ ] 双向校验 `assert_catalog_consistency` + `assert_matrix_coverage` 均实现（F2）
- [ ] `SessionManager` 可多实例、可容纳 2 个引擎 key
- [ ] 桩用 `NotImplementedError`（消息含 "M4"），能力边界用 `UnsupportedActionError`

### E.2 数据与契约

- [ ] `element_locator` 的 `platform × engine_key` 二维查询可用（含 `'*'` 通配）
- [ ] 回退链排序：精确优先通配 → priority → id
- [ ] `execution_step_result.used_locator_id` / `fallback_index` 有真实写入
- [ ] `active_platform` / `active_engine` 列存在且写入 `("WEB","playwright")`
- [ ] 错误体为 `{"error":{code,message,detail,trace_id}}`
- [ ] 三处写入期拦截均实现（`PROJECT_PLATFORM_ENGINE_MISMATCH` / `ELEMENT_LOCATOR_TYPE_INVALID` / `CASE_STEP_*`）
- [ ] `FAILED` 与 `ERROR` 在结果与统计中语义分离

### E.3 工程与规范

- [ ] `lint-imports` 通过；反向验证（故意加 `import playwright`）能报错
- [ ] 结构化日志含 `trace_id` / `execution_id` / `case_id` / `step_seq`
- [ ] `README` 含 5 分钟跑通步骤（含 `playwright install` 与 `browser_channel` 说明）
- [ ] `.env.example` 覆盖 §2.3 全部配置项
- [ ] 无外网依赖即可跑 `pytest`

### E.4 文档一致性（用户明确要求）

- [ ] §0.5 三处修正（F1/F2/F3）已回写总方案 D1
- [ ] 附录 A 已落成为 `backend/sql/schema.sql`，内容一致
- [ ] 附录 B 已落成为 `backend/sql/seed_action_catalog.sql`，内容一致
- [ ] `_to_selector` 实测结论（附录 D.2 的表）已回写 §2.5.8 并更新总方案 §12.4 待确认项
- [ ] 本文件「变更记录」已记录 M1 期间对冻结项的任何调整

### E.5 明确不做（不算未完成）

- [ ] ~~元素库 UI~~（M2）· ~~StepEditor~~（M3）· ~~WebSocket 推送~~（M3）· ~~报告导出~~（M3）
- [ ] ~~Appium / uiautomator2 实现~~（M4）· ~~定位自愈~~（二期）

---

## 变更记录

> 依据 §6.4「变更流程」。M1 尚未验收、冻结未生效，但变更仍需在此留痕。

| # | 日期 | 条目 | 原因 | 影响面 |
|---|---|---|---|---|
| — | 2026-10-14 | v1.0 初稿 | M1 详细设计成稿 | — |
| — | 2026-10-14 | v1.1：新增决策 D11–D13（`run_python` 默认禁用 / `switch_to_iframe` 单动作栈语义 / M1 前端零组件库）+ FR17 | 三项评审结论确认 | §0.4 / §2.7 / §6.1 / §6.2 |
| 1 | 2026-10-19 | 附录 A `element` 表：新增 `deleted_seq BIGINT NOT NULL DEFAULT 0`；唯一键 `uk_element_name` 由 `(project_id, parent_id, element_name, is_deleted)` 改为 `(project_id, parent_id, element_name, deleted_seq)`；新增 `idx_element_name (project_id, element_name)`；`is_shared` 注释更新为"M2 起固定为 1，预留给二期跨项目共享" | **软删除唯一键缺陷（M2 §0.6 F-M2-2）**：布尔列 `is_deleted` 参与唯一键，删除第二条同名元素时必然撞键 `Duplicate entry`，元素 CRUD 一写就会踩到 | 表名与已有列名**未变**（符合 FR16 边界"可加列、不可改名删列"）；仅加列 + 换索引。M1 尚未开工、`schema.sql` 未生成，故直接改建表语句，不产生 ALTER 脚本（ALTER 版备在 M2 附录 A.3） |
| 2 | 2026-10-19 | 附录 A `element_locator` 表：新增 `probe_detail JSON NULL`；`locator_type` 注释明确为"**语义定位类型**"；`locator_value` 注释明确"不含引擎前缀"；`is_primary` 注释明确"不影响执行顺序" | 为 M2 的定位符验证器留存最近一次结果（M2 §2.3.2）；并落实 F-M2-1"语义层与语汇层分离" | 加列，向后兼容；`LocatorResolver` 不读 `probe_detail`，解析行为零影响 |
| 3 | 2026-10-19 | §2.5.2 `EngineAdapter` 新增**非动作**诊断方法 `probe_locator(chain, ctx) -> LocatorProbe`（默认实现基于 `check_exists` 兜底） | M2 验证器需要"命中 N 个"，而 `check_exists` 只返回 bool（M2 §0.6 F-M2-3） | **不进 `action_catalog`**（动作字典仍 51 条）；桩适配器无需覆写，不破坏 FR15 |

> **未变更项**：动作字典 51 条、`CAPABILITY_MATRIX`、`LocatorResolver` 排序规则、`execution_step_result` 全部列、18 个 M1 端点 —— M2 对这些资产**零改动**，这本身是 M1 分层设计有效的证据。

---

*— 文档结束 —*
*DDL 事实来源：附录 A（M1 期间）→ `backend/sql/schema.sql`（M1 完成后）*
*上游：《UI自动化平台技术方案》v1.0 · 同链：《UI自动化平台移动端对接方案》·《UI自动化平台M2详细设计》*


