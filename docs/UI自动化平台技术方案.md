# UI 自动化平台 · 技术方案（v1.0）

> ⚠️ **修订提示（2026-11-08）**：本文是 v1.0 首版总方案，部分选型已被后续决策覆盖 —— **队列用进程内 `asyncio.Queue`（D23/D26，不用 Redis）**、**CI 已接入但无 CD（D40）**、**Android 已按 D42/D43 落地（M4.1/M4.2）**、**生产库 SQLite vs MySQL 8 仍待定**。带 Redis 的段落仅作历史设计保留，实现以 `backend/` 代码与《HANDOVER》为准。

| 项 | 内容 |
|---|---|
| 文档版本 | v1.0（首版） |
| 编写日期 | 2026-10-14 |
| 上游依据 | 《UI 自动化平台技术选型报告.md》（含**附录 B** 本地调试环境方案、**附录 C** 二次验证与结论更新） |
| 方案性质 | **从零自建**，仅借鉴开源项目的**架构设计**，**不复制任何代码** |
| 后端技术栈 | **Python 3.11+ + FastAPI + SQLAlchemy 2.x + SQLite（默认）/ MySQL 8（生产选型待定）**；队列用进程内 `asyncio.Queue`（D23，**不用 Redis**） |
| 前端技术栈 | **Vue 3 + Vite + TypeScript**（UI 组件库待定，参考 Arco Design / Element Plus） |
| 一期范围 | **Web 端（Playwright）+ 适配器骨架**，零设备成本 |
| 文档粒度 | **完整方案**：目标架构 + 数据模型（含 DDL）+ EngineAdapter 接口 + 路由机制 + 里程碑与风险 |

---

## 0. 前置决策记录

本文档的所有设计均建立在以下 6 项已确认决策之上（另有 4 项**文档组织层面**的决策 D7–D10 —— 详细设计按里程碑横切 / 下一份为 M1 / monorepo 前后端分目录 / SQL 先嵌入文档附录 —— 记录在《UI 自动化平台 M1 详细设计》§0.4）：

| # | 决策点 | 选定 | 对设计的约束 |
|---|---|---|---|
| **D1** | 建设方式 | ✅ **从零自建，只借鉴架构** | 不 fork、不复制代码；rd / MokaTest / Pilot / Mops / Toolium 只作为**设计参照**；所有授权风险（R1/R2/R3）自动解除 |
| **D2** | 后端技术栈 | ✅ **Python + FastAPI** | 与 Playwright(python) / Appium-Python-Client / uiautomator2 / pytest 同源，适配层零跨语言桥接 |
| **D3** | 一期范围 | ✅ **仅 Web + 适配器骨架** | 一期交付物必须能**独立跑通 Web 用例**；Android/iOS 适配器只留接口与注册位，不实现 |
| **D4** | 文档粒度 | ✅ **完整方案** | 含 DDL、接口定义、里程碑、风险；**不含** REST API 契约与前端页面清单（留待下一份文档） |
| **D5** | 端类型取值 | ✅ **只有 3 个：`WEB` / `ANDROID` / `IOS`** | **不设 `WAP`**。移动浏览器（H5 / 响应式页）仍属 `WEB` 端，通过 `execution_target` 的**移动设备仿真**表达（见 §3.2.2 说明）。移动端对接方案单独成文：见《UI自动化平台·移动端对接方案》 |
| **D6** | 动作命名 | ✅ **一律英文 `snake_case`，语义自明** | 判定标准：新人看 `action_key` 能直接猜到动作语义。中文名只放 `name` 列供展示，与 `action_key` 解耦。细则见 §3.2.5 |

> **D5 补充说明（WAP 的处置）**：`WAP` 源自 rd-uitest-platform 的 `project.type`（`1:PC端 2:WAP端`），其本意是区分「PC 浏览器」与「移动浏览器」。但两者用的是**同一个引擎**（Playwright / Chromium）、**同一套定位符类型**（`css`/`xpath`/`testid`/`role`…），差异只在**视口尺寸与 User-Agent**。把这种差异上升为"端"，代价是三处：① 每个元素要维护两套完全重复的 Web 定位符；② `action_catalog.platforms` 需要为每个 Web 动作写两个值；③ 用例无法在 PC/移动视口间复用。**因此本方案把"移动浏览器"下沉为 `execution_target` 的一个选项**，而不是一个端。

**「只借鉴架构」的具体含义**（边界声明）：

| 允许 | 禁止 |
|---|---|
| 参照其**数据模型思路**（如 MokaTest 的元素树形组织、软删除、共享/私有） | 复制其 `.java` / `.py` / `.vue` 源码或整段 SQL |
| 参照其**接口形状**（如 Pilot 的 `TestingFrameworkDriver` 双接口、Mops 的 `Locator` dataclass） | 引入其依赖或包（`@wix-pilot/*`、`toolium`、`mops`） |
| 复用其**动作语汇**（rd 的 `playwright_method` 动作清单作为命名参照） | 直接搬运其表结构的缺陷（如重复列、错别字枚举） |

---

## 1. 目标与范围

### 1.1 建设目标

为「App 软件 + 配套 Web 中台」的项目组合，构建一个**统一管理测试资产、按项目/端路由到不同执行引擎**的 UI 自动化平台。

```
Project ──► Target/Platform ──► Engine Adapter ──► Playwright / Appium / uiautomator2
```

**必须满足的 5 条能力**（来自需求简报）：

| # | 能力 | 一期是否交付 |
|---|---|---|
| C1 | **项目 → 元素 → 用例** 三级统一管理 | ✅ 交付 |
| C2 | **元素的多端定位符映射**（一个逻辑元素挂 Web/Android/iOS 多套定位符） | ✅ 数据模型 + Web 端交付 |
| C3 | **按项目/端路由执行引擎** | ✅ 路由机制 + Playwright 适配器交付 |
| C4 | **可插拔的引擎适配器**（新增引擎 = 注册一个 adapter） | ✅ 接口 + 注册表交付 |
| C5 | App 原生端自动化（Appium / uiautomator2） | ⛔ 一期不实现（仅留接口位） |

### 1.2 一期范围（D3）

**做什么**：

1. 完整数据模型（含 `element_locator` 多端映射表）落地为 MySQL DDL；
2. `EngineAdapter` 接口 + 能力矩阵 + 注册表 + 路由解析；
3. **Playwright 适配器**完整实现（一期内唯一真正实现的引擎）；
4. 元素库 CRUD + 用例/步骤编排 + 执行调度 + 报告，端到端跑通；
5. Android / iOS 适配器**留桩**（`NotImplementedError` + 明确的能力声明），保证"新增引擎 = 加一个文件 + 注册"这一路径**在一期就被验证过**。

**明确不做**（避免范围蔓延）：

| 不做 | 原因 |
|---|---|
| Android / iOS 真实执行 | 一期零设备成本；架构先定型 |
| 元素的**定位自愈（AI heal）** | 需先积累真实失败样本；列二期 |
| 分布式多机执行（引擎注册到任意机器） | 一期单机足够；注册表已预留 `target` 维度 |
| CI/CD 集成、视觉回归、性能测试 | 非核心痛点 |
| REST API 契约文档、前端页面清单 | D4 已明确排除，留待下一份文档 |

### 1.3 设计原则

| # | 原则 | 说明 | 直接来自哪条调研结论 |
|---|---|---|---|
| P1 | **路由必须显式** | 项目上必须有 `platform` + `engine_key` 字段，**禁止**用"用例里用了什么动作"反推端类型 | 附录 C.6：rd 的 `project.type` 只有 PC/WAP，App 靠动作隐式推断，自相矛盾 |
| P2 | **Locator 必须是二维映射** | `platform × engine`，不能只按 `platform` | 附录 C.2：rd 的 Android 有 Appium / uiautomator2 两条路径，定位语汇不同 |
| P3 | **能力不对称要显式声明** | 适配器必须能回答"我支持哪些动作"，路由前校验 | 附录 C.4：rd 的 iOS(30) / Android(18) 动作集不同 |
| P4 | **动作语汇统一、实现各异** | 平台层只认统一动作 key；各适配器自己翻译成引擎 API | 附录 C.4：rd 已有跨引擎动作字典，直接对齐 |
| P5 | **不搬运缺陷** | 上游已知的 schema 缺陷（重复列、错别字枚举）在自建时一次性修正 | 附录 C.4 / C.7 |
| P6 | **引擎无关的资产与引擎相关的实现分离** | 元素、用例、步骤是引擎无关资产；driver 生命周期、定位翻译是引擎相关实现 | 全局 |

---

## 2. 总体架构

### 2.1 分层架构

```
┌──────────────────────────────────────────────────────────────────────────┐
│ L4  交互层      Vue 3 + Vite + TS                                        │
│     项目 / 元素库 / 用例编排 / 执行看板 / 报告                              │
├──────────────────────────────────────────────────────────────────────────┤
│ L3  应用层      FastAPI                                                  │
│     ┌────────────┬────────────┬────────────┬────────────┬────────────┐  │
│     │ ProjectSvc │ ElementSvc │ CaseSvc    │ ExecutionSvc│ ReportSvc │  │
│     └────────────┴────────────┴────────────┴────────────┴────────────┘  │
│     ┌──────────────────────┬──────────────────────┐                     │
│     │ Scheduler (APScheduler│ RealtimeHub(WebSocket)│                    │
│     │  + Redis 队列)         │                       │                    │
│     └──────────────────────┴──────────────────────┘                     │
├──────────────────────────────────────────────────────────────────────────┤
│ L2  引擎适配层  ★核心                                     │
│     ┌──────────────────────────────────────────────────────────────┐    │
│     │              EngineAdapterRegistry                            │    │
│     │   engine_key ──► adapter class                                │    │
│     └──────────────────────────────────────────────────────────────┘    │
│     ┌─────────────────────┬─────────────────────┬──────────────────┐    │
│     │  CapabilityMatrix   │  LocatorResolver    │  SessionManager  │    │
│     │  (能力不对称声明)     │  (多端定位+回退链)    │  (生命周期)       │    │
│     └─────────────────────┴─────────────────────┴──────────────────┘    │
│     ┌──────────────┬──────────────┬────────────────────┐                │
│     │ Playwright   │ Appium       │ UiAutomator2       │                │
│     │ Adapter ✅一期 │ Adapter ⛔桩  │ Adapter ⛔桩        │                │
│     │ WEB          │ ANDROID/iOS  │ ANDROID            │                │
│     └──────────────┴──────────────┴────────────────────┘                │
├──────────────────────────────────────────────────────────────────────────┤
│ L1  基础设施     MySQL 8（资产与结果） · Redis（队列/Pub-Sub）              │
│                 ArtifactStore（截图/视频/trace 本地或 MinIO）              │
└──────────────────────────────────────────────────────────────────────────┘
```

### 2.2 分层职责

| 层 | 职责 | 不做什么 |
|---|---|---|
| **L4 交互层** | 资产的增删改查、可视化编排、执行触发、结果展示 | 不含业务规则；不含引擎知识 |
| **L3 应用层** | 事务、校验、编排、调度、状态推进、报告聚合 | **不含任何引擎 API 调用**（这是 L2 的活） |
| **L2 引擎适配层** | 把统一动作翻译成具体引擎调用；管理 driver/context 生命周期；解析定位符 | 不写数据库；不感知 HTTP |
| **L1 基础设施** | 持久化、队列、产物存储 | — |

> **架构红线**：L3 **不允许** `import playwright` / `import appium`。所有引擎依赖只能出现在 `app/engines/adapters/` 下。这条红线是"C4 可插拔"能否成立的唯一保障，建议用 CI 静态检查（如 `import-linter`）强制。

### 2.3 与参考项目的对应关系（只借鉴，不搬运）

| 借鉴对象 | 借鉴的具体设计 | 落地在本方案的哪里 | 不借鉴什么 |
|---|---|---|---|
| **rd-uitest-platform** | ① 跨引擎**统一动作字典**的思路 ② 项目/用例/步骤的三级结构 ③ 实时进度推送 | §3.2 `action_catalog`、§3.2 `test_case`/`test_step`、§6.4 | 不搬其 `playwright_method`（表名误导 + `type` 列重复定义）、不搬"按用例类型分模块"的路由 |
| **MokaTest** | ① 元素**树形组织**（ELEMENT/FOLDER + parent_id + sort）② `is_shared` 共享/私有 ③ 全表软删除 | §3.2 `element` 表 | 不搬其单定位符模型（它只有 1 个 `locator_type`，且枚举全是 Web）→ **多端映射本方案自研**（P2） |
| **Wix Pilot** | `TestingFrameworkDriver` 的**接口形状**：一个引擎一个实现、接口最小化 | §4.1 / §4.2 `EngineAdapter` | 不引入其 JS 包；不照搬自然语言驱动（一期用结构化步骤） |
| **Mops** | `Locator` 的**数据形状** + 定位类型的自动判定思路 | §3.2 `element_locator`、§5.2 | 不引入其库；不照搬"同用例随意切引擎"（一期显式路由） |
| **Toolium** | **配置驱动**选择引擎/驱动的组织方式 | §4.4 `ExecutionTarget` 配置 | 不引入其库（Playwright 集成为 Beta） |

---

## 3. 数据模型

### 3.1 模型总览

```
                       ┌──────────┐
                       │ project  │  platform + engine_key  ← 显式路由（P1）
                       └────┬─────┘
              ┌─────────────┼──────────────┬────────────────┐
              ▼             ▼              ▼                ▼
        ┌──────────┐  ┌──────────┐   ┌───────────┐   ┌──────────────┐
        │ element  │  │test_case │   │exec_target│   │ (二期)        │
        │ (树形)    │  └────┬─────┘   │ (设备/环境) │   │ 计划/套件     │
        └────┬─────┘       │          └───────────┘   └──────────────┘
             │             ▼
             ▼        ┌───────────┐
     ┌───────────────┐│ test_step │
     │element_locator│└─────┬─────┘
     │platform×engine│      │ action_key
     │  ★核心        │      ▼
     └───────────────┘┌──────────────┐
                      │action_catalog│  统一动作字典（P4）
                      └──────────────┘
                              │
                              ▼
                      ┌──────────────┐      ┌──────────────────────┐
                      │ execution    │─────►│ execution_step_result│
                      └──────┬───────┘      └──────────────────────┘
                             ▼
                      ┌──────────────┐      ┌──────────────┐
                      │ report       │─────►│ artifact     │
                      └──────────────┘      └──────────────┘
```

**表清单（一期）**：

| 分组 | 表 | 说明 |
|---|---|---|
| 项目 | `project` | 测试项目，**显式绑定 platform + engine_key** |
| 项目 | `execution_target` | 执行目标（Web：浏览器规格；App：设备/caps JSON） |
| 元素 | `element` | 逻辑元素树（ELEMENT / FOLDER） |
| 元素 | **`element_locator`** | **多端定位符映射（platform × engine）★ 本方案核心** |
| 用例 | `test_case` | 用例 |
| 用例 | `test_step` | 步骤（引用动作 key + 元素 id + 参数 JSON） |
| 用例 | `action_catalog` | 统一动作字典（驱动前端下拉 + 能力校验） |
| 执行 | `execution` | 一次执行批次 |
| 执行 | `execution_step_result` | 步骤级结果 |
| 报告 | `report` | 批次汇总 |
| 报告 | `artifact` | 截图 / 视频 / trace / 日志 |

> 命名与 `rd` / `MokaTest` 保持**可对照**（便于团队阅读两者源码时迁移心智），但表结构按本方案重新设计。

### 3.2 核心 DDL（MySQL 8 / utf8mb4）

#### 3.2.1 `project` —— 显式路由（P1 落地）

```sql
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
  -- 软删除（借鉴 MokaTest 全表软删除）
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
```

**为什么要把 `platform` 与 `engine_key` 分成两个字段**（P1 / P2）：

| 场景 | `platform` | `engine_key` | 说明 |
|---|---|---|---|
| Web 中台 | `WEB` | `playwright` | 唯一解 |
| Web 中台 · 移动浏览器（原 WAP） | `WEB` | `playwright` | **同一个端、同一个引擎**，仅 `execution_target` 不同（移动视口 / 移动 UA），见下方说明 |
| Android 原生 App（Appium 路径） | `ANDROID` | `appium` | 需要 WebView context 能力时选这条 |
| Android 原生 App（u2 路径） | `ANDROID` | `uiautomator2` | 只做纯原生、启动更快 |
| iOS 原生 App | `IOS` | `appium` | iOS 唯一解 |
| App 内 H5（二期） | `WEB`（子上下文） | `playwright` | 由 Appium 切 context 后交棒，见 §4.5 与移动端方案 |

> 若合并成一个字段（如 `engine_key='android_appium'`），后续加引擎会导致字段值爆炸且无法按"端"做统计。**分两列是刻意的。**

**移动浏览器（原 WAP）如何表达**（D5 落地）：不改端类型，而是建两个 `execution_target`：

```jsonc
// execution_target: "Chrome-桌面"
{ "platform": "WEB", "engine_key": "playwright",
  "options": { "browser": "chromium", "channel": "chrome", "headless": false,
               "viewport": { "width": 1440, "height": 900 } } }

// execution_target: "Chrome-移动仿真（原 WAP）"
{ "platform": "WEB", "engine_key": "playwright",
  "options": { "browser": "chromium", "headless": false,
               "device": "iPhone 15",           // Playwright 内置设备描述符
               "is_mobile": true, "has_touch": true,
               "user_agent": "Mozilla/5.0 (iPhone; ...)" } }
```

→ 同一份用例、同一套元素定位符，**切换 `target_id` 即可在桌面与移动浏览器间复用**；这正是把 WAP 下沉为 target 而非端的直接收益。

#### 3.2.2 `execution_target` —— 执行目标（借鉴 Toolium 的配置驱动）

```sql
CREATE TABLE `execution_target` (
  `id`         BIGINT       NOT NULL AUTO_INCREMENT,
  `name`       VARCHAR(128) NOT NULL COMMENT '目标名称，如 "Chrome-136-桌面" / "Pixel7-API34-AVD"',
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
```

`options` 示例：

```jsonc
// platform=WEB, engine_key=playwright
{ "browser": "chromium", "channel": "chrome", "headless": false,
  "viewport": { "width": 1440, "height": 900 }, "record_video": true }

// platform=ANDROID, engine_key=appium
{ "platformName": "Android", "platformVersion": "14",
  "deviceName": "emulator-5554", "udid": "emulator-5554",
  "automationName": "UiAutomator2", "appPackage": "com.demo.app",
  "appActivity": ".MainActivity", "noReset": true,
  "appiumServer": "http://127.0.0.1:4723" }

// platform=ANDROID, engine_key=uiautomator2
{ "serial": "127.0.0.1:21503" }
```

#### 3.2.3 `element` —— 逻辑元素（借鉴 MokaTest 的树形 + 共享/私有）

```sql
CREATE TABLE `element` (
  `id`           BIGINT       NOT NULL AUTO_INCREMENT,
  `project_id`   BIGINT       NOT NULL,
  `parent_id`    BIGINT       NOT NULL DEFAULT 0 COMMENT '父节点，0=根',
  `path`         VARCHAR(512) NOT NULL DEFAULT '/' COMMENT '物化路径，如 /1/12/ 便于子树查询',
  `element_name` VARCHAR(255) NOT NULL COMMENT '逻辑名，如「登录按钮」',
  `node_type`    ENUM('ELEMENT','FOLDER') NOT NULL DEFAULT 'ELEMENT' COMMENT '元素 / 目录',
  `description`  VARCHAR(512) NULL,
  `memo`         TEXT         NULL COMMENT '业务语义说明，供人与 AI 理解该元素是什么',
  `is_shared`    TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '1=项目内共享 0=用例私有（借鉴 MokaTest）',
  `sort`         INT          NOT NULL DEFAULT 0,
  `is_deleted`   TINYINT(1)   NOT NULL DEFAULT 0,
  `deleted_at`   DATETIME     NULL,
  `created_by`   BIGINT       NULL,
  `updated_by`   BIGINT       NULL,
  `created_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_element_name` (`project_id`, `parent_id`, `element_name`, `is_deleted`),
  KEY `idx_element_project` (`project_id`, `is_deleted`),
  KEY `idx_element_path` (`project_id`, `path`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='逻辑元素（树形）';
```

> **注意**：`element` 表**不含任何定位信息**。这是与 MokaTest 最大的区别 —— 它把 `locator_type`/`locator_value` 放在元素表里，导致一个元素只能有一个定位符、且只能定位一种端。本方案把定位信息**全部下沉到 `element_locator`**。

#### 3.2.4 ★ `element_locator` —— 多端定位符映射（P2 落地，本方案核心）

```sql
CREATE TABLE `element_locator` (
  `id`            BIGINT       NOT NULL AUTO_INCREMENT,
  `element_id`    BIGINT       NOT NULL,
  -- ★ 二维定位：platform（业务端） × engine_key（技术引擎）
  `platform`      ENUM('WEB','ANDROID','IOS') NOT NULL,
  `engine_key`    VARCHAR(64)  NOT NULL DEFAULT '*' COMMENT '* 表示该平台下所有引擎通用；也可指定具体引擎',
  `locator_type`  VARCHAR(32)  NOT NULL COMMENT '定位类型，取值受 platform 约束，见 §5.1 字典',
  `locator_value` TEXT         NOT NULL COMMENT '定位表达式',
  -- 回退链：同一 element+platform+engine 下可有多条，按 priority 由小到大依次尝试
  `priority`      INT          NOT NULL DEFAULT 100,
  `is_primary`    TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否首选（用于 UI 展示主定位）',
  `verified_at`   DATETIME     NULL COMMENT '最后一次人工/自动验证通过时间',
  `status`        ENUM('UNVERIFIED','VALID','INVALID') NOT NULL DEFAULT 'UNVERIFIED',
  `enabled`       TINYINT(1)   NOT NULL DEFAULT 1,
  `remark`        VARCHAR(255) NULL,
  `created_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_locator` (`element_id`, `platform`, `engine_key`, `locator_type`, `locator_value`(128)),
  KEY `idx_locator_lookup` (`element_id`, `platform`, `engine_key`, `enabled`, `priority`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='元素多端定位符映射';
```

**这张表怎么解决 P2 的两类问题**：

场景一 —— **同一元素跨三端**（`engine_key='*'` 通配）：

| element_id | platform | engine_key | locator_type | locator_value | priority |
|---|---|---|---|---|---|
| 101 | `WEB` | `*` | `testid` | `login-submit` | 10 |
| 101 | `WEB` | `*` | `css` | `.login-form button[type=submit]` | 100 |
| 101 | `ANDROID` | `*` | `resource_id` | `com.demo.app:id/btn_login` | 10 |
| 101 | `ANDROID` | `*` | `text` | `登录` | 100 |
| 101 | `IOS` | `*` | `accessibility_id` | `loginButton` | 10 |

→ 用例里只写「点击 元素#101」，平台按当前项目的 `platform` 自动取对应定位符，并按 `priority` 形成回退链。

场景二 —— **同一端不同引擎的定位语汇不同**（`engine_key` 精确指定）：

| element_id | platform | engine_key | locator_type | locator_value | priority |
|---|---|---|---|---|---|
| 101 | `ANDROID` | `appium` | `accessibility_id` | `loginButton` | 10 |
| 101 | `ANDROID` | `appium` | `-android uiautomator` | `new UiSelector().resourceId("com.demo.app:id/btn_login")` | 100 |
| 101 | `ANDROID` | `uiautomator2` | `resourceId` | `com.demo.app:id/btn_login` | 10 |
| 101 | `ANDROID` | `uiautomator2` | `text` | `登录` | 100 |

→ 这正是相对 rd 的 **关键改进**：rd 的 Android 同时存在 Appium 与 uiautomator2 两条执行路径，若定位符只按 platform 存，切引擎就会定位失败。**本方案把 `engine_key` 作为定位符的一个维度。**

**解析规则**（`LocatorResolver`，见 §5.2）：

```
resolve(element_id, platform, engine_key):
    locs = SELECT * FROM element_locator
           WHERE element_id = ? AND platform = ? AND engine_key IN (?, '*') AND enabled = 1
    # 精确匹配优先于通配
    sort by (engine_key == engine_key_desc), priority ASC
    return locs   # 有序回退链
```

#### 3.2.5 `action_catalog` —— 统一动作字典（P4 落地）

```sql
CREATE TABLE `action_catalog` (
  `id`               BIGINT       NOT NULL AUTO_INCREMENT,
  `action_key`       VARCHAR(64)  NOT NULL COMMENT '统一动作标识，如 click / input / wait_element',
  `name`             VARCHAR(64)  NOT NULL COMMENT '中文名，如「点击」',
  `category`         ENUM('ELEMENT','APP_LIFECYCLE','CONTEXT','NAVIGATION','ASSERT','DATA','SYSTEM')
                     NOT NULL COMMENT '动作分类，驱动前端分组',
  `platforms`        JSON         NOT NULL COMMENT '适用端，如 ["WEB"]，取值仅 WEB/ANDROID/IOS',
  `engines`          JSON         NOT NULL COMMENT '适用引擎，如 ["playwright"] —— 与 CapabilityMatrix 保持一致',
  `params_schema`    JSON         NOT NULL COMMENT '参数契约（JSON Schema），驱动前端表单与后端校验',
  `requires_element` TINYINT(1)   NOT NULL DEFAULT 0,
  `sort`             INT          NOT NULL DEFAULT 0,
  `enabled`          TINYINT(1)   NOT NULL DEFAULT 1,
  `created_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_action_key` (`action_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='统一动作字典';
```

**一期种子数据（节选，完整版见 `sql/seed_action_catalog.sql`）**：

| action_key | name | category | platforms | engines | requires_element |
|---|---|---|---|---|---|
| `navigate` | 前往 URL | NAVIGATION | `["WEB"]` | `["playwright"]` | 0 |
| `click` | 点击 | ELEMENT | `["WEB","ANDROID","IOS"]` | `["playwright","appium","uiautomator2"]` | 1 |
| `input` | 输入 | ELEMENT | 同上 | 同上 | 1 |
| `hover` | 悬停 | ELEMENT | `["WEB","IOS"]` | `["playwright","appium"]` | 1 |
| `select_option` | 下拉选择 | ELEMENT | `["WEB","IOS"]` | `["playwright","appium"]` | 1 |
| `wait_element` | 等待元素出现 | ELEMENT | 全端 | 全引擎 | 1 |
| `get_text` | 获取文本 | ELEMENT | 全端 | 全引擎 | 1 |
| `get_attribute` | 获取属性值 | ELEMENT | 全端 | 全引擎 | 1 |
| `check_exists` | 判断元素存在 | ELEMENT | 全端 | 全引擎 | 1 |
| `screenshot` | 截图 | SYSTEM | 全端 | 全引擎 | 0 |
| `start_app` | 启动应用 | APP_LIFECYCLE | `["ANDROID","IOS"]` | `["appium","uiautomator2"]` | 0 |
| `stop_app` | 关闭应用 | APP_LIFECYCLE | `["ANDROID","IOS"]` | `["appium","uiautomator2"]` | 0 |
| `get_contexts` | 获取上下文 | CONTEXT | `["ANDROID","IOS"]` | `["appium"]` | 0 |
| `switch_to_context` | 切换到上下文 | CONTEXT | `["ANDROID","IOS"]` | `["appium"]` | 0 |
| `multi_finger_swipe` | 多指滑动 | ELEMENT | `["IOS"]` | `["appium"]` | 1 |
| `switch_to_iframe` | 进入 iframe | NAVIGATION | `["WEB"]` | `["playwright"]` | 1 |
| `get_cookies` | 获取所有 Cookie | SYSTEM | `["WEB"]` | `["playwright"]` | 0 |
| `assert_equals` | 断言：等于 | ASSERT | 全端 | `[]`（平台内建，非引擎动作） | 0 |
| `assert_contains` | 断言：包含 | ASSERT | 全端 | 同上 | 0 |
| `db_query` | 数据库查询 | DATA | 全端 | 同上 | 0 |
| `run_python` | 执行 Python 代码 | SYSTEM | 全端 | 同上 | 0 |

> 三点说明（均来自附录 C 的教训）：
> 1. `platforms` / `engines` 双数组是**刻意的**：它同时是"能力矩阵的数据库落地"，供前端过滤 + 后端校验，避免出现"选了 iOS 项目却配了 Web 动作"。
> 2. `engines = []` 表示**平台内建动作**（断言、数据、脚本），不需要引擎实现 —— 这样断言逻辑就不会漂移到适配器里。
> 3. `get_contexts` / `switch_to_context` 一期标 `engines=["appium"]`，与 rd 现状一致（rd 只在 iOS 动作集暴露）。二期补 Android 时只需改这一行数据 + 适配器实现。
> 4. **动作命名一律用英文**（决策 D6）。规则见下节。

**动作命名约定（决策 D6）**

| 规则 | 说明 | 示例 |
|---|---|---|
| **全英文 `snake_case`** | 不使用拼音、不使用中文；`action_key` 一经发布不改名（改名即破坏已有用例） | `click` · `wait_element` |
| **动词开头，2–3 词** | 保证「一眼看出这是什么动作」；宾语可省（`click`）但不可只有宾语 | ✅ `get_text` / `switch_to_iframe` ❌ `text_get` / `element_wait_for_appearance` |
| **同类动作统一前缀** | 取用 `get_*`、`switch_*`、`assert_*`、`*_app`，便于前端分组与检索 | `get_text` / `get_cookies` / `get_contexts` |
| **平台内建动作显式前缀** | 断言用 `assert_*`，数据用 `db_*`，脚本用 `run_*` → 与引擎动作在命名上即可区分 | `assert_equals` / `db_query` / `run_python` |
| **中文名放 `name` 列** | 前端展示用中文，`action_key` 保持英文；**两者解耦**，中文名可随时优化而不影响用例 | `name='等待元素出现'` |

> 判定标准只有一条：**新人看 `action_key` 能否直接猜到动作语义**。不追求命名族谱的完备，宁可短而直白（`click` 优于 `click_element`）。
> 一期种子清单（24 个动作）会随《M3 详细设计》落成 `sql/seed_action_catalog.sql`；在此之前如对某个动作名有异议，直接改种子表即可，**没有兼容负担**。

#### 3.2.6 `test_case` / `test_step`

```sql
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
-- 注：无 project_type —— 端类型统一从 project 继承（P1，避免 rd 的信息冗余与不一致）

CREATE TABLE `test_step` (
  `id`            BIGINT       NOT NULL AUTO_INCREMENT,
  `case_id`       BIGINT       NOT NULL,
  `seq`           INT          NOT NULL COMMENT '执行顺序，从 1 开始',
  `action_key`    VARCHAR(64)  NOT NULL COMMENT '指向 action_catalog.action_key',
  `element_id`    BIGINT       NULL     COMMENT 'requires_element=1 时必填',
  `params`        JSON         NOT NULL COMMENT '动作参数，schema 见 action_catalog.params_schema',
  `output_var`    VARCHAR(64)  NULL     COMMENT '把动作结果存入变量，供后续步骤引用，如 ${text}',
  `assert_expr`   JSON         NULL     COMMENT '断言表达式（Web：jmespath/表达式；通用：字面量）',
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
```

> 设计取舍：`test_step` 采用 **`action_key` + `params` JSON**（而非 rd 的 20+ 宽表列）。原因：① 加动作不改表结构 ② `params_schema` 已能校验 ③ 避免 rd `app_case_steps` 那种"api_url/method/sql/files 全塞一张表"的宽表腐化。需要统计分析时，用 `action_key` 建索引查询即可。

`params` 示例：

```jsonc
// 点击 + 断言
[
  { "seq": 1, "action_key": "navigate", "params": { "url": "https://demo.example.com/login" } },
  { "seq": 2, "action_key": "input",  "element_id": 101, "params": { "text": "${username}" } },
  { "seq": 3, "action_key": "input",  "element_id": 102, "params": { "text": "${password}" } },
  { "seq": 4, "action_key": "click",  "element_id": 103 },
  { "seq": 5, "action_key": "wait_element", "element_id": 201, "timeout_ms": 10000 },
  { "seq": 6, "action_key": "get_text", "element_id": 201, "output_var": "welcome",
    "assert_expr": { "op": "contains", "value": "欢迎" } }
]
```

#### 3.2.7 执行与报告表

```sql
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
  -- ★ 二期预留：WebView 场景下同一 execution 内会切换"活动端/引擎"，此两列记录步骤执行时的实际上下文
  --   一期（仅 Web）恒为 ('WEB','playwright')，现在加可空列可免二期迁移
  `active_platform` ENUM('WEB','ANDROID','IOS') NULL COMMENT '★ 该步骤执行时的活动端（WebView 上下文栈）',
  `active_engine`   VARCHAR(64) NULL COMMENT '★ 该步骤执行时的活动引擎（WebView 接棒）',
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

CREATE TABLE `report` (
  `id`            BIGINT      NOT NULL AUTO_INCREMENT,
  `execution_id`  BIGINT      NOT NULL,
  `project_id`    BIGINT      NOT NULL,
  `status`        ENUM('PASSED','FAILED','ERROR') NOT NULL,
  `pass_rate`     DECIMAL(5,2) NOT NULL DEFAULT 0 COMMENT '通过率 %',
  `summary`       JSON        NOT NULL COMMENT '按用例/按失败类型聚合',
  `html_path`     VARCHAR(512) NULL COMMENT 'Allure / 自渲染报告路径',
  `junit_path`    VARCHAR(512) NULL,
  `created_at`    DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_report_exec` (`execution_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='执行报告';

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
```

> `execution_step_result.used_locator_id` + `fallback_index` 是本方案的**埋点设计**：它让"哪条定位符最稳"变成可统计的事实，是二期做**定位自愈**和**定位符自动排序**的数据基础。rd 与 MokaTest 都没有这个字段。

---

## 4. 引擎适配层设计

### 4.1 为什么必须做适配层

调研实测的三个事实，共同决定了适配层不可省略：

| 事实 | 后果 |
|---|---|
| rd 里 `AppiumMethod` / `UiAutomator2Method` / `WebAutomation` 三个类**方法名与签名不统一**（`input(element_type, element, text)` vs `input(element_type, value, text)`） | 调用方必须写 `if 引擎==X: ...` 分支 → **业务逻辑与引擎耦合** |
| rd 的引擎路由是**按用例类型分模块**（`routers/web_case.py` / `api_case.py` / `app_case.py`） | 加第三个引擎要改模块结构，**不是"注册一个 adapter"** |
| iOS 与 Android 的**动作集不对称**（iOS 30 / Android 18，`get_contexts` 只有 iOS 有） | 若不显式声明能力，运行到一半才报 `AttributeError` |

### 4.2 `EngineAdapter` 接口

> **★ 本节签名已按《UI 自动化平台 M1 详细设计》§0.5 修正两处**（2026-10-14）：
>
> | # | 原稿 | 修正为 | 原因 |
> |---|---|---|---|
> | **F1** | 动作方法为同步 `def` | **全部 `async def`** | 原稿与 §4.5 的 `async_playwright` + `await` 实现**自相矛盾**；Playwright Python 的 async API 是官方推荐路径，FastAPI 本身也是 async |
> | **F3** | 基类为 `Protocol` + `@runtime_checkable` | **`ABC` + `@abstractmethod`** | `@runtime_checkable` 的 `isinstance` **只检查属性是否存在，不校验签名**；而 M1–M4 最可能犯的错正是"桩适配器漏实现某个动作"。`ABC` 在**实例化时**立即报 `TypeError`，把错误提前到进程启动阶段。测试替身 `FakeAdapter` 继承 `ABC` 同样简单，"便于写测试替身"的收益并未丢失 |
>
> **接口的完整实现级定义（含全部 40+ 个可选动作签名）见《UI 自动化平台 M1 详细设计》§2.5.2**。本文只保留设计意图与形状，**同一份接口不在两处维护**。

**值对象（三个）** —— 完整字段与语义见 D2-M1 §2.5.2：

| 类型 | 职责 | 关键字段 |
|---|---|---|
| `Locator` | 一条定位符 | `type` · `value` · `index` · **`locator_id`**（埋点用，对应 `element_locator.id`） |
| `LocatorChain` | 一个元素的**有序回退链** | `element_id` · `locators: tuple[Locator, ...]` |
| `ActionContext` | 单步执行上下文（由平台注入） | `step_seq` · `timeout_ms` · `variables` · `artifacts_dir` · `on_log` · **`active_platform` / `active_engine`**（二期 WebView 预留） |

**异常体系** —— `error_type` 会写入 `execution_step_result.error_type`，并被上层用来区分 `FAILED`（产品 bug）与 `ERROR`（测试/环境问题）：

| 异常 | `error_type` | 语义 |
|---|---|---|
| `EngineError` | `ENGINE_ERROR` | 基类 |
| `LocatorNotFoundError` | `LOCATOR_NOT_FOUND` | 回退链全未命中 → 属测试资产问题 |
| `ActionTimeoutError` | `TIMEOUT` | 动作超时 |
| `UnsupportedActionError` | `UNSUPPORTED_ACTION` | **引擎本来就不支持**该动作（能力边界，永久事实） |
| `SessionCrashedError` | `SESSION_CRASHED` | 唯一允许触发"重建 session 后重试"的类型 |
| `DriverDisconnectedError` | `DRIVER_DISCONNECTED` | |
| `ScriptExecutionError` | `SCRIPT_ERROR` | 平台内建 `run_python` 失败 |

**适配器契约（形状）**：

```python
class EngineAdapter(ABC):
    key: ClassVar[str]                        # 注册表 key，如 "playwright"
    platforms: ClassVar[frozenset[Platform]]  # {"WEB"} / {"ANDROID","IOS"} / {"ANDROID"}
    capabilities: ClassVar[frozenset[str]]    # 必须 is CAPABILITY_MATRIX[key]（同一对象）

    # ── 生命周期（@abstractmethod；start/stop 必须幂等）──
    @classmethod
    @abstractmethod
    def create(cls, target_options: dict[str, Any]) -> "EngineAdapter": ...
    @abstractmethod
    async def start(self) -> None: ...
    @abstractmethod
    async def stop(self) -> None: ...
    @property
    @abstractmethod
    def session_id(self) -> str | None: ...

    # ── 核心元素动作（@abstractmethod：任何 UI 引擎都必须有这 7 个）──
    @abstractmethod
    async def click(self, loc: LocatorChain, ctx: ActionContext, *, button: str = "left") -> None: ...
    @abstractmethod
    async def input(self, loc: LocatorChain, ctx: ActionContext, *,
                    text: str, clear_first: bool = True) -> None: ...
    @abstractmethod
    async def get_text(self, loc: LocatorChain, ctx: ActionContext) -> str: ...
    @abstractmethod
    async def get_attribute(self, loc: LocatorChain, ctx: ActionContext, *, name: str) -> str | None: ...
    @abstractmethod
    async def wait_element(self, loc: LocatorChain, ctx: ActionContext, *, state: str = "visible") -> None: ...
    @abstractmethod
    async def check_exists(self, loc: LocatorChain, ctx: ActionContext) -> bool: ...
    @abstractmethod
    async def screenshot(self, ctx: ActionContext, *, full_page: bool = False,
                         path: str | None = None) -> str: ...

    # ── 可选动作（默认 raise UnsupportedActionError；支持则覆盖并同步 capabilities）──
    async def hover(self, loc: LocatorChain, ctx: ActionContext) -> None: ...
    async def select_option(self, loc: LocatorChain, ctx: ActionContext, *,
                            option: str | None = None, label: str | None = None,
                            value: str | None = None, index: int | None = None) -> None: ...
    async def navigate(self, ctx: ActionContext, *, url: str) -> None: ...
    async def switch_to_iframe(self, ctx: ActionContext, *,
                               element: LocatorChain | None = None,
                               index: int | None = None) -> None: ...
    async def get_contexts(self, ctx: ActionContext) -> list[str]: ...
    async def switch_to_context(self, ctx: ActionContext, *, name: str) -> None: ...
    # ... 其余可选动作（合计 40+ 个）见 D2-M1 §2.5.2
```

**接口设计的四条要点**：

| 要点 | 理由 |
|---|---|
| 用 `ABC` + `@abstractmethod`（F3） | 漏实现动作时**实例化即报错**，把错误提前到进程启动阶段 |
| **核心 7 动作必须实现、其余默认不支持** | 能力不对称是常态（P3）。核心 7 个构成"最小完整闭环"；其余默认 `raise UnsupportedActionError`，与 `capabilities` 声明形成**双保险**：声明少了被 `supports()` 拦，声明多了在此抛错 |
| **元素类动作一律收 `LocatorChain`**（不是单个 `Locator`） | 回退链是引擎层的职责，业务层只关心"哪个元素" |
| 统一 `ctx: ActionContext` 载体 | 避免每个方法都加七八个参数（rd 的 `start_app` 就是 6 个位置参数，易错） |

> **★ 冻结约定（FR4）**：适配器的方法名 **==** `action_key`，关键字参数名 **==** `params_schema` 的属性名。
> 有了这条，`actions.py` 可以直接 `getattr(adapter, action_key)(chain, ctx, **params)` 转发，**不需要为每个动作写映射表**，也不需要 if-else 长链。详见 D2-M1 §2.5.7。
>
> **★ 桩的语义分界（FR15）**：`NotImplementedError` = *"该引擎该支持，但里程碑未到"*；`UnsupportedActionError` = *"该引擎本来就不支持"*。两者混用会让 M4 的工作量失去可追踪性。

### 4.3 能力矩阵（P3 落地）

`app/engines/capabilities.py`：

```python
"""能力矩阵：声明每个引擎支持哪些动作 key。
与 action_catalog.engines 保持一致，启动时做一次一致性自检。"""

CAPABILITY_MATRIX: dict[str, frozenset[str]] = {
    "playwright": frozenset({
        # 元素
        "click", "input", "get_text", "get_attribute", "wait_element",
        "check_exists", "hover", "select_option", "double_click",
        "scroll_to_element", "drag", "screenshot", "coordinate_click",
        # Web 专属
        "navigate", "go_back", "go_forward", "refresh",
        "switch_to_iframe", "switch_to_page", "get_url", "get_title",
        "get_cookies", "set_cookies", "delete_cookies", "accept_dialog",
        "upload_file", "page_scroll", "element_scroll",
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
        #      / multi_finger_swipe —— 与 rd 实测的 Android 动作集一致（附录 C.4）
    }),
}

def supports(engine_key: str, action_key: str) -> bool:
    return action_key in CAPABILITY_MATRIX.get(engine_key, frozenset())
```

**一致性自检（★ F2：双向校验，启动时执行，任一方向失败则拒绝启动）**：

```python
class CapabilityInconsistency(AssertionError):
    """能力矩阵与动作字典不一致 —— 启动时抛出，进程拒绝启动。"""


def assert_catalog_consistency(catalog_rows: list[dict]) -> None:
    """方向 A：动作字典 → 能力矩阵。

    字典声明某动作支持引擎 E，则 E 的矩阵里必须真有这个动作。
    否则会出现"前端能选、引擎不支持"。
    """
    problems: list[str] = []
    for row in catalog_rows:
        key = row["action_key"]
        for eng in (row["engines"] or []):
            if eng not in CAPABILITY_MATRIX:
                problems.append(f"[未知引擎] {key} 声明支持 {eng}，但该引擎未在矩阵中注册")
            elif key not in CAPABILITY_MATRIX[eng]:
                problems.append(f"[漏实现] {key} 声明支持 {eng}，但 {eng} 的矩阵不含该动作")
    if problems:
        raise CapabilityInconsistency(
            "动作字典 -> 能力矩阵 校验失败（共 %d 处）：\n  - %s"
            % (len(problems), "\n  - ".join(problems))
        )


def assert_matrix_coverage(catalog_rows: list[dict]) -> None:
    """方向 B：能力矩阵 → 动作字典（★ F2 新增）。

    矩阵里声明支持的每个引擎动作，字典里必须有一行且 engines 含该引擎。
    否则该动作在前端永远选不到 -> 死代码，且无人发现。
    """
    declared: dict[str, set[str]] = {r["action_key"]: set(r["engines"] or [])
                                     for r in catalog_rows}
    problems: list[str] = []
    for eng, actions in CAPABILITY_MATRIX.items():
        for action in sorted(actions):
            if action not in declared:
                problems.append(f"[孤儿动作] {eng}.{action} 在矩阵中，但字典里没有这一行")
            elif eng not in declared[action]:
                problems.append(
                    f"[声明缺失] {eng}.{action} 在矩阵中，但字典该行 engines 不含 {eng}"
                )
    if problems:
        raise CapabilityInconsistency(
            "能力矩阵 -> 动作字典 校验失败（共 %d 处）：\n  - %s"
            % (len(problems), "\n  - ".join(problems))
        )
```

> 这一步直接消灭了 rd 式的隐患：rd 的动作字典里 iOS 有 `获取上下文` 而 Android 没有，但因为两边是**独立的硬编码方法列表**，任何一处漏改都不会被发现。本方案把动作支持情况收敛成**唯一事实来源**，并在启动时强校验。

**★ F2 修正：为什么两个方向都要校验**

| 方向 | 机制 | 漏了会怎样 | 谁能发现 |
|---|---|---|---|
| **A** 字典 → 矩阵 | `assert_catalog_consistency` | 前端能配这个动作，跑到一半抛 `AttributeError` | 只有真正跑到该步骤的人 |
| **B** 矩阵 → 字典 | `assert_matrix_coverage`（F2 新增） | 适配器实现了该动作，但 UI 永远不给选 → **死代码** | **没人会发现** |

方向 B 是 M1 详细设计阶段补上的：单向校验只能发现"声明了但矩阵没有"，而**反向的漏声明是静默失效**。第 10 章的测试策略原本已写"双向一致"，这里把代码补齐。

### 4.4 注册表与路由（P1 落地）

`app/engines/registry.py`：

```python
"""引擎注册表。新增引擎只需 import 后 register()。"""
from typing import Type
from app.engines.base import EngineAdapter

_REGISTRY: dict[str, Type[EngineAdapter]] = {}


def register(adapter_cls: Type[EngineAdapter]) -> Type[EngineAdapter]:
    key = adapter_cls.key
    if key in _REGISTRY and _REGISTRY[key] is not adapter_cls:
        raise ValueError(f"引擎 key 重复注册：{key}")
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


def resolve(platform: str, engine_key: str) -> Type[EngineAdapter]:
    """路由入口：校验 platform 与 engine_key 是否匹配。"""
    cls = get_adapter_class(engine_key)
    if platform not in cls.platforms:
        raise ValueError(
            f"项目端 {platform} 与引擎 {engine_key} 不匹配"
            f"（该引擎支持：{sorted(cls.platforms)}）"
        )
    return cls
```

`app/engines/adapters/__init__.py`（唯一的引擎注册点）：

```python
from app.engines.adapters.playwright_adapter import PlaywrightAdapter
from app.engines.adapters.appium_adapter import AppiumAdapter            # 一期为桩
from app.engines.adapters.uiautomator2_adapter import UiAutomator2Adapter  # 一期为桩
from app.engines.registry import register

register(PlaywrightAdapter)
register(AppiumAdapter)
register(UiAutomator2Adapter)
```

**路由调用链**（L3 → L2）：

```
ExecutionService.run(project_id, case_ids)
    │
    ├─ project = repo.get_project(project_id)
    ├─ cls = registry.resolve(project.platform, project.engine_key)   # ← 显式路由
    ├─ adapter = cls.create(target.options)
    ├─ adapter.start()
    ├─ for case in cases:
    │      for step in case.steps:
    │          action = ACTION_DISPATCH[step.action_key]            # 平台内建 or 引擎动作
    │          if action.needs_engine and not supports(project.engine_key, step.action_key):
    │              raise UnsupportedActionError(...)               # 提前失败，不跑到一半才炸
    │          chain = LocatorResolver.resolve(step.element_id, project.platform, project.engine_key)
    │          await action.invoke(adapter, chain, ctx)
    └─ adapter.stop()
```

### 4.5 Playwright 适配器（一期交付）

> **★ 完整实现清单见《UI 自动化平台 M1 详细设计》§2.5.8**（28 个动作的映射表 + 三个 M1 特有实现决策）。本节只给出骨架与设计要点。M1 阶段相对本节骨架有四处细化：① `_find()` 返回 `(element, fallback_index, locator)` —— 第三个值即 `used_locator_id` 的来源；② `accept_dialog` 改为**预注册 dialog handler + 策略设置**（弹窗是事件驱动，不预注册会永久阻塞）；③ `switch_to_iframe` 改为**栈语义**（无参调用即弹栈，不新增动作条目）；④ 定位类型翻译 `_to_selector` 的 11 种映射需用 fixture 页面实测后再定稿。

`app/engines/adapters/playwright_adapter.py`（骨架示意）：

```python
from playwright.async_api import async_playwright
from app.engines.base import (EngineAdapter, Locator, LocatorChain, ActionContext,
                              LocatorNotFoundError, ActionTimeoutError, UnsupportedActionError)
from app.engines.capabilities import CAPABILITY_MATRIX
from app.engines.registry import register


@register
class PlaywrightAdapter(EngineAdapter):
    key = "playwright"
    platforms = frozenset({"WEB"})
    capabilities = CAPABILITY_MATRIX["playwright"]

    def __init__(self, options: dict):
        self._opts = options
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    @classmethod
    def create(cls, target_options: dict) -> "PlaywrightAdapter":
        return cls(target_options)

    async def start(self) -> None:
        self._pw = await async_playwright().start()
        self._browser = await getattr(self._pw, self._opts.get("browser", "chromium")).launch(
            headless=self._opts.get("headless", True),
            channel=self._opts.get("channel"),          # 如 "chrome" → 用本机 Chrome
        )
        ctx_args = {"viewport": self._opts.get("viewport", {"width": 1440, "height": 900})}
        if self._opts.get("record_video"):
            ctx_args |= {"record_video_dir": self._opts["artifacts_dir"], "record_video_size": ctx_args["viewport"]}
        self._context = await self._browser.new_context(**ctx_args)
        self._page = await self._context.new_page()

    # ---- 定位符翻译：本方案 11 种 Web locator_type → Playwright ----
    @staticmethod
    def _to_selector(loc: Locator) -> str:
        t, v = loc.type, loc.value
        if t == "css":      return v
        if t == "xpath":    return f"xpath={v}"
        if t == "testid":   return f"[data-testid='{v}']"
        if t == "text":     return f"text={v}"
        if t == "role":     return v                      # 形如 "button[name=Submit]"
        if t == "placeholder": return f"[placeholder='{v}']"
        if t == "label":    return f"label:has-text('{v}')"
        if t == "title":    return f"[title='{v}']"
        if t == "alt":      return f"[alt='{v}']"
        if t == "id":       return f"#{v}"
        if t == "class":    return f".{v}"
        raise UnsupportedActionError(f"Playwright 不支持的定位类型：{t}")

    async def _find(self, chain: LocatorChain, ctx: ActionContext, timeout_ms: int):
        """按优先级逐条尝试，返回 (locator, 命中的 locator 索引)。"""
        last_err = None
        for idx, loc in enumerate(chain.locators):
            try:
                el = self._page.locator(self._to_selector(loc)).first
                await el.wait_for(state="attached", timeout=timeout_ms)
                ctx.on_log("locator.hit", {"element_id": chain.element_id,
                                           "locator": loc.describe(), "fallback_index": idx})
                return el, idx
            except Exception as e:                        # noqa: BLE001
                last_err = e
                ctx.on_log("locator.miss", {"element_id": chain.element_id,
                                            "locator": loc.describe(), "fallback_index": idx})
        raise LocatorNotFoundError(
            f"元素 {chain.element_id} 的 {len(chain.locators)} 条定位符全部未命中："
            f"{[l.describe() for l in chain.locators]}"
        ) from last_err

    async def click(self, loc: LocatorChain, ctx: ActionContext) -> None:
        el, _ = await self._find(loc, ctx, ctx.timeout_ms)
        await el.click(timeout=ctx.timeout_ms)

    async def input(self, loc: LocatorChain, text: str, ctx: ActionContext) -> None:
        el, _ = await self._find(loc, ctx, ctx.timeout_ms)
        await el.fill(text, timeout=ctx.timeout_ms)

    async def navigate(self, url: str, ctx: ActionContext) -> None:
        await self._page.goto(url, timeout=ctx.timeout_ms)
    # ... 其余动作略（实现清单见 §9 M1）
```

**二期预留的 WebView 接棒点**（`WebViewHandoff`）：

```python
class PlaywrightAdapter:
    async def attach_to_cdp(self, cdp_endpoint: str) -> None:
        """二期：接管 Appium 切出的 WebView。
        Appium 侧 switch_to_context('WEBVIEW_xxx') 后，从 chrome://inspect
        拿到 devtools endpoint，Playwright 用 CDP connect_over_cdp 接棒。"""
        self._browser = await self._pw.chromium.connect_over_cdp(cdp_endpoint)
        self._context = self._browser.contexts[0]
        self._page = self._context.pages[0]
```

> 这对应调研的扩展点 C：**rd 已有 `switch_to_context` 原语，但切完仍用 Appium 操作 WebView**。本方案的做法是「Appium 切 context → Playwright 用 CDP 接棒」，把两边的长处各用一次。

### 4.6 会话与生命周期（`SessionManager`）

| 场景 | 策略 |
|---|---|
| Web，用例间 | **复用** `browser`，每个用例新建 `context`（隔离 cookie/storage，且天然并发安全） |
| Web，用例内 | 复用同一个 `page`；`switch_to_page` 动作可切到新标签页 |
| App | driver 生命周期跟随 `execution`；**用例间是否重启由 `project.no_reset` 决定** |
| 失败重试 | 重试**不重建** session（除非错误类型 ∈ {`SESSION_CRASHED`, `DRIVER_DISCONNECTED`}） |
| **WebView（二期）** | ⚠️ **一次 execution 内可并存 2 个 adapter 实例**（主 Appium + 次 Playwright），由「上下文栈」管理。→ **一期必须保证 `SessionManager` 不是单例设计**，否则二期返工。详见配套文档《移动端对接方案》§4 与 §6 |
| 兜底 | 任何 `EngineError` 未捕获时，`stop()` 必须被执行（`try/finally` + 超时强杀） |

### 4.7 Android / iOS 适配器（一期为「桩」）

一期**只写接口实现骨架**，验证"新增引擎 = 加一个文件 + 注册"这条路径：

```python
# app/engines/adapters/appium_adapter.py
from app.engines.base import EngineAdapter, UnsupportedActionError
from app.engines.capabilities import CAPABILITY_MATRIX
from app.engines.registry import register

@register
class AppiumAdapter(EngineAdapter):
    key = "appium"
    platforms = frozenset({"ANDROID", "IOS"})
    capabilities = CAPABILITY_MATRIX["appium"]

    @classmethod
    def create(cls, target_options: dict) -> "AppiumAdapter":
        return cls(target_options)

    def start(self) -> None:
        raise NotImplementedError("Appium 适配器计划于 M4 实现（见 §9）")
    # ... 其余动作同样 raise NotImplementedError
```

> 一期验收时会有一条测试：**注册表能解析出 `appium`，且 `resolve('ANDROID', 'appium')` 成功、`resolve('WEB', 'appium')` 抛错**。这证明路由与注册机制已经工作，缺的只是实现。

---

## 5. 元素与定位符子系统

### 5.1 定位类型字典（受 `platform` 约束）

| platform | 允许的 `locator_type` | 说明 |
|---|---|---|
| `WEB` | `css` · `xpath` · `testid` · `role` · `text` · `placeholder` · `label` · `title` · `alt` · `id` · `class` | 与 MokaTest `element.locator_type` 的 11 种**对齐**（便于团队复用其心智），但只作为**候选之一**，不是全部。**桌面浏览器与移动浏览器共用同一套定位类型**（D5） |
| `ANDROID` | `resource_id` · `accessibility_id` · `uiautomator`（仅 appium）· `text` · `text_contains` · `class_name` · `xpath` | **语义归一**：`resource_id` 一条记录同时服务 Appium 与 u2（各自翻译成 `id=…` / `resourceId=…`）。仅 `uiautomator` 是 Appium 专属表达式，不可用于 `engine_key='*'` |
| `IOS` | `accessibility_id` · `predicate` · `class_chain` · `name` · `xpath` | **`xpath` 必须排最后**：iOS 上逐节点求值，复杂页面可慢到秒级。引擎只有 appium |

> **★ 本条已于 2026-10-19 修正（M2 §0.6 F-M2-1）**：原文的 `ANDROID` 允许值里混入了 **`-android uiautomator`(Appium)** 与 **`resourceId`(u2)**、`IOS` 混入了 **`-ios predicate string`(Appium)** —— 那是**引擎语汇**，不是**业务语义**。混入的后果是致命的：
>
> 1. 同一个「登录按钮」的 resource-id 是**同一条业务事实**，却被迫写成两条不同 `locator_type` 的记录 → **`engine_key='*'` 通配失去意义**，P2 的多端复用退化成"每端每引擎各配一份"；
> 2. 每接入一个 Android 引擎就要新增一个枚举值 → 正是 P1 要避免的"字段值爆炸"。
>
> **正确分层**：`locator_type` 只表达语义（入库），**引擎语汇的翻译发生在适配器内**（M1 的 `_to_selector` 早已对 Web 这么做 —— `testid` 并非 Playwright 的语汇，翻译成 `[data-testid="…"]` 才发生）。M2 只是把同一条原则贯彻到移动端。
>
> 同时字典从"一维（按 platform）"升级为"**二维（platform × engine）**"：每个类型声明 `engines` 集合，写入期据此拒绝"给 u2 配 `uiautomator`"。完整实现见《M2 详细设计》§2.5 与附录 B。

**校验落点**：`ElementService.upsert_locator()` 在写库前用本字典校验，拒绝"给 iOS 配 css 定位符"这类错误。字典以常量表实现（`app/domain/locator_types.py`），**不入库**——因为它是随引擎能力变化的代码事实，不是业务数据。

### 5.2 `LocatorResolver` —— 解析与回退链

```python
class LocatorResolver:
    def resolve(self, element_id: int, platform: str, engine_key: str) -> LocatorChain:
        """返回按优先级排序的回退链。精确匹配引擎的定位符排在通配 '*' 之前。"""
        rows = self._repo.find_locators(element_id, platform, engine_key)  # 已含 '*' 通配
        rows.sort(key=lambda r: (0 if r.engine_key == engine_key else 1, r.priority))
        return LocatorChain(
            element_id=element_id,
            locators=[Locator(type=r.locator_type, value=r.locator_value) for r in rows],
        )

    def resolve_optional(self, element_id: int | None, platform: str, engine_key: str) -> LocatorChain | None:
        if element_id is None:
            return None
        chain = self.resolve(element_id, platform, engine_key)
        if not chain:
            # 提前失败，附带"该元素已配了哪些端"的提示，便于修数据
            raise LocatorNotFoundError(
                f"元素 {element_id} 在 platform={platform}, engine={engine_key} 下无任何定位符；"
                f"已配置的端：{self._repo.list_platforms(element_id)}"
            )
        return chain
```

**回退链的排序示例**（元素 101，platform=ANDROID，engine=appium）：

| 顺序 | engine_key | priority | locator_type | 命中判定 |
|---|---|---|---|---|
| 1 | `appium`（精确） | 10 | `accessibility_id` | 首选，最稳 |
| 2 | `appium`（精确） | 100 | `-android uiautomator` | 回退 1 |
| 3 | `*`（通配） | 10 | `resource_id` | 回退 2 |
| 4 | `*`（通配） | 100 | `text` | 回退 3（最不稳） |

### 5.3 定位稳定性度量（为二期自愈打基础）

由 `execution_step_result.used_locator_id` + `fallback_index` 聚合出：

```
元素 101 · ANDROID · appium
  accessibility_id=loginButton     命中 142 次（首选命中 138）  成功率 97.2%  → 稳定
  -android uiautomator=...         命中   6 次（均为回退）       成功率  4.2%  → 建议降权/替换
```

二期可据此**自动调整 `priority`** 或触发**自愈建议**（参考 MokaTest 的 `AiLocatorHealService` 思路，但本方案选择"先度量、后自愈"的路径）。

---

## 6. 用例执行链路

### 6.1 端到端链路

```
[前端] 勾选用例 → POST /executions
   ▼
[L3] ExecutionService.create()
   ├─ 快照 project.platform / engine_key / target.options  → execution 行（PENDING）
   ├─ 展开 case_ids（含步骤、元素）→ 组装 ActionPlan
   └─ 投递进程内队列（asyncio.Queue + Semaphore，单进程语义；D23/D26 —— 原设计为 Redis 队列）
   ▼
[L2] Worker 消费
   ├─ registry.resolve(platform, engine_key) → AdapterClass
   ├─ adapter = AdapterClass.create(options); adapter.start()
   ├─ for case in plan:
   │     for step in case.steps:
   │         chain = LocatorResolver.resolve_optional(step.element_id, platform, engine_key)
   │         result = await dispatch(step.action_key, adapter, chain, ctx)
   │         persist execution_step_result   （含 used_locator_id / fallback_index）
   │         publish ws event "step.finished"
   └─ adapter.stop()
   ▼
[L3] ReportService.aggregate(execution_id)
   ├─ 汇总 pass_rate、失败类型分布
   ├─ 收集 artifact（截图/视频/trace）
   └─ 生成 report 行 + 通知（钉钉/企业微信，按 project.notify_type）
   ▼
[前端] 实时看板（WebSocket）/ 报告页
```

### 6.2 执行状态机

```
              ┌─────────┐
              │ PENDING │
              └────┬────┘
                   │ worker 领取
                   ▼
   ┌──────────► RUNNING ──────────┐
   │               │              │ 全部用例完成
   │ 取消           │ 引擎崩溃      ▼
   │               ▼         ┌──────────┐
CANCELLED      ┌────────┐   │ 判定汇总 │
               │ ERROR  │   └────┬─────┘
               └────────┘        │
                          ┌──────┴──────┐
                          ▼             ▼
                     ┌────────┐   ┌────────┐
                     │ PASSED │   │ FAILED │
                     └────────┘   └────────┘
```

**用例级状态**（由步骤结果推导，独立于批次状态）：

| 用例状态 | 判据 |
|---|---|
| `PASSED` | 所有 `enabled` 步骤均 `PASSED` |
| `FAILED` | 存在 `FAILED`，且 `expected_fail=0`（或反之） |
| `ERROR` | 存在 `ERROR`（引擎层异常，非断言失败） |
| `SKIPPED` | `state=0` 或前置步骤 `ABORT` 导致未执行 |

> **断言失败（FAILED）与引擎异常（ERROR）必须分开统计** —— 这是工程上最重要的区分：前者是"产品有 bug"，后者是"测试代码/环境有问题"。rd 的 `update_test_status` 只用一个 `state` 字段，容易混淆。

### 6.3 并发模型

| 层级 | 并发方式 | 说明 |
|---|---|---|
| 批次 | 一个 `execution` 一个 worker | 避免同一浏览器/设备被抢占 |
| 用例 | `project.threads` 控制协程并发 | Web 场景下每用例独立 `context`，天然隔离 |
| 项目间 | 进程内队列 + `Semaphore(max_concurrent_executions=2)`（D23） | 多 worker/多实例才需要 Redis，目前明确不做 |

**一期限制**：Web 场景 `threads` 建议 ≤ 4（受内存与 Chromium 实例数限制）。App 场景（二期）需按"设备数"限制，不能用 `threads` 直接控制 —— 这一约束在二期文档里给出。

### 6.4 实时进度（WebSocket）

| 事件 | 载荷 |
|---|---|
| `execution.started` | `{execution_id, total, platform, engine_key}` |
| `case.started` | `{execution_id, case_id, title}` |
| `step.finished` | `{execution_id, case_id, seq, action_key, status, fallback_index, duration_ms}` |
| `case.finished` | `{execution_id, case_id, status, duration_ms}` |
| `execution.finished` | `{execution_id, status, passed, failed, errored, pass_rate}` |

通道设计：`/ws/executions/{execution_id}`（单批次订阅）+ `/ws/projects/{project_id}`（项目级汇总）。**实现为同进程事件总线**（D24）：跨进程收不到 WS，前端另有 5s 轮询兜底；原设想的 Redis Pub/Sub 随 D23 一并放弃。

---

## 7. 报告与产物

| 产物 | 一期 | 说明 |
|---|---|---|
| **HTML 报告** | ✅ | 自渲染（Vue 页）+ 可选导出 Allure 静态包 |
| **JUnit XML** | ✅ | 供 CI 集成 |
| **截图** | ✅ 每步失败自动截图；`screenshot` 动作显式截图 |
| **录屏** | 🟡 用例级开关（`test_case.record_video`），Web 用 Playwright `record_video_dir` |
| **trace** | 🟡 Playwright trace（`context.tracing`），仅失败用例保留 |
| **DOM / page source** | ✅ 失败时抓取，存 `artifact` |

存储：一期 `LOCAL`（`artifacts/{execution_id}/...`），`artifact.storage` 已预留 `MINIO`/`S3`。

---

## 8. 平台自身代码结构（FastAPI + Vue 3）

```
ui-test-platform/
├─ backend/
│  ├─ app/
│  │  ├─ main.py                    # FastAPI 入口
│  │  ├─ core/                      # config(pydantic-settings) / db / security / logging
│  │  ├─ api/                       # L3 路由层（HTTP）
│  │  │  ├─ projects.py  elements.py  cases.py  executions.py  reports.py  actions.py
│  │  │  └─ ws.py
│  │  ├─ schemas/                   # Pydantic DTO
│  │  ├─ models/                    # SQLAlchemy ORM
│  │  ├─ services/                  # L3 业务层（禁止 import 引擎库）
│  │  │  ├─ project_service.py  element_service.py  case_service.py
│  │  │  ├─ execution_service.py  report_service.py
│  │  │  └─ notification/           # 钉钉 / 企业微信
│  │  ├─ domain/                    # 纯领域：locator_types.py / action_keys.py
│  │  ├─ engines/                   # ★ L2 适配层
│  │  │  ├─ base.py                 # EngineAdapter / Locator / ActionContext / 异常
│  │  │  ├─ registry.py             # 注册表 + resolve()
│  │  │  ├─ capabilities.py         # 能力矩阵 + 一致性自检
│  │  │  ├─ resolver.py             # LocatorResolver
│  │  │  ├─ session.py              # SessionManager
│  │  │  ├─ actions.py              # 动作分发器（平台内建动作在此）
│  │  │  └─ adapters/
│  │  │     ├─ __init__.py          # 唯一注册点
│  │  │     ├─ playwright_adapter.py
│  │  │     ├─ appium_adapter.py     # 桩
│  │  │     └─ uiautomator2_adapter.py  # 桩
│  │  ├─ runner/                    # L3 执行器 + 调度
│  │  │  ├─ worker.py  scheduler.py  plan.py
│  │  └─ ws/                        # 实时推送 hub
│  ├─ sql/
│  │  ├─ schema.sql                 # 本方案 §3 的 DDL
│  │  └─ seed_action_catalog.sql    # §3.2.5 种子数据
│  ├─ tests/
│  │  ├─ unit/                      # 含 FakeAdapter 驱动的执行器测试
│  │  └─ e2e/                       # Playwright 打本地 fixtures 页面
│  ├─ pyproject.toml
│  └─ importlinter.ini              # 强制"L3 不得 import 引擎库"红线
└─ frontend/
   ├─ src/
   │  ├─ api/  stores/  router/
   │  ├─ views/{Projects,ElementLibrary,CaseEditor,ExecutionBoard,Reports}
   │  └─ components/StepEditor/      # 由 action_catalog 驱动渲染
   └─ vite.config.ts
```

**关键依赖**：

```toml
[tool.poetry.dependencies]
python = "^3.11"
fastapi = "^0.115"
uvicorn = {extras = ["standard"], version = "^0.32"}
sqlalchemy = "^2.0"
aiomysql = "^0.2"
alembic = "^1.13"
pydantic = "^2.9"
pydantic-settings = "^2.6"
# 原设计含 redis = "^5.2"，已按 D23 移除
apscheduler = "^3.10"
playwright = "^1.51"
# 二期：Appium-Python-Client = "^4.0"; uiautomator2 = "^3.5"
jinja2 = "^3.1"
```

---

## 9. 一期实施计划（里程碑）

| 里程碑 | 交付物 | 验收标准 |
|---|---|---|
| **M1 · 骨架与适配层** | 项目脚手架；`sql/schema.sql` 全表；`engines/base.py` + `registry.py` + `capabilities.py`；**PlaywrightAdapter 完整实现**；`importlinter` 红线生效 | ① `python -m pytest tests/unit` 通过；② 用一段硬编码 ActionPlan 驱动 Playwright 跑通一个真实页面（导航/输入/点击/取文本/截图）；③ `resolve('ANDROID','appium')` 成功、`resolve('WEB','appium')` 抛错；④ import-linter 校验通过 |
| **M2 · 元素库与多端 Locator** | `element` + `element_locator` 的 CRUD API 与 UI（含树形、拖拽排序）；`LocatorResolver` 回退链；定位类型校验 | ① 同一元素配 Web/Android/iOS 三套定位符；② Web 用例改用 `element_id` 引用后仍跑通；③ 故意把首选定位符写错，验证自动回退到第 2 条并在结果里记录 `fallback_index=1` |
| **M3 · 编排 / 执行 / 报告** | `action_catalog` 种子数据 + 前端 StepEditor（由字典驱动）；`ExecutionService` + Redis 队列 + `SessionManager`；WebSocket 实时推送；HTML + JUnit 报告；失败截图/DOM | ① 图形化编排出 ≥ 5 步用例并执行成功；② 看板实时步进；③ 报告可下载，含失败截图与 DOM；④ 通知（钉钉/企业微信）可发送 |
| **M4 · 扩端（二期，Android 已交付）** | AppiumAdapter 实现 + 真机环境；**M4.1（平台侧 + 用例固化）/ M4.2（手势、上下文、执行加固）已完成**（见 `UI自动化平台M4详细设计.md`）；iOS（云真机）+ WebView 内部元素待 M4.3/GAP-47。**详细设计见《移动端对接方案》+《M4 详细设计》** | ① 同一用例在 `engine_key=uiautomator2` 与 `appium` 下用各自的 `element_locator` 均能跑通（验证 P2 的价值）；② WebView 场景：Appium 切 context → Playwright 通过 CDP 接棒完成 WebView 内操作 |

**建议节奏**：M1 → M2 是关键路径（架构定型），M3 是体量最大的一块，M4 在 M1–M3 稳定后启动。**实际执行**：M4.1/M4.2 已于 2026-11-08 交付 Android 侧。

> **M4 的详细方案已单独成文**：《UI自动化平台 · 移动端对接方案（Android / iOS / WebView）》+《UI自动化平台 M4 详细设计》。**Android 部分已于 2026-11-08 实现**，D1a 剩下的作用是：① 确保 M1–M3 的实现不挡住二期（见该文档第 6 节「对一期的依赖清单」）；② 二期启动时无需重新调研。

---

## 10. 测试与验收策略

| 层 | 方式 | 说明 |
|---|---|---|
| `engines/base` 契约 | **契约测试**：同一套测试用例跑所有 adapter | 用 `FakeAdapter` 先立契约；PlaywrightAdapter 通过后才算 M1 完成 |
| `LocatorResolver` | 单元测试 + 表驱动 | 覆盖：精确 vs 通配排序、回退链、无定位符报错、platform 不匹配 |
| 能力矩阵一致性 | 启动自检 + 单测 | `action_catalog.engines` ↔ `CAPABILITY_MATRIX` 双向一致 |
| 执行链路 | 用 `FakeAdapter` 驱动 `ExecutionService` | 断言状态机流转、`FAILED` vs `ERROR` 区分、`on_failure` 语义 |
| 真实 Web | `tests/e2e` 起本地 fixture 页面 | 不依赖外网；覆盖 iframe、新标签页、上传、alert |
| **架构红线** | `import-linter` 在 CI 执行 | L3 `services` 层不得 import `playwright`/`appium`/`engines.adapters` |

---

## 11. 风险与对策

| # | 风险 | 等级 | 对策 |
|---|---|---|---|
| RK1 | 自建工作量大于预期 | 🟡 | 用 `action_catalog` 驱动前端与校验（少写一套表单代码）；一期严格限定 Web |
| RK2 | 定位符脆弱导致用例大面积失败 | 🔴 | 回退链 + `fallback_index` 埋点；M2 验收即包含"故意写错验证回退"；二期做优先级自动调优 |
| RK3 | 能力不对称被忽略（选了动作但引擎不支持） | 🟡 | `CAPABILITY_MATRIX` 唯一事实来源 + 启动强校验 + 执行前前置校验（§4.3） |
| RK4 | Android 双引擎（Appium/u2）定位符维护量翻倍 | 🟡 | `element_locator.engine_key` 维度（本次建模修正的直接收益）；建议**一期二选一**（推荐 Appium，能力更全） |
| RK5 | 引擎库依赖泄漏到业务层 | 🟡 | `import-linter` 强制；code review checklist |
| RK6 | iOS 环境依赖 macOS / 云真机（R7） | 🟡 | 一期不做 iOS；二期按附录 B.4 三方案决策，推荐云真机起步 |
| RK7 | 步骤 JSON 过于自由，导致数据质量差 | 🟡 | `action_catalog.params_schema`（JSON Schema）在写入时强校验 |
| RK8 | 上游参考项目的缺陷被无意引入 | 🟢 | 已识别并规避：rd 的重复列/错别字枚举、路由隐式推断、无元素表；MokaTest 的单端定位符（详见附录 C） |
| RK9 | 并发下浏览器/设备资源争抢 | 🟡 | 一期 `threads ≤ 4`；`SessionManager` 保证每用例独立 context；二期按设备数限流 |
| RK10 | 文档与代码脱节（用户明确要求二者一致） | 🟢 | 里程碑完成时同步更新本文档与 `schema.sql`；`schema.sql` 为唯一 DDL 事实来源，本文档引用它 |

---

## 12. 附录

### 12.1 术语表

| 术语 | 含义 |
|---|---|
| **端 / platform** | 业务维度，仅 3 个取值：`WEB` / `ANDROID` / `IOS`（D5，不含 WAP） |
| **引擎 / engine_key** | 技术维度：`playwright` / `appium` / `uiautomator2` |
| **执行目标 / target** | 一次执行的环境配置（浏览器规格或设备 caps） |
| **逻辑元素 / element** | 与引擎无关的元素抽象，如「登录按钮」 |
| **定位符 / locator** | 逻辑元素在「某端 × 某引擎」下的具体定位表达式 |
| **回退链 / locator chain** | 一个元素在某端某引擎下的多条定位符，按优先级依次尝试 |
| **动作 / action** | 引擎无关的操作语汇，如 `click` / `input` / `switch_to_context` |
| **能力矩阵 / capability matrix** | 每个引擎支持哪些动作的声明表 |
| **适配器 / adapter** | 把统一动作翻译成具体引擎调用的实现 |

### 12.2 与需求简报的对应关系

| 简报中的期望模型 | 本方案落点 | 备注 |
|---|---|---|
| Project（绑定端类型） | `project.platform` + `project.engine_key` | **显式两字段**（简报只写"绑定端类型"） |
| Element（逻辑元素） | `element`（树形） | 借鉴 MokaTest 树形 + 共享/私有 |
| Locator（多端定位符映射） | **`element_locator`（platform × engine）** | ★ 本方案核心创新，简报未提 engine 维度 |
| TestCase | `test_case` | 无 `project_type`（从 project 继承） |
| Step / Action | `test_step` + `action_catalog` | 动作语汇统一，参数走 JSON Schema |
| Execution / Target | `execution` + `execution_target` | 执行时快照 platform/engine，便于回溯 |
| Engine Adapter | `EngineAdapter` Protocol + 注册表 | 借鉴 Pilot 接口形状；含能力矩阵 |
| Report | `report` + `artifact` + `execution_step_result` | 含 `FAILED`/`ERROR` 分离与定位符埋点 |

### 12.3 与选型报告结论的对应（可追溯）

| 本方案的设计 | 依据 |
|---|---|
| 显式 `platform` + `engine_key`（P1） | 附录 C.6（rd 路由判据自相矛盾） |
| `element_locator` 带 `engine_key` 维度（P2） | 附录 C.2（Android 双路径定位语汇不同） |
| `CAPABILITY_MATRIX` + 启动强校验（P3） | 附录 C.4（iOS 30 / Android 18 动作集不对称） |
| `action_catalog` 统一动作字典（P4） | 附录 C.4（rd 已有跨引擎动作字典，改造量下调） |
| WebView 走「Appium 切 context → Playwright CDP 接棒」（§4.5） | 附录 C.5（原语已有、编排缺失） |
| 不照搬 MokaTest 元素表（§3.2.3 注） | 附录 C.3（MokaTest 是单端单定位符） |
| 一期仅 Web + 适配器骨架 | 附录 B.6 推进顺序 + 决策 D3 |
| 不搬运上游缺陷（P5） | 附录 C.4（重复 `type` 列）、C.7（错别字枚举） |

### 12.4 待办与下一份文档

**本篇未覆盖（D4 明确排除，待下一份）**：

1. **REST API 契约**（OpenAPI 定义、错误码表、分页规范）→ 🟡 **M1 范围内的部分已在《M1 详细设计》§3 定义**（通用规范 + 错误体 + 16 个端点 + 错误码表）；M2/M3 的增量契约待写；
2. **前端页面与交互清单**（元素库树形交互、StepEditor 表单、看板布局）；
3. **部署方案**：Docker Compose、环境变量、数据初始化与迁移（Alembic）。

**已单独成文（本篇的配套文档）**：

| 文档 | 内容 | 状态 |
|---|---|---|
| **《UI自动化平台 · 移动端对接方案（Android / iOS / WebView）》** | Appium / uiautomator2 适配器实现清单、AVD 与云真机环境、iOS 三方案、WebView 接棒编排、二期里程碑与验收 | ✅ 已编写，**按决策"不着急实现"**，作为预留对接方案 |
| **《UI自动化平台 M1 详细设计》**（D2-M1） | M1 施工图：逐文件设计 · 接口签名冻结（17 条）· 51 条动作字典种子 · DDL 冻结版 · 9 条可执行验收标准 · 附录 D 待实测清单 | ✅ 已编写（v1.1，评审通过） |
| **《UI自动化平台 M2 详细设计》**（D2-M2） | M2 施工图：三端定位字典（语义/语汇分层）· 树形模型与 path 维护 · 定位符验证器 · 18 个端点 · 元素库三栏前端 · 10 条验收标准 | ✅ 已编写（v1.0，待评审） |
| **《UI自动化平台 M3 / M4 详细设计》**（D2-M3/M4） | 编排执行报告 / 扩端 | ✅ D2-M3 与 D2-M4 均已编写并落地（M4.1/M4.2 已实现） |

**需要实测才能确认的事（不阻塞本篇）**：

| 事项 | 说明 |
|---|---|
| Playwright 对 `role` / `testid` 的实际匹配行为 | M1 期间以本地 fixture 页面实测，必要时修正 §4.5 的 `_to_selector` |
| 移动浏览器（原 WAP）的仿真参数取值 | D5 已确定不再作为独立端；需实测 Playwright `device` 描述符覆盖的机型范围，决定 `execution_target` 的预置清单 |
| 并发上限 | M3 期间实测 `threads` 与 AVD/内存的关系 |

---

*— 文档结束 —*
*DDL 事实来源：`backend/sql/schema.sql`（实现后以该文件为准）*
