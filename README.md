# UI 自动化平台（jerryyang-uitestplatform）

[![ci](https://github.com/Chunxia-zzz/uitestplatform/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Chunxia-zzz/uitestplatform/actions/workflows/ci.yml)

> 🤖 **新的 AI 会话接手本项目？先读 [`docs/HANDOVER.md`](docs/HANDOVER.md)** —— 当前状态、铁律、环境坑（Git 推送必须走 7890 代理）、待决策事项、下一步优先级全在里面。

多引擎 UI 自动化测试平台：以 **项目 → 元素 → 用例** 统一管理测试资产，按 **项目/端类型** 路由到不同执行引擎。

**项目定位**：小型测试团队**内部**使用的用例管理与执行平台（非对外 SaaS）。只保留主链：
**项目管理 → 元素库 → 用例编排 → 按引擎执行 → 生成报告**。
鉴权、分页、通知管理 UI、多实例、Docker/CD 等平台管理功能**刻意不做**（见 M3 §0.2.1）；
**CI 已作为工程门槛接入（D40，只校验不部署）**。执行通知支持**企微 / 飞书**两种渠道（D41）。

**当前实现范围**：M1（骨架 + 适配层）+ M2（元素库与多端 Locator）+ M3.1（执行内核）+ M3.3（用例集）+ M3.2（用例编排 / 报告页 / 产物访问）+ M3.4（一键接入）+ M3.5（元素扫描：URL → 候选 → 人工确认落库）+ **M3.6（平台收尾：执行目标 CRUD / 企微通知 / trace·video·HAR）** + **M3.7（飞书通知渠道）** + **M4.1（Android / Appium 平台侧 + 用例固化）**。
Web 端用 Playwright 真实执行；**Android 用 Appium 真机执行（M4.1 已实现 12/28 动作，见 `docs/UI自动化平台M4详细设计.md`）**；uiautomator2 仍是桩（M4.3）。

```
Project(platform, engine_key) ──► EngineRegistry ──► PlaywrightAdapter / AppiumAdapter(桩) / U2Adapter(桩)
                                        ▲
                        element ──► element_locator(platform × engine_key, priority 回退链)
```

---

## 1. 目录结构

```
jerryyang-uitestplatform/
├─ docs/                       设计文档（唯一维护源，按 D 编号组织）
│  ├─ README.md                文档索引 + 阅读路径
│  ├─ UI自动化平台技术选型报告.md      D0 为什么选这条路
│  ├─ UI自动化平台技术方案.md          D1 架构 / 数据模型 / 接口形状 / 里程碑
│  ├─ UI自动化平台移动端对接方案.md    D1a 二期预留（不实现）
│  ├─ UI自动化平台M1详细设计.md        D2-M1 骨架与适配层（v1.2 冻结）
│  ├─ UI自动化平台M2详细设计.md        D2-M2 元素库与多端 Locator（v1.0）
│  ├─ UI自动化平台M3详细设计.md        D2-M3 执行内核 + 编排呈现（M3.1/M3.2/M3.3 已实现）
│  ├─ UI自动化平台M3.4详细设计.md      D2-M3.4 一键接入（URL + 动作 → 全链装配，已实现）
│  ├─ UI自动化平台M3.5详细设计.md      D2-M3.5 元素扫描（URL → 候选 → 人工确认落库，已实现）
│  ├─ UI自动化平台M3.6详细设计.md      D2-M3.6 平台收尾（target CRUD / 企微通知 / trace-video-HAR，已实现）
│  ├─ UI自动化平台M3.7详细设计.md      D2-M3.7 飞书通知渠道（channel 单选 / interactive 卡片 / 关键词，已实现）
│  ├─ UI自动化平台M4详细设计.md        D2-M4 Android/Appium 平台侧 + 用例固化（M4.1 已实现）
│  ├─ Web端能力与使用指南.md           ★ 能测什么 / 怎么写用例 / 怎么执行（与代码同步）
│  └─ 待办与缺口跟踪.md               ★ 未完成/待确认事项唯一清单（含核验命令）
│
├─ backend/                    FastAPI 后端
│  ├─ app/
│  │  ├─ main.py               应用装配：建表 → 种子 → 启动强校验 → 路由
│  │  ├─ cli.py                命令行：doctor / audit / seed-demo
│  │  ├─ core/                 配置(config) / 数据库(db) / 错误码(errors) / 日志
│  │  ├─ domain/               ★ 领域常量（零业务依赖）
│  │  │  ├─ enums.py           端/引擎/状态枚举 + PLATFORM_ENGINES
│  │  │  ├─ action_keys.py     51 条动作字典（单一事实来源）
│  │  │  ├─ capabilities.py    引擎能力矩阵（P3）
│  │  │  └─ locator_types.py   三端定位类型字典（语义层，FR18）
│  │  ├─ engines/              ★ 引擎适配层
│  │  │  ├─ base.py            EngineAdapter ABC + Locator/LocatorChain/LocatorProbe
│  │  │  ├─ registry.py        引擎注册表 + 启动期双向强校验
│  │  │  ├─ resolver.py        LocatorResolver 回退链解析
│  │  │  ├─ session.py         SessionManager（非单例，FR8）
│  │  │  ├─ actions.py         动作分发（方法名==action_key，无映射表）+ 9 个内建动作
│  │  │  └─ adapters/          playwright_adapter（完整）/ stub_adapter（Appium、u2 桩）
│  │  ├─ models/               13 张表的 ORM（含 test_suite / test_suite_case）
│  │  ├─ repositories/         element_repo（含子树 path 重写）/ locator_repo
│  │  ├─ services/             tree / element / locator / locator_verify / project
│  │  │                       execution / execution_queue / event_bus / report
│  │  │                       suite（用例集）/ scheduler（cron 定时）
│  │  │                       case（步骤编排）/ artifact（产物访问）/ scaffold（一键接入）
│  │  │                       scan（页面扫描）/ notify（企微通知）/ target（执行目标）
│  │  ├─ schemas/              请求模型 + 响应序列化
│  │  └─ api/v1/               64 个 API 操作 + /ws/executions/{id}
│  ├─ alembic/                 ★ 迁移（GAP-33）；env.py 从 UIP_DATABASE_URL 取连接
│  │  └─ versions/             0001 baseline + 0002 target 软删（13 张表）
│  ├─ sql/
│  │  ├─ schema.sql            13 张表 DDL（MySQL 8，含 M2/M3.3 修正）
│  │  └─ seed_action_catalog.sql  51 条动作种子（由脚本生成，勿手改）
│  ├─ fixtures/web/            e2e 静态页面：login / locators / multi-hit
│  ├─ tests/                   244 个单元测试（target/通知/诊断/扫描/装配/编排…，另 MySQL 集成按需跳过）
│  ├─ requirements.txt · pyproject.toml · .env.example
│
├─ frontend/                   Vue 3 + Vite + TypeScript
│  ├─ src/
│  │  ├─ api/                  http 封装（错误体解包 + trace_id）/ 类型 / 端点函数
│  │  ├─ stores/element.ts     元素库状态（树、选中、定位符、验证结果）
│  │  ├─ components/           TreeNode（拖拽树）/ LocatorPanel / SchemaParams / AppModal / AppToast
│  │  ├─ views/                Scaffold / Scan(元素扫描) / ElementLibrary / Cases / Suites / Engines / Executions / Report
│  │  └─ styles/app.css        原生 CSS（不引入 UI 组件库，D13）
│  └─ package.json · vite.config.ts · tsconfig.json
│
└─ scripts/
   ├─ setup.ps1 / setup.sh     一键建 venv、装依赖、装 Chromium、装 npm 包
   ├─ dev.ps1 / dev.sh         同时起后端(8000) + 前端(5173)
   ├─ serve_fixtures.py        在 8899 端口伺服 e2e 静态页（login / locators / multi-hit / todo）
   ├─ demo_web_case.py         一条 11 步的 Todo 用例：建资产 → 执行 → 打印每步结果
   ├─ demo_android_case.py     星财富 Android 用例：7 步固化 → 执行 → 报告（M4.1）
   ├─ smoke_m3.py              M3.1 验收（202/重试/产物/报告/WS/并发）
   ├─ smoke_m32.py             M3.2 验收（编排/元素截图/产物/报告幂等/成员开关/筛选/断言/登录态）
   ├─ smoke_m34.py             M3.4 验收（一键装配/幂等/失败不残留/只建不跑）
   ├─ smoke_m35.py             M3.5 验收（扫描不落库/分级/导入落库/同名冲突/无目标）
   ├─ smoke_m36.py             M3.6 验收（target CRUD/通知矩阵/trace-video-HAR 产物/webhook 隔离）
   ├─ probe_dom_capability.py  评估工具：扫任意页面统计可定位比例（非产品功能）
   ├─ smoke_ui.py              前端各页冒烟（Playwright 截图，产物在 backend/artifacts）
   └─ gen_seed_sql.py          从动作字典生成 seed_action_catalog.sql
```

**为什么这样分层**：`domain` 零业务依赖 → 被 engines / services / api 三方引用而不会循环；
`engines` 只依赖 domain 与 core；`services` 依赖 repos 与 engines；`api` 只做协议转换。
`pyproject.toml` 里的 import-linter 契约把这条红线固化（`element_service` 不得 import 适配器）。

---

## 2. 快速开始（Windows / PowerShell）

> 第一次用？先看 [`docs/Web端能力与使用指南.md`](docs/Web端能力与使用指南.md)：
> 它回答「能测什么、怎么写第一条用例、跑完看哪里」。


```powershell
# 1) 一次性初始化（建 venv、装依赖、装 Chromium、装前端包）
./scripts/setup.ps1

# 2) 生成演示项目（demo-web：6 个元素、5 条定位符、1 个用例）
cd backend
../.venv/Scripts/python.exe -m app.cli seed-demo

# 3) 起服务（两个终端，或直接用 scripts/dev.ps1）
../.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
cd ../frontend && npm run dev        # http://localhost:5173
```

Linux / macOS 把 `scripts\setup.ps1` 换成 `scripts/setup.sh`，python 路径换成 `.venv/bin/python`。

**零配置**：默认数据库是 SQLite（`backend/data/uitest.db`），不需要装 MySQL。

### CI（只校验，不部署 · D40）

`.github/workflows/ci.yml` 三个 job，push `main` / PR 触发（纯文档改动走 `paths-ignore` 跳过）：

| job | 内容 |
|---|---|
| `backend` | `pytest` · `lint-imports` · 全新空库 `alembic upgrade head` + `alembic check` |
| `frontend` | `npm ci` · `vue-tsc --noEmit` · `vite build`（node 22 + npm 缓存） |
| `e2e` | seed-demo → 起后端 8000 + fixture 8899 → `smoke_m3/m32/m34/m35`（真 Chromium）；`needs: backend` |

本地跑与 CI 同一组命令：`bash scripts/ci_local.sh`（加 `--with-e2e` 时需 8000/8899 已启动）。
**没有 CD**：项目尚未部署到线上，不建空转的部署 job。

### Android 用例固化（M4.1）

前置：Appium Server 4723、后端 8000、真机已连接、被测包已安装且屏幕已解锁。

```bash
NO_PROXY=127.0.0.1,localhost python scripts/demo_android_case.py
```

脚本按 7 步把「星财富测试包 · 自选 → 第一个标的 → 个股详情」固化到平台：
项目 → 执行目标（udid/app_package）→ 元素 → 定位符 → 用例 → 5 个步骤 → 用例集并执行。
重复执行会复用已有项目/目标/元素/用例/用例集，不重复创建；第 2 步故意放了一条写错的
`resource_id`，用于验证回退链（预期 `fallback_index=1`）。

参数含义、保存与复用规则见 [`docs/UI自动化平台M4详细设计.md`](docs/UI自动化平台M4详细设计.md) §4。

### 验证 M2 的核心能力（回退链）

1. 起 fixture 静态页：`python scripts/serve_fixtures.py`（8899）
2. 前端打开「元素库」→ 选中「登录按钮」→ Web 端会看到两条定位符：
   - 第 1 条 `testid=submit-not-exist`（**故意写错**）
   - 第 2 条 `css=#submit`
3. 点「验证当前端」→ 第 1 条判断 `NONE`，第 2 条 `VALID`
4. 打开「执行结果」→ 运行首个用例 → 第 4 步 `click` 的 `fallback_index = 1`（黄底），
   `used_locator_id` 指向第 2 条 —— 这就是 P2 从设计变成事实的证据。

---

## 3. 已实现的能力

| 能力 | 状态 |
|---|---|
| 端/引擎显式路由（`project.platform` + `engine_key` 两列） | ✅ |
| 引擎注册表 + 启动期"动作字典 ↔ 能力矩阵"双向强校验 | ✅ |
| 动作分发（方法名==action_key，零映射表） | ✅ 51 条字典 / 42 个引擎动作 / 9 个内建 |
| 9 个平台内建动作（断言 / 变量 / db_query / run_python） | ✅ `run_python` 默认禁用（D11） |
| element_locator 二维定位（platform × engine_key，`*` 通配） | ✅ |
| 回退链解析 + `used_locator_id` / `fallback_index` 埋点 | ✅ |
| 元素树：物化路径、子树移动一条 UPDATE、循环检测、深度上限 | ✅ |
| 元素软删 + 引用保护（`deleted_seq` 修正唯一键） | ✅ |
| 三端定位类型字典（语义 / 引擎语汇分离） | ✅ 23 个语义类型 |
| ★ 定位符验证器（逐条探测、草稿验证、MULTIPLE 只警告） | ✅ |
| **异步执行队列**（提交 202 / 并发上限可配 / FIFO） | ✅ M3.1 |
| **失败重试**（`RETRY` + `retry_times`，逐次落 `attempt`） | ✅ M3.1 |
| **取消执行**（步骤间检查点） | ✅ M3.1 |
| **产物落库**（截图 → `artifact` 表） | ✅ M3.1 |
| **报告**（HTML + JSON，`report` 表幂等） | ✅ M3.1 |
| **WebSocket 推送** + JSONL 事件日志 | ✅ M3.1 |
| **启动自愈**（残留 RUNNING → ERROR） | ✅ M3.1 |
| **用例集**（`test_suite` + 成员、四层模型、单次运行） | ✅ M3.3 |
| **定时执行**（cron 5 段，APScheduler，重启重建 job） | ✅ M3.3 |
| **一键接入**（URL + 动作 → 建项目/元素/用例/用例集并执行） | ✅ M3.4 |
| **元素扫描**（URL → 候选 + 稳定性分级 → 人工勾选 → 落库） | ✅ M3.5 |
| **执行目标 CRUD**（创建/详情/更新/软删；路由校验 + 删除置空引用） | ✅ M3.6 |
| **企微 / 飞书通知**（渠道单选；飞书 interactive 卡片 + 自定义关键词；fire-and-forget 不影响执行；掩码防泄漏） | ✅ M3.6 / M3.7 |
| **trace / video / HAR**（trace 默认失败才存；产物落库、报告可下载） | ✅ M3.6 |
| 元素库前端（三栏、拖拽树、定位符面板、验证闭环） | ✅ |
| **用例编排**（按 `params_schema` 生成表单、步骤排序、写入期校验） | ✅ M3.2 |
| **报告页**（HTML iframe + JSON 视图 + 下载） | ✅ M3.2 |
| **产物访问**（按执行列出 / 下载，归属 + 目录双校验） | ✅ M3.2 |
| **元素级截图**（`screenshot(target=element)`） | ✅ M3.2 |
| **断言轮询**（`timeout_ms` 窗口内，无固定次数） | ✅ M3.2 |
| **登录态复用**（`storage_state` 读 / `save_storage_state` 写） | ✅ M3.2 |
| **Alembic 迁移**（baseline + `alembic check` 一致性） | ✅ M3.2 |
| 用例集成员启用开关 / 执行列表按用例集筛选 | ✅ M3.2 |
| **Android / Appium**（真机；12 个核心动作；回退链 / 截图 / 报告） | ✅ M4.1 |
| Appium 手势 / WebView / iOS；uiautomator2 | 🟡 M4.2 / M4.3 |
| 通知管理 UI / 健康度页 / trace 页面配置 / 网络拦截 | ⏸ 暂不做或顺延（见跟踪清单） |
| 登录鉴权 / 跨项目共享元素 / 定位自愈 | ⬜ 二期 |

## 4. 已知限制（刻意的，不是遗漏）

- **队列是进程内**（D23，**已确认不做 Redis**）：重启会丢排队任务（启动自愈把残留置 ERROR），WS 只在同进程有效；多实例部署才需要改，触发条件见 M3 §0.5。
- **取消只在步骤之间生效**（D22）：不强杀浏览器，避免半截会话与脏产物。
- **一次执行一个会话**：WebView 双会话要等 M4。
- **`probe_locator` 只精确到 Playwright**：桩适配器走基类默认实现（count ∈ {0,1}）。
- **SQLite 不做 ENUM 强约束**：生产用 MySQL 8 + `sql/schema.sql` 才能获得 ENUM 校验。
- **iOS 自动化需要 macOS**：架构级约束，见 D1a。
- **改表必须走 Alembic**：`cd backend && alembic revision --autogenerate -m "..."`，再 `alembic upgrade head`；
  `schema.sql` 仍是 MySQL DDL 事实源，两者由 `alembic check` 保证一致。
- **`storage_state` 通过执行目标的 `options` 配置**（`storage_state` 读、`save_storage_state` 写），不是全局开关。
- **无鉴权 / 无分页 / 无通知**：内网小团队场景，D26 明确不做。

完整的未完成清单与核验命令见 [`docs/待办与缺口跟踪.md`](docs/待办与缺口跟踪.md)。

## 5. 常用命令

```bash
# 自检：动作字典 / 定位字典 / 引擎注册表是否一致
python -m app.cli doctor

# 体检某项目全部定位符（真跑浏览器）
python -m app.cli audit --project 1 --platform WEB

# 重新生成动作种子 SQL
python ../scripts/gen_seed_sql.py

# M3.1 端到端验收（202 / 重试 / 产物 / 报告 / WS / 并发）
python ../scripts/smoke_m3.py

# M3.2 端到端验收（编排 / 元素截图 / 产物 / 报告幂等 / 成员开关 / 筛选 / 断言 / 登录态）
python ../scripts/smoke_m32.py

# M3.4 端到端验收（一键装配 / 幂等 / 失败不残留 / 只建不跑）
python ../scripts/smoke_m34.py

# M3.5 端到端验收（扫描不落库 / 分级 / 导入落库 / 同名冲突 / 无目标）
python ../scripts/smoke_m35.py

# M3.6 端到端验收（target CRUD / 通知矩阵 / trace-video-HAR 产物 / webhook 隔离）
python ../scripts/smoke_m36.py

# 前端各页冒烟 + 截图
python ../scripts/smoke_ui.py

# 迁移（改表前先确认模型与迁移一致）
../.venv/Scripts/alembic.exe check
../.venv/Scripts/alembic.exe upgrade head

# 说明：开发库由 init_db 的 create_all 建出，首次接 Alembic 时执行一次
#   ../.venv/Scripts/alembic.exe stamp head
# 把当前 schema 标记为基线；之后所有改表走 revision + upgrade，不再 create_all。

# 分层红线（需 requirements-dev.txt）
../.venv/Scripts/lint-imports.exe

# 测试（149 个）
python -m pytest -q
```

## 6. 文档

设计与实现的一致性由文档链保证：**D0 → D1 → D1a → D2-M1 → D2-M2 → D2-M3 → D2-M3.4 → D2-M3.5 → D2-M3.6**。
每份 D2-Mx 文末有「变更记录」，修改冻结项必须留痕并回写上游。
详见 [`docs/README.md`](docs/README.md)。
